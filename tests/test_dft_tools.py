from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.tools.dft_tools import (
    check_stationary_point,
    compare_dft_energies,
    parse_dft_output,
    plan_dft_jobs,
    render_dft_input,
)


class DFTToolsTests(unittest.TestCase):
    def test_plan_dft_jobs_uses_existing_schema(self) -> None:
        result = plan_dft_jobs(
            {
                "molecule_or_structure": "H 0 0 0\nH 0 0 0.74",
                "linked_hypothesis_id": "h-001",
                "include_frequency": True,
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["count"], 3)
        self.assertEqual(result.data["jobs"][0]["linked_hypothesis_id"], "h-001")

    def test_render_dft_input_can_write_orca_file(self) -> None:
        planned = plan_dft_jobs({"molecule_or_structure": "H 0 0 0\nH 0 0 0.74"})
        with tempfile.TemporaryDirectory() as directory:
            result = render_dft_input({"job": planned.data["jobs"][0], "output_dir": directory})
            output_path = Path(result.data["path"])

            self.assertTrue(result.ok, result.error)
            self.assertTrue(output_path.exists())
            self.assertIn("! B3LYP def2-SVP", output_path.read_text(encoding="utf-8"))

    def test_parse_dft_output_extracts_energy_and_frequencies(self) -> None:
        result = parse_dft_output(
            {
                "job_id": "job-1",
                "output_text": """
                FINAL SINGLE POINT ENERGY     -76.40401234
                Frequencies --  100.0 250.0 -12.5
                """,
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertAlmostEqual(result.data["energy_hartree"], -76.40401234)
        self.assertIn(-12.5, result.data["frequencies_cm1"])

    def test_compare_dft_energies_ranks_relative_energy(self) -> None:
        result = compare_dft_energies(
            {
                "results": [
                    {"job_id": "high", "energy_hartree": -99.99},
                    {"job_id": "low", "energy_hartree": -100.00},
                ]
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["rows"][0]["label"], "low")
        self.assertAlmostEqual(result.data["rows"][0]["relative_energy"], 0.0)
        self.assertGreater(result.data["rows"][0]["boltzmann_population"], result.data["rows"][1]["boltzmann_population"])

    def test_check_stationary_point_classifies_transition_state(self) -> None:
        result = check_stationary_point(
            {
                "frequencies_cm1": [-450.0, 120.0, 240.0],
                "expected": "transition_state",
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["classification"], "transition_state_candidate")
        self.assertEqual(result.data["flags"], [])


if __name__ == "__main__":
    unittest.main()
