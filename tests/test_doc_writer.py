from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.tools.doc_writer import write_scientific_report


@unittest.skipUnless(importlib.util.find_spec("docx") is not None, "python-docx is not installed")
class DocWriterTests(unittest.TestCase):
    def test_write_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.docx"
            result = write_scientific_report(
                {
                    "output_path": str(output),
                    "user_request": "Find promising candidates",
                    "candidates": [{"name": "ethanol", "smiles": "CCO", "descriptors": {"mol_wt": 46.0}}],
                    "critic_notes": ["Smoke test note"],
                }
            )
            self.assertTrue(result.ok)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
