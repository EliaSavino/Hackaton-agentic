from __future__ import annotations

import unittest

from hackathon_agents.mechanism.hypothesis import generate_initial_hypotheses
from hackathon_agents.mechanism.kinetic_fitting import fit_hypothesis_to_dataset, simulate_kinetic_dataset
from hackathon_agents.mechanism.schemas import KineticExperiment, KineticExperimentVariables


class KineticFittingTests(unittest.TestCase):
    def test_synthetic_kinetic_data_has_expected_shape(self) -> None:
        dataset = simulate_kinetic_dataset(_experiment())
        self.assertGreaterEqual(len(dataset.time_points), 8)
        self.assertEqual(set(dataset.concentration_profiles), {"A", "B", "P"})
        for profile in dataset.concentration_profiles.values():
            self.assertEqual(len(profile), len(dataset.time_points))

    def test_least_squares_fitting_runs(self) -> None:
        dataset = simulate_kinetic_dataset(_experiment(), noise_level=0.0)
        hypothesis = generate_initial_hypotheses("Infer mechanism for photochemical reaction A + B -> P")[0]
        result = fit_hypothesis_to_dataset(hypothesis, dataset)
        self.assertTrue(result.ok, result.error)
        self.assertIn("k", result.parameters)
        self.assertIsNotNone(result.rmse)


def _experiment() -> KineticExperiment:
    return KineticExperiment(
        id="exp-test",
        objective="test synthetic kinetics",
        variables=KineticExperimentVariables(
            concentrations={"A": 1.0, "B": 1.0},
            residence_time=12.0,
            light_intensity=1.0,
            catalyst_loading=0.05,
        ),
        robot_protocol={"schema_version": "test"},
    )


if __name__ == "__main__":
    unittest.main()
