"""Bounded extraction from explicitly catalogued files. Never executes document content."""

from hashlib import sha256
from pathlib import Path
import re
import unicodedata
from zipfile import ZipFile
from xml.etree import ElementTree as ET

SOURCE_TYPES = (
    "official",
    "technical_guide",
    "simulated_manual",
    "simulated_procedure",
    "authorized_other",
)
MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 500
MAX_CHARS = 2_000_000
OCR_MESSAGE = "Este documento requiere extracción OCR o una versión digital accesible"


class DocumentError(ValueError):
    pass


def normalize(text):
    text = unicodedata.normalize("NFC", text).replace("\x00", "")
    return "\n\n".join(
        " ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()
    )


def safe_path(root, filename):
    root = Path(root).resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root) or path == root:
        raise DocumentError("Ruta documental fuera del corpus autorizado.")
    return path


def reject_secrets(text):
    patterns = [
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"\b(?:gsk_|sk-proj-|hf_)[A-Za-z0-9_-]{20,}",
        r'(?i)(?:api[_ -]?key|token|password|secret)\s*[:=]\s*["\']?[A-Za-z0-9_/-]{16,}',
    ]
    if any(re.search(p, text) for p in patterns):
        raise DocumentError(
            "Contenido con posible credencial: excluido; requiere revisión local."
        )


def extract(path, max_bytes=MAX_BYTES, max_pages=MAX_PAGES, max_chars=MAX_CHARS):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise DocumentError("Archivo ausente o demasiado grande.")
    raw = path.read_bytes()
    units, empty, warnings = [], [], []
    suffix = path.suffix.lower()
    page_count = None
    try:
        if suffix == ".pdf":
            if not raw.startswith(b"%PDF-"):
                raise DocumentError("Cabecera PDF inválida.")
            from pypdf import PdfReader
            from io import BytesIO

            reader = PdfReader(BytesIO(raw), strict=True)
            if reader.is_encrypted:
                raise DocumentError("PDF cifrado: no se procesa.")
            page_count = len(reader.pages)
            if not 0 < page_count <= max_pages:
                raise DocumentError("Número de páginas fuera del límite.")
            for n, page in enumerate(reader.pages, 1):
                # Bound decompressed streams before invoking layout/text extraction.
                contents = page.get_contents()
                if contents and len(contents.get_data()) > 10 * 1024 * 1024:
                    raise DocumentError(
                        "Página demasiado compleja para la extracción local."
                    )
                text = normalize(page.extract_text() or "")
                if len(re.findall(r"\w", text)) < 20:
                    empty.append(n)
                else:
                    units.append(
                        {"page_number": n, "locator": f"Página PDF {n}", "text": text}
                    )
            if not units:
                raise DocumentError(OCR_MESSAGE)
            if empty:
                warnings.append("Páginas sin texto útil: " + ", ".join(map(str, empty)))
        elif suffix == ".docx":
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            with ZipFile(path) as archive:
                if sum(i.file_size for i in archive.infolist()) > 40 * 1024 * 1024:
                    raise DocumentError("DOCX expandido demasiado grande.")
                xml = archive.read("word/document.xml")
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                    raise DocumentError("Entidades XML no permitidas.")
                tree = ET.fromstring(xml)
                for n, para in enumerate(tree.findall(".//w:body//w:p", ns), 1):
                    text = normalize(
                        "".join(t.text or "" for t in para.findall(".//w:t", ns))
                    )
                    if text:
                        units.append(
                            {
                                "page_number": None,
                                "locator": f"Párrafo DOCX {n}",
                                "text": text,
                            }
                        )
                media = [
                    i.filename
                    for i in archive.infolist()
                    if i.filename.startswith("word/media/")
                ]
                if media:
                    warnings.append(
                        "Imágenes incrustadas sin OCR; pueden contener anexos no extraídos."
                    )
                warnings.append(
                    "DOCX: sin paginación física verificada; se citan párrafos en orden XML."
                )
        elif suffix in (".md", ".txt"):
            text = raw.decode("utf-8-sig")
            for n, block in enumerate(re.split(r"\n\s*\n", text), 1):
                if block.strip():
                    units.append(
                        {
                            "page_number": None,
                            "locator": f"Bloque de texto {n}",
                            "text": normalize(block),
                        }
                    )
        else:
            raise DocumentError("Formato no autorizado: use PDF, DOCX, Markdown o TXT.")
    except DocumentError:
        raise
    except (Exception,) as exc:
        raise DocumentError(
            f"Extracción fallida ({type(exc).__name__}); archivo no indexado."
        ) from exc
    total = sum(len(u["text"]) for u in units)
    if not total or total > max_chars:
        raise DocumentError("Contenido vacío o superior al límite de extracción.")
    reject_secrets("\n".join(u["text"] for u in units))
    return {
        "sha256": sha256(raw).hexdigest(),
        "page_count": page_count,
        "units": units,
        "empty_pages": empty,
        "warnings": warnings,
        "characters": total,
    }
