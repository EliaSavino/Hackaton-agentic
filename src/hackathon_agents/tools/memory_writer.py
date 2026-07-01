from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hackathon_agents.tools.base import error_result, ok_result


class MemoryEntryInput(BaseModel):
    event_type: str
    summary: str
    jsonl_path: str = "data/memory/project_memory.jsonl"
    markdown_path: str | None = "data/memory/project_memory.md"
    run_id: str | None = None
    run_dir: str | None = None
    user_request: str | None = None
    node: str | None = None
    iteration: int | None = None
    run_mode: str | None = None
    candidate_count: int | None = None
    valid_candidate_count: int | None = None
    best_score: float | None = None
    stop_reason: str | None = None
    next_actions: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    recent_messages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_markdown_entries: int = 200


def append_project_memory(input_data: MemoryEntryInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, MemoryEntryInput) else MemoryEntryInput.model_validate(input_data)
    try:
        entry = _entry_payload(parsed)
        jsonl_path = Path(parsed.jsonl_path)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

        artifacts = [str(jsonl_path)]
        data: dict[str, Any] = {"jsonl_path": str(jsonl_path), "entry": entry}
        if parsed.markdown_path:
            markdown_path = Path(parsed.markdown_path)
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            entries = _read_memory_entries(jsonl_path)
            markdown_path.write_text(
                _render_markdown(entries[-parsed.max_markdown_entries :]),
                encoding="utf-8",
            )
            artifacts.append(str(markdown_path))
            data["markdown_path"] = str(markdown_path)

        return ok_result(data, artifacts)
    except Exception as exc:
        return error_result(str(exc), {"jsonl_path": parsed.jsonl_path, "markdown_path": parsed.markdown_path})


def _entry_payload(parsed: MemoryEntryInput) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "timestamp": timestamp,
        "event_type": parsed.event_type,
        "summary": parsed.summary,
        "run_id": parsed.run_id,
        "run_dir": parsed.run_dir,
        "user_request": parsed.user_request,
        "node": parsed.node,
        "iteration": parsed.iteration,
        "run_mode": parsed.run_mode,
        "candidate_count": parsed.candidate_count,
        "valid_candidate_count": parsed.valid_candidate_count,
        "best_score": parsed.best_score,
        "stop_reason": parsed.stop_reason,
        "next_actions": parsed.next_actions,
        "artifact_paths": parsed.artifact_paths,
        "recent_messages": parsed.recent_messages,
        "metadata": parsed.metadata,
    }


def _read_memory_entries(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries


def _render_markdown(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# Project Memory",
        "",
        "Shared agent memory for knowledge transfer across runs and users.",
        "The JSONL file is the append-only source of truth; this Markdown file is regenerated for reading.",
        "",
    ]
    if not entries:
        lines.append("No memory entries have been recorded yet.")
        lines.append("")
        return "\n".join(lines)

    for entry in reversed(entries):
        title_parts = [str(entry.get("timestamp") or "unknown time"), str(entry.get("event_type") or "event")]
        node = entry.get("node")
        if node:
            title_parts.append(str(node))
        lines.append(f"## {' - '.join(title_parts)}")
        if entry.get("summary"):
            lines.extend(["", str(entry["summary"])])
        details = _entry_details(entry)
        if details:
            lines.extend(["", *details])
        artifacts = [str(path) for path in entry.get("artifact_paths") or []]
        if artifacts:
            lines.extend(["", "Artifacts:"])
            lines.extend(f"- `{path}`" for path in artifacts)
        messages = [str(message) for message in entry.get("recent_messages") or []]
        if messages:
            lines.extend(["", "Recent messages:"])
            lines.extend(f"- {message}" for message in messages[-5:])
        lines.append("")

    return "\n".join(lines)


def _entry_details(entry: dict[str, Any]) -> list[str]:
    details = []
    for key, label in [
        ("run_id", "Run"),
        ("run_dir", "Run directory"),
        ("run_mode", "Run mode"),
        ("iteration", "Iteration"),
        ("candidate_count", "Candidates"),
        ("valid_candidate_count", "Valid candidates"),
        ("best_score", "Best score"),
        ("stop_reason", "Stop reason"),
    ]:
        value = entry.get(key)
        if value is not None:
            details.append(f"- {label}: `{value}`")
    next_actions = entry.get("next_actions") or []
    if next_actions:
        details.append(f"- Next actions: {', '.join(str(action) for action in next_actions)}")
    return details
