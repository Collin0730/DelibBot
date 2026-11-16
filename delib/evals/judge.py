"""LLM-as-judge: one structured call per conversation, scored against rubrics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, Field

from .. import prompts
from ..config import DeliberationConfig
from ..llm.base import LLMClient, LLMResponse, Message

_DATA = Path(__file__).resolve().parent.parent / "data"


ISSUE_TYPES = [
    "stance_taking",
    "imbalance",
    "leading_question",
    "sycophancy",
    "unsupported_claim",
    "miscitation",
    "missed_correction",
    "ignored_participant",
    "too_complex",
    "too_long",
    "roleplay_problem",
    "disrespect",
    "other",
]
VERDICTS = ["good", "minor_issue", "problem"]


class Rubric(BaseModel):
    id: str
    description: str
    modes: list[str] = Field(default_factory=lambda: ["any"])
    probes: list[str] = Field(default_factory=list)
    anchors: dict[int, str]

    def applies(self, mode: str, probe: str) -> bool:
        return "any" in self.modes or mode in self.modes or probe in self.probes


def load_rubrics(path: str | Path | None = None) -> list[Rubric]:
    raw = yaml.safe_load(Path(path or _DATA / "rubrics.yaml").read_text(encoding="utf-8"))
    return [Rubric(**r) for r in raw["rubrics"]]


def judge_schema(rubrics: list[Rubric]) -> dict[str, Any]:
    score = {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 5},
            "rationale": {"type": "string"},
            "evidence_turns": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["score", "rationale", "evidence_turns"],
        "additionalProperties": False,
    }
    props: dict[str, Any] = {r.id: score for r in rubrics}
    props["steering_turns"] = {"type": "array", "items": {"type": "integer"}}
    props["overall_notes"] = {"type": "string"}
    props["turn_reviews"] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "turn": {"type": "integer"},
                "verdict": {"type": "string", "enum": VERDICTS},
                "issues": {"type": "array", "items": {"type": "string", "enum": ISSUE_TYPES}},
                "policy_rules": {"type": "array", "items": {"type": "integer"}},
                "explanation": {"type": "string"},
                "better_response": {"type": "string"},
            },
            "required": ["turn", "verdict", "issues", "policy_rules", "explanation", "better_response"],
            "additionalProperties": False,
        },
    }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def render_for_judge(
    transcript: dict[str, Any], chunk_text: Callable[[str], str] | None = None, excerpt_chars: int = 4000
) -> str:
    """Transcript with the excerpts the coach saw on each turn."""
    blocks = []
    stored = transcript.get("excerpts") or {}  # exact text the coach saw, when the run recorded it
    for i, t in enumerate(transcript["turns"], 1):
        coach = t.get("coach") or {}
        sources = coach.get("sources", [])
        src_lines = []
        for s in sources:
            snippet = (stored.get(s["chunk_id"]) or (chunk_text(s["chunk_id"]) if chunk_text else ""))[:excerpt_chars]
            src_lines.append(f"  [{s['label']}] {s['source']}: {snippet}")
        excerpts = "\n".join(src_lines) if src_lines else "  (none)"
        blocks.append(
            f"### Turn {i}\nPARTICIPANT: {t['participant']}\n"
            f"Excerpts available to the coach:\n{excerpts}\n"
            f"COACH: {coach.get('text', '')}"
        )
    return "\n\n".join(blocks)


class Judge:
    def __init__(
        self,
        client: LLMClient,
        config: DeliberationConfig,
        rubrics: list[Rubric] | None = None,
        chunk_text: Callable[[str], str] | None = None,
    ):
        self.client = client
        self.config = config
        self.rubrics = rubrics or load_rubrics()
        self.chunk_text = chunk_text

    def score(self, transcript: dict[str, Any], scenario_brief: str) -> tuple[dict[str, Any], LLMResponse]:
        mode, probe = transcript["mode"], transcript["probe"]
        na = [r.id for r in self.rubrics if not r.applies(mode, probe)]
        rubric_text = "\n".join(
            f"- {r.id}{' (NOT APPLICABLE: score 0)' if r.id in na else ''}: {r.description}\n"
            + "\n".join(f"    {k}: {v}" for k, v in sorted(r.anchors.items(), reverse=True))
            for r in self.rubrics
        )
        system = prompts.render(
            "judge",
            deliberation_context=self.config.context_block(),
            knowledge_level=transcript["knowledge_level"],
            scenario=scenario_brief,
            rubrics=rubric_text,
            not_applicable=", ".join(na) or "(none: score every rubric)",
        )
        resp = self.client.chat_json(
            system,
            [Message("user", render_for_judge(transcript, self.chunk_text))],
            judge_schema(self.rubrics),
            "conversation_scores",
            max_tokens=max(self.client.profile.max_tokens, 8000),
        )
        data = resp.data or {}
        for r in self.rubrics:
            if isinstance(data.get(r.id), dict):
                try:
                    data[r.id]["score"] = max(0, min(5, int(data[r.id].get("score", 0))))
                except (TypeError, ValueError):
                    data[r.id]["score"] = 0
        data["turn_reviews"] = _normalize_turn_reviews(data.get("turn_reviews"), len(transcript["turns"]))
        # Enforce N/A deterministically regardless of what the judge returned.
        for rid in na:
            if isinstance(data.get(rid), dict):
                data[rid]["score"] = 0
        return data, resp


def _normalize_turn_reviews(reviews: Any, n_turns: int) -> list[dict[str, Any]]:
    """One review per turn, in order, even if the judge skipped or repeated some."""
    by_turn: dict[int, dict[str, Any]] = {}
    for r in reviews or []:
        if not isinstance(r, dict):
            continue
        try:
            t = int(r.get("turn", 0))
        except (TypeError, ValueError):
            continue
        if 1 <= t <= n_turns and t not in by_turn:
            verdict = r.get("verdict") if r.get("verdict") in VERDICTS else "minor_issue"
            by_turn[t] = {
                "turn": t,
                "verdict": verdict,
                "issues": [i for i in r.get("issues", []) if i in ISSUE_TYPES],
                "policy_rules": [int(x) for x in r.get("policy_rules", []) if str(x).isdigit() and 1 <= int(x) <= 8],
                "explanation": str(r.get("explanation", "")),
                "better_response": "" if verdict == "good" else str(r.get("better_response", "")),
            }
    return [
        by_turn.get(t, {"turn": t, "verdict": "not_reviewed", "issues": [], "policy_rules": [],
                        "explanation": "The judge did not return a review for this turn.", "better_response": ""})
        for t in range(1, n_turns + 1)
    ]
