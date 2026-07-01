from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.llm.validators import validate_latex_output
from hackathon_agents.schemas.linkers import ADCGoalProfile
from hackathon_agents.tools.paper_writer import write_adc_paper


def _candidates() -> list[dict]:
    return [
        {
            "name": "linker-1",
            "smiles": "O=C(NCC(=O)NCCO)CCO",
            "score": 0.72,
            "descriptors": {"adc_solubility": 0.8, "adc_cleavability": 1.0, "adc_stability": 1.0},
        },
        {
            "name": "linker-2",
            "smiles": "OCCOCCOCCO",
            "score": 0.55,
            "descriptors": {"adc_solubility": 0.9, "adc_cleavability": 0.4, "adc_stability": 1.0},
        },
    ]


class PaperWriterTests(unittest.TestCase):
    def test_paper_has_all_sections_and_valid_latex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "adc_paper.tex"
            result = write_adc_paper(
                {
                    "output_path": str(out),
                    "user_request": "Design a cathepsin-cleavable ADC linker",
                    "goal_profile": ADCGoalProfile().model_dump(mode="json"),
                    "candidates": _candidates(),
                    "decision_trail": [
                        {
                            "iteration": 1,
                            "overrides": {"weights": {"solubility": 0.6}},
                            "rationale": "too lipophilic",
                            "weights_before": {"solubility": 1.0},
                            "weights_after": {"solubility": 0.6},
                        }
                    ],
                    "warhead_pair": "O=C1C=CC(=O)N1CCCCCC(=O)*|*Nc1ccccc1",
                }
            )
            self.assertTrue(result.ok, result.error)
            text = out.read_text(encoding="utf-8")
            for heading in ["Introduction and Background", "Methods", "Results", "Discussion", "Conclusion"]:
                self.assertIn(heading, text)
            # Candidate + decision-trail data present.
            self.assertIn("linker-1", text)
            self.assertIn("too lipophilic", text)
            # Compile-safe per the shared validator.
            self.assertTrue(validate_latex_output(text).ok)
            self.assertIn("\\end{document}", text)

    def test_paper_handles_empty_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "adc_paper.tex"
            result = write_adc_paper(
                {
                    "output_path": str(out),
                    "user_request": "Design an ADC linker",
                    "goal_profile": ADCGoalProfile().model_dump(mode="json"),
                    "candidates": [],
                    "decision_trail": [],
                }
            )
            self.assertTrue(result.ok, result.error)
            text = out.read_text(encoding="utf-8")
            self.assertIn("No scored linker candidates", text)
            self.assertIn("did not adjust the objective", text)
            self.assertTrue(validate_latex_output(text).ok)


if __name__ == "__main__":
    unittest.main()
