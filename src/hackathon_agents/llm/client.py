from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from pydantic import BaseModel, Field

from hackathon_agents.config import AppConfig, ModelConfig


class CompletionRequest(BaseModel):
    model_alias: str | None = None
    messages: list[dict[str, str]]
    temperature: float = 0.1
    max_tokens: int = 1200
    retries: int = 1
    fallback_aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionResult(BaseModel):
    ok: bool
    content: str = ""
    model_alias: str | None = None
    provider: str | None = None
    error: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    cost: float | None = None
    latency_seconds: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class LLMClient:
    """Small LiteLLM wrapper with alias resolution and deterministic failure handling."""

    def __init__(self, config: AppConfig):
        self.config = config

    def complete(self, request: CompletionRequest | dict[str, Any]) -> CompletionResult:
        parsed = request if isinstance(request, CompletionRequest) else CompletionRequest.model_validate(request)
        aliases = [parsed.model_alias or self.config.model_routing.default_alias, *parsed.fallback_aliases]
        last_error: str | None = None

        for alias in aliases:
            try:
                model_config = self.config.get_model(alias)
            except Exception as exc:
                last_error = str(exc)
                continue

            for attempt in range(max(1, parsed.retries)):
                started = time.perf_counter()
                result = self._complete_once(alias, model_config, parsed)
                result.latency_seconds = time.perf_counter() - started
                if result.ok:
                    return result
                last_error = result.error
                if attempt + 1 < parsed.retries:
                    time.sleep(0.25 * (attempt + 1))

        return CompletionResult(ok=False, error=last_error or "No model call succeeded.")

    def _complete_once(
        self,
        alias: str,
        model_config: ModelConfig,
        request: CompletionRequest,
    ) -> CompletionResult:
        try:
            import litellm
        except Exception:
            if model_config.provider == "ollama":
                return self._direct_ollama_completion(alias, model_config, request)
            return CompletionResult(
                ok=False,
                model_alias=alias,
                provider=model_config.provider,
                error="LiteLLM is not installed and direct fallback only supports Ollama.",
            )

        kwargs: dict[str, Any] = {
            "model": model_config.litellm_model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "metadata": {"model_alias": alias, **request.metadata},
            "drop_params": True,
        }
        if model_config.api_base:
            kwargs["api_base"] = model_config.api_base
        if model_config.api_key:
            kwargs["api_key"] = model_config.api_key

        try:
            response = litellm.completion(**kwargs)
            content = _extract_content(response)
            raw = _to_dict(response)
            usage = raw.get("usage") or {}
            cost = None
            try:
                cost = float(litellm.completion_cost(completion_response=response))
            except Exception:
                cost = None
            return CompletionResult(
                ok=True,
                content=content,
                model_alias=alias,
                provider=model_config.provider,
                usage=usage,
                cost=cost,
                raw=raw,
            )
        except Exception as exc:
            if model_config.provider == "ollama":
                return self._direct_ollama_completion(alias, model_config, request, previous_error=str(exc))
            return CompletionResult(ok=False, model_alias=alias, provider=model_config.provider, error=str(exc))

    def _direct_ollama_completion(
        self,
        alias: str,
        model_config: ModelConfig,
        request: CompletionRequest,
        previous_error: str | None = None,
    ) -> CompletionResult:
        if not model_config.host:
            return CompletionResult(
                ok=False,
                model_alias=alias,
                provider=model_config.provider,
                error=previous_error or "Ollama host is not configured.",
            )

        payload = {
            "model": model_config.model,
            "messages": request.messages,
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        try:
            req = urllib.request.Request(
                f"{model_config.host.rstrip('/')}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "")
            return CompletionResult(
                ok=True,
                content=content,
                model_alias=alias,
                provider=model_config.provider,
                raw=data,
            )
        except Exception as exc:
            error = str(exc)
            if previous_error:
                error = f"LiteLLM failed: {previous_error}; direct Ollama fallback failed: {error}"
            return CompletionResult(ok=False, model_alias=alias, provider=model_config.provider, error=error)


def _extract_content(response: Any) -> str:
    try:
        return response.choices[0].message.content or ""
    except Exception:
        raw = _to_dict(response)
        choices = raw.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or ""


def _to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if isinstance(response, dict):
        return response
    try:
        return json.loads(json.dumps(response, default=str))
    except Exception:
        return {"repr": repr(response)}
