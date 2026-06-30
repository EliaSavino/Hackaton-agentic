from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.benchmarks.system import benchmark_system


class SystemBenchmarkTests(unittest.TestCase):
    def test_system_benchmark_reports_cases_criteria_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = benchmark_system(run_root=tmp)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            index = json.loads((output_path.parent / "artifact_index.json").read_text(encoding="utf-8"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["case_count"], 4)
        self.assertEqual(payload["passed_count"], 4)
        self.assertEqual(payload["failed_count"], 0)
        case_names = {case["name"] for case in payload["cases"]}
        self.assertEqual(
            case_names,
            {
                "kinetics_to_mechanism_report",
                "smiles_to_descriptor_table",
                "paper_snippet_to_review",
                "statistics_regression_summary",
            },
        )
        for case in payload["cases"]:
            self.assertTrue(case["criteria"])
            self.assertGreaterEqual(case["duration_seconds"], 0.0)
        self.assertEqual(index["provenance"]["workflow"], "system_benchmark")
        self.assertEqual(index["provenance"]["case_count"], 4)


if __name__ == "__main__":
    unittest.main()
