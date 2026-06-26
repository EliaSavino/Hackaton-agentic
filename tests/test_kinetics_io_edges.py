from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.mechanism.schemas import KineticDataset
from hackathon_agents.tools.kinetics_io import parse_kinetics_file, write_kinetic_dataset


class KineticsIOTests(unittest.TestCase):
    def test_parse_json_injects_experiment_id_and_raw_file_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text(
                json.dumps(
                    {
                        "time_points": [0.0, 1.0],
                        "concentration_profiles": {"P": [0.0, 0.2]},
                    }
                ),
                encoding="utf-8",
            )

            dataset = parse_kinetics_file(path, experiment_id="exp-json")

        self.assertEqual(dataset.experiment_id, "exp-json")
        self.assertEqual(dataset.raw_files, [str(path)])
        self.assertEqual(dataset.concentration_profiles["P"], [0.0, 0.2])

    def test_parse_json_preserves_existing_experiment_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text(
                json.dumps(
                    {
                        "experiment_id": "from-file",
                        "time_points": [0.0, 1.0],
                        "concentration_profiles": {"P": [0.0, 0.2]},
                    }
                ),
                encoding="utf-8",
            )

            dataset = parse_kinetics_file(path, experiment_id="ignored")

        self.assertEqual(dataset.experiment_id, "from-file")

    def test_parse_csv_accepts_time_alias_and_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alias.csv"
            path.write_text("time_s,A,P\n0,1,0\n2,0.7,0.3\n", encoding="utf-8")

            dataset = parse_kinetics_file(path)

        self.assertEqual(dataset.experiment_id, "alias")
        self.assertEqual(dataset.time_points, [0.0, 2.0])
        self.assertEqual(dataset.concentration_profiles["A"], [1.0, 0.7])
        self.assertEqual(dataset.metadata["source_path"], str(path))

    def test_parse_csv_uses_first_column_as_time_when_no_known_time_key_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.csv"
            path.write_text("elapsed,A\n0,1\n1,0.8\n", encoding="utf-8")

            dataset = parse_kinetics_file(path, experiment_id="exp-custom")

        self.assertEqual(dataset.experiment_id, "exp-custom")
        self.assertEqual(dataset.time_points, [0.0, 1.0])
        self.assertEqual(dataset.concentration_profiles, {"A": [1.0, 0.8]})

    def test_parse_csv_marks_negative_concentrations_as_quality_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "negative.csv"
            path.write_text("time,A,P\n0,1,0\n1,-0.1,0.2\n", encoding="utf-8")

            dataset = parse_kinetics_file(path)

        self.assertFalse(dataset.parsed_ok)
        self.assertIn("negative_concentration:A", dataset.quality_flags)

    def test_parse_csv_rejects_non_monotonic_time_grid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-time.csv"
            path.write_text("time,A\n1,1\n0,0.9\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "time_points must be sorted"):
                parse_kinetics_file(path)

    def test_parse_csv_rejects_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.csv"
            path.write_text("time,A\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "has no rows"):
                parse_kinetics_file(path)

    def test_parse_csv_requires_concentration_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "time-only.csv"
            path.write_text("time\n0\n1\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "at least one concentration column"):
                parse_kinetics_file(path)

    def test_parse_csv_reports_non_numeric_values_with_column_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-value.csv"
            path.write_text("time,A\n0,one\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "numeric value for A"):
                parse_kinetics_file(path)

    def test_parse_kinetics_file_rejects_unsupported_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.tsv"
            path.write_text("time\tA\n0\t1\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported kinetic data format"):
                parse_kinetics_file(path)

    def test_write_kinetic_dataset_writes_json_and_csv_roundtrip(self) -> None:
        dataset = KineticDataset(
            experiment_id="exp-write",
            time_points=[0.0, 1.0],
            concentration_profiles={"A": [1.0, 0.6], "P": [0.0, 0.4]},
        )
        with tempfile.TemporaryDirectory() as directory:
            artifacts = write_kinetic_dataset(dataset, directory)
            json_path = Path(directory) / "exp-write.json"
            csv_path = Path(directory) / "exp-write.csv"
            parsed_json = parse_kinetics_file(json_path)
            parsed_csv = parse_kinetics_file(csv_path)
            csv_text = csv_path.read_text(encoding="utf-8")

        self.assertEqual(artifacts, [json_path, csv_path])
        self.assertEqual(parsed_json.experiment_id, "exp-write")
        self.assertEqual(parsed_csv.concentration_profiles["P"], [0.0, 0.4])
        self.assertIn("time,A,P", csv_text)


if __name__ == "__main__":
    unittest.main()
