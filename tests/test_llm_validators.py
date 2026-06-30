from __future__ import annotations

import unittest

from hackathon_agents.llm.validators import strip_markdown_fence, validate_json_output, validate_latex_output


class LLMValidatorTests(unittest.TestCase):
    def test_json_validator_accepts_fenced_json(self) -> None:
        result = validate_json_output('``` json\n{"ok": true}\n```')

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.normalized, '{"ok": true}')
        self.assertEqual(result.parsed, {"ok": True})
        self.assertIn("stripped markdown fence", result.warnings or [])

    def test_json_validator_extracts_embedded_json(self) -> None:
        result = validate_json_output('Here is the payload: {"ok": true, "score": 1} done.')

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.parsed, {"ok": True, "score": 1})
        self.assertIn("extracted embedded JSON object", result.warnings or [])

    def test_latex_validator_rejects_unclosed_tabular(self) -> None:
        result = validate_latex_output("\\subsection{Results}\n\\begin{tabular}{ll}\nA & B")

        self.assertFalse(result.ok)
        self.assertIn("tabular environment is not closed", result.errors)

    def test_latex_validator_accepts_complete_document(self) -> None:
        latex = "\n".join(
            [
                "\\documentclass{article}",
                "\\usepackage{longtable}",
                "\\begin{document}",
                "\\section{Results}",
                "\\begin{longtable}{ll}",
                "A & B \\\\",
                "\\end{longtable}",
                "\\end{document}",
            ]
        )

        result = validate_latex_output(latex)

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])

    def test_latex_validator_repairs_surrounding_fence(self) -> None:
        result = validate_latex_output("``` latex\n\\section{Results}\nPlain text.\n```")

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.normalized, "\\section{Results}\nPlain text.")
        self.assertIn("stripped markdown fence", result.warnings or [])

    def test_latex_validator_rejects_mismatched_environment(self) -> None:
        result = validate_latex_output("\\section{Results}\n\\begin{table}\n\\end{tabular}")

        self.assertFalse(result.ok)
        self.assertIn("table environment closed by tabular", result.errors)

    def test_strip_markdown_fence_leaves_plain_text(self) -> None:
        self.assertEqual(strip_markdown_fence("plain text"), "plain text")


if __name__ == "__main__":
    unittest.main()
