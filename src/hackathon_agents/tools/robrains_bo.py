from __future__ import annotations

import os
import sys
from pathlib import Path
from types import MethodType
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, Field, model_validator

from hackathon_agents.tools.base import error_result, ok_result


DEFAULT_ROBRAINS_REPO_PATH = "/Users/es/GitHub/RoBrains"


class RoBrainsAvailabilityInput(BaseModel):
    repo_path: str | None = None


class RoBrainsParameterSpec(BaseModel):
    name: str
    kind: Literal["continuous", "categorical", "discrete"] = "continuous"
    min_value: float | None = None
    max_value: float | None = None
    values: list[str | int | float | bool] = Field(default_factory=list)
    unit: str = "-"

    @model_validator(mode="after")
    def validate_parameter_spec(self) -> "RoBrainsParameterSpec":
        if self.kind == "continuous":
            if self.min_value is None or self.max_value is None:
                raise ValueError(f"Continuous parameter '{self.name}' needs min_value and max_value.")
            if self.max_value <= self.min_value:
                raise ValueError(f"Continuous parameter '{self.name}' needs max_value > min_value.")
        else:
            if not self.values:
                raise ValueError(f"{self.kind.title()} parameter '{self.name}' needs values.")
        return self


class RoBrainsObjectiveSpec(BaseModel):
    name: str
    direction: Literal["maximize", "minimize"] = "maximize"


class RoBrainsSuggestionInput(BaseModel):
    parameters: list[RoBrainsParameterSpec]
    objectives: list[RoBrainsObjectiveSpec]
    observations: list[dict[str, Any]] = Field(default_factory=list)
    repo_path: str | None = None
    output_dir: str = "runs/robrains_bo"
    batch_size: int = Field(default=1, ge=1, le=1000)
    initial_points: int | None = Field(default=None, ge=0)
    total_points: int | None = Field(default=None, ge=1)
    model: str = "SingleTaskGP"
    acquisition_function: str = "UCB"
    initialisation_method: Literal["LHS", "Random"] = "LHS"
    force_categorical: bool = False
    explorative_factor: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_suggestion_input(self) -> "RoBrainsSuggestionInput":
        parameter_names = {parameter.name for parameter in self.parameters}
        if len(parameter_names) != len(self.parameters):
            raise ValueError("Parameter names must be unique.")
        objective_names = {objective.name for objective in self.objectives}
        if len(objective_names) != len(self.objectives):
            raise ValueError("Objective names must be unique.")
        if not self.objectives:
            raise ValueError("At least one objective is required.")
        return self


class _RoBrainsRuntime(NamedTuple):
    SingleBayesianOptiBackend: Any
    MLParameter: Any
    MLParameterType: Any
    LocalBackendAPI: Any | None
    pd: Any
    torch: Any


def check_robrains_availability(input_data: RoBrainsAvailabilityInput | dict[str, Any] | None = None):
    parsed = _parse_availability_input(input_data)
    repo_path = _resolve_repo_path(parsed.repo_path)
    data: dict[str, Any] = {
        "available": False,
        "repo_path": str(repo_path),
        "repo_exists": repo_path.exists(),
        "src_path": str(repo_path / "src"),
        "src_exists": (repo_path / "src").exists(),
    }
    if not data["repo_exists"]:
        data["error"] = "RoBrains repository path does not exist."
        return ok_result(data)

    _add_robrains_to_path(repo_path)
    try:
        import robrains  # noqa: F401

        data["package_importable"] = True
    except Exception as exc:
        data["package_importable"] = False
        data["error"] = f"Could not import robrains package: {exc}"
        return ok_result(data)

    runtime, runtime_error = _load_robrains_runtime(repo_path)
    data["backend_importable"] = runtime is not None
    if runtime_error:
        data["error"] = runtime_error
        return ok_result(data)

    data["available"] = True
    data["backend"] = "SingleBayesianOptiBackend"
    data["capabilities_available"] = runtime.LocalBackendAPI is not None if runtime else False
    return ok_result(data)


def list_robrains_capabilities(input_data: RoBrainsAvailabilityInput | dict[str, Any] | None = None):
    parsed = _parse_availability_input(input_data)
    repo_path = _resolve_repo_path(parsed.repo_path)
    runtime, runtime_error = _load_robrains_runtime(repo_path)
    if runtime_error or runtime is None:
        return error_result(runtime_error or "RoBrains runtime is unavailable.", {"repo_path": str(repo_path)})
    if runtime.LocalBackendAPI is None:
        return error_result("RoBrains LocalBackendAPI is unavailable.", {"repo_path": str(repo_path)})

    try:
        capabilities = runtime.LocalBackendAPI.get_capabilities()
        return ok_result({"repo_path": str(repo_path), "capabilities": capabilities})
    except Exception as exc:
        return error_result(str(exc), {"repo_path": str(repo_path)})


def suggest_robrains_experiments(input_data: RoBrainsSuggestionInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, RoBrainsSuggestionInput) else RoBrainsSuggestionInput.model_validate(input_data)
    repo_path = _resolve_repo_path(parsed.repo_path)
    runtime, runtime_error = _load_robrains_runtime(repo_path)
    if runtime_error or runtime is None:
        return error_result(runtime_error or "RoBrains runtime is unavailable.", {"repo_path": str(repo_path)})

    try:
        output_dir = Path(parsed.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        backend = runtime.SingleBayesianOptiBackend()
        _bind_standalone_backend_methods(backend)
        ml_parameters = [_build_ml_parameter(runtime, parameter) for parameter in parsed.parameters]
        objective_names = [objective.name for objective in parsed.objectives]
        objective_signs = {objective.name: -1.0 if objective.direction == "minimize" else 1.0 for objective in parsed.objectives}
        results_df = _observations_to_dataframe(runtime.pd, parsed, objective_signs)
        backend.ML_prime(
            ML_parameters=ml_parameters,
            targets=objective_names,
            save_path=str(output_dir),
            model_parameters=getattr(backend, "model_parameters", None),
            results_df=results_df if not results_df.empty else None,
        )
        for key, value in _model_settings(parsed).items():
            backend.validate_and_update(key, value)
        if not results_df.empty:
            backend.results_df = results_df
            backend.run_index = int(results_df["run_index"].max()) + 1

        payload = backend.update() if not results_df.empty else backend.first_run()
        payload_data = _payload_to_data(runtime, payload, parsed, objective_signs, ml_parameters)
        payload_data.update(
            {
                "repo_path": str(repo_path),
                "backend": "SingleBayesianOptiBackend",
                "observation_count": len(parsed.observations),
                "mode": "bayesian_update" if parsed.observations else "initial_design",
                "output_dir": str(output_dir),
            }
        )
        return ok_result(payload_data, [str(output_dir)])
    except Exception as exc:
        return error_result(str(exc), {"repo_path": str(repo_path), "observation_count": len(parsed.observations)})


def _parse_availability_input(input_data: RoBrainsAvailabilityInput | dict[str, Any] | None) -> RoBrainsAvailabilityInput:
    if input_data is None:
        return RoBrainsAvailabilityInput()
    return input_data if isinstance(input_data, RoBrainsAvailabilityInput) else RoBrainsAvailabilityInput.model_validate(input_data)


def _resolve_repo_path(repo_path: str | None) -> Path:
    configured = repo_path or os.getenv("ROBRAINS_REPO_PATH") or DEFAULT_ROBRAINS_REPO_PATH
    return Path(configured).expanduser()


def _add_robrains_to_path(repo_path: Path) -> None:
    for candidate in (repo_path / "src", repo_path):
        candidate_str = str(candidate)
        if candidate.exists() and candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)


def _load_robrains_runtime(repo_path: Path) -> tuple[_RoBrainsRuntime | None, str | None]:
    if not repo_path.exists():
        return None, f"RoBrains repository path does not exist: {repo_path}"
    _add_robrains_to_path(repo_path)
    try:
        import pandas as pd
        import torch
        from robrains.application.use_cases import SingleBayesianOptiBackend
        from robrains.domain.parameters import MLParameter, MLParameterType
        from robrains.domain.core.logger import Logger

        Logger._console_enabled = False
        Logger._web_stream = False
    except Exception as exc:
        return None, f"Could not import RoBrains Bayesian optimization runtime: {exc}"

    try:
        from robrains.interfaces.api import LocalBackendAPI
    except Exception:
        LocalBackendAPI = None

    return (
        _RoBrainsRuntime(
            SingleBayesianOptiBackend=SingleBayesianOptiBackend,
            MLParameter=MLParameter,
            MLParameterType=MLParameterType,
            LocalBackendAPI=LocalBackendAPI,
            pd=pd,
            torch=torch,
        ),
        None,
    )


def _bind_standalone_backend_methods(backend: Any) -> None:
    def extract_tensor_from_result_df(self: Any, run_index: int | str, override_df: Any = None):
        df = self.results_df if override_df is None else override_df
        row_df = df[df["run_index"] == int(run_index)]
        if row_df.empty:
            raise ValueError(f"No row found with run_index {run_index}.")
        return self.tensor_from_row(row_df.iloc[0])

    object.__setattr__(backend, "extract_tensor_from_result_df", MethodType(extract_tensor_from_result_df, backend))


def _model_settings(parsed: RoBrainsSuggestionInput) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "Model": parsed.model,
        "Acquisition Function": parsed.acquisition_function,
        "Initialisation Method": parsed.initialisation_method,
        "Number of Experiments per batch": parsed.batch_size,
        "force_categorical": parsed.force_categorical,
    }
    if parsed.initial_points is not None:
        settings["Number of initial points"] = parsed.initial_points
    else:
        settings["Number of initial points"] = max(parsed.batch_size, 2 * len(parsed.parameters))
    if parsed.total_points is not None:
        settings["Number of total points"] = parsed.total_points
    elif parsed.observations:
        settings["Number of total points"] = len(parsed.observations) + parsed.batch_size
    if parsed.explorative_factor is not None:
        settings["Explorative Factor"] = parsed.explorative_factor
    return settings


def _build_ml_parameter(runtime: _RoBrainsRuntime, spec: RoBrainsParameterSpec):
    if spec.kind == "continuous":
        return runtime.MLParameter(
            spec.name,
            mode=runtime.MLParameterType.CONT,
            unit=spec.unit,
            min_value=spec.min_value,
            max_value=spec.max_value,
        )
    if spec.kind == "categorical":
        return runtime.MLParameter(
            spec.name,
            mode=runtime.MLParameterType.CAT,
            unit=spec.unit,
            discrete=list(spec.values),
        )
    return runtime.MLParameter(
        spec.name,
        mode=runtime.MLParameterType.DISC,
        unit=spec.unit,
        discrete=list(spec.values),
    )


def _observations_to_dataframe(pd: Any, parsed: RoBrainsSuggestionInput, objective_signs: dict[str, float]):
    if not parsed.observations:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    parameter_names = [parameter.name for parameter in parsed.parameters]
    objective_names = [objective.name for objective in parsed.objectives]
    for index, observation in enumerate(parsed.observations):
        missing_parameters = [name for name in parameter_names if name not in observation]
        missing_objectives = [name for name in objective_names if name not in observation]
        if missing_parameters or missing_objectives:
            raise ValueError(
                f"Observation {index} is missing parameters={missing_parameters} objectives={missing_objectives}."
            )
        row = dict(observation)
        row.setdefault("run_index", index)
        row["status"] = "finished"
        for objective_name, sign in objective_signs.items():
            row[objective_name] = sign * float(row[objective_name])
        rows.append(row)
    return pd.DataFrame(rows)


def _payload_to_data(
    runtime: _RoBrainsRuntime,
    payload: Any,
    parsed: RoBrainsSuggestionInput,
    objective_signs: dict[str, float],
    ml_parameters: list[Any] | None = None,
) -> dict[str, Any]:
    if isinstance(payload, str):
        return {"status": payload, "suggestions": [], "predicted_objectives": []}

    next_points = getattr(payload, "next_points", payload)
    tensors = _coerce_tensor_list(runtime.torch, next_points)
    suggestions = [_decode_suggestion(tensor, parsed.parameters, ml_parameters) for tensor in tensors]
    predicted = _decode_predictions(runtime.torch, getattr(payload, "predicted_y", None), parsed.objectives, objective_signs)
    return {
        "status": "suggested",
        "suggestions": suggestions,
        "encoded_suggestions": [_tensor_to_list(tensor) for tensor in tensors],
        "predicted_objectives": predicted,
        "batch_size": len(suggestions),
        "meta": getattr(payload, "meta", {}) or {},
    }


def _coerce_tensor_list(torch: Any, value: Any) -> list[Any]:
    if isinstance(value, list):
        return [torch.as_tensor(item, dtype=torch.float64).flatten() for item in value]
    tensor = torch.as_tensor(value, dtype=torch.float64)
    if tensor.ndim <= 1:
        return [tensor.flatten()]
    return [row.flatten() for row in tensor.reshape(-1, tensor.shape[-1])]


def _decode_suggestion(
    tensor: Any,
    parameters: list[RoBrainsParameterSpec],
    ml_parameters: list[Any] | None = None,
) -> dict[str, Any]:
    if ml_parameters and all(hasattr(parameter, "tensor_columns") for parameter in ml_parameters):
        decoded = _decode_with_robrains_translators(tensor, parameters, ml_parameters)
        if decoded is not None:
            return decoded

    values = _tensor_to_list(tensor)
    suggestion: dict[str, Any] = {}
    cursor = 0
    for parameter in parameters:
        if cursor >= len(values):
            break
        raw_value = values[cursor]
        if parameter.kind == "continuous":
            min_value = float(parameter.min_value) if parameter.min_value is not None else 0.0
            max_value = float(parameter.max_value) if parameter.max_value is not None else 1.0
            value = min_value + raw_value * (max_value - min_value)
            suggestion[parameter.name] = value
            cursor += 1
            continue
        index = int(round(raw_value))
        index = max(0, min(index, len(parameter.values) - 1))
        suggestion[parameter.name] = parameter.values[index]
        cursor += 1
    return suggestion


def _decode_with_robrains_translators(
    tensor: Any,
    specs: list[RoBrainsParameterSpec],
    ml_parameters: list[Any],
) -> dict[str, Any] | None:
    suggestion: dict[str, Any] = {}
    cursor = 0
    try:
        for spec, ml_parameter in zip(specs, ml_parameters, strict=True):
            for column_spec in ml_parameter.tensor_columns():
                width = int(column_spec.width)
                if column_spec.kind in {"continuous", "fidelity", "task"}:
                    raw_value = tensor[cursor].item() if hasattr(tensor[cursor], "item") else tensor[cursor]
                    if hasattr(ml_parameter, "back_translation_continuous") and column_spec.kind == "continuous":
                        suggestion[spec.name] = ml_parameter.back_translation_continuous(raw_value)
                    else:
                        suggestion[spec.name] = raw_value
                elif column_spec.kind == "categorical":
                    vector = tensor[cursor : cursor + width]
                    if hasattr(ml_parameter, "back_translation_discrete"):
                        suggestion[spec.name] = ml_parameter.back_translation_discrete(vector)
                    else:
                        return None
                cursor += width
        return suggestion
    except Exception:
        return None


def _decode_predictions(
    torch: Any,
    predicted_y: Any,
    objectives: list[RoBrainsObjectiveSpec],
    objective_signs: dict[str, float],
) -> list[dict[str, Any]]:
    if predicted_y is None:
        return []
    if isinstance(predicted_y, tuple) and len(predicted_y) == 2:
        means_tensor = torch.as_tensor(predicted_y[0], dtype=torch.float64)
        variances_tensor = torch.as_tensor(predicted_y[1], dtype=torch.float64)
    else:
        means_tensor = torch.as_tensor(predicted_y, dtype=torch.float64)
        variances_tensor = None
    means = means_tensor.reshape(-1, len(objectives)).tolist()
    variances = variances_tensor.reshape(-1, len(objectives)).tolist() if variances_tensor is not None else None

    rows: list[dict[str, Any]] = []
    for row_index, mean_row in enumerate(means):
        row: dict[str, Any] = {}
        for objective_index, objective in enumerate(objectives):
            sign = objective_signs[objective.name]
            row[objective.name] = sign * float(mean_row[objective_index])
            if variances is not None:
                row[f"{objective.name}_variance"] = float(variances[row_index][objective_index])
        rows.append(row)
    return rows


def _tensor_to_list(tensor: Any) -> list[float]:
    if hasattr(tensor, "detach"):
        tensor = tensor.detach().cpu()
    if hasattr(tensor, "tolist"):
        value = tensor.tolist()
    else:
        value = list(tensor)
    if value and isinstance(value[0], list):
        return [float(item) for row in value for item in row]
    return [float(item) for item in value]
