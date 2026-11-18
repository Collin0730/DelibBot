"""Retrieval over deliberation materials.

* BM25 lexical retrieval, pure Python, always on (no extra dependencies).
* Optional dense retrieval through any adapter that implements ``embed``.
* When both are on, results are fused with Reciprocal Rank Fusion.

The index is cached as JSON under ``.delib_cache/<deliberation id>/``.
"""

from __future__ import annotations

import glob
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..config import DeliberationConfig
from ..llm.base import LLMClient
from .chunker import Chunk, chunk_document
from .loaders import SUPPORTED, Document, Segment, html_title, load_file, slugify

_STOP = set(
    """a an and are as at be but by for from has have he her his i if in into is it its
    me my of on or our she so that the their them there these they this to was we were
    what when which who will with you your not no do does did can could would should
    about than then also just more most very""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")


def _stem(t: str) -> str:
    """Tiny suffix stripper: enough to match closes/closed/closing/closure."""
    if len(t) > 4 and t.endswith(("ies", "ied")):
        return t[:-3] + "y"
    for suf in ("ations", "ation", "ingly", "ings", "ing", "ures", "ure", "es", "ed", "ly", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t[:-1] if len(t) > 4 and t.endswith("e") else t


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


@dataclass
class Hit:
    chunk: Chunk
    score: float


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = (sum(self.len) / len(self.len)) if docs else 0.0
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf, ln in zip(self.tf, self.len):
            s = 0.0
            for t in query:
                if t not in tf:
                    continue
                f = tf[t]
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / (self.avg or 1)))
            out.append(s)
        return out


class MaterialIndex:
    def __init__(self, chunks: list[Chunk], embeddings: list[list[float]] | None = None, embedder: LLMClient | None = None):
        self.chunks = chunks
        self.by_id = {c.chunk_id: c for c in chunks}
        self.bm25 = BM25([tokenize(f"{c.title} {c.text}") for c in chunks])
        self.embeddings = embeddings
        self.embedder = embedder

    # ---- building ----------------------------------------------------------
    @classmethod
    def build(
        cls,
        config: DeliberationConfig,
        embedder: LLMClient | None = None,
        cache_dir: str | Path | None = ".delib_cache",
        rebuild: bool = False,
    ) -> "MaterialIndex":
        docs = load_documents(config)
        if not docs:
            raise FileNotFoundError(
                f"No materials found for '{config.id}'. Check the 'materials' paths in the config "
                f"(resolved relative to {config.base_dir})."
            )
        fingerprint = _fingerprint(docs, embedder)
        cache = Path(cache_dir) / config.id if cache_dir else None
        if cache and not rebuild and (cache / "index.json").exists():
            data = json.loads((cache / "index.json").read_text(encoding="utf-8"))
            if data.get("fingerprint") == fingerprint:
                chunks = [Chunk(**c) for c in data["chunks"]]
                return cls(chunks, data.get("embeddings"), embedder)
        chunks = [c for d in docs for c in chunk_document(d)]
        embeddings = embedder.embed([f"{c.title}\n{c.text}" for c in chunks]) if embedder else None
        if cache:
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "index.json").write_text(
                json.dumps(
                    {"fingerprint": fingerprint, "chunks": [c.to_dict() for c in chunks], "embeddings": embeddings}
                ),
                encoding="utf-8",
            )
        return cls(chunks, embeddings, embedder)

    # ---- querying ------------------------------------------------------------
    def search(
        self, query: str, k: int = 5, agenda_item: str | None = None, max_per_doc: int | None = None
    ) -> list[Hit]:
        """Top-k chunks. ``max_per_doc`` caps chunks from any one source, so a
        single speaker or advocate cannot fill the whole context window."""
        ranked = self._ranked(query, agenda_item)
        if not max_per_doc:
            return ranked[:k]
        out: list[Hit] = []
        per_doc: Counter = Counter()
        for h in ranked:
            if per_doc[h.chunk.doc_id] < max_per_doc:
                out.append(h)
                per_doc[h.chunk.doc_id] += 1
                if len(out) == k:
                    break
        return out

    def _ranked(self, query: str, agenda_item: str | None) -> list[Hit]:
        if not self.chunks:
            return []
        pool = [
            i for i, c in enumerate(self.chunks)
            if not agenda_item or not c.agenda_items or agenda_item in c.agenda_items
        ] or list(range(len(self.chunks)))
        lex = self.bm25.scores(tokenize(query))
        lex_rank = sorted(pool, key=lambda i: -lex[i])
        if self.embeddings and self.embedder:
            qv = self.embedder.embed([query])[0]
            dense = {i: _cos(qv, self.embeddings[i]) for i in pool}
            dense_rank = sorted(pool, key=lambda i: -dense[i])
            fused: Counter = Counter()
            for rank_list in (lex_rank, dense_rank):
                for r, i in enumerate(rank_list):
                    fused[i] += 1.0 / (60 + r)
            order = [i for i, _ in fused.most_common()]
            return [Hit(self.chunks[i], fused[i]) for i in order]
        return [Hit(self.chunks[i], lex[i]) for i in lex_rank if lex[i] > 0]


def load_documents(config: DeliberationConfig) -> list[Document]:
    docs: list[Document] = []
    seen: set[str] = set()
    strip = [re.compile(pat, re.MULTILINE) for pat in config.strip_patterns]
    for src in config.materials:
        pattern = str(config.base_dir / src.path)
        matches = sorted(glob.glob(pattern, recursive=True))
        for m in matches:
            p = Path(m)
            if p.suffix.lower() not in SUPPORTED or str(p) in seen:
                continue
            seen.add(str(p))
            title = (src.title if (src.title and len(matches) == 1) else None) or html_title(p) or _title_from_name(p)
            segments = load_file(p)
            if strip:
                segments = [Segment(_strip(sg.text, strip), sg.locator) for sg in segments]
                segments = [sg for sg in segments if sg.text.strip()]
            doc_id = slugify(p.stem)
            while doc_id in {d.doc_id for d in docs}:
                doc_id += "-x"
            docs.append(
                Document(
                    doc_id=doc_id,
                    title=title,
                    kind=src.kind,
                    source_path=str(p),
                    segments=segments,
                    agenda_items=list(src.agenda_items),
                )
            )
    return docs


def _strip(text: str, patterns: list[re.Pattern]) -> str:
    for pat in patterns:
        text = pat.sub("", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _title_from_name(p: Path) -> str:
    return re.sub(r"[_\-]+", " ", p.stem).strip().title()


def _fingerprint(docs: list[Document], embedder: LLMClient | None) -> str:
    h = hashlib.sha256()
    for d in docs:
        h.update(d.doc_id.encode())
        h.update(d.text.encode("utf-8", errors="ignore"))
        h.update(",".join(d.agenda_items).encode())
    h.update((embedder.profile.name if embedder else "none").encode())
    return h.hexdigest()[:16]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
