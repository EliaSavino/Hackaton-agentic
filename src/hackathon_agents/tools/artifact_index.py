from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_artifact_index(
    *,
    run_dir: str | Path,
    producer: str,
    artifacts: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> Path:
    """Write a compact run artifact index for provenance and handoff."""

    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    entries = [_normalize_artifact(root, artifact, producer) for artifact in artifacts or []]
    entries.extend(_discover_standard_artifacts(root, producer))
    deduped = _dedupe(entries)
    payload = {
        "schema_version": 2,
        "generated_at": _now(),
        "run_dir": str(root),
        "producer": producer,
        "artifact_count": len(deduped),
        "missing_artifacts": [entry["path"] for entry in deduped if not entry["exists"]],
        "artifacts": deduped,
        "provenance": provenance or {},
        "metadata": metadata or {},
    }
    output_path = root / "artifact_index.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def tool_result_artifacts(tool_results: list[Any]) -> list[dict[str, Any]]:
    """Extract artifact paths from ToolExecutionRecord-like objects."""

    artifacts: list[dict[str, Any]] = []
    for record in tool_results:
        tool_name = getattr(record, "tool_name", "tool")
        result = getattr(record, "result", None)
        for artifact in getattr(result, "artifacts", []) or []:
            artifacts.append(
                {
                    "path": artifact,
                    "kind": _kind_for_path(Path(artifact)),
                    "producer": tool_name,
                    "description": f"Artifact emitted by {tool_name}.",
                    "metadata": {
                        "tool_ok": getattr(result, "ok", None),
                        "tool_error": getattr(result, "error", None),
                    },
                }
            )
    return artifacts


def discovery_provenance(state: Any) -> dict[str, Any]:
    """Build a concise provenance summary from DiscoveryStatePayload-like state."""

    tool_results = list(getattr(state, "tool_results", []) or [])
    model_calls = list(getattr(state, "metadata", {}).get("model_calls", []) or [])
    return {
        "workflow": "discovery",
        "request": getattr(state, "original_user_request", None),
        "run_mode": _value(getattr(state, "run_mode", None)),
        "iteration": getattr(state, "iteration", None),
        "max_iterations": getattr(state, "max_iterations", None),
        "stop_reason": getattr(state, "stop_reason", None),
        "candidate_count": len(getattr(state, "candidate_molecules", []) or []),
        "error_count": len(getattr(state, "errors", []) or []),
        "errors": list(getattr(state, "errors", []) or [])[-20:],
        "tool_calls": _tool_call_summary(tool_results),
        "model_calls": _model_call_summary(model_calls),
        "planner_task_summary": _planner_task_summary(getattr(state, "metadata", {})),
        "tool_registry_summary": getattr(state, "metadata", {}).get("tool_registry_summary", {}),
        "final_report_path": getattr(state, "final_report_path", None),
    }


def mechanism_provenance(state: Any) -> dict[str, Any]:
    """Build a concise provenance summary from MechanismDiscoveryState-like state."""

    return {
        "workflow": "mechanism",
        "objective": getattr(state, "objective", None),
        "mode": getattr(state, "mode", None),
        "round_index": getattr(state, "round_index", None),
        "max_rounds": getattr(state, "max_rounds", None),
        "dataset_count": len(getattr(state, "datasets", []) or []),
        "hypothesis_count": len(getattr(state, "hypotheses", []) or []),
        "fit_result_count": len(getattr(state, "fit_results", []) or []),
        "ranking_count": len(getattr(state, "rankings", []) or []),
        "dft_job_count": len(getattr(state, "dft_jobs", []) or []),
        "robot_job_count": len(getattr(state, "robot_jobs", []) or []),
        "hpc_job_count": len(getattr(state, "hpc_jobs", []) or []),
        "error_count": len(getattr(state, "errors", []) or []),
        "validation_error_count": len(getattr(state, "validation_errors", []) or []),
        "errors": list(getattr(state, "errors", []) or [])[-20:],
        "critic_note_count": len(getattr(state, "critic_notes", []) or []),
        "report_json_path": getattr(state, "report_json_path", None),
        "report_docx_path": getattr(state, "report_docx_path", None),
    }


def _normalize_artifact(root: Path, artifact: dict[str, Any], default_producer: str) -> dict[str, Any]:
    raw_path = Path(str(artifact.get("path", "")))
    path = raw_path if raw_path.is_absolute() else root / raw_path
    return {
        "path": str(path),
        "relative_path": _relative(path, root),
        "kind": artifact.get("kind") or _kind_for_path(path),
        "producer": artifact.get("producer") or default_producer,
        "description": artifact.get("description") or "",
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() and path.is_file() else None,
        "sha256": _sha256(path) if path.exists() and path.is_file() else None,
        "metadata": artifact.get("metadata", {}),
    }


def _discover_standard_artifacts(root: Path, producer: str) -> list[dict[str, Any]]:
    names = [
        "state.json",
        "report.json",
        "report.docx",
        "report.tex",
        "descriptors.csv",
        "qed_plot.png",
        "hypotheses.json",
        "experiments.json",
        "trace.log",
    ]
    artifacts = []
    for name in names:
        path = root / name
        if path.exists():
            artifacts.append(
                {
                    "path": str(path),
                    "relative_path": name,
                    "kind": _kind_for_path(path),
                    "producer": producer,
                    "description": f"Standard run artifact: {name}.",
                    "exists": True,
                    "bytes": path.stat().st_size if path.is_file() else None,
                    "sha256": _sha256(path) if path.is_file() else None,
                    "metadata": {},
                }
            )
    for child in sorted((root / "datasets").glob("*")) if (root / "datasets").exists() else []:
        artifacts.append(
            {
                "path": str(child),
                "relative_path": _relative(child, root),
                "kind": _kind_for_path(child),
                "producer": "kinetics_io",
                "description": "Parsed or serialized kinetic dataset.",
                "exists": child.exists(),
                "bytes": child.stat().st_size if child.is_file() else None,
                "sha256": _sha256(child) if child.is_file() else None,
                "metadata": {},
            }
        )
    return artifacts


def _dedupe(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique = []
    for entry in entries:
        path = entry["path"]
        if path in seen:
            continue
        seen.add(path)
        unique.append(entry)
    return unique


def _kind_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".csv": "table",
        ".docx": "document",
        ".json": "json",
        ".log": "log",
        ".png": "plot",
        ".tex": "latex",
    }.get(suffix, "artifact")


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _tool_call_summary(tool_results: list[Any]) -> dict[str, Any]:
    by_tool: dict[str, dict[str, int]] = {}
    failed = []
    for record in tool_results:
        name = getattr(record, "tool_name", "tool")
        result = getattr(record, "result", None)
        ok = bool(getattr(result, "ok", False))
        entry = by_tool.setdefault(name, {"count": 0, "ok": 0, "failed": 0})
        entry["count"] += 1
        entry["ok" if ok else "failed"] += 1
        if not ok:
            failed.append({"tool_name": name, "error": getattr(result, "error", None)})
    return {
        "count": len(tool_results),
        "by_tool": by_tool,
        "failed": failed[-20:],
    }


def _model_call_summary(model_calls: list[dict[str, Any]]) -> dict[str, Any]:
    attempted = [call for call in model_calls if call.get("attempted")]
    ok = [call for call in model_calls if call.get("ok")]
    return {
        "count": len(model_calls),
        "attempted_count": len(attempted),
        "ok_count": len(ok),
        "fallback_count": sum(1 for call in model_calls if call.get("fallback")),
        "calls": model_calls[-20:],
    }


def _planner_task_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    stored = metadata.get("planner_task_summary")
    if isinstance(stored, dict):
        return stored

    graph = metadata.get("planner_task_graph") or {}
    tasks = graph.get("tasks", []) if isinstance(graph, dict) else []
    counts: dict[str, int] = {}
    status_by_id = {task.get("id"): task.get("status") for task in tasks if isinstance(task, dict)}
    ready_task_ids: list[str] = []
    blocked_tasks: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
        if status != "planned":
            continue
        blockers = [
            dependency
            for dependency in task.get("depends_on", [])
            if status_by_id.get(dependency) != "completed"
        ]
        if blockers:
            blocked_tasks.append({"id": task.get("id"), "blocked_by": blockers})
        else:
            ready_task_ids.append(task.get("id"))
    return {
        "objective": graph.get("objective") if isinstance(graph, dict) else None,
        "task_count": len(tasks),
        "status_counts": counts,
        "planned_task_ids": [
            task.get("id") for task in tasks if isinstance(task, dict) and task.get("status") == "planned"
        ],
        "running_task_ids": [
            task.get("id") for task in tasks if isinstance(task, dict) and task.get("status") == "running"
        ],
        "completed_task_ids": [
            task.get("id") for task in tasks if isinstance(task, dict) and task.get("status") == "completed"
        ],
        "failed_task_ids": [
            task.get("id") for task in tasks if isinstance(task, dict) and task.get("status") == "failed"
        ],
        "skipped_task_ids": [
            task.get("id") for task in tasks if isinstance(task, dict) and task.get("status") == "skipped"
        ],
        "ready_task_ids": ready_task_ids,
        "blocked_tasks": blocked_tasks,
        "tasks": [
            {
                "id": task.get("id"),
                "title": task.get("title"),
                "task_type": task.get("task_type"),
                "agent": task.get("agent"),
                "status": task.get("status"),
                "depends_on": task.get("depends_on", []),
                "attempts": task.get("attempts"),
                "produced_artifacts": task.get("produced_artifacts", []),
            }
            for task in tasks
            if isinstance(task, dict)
        ],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
