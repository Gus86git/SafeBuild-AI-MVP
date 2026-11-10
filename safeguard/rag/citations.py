"""Citations are derived only from retrieved metadata, not generated text."""

from urllib.parse import urlsplit

LABELS = {
    "official": "Normativa oficial · copia aportada",
    "technical_guide": "Guía técnica",
    "simulated_manual": "Documento ficticio de TechCorp · manual",
    "simulated_procedure": "Documento ficticio de TechCorp · procedimiento",
    "authorized_other": "Otro documento autorizado",
}


def safe_url(chunk):
    value = chunk.get("source_url") or ""
    try:
        url = urlsplit(value)
        if (
            chunk.get("source_url_verified") is True
            and url.scheme == "https"
            and url.hostname
            in ("www.argentina.gob.ar", "www.ilo.org", "www.boletinoficial.gob.ar")
            and not url.username
            and not url.password
            and url.port in (None, 443)
            and not any(ord(c) < 32 for c in value)
        ):
            return value
    except ValueError:
        pass
    return None


def citation(chunk):
    location = (
        f"Página PDF {chunk['page_number']}"
        if chunk.get("page_number")
        else chunk["locator"]
    )
    return f"{chunk['title']} | {chunk.get('organization') or 'Organismo no informado'} | {location} | Fragmento {chunk['chunk_id']} | {LABELS[chunk['source_type']]} | Versión: {chunk.get('document_version') or 'no verificada'}"
