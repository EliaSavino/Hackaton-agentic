from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hackathon_agents.tools.base import error_result, ok_result


class OrcaInput(BaseModel):
    coordinates: str
    work_dir: str
    filename: str = "job.inp"
    method: str = "B3LYP"
    basis: str = "def2-SVP"
    charge: int = 0
    multiplicity: int = 1
    executable: str = "orca"
    timeout_seconds: int = 300
    run: bool = True


def check_orca_availability(executable: str = "orca"):
    path = shutil.which(executable)
    return ok_result({"available": path is not None, "executable": executable, "path": path})


def generate_orca_input(input_data: OrcaInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, OrcaInput) else OrcaInput.model_validate(input_data)
    try:
        work_dir = Path(parsed.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        input_path = work_dir / parsed.filename
        content = (
            f"! {parsed.method} {parsed.basis} TightSCF\n\n"
            f"* xyz {parsed.charge} {parsed.multiplicity}\n"
            f"{parsed.coordinates.strip()}\n"
            "*\n"
        )
        input_path.write_text(content, encoding="utf-8")
        return ok_result({"input_path": str(input_path), "content": content}, [str(input_path)])
    except Exception as exc:
        return error_result(str(exc), {"work_dir": parsed.work_dir, "filename": parsed.filename})


def run_orca(input_data: OrcaInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, OrcaInput) else OrcaInput.model_validate(input_data)
    generated = generate_orca_input(parsed)
    if not generated.ok:
        return generated
    if not parsed.run:
        return generated

    availability = check_orca_availability(parsed.executable)
    if not availability.data["available"]:
        return error_result(
            "ORCA executable is not available.",
            {**availability.data, "input_path": generated.data.get("input_path")},
            generated.artifacts,
        )

    try:
        input_path = Path(generated.data["input_path"])
        completed = subprocess.run(
            [availability.data["path"], input_path.name],
            cwd=input_path.parent,
            check=False,
            capture_output=True,
            text=True,
            timeout=parsed.timeout_seconds,
        )
        return ok_result(
            {
                "input_path": str(input_path),
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            },
            generated.artifacts,
        )
    except Exception as exc:
        return error_result(str(exc), {"input_path": generated.data.get("input_path")}, generated.artifacts)
