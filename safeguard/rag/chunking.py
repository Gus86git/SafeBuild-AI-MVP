"""Stable, page-local chunks with paragraph and sentence boundaries."""

from hashlib import sha256
import json
import re

CONFIG = {"max_chars": 900, "overlap": 120, "algorithm": "paragraph-page-v2"}


def split_text(text, max_chars=900, overlap=120):
    if max_chars < 100 or not 0 <= overlap < max_chars // 2:
        raise ValueError("Configuración de fragmentación inválida.")
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            candidates = [
                m.end() for m in re.finditer(r"\n\n|[.;]\s|\s", text[start:end])
            ]
            candidates = [x for x in candidates if x >= max_chars // 2]
            if candidates:
                end = start + candidates[-1]
        segment = text[start:end].strip()
        if segment:
            yield segment
        if end == len(text):
            break
        next_start = max(start + 1, end - overlap)
        while next_start < end and not text[next_start - 1].isspace():
            next_start += 1
        start = next_start


def chunks_for(document, extracted, config=None):
    config = config or CONFIG
    chunks = []
    units, pending = [], []

    def flush():
        if pending:
            units.append(
                {
                    "page_number": None,
                    "locator": pending[0]["locator"]
                    + (" a " + pending[-1]["locator"] if len(pending) > 1 else ""),
                    "text": "\n\n".join(u["text"] for u in pending),
                }
            )
            pending.clear()

    for unit in extracted["units"]:
        if unit["page_number"] is not None:
            flush()
            units.append(unit)
        else:
            if (
                sum(len(u["text"]) + 2 for u in pending) + len(unit["text"])
                > config["max_chars"]
            ):
                flush()
            pending.append(unit)
    flush()
    for unit in units:
        for index, text in enumerate(
            split_text(unit["text"], config["max_chars"], config["overlap"])
        ):
            identity = [
                document["document_id"],
                extracted["sha256"],
                unit["locator"],
                index,
                text,
                config,
            ]
            identifier = sha256(
                json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            chunks.append(
                {
                    **{
                        k: document.get(k)
                        for k in (
                            "document_id",
                            "title",
                            "source_type",
                            "source_url",
                            "source_url_verified",
                            "organization",
                            "document_version",
                            "is_synthetic",
                            "content_status",
                        )
                    },
                    "chunk_id": identifier,
                    "page_number": unit["page_number"],
                    "locator": unit["locator"],
                    "chunk_index": index,
                    "text": text,
                    "document_sha256": extracted["sha256"],
                }
            )
    return chunks
