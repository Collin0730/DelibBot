"""Load source material into plain-text segments with locators for citation.

Supported: .pdf, .docx, .txt, .md, .html/.htm, .vtt, .srt
Each segment carries a locator (page number, or a timestamp for transcripts)
so the coach can cite where a claim came from.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".vtt", ".srt"}


@dataclass
class Segment:
    text: str
    locator: str = ""  # "p. 3", "00:12:04", or ""


@dataclass
class Document:
    doc_id: str
    title: str
    kind: str
    source_path: str
    segments: list[Segment] = field(default_factory=list)
    agenda_items: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.segments)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "doc"


def load_file(path: Path) -> list[Segment]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _load_pdf(path)
    if ext == ".docx":
        return _load_docx(path)
    if ext in {".txt", ".md"}:
        return [Segment(_read_text(path))]
    if ext in {".html", ".htm"}:
        return [Segment(_html_to_text(_read_text(path)))]
    if ext in {".vtt", ".srt"}:
        return _load_captions(_read_text(path))
    raise ValueError(f"Unsupported file type: {path.name}")


def _read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def _load_pdf(path: Path) -> list[Segment]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    segs = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            segs.append(Segment(_clean_pdf_text(text), f"p. {i}"))
    return segs


def _clean_pdf_text(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join hyphenated line breaks
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _load_docx(path: Path) -> list[Segment]:
    import docx

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return [Segment("\n\n".join(parts))]


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "noscript"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(?m)^\s*#\s*$", "", text)  # lone anchor markers left by some CMSs
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def html_title(path: Path) -> str | None:
    """Page <title>, minus a trailing " - Site Name" segment if present."""
    if path.suffix.lower() not in {".html", ".htm"}:
        return None
    m = re.search(r"<title[^>]*>(.*?)</title>", _read_text(path), re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    title = html.unescape(" ".join(m.group(1).split()))
    if " - " in title:
        title = title.rsplit(" - ", 1)[0]
    return title or None


_TS = re.compile(r"(\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}\s*-->\s*(\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}.*")


def _load_captions(raw: str) -> list[Segment]:
    """Collapse WebVTT/SRT cues into ~1 minute blocks stamped with start time."""
    segs: list[Segment] = []
    buf: list[str] = []
    block_start = ""
    current = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or line.isdigit() or line.startswith("NOTE"):
            continue
        if _TS.match(line):
            current = line.split("-->")[0].strip().split(".")[0].split(",")[0]
            if not block_start:
                block_start = current
            elif _seconds(current) - _seconds(block_start) >= 60 and buf:
                segs.append(Segment(" ".join(buf), block_start))
                buf, block_start = [], current
            continue
        line = re.sub(r"<v\s+([^>]+)>", r"\1: ", line)  # VTT speaker tags
        line = re.sub(r"<[^>]+>", "", line)
        buf.append(line)
    if buf:
        segs.append(Segment(" ".join(buf), block_start))
    return segs


def _seconds(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s
