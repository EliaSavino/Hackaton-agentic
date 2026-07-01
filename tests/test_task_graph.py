from __future__ import annotations

import unittest

from hackathon_agents.schemas.tasks import PlannedTask, PlannerTaskGraph
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.task_graph import mark_task_completed, mark_task_started, task_graph_summary


class TaskGraphTests(unittest.TestCase):
    def test_task_status_helpers_update_metadata_graph(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="x",
            metadata={
                "planner_task_graph": PlannerTaskGraph(
                    objective="x",
                    tasks=[
                        PlannedTask(
                            id="plan",
                            title="Plan",
                            task_type="planning",
                            agent="planner",
                            description="Plan the work.",
                        )
                    ],
                ).model_dump(mode="json")
            },
        )

        mark_task_started(state, "plan", reason="begin")
        mark_task_completed(state, "plan", reason="done", artifacts=["state.json"])

        task = state.metadata["planner_task_graph"]["tasks"][0]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["attempts"], 1)
        self.assertEqual(task["produced_artifacts"], ["state.json"])
        self.assertEqual(task_graph_summary(state)["status_counts"], {"completed": 1})
        self.assertEqual(state.metadata["planner_task_summary"]["completed_task_ids"], ["plan"])

    def test_summary_reports_ready_and_blocked_tasks(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="x",
            metadata={
                "planner_task_graph": PlannerTaskGraph(
                    objective="x",
                    tasks=[
                        PlannedTask(
                            id="plan",
                            title="Plan",
                            task_type="planning",
                            agent="planner",
                            description="Plan the work.",
                        ),
                        PlannedTask(
                            id="run_tools",
                            title="Run tools",
                            task_type="tool_execution",
                            agent="tool_executor",
                            description="Run deterministic tools.",
                            depends_on=["plan"],
                        ),
                        PlannedTask(
                            id="write",
                            title="Write",
                            task_type="reporting",
                            agent="writer",
                            description="Write artifacts.",
                            depends_on=["run_tools"],
                        ),
                    ],
                ).model_dump(mode="json")
            },
        )

        summary = task_graph_summary(state)

        self.assertEqual(summary["ready_task_ids"], ["plan"])
        self.assertEqual(
            summary["blocked_tasks"],
            [
                {"id": "run_tools", "blocked_by": ["plan"]},
                {"id": "write", "blocked_by": ["run_tools"]},
            ],
        )

        mark_task_completed(state, "plan")
        summary = task_graph_summary(state)

        self.assertEqual(summary["ready_task_ids"], ["run_tools"])
        self.assertEqual(summary["blocked_tasks"], [{"id": "write", "blocked_by": ["run_tools"]}])


if __name__ == "__main__":
    unittest.main()
