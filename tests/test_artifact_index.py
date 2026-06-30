from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.tools.artifact_index import write_artifact_index


class ArtifactIndexTests(unittest.TestCase):
    def test_index_records_hashes_missing_paths_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "result.json"
            artifact.write_text('{"ok": true}', encoding="utf-8")

            index_path = write_artifact_index(
                run_dir=root,
                producer="test",
                artifacts=[
                    {"path": str(artifact), "producer": "unit", "description": "Result file."},
                    {"path": str(root / "missing.csv"), "producer": "unit", "description": "Missing file."},
                ],
                provenance={"workflow": "unit_test", "ok": True},
                metadata={"example": True},
            )

            payload = json.loads(index_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["producer"], "test")
        self.assertEqual(payload["provenance"]["workflow"], "unit_test")
        by_name = {Path(entry["path"]).name: entry for entry in payload["artifacts"]}
        self.assertEqual(len(by_name["result.json"]["sha256"]), 64)
        self.assertIn(str(root / "missing.csv"), payload["missing_artifacts"])


if __name__ == "__main__":
    unittest.main()
