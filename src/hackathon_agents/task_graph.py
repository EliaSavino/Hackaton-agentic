from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from hackathon_agents.schemas.tasks import PlannerTaskGraph
from hackathon_agents.state import DiscoveryStatePayload


TaskStatus = Literal["planned", "running", "completed", "failed", "skipped"]


def get_task_graph(state: DiscoveryStatePayload) -> PlannerTaskGraph | None:
    raw = state.metadata.get("planner_task_graph")
    if not raw:
        return None
    try:
        return PlannerTaskGraph.model_validate(raw)
    except Exception as exc:
        state.add_error(f"planner_task_graph: {exc}")
        return None


def mark_task_started(state: DiscoveryStatePayload, task_id: str, *, reason: str | None = None) -> None:
    _update_task(state, task_id, status="running", reason=reason, increment_attempt=True)


def mark_task_completed(
    state: DiscoveryStatePayload,
    task_id: str,
    *,
    reason: str | None = None,
    artifacts: list[str] | None = None,
) -> None:
    _update_task(state, task_id, status="completed", reason=reason, artifacts=artifacts)


def mark_task_failed(state: DiscoveryStatePayload, task_id: str, *, reason: str) -> None:
    _update_task(state, task_id, status="failed", reason=reason)


def mark_task_skipped(state: DiscoveryStatePayload, task_id: str, *, reason: str) -> None:
    _update_task(state, task_id, status="skipped", reason=reason)


def task_graph_summary(state: DiscoveryStatePayload) -> dict[str, Any]:
    graph = get_task_graph(state)
    if graph is None:
        return {}
    return _summarize_graph(graph)


def _summarize_graph(graph: PlannerTaskGraph) -> dict[str, Any]:
    counts: dict[str, int] = {}
    status_by_id = {task.id: task.status for task in graph.tasks}
    blocked_tasks: list[dict[str, Any]] = []
    ready_task_ids: list[str] = []

    for task in graph.tasks:
        counts[task.status] = counts.get(task.status, 0) + 1
        if task.status != "planned":
            continue
        blockers = [
            dependency
            for dependency in task.depends_on
            if status_by_id.get(dependency) != "completed"
        ]
        if blockers:
            blocked_tasks.append({"id": task.id, "blocked_by": blockers})
        else:
            ready_task_ids.append(task.id)

    return {
        "objective": graph.objective,
        "task_count": len(graph.tasks),
        "status_counts": counts,
        "planned_task_ids": [task.id for task in graph.tasks if task.status == "planned"],
        "running_task_ids": [task.id for task in graph.tasks if task.status == "running"],
        "completed_task_ids": [task.id for task in graph.tasks if task.status == "completed"],
        "failed_task_ids": [task.id for task in graph.tasks if task.status == "failed"],
        "skipped_task_ids": [task.id for task in graph.tasks if task.status == "skipped"],
        "ready_task_ids": ready_task_ids,
        "blocked_tasks": blocked_tasks,
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "task_type": task.task_type,
                "agent": task.agent,
                "status": task.status,
                "depends_on": task.depends_on,
                "attempts": task.attempts,
                "produced_artifacts": task.produced_artifacts,
            }
            for task in graph.tasks
        ],
    }


def _update_task(
    state: DiscoveryStatePayload,
    task_id: str,
    *,
    status: TaskStatus,
    reason: str | None = None,
    artifacts: list[str] | None = None,
    increment_attempt: bool = False,
) -> None:
    graph = get_task_graph(state)
    if graph is None:
        return
    now = _now()
    found = False
    for task in graph.tasks:
        if task.id != task_id:
            continue
        found = True
        task.status = status
        task.status_reason = reason
        if status == "running":
            task.started_at = task.started_at or now
            task.completed_at = None
            if increment_attempt:
                task.attempts += 1
        if status in {"completed", "failed", "skipped"}:
            task.completed_at = now
            task.started_at = task.started_at or now
        if artifacts:
            task.produced_artifacts = _dedupe([*task.produced_artifacts, *artifacts])
        event = status if reason is None else f"{status}: {reason}"
        task.events.append(f"{now} {event}")
        break
    if not found:
        state.add_error(f"planner_task_graph: unknown task id {task_id!r}")
        return
    state.metadata["planner_task_graph"] = graph.model_dump(mode="json")
    state.metadata["planner_task_summary"] = _summarize_graph(graph)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
