from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Literal

from pydantic import BaseModel, Field

from hackathon_agents.config import AppConfig, ModelConfig, RunMode


Difficulty = Literal["low", "medium", "high"]


class ModelSelectionRequest(BaseModel):
    task_type: str
    expected_difficulty: Difficulty = "medium"
    context_size: int = 0
    privacy_required: bool = False
    budget_mode: RunMode
    required_capabilities: list[str] = Field(default_factory=list)
    agent_name: str | None = None


class ModelSelection(BaseModel):
    alias: str
    provider: str
    model: str
    reason: str
    host: str | None = None


class ModelAvailability(BaseModel):
    alias: str
    provider: str
    model: str
    available: bool
    reason: str
    host: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    listed_models: list[str] = Field(default_factory=list)


class ModelRouter:
    """Capability-based model selection for hosted and local backends."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.availability: dict[str, ModelAvailability] = {}

    def check_model_availability(self, timeout_seconds: float = 2.0) -> dict[str, ModelAvailability]:
        ollama_models_by_host: dict[str, tuple[bool, str, list[str]]] = {}
        vllm_models_by_base: dict[str, tuple[bool, str, list[str]]] = {}
        openrouter_models_by_base: dict[str, tuple[bool, str, list[str]]] = {}

        for alias, model in self.config.models.items():
            if not model.enabled:
                self.availability[alias] = ModelAvailability(
                    alias=alias,
                    provider=model.provider,
                    model=model.model,
                    available=False,
                    reason="disabled in config",
                    host=model.host,
                    capabilities=model.capabilities,
                )
                continue

            if model.provider == "ollama":
                host = model.host or ""
                if host not in ollama_models_by_host:
                    ollama_models_by_host[host] = self._ping_ollama(host, timeout_seconds)
                ok, reason, listed = ollama_models_by_host[host]
                available = ok and (not listed or model.model in listed)
                if ok and listed and model.model not in listed:
                    reason = f"Ollama host is reachable but model {model.model!r} is not listed."
                self.availability[alias] = ModelAvailability(
                    alias=alias,
                    provider=model.provider,
                    model=model.model,
                    available=available,
                    reason=reason,
                    host=model.host,
                    capabilities=model.capabilities,
                    listed_models=listed,
                )
                continue

            if model.provider == "vllm":
                base_url = model.api_base or model.host or ""
                if base_url not in vllm_models_by_base:
                    vllm_models_by_base[base_url] = self._ping_vllm(base_url, timeout_seconds)
                ok, reason, listed = vllm_models_by_base[base_url]
                available = ok and (not listed or model.model in listed)
                if ok and listed and model.model not in listed:
                    reason = f"vLLM endpoint is reachable but model {model.model!r} is not listed."
                self.availability[alias] = ModelAvailability(
                    alias=alias,
                    provider=model.provider,
                    model=model.model,
                    available=available,
                    reason=reason,
                    host=base_url,
                    capabilities=model.capabilities,
                    listed_models=listed,
                )
                continue

            if model.provider == "openrouter":
                base_url = model.api_base or model.host or "https://openrouter.ai/api/v1"
                if model.api_key_env and not os.getenv(model.api_key_env):
                    self.availability[alias] = ModelAvailability(
                        alias=alias,
                        provider=model.provider,
                        model=model.model,
                        available=False,
                        reason=f"missing environment variable {model.api_key_env}",
                        host=base_url,
                        capabilities=model.capabilities,
                    )
                    continue
                if base_url not in openrouter_models_by_base:
                    openrouter_models_by_base[base_url] = self._ping_openrouter(model, timeout_seconds)
                ok, reason, listed = openrouter_models_by_base[base_url]
                listed_model = model.model.removeprefix("openrouter/")
                available = ok and (not listed or listed_model.startswith("~") or listed_model in listed)
                if ok and listed and not listed_model.startswith("~") and listed_model not in listed:
                    reason = f"OpenRouter is reachable but model {listed_model!r} is not listed."
                self.availability[alias] = ModelAvailability(
                    alias=alias,
                    provider=model.provider,
                    model=model.model,
                    available=available,
                    reason=reason,
                    host=base_url,
                    capabilities=model.capabilities,
                    listed_models=listed,
                )
                continue

            key_ok = True
            reason = "configured"
            if model.api_key_env and not os.getenv(model.api_key_env) and _requires_api_key(model):
                key_ok = False
                reason = f"missing environment variable {model.api_key_env}"
            self.availability[alias] = ModelAvailability(
                alias=alias,
                provider=model.provider,
                model=model.model,
                available=key_ok,
                reason=reason,
                host=model.host,
                capabilities=model.capabilities,
            )

        return self.availability

    def select(self, request: ModelSelectionRequest | dict[str, Any]) -> ModelSelection:
        parsed = request if isinstance(request, ModelSelectionRequest) else ModelSelectionRequest.model_validate(request)
        agent = self.config.agents.get(parsed.agent_name or "") if parsed.agent_name else None
        required = parsed.required_capabilities or (agent.requires if agent else [])

        aliases = self._policy_aliases(parsed, required)
        aliases.extend(self._capability_aliases(required))
        if agent and agent.preferred_model:
            aliases.append(agent.preferred_model)
            aliases.extend(agent.fallback)
        aliases.append(self.config.model_routing.default_alias)

        for alias in _dedupe(aliases):
            model = self.config.models.get(alias)
            if not model:
                continue
            if not self._candidate_allowed(model, parsed, required):
                continue
            return ModelSelection(
                alias=alias,
                provider=model.provider,
                model=model.model,
                host=model.host,
                reason=self._selection_reason(alias, parsed, required),
            )

        raise RuntimeError(f"No configured model satisfies request: {parsed.model_dump(mode='json')}")

    def select_for_agent(
        self,
        agent_name: str,
        task_type: str | None = None,
        expected_difficulty: Difficulty = "medium",
        context_size: int = 0,
        privacy_required: bool = False,
        budget_mode: RunMode | None = None,
    ) -> ModelSelection:
        agent = self.config.get_agent(agent_name)
        return self.select(
            ModelSelectionRequest(
                task_type=task_type or agent_name,
                expected_difficulty=expected_difficulty,
                context_size=context_size,
                privacy_required=privacy_required,
                budget_mode=budget_mode or self.config.run_mode,
                required_capabilities=agent.requires,
                agent_name=agent_name,
            )
        )

    def _policy_aliases(self, request: ModelSelectionRequest, required: list[str]) -> list[str]:
        heavy_aliases = self._heavy_aliases(request)

        if request.budget_mode == RunMode.OFFLINE:
            if "fast" in required or request.task_type in {"router", "summarization", "formatting"}:
                return ["local_small", "local_large"]
            return ["local_large", "local_small"]

        if request.privacy_required:
            return [*heavy_aliases, "local_large", "local_small"]

        if request.budget_mode == RunMode.CHEAP:
            if request.task_type in {"router", "summarization", "formatting", "writer"}:
                return ["local_small", "local_large"]
            if heavy_aliases:
                return [*heavy_aliases, "local_large", "local_small"]
            if request.task_type in {"final_critic", "critic"} and not request.privacy_required:
                final_alias = self.config.model_routing.cheap_final_review_alias
                return [alias for alias in [final_alias, "local_large"] if alias]
            return ["local_large", "local_small"]

        if request.task_type in {"bulk", "hypothesis_generation"}:
            return [*heavy_aliases, "local_large", "local_small"]
        if request.task_type in {"chemist", "science_reasoning"}:
            return [*heavy_aliases, "science_reasoning", "frontier_reasoning", "local_large"]
        if request.task_type in {"critic", "final_critic", "planner"} or request.expected_difficulty == "high":
            return [*heavy_aliases, "frontier_reasoning", "science_reasoning", "local_large"]
        return [*heavy_aliases, "frontier_reasoning", "local_large", "local_small"]

    def _heavy_aliases(self, request: ModelSelectionRequest) -> list[str]:
        if request.expected_difficulty != "high" and request.context_size < 32_000:
            return []
        alias = self.config.model_routing.heavy_task_alias
        return [alias] if alias else []

    def _capability_aliases(self, required: list[str]) -> list[str]:
        scored: list[tuple[int, str]] = []
        required_set = set(required)
        for alias, model in self.config.models.items():
            capabilities = set(model.capabilities)
            score = len(required_set & capabilities)
            if score:
                scored.append((score, alias))
        return [alias for _, alias in sorted(scored, reverse=True)]

    def _candidate_allowed(self, model: ModelConfig, request: ModelSelectionRequest, required: list[str]) -> bool:
        if not model.enabled:
            return False
        known = self.availability.get(next((a for a, m in self.config.models.items() if m is model), ""), None)
        if known and not known.available:
            return False
        if model.api_key_env and not os.getenv(model.api_key_env) and _requires_api_key(model):
            return False
        if model.api_base_env and not os.getenv(model.api_base_env) and model.provider != "openrouter":
            return False
        if model.provider == "vllm" and not (model.api_base or model.host):
            return False
        if request.budget_mode == RunMode.OFFLINE and model.provider != self.config.model_routing.offline_required_provider:
            return False
        if request.privacy_required and model.provider != "ollama" and "private" not in model.capabilities:
            return False
        if required and not set(required).issubset(set(model.capabilities)):
            overlap = set(required) & set(model.capabilities)
            if not overlap:
                return False
        return True

    def _selection_reason(self, alias: str, request: ModelSelectionRequest, required: list[str]) -> str:
        parts = [f"selected {alias}", f"mode={request.budget_mode.value}", f"task={request.task_type}"]
        if required:
            parts.append(f"capabilities={','.join(required)}")
        if request.privacy_required:
            parts.append("privacy_required")
        return "; ".join(parts)

    def _ping_ollama(self, host: str, timeout_seconds: float) -> tuple[bool, str, list[str]]:
        if not host:
            return False, "missing Ollama host", []
        try:
            with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [item.get("name", "") for item in payload.get("models", []) if item.get("name")]
            return True, "reachable", models
        except Exception as exc:
            return False, str(exc), []

    def _ping_vllm(self, base_url: str, timeout_seconds: float) -> tuple[bool, str, list[str]]:
        if not base_url:
            return False, "missing vLLM base URL", []
        try:
            with urllib.request.urlopen(_vllm_models_url(base_url), timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [item.get("id", "") for item in payload.get("data", []) if item.get("id")]
            return True, "reachable", models
        except Exception as exc:
            return False, str(exc), []

    def _ping_openrouter(self, model: ModelConfig, timeout_seconds: float) -> tuple[bool, str, list[str]]:
        base_url = model.api_base or model.host or "https://openrouter.ai/api/v1"
        headers = {}
        if model.api_key:
            headers["Authorization"] = f"Bearer {model.api_key}"
        try:
            request = urllib.request.Request(_openai_compatible_models_url(base_url), headers=headers, method="GET")
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [item.get("id", "") for item in payload.get("data", []) if item.get("id")]
            return True, "reachable", models
        except Exception as exc:
            return False, str(exc), []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _vllm_models_url(base_url: str) -> str:
    return _openai_compatible_models_url(base_url)


def _openai_compatible_models_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return f"{base}/models"


def _requires_api_key(model: ModelConfig) -> bool:
    if model.provider == "vllm":
        return bool(model.metadata.get("requires_api_key"))
    return True
