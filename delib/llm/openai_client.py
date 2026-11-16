"""OpenAI adapter, plus an OpenAI-compatible adapter for any server that
speaks the Chat Completions protocol (Ollama, vLLM, LM Studio, Together,
Groq, Azure OpenAI with a base_url, and so on).

Chat Completions is used rather than the newer Responses API because it is
the protocol that third-party servers implement, which keeps one code path
for every OpenAI-style backend.
"""

from __future__ import annotations

from typing import Any

from .base import LLMClient, LLMError, Message, ModelProfile, Usage, extract_json, schema_instructions

# Keywords that OpenAI strict structured outputs may reject. Ranges are
# enforced in code by the callers instead (judge scores, stance values).
_UNSUPPORTED_STRICT = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
                       "minLength", "maxLength", "pattern", "format", "minItems", "maxItems"}


def strict_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: strict_schema(v) for k, v in schema.items() if k not in _UNSUPPORTED_STRICT}
    if isinstance(schema, list):
        return [strict_schema(v) for v in schema]
    return schema


class OpenAIClient(LLMClient):
    provider = "openai"
    default_token_param = "max_completion_tokens"
    key_required = True

    def __init__(self, profile: ModelProfile):
        super().__init__(profile)
        try:
            import openai
        except ImportError as e:  # pragma: no cover
            raise LLMError("Install the OpenAI SDK: pip install openai") from e
        key = self._api_key(required=self.key_required) or "not-needed"
        kwargs: dict[str, Any] = {"api_key": key, "max_retries": 0, "timeout": profile.timeout_s}
        if profile.base_url:
            kwargs["base_url"] = profile.base_url
        self._client = openai.OpenAI(**kwargs)

    def _kwargs(
        self, system: str, messages: list[Message], max_tokens: int, temperature: float | None
    ) -> dict[str, Any]:
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(m.to_dict() for m in messages)
        kwargs: dict[str, Any] = {"model": self.profile.model, "messages": msgs, **self.profile.extra}
        kwargs[self.profile.token_param or self.default_token_param] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature
        return kwargs

    @staticmethod
    def _usage(resp: Any) -> Usage:
        u = getattr(resp, "usage", None)
        if u is None:
            return Usage()
        return Usage(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)

    @staticmethod
    def _text(resp: Any) -> str:
        if not resp.choices:
            raise LLMError("Empty response from model")
        return resp.choices[0].message.content or ""

    def _chat(self, system, messages, max_tokens, temperature):
        resp = self._client.chat.completions.create(**self._kwargs(system, messages, max_tokens, temperature))
        return self._text(resp), self._usage(resp), resp

    def _chat_json(self, system, messages, schema, schema_name, max_tokens, temperature):
        mode = self.profile.json_mode
        if mode == "native":
            kwargs = self._kwargs(system, messages, max_tokens, temperature)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": strict_schema(schema), "strict": True},
            }
        elif mode == "json_object":
            kwargs = self._kwargs(system + schema_instructions(schema), messages, max_tokens, temperature)
            kwargs["response_format"] = {"type": "json_object"}
        else:
            kwargs = self._kwargs(system + schema_instructions(schema), messages, max_tokens, temperature)
        resp = self._client.chat.completions.create(**kwargs)
        return extract_json(self._text(resp)), self._usage(resp), resp

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self.profile.embedding_model or self.profile.model
        out: list[list[float]] = []
        for i in range(0, len(texts), 96):
            resp = self._with_retries(
                lambda batch=texts[i : i + 96]: self._client.embeddings.create(model=model, input=batch)
            )
            out.extend(d.embedding for d in resp.data)
        return out


class OpenAICompatibleClient(OpenAIClient):
    """Any Chat Completions server. Local servers usually need no key."""

    provider = "openai_compatible"
    default_token_param = "max_tokens"
    key_required = False

    def __init__(self, profile: ModelProfile):
        if not profile.base_url:
            raise LLMError(f"Profile '{profile.name}' (openai_compatible) needs a base_url")
        super().__init__(profile)
