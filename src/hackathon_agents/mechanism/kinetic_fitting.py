from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from hackathon_agents.mechanism.mechanism_classes import MechanismClass
from hackathon_agents.mechanism.schemas import FitResult, KineticDataset, KineticExperiment, MechanismHypothesis


def fit_all_hypotheses(hypotheses: Sequence[MechanismHypothesis], dataset: KineticDataset) -> list[FitResult]:
    """Fit every hypothesis to one kinetic dataset with simple rate-law models."""

    return [fit_hypothesis_to_dataset(hypothesis, dataset) for hypothesis in hypotheses]


def fit_hypothesis_to_dataset(hypothesis: MechanismHypothesis, dataset: KineticDataset) -> FitResult:
    """Fit a toy ODE/rate-law model to product concentration data.

    The first implementation deliberately starts with SciPy least_squares and
    compact models.  JAX/PyTorch backends can replace this function later
    without changing the graph or state contracts.
    """

    try:
        from scipy.optimize import least_squares
    except Exception as exc:
        return FitResult(
            hypothesis_id=hypothesis.id,
            experiment_id=dataset.experiment_id,
            ok=False,
            model_name="least_squares_unavailable",
            error=f"scipy least_squares unavailable: {exc}",
        )

    times = np.asarray(dataset.time_points, dtype=float)
    product = np.asarray(_select_product_profile(dataset), dtype=float)
    if times.size < 3 or product.size != times.size:
        return FitResult(
            hypothesis_id=hypothesis.id,
            experiment_id=dataset.experiment_id,
            ok=False,
            model_name="invalid_dataset",
            error="dataset must contain at least three aligned time/product points",
        )

    model_name, param_names, lower, upper, initial = _model_spec(hypothesis.mechanism_class, times, product)

    def residuals(params: np.ndarray) -> np.ndarray:
        return _predict_product(times, params, model_name) - product

    try:
        result = least_squares(residuals, x0=initial, bounds=(lower, upper), max_nfev=5000)
        residual = residuals(result.x)
        sse = float(np.sum(residual**2))
        n_obs = int(product.size)
        n_params = int(len(result.x))
        rmse = math.sqrt(sse / max(1, n_obs))
        aic = _information_criterion(sse=sse, n_obs=n_obs, n_params=n_params, kind="aic")
        bic = _information_criterion(sse=sse, n_obs=n_obs, n_params=n_params, kind="bic")
        uncertainty = _parameter_uncertainty(result.jac, residual, param_names)
        confidence_update = max(-0.5, min(0.5, 0.25 - rmse))
        return FitResult(
            hypothesis_id=hypothesis.id,
            experiment_id=dataset.experiment_id,
            ok=bool(result.success),
            model_name=model_name,
            parameters={name: float(value) for name, value in zip(param_names, result.x)},
            parameter_uncertainty=uncertainty,
            residual_norm=float(np.linalg.norm(residual)),
            rmse=float(rmse),
            aic=float(aic),
            bic=float(bic),
            confidence_update=float(confidence_update),
            diagnostics={
                "success": bool(result.success),
                "message": str(result.message),
                "nfev": int(result.nfev),
            },
            error=None if result.success else str(result.message),
        )
    except Exception as exc:
        return FitResult(
            hypothesis_id=hypothesis.id,
            experiment_id=dataset.experiment_id,
            ok=False,
            model_name=model_name,
            error=str(exc),
        )


def simulate_kinetic_dataset(
    experiment: KineticExperiment,
    *,
    mechanism_class: MechanismClass = MechanismClass.PHOTOREDOX_CATALYTIC_CYCLE,
    noise_level: float = 0.005,
    seed: int = 7,
) -> KineticDataset:
    """Generate deterministic synthetic kinetic traces for mock robot runs."""

    variables = experiment.variables
    n_points = max(8, min(24, int(variables.residence_time) + 6))
    times = np.linspace(0.0, float(variables.residence_time), n_points)
    concentration_a0 = float(variables.concentrations.get("A", 1.0))
    concentration_b0 = float(variables.concentrations.get("B", 1.0))
    limiting = max(1e-6, min(concentration_a0, concentration_b0))
    light_factor = 1.0 + 0.4 * min(2.0, variables.light_intensity)
    catalyst_factor = 1.0 + 2.0 * min(0.2, variables.catalyst_loading)
    temperature_factor = max(0.25, math.exp((variables.temperature - 298.15) / 80.0))
    class_factor = {
        MechanismClass.RADICAL_CHAIN: 1.25,
        MechanismClass.PHOTOREDOX_CATALYTIC_CYCLE: 1.1,
        MechanismClass.CATALYST_DEACTIVATION: 0.85,
        MechanismClass.PRODUCT_INHIBITION: 0.75,
        MechanismClass.MASS_TRANSFER_LIMITED_APPARENT_KINETICS: 0.65,
    }.get(mechanism_class, 1.0)
    k = 0.18 * light_factor * catalyst_factor * temperature_factor * class_factor
    product = limiting * _predict_product(times, np.asarray([k, 0.92]), "first_order")
    if mechanism_class == MechanismClass.CATALYST_DEACTIVATION:
        product = limiting * _predict_product(times, np.asarray([k, 0.9, 0.035]), "deactivation")
    elif mechanism_class == MechanismClass.PRODUCT_INHIBITION:
        product = limiting * _predict_product(times, np.asarray([k, 0.88, 0.35]), "product_inhibition")
    elif mechanism_class == MechanismClass.MASS_TRANSFER_LIMITED_APPARENT_KINETICS:
        product = limiting * _predict_product(times, np.asarray([k, 0.86]), "mass_transfer")

    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, noise_level, size=times.size)
    product = np.clip(product + noise, 0.0, limiting)
    profile_a = np.clip(concentration_a0 - product, 0.0, None)
    profile_b = np.clip(concentration_b0 - product, 0.0, None)
    return KineticDataset(
        experiment_id=experiment.id,
        time_points=[float(value) for value in times],
        concentration_profiles={
            "A": [float(value) for value in profile_a],
            "B": [float(value) for value in profile_b],
            "P": [float(value) for value in product],
        },
        metadata={
            "synthetic": True,
            "hidden_mechanism_class": mechanism_class.value,
            "noise_level": noise_level,
        },
        parsed_ok=True,
        quality_flags=[],
    )


def _select_product_profile(dataset: KineticDataset) -> list[float]:
    for candidate in ("P", "product", "Product"):
        if candidate in dataset.concentration_profiles:
            return dataset.concentration_profiles[candidate]
    first_species = next(iter(dataset.concentration_profiles))
    return dataset.concentration_profiles[first_species]


def _model_spec(
    mechanism_class: MechanismClass | str,
    times: np.ndarray,
    product: np.ndarray,
) -> tuple[str, list[str], np.ndarray, np.ndarray, np.ndarray]:
    upper_product = max(1.0, float(np.nanmax(product)) * 2.0 + 0.1)
    base_k = max(1e-3, 1.0 / max(1.0, float(np.nanmax(times))))
    mechanism = MechanismClass(mechanism_class)
    if mechanism == MechanismClass.CATALYST_DEACTIVATION:
        return (
            "deactivation",
            ["k", "p_inf", "k_deactivation"],
            np.asarray([1e-6, 0.0, 0.0]),
            np.asarray([10.0, upper_product, 1.0]),
            np.asarray([base_k, min(upper_product, max(0.2, float(np.nanmax(product)))), 0.02]),
        )
    if mechanism == MechanismClass.PRODUCT_INHIBITION:
        return (
            "product_inhibition",
            ["k", "p_inf", "k_inhibition"],
            np.asarray([1e-6, 0.0, 0.0]),
            np.asarray([10.0, upper_product, 10.0]),
            np.asarray([base_k, min(upper_product, max(0.2, float(np.nanmax(product)))), 0.1]),
        )
    if mechanism == MechanismClass.MASS_TRANSFER_LIMITED_APPARENT_KINETICS:
        return (
            "mass_transfer",
            ["k_transfer", "p_inf"],
            np.asarray([1e-6, 0.0]),
            np.asarray([10.0, upper_product]),
            np.asarray([base_k, min(upper_product, max(0.2, float(np.nanmax(product))))]),
        )
    return (
        "first_order",
        ["k", "p_inf"],
        np.asarray([1e-6, 0.0]),
        np.asarray([10.0, upper_product]),
        np.asarray([base_k, min(upper_product, max(0.2, float(np.nanmax(product))))]),
    )


def _predict_product(times: np.ndarray, params: np.ndarray, model_name: str) -> np.ndarray:
    times = np.maximum(times, 0.0)
    if model_name == "deactivation":
        k, p_inf, k_deactivation = params
        active_fraction = np.exp(-k_deactivation * times)
        return p_inf * (1.0 - np.exp(-k * times)) * active_fraction
    if model_name == "product_inhibition":
        k, p_inf, k_inhibition = params
        slowed_time = times / (1.0 + k_inhibition * np.maximum(times, 0.0))
        return p_inf * (1.0 - np.exp(-k * slowed_time))
    if model_name == "mass_transfer":
        k_transfer, p_inf = params
        return p_inf * (1.0 - np.exp(-k_transfer * np.sqrt(times + 1e-12)))
    k, p_inf = params
    return p_inf * (1.0 - np.exp(-k * times))


def _information_criterion(*, sse: float, n_obs: int, n_params: int, kind: str) -> float:
    safe_sse = max(sse, 1e-12)
    base = n_obs * math.log(safe_sse / max(1, n_obs))
    if kind == "bic":
        return base + n_params * math.log(max(1, n_obs))
    return base + 2 * n_params


def _parameter_uncertainty(jacobian: np.ndarray, residual: np.ndarray, param_names: Sequence[str]) -> dict[str, float]:
    dof = max(1, residual.size - len(param_names))
    try:
        variance = float(np.sum(residual**2) / dof)
        covariance = np.linalg.pinv(jacobian.T @ jacobian) * variance
        stderr = np.sqrt(np.maximum(np.diag(covariance), 0.0))
        return {name: float(value) for name, value in zip(param_names, stderr)}
    except Exception:
        return {name: float("nan") for name in param_names}
