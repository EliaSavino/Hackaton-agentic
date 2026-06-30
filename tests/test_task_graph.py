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


if __name__ == "__main__":
    unittest.main()
