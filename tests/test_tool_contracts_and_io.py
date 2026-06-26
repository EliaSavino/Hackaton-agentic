from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hackathon_agents.tools.base import error_result, ok_result
from hackathon_agents.tools.file_io import read_csv, read_json, write_csv, write_json
from hackathon_agents.tools.orca import check_orca_availability, generate_orca_input, run_orca
from hackathon_agents.tools.plotting import generate_plot
from hackathon_agents.tools.python_exec import run_python
from hackathon_agents.tools.xtb import check_xtb_availability, run_xtb


class ToolResultContractTests(unittest.TestCase):
    def test_ok_result_defaults_to_empty_payloads(self) -> None:
        result = ok_result()

        self.assertTrue(result.ok)
        self.assertEqual(result.data, {})
        self.assertEqual(result.artifacts, [])
        self.assertIsNone(result.error)

    def test_error_result_preserves_context_and_artifacts(self) -> None:
        result = error_result("failed", {"step": "parse"}, ["artifact.txt"])

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "failed")
        self.assertEqual(result.data["step"], "parse")
        self.assertEqual(result.artifacts, ["artifact.txt"])


class FileIOToolTests(unittest.TestCase):
    def test_write_and_read_json_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "payload.json"

            write = write_json(target, {"b": 2, "a": [1, 3]})
            read = read_json(target)

        self.assertTrue(write.ok, write.error)
        self.assertEqual(write.artifacts, [str(target)])
        self.assertTrue(read.ok, read.error)
        self.assertEqual(read.data["content"], {"a": [1, 3], "b": 2})

    def test_read_json_reports_missing_file(self) -> None:
        result = read_json("/definitely/not/a/file.json")

        self.assertFalse(result.ok)
        self.assertIn("file", result.error.lower())
        self.assertEqual(result.data["path"], "/definitely/not/a/file.json")

    def test_write_csv_infers_sorted_fieldnames_and_read_csv_returns_strings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "table.csv"

            write = write_csv(target, [{"b": 2, "a": 1}, {"a": 3, "b": 4}])
            with target.open("r", encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle))
            read = read_csv(target)

        self.assertTrue(write.ok, write.error)
        self.assertEqual(write.data["row_count"], 2)
        self.assertEqual(header, ["a", "b"])
        self.assertTrue(read.ok, read.error)
        self.assertEqual(read.data["rows"][0], {"a": "1", "b": "2"})

    def test_write_csv_honors_explicit_field_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "table.csv"

            write = write_csv(target, [{"b": 2, "a": 1}], fieldnames=["b", "a"])
            with target.open("r", encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle))

        self.assertTrue(write.ok, write.error)
        self.assertEqual(header, ["b", "a"])


class PythonExecToolTests(unittest.TestCase):
    def test_run_python_captures_stdout_and_public_variables(self) -> None:
        result = run_python(
            {
                "code": "print('answer', math.sqrt(16))\nvalue = statistics.mean([2, 4, 6])",
                "timeout_seconds": 3,
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertIn("answer 4.0", result.data["stdout"])
        self.assertIn("'value': 4", result.data["variables"])

    def test_run_python_blocks_imports(self) -> None:
        result = run_python({"code": "import os\nvalue = 1", "timeout_seconds": 3})

        self.assertFalse(result.ok)
        self.assertIn("Blocked syntax: Import", result.error)

    def test_run_python_blocks_dunder_attribute_access(self) -> None:
        result = run_python({"code": "value = (1).__class__", "timeout_seconds": 3})

        self.assertFalse(result.ok)
        self.assertIn("Blocked dunder attribute", result.error)

    def test_run_python_times_out_long_running_code(self) -> None:
        result = run_python({"code": "while True:\n    pass", "timeout_seconds": 1})

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Python snippet timed out.")
        self.assertEqual(result.data["timeout_seconds"], 1)


class OrcaToolTests(unittest.TestCase):
    def test_check_orca_availability_reports_missing_executable(self) -> None:
        result = check_orca_availability("definitely-not-orca")

        self.assertTrue(result.ok, result.error)
        self.assertFalse(result.data["available"])
        self.assertEqual(result.data["executable"], "definitely-not-orca")

    def test_generate_orca_input_writes_expected_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = generate_orca_input(
                {
                    "coordinates": "H 0 0 0\nH 0 0 0.74\n",
                    "work_dir": directory,
                    "filename": "hydrogen.inp",
                    "method": "PBE0",
                    "basis": "def2-TZVP",
                    "charge": 1,
                    "multiplicity": 2,
                }
            )
            content = Path(result.data["input_path"]).read_text(encoding="utf-8")

        self.assertTrue(result.ok, result.error)
        self.assertIn("! PBE0 def2-TZVP TightSCF", content)
        self.assertIn("* xyz 1 2", content)
        self.assertIn("H 0 0 0.74", content)
        self.assertEqual(result.artifacts, [result.data["input_path"]])

    def test_run_orca_dry_run_returns_generated_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_orca({"coordinates": "H 0 0 0", "work_dir": directory, "run": False})

        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.data["input_path"].endswith("job.inp"))
        self.assertIn("* xyz 0 1", result.data["content"])

    def test_run_orca_unavailable_preserves_input_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_orca(
                {
                    "coordinates": "H 0 0 0",
                    "work_dir": directory,
                    "executable": "definitely-not-orca",
                }
            )
            input_exists = Path(result.data["input_path"]).exists()

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "ORCA executable is not available.")
        self.assertTrue(input_exists)
        self.assertEqual(result.artifacts, [result.data["input_path"]])

    def test_run_orca_invokes_available_executable_in_work_dir(self) -> None:
        completed = SimpleNamespace(returncode=7, stdout="x" * 5000, stderr="warning")
        with tempfile.TemporaryDirectory() as directory:
            with patch("hackathon_agents.tools.orca.check_orca_availability") as availability:
                with patch("hackathon_agents.tools.orca.subprocess.run", return_value=completed) as run_mock:
                    availability.return_value = ok_result(
                        {"available": True, "executable": "orca", "path": "/usr/local/bin/orca"}
                    )

                    result = run_orca({"coordinates": "H 0 0 0", "work_dir": directory})

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["returncode"], 7)
        self.assertEqual(len(result.data["stdout"]), 4000)
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.kwargs["cwd"], Path(directory))
        self.assertEqual(run_mock.call_args.args[0], ["/usr/local/bin/orca", "job.inp"])


class XtbToolTests(unittest.TestCase):
    def test_check_xtb_availability_reports_missing_executable(self) -> None:
        result = check_xtb_availability("definitely-not-xtb")

        self.assertTrue(result.ok, result.error)
        self.assertFalse(result.data["available"])
        self.assertEqual(result.data["executable"], "definitely-not-xtb")

    def test_run_xtb_returns_error_when_executable_is_missing(self) -> None:
        result = run_xtb(
            {
                "xyz_path": "mol.xyz",
                "work_dir": "/tmp",
                "executable": "definitely-not-xtb",
            }
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "xTB executable is not available.")

    def test_run_xtb_invokes_subprocess_with_configured_args(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="done", stderr="")
        with tempfile.TemporaryDirectory() as directory:
            with patch("hackathon_agents.tools.xtb.check_xtb_availability") as availability:
                with patch("hackathon_agents.tools.xtb.subprocess.run", return_value=completed) as run_mock:
                    availability.return_value = ok_result(
                        {"available": True, "executable": "xtb", "path": "/usr/local/bin/xtb"}
                    )

                    result = run_xtb(
                        {
                            "xyz_path": "mol.xyz",
                            "work_dir": directory,
                            "args": ["--sp", "--gfn", "2"],
                        }
                    )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["stdout"], "done")
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0], ["/usr/local/bin/xtb", "mol.xyz", "--sp", "--gfn", "2"])
        self.assertEqual(run_mock.call_args.kwargs["cwd"], Path(directory))


class PlottingToolTests(unittest.TestCase):
    def test_generate_plot_from_inline_data_creates_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "plot.png"
            result = generate_plot(
                {
                    "data": [{"time": 0, "yield": 0.0}, {"time": 1, "yield": 0.4}],
                    "x_key": "time",
                    "y_key": "yield",
                    "output_path": str(target),
                    "kind": "line",
                    "title": "Yield profile",
                }
            )
            artifact_exists = target.exists()
            artifact_size = target.stat().st_size

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["points"], 2)
        self.assertEqual(result.artifacts, [str(target)])
        self.assertTrue(artifact_exists)
        self.assertGreater(artifact_size, 0)

    def test_generate_plot_requires_data_or_csv_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = generate_plot(
                {
                    "x_key": "time",
                    "y_key": "yield",
                    "output_path": str(Path(directory) / "plot.png"),
                }
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Either data or csv_path is required.")


if __name__ == "__main__":
    unittest.main()
