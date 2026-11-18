"""Turn an uploaded file into text and retrieval chunks. The original file is not kept."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from delib.corpus.chunker import chunk_document
from delib.corpus.loaders import Document as LoadedDocument
from delib.corpus.loaders import load_file

from . import models as m

SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".vtt", ".srt"}


def clean_name(name: str) -> str:
    return Path((name or "document").replace("\\", "/")).name[:200] or "document"


def ingest(file_name: str, data: bytes) -> m.Document:
    ext = Path(file_name).suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"{file_name}: this file type is not supported. Use PDF, Word, text, Markdown, HTML or captions (VTT, SRT).")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ("upload" + ext)
        path.write_bytes(data)
        segments = load_file(path)
    for s in segments:
        s.text = s.text.replace("\x00", "")  # Postgres text cannot hold NUL bytes
    loaded = LoadedDocument(doc_id="d", title=Path(file_name).stem, kind="briefing", source_path=file_name, segments=segments)
    text = loaded.text.strip()
    if not text:
        raise ValueError(f"{file_name}: no readable text found. Scanned PDFs need OCR first.")
    doc = m.Document(file_name=file_name, file_ext=ext.lstrip("."), sha256=hashlib.sha256(data).hexdigest(), content=text, char_count=len(text), indexed_at=m.now())
    for i, c in enumerate(chunk_document(loaded)):
        doc.chunks.append(m.DocumentChunk(seq=i, locator=c.locator or "", text=c.text))
    return doc
