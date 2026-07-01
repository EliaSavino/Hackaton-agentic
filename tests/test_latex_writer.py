from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.tools.latex_writer import write_latex_report


class LatexWriterTests(unittest.TestCase):
    def test_write_latex_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.tex"
            result = write_latex_report(
                {
                    "output_path": str(output),
                    "user_request": "Measure A_B & yield at 10%",
                    "plan": {
                        "objective": "Find robust candidates",
                        "assumptions": ["Evidence must be checked before claiming success."],
                        "steps": [{"name": "Run tools", "description": "Validate candidates", "agent": "tool_executor"}],
                    },
                    "candidates": [{"name": "nitrile", "smiles": "C#N", "descriptors": {"mol_wt": 27.0}}],
                    "critic_notes": ["Keep claims proportional."],
                }
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.data["latex_validation"]["errors"], [])
            self.assertTrue(result.data["latex_validation"]["ok"])
            self.assertTrue(output.exists())
            text = output.read_text(encoding="utf-8")
            self.assertIn(r"A\_B \& yield at 10\%", text)
            self.assertIn(r"C\#N", text)
            self.assertIn(r"\begin{longtable}", text)

    def test_writes_optional_bibliography_stub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.tex"
            bibliography = Path(tmp) / "references.bib"
            result = write_latex_report(
                {
                    "output_path": str(output),
                    "bibliography_path": str(bibliography),
                    "user_request": "Draft report",
                }
            )

            self.assertTrue(result.ok)
            self.assertTrue(result.data["latex_validation"]["ok"])
            self.assertTrue(bibliography.exists())
            self.assertIn(str(bibliography), result.artifacts)


if __name__ == "__main__":
    unittest.main()
