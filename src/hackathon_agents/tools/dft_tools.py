from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from hackathon_agents.tools.base import error_result, ok_result
from hackathon_agents.tools.dft_job import DFTCalculationType, DFTJob, DFTResult


class DFTPlanInput(BaseModel):
    molecule_or_structure: str
    linked_hypothesis_id: str = "standalone"
    reason_for_calculation: str = "screen relative energy"
    job_prefix: str = "dft"
    charge: int = 0
    multiplicity: int = Field(default=1, ge=1)
    method: str = "B3LYP"
    basis: str = "def2-SVP"
    solvent_model: str | None = None
    include_frequency: bool = False
    include_transition_state: bool = False


class DFTInputRenderInput(BaseModel):
    job: DFTJob | dict[str, Any]
    program: str = "orca"
    output_dir: str | None = None
    filename: str | None = None


class DFTOutputParseInput(BaseModel):
    output_text: str | None = None
    output_path: str | None = None
    job_id: str = "parsed-output"


class DFTEnergyComparisonInput(BaseModel):
    results: list[dict[str, Any]]
    label_key: str = "job_id"
    energy_key: str = "energy_hartree"
    temperature_k: float = Field(default=298.15, gt=0.0)
    unit: Literal["kcal/mol", "kJ/mol"] = "kcal/mol"


class StationaryPointCheckInput(BaseModel):
    frequencies_cm1: list[float]
    expected: Literal["minimum", "transition_state", "any"] = "any"
    imaginary_threshold_cm1: float = Field(default=20.0, ge=0.0)


_ENERGY_PATTERNS = [
    re.compile(r"FINAL\s+SINGLE\s+POINT\s+ENERGY\s+(-?\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"SCF\s+Done:\s+E\([^)]+\)\s+=\s+(-?\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"Total\s+Energy\s*[:=]\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE),
]
_FREQUENCY_RE = re.compile(r"(?:VIBRATIONAL\s+FREQUENCIES|Frequencies\s+--)(.*)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_HARTREE_TO_KCAL = 627.5094740631
_HARTREE_TO_KJ = 2625.4996394799
_R_KCAL = 0.00198720425864083
_R_KJ = 0.00831446261815324


def plan_dft_jobs(input_data: DFTPlanInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, DFTPlanInput) else DFTPlanInput.model_validate(input_data)
    try:
        calculation_types = [DFTCalculationType.OPTIMIZATION, DFTCalculationType.SINGLE_POINT]
        if parsed.include_frequency:
            calculation_types.append(DFTCalculationType.FREQUENCY)
        if parsed.include_transition_state:
            calculation_types.insert(0, DFTCalculationType.TRANSITION_STATE)

        jobs = []
        for index, calculation_type in enumerate(calculation_types, start=1):
            jobs.append(
                DFTJob(
                    id=f"{parsed.job_prefix}-{index:02d}-{calculation_type.value}",
                    molecule_or_structure=parsed.molecule_or_structure,
                    charge=parsed.charge,
                    multiplicity=parsed.multiplicity,
                    method=parsed.method,
                    basis=parsed.basis,
                    solvent_model=parsed.solvent_model,
                    calculation_type=calculation_type,
                    reason_for_calculation=parsed.reason_for_calculation,
                    linked_hypothesis_id=parsed.linked_hypothesis_id,
                ).model_dump(mode="json")
            )
        return ok_result({"jobs": jobs, "count": len(jobs)})
    except Exception as exc:
        return error_result(str(exc), {"linked_hypothesis_id": parsed.linked_hypothesis_id})


def render_dft_input(input_data: DFTInputRenderInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, DFTInputRenderInput) else DFTInputRenderInput.model_validate(input_data)
    try:
        job = parsed.job if isinstance(parsed.job, DFTJob) else DFTJob.model_validate(parsed.job)
        program = parsed.program.lower()
        if program != "orca":
            return error_result("Only ORCA input rendering is currently implemented.", {"program": parsed.program})
        content = _render_orca(job)
        artifacts = []
        data = {"job_id": job.id, "program": "orca", "content": content}
        if parsed.output_dir:
            output_dir = Path(parsed.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = parsed.filename or f"{job.id}.inp"
            path = output_dir / filename
            path.write_text(content, encoding="utf-8")
            data["path"] = str(path)
            artifacts.append(str(path))
        return ok_result(data, artifacts)
    except Exception as exc:
        return error_result(str(exc), {"program": parsed.program})


def parse_dft_output(input_data: DFTOutputParseInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, DFTOutputParseInput) else DFTOutputParseInput.model_validate(input_data)
    try:
        text = parsed.output_text
        if text is None:
            if parsed.output_path is None:
                return error_result("Either output_text or output_path is required.", {"job_id": parsed.job_id})
            text = Path(parsed.output_path).read_text(encoding="utf-8", errors="ignore")
        energy = _parse_energy(text)
        frequencies = _parse_frequencies(text)
        has_imaginary = any(frequency < 0 for frequency in frequencies)
        diagnostics = _parse_diagnostics(text, frequencies)
        result = DFTResult(
            job_id=parsed.job_id,
            status="completed" if diagnostics["terminated_normally"] else "parsed",
            energy_hartree=energy,
            frequencies_cm1=frequencies,
            output_files=[parsed.output_path] if parsed.output_path else [],
            parsed_ok=energy is not None or bool(frequencies) or diagnostics["terminated_normally"],
            summary=_summary(energy, frequencies, has_imaginary),
        )
        data = result.model_dump(mode="json")
        data["diagnostics"] = diagnostics
        return ok_result(data, result.output_files)
    except Exception as exc:
        return error_result(str(exc), {"job_id": parsed.job_id, "output_path": parsed.output_path})


def compare_dft_energies(input_data: DFTEnergyComparisonInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, DFTEnergyComparisonInput) else DFTEnergyComparisonInput.model_validate(input_data)
    try:
        rows = []
        for index, result in enumerate(parsed.results):
            energy = result.get(parsed.energy_key)
            if energy is None:
                continue
            rows.append(
                {
                    "label": str(result.get(parsed.label_key) or result.get("id") or f"state-{index + 1}"),
                    "energy_hartree": float(energy),
                    "input_index": index,
                }
            )
        if not rows:
            return error_result("No usable energies were provided.", {"energy_key": parsed.energy_key})
        min_energy = min(row["energy_hartree"] for row in rows)
        factor = _HARTREE_TO_KCAL if parsed.unit == "kcal/mol" else _HARTREE_TO_KJ
        rt = (_R_KCAL if parsed.unit == "kcal/mol" else _R_KJ) * parsed.temperature_k
        weights = []
        for row in rows:
            relative = (row["energy_hartree"] - min_energy) * factor
            row["relative_energy"] = relative
            row["relative_energy_unit"] = parsed.unit
            weight = math.exp(max(-700.0, -relative / rt))
            weights.append(weight)
            row["boltzmann_weight"] = weight
        total_weight = sum(weights)
        for row, weight in zip(rows, weights):
            row["boltzmann_population"] = weight / total_weight if total_weight else 0.0
        rows.sort(key=lambda item: item["relative_energy"])
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        return ok_result({"rows": rows, "temperature_k": parsed.temperature_k, "unit": parsed.unit})
    except Exception as exc:
        return error_result(str(exc), {"energy_key": parsed.energy_key})


def check_stationary_point(input_data: StationaryPointCheckInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, StationaryPointCheckInput) else StationaryPointCheckInput.model_validate(input_data)
    try:
        imaginary = [frequency for frequency in parsed.frequencies_cm1 if frequency < -parsed.imaginary_threshold_cm1]
        near_zero = [frequency for frequency in parsed.frequencies_cm1 if abs(frequency) <= parsed.imaginary_threshold_cm1]
        if len(imaginary) == 0:
            classification = "minimum"
        elif len(imaginary) == 1:
            classification = "transition_state_candidate"
        else:
            classification = "higher_order_saddle"
        flags = []
        if parsed.expected == "minimum" and imaginary:
            flags.append("unexpected_imaginary_frequency")
        if parsed.expected == "transition_state" and len(imaginary) != 1:
            flags.append("transition_state_should_have_one_imaginary_frequency")
        if near_zero:
            flags.append("near_zero_frequencies_present")
        return ok_result(
            {
                "classification": classification,
                "imaginary_count": len(imaginary),
                "imaginary_frequencies_cm1": imaginary,
                "near_zero_frequencies_cm1": near_zero,
                "expected": parsed.expected,
                "flags": flags,
            }
        )
    except Exception as exc:
        return error_result(str(exc), {"expected": parsed.expected})


def _render_orca(job: DFTJob) -> str:
    task = {
        "optimization": "Opt",
        "frequency": "Freq",
        "single_point": "SP",
        "transition_state": "OptTS Freq",
    }.get(str(job.calculation_type), "Opt")
    solvent = f" CPCM({job.solvent_model})" if job.solvent_model else ""
    return "\n".join(
        [
            f"! {job.method} {job.basis}{solvent} {task} TightSCF",
            "",
            "%pal nprocs 4 end",
            "",
            f"* xyz {job.charge} {job.multiplicity}",
            job.molecule_or_structure.strip(),
            "*",
            "",
        ]
    )


def _parse_energy(text: str) -> float | None:
    for pattern in _ENERGY_PATTERNS:
        match = pattern.search(text)
        if match:
            return float(match.group(1))
    return None


def _parse_frequencies(text: str) -> list[float]:
    frequencies: list[float] = []
    for line in text.splitlines():
        if "cm**-1" in line or "Frequencies --" in line or "Frequency:" in line:
            frequencies.extend(float(value) for value in _NUMBER_RE.findall(line))
    if frequencies:
        return frequencies
    for match in _FREQUENCY_RE.finditer(text):
        frequencies.extend(float(value) for value in _NUMBER_RE.findall(match.group(1)))
    return frequencies


def _parse_diagnostics(text: str, frequencies: list[float]) -> dict[str, Any]:
    lower = text.lower()
    return {
        "terminated_normally": "orca terminated normally" in lower or "normal termination" in lower,
        "scf_converged": "scf converged" in lower or "scf done" in lower,
        "imaginary_count": sum(1 for frequency in frequencies if frequency < 0),
    }


def _summary(energy: float | None, frequencies: list[float], has_imaginary: bool) -> str:
    pieces = []
    if energy is not None:
        pieces.append(f"energy={energy:.8f} hartree")
    if frequencies:
        pieces.append(f"{len(frequencies)} frequencies parsed")
    if has_imaginary:
        pieces.append("imaginary frequency present")
    if not pieces:
        return "No energy or frequency values were parsed."
    return "; ".join(pieces)
