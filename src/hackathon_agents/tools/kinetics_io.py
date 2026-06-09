from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from hackathon_agents.mechanism.schemas import KineticDataset


def parse_kinetics_file(path: str | Path, *, experiment_id: str | None = None) -> KineticDataset:
    """Parse CSV or JSON kinetic traces into a KineticDataset."""

    input_path = Path(path)
    suffix = input_path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if "experiment_id" not in payload and experiment_id:
            payload["experiment_id"] = experiment_id
        payload.setdefault("raw_files", [str(input_path)])
        return KineticDataset.model_validate(payload)
    if suffix == ".csv":
        return _parse_csv(input_path, experiment_id=experiment_id)
    raise ValueError(f"unsupported kinetic data format: {input_path.suffix}")


def write_kinetic_dataset(dataset: KineticDataset, output_dir: str | Path) -> list[Path]:
    """Write dataset JSON and CSV artifacts under a round's datasets directory."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{dataset.experiment_id}.json"
    csv_path = directory / f"{dataset.experiment_id}.csv"
    json_path.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")

    species = list(dataset.concentration_profiles)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", *species])
        for index, time_point in enumerate(dataset.time_points):
            writer.writerow([time_point, *[dataset.concentration_profiles[name][index] for name in species]])
    return [json_path, csv_path]


def _parse_csv(path: Path, *, experiment_id: str | None = None) -> KineticDataset:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError(f"kinetics CSV has no rows: {path}")
    fieldnames = reader.fieldnames or []
    time_key = _time_key(fieldnames)
    species = [field for field in fieldnames if field != time_key]
    if not species:
        raise ValueError("kinetics CSV must contain at least one concentration column")
    time_points = [_float(row[time_key], key=time_key) for row in rows]
    profiles: dict[str, list[float]] = {
        name: [_float(row[name], key=name) for row in rows]
        for name in species
    }
    quality_flags = _quality_flags(time_points, profiles)
    return KineticDataset(
        experiment_id=experiment_id or path.stem,
        time_points=time_points,
        concentration_profiles=profiles,
        metadata={"source_path": str(path)},
        raw_files=[str(path)],
        parsed_ok=not quality_flags,
        quality_flags=quality_flags,
    )


def _time_key(fieldnames: list[str]) -> str:
    for candidate in ("time", "time_s", "t"):
        if candidate in fieldnames:
            return candidate
    return fieldnames[0]


def _float(value: Any, *, key: str) -> float:
    try:
        return float(value)
    except Exception as exc:
        raise ValueError(f"could not parse numeric value for {key}: {value!r}") from exc


def _quality_flags(time_points: list[float], profiles: dict[str, list[float]]) -> list[str]:
    flags: list[str] = []
    if any(next_time < current for current, next_time in zip(time_points, time_points[1:])):
        flags.append("time_not_monotonic")
    for species, values in profiles.items():
        if any(value < -1e-9 for value in values):
            flags.append(f"negative_concentration:{species}")
    return flags
