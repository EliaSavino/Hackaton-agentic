"""BayBE Bayesian Design-of-Experiments tool.

This wraps `emdgroup/baybe <https://github.com/emdgroup/baybe>`_ (the **Bay**esian
**B**ack **E**nd), Merck KGaA's open-source toolbox for Bayesian optimization /
Design of Experiments (DoE). It lets an agent (or a chemist) ask the question
that BayBE is built to answer:

    "Given the experimental knobs I can turn, the property I want to optimize,
     and the experiments I have already run, **which experiments should I run
     next?**"

Unlike Saturn (which *invents* new molecules), BayBE *selects the most
informative configurations* from a search space you define -- reaction
conditions, formulation ratios, process parameters, or which compound from a
fixed library to test next. It is designed for the low-/no-data regime, so it is
useful from the very first experiment.

Design philosophy (mirrors the xTB / ORCA / Saturn / Boltz wrappers):

1. A small, typed, chemist-readable schema describes the **search space**
   (``parameters``), the **objective** (``targets``), and any **measurements**
   collected so far.
2. When BayBE is installed, the tool builds a real ``Campaign``, ingests the
   measurements, and asks BayBE to ``recommend`` the next batch of experiments
   using its Bayesian (Gaussian-process / BoTorch) recommender.
3. When BayBE is **not** installed, or when ``run=False`` (the default), the
   tool returns a deterministic, space-filling **mock** recommendation set, so
   the pipeline stays offline-safe and demo-ready -- exactly like the other
   heavy tools.

The tool is intentionally *stateless*: each call rebuilds the campaign from the
parameters, targets, and the full ``measurements`` history that the caller
passes in. This fits the JSON-serializable state model used by the rest of the
workbench -- the agent simply keeps appending measured rows and asking for the
next batch.

Every code path returns a ``ToolResult``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hackathon_agents.tools.base import error_result, ok_result
from hackathon_agents.tools.file_io import write_csv


# --------------------------------------------------------------------------- #
# Typed, chemist-readable schema
# --------------------------------------------------------------------------- #
class BayBEParameter(BaseModel):
    """A single experimental "knob" (a controllable input variable).

    Examples
    --------
    Continuous temperature between 25 and 80 degrees::

        {"name": "Temperature_C", "type": "numerical_continuous", "bounds": [25, 80]}

    A handful of discrete pressures::

        {"name": "Pressure_bar", "type": "numerical_discrete", "values": [1, 5, 10]}

    A categorical choice of base::

        {"name": "Base", "type": "categorical", "values": ["NaOH", "KOtBu", "Et3N"]}

    A solvent chosen from a library, encoded by chemical structure so BayBE can
    reason about chemical similarity::

        {"name": "Solvent", "type": "substance",
         "data": {"DMSO": "CS(=O)C", "Water": "O", "Methanol": "CO"},
         "encoding": "MORDRED"}
    """

    name: str = Field(description="Human-readable column name, e.g. 'Temperature_C'.")
    type: Literal[
        "numerical_continuous",
        "numerical_discrete",
        "categorical",
        "substance",
    ] = Field(description="The kind of knob this is.")

    # Discrete numeric or categorical knobs enumerate their allowed values.
    values: list[Any] = Field(
        default_factory=list,
        description="Allowed values for 'numerical_discrete' or 'categorical' parameters.",
    )
    # Continuous knobs are bounded by a [low, high] interval.
    bounds: tuple[float, float] | None = Field(
        default=None,
        description="[low, high] interval for 'numerical_continuous' parameters.",
    )
    # Substance knobs map a friendly label to a SMILES string.
    data: dict[str, str] = Field(
        default_factory=dict,
        description="label -> SMILES mapping for 'substance' parameters.",
    )
    # Optional encoding hint (e.g. 'OHE' for categorical, 'MORDRED'/'ECFP' for substance).
    encoding: str | None = Field(
        default=None,
        description="Optional encoding (categorical: 'OHE'/'INT'; substance: 'MORDRED'/'ECFP'/...).",
    )
    tolerance: float | None = Field(
        default=None,
        description="Optional read tolerance for discrete numeric values.",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_shape(self) -> "BayBEParameter":
        if self.type in ("numerical_discrete", "categorical") and not self.values:
            raise ValueError(f"Parameter {self.name!r} of type {self.type!r} requires non-empty 'values'.")
        if self.type == "numerical_continuous" and self.bounds is None:
            raise ValueError(f"Parameter {self.name!r} of type 'numerical_continuous' requires 'bounds'.")
        if self.type == "substance" and not self.data:
            raise ValueError(f"Parameter {self.name!r} of type 'substance' requires a 'data' label->SMILES mapping.")
        return self

    def options(self) -> list[Any]:
        """Return a small, representative set of values for mock space-filling."""

        if self.type == "numerical_continuous" and self.bounds is not None:
            low, high = float(self.bounds[0]), float(self.bounds[1])
            mid = round((low + high) / 2.0, 6)
            # Deduplicate in case of a degenerate interval.
            return list(dict.fromkeys([low, mid, high]))
        if self.type == "substance":
            return list(self.data.keys())
        return list(self.values)


class BayBETarget(BaseModel):
    """The property to optimize (the experiment's measured outcome).

    ``mode`` is the optimization direction:

    - ``"MAX"`` -- maximize (e.g. yield, binding affinity, selectivity).
    - ``"MIN"`` -- minimize (e.g. cost, impurity, reaction time).
    - ``"MATCH"`` -- hit a specific ``match_value`` (e.g. a target pH or melting point).
    """

    name: str = Field(description="Name of the measured outcome, e.g. 'Yield'.")
    mode: Literal["MAX", "MIN", "MATCH"] = "MAX"
    bounds: tuple[float, float] | None = Field(
        default=None,
        description="Optional [low, high] range of plausible target values.",
    )
    match_value: float | None = Field(
        default=None,
        description="Target set-point value, required when mode='MATCH'.",
    )
    weight: float = Field(default=1.0, gt=0.0, description="Relative importance when optimizing multiple targets.")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_match(self) -> "BayBETarget":
        if self.mode == "MATCH" and self.match_value is None:
            raise ValueError(f"Target {self.name!r} with mode='MATCH' requires a 'match_value'.")
        return self


class BayBERecommendInput(BaseModel):
    """Inputs for one BayBE recommendation step.

    The caller provides the search space (``parameters``), what to optimize
    (``targets``), and every measurement collected so far (``measurements``).
    The tool returns the next ``batch_size`` experiments to run.
    """

    objective: str = "Recommend the next most informative experiments."
    parameters: list[BayBEParameter] = Field(description="The experimental knobs to tune.")
    targets: list[BayBETarget] = Field(
        default_factory=lambda: [BayBETarget(name="Target", mode="MAX")],
        description="One or more measured outcomes to optimize.",
    )
    measurements: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Experiments already run. Each row maps parameter names AND target "
            "names to their values, e.g. {'Temperature_C': 60, 'Yield': 78.5}."
        ),
    )
    batch_size: int = Field(default=3, ge=1, le=100, description="How many experiments to recommend next.")

    # --- Execution / environment -------------------------------------------
    work_dir: str | None = Field(
        default=None,
        description="Optional directory; recommendations are written there as recommendations.csv.",
    )
    run: bool = Field(
        default=False,
        description="Opt-in real BayBE optimization. False => deterministic mock recommendations.",
    )
    recommend_filename: str = "baybe_recommendations.csv"
    seed: int = 0

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_unique_names(self) -> "BayBERecommendInput":
        if not self.parameters:
            raise ValueError("At least one parameter is required to define a search space.")
        param_names = [p.name for p in self.parameters]
        target_names = [t.name for t in self.targets]
        if len(set(param_names)) != len(param_names):
            raise ValueError("Parameter names must be unique.")
        if len(set(target_names)) != len(target_names):
            raise ValueError("Target names must be unique.")
        overlap = set(param_names) & set(target_names)
        if overlap:
            raise ValueError(f"Parameter and target names must not overlap: {sorted(overlap)}.")
        # Multiple targets are combined into a desirability score, which requires
        # each target to be normalized onto a common scale. For MAX/MIN targets
        # that means we need a plausible value range (`bounds`) to normalize by.
        if len(self.targets) > 1:
            missing = [t.name for t in self.targets if t.mode in ("MAX", "MIN") and t.bounds is None]
            if missing:
                raise ValueError(
                    "When optimizing multiple targets, each MAX/MIN target needs 'bounds' "
                    f"so it can be normalized for the desirability score. Missing bounds for: {missing}."
                )
        return self


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #
def check_baybe_availability():
    """Report whether the optional ``baybe`` package can be imported in-process.

    Unlike Saturn/Boltz, BayBE is a normal pip package, so availability simply
    means "is it importable". When unavailable, recommendation falls back to the
    deterministic mock recommender.
    """

    available = False
    version: str | None = None
    try:
        import baybe  # type: ignore

        available = True
        version = getattr(baybe, "__version__", None)
    except Exception:
        available = False

    # Chemical encodings (SubstanceParameter) need the optional [chem] extra,
    # which provides the scikit-fingerprints package.
    chem_available = _module_importable("skfp") or _module_importable("scikit_fingerprints")
    return ok_result(
        {
            "available": available,
            "version": version,
            "chem_encoding_available": chem_available,
        }
    )


def _module_importable(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def recommend_experiments(input_data: BayBERecommendInput | dict[str, Any]):
    """Recommend the next batch of experiments via Bayesian DoE.

    Returns a ``ToolResult`` whose ``data`` contains:

    - ``recommendations``: list of rows (parameter name -> value) to run next.
    - ``batch_size``, ``parameter_names``, ``target_names``, ``objective_kind``.
    - ``n_prior_measurements``: how many measured rows informed the suggestion.
    - ``mock``: ``True`` when the deterministic fallback produced the result.
    - ``recommender``: the recommender used (BayBE class name or mock label).
    """

    parsed = _coerce(input_data)
    try:
        config_path: Path | None = None
        if parsed.work_dir:
            work_dir = Path(parsed.work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
            config_path = work_dir / parsed.recommend_filename

        if not parsed.run:
            return _mock_result(parsed, config_path, reason="run=False")

        availability = check_baybe_availability()
        if not availability.data["available"]:
            result = _mock_result(parsed, config_path, reason="baybe_not_installed")
            result.metadata["baybe_availability"] = availability.data
            return result

        return _real_result(parsed, config_path, availability.data)
    except Exception as exc:  # pragma: no cover - defensive guard
        return error_result(str(exc), {"objective": parsed.objective})


# --------------------------------------------------------------------------- #
# Real BayBE path
# --------------------------------------------------------------------------- #
def build_search_space(parameters: list[BayBEParameter]):
    """Build a BayBE ``SearchSpace`` from typed parameters. Requires ``baybe``."""

    from baybe.searchspace import SearchSpace

    return SearchSpace.from_product([_build_parameter(p) for p in parameters])


def build_objective(targets: list[BayBETarget]):
    """Build a BayBE objective (single-target or desirability). Requires ``baybe``."""

    from baybe.objectives import DesirabilityObjective, SingleTargetObjective

    if len(targets) == 1:
        return SingleTargetObjective(target=_build_target(targets[0], normalize=False))
    # Multiple targets are scalarized into a desirability score, which requires
    # each target to be normalized onto a common [0, 1] scale.
    baybe_targets = [_build_target(t, normalize=True) for t in targets]
    weights = [t.weight for t in targets]
    return DesirabilityObjective(targets=baybe_targets, weights=weights)


def _real_result(parsed: BayBERecommendInput, config_path: Path | None, availability: dict[str, Any]):
    import pandas as pd
    from baybe import Campaign

    searchspace = build_search_space(parsed.parameters)
    objective = build_objective(parsed.targets)
    campaign = Campaign(searchspace, objective)

    if parsed.measurements:
        measurements_df = pd.DataFrame(parsed.measurements)
        campaign.add_measurements(measurements_df)

    recommendation_df = campaign.recommend(batch_size=parsed.batch_size)
    recommendations = recommendation_df.to_dict(orient="records")

    artifacts = _write_recommendations(config_path, recommendations)
    result = ok_result(
        {
            "recommendations": recommendations,
            "batch_size": parsed.batch_size,
            "parameter_names": [p.name for p in parsed.parameters],
            "target_names": [t.name for t in parsed.targets],
            "objective_kind": "single_target" if len(parsed.targets) == 1 else "desirability",
            "n_prior_measurements": len(parsed.measurements),
            "mock": False,
            "recommender": type(campaign.recommender).__name__,
        },
        artifacts=artifacts,
    )
    result.metadata["baybe_version"] = availability.get("version")
    return result


def _build_parameter(spec: BayBEParameter):
    from baybe.parameters import (
        CategoricalParameter,
        NumericalContinuousParameter,
        NumericalDiscreteParameter,
        SubstanceParameter,
    )

    if spec.type == "numerical_discrete":
        kwargs: dict[str, Any] = {"name": spec.name, "values": list(spec.values)}
        if spec.tolerance is not None:
            kwargs["tolerance"] = spec.tolerance
        return NumericalDiscreteParameter(**kwargs)
    if spec.type == "numerical_continuous":
        assert spec.bounds is not None  # guaranteed by validator
        return NumericalContinuousParameter(name=spec.name, bounds=tuple(spec.bounds))
    if spec.type == "categorical":
        return CategoricalParameter(
            name=spec.name,
            values=[str(v) for v in spec.values],
            encoding=spec.encoding or "OHE",
        )
    # substance
    return SubstanceParameter(
        name=spec.name,
        data=dict(spec.data),
        encoding=spec.encoding or "MORDRED",
    )


def _build_target(spec: BayBETarget, *, normalize: bool):
    """Create a ``NumericalTarget`` robustly across BayBE versions.

    BayBE reworked the target interface in v0.14 (direction is now expressed via
    a ``minimize`` flag instead of a ``mode`` argument). This helper tries the
    modern interface first and falls back to the legacy one, so the wrapper works
    with whichever BayBE version is installed.

    When ``normalize`` is ``True`` (multi-target desirability), MAX/MIN targets
    are mapped onto a normalized [0, 1] ramp using their ``bounds`` so they can
    be combined into a single desirability score.
    """

    from baybe.targets import NumericalTarget

    if spec.mode == "MATCH" and spec.match_value is not None:
        # Set-point matching. Bell/triangular constructors are inherently
        # normalized, which also satisfies the desirability requirement.
        for constructor in ("match_bell", "match_triangular"):
            factory = getattr(NumericalTarget, constructor, None)
            if factory is not None:
                try:
                    return factory(name=spec.name, match_value=spec.match_value)
                except Exception:
                    continue
        # Legacy MATCH mode.
        try:
            return NumericalTarget(name=spec.name, mode="MATCH", bounds=spec.bounds)
        except Exception:
            return NumericalTarget(name=spec.name)

    minimize = spec.mode == "MIN"

    if normalize and spec.bounds is not None:
        # Normalized ramp keeps the optimization direction while mapping the
        # plausible value range onto [0, 1] (validator guarantees bounds here).
        ramp = getattr(NumericalTarget, "normalized_ramp", None)
        if ramp is not None:
            try:
                return ramp(name=spec.name, cutoffs=tuple(spec.bounds), descending=minimize)
            except Exception:
                pass

    # Modern interface (>= 0.14): direction via `minimize`.
    try:
        return NumericalTarget(name=spec.name, minimize=minimize)
    except TypeError:
        pass
    # Legacy interface (< 0.14): explicit `mode` (+ optional bounds).
    legacy_kwargs: dict[str, Any] = {"name": spec.name, "mode": spec.mode}
    if spec.bounds is not None:
        legacy_kwargs["bounds"] = tuple(spec.bounds)
    return NumericalTarget(**legacy_kwargs)


# --------------------------------------------------------------------------- #
# Deterministic mock path (offline-safe fallback)
# --------------------------------------------------------------------------- #
def _mock_result(parsed: BayBERecommendInput, config_path: Path | None, *, reason: str):
    recommendations = _mock_recommendations(parsed)
    artifacts = _write_recommendations(config_path, recommendations)
    result = ok_result(
        {
            "recommendations": recommendations,
            "batch_size": parsed.batch_size,
            "parameter_names": [p.name for p in parsed.parameters],
            "target_names": [t.name for t in parsed.targets],
            "objective_kind": "single_target" if len(parsed.targets) == 1 else "desirability",
            "n_prior_measurements": len(parsed.measurements),
            "mock": True,
            "recommender": "mock_space_filling",
        },
        artifacts=artifacts,
    )
    result.metadata["mock_reason"] = reason
    return result


def _mock_recommendations(parsed: BayBERecommendInput) -> list[dict[str, Any]]:
    """Deterministic, space-filling recommendations covering the search grid.

    Uses mixed-radix counting over each parameter's representative options so
    that successive recommendations vary across the whole space rather than
    changing only one parameter. Already-measured configurations are skipped
    when possible. This is not Bayesian, but it is a sensible, reproducible
    stand-in that keeps the pipeline runnable without BayBE installed.
    """

    option_lists = [(p.name, p.options()) for p in parsed.parameters]
    radices = [max(1, len(options)) for _, options in option_lists]
    total_combinations = 1
    for radix in radices:
        total_combinations *= radix

    measured_keys = {_combo_key(_project_to_params(row, parsed)) for row in parsed.measurements}

    recommendations: list[dict[str, Any]] = []
    seen: set[tuple] = set(measured_keys)
    index = 0
    max_attempts = total_combinations + parsed.batch_size
    while len(recommendations) < parsed.batch_size and index < max_attempts:
        combo: dict[str, Any] = {}
        divisor = 1
        for (name, options), radix in zip(option_lists, radices):
            choice = options[(index // divisor) % radix] if options else None
            combo[name] = choice
            divisor *= radix
        key = _combo_key(combo)
        if key not in seen:
            recommendations.append(combo)
            seen.add(key)
        index += 1

    # Tiny space already fully explored: allow repeats so batch_size is honored.
    if not recommendations:
        divisor = 1
        fallback: dict[str, Any] = {}
        for (name, options), radix in zip(option_lists, radices):
            fallback[name] = options[0] if options else None
            divisor *= radix
        recommendations.append(fallback)
    while len(recommendations) < parsed.batch_size:
        recommendations.append(dict(recommendations[len(recommendations) % len(recommendations)]))

    return recommendations[: parsed.batch_size]


def _project_to_params(row: dict[str, Any], parsed: BayBERecommendInput) -> dict[str, Any]:
    return {p.name: row.get(p.name) for p in parsed.parameters}


def _combo_key(combo: dict[str, Any]) -> tuple:
    return tuple(sorted((name, _normalize_value(value)) for name, value in combo.items()))


def _normalize_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _coerce(input_data: BayBERecommendInput | dict[str, Any]) -> BayBERecommendInput:
    return (
        input_data
        if isinstance(input_data, BayBERecommendInput)
        else BayBERecommendInput.model_validate(input_data)
    )


def _write_recommendations(config_path: Path | None, recommendations: list[dict[str, Any]]) -> list[str]:
    if config_path is None or not recommendations:
        return []
    fieldnames = list(recommendations[0].keys())
    result = write_csv(config_path, recommendations, fieldnames=fieldnames)
    return [str(config_path)] if result.ok else []
