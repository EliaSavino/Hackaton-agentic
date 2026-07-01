from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hackathon_agents.config import AppConfig, ModelConfig, ModelRoutingConfig, RunMode
from hackathon_agents.llm.benchmark import benchmark_models
from hackathon_agents.llm.client import CompletionResult
from hackathon_agents.llm.router import ModelAvailability


def _config() -> AppConfig:
    return AppConfig(
        config_dir=Path("configs"),
        run_mode=RunMode.CHEAP,
        models={
            "fake": ModelConfig(
                provider="other",
                model="fake/model",
                capabilities=["reasoning"],
                enabled=True,
            )
        },
        model_routing=ModelRoutingConfig(default_alias="fake"),
    )


class LLMBenchmarkTests(unittest.TestCase):
    def test_benchmark_records_json_repair_metadata(self) -> None:
        availability = {
            "fake": ModelAvailability(
                alias="fake",
                provider="other",
                model="fake/model",
                available=True,
                reason="mocked",
            )
        }

        def fake_complete(request):
            prompt = request.messages[0]["content"]
            if "Return valid JSON only" in prompt:
                content = '```json\n{"ok": true, "score": 1}\n```'
            elif "validate_smiles" in prompt:
                content = '{"tool": "validate_smiles", "args": {"smiles": "CCO"}}'
            else:
                content = "ready"
            return CompletionResult(ok=True, content=content, model_alias="fake", provider="other")

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "hackathon_agents.llm.benchmark.ModelRouter.check_model_availability",
                return_value=availability,
            ), patch("hackathon_agents.llm.benchmark.LLMClient.complete", side_effect=fake_complete):
                output_path = benchmark_models(_config(), run_root=tmp)
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        result = payload["results"]["fake"]["tasks"]["json_compliance"]
        self.assertTrue(result["json_valid"])
        self.assertTrue(result["json_repaired"])
        self.assertEqual(result["normalized_json"], '{"ok": true, "score": 1}')
        self.assertEqual(result["json_validation_errors"], [])
        self.assertIn("stripped markdown fence", result["json_validation_warnings"])


if __name__ == "__main__":
    unittest.main()
