from __future__ import annotations

import json
import os
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from hackathon_agents.config import AppConfig
from hackathon_agents.llm.client import CompletionRequest, LLMClient
from hackathon_agents.llm.router import ModelRouter
from hackathon_agents.llm.validators import validate_json_output
from hackathon_agents.state import DiscoveryStatePayload


T = TypeVar("T", bound=BaseModel)


class AgentModelCall(BaseModel):
    """Compact audit record for optional model-backed agent work."""

    agent: str
    attempted: bool
    ok: bool
    alias: str | None = None
    provider: str | None = None
    reason: str | None = None
    error: str | None = None
    fallback: bool = False


def call_agent_model(
    *,
    state: DiscoveryStatePayload,
    config: AppConfig | None,
    agent_name: str,
    task_type: str,
    response_model: type[T],
    user_payload: dict[str, Any],
    expected_difficulty: str = "medium",
    system_prompt: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> T | None:
    """Call a configured model for an agent and validate a JSON response.

    The helper is intentionally non-fatal.  It records why the model path was not
    used and lets the deterministic agent implementation finish the workflow.
    """

    if config is None:
        _record_model_call(state, AgentModelCall(agent=agent_name, attempted=False, ok=False, reason="no config"))
        return None
    if _llm_mode(state) == "off":
        _record_model_call(
            state,
            AgentModelCall(agent=agent_name, attempted=False, ok=False, reason="model agents disabled"),
        )
        return None

    try:
        router = ModelRouter(config)
        availability = router.check_model_availability(timeout_seconds=_availability_timeout())
        selection = router.select_for_agent(
            agent_name,
            task_type=task_type,
            expected_difficulty=expected_difficulty,  # type: ignore[arg-type]
            budget_mode=config.run_mode,
        )
        selected_availability = availability.get(selection.alias)
        if _llm_mode(state) == "auto" and selected_availability is not None and not selected_availability.available:
            _record_model_call(
                state,
                AgentModelCall(
                    agent=agent_name,
                    attempted=False,
                    ok=False,
                    alias=selection.alias,
                    provider=selection.provider,
                    reason=selected_availability.reason,
                    fallback=True,
                ),
            )
            return None
    except Exception as exc:
        _record_model_call(
            state,
            AgentModelCall(agent=agent_name, attempted=False, ok=False, error=str(exc), fallback=True),
        )
        return None

    agent_config = config.agents.get(agent_name)
    prompt = system_prompt or (agent_config.system_prompt if agent_config else None) or ""
    request = CompletionRequest(
        model_alias=selection.alias,
        fallback_aliases=list(agent_config.fallback if agent_config else []),
        messages=[
            {
                "role": "system",
                "content": _schema_prompt(prompt, response_model),
            },
            {
                "role": "user",
                "content": json.dumps(user_payload, indent=2, sort_keys=True),
            },
        ],
        temperature=temperature if temperature is not None else (agent_config.temperature if agent_config else 0.1),
        max_tokens=max_tokens if max_tokens is not None else (agent_config.max_tokens if agent_config else 1200),
        retries=1,
        metadata={"agent": agent_name, "task_type": task_type},
    )
    result = LLMClient(config).complete(request)
    if not result.ok:
        _record_model_call(
            state,
            AgentModelCall(
                agent=agent_name,
                attempted=True,
                ok=False,
                alias=selection.alias,
                provider=selection.provider,
                error=result.error,
                fallback=True,
            ),
        )
        return None

    try:
        parsed = response_model.model_validate(_extract_json(result.content))
    except (ValueError, ValidationError) as exc:
        _record_model_call(
            state,
            AgentModelCall(
                agent=agent_name,
                attempted=True,
                ok=False,
                alias=result.model_alias or selection.alias,
                provider=result.provider or selection.provider,
                error=f"invalid JSON response: {exc}",
                fallback=True,
            ),
        )
        return None

    _record_model_call(
        state,
        AgentModelCall(
            agent=agent_name,
            attempted=True,
            ok=True,
            alias=result.model_alias or selection.alias,
            provider=result.provider or selection.provider,
        ),
    )
    return parsed


def _schema_prompt(system_prompt: str, response_model: type[BaseModel]) -> str:
    schema = response_model.model_json_schema()
    return "\n".join(
        [
            system_prompt.strip(),
            "",
            "Return exactly one JSON object. Do not wrap it in markdown.",
            "The JSON must conform to this schema:",
            json.dumps(schema, indent=2, sort_keys=True),
        ]
    ).strip()


def _extract_json(content: str) -> Any:
    validation = validate_json_output(content)
    if not validation.ok:
        detail = "; ".join(validation.errors) or "unknown validation error"
        raise ValueError(f"model response did not contain valid JSON: {detail}")
    return validation.parsed


def _llm_mode(state: DiscoveryStatePayload) -> str:
    value = state.metadata.get("agent_llm_mode") or os.getenv("HACKATHON_AGENT_LLM_MODE", "auto")
    normalized = str(value).strip().lower()
    if normalized in {"off", "false", "0", "disabled"}:
        return "off"
    if normalized in {"always", "force", "on", "true", "1"}:
        return "always"
    return "auto"


def _availability_timeout() -> float:
    raw_value = os.getenv("HACKATHON_MODEL_CHECK_TIMEOUT", "0.5")
    try:
        return max(0.05, min(float(raw_value), 5.0))
    except ValueError:
        return 0.5


def _record_model_call(state: DiscoveryStatePayload, record: AgentModelCall) -> None:
    state.metadata.setdefault("model_calls", []).append(record.model_dump(mode="json"))
