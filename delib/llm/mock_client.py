"""Deterministic offline model for tests and dry runs. No network, no cost.

It produces plausible coach and participant text and fills any JSON schema
with valid placeholder values, so the whole pipeline (retrieval, prompts,
simulation, judging, reporting) can be exercised without an API key.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .base import LLMClient, Message, Usage

_SOURCE_ID = re.compile(r"\[(S\d+)\]")


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockClient(LLMClient):
    provider = "mock"

    def _chat(self, system, messages, max_tokens, temperature):
        last = messages[-1].content
        if "SIMULATED PARTICIPANT" in system:
            text = self._participant_reply(last, len(messages))
        else:
            text = self._coach_reply(system, last)
        usage = Usage(_tokens(system) + sum(_tokens(m.content) for m in messages), _tokens(text))
        return text, usage, None

    def _chat_json(self, system, messages, schema, schema_name, max_tokens, temperature):
        seed = int(hashlib.sha1((system + messages[-1].content).encode()).hexdigest(), 16)
        data = fill_schema(schema, seed)
        if "turn_reviews" in schema.get("properties", {}):
            data["turn_reviews"] = _mock_turn_reviews(messages[-1].content.count("### Turn"), seed)
        usage = Usage(_tokens(system) + sum(_tokens(m.content) for m in messages), 60)
        return data, usage, None

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for t in texts:
            v = [0.0] * 32
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 32] += 1.0
            norm = sum(x * x for x in v) ** 0.5 or 1.0
            vecs.append([x / norm for x in v])
        return vecs

    @staticmethod
    def _coach_reply(system: str, last: str) -> str:
        ids = _SOURCE_ID.findall(system)
        cite = f" [{ids[0]}]" if ids else ""
        if "MODE: perspectives" in system:
            return (
                "(Roleplay: I'm voicing one perspective, not my own view.) Someone holding this view "
                f"might start from the evidence in the materials{cite}. (Stepping out of the role.) "
                "Which part of that argument feels strongest or weakest to you?"
            )
        return (
            f"The materials touch on this{cite}. People weigh it differently depending on what they "
            "prioritise. What stands out to you about it so far?"
        )

    @staticmethod
    def _participant_reply(last: str, n: int) -> str:
        if n <= 1:
            return "Hi. I read some of the materials but I'm not sure I followed all of it. Can you help?"
        return "That helps a bit. I think cost matters most to me, but I'm still unsure. What else should I consider?"


def fill_schema(schema: dict[str, Any], seed: int = 0) -> Any:
    """Return a value that validates against a (simple) JSON schema."""
    if "enum" in schema:
        return schema["enum"][seed % len(schema["enum"])]
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "null")
    if t == "object":
        props = schema.get("properties", {})
        return {k: fill_schema(v, seed + i) for i, (k, v) in enumerate(props.items())}
    if t == "array":
        item = schema.get("items", {"type": "string"})
        n = schema.get("minItems", 0)
        return [fill_schema(item, seed + i) for i in range(n)]
    if t == "integer":
        lo, hi = schema.get("minimum", 1), schema.get("maximum", 5)
        return hi if hi - lo >= 1 and seed % 4 else max(lo, hi - 1)
    if t == "number":
        return float(schema.get("maximum", 1.0))
    if t == "boolean":
        return False
    if t == "null":
        return None
    return "mock"


def _mock_turn_reviews(n_turns: int, seed: int) -> list[dict[str, Any]]:
    out = []
    for t in range(1, n_turns + 1):
        roll = (seed >> t) % 5
        if roll == 0:
            out.append({
                "turn": t, "verdict": "problem", "issues": ["sycophancy"], "policy_rules": [5],
                "explanation": "Mock review: the coach agreed with the participant without adding a consideration.",
                "better_response": "Mock better response: that's a reasonable concern. Some speakers weighed it differently [S1]. What would change your mind?",
            })
        elif roll == 1:
            out.append({
                "turn": t, "verdict": "minor_issue", "issues": ["too_long"], "policy_rules": [],
                "explanation": "Mock review: helpful but longer than needed for this participant.",
                "better_response": "Mock better response: a shorter version of the same point.",
            })
        else:
            out.append({"turn": t, "verdict": "good", "issues": [], "policy_rules": [],
                        "explanation": "Mock review: on policy.", "better_response": ""})
    return out
