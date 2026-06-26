from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from hackathon_agents.tools import robrains_bo
from hackathon_agents.tools.robrains_bo import RoBrainsSuggestionInput


class FakeTensor:
    def __init__(self, value):
        if isinstance(value, FakeTensor):
            value = value.value
        self.value = value

    @property
    def ndim(self) -> int:
        if isinstance(self.value, list) and self.value and isinstance(self.value[0], list):
            return 2
        return 1

    @property
    def shape(self):
        if self.ndim == 2:
            return (len(self.value), len(self.value[0]))
        return (len(self.value),)

    def flatten(self):
        if self.ndim == 2:
            return FakeTensor([item for row in self.value for item in row])
        return self

    def reshape(self, *_shape):
        return self

    def tolist(self):
        return self.value


class FakeTorch:
    float64 = "float64"

    @staticmethod
    def as_tensor(value, dtype=None):
        return FakeTensor(value)


class FakeMLParameterType:
    CONT = "Continuous"
    CAT = "Categorical"
    DISC = "Discrete"


class FakeMLParameter:
    def __init__(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs


class FakeBackend:
    def __init__(self):
        self.settings = {}
        self.results_df = pd.DataFrame()
        self.run_index = 0

    def validate_and_update(self, key, value):
        self.settings[key] = value

    def ML_prime(self, ML_parameters, targets, save_path, model_parameters=None, results_df=None):
        self.ML_parameters = ML_parameters
        self.targets = targets
        self.save_path = save_path
        self.model_parameters_arg = model_parameters
        if results_df is not None:
            self.results_df = results_df

    def first_run(self):
        return SimpleNamespace(next_points=[[0.5, 1.0]], predicted_y=None, meta={"fake": True})

    def update(self):
        return SimpleNamespace(
            next_points=[[0.75, 0.0]],
            predicted_y=([[2.5]], [[0.2]]),
            meta={"fake": True},
        )


def fake_runtime():
    return robrains_bo._RoBrainsRuntime(
        SingleBayesianOptiBackend=FakeBackend,
        MLParameter=FakeMLParameter,
        MLParameterType=FakeMLParameterType,
        LocalBackendAPI=None,
        pd=pd,
        torch=FakeTorch,
    )


class RoBrainsBoTests(unittest.TestCase):
    def test_availability_reports_missing_repo_without_error(self) -> None:
        result = robrains_bo.check_robrains_availability({"repo_path": "/definitely/missing/robrains"})

        self.assertTrue(result.ok)
        self.assertFalse(result.data["available"])
        self.assertFalse(result.data["repo_exists"])

    def test_suggest_initial_design_decodes_robrains_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(robrains_bo, "_load_robrains_runtime", return_value=(fake_runtime(), None)):
                result = robrains_bo.suggest_robrains_experiments(
                    {
                        "repo_path": tmpdir,
                        "output_dir": tmpdir,
                        "parameters": [
                            {"name": "temperature", "kind": "continuous", "min_value": 20.0, "max_value": 100.0},
                            {"name": "solvent", "kind": "categorical", "values": ["MeCN", "EtOH"]},
                        ],
                        "objectives": [{"name": "yield"}],
                        "batch_size": 1,
                    }
                )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["mode"], "initial_design")
        self.assertEqual(result.data["suggestions"], [{"temperature": 60.0, "solvent": "EtOH"}])
        self.assertEqual(result.data["batch_size"], 1)

    def test_suggest_update_inverts_minimize_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(robrains_bo, "_load_robrains_runtime", return_value=(fake_runtime(), None)):
                result = robrains_bo.suggest_robrains_experiments(
                    {
                        "repo_path": tmpdir,
                        "output_dir": tmpdir,
                        "parameters": [
                            {"name": "temperature", "kind": "continuous", "min_value": 20.0, "max_value": 100.0},
                            {"name": "solvent", "kind": "categorical", "values": ["MeCN", "EtOH"]},
                        ],
                        "objectives": [{"name": "cost", "direction": "minimize"}],
                        "observations": [{"temperature": 40.0, "solvent": "EtOH", "cost": 4.0}],
                    }
                )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["mode"], "bayesian_update")
        self.assertEqual(result.data["suggestions"], [{"temperature": 80.0, "solvent": "MeCN"}])
        self.assertEqual(result.data["predicted_objectives"], [{"cost": -2.5, "cost_variance": 0.2}])

    def test_parameter_validation_requires_continuous_bounds(self) -> None:
        with self.assertRaises(ValueError):
            RoBrainsSuggestionInput.model_validate(
                {
                    "parameters": [{"name": "temperature", "kind": "continuous"}],
                    "objectives": [{"name": "yield"}],
                }
            )


if __name__ == "__main__":
    unittest.main()
