from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from hackathon_agents.config import AppConfig
from hackathon_agents.llm.client import CompletionRequest, LLMClient
from hackathon_agents.llm.router import ModelRouter


BENCHMARK_TASKS: dict[str, list[dict[str, str]]] = {
    "latency": [{"role": "user", "content": "Reply with exactly: ready"}],
    "tool_calling_ability": [
        {"role": "user", "content": 'Return JSON for calling validate_smiles on "CCO". Use keys tool and args.'}
    ],
    "json_compliance": [{"role": "user", "content": 'Return valid JSON only: {"ok": true, "score": 1}'}],
    "simple_chemistry_reasoning": [
        {"role": "user", "content": "In one sentence, explain why ethanol is polar."}
    ],
    "code_generation": [
        {"role": "user", "content": "Write a Python function add(a, b) that returns their sum. No explanation."}
    ],
}


def benchmark_models(config: AppConfig, run_root: str | Path = "runs") -> Path:
    router = ModelRouter(config)
    availability = router.check_model_availability()
    client = LLMClient(config)
    output: dict[str, Any] = {
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "availability": {alias: item.model_dump(mode="json") for alias, item in availability.items()},
        "results": {},
    }

    for alias, model in config.models.items():
        model_results: dict[str, Any] = {"provider": model.provider, "model": model.model, "tasks": {}}
        for task_name, messages in BENCHMARK_TASKS.items():
            started = time.perf_counter()
            result = client.complete(
                CompletionRequest(
                    model_alias=alias,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=256,
                    retries=1,
                )
            )
            elapsed = time.perf_counter() - started
            task_payload = result.model_dump(mode="json")
            task_payload["latency_seconds"] = elapsed
            if task_name == "json_compliance":
                task_payload["json_valid"] = _is_json(result.content)
            if task_name == "tool_calling_ability":
                task_payload["mentions_tool"] = "validate_smiles" in result.content
            model_results["tasks"][task_name] = task_payload
        output["results"][alias] = model_results

    run_path = Path(run_root)
    run_path.mkdir(parents=True, exist_ok=True)
    target = run_path / f"model_benchmark_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    target.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return target


def _is_json(value: str) -> bool:
    try:
        json.loads(value)
        return True
    except Exception:
        return False
