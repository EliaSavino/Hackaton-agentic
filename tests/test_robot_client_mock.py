from __future__ import annotations

import unittest

from hackathon_agents.mechanism.schemas import KineticExperiment, KineticExperimentVariables
from hackathon_agents.tools.robot_client import MockRobotClient


class MockRobotClientTests(unittest.TestCase):
    def test_robot_mock_returns_dataset(self) -> None:
        client = MockRobotClient()
        job_id = client.submit_experiment(
            KineticExperiment(
                id="exp-robot",
                objective="mock robot experiment",
                variables=KineticExperimentVariables(concentrations={"A": 1.0, "B": 1.0}),
                robot_protocol={"schema_version": "test"},
            )
        )
        self.assertEqual(client.get_status(job_id), "completed")
        dataset = client.fetch_results(job_id)
        self.assertEqual(dataset.experiment_id, "exp-robot")
        self.assertIn("P", dataset.concentration_profiles)
        self.assertTrue(dataset.parsed_ok)


if __name__ == "__main__":
    unittest.main()
