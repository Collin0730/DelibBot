"""The Deliberation Partner itself: retrieval + prompt assembly + one model call."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .. import prompts
from ..config import DeliberationConfig
from ..corpus.chunker import Chunk
from ..corpus.index import MaterialIndex
from ..llm.base import LLMClient, Message, Usage
from .state import WORD_LIMITS, ParticipantJourney

Mode = Literal["auto", "prep", "tutor", "perspectives", "reflect", "debrief"]
MODES: tuple[str, ...] = ("auto", "prep", "tutor", "perspectives", "reflect", "debrief")

_LABEL = re.compile(r"\[S(\d+)\]")


@dataclass
class Citation:
    label: str
    chunk_id: str
    source: str


@dataclass
class CoachTurn:
    text: str
    mode: str
    sources: list[Chunk]
    citations: list[Citation] = field(default_factory=list)
    invalid_labels: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    latency_s: float = 0.0
    model: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "mode": self.mode,
            "sources": [{"label": f"S{i}", "chunk_id": c.chunk_id, "source": c.cite_label} for i, c in enumerate(self.sources, 1)],
            "citations": [c.__dict__ for c in self.citations],
            "invalid_labels": self.invalid_labels,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "cost_usd": self.cost_usd,
            "latency_s": round(self.latency_s, 3),
            "model": self.model,
        }


class Coach:
    def __init__(
        self,
        client: LLMClient,
        config: DeliberationConfig,
        index: MaterialIndex,
        k: int = 5,
        max_per_doc: int | None = 1,
    ):
        self.client = client
        self.config = config
        self.index = index
        self.k = k
        # One chunk per source by default: excerpts come from several speakers,
        # which is a structural safeguard for balance.
        self.max_per_doc = max_per_doc

    def retrieve(self, history: list[Message], user_message: str, agenda_item: str | None) -> list[Chunk]:
        prior_user = next((m.content for m in reversed(history) if m.role == "user"), "")
        item = self.config.agenda_item(agenda_item)
        query = " ".join(filter(None, [user_message, prior_user[:300], item.title if item else ""]))
        hits = self.index.search(query, k=self.k, agenda_item=agenda_item, max_per_doc=self.max_per_doc)
        return [h.chunk for h in hits]

    def build_system(
        self, journey: ParticipantJourney, mode: str, sources: list[Chunk], agenda_item: str | None = None
    ) -> str:
        if mode not in MODES:
            raise ValueError(f"Unknown mode '{mode}'. Choose from {MODES}")
        item = self.config.agenda_item(agenda_item or journey.focus_agenda_item)
        additions = "".join(
            f"{i}. {rule}\n" for i, rule in enumerate(self.config.policy_additions, start=9)
        )
        return prompts.render(
            "coach_core",
            deliberation_context=self.config.context_block(),
            participant_context=journey.prompt_block(item.title if item else None),
            policy_additions=additions,
            sources=format_sources(sources),
            language=self.config.language,
            knowledge_level=journey.knowledge_level,
            word_limit=WORD_LIMITS[journey.knowledge_level],
            mode_instructions=prompts.load(f"mode_{mode}"),
        )

    def respond(
        self,
        journey: ParticipantJourney,
        history: list[Message],
        user_message: str,
        mode: str = "auto",
        agenda_item: str | None = None,
    ) -> CoachTurn:
        agenda_item = agenda_item or journey.focus_agenda_item
        sources = self.retrieve(history, user_message, agenda_item)
        system = self.build_system(journey, mode, sources, agenda_item)
        resp = self.client.chat(system, [*history, Message("user", user_message)])
        citations, invalid = parse_citations(resp.text, sources)
        return CoachTurn(
            text=resp.text.strip(),
            mode=mode,
            sources=sources,
            citations=citations,
            invalid_labels=invalid,
            usage=resp.usage,
            cost_usd=resp.cost_usd,
            latency_s=resp.latency_s,
            model=resp.model,
        )


def format_sources(sources: list[Chunk]) -> str:
    if not sources:
        return "(No excerpts matched this turn. Do not cite anything.)"
    blocks = []
    for i, c in enumerate(sources, 1):
        blocks.append(f"[S{i}] {c.cite_label} ({c.kind})\n{c.text}")
    return "\n\n".join(blocks)


def parse_citations(text: str, sources: list[Chunk]) -> tuple[list[Citation], list[str]]:
    seen: set[int] = set()
    cites: list[Citation] = []
    invalid: list[str] = []
    for m in _LABEL.finditer(text):
        n = int(m.group(1))
        if n in seen:
            continue
        seen.add(n)
        if 1 <= n <= len(sources):
            c = sources[n - 1]
            cites.append(Citation(f"S{n}", c.chunk_id, c.cite_label))
        else:
            invalid.append(f"S{n}")
    return cites, invalid
