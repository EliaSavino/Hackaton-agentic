from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.schemas.linkers import ADC_GOAL_KEYS, ADCGoalProfile
from hackathon_agents.tools.adc_linker_objective import (
    CANONICAL_WARHEAD_PAIR,
    CLEAVABLE_MOTIF_SMARTS,
    DEFAULT_ADC_GOAL_PROFILE,
    LABILE_ALERT_SMARTS,
    build_adc_linkinvent_objective,
)
from hackathon_agents.tools.reinvent_tools import (
    ReinventInput,
    build_reinvent_config,
    generate_with_reinvent,
    reinvent_records,
)


class ADCGoalProfileTests(unittest.TestCase):
    def test_weights_clamped_and_unknown_keys_ignored(self) -> None:
        profile = ADCGoalProfile(weights={"solubility": 5.0, "size": -3.0, "bogus": 0.9})
        self.assertEqual(profile.weights["solubility"], 1.0)  # clamped high
        self.assertEqual(profile.weights["size"], 0.0)  # clamped low
        self.assertNotIn("bogus", profile.weights)
        self.assertEqual(set(profile.weights.keys()), set(ADC_GOAL_KEYS))


class ADCObjectiveBuilderTests(unittest.TestCase):
    def test_default_objective_is_valid_linkinvent(self) -> None:
        obj = build_adc_linkinvent_objective(DEFAULT_ADC_GOAL_PROFILE)
        self.assertEqual(obj["generator_type"], "linkinvent")
        self.assertEqual(obj["run_type"], "staged_learning")
        self.assertEqual(obj["prior"], ".linkinvent")
        self.assertEqual(obj["input_smiles"], [CANONICAL_WARHEAD_PAIR])
        component_types = [c["component_type"] for c in obj["scoring"]]
        self.assertIn("FragmentSlogP", component_types)
        self.assertIn("FragmentMolecularWeight", component_types)
        self.assertIn("MatchingSubstructure", component_types)  # cleavable motif on
        self.assertIn("CustomAlerts", component_types)  # stability alerts on
        # The whole objective must parse as a ReinventInput.
        ReinventInput.model_validate({"work_dir": "x", **obj})

    def test_zero_weight_drops_component(self) -> None:
        profile = ADCGoalProfile(weights={"solubility": 0.0, "size": 1.0}, require_cleavable_motif=False, enforce_stability_alerts=False)
        obj = build_adc_linkinvent_objective(profile)
        component_types = [c["component_type"] for c in obj["scoring"]]
        self.assertNotIn("FragmentSlogP", component_types)
        self.assertNotIn("MatchingSubstructure", component_types)
        self.assertNotIn("CustomAlerts", component_types)
        self.assertIn("FragmentMolecularWeight", component_types)

    def test_objective_renders_valid_reinvent_config(self) -> None:
        obj = build_adc_linkinvent_objective(DEFAULT_ADC_GOAL_PROFILE)
        config = build_reinvent_config(ReinventInput.model_validate({"work_dir": "x", **obj}))
        self.assertEqual(config["run_type"], "staged_learning")
        self.assertEqual(config["parameters"]["prior_file"], ".linkinvent")
        stage = config["stage"][0]
        comp = stage["scoring"]["component"]
        # Nested REINVENT shape: [{"FragmentSlogP": {"endpoint": [...]}}, ...]
        first_key = list(comp[0].keys())[0]
        self.assertIn("endpoint", comp[0][first_key])

    def test_cleavable_and_labile_smarts_are_valid(self) -> None:
        from rdkit import Chem

        for smarts in [*CLEAVABLE_MOTIF_SMARTS, *LABILE_ALERT_SMARTS]:
            self.assertIsNotNone(Chem.MolFromSmarts(smarts), f"invalid SMARTS: {smarts}")

    def test_mock_generate_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            obj = build_adc_linkinvent_objective(DEFAULT_ADC_GOAL_PROFILE)
            result = generate_with_reinvent({"work_dir": tmp, **obj})  # run=False by default
            self.assertTrue(result.ok)
            self.assertTrue(result.data["mock"])
            self.assertEqual(result.data["generator_type"], "linkinvent")
            # Warhead .smi file written for the linkinvent generator.
            self.assertTrue((Path(tmp) / "reinvent_inputs.smi").exists())
            config = json.loads(Path(result.data["config_path"]).read_text(encoding="utf-8"))
            self.assertEqual(config["run_type"], "staged_learning")
            molecules = reinvent_records(result.data)
            self.assertTrue(molecules)


if __name__ == "__main__":
    unittest.main()
