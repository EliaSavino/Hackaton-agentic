from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hackathon_agents.tools.base import error_result, ok_result


class XtbInput(BaseModel):
    xyz_path: str
    work_dir: str
    executable: str = "xtb"
    args: list[str] = Field(default_factory=lambda: ["--opt"])
    timeout_seconds: int = 120


def check_xtb_availability(executable: str = "xtb"):
    path = shutil.which(executable)
    return ok_result({"available": path is not None, "executable": executable, "path": path})


def run_xtb(input_data: XtbInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, XtbInput) else XtbInput.model_validate(input_data)
    availability = check_xtb_availability(parsed.executable)
    if not availability.data["available"]:
        return error_result("xTB executable is not available.", availability.data)

    try:
        work_dir = Path(parsed.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        command = [availability.data["path"], parsed.xyz_path, *parsed.args]
        completed = subprocess.run(
            command,
            cwd=work_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=parsed.timeout_seconds,
        )
        return ok_result(
            {
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        )
    except Exception as exc:
        return error_result(str(exc), {"xyz_path": parsed.xyz_path, "work_dir": parsed.work_dir})
