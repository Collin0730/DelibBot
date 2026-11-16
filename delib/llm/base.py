"""Provider-neutral types and the LLMClient interface.

Every provider adapter implements two primitives:

* ``_chat``: plain text completion from a system prompt plus a message list.
* ``_chat_json``: completion constrained to a JSON schema.

The public ``chat`` / ``chat_json`` wrappers add timing, retries, and cost
accounting so the rest of the codebase never touches a provider SDK.
"""

from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant"]

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


class Pricing(BaseModel):
    """USD per million tokens. Verify against the provider's pricing page."""

    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0


class ModelProfile(BaseModel):
    """One named model configuration, loaded from configs/models.yaml."""

    name: str
    provider: Literal["anthropic", "openai", "openai_compatible", "mock"]
    model: str
    api_key_env: str | None = None
    base_url: str | None = None
    max_tokens: int = 1024
    temperature: float | None = None
    pricing: Pricing = Field(default_factory=Pricing)
    # How to get JSON out of the model:
    #   native      -> provider feature (Anthropic forced tool use, OpenAI json_schema)
    #   json_object -> OpenAI-style {"type": "json_object"} plus schema in the prompt
    #   prompt      -> schema in the prompt only, parse the reply
    json_mode: Literal["native", "json_object", "prompt"] = "native"
    # Name of the token-limit parameter for OpenAI-style APIs.
    token_param: Literal["max_completion_tokens", "max_tokens"] | None = None
    embedding_model: str | None = None
    timeout_s: float = 120.0
    max_retries: int = 3
    extra: dict[str, Any] = Field(default_factory=dict)

    def cost(self, usage: "Usage") -> float:
        return (
            usage.input_tokens * self.pricing.input_per_mtok
            + usage.output_tokens * self.pricing.output_per_mtok
        ) / 1_000_000


@dataclass
class Message:
    role: Role
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
        )


@dataclass
class LLMResponse:
    text: str
    usage: Usage
    cost_usd: float
    latency_s: float
    model: str
    provider: str
    data: dict[str, Any] | None = None
    raw: Any = field(default=None, repr=False)


class LLMError(RuntimeError):
    pass


class LLMClient(ABC):
    provider: str = "base"

    def __init__(self, profile: ModelProfile):
        self.profile = profile

    # ---- provider primitives -------------------------------------------
    @abstractmethod
    def _chat(
        self, system: str, messages: list[Message], max_tokens: int, temperature: float | None
    ) -> tuple[str, Usage, Any]: ...

    @abstractmethod
    def _chat_json(
        self,
        system: str,
        messages: list[Message],
        schema: dict[str, Any],
        schema_name: str,
        max_tokens: int,
        temperature: float | None,
    ) -> tuple[dict[str, Any], Usage, Any]: ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(f"{self.provider} adapter does not support embeddings")

    # ---- public API ------------------------------------------------------
    def chat(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        _validate_messages(messages)
        mt = max_tokens or self.profile.max_tokens
        temp = temperature if temperature is not None else self.profile.temperature
        start = time.perf_counter()
        text, usage, raw = self._with_retries(lambda: self._chat(system, messages, mt, temp))
        return self._response(text, usage, raw, start)

    def chat_json(
        self,
        system: str,
        messages: list[Message],
        schema: dict[str, Any],
        schema_name: str = "result",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        _validate_messages(messages)
        mt = max_tokens or self.profile.max_tokens
        temp = temperature if temperature is not None else self.profile.temperature
        start = time.perf_counter()
        data, usage, raw = self._with_retries(
            lambda: self._chat_json(system, messages, schema, schema_name, mt, temp)
        )
        resp = self._response(json.dumps(data), usage, raw, start)
        resp.data = data
        return resp

    # ---- helpers ---------------------------------------------------------
    def _response(self, text: str, usage: Usage, raw: Any, start: float) -> LLMResponse:
        return LLMResponse(
            text=text,
            usage=usage,
            cost_usd=self.profile.cost(usage),
            latency_s=time.perf_counter() - start,
            model=self.profile.model,
            provider=self.provider,
            raw=raw,
        )

    def _api_key(self, required: bool = True) -> str | None:
        env = self.profile.api_key_env
        key = os.environ.get(env) if env else None
        if required and not key:
            raise LLMError(
                f"Model profile '{self.profile.name}' needs an API key in the "
                f"environment variable '{env}'. Add it to your .env file."
            )
        return key

    def _is_retryable(self, exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status in RETRYABLE_STATUS:
            return True
        name = type(exc).__name__
        return name in {"APIConnectionError", "APITimeoutError", "OverloadedError"}

    def _with_retries(self, fn):
        attempts = max(1, self.profile.max_retries + 1)
        for i in range(attempts):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
                if i == attempts - 1 or not self._is_retryable(exc):
                    raise
                time.sleep(min(30, 2**i + 0.25 * i))
        raise LLMError("unreachable")


def _validate_messages(messages: list[Message]) -> None:
    if not messages:
        raise LLMError("At least one message is required")
    if messages[0].role != "user":
        raise LLMError("The first message must have role 'user'")
    for a, b in zip(messages, messages[1:]):
        if a.role == b.role:
            raise LLMError("Messages must alternate between user and assistant")


def schema_instructions(schema: dict[str, Any]) -> str:
    """Prompt text that asks for JSON matching a schema (fallback modes)."""
    return (
        "\n\nRespond with a single JSON object only, no prose and no code fences. "
        "It must validate against this JSON Schema:\n" + json.dumps(schema, indent=2)
    )


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating fences and stray prose."""
    text = text.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"Model did not return JSON: {text[:200]!r}")
        obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise LLMError("Expected a JSON object")
    return obj
