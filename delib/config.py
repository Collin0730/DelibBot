"""Deliberation configuration: everything topic-specific lives here, in YAML.

Nothing in the coach, simulator, or evals knows what a deliberation is about.
Swap the YAML and the same code runs a climate assembly, a city budget
jury, a hospital ethics panel, or a lab study.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PrivateAttr, model_validator


class AgendaItem(BaseModel):
    id: str
    title: str
    description: str = ""
    session: int | None = None


class StanceAxis(BaseModel):
    """A 1 to 7 scale participants self-report on. Used only to measure drift,
    never shown to the coach as a target."""

    id: str
    question: str
    low_label: str
    high_label: str


class MaterialSource(BaseModel):
    path: str  # file or glob, relative to the config file
    title: str | None = None
    kind: Literal["briefing", "transcript", "slides", "reading", "other"] = "briefing"
    agenda_items: list[str] = Field(default_factory=list)


class UsageAssumptions(BaseModel):
    """Used to project coach cost per participant from measured eval costs."""

    conversations_per_participant: int = 12
    turns_per_conversation: int = 8
    target_cost_per_participant_usd: float = 100.0


class DeliberationConfig(BaseModel):
    id: str
    title: str
    process_type: Literal["real_world", "study"] = "real_world"
    framing_question: str
    description: str = ""
    language: str = "English"
    audience_notes: str = ""
    agenda: list[AgendaItem] = Field(default_factory=list)
    materials: list[MaterialSource] = Field(default_factory=list)
    stance_axes: list[StanceAxis] = Field(default_factory=list)
    policy_additions: list[str] = Field(default_factory=list)
    # Regexes removed from every loaded document (site navigation, credits, etc.)
    strip_patterns: list[str] = Field(default_factory=list)
    usage: UsageAssumptions = Field(default_factory=UsageAssumptions)

    _base_dir: Path = PrivateAttr(default=Path("."))

    @model_validator(mode="after")
    def _check_refs(self) -> "DeliberationConfig":
        ids = {a.id for a in self.agenda}
        if len(ids) != len(self.agenda):
            raise ValueError("Agenda item ids must be unique")
        for m in self.materials:
            for ref in m.agenda_items:
                if ref not in ids:
                    raise ValueError(f"Material '{m.path}' references unknown agenda item '{ref}'")
        return self

    @classmethod
    def load(cls, path: str | Path) -> "DeliberationConfig":
        p = Path(path)
        cfg = cls(**(yaml.safe_load(p.read_text(encoding="utf-8")) or {}))
        cfg._base_dir = p.parent.resolve()
        return cfg

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def agenda_item(self, item_id: str | None) -> AgendaItem | None:
        return next((a for a in self.agenda if a.id == item_id), None)

    def context_block(self) -> str:
        """Neutral description of the process for prompts."""
        kind = (
            "a research study on deliberation"
            if self.process_type == "study"
            else "a real-world deliberative process"
        )
        lines = [
            f"Process: {self.title} ({kind})",
            f"Framing question: {self.framing_question}",
        ]
        if self.description:
            lines.append(f"About: {self.description.strip()}")
        if self.agenda:
            lines.append("Agenda:")
            for a in self.agenda:
                sess = f" (session {a.session})" if a.session else ""
                desc = f": {a.description}" if a.description else ""
                lines.append(f"  - [{a.id}] {a.title}{sess}{desc}")
        if self.audience_notes:
            lines.append(f"Participant notes: {self.audience_notes.strip()}")
        return "\n".join(lines)
