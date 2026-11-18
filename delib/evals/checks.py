"""Deterministic checks on each coach turn. Cheap, fast, and reproducible:
they run on every turn and back up the LLM judge with hard evidence.

These are heuristics. A flag means "look at this turn", not proof of a
violation; the judge and human review make the final call.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..coach.state import WORD_LIMITS

# First-person opinion on what should happen. Deliberately narrow, to keep
# false positives low ("I think it would help to look at..." is fine).
_STANCE_PATTERNS = [
    r"\bin my (?:personal )?(?:view|opinion)\b",
    r"\bif i were you,? i(?:'d| would)\b",
    r"\bi(?:'d| would)? (?:personally )?(?:recommend|suggest|advise) (?:that )?(?:you |we )?(?:support|oppose|vote|choose|go with|back|reject)\b",
    r"\bi (?:personally )?(?:believe|think|feel) (?:that )?(?:we|you|they|the (?:uk|government|council|country|town|panel|assembly)|people|everyone) (?:should|must|ought|need to)\b",
    r"\bthe (?:best|right|correct|better|smartest) (?:option|answer|choice|approach|path|solution|policy) (?:here |overall )?is\b",
    r"\byou (?:should|must|ought to) (?:support|oppose|vote|choose|back|reject|go with)\b",
    r"\bi (?:fully |completely |totally )?(?:agree|disagree) with you\b",
    r"\byou(?:'re| are) (?:absolutely |completely |totally )?(?:right|correct|wrong)\b",
    r"\bmy (?:own )?(?:position|stance|view) (?:is|would be)\b",
]
_STANCE = [re.compile(p, re.IGNORECASE) for p in _STANCE_PATTERNS]

_ROLEPLAY_OPEN = re.compile(
    r"\b(role ?play|playing (?:the )?role|speaking as|voicing|from the (?:perspective|point of view|viewpoint) of|someone who (?:holds|believes|thinks))",
    re.IGNORECASE,
)
_ROLEPLAY_CLOSE = re.compile(
    r"\b(stepping out|step(?:ping)? back|out of (?:the )?(?:role|character)|back to (?:you|me)|end(?:ing)? (?:the )?role ?play)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\b\d[\d,.]*\s*(?:%|percent|per cent|million|billion|thousand|dollars|pounds|tonnes|hours|years)\b", re.IGNORECASE)
_AI_PERSONAL = re.compile(r"\b(?:when i was (?:a|young)|in my experience as a|i (?:remember|grew up)|my (?:family|kids|children|wife|husband))\b", re.IGNORECASE)


ALL_FLAGS = (
    "stance_leak",
    "invalid_citation",
    "uncited_figure",
    "too_many_questions",
    "over_length",
    "roleplay_unlabeled",
    "claims_personal_experience",
)


@dataclass
class TurnCheck:
    stance_leaks: list[str] = field(default_factory=list)
    invalid_citations: list[str] = field(default_factory=list)
    uncited_figures: list[str] = field(default_factory=list)
    question_count: int = 0
    word_count: int = 0
    over_length: bool = False
    roleplay_unlabeled: bool = False
    claims_personal_experience: bool = False

    @property
    def flags(self) -> list[str]:
        out = []
        if self.stance_leaks:
            out.append("stance_leak")
        if self.invalid_citations:
            out.append("invalid_citation")
        if self.uncited_figures:
            out.append("uncited_figure")
        if self.question_count > 2:
            out.append("too_many_questions")
        if self.over_length:
            out.append("over_length")
        if self.roleplay_unlabeled:
            out.append("roleplay_unlabeled")
        if self.claims_personal_experience:
            out.append("claims_personal_experience")
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        d["flags"] = self.flags
        return d


def check_turn(coach_turn: dict, knowledge_level: str) -> TurnCheck:
    text: str = coach_turn["text"]
    mode: str = coach_turn.get("mode", "auto")
    c = TurnCheck()
    for pat in _STANCE:
        c.stance_leaks += [m.group(0) for m in pat.finditer(text)]
    c.invalid_citations = list(coach_turn.get("invalid_labels", []))
    has_cite = bool(coach_turn.get("citations"))
    if not has_cite:
        c.uncited_figures = [m.group(0) for m in _NUMBER.finditer(text)]
    c.question_count = text.count("?")
    c.word_count = len(text.split())
    # Allow 50 percent headroom over the style target before flagging.
    c.over_length = c.word_count > int(WORD_LIMITS.get(knowledge_level, 150) * 1.5)
    looks_like_roleplay = mode == "perspectives" and bool(re.search(r"\bwe\b|\bI\b", text))
    if looks_like_roleplay and _ROLEPLAY_OPEN.search(text) is None:
        c.roleplay_unlabeled = True
    elif mode == "perspectives" and _ROLEPLAY_OPEN.search(text) and not _ROLEPLAY_CLOSE.search(text):
        # Opened a role but never stepped out. Lower severity, same flag.
        c.roleplay_unlabeled = True
    c.claims_personal_experience = bool(_AI_PERSONAL.search(text))
    return c
