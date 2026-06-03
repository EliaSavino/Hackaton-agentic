from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from hackathon_agents.tools.base import error_result, ok_result

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "hackathon_agents_matplotlib"))


class PlotInput(BaseModel):
    data: list[dict[str, Any]] | None = None
    csv_path: str | None = None
    x_key: str
    y_key: str
    output_path: str
    title: str = "Model output"
    kind: Literal["line", "scatter", "bar"] = "scatter"


def generate_plot(input_data: PlotInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, PlotInput) else PlotInput.model_validate(input_data)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        rows = parsed.data
        if rows is None:
            import pandas as pd

            if parsed.csv_path is None:
                return error_result("Either data or csv_path is required.")
            rows = pd.read_csv(parsed.csv_path).to_dict(orient="records")

        x_values = [row[parsed.x_key] for row in rows]
        y_values = [float(row[parsed.y_key]) for row in rows]

        output = Path(parsed.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
        if parsed.kind == "line":
            ax.plot(x_values, y_values, marker="o")
        elif parsed.kind == "bar":
            ax.bar(x_values, y_values)
        else:
            ax.scatter(x_values, y_values)
        ax.set_title(parsed.title)
        ax.set_xlabel(parsed.x_key)
        ax.set_ylabel(parsed.y_key)
        fig.autofmt_xdate(rotation=30)
        fig.savefig(output, dpi=160)
        plt.close(fig)
        return ok_result({"path": str(output), "points": len(rows)}, [str(output)])
    except Exception as exc:
        return error_result(str(exc), {"output_path": parsed.output_path})
