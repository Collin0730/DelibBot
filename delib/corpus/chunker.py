"""Paragraph-aware chunking that keeps each chunk's page/timestamp locator."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .loaders import Document


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    kind: str
    locator: str
    text: str
    agenda_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def cite_label(self) -> str:
        return f"{self.title}, {self.locator}" if self.locator else self.title


def _paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    for p in paras:
        # PDFs often lack blank lines; split very long blocks on sentences.
        if len(p.split()) > 400:
            out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", p) if s.strip())
        else:
            out.append(p)
    return out


def chunk_document(doc: Document, target_words: int = 220, overlap_words: int = 40) -> list[Chunk]:
    chunks: list[Chunk] = []
    n = 0
    for seg in doc.segments:
        buf: list[str] = []
        count = 0
        for para in _paragraphs(seg.text):
            words = len(para.split())
            if buf and count + words > target_words:
                chunks.append(_make(doc, seg.locator, buf, n))
                n += 1
                tail = " ".join(" ".join(buf).split()[-overlap_words:]) if overlap_words else ""
                buf, count = ([tail] if tail else []), len(tail.split())
            buf.append(para)
            count += words
        if buf and count > 0:
            chunks.append(_make(doc, seg.locator, buf, n))
            n += 1
    return chunks


def _make(doc: Document, locator: str, buf: list[str], n: int) -> Chunk:
    return Chunk(
        chunk_id=f"{doc.doc_id}#{n}",
        doc_id=doc.doc_id,
        title=doc.title,
        kind=doc.kind,
        locator=locator,
        text="\n".join(buf).strip(),
        agenda_items=list(doc.agenda_items),
    )
