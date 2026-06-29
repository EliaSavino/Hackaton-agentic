from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.config import AppConfig, RunMode, ToolConfig
from hackathon_agents.graph import build_graph
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.baybe_tools import (
    BayBEParameter,
    BayBERecommendInput,
    BayBETarget,
    check_baybe_availability,
    recommend_experiments,
)


def _config_with_baybe(enabled: bool, allow_run: bool = False, run_mode: RunMode = RunMode.NO_DFT) -> AppConfig:
    return AppConfig(
        config_dir=Path("configs"),
        run_mode=run_mode,
        models={},
        agents={},
        tools={
            "baybe": ToolConfig(
                enabled=enabled,
                enabled_modes=[RunMode.FULL, RunMode.CHEAP, RunMode.NO_DFT],
                allow_run=allow_run,
            )
        },
    )


def _example_settings() -> dict:
    return {
        "parameters": [
            {"name": "Temperature_C", "type": "numerical_continuous", "bounds": [25, 80]},
            {"name": "Pressure_bar", "type": "numerical_discrete", "values": [1, 5, 10]},
            {"name": "Base", "type": "categorical", "values": ["NaOH", "KOtBu", "Et3N"]},
        ],
        "targets": [{"name": "Yield", "mode": "MAX"}],
        "batch_size": 3,
    }


class BayBESchemaTests(unittest.TestCase):
    def test_continuous_requires_bounds(self) -> None:
        with self.assertRaises(Exception):
            BayBEParameter(name="T", type="numerical_continuous")

    def test_discrete_requires_values(self) -> None:
        with self.assertRaises(Exception):
            BayBEParameter(name="P", type="numerical_discrete")

    def test_substance_requires_data(self) -> None:
        with self.assertRaises(Exception):
            BayBEParameter(name="Solvent", type="substance")

    def test_match_target_requires_match_value(self) -> None:
        with self.assertRaises(Exception):
            BayBETarget(name="pH", mode="MATCH")

    def test_parameter_and_target_names_must_not_overlap(self) -> None:
        with self.assertRaises(Exception):
            BayBERecommendInput(
                parameters=[BayBEParameter(name="Yield", type="numerical_discrete", values=[1, 2])],
                targets=[BayBETarget(name="Yield", mode="MAX")],
            )

    def test_continuous_options_are_low_mid_high(self) -> None:
        param = BayBEParameter(name="T", type="numerical_continuous", bounds=(0.0, 100.0))
        self.assertEqual(param.options(), [0.0, 50.0, 100.0])


class BayBEMockRecommendationTests(unittest.TestCase):
    def test_mock_returns_requested_batch_size(self) -> None:
        result = recommend_experiments({**_example_settings(), "run": False})
        self.assertTrue(result.ok)
        self.assertTrue(result.data["mock"])
        self.assertEqual(len(result.data["recommendations"]), 3)
        self.assertEqual(result.data["recommender"], "mock_space_filling")
        self.assertEqual(result.metadata["mock_reason"], "run=False")

    def test_mock_recommendations_are_within_search_space(self) -> None:
        result = recommend_experiments({**_example_settings(), "run": False})
        for row in result.data["recommendations"]:
            self.assertIn(row["Pressure_bar"], [1, 5, 10])
            self.assertIn(row["Base"], ["NaOH", "KOtBu", "Et3N"])
            self.assertGreaterEqual(row["Temperature_C"], 25)
            self.assertLessEqual(row["Temperature_C"], 80)

    def test_mock_is_deterministic(self) -> None:
        first = recommend_experiments({**_example_settings(), "run": False})
        second = recommend_experiments({**_example_settings(), "run": False})
        self.assertEqual(first.data["recommendations"], second.data["recommendations"])

    def test_mock_skips_already_measured_configurations(self) -> None:
        settings = _example_settings()
        # The first space-filling combo is (Temp=25, Pressure=1, Base=NaOH).
        settings["measurements"] = [
            {"Temperature_C": 25, "Pressure_bar": 1, "Base": "NaOH", "Yield": 10.0}
        ]
        result = recommend_experiments({**settings, "run": False})
        self.assertTrue(result.ok)
        self.assertEqual(result.data["n_prior_measurements"], 1)
        measured = {"Temperature_C": 25.0, "Pressure_bar": 1, "Base": "NaOH"}
        for row in result.data["recommendations"]:
            normalized = {k: (float(v) if k == "Temperature_C" else v) for k, v in row.items()}
            self.assertNotEqual(normalized, measured)

    def test_mock_writes_recommendations_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = recommend_experiments({**_example_settings(), "run": False, "work_dir": tmp})
            self.assertTrue(result.ok)
            csv_path = Path(result.artifacts[0])
            self.assertTrue(csv_path.exists())
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 3)

    def test_multi_target_reports_desirability(self) -> None:
        settings = _example_settings()
        settings["targets"] = [
            {"name": "Yield", "mode": "MAX", "bounds": [0, 100]},
            {"name": "Cost", "mode": "MIN", "weight": 0.5, "bounds": [0, 100]},
        ]
        result = recommend_experiments({**settings, "run": False})
        self.assertEqual(result.data["objective_kind"], "desirability")
        self.assertEqual(result.data["target_names"], ["Yield", "Cost"])

    def test_multi_target_max_min_requires_bounds(self) -> None:
        settings = _example_settings()
        settings["targets"] = [
            {"name": "Yield", "mode": "MAX"},
            {"name": "Cost", "mode": "MIN", "weight": 0.5},
        ]
        with self.assertRaises(Exception):
            BayBERecommendInput.model_validate(settings)

    def test_substance_parameter_mock_uses_labels(self) -> None:
        settings = {
            "parameters": [
                {
                    "name": "Solvent",
                    "type": "substance",
                    "data": {"DMSO": "CS(=O)C", "Water": "O", "Methanol": "CO"},
                    "encoding": "MORDRED",
                }
            ],
            "targets": [{"name": "Yield", "mode": "MAX"}],
            "batch_size": 2,
        }
        result = recommend_experiments({**settings, "run": False})
        self.assertTrue(result.ok)
        for row in result.data["recommendations"]:
            self.assertIn(row["Solvent"], ["DMSO", "Water", "Methanol"])


class BayBEAvailabilityTests(unittest.TestCase):
    def test_check_availability_returns_structured_result(self) -> None:
        result = check_baybe_availability()
        self.assertTrue(result.ok)
        self.assertIn("available", result.data)
        self.assertIn("chem_encoding_available", result.data)
        self.assertIsInstance(result.data["available"], bool)


class BayBEGraphGatingTests(unittest.TestCase):
    """BayBE should be opt-in and config-gated, never breaking the pipeline."""

    def test_graph_recommends_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_with_baybe(enabled=True)
            state = DiscoveryStatePayload(
                original_user_request="Optimize reaction yield",
                run_dir=tmp,
                run_mode=config.run_mode,
                metadata={"baybe": _example_settings()},
            )
            final = build_graph(config).invoke(state)
            tool_names = [record.tool_name for record in final.tool_results]
            self.assertIn("baybe.recommend_experiments", tool_names)
            self.assertTrue(final.metadata.get("baybe_recommendations"))

    def test_graph_skips_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_with_baybe(enabled=False)
            state = DiscoveryStatePayload(
                original_user_request="Optimize reaction yield",
                run_dir=tmp,
                run_mode=config.run_mode,
                metadata={"baybe": _example_settings()},
            )
            final = build_graph(config).invoke(state)
            tool_names = [record.tool_name for record in final.tool_results]
            self.assertNotIn("baybe.recommend_experiments", tool_names)
            self.assertEqual(final.metadata.get("baybe_source"), "disabled_by_config")

    def test_graph_ignores_when_no_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_with_baybe(enabled=True)
            state = DiscoveryStatePayload(
                original_user_request="Find candidates",
                run_dir=tmp,
                run_mode=config.run_mode,
            )
            final = build_graph(config).invoke(state)
            tool_names = [record.tool_name for record in final.tool_results]
            self.assertNotIn("baybe.recommend_experiments", tool_names)


if __name__ == "__main__":
    unittest.main()
