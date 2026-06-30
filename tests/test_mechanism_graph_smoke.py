from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.mechanism.graph import run_mechanism_loop


class MechanismGraphSmokeTests(unittest.TestCase):
    def test_mock_mechanism_loop_completes_two_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = run_mechanism_loop(
                objective="Infer mechanism for photochemical reaction A + B -> P",
                rounds=2,
                mode="mock",
                run_root=tmp,
            )
            run_dir = Path(state.run_dir or "")
            self.assertEqual(state.round_index, 2)
            self.assertEqual(len(state.datasets), 2)
            self.assertGreaterEqual(len(state.hypotheses), 3)
            self.assertGreaterEqual(len(state.rankings), 3)
            self.assertTrue((run_dir / "state.json").exists())
            self.assertTrue((run_dir / "hypotheses.json").exists())
            self.assertTrue((run_dir / "experiments.json").exists())
            self.assertTrue((run_dir / "trace.log").exists())
            self.assertTrue((run_dir / "report.json").exists())
            self.assertTrue((run_dir / "report.docx").exists())
            self.assertTrue((run_dir / "artifact_index.json").exists())
            self.assertEqual(state.metadata.get("artifact_index_path"), str(run_dir / "artifact_index.json"))
            artifact_index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact_index["schema_version"], 2)
            self.assertEqual(artifact_index["provenance"]["workflow"], "mechanism")
            self.assertEqual(artifact_index["provenance"]["dataset_count"], len(state.datasets))
            self.assertEqual(artifact_index["provenance"]["hypothesis_count"], len(state.hypotheses))
            self.assertTrue(any(entry["relative_path"] == "state.json" for entry in artifact_index["artifacts"]))
            self.assertTrue(any((run_dir / "datasets").glob("*.csv")))


if __name__ == "__main__":
    unittest.main()
