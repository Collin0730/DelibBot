"""Participant journey state.

Design rule: the journey records what the participant SAID, never what a
model inferred about their opinions. Views are stored only as the
participant's own words, so nothing downstream can quietly build a profile
of someone's politics from guesses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

KnowledgeLevel = Literal["novice", "some", "informed", "expert"]

KNOWLEDGE_DESCRIPTIONS: dict[str, str] = {
    "novice": "new to the topic; avoid jargon and explain basics simply",
    "some": "has some familiarity; explain specialist terms",
    "informed": "well read on the topic; can handle detail and nuance",
    "expert": "a subject-matter expert; be precise and skip basics, but they still benefit from other perspectives",
}

WORD_LIMITS: dict[str, int] = {"novice": 120, "some": 150, "informed": 180, "expert": 200}


class StatedView(BaseModel):
    topic: str
    in_their_words: str
    conversation: int


class ParticipantJourney(BaseModel):
    participant_id: str
    knowledge_level: KnowledgeLevel = "some"
    focus_agenda_item: str | None = None
    topics_explored: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    stated_views: list[StatedView] = Field(default_factory=list)
    concerns_raised: list[str] = Field(default_factory=list)
    conversations: int = 0

    def prompt_block(self, agenda_title: str | None = None) -> str:
        lines = [
            f"Knowledge level: {self.knowledge_level} ({KNOWLEDGE_DESCRIPTIONS[self.knowledge_level]})",
        ]
        if agenda_title:
            lines.append(f"Current focus: {agenda_title}")
        if self.conversations:
            lines.append(f"Previous conversations with you: {self.conversations}")
        if self.topics_explored:
            lines.append("Topics explored before: " + "; ".join(self.topics_explored[-8:]))
        if self.open_questions:
            lines.append("Their open questions: " + "; ".join(self.open_questions[-5:]))
        if self.stated_views:
            lines.append("Views they have stated, in their own words (do not treat as fixed):")
            for v in self.stated_views[-5:]:
                lines.append(f'  - {v.topic}: "{v.in_their_words}"')
        if self.concerns_raised:
            lines.append("Concerns they raised about the process: " + "; ".join(self.concerns_raised[-3:]))
        if len(lines) == 1 + (1 if agenda_title else 0):
            lines.append("This is your first conversation with this participant.")
        return "\n".join(lines)
