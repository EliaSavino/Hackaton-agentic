from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from hackathon_agents.tools.base import error_result, ok_result


def read_json(path: str | Path):
    try:
        target = Path(path)
        return ok_result({"path": str(target), "content": json.loads(target.read_text(encoding="utf-8"))})
    except Exception as exc:
        return error_result(str(exc), {"path": str(path)})


def write_json(path: str | Path, content: Any):
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")
        return ok_result({"path": str(target)}, [str(target)])
    except Exception as exc:
        return error_result(str(exc), {"path": str(path)})


def read_csv(path: str | Path):
    try:
        target = Path(path)
        with target.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return ok_result({"path": str(target), "rows": rows})
    except Exception as exc:
        return error_result(str(exc), {"path": str(path)})


def write_csv(path: str | Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None):
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        resolved_fieldnames = fieldnames or sorted({key for row in rows for key in row.keys()})
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=resolved_fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return ok_result({"path": str(target), "row_count": len(rows)}, [str(target)])
    except Exception as exc:
        return error_result(str(exc), {"path": str(path)})
