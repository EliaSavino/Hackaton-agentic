from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from typing import Sequence

from hackathon_agents.mechanism.schemas import (
    CriticAssessment,
    FitResult,
    KineticExperiment,
    MechanismHypothesis,
    MechanismRanking,
)
from hackathon_agents.tools.dft_job import DFTJob


def rank_hypotheses(
    hypotheses: Sequence[MechanismHypothesis],
    fit_results: Sequence[FitResult],
) -> list[MechanismRanking]:
    """Rank hypotheses using prior confidence and latest fit quality."""

    fits_by_hypothesis: dict[str, list[FitResult]] = defaultdict(list)
    for fit in fit_results:
        fits_by_hypothesis[fit.hypothesis_id].append(fit)

    latest_fits = {
        hypothesis_id: fits[-1]
        for hypothesis_id, fits in fits_by_hypothesis.items()
        if fits
    }
    aic_weights = _aic_weights([fit for fit in latest_fits.values() if fit.ok and fit.aic is not None])
    rankings: list[MechanismRanking] = []
    for hypothesis in hypotheses:
        fit = latest_fits.get(hypothesis.id)
        data_score = aic_weights.get(hypothesis.id, 0.0)
        prior_score = hypothesis.confidence
        score = max(0.0, min(1.0, 0.35 * prior_score + 0.65 * data_score))
        uncertainty = _combined_uncertainty(hypothesis, fit)
        evidence = list(hypothesis.literature_support[:2])
        caveats = list(hypothesis.assumptions[:1])
        if fit and fit.ok:
            evidence.append(f"least_squares RMSE={fit.rmse:.4f}" if fit.rmse is not None else "least_squares fit completed")
            if fit.aic is not None:
                evidence.append(f"AIC={fit.aic:.2f}")
        elif fit:
            caveats.append(f"fit failed: {fit.error}")
        else:
            caveats.append("no kinetic fit has been run for this hypothesis")
        rankings.append(
            MechanismRanking(
                hypothesis_id=hypothesis.id,
                title=hypothesis.title,
                mechanism_class=hypothesis.mechanism_class,
                score=score,
                uncertainty=uncertainty,
                evidence=evidence,
                caveats=caveats,
            )
        )
    return sorted(rankings, key=lambda ranking: ranking.score, reverse=True)


def build_critic_assessment(
    *,
    round_index: int,
    rankings: Sequence[MechanismRanking],
    fit_results: Sequence[FitResult],
    experiment: KineticExperiment | None,
    dft_jobs: Sequence[DFTJob],
) -> CriticAssessment:
    """Perform deterministic critic checks for plausibility and next actions."""

    plausibility_notes: list[str] = []
    overfitting_notes: list[str] = []
    identifiability_notes: list[str] = []
    missing_controls: list[str] = []
    dft_notes: list[str] = []
    robot_notes: list[str] = []

    if rankings:
        top = rankings[0]
        plausibility_notes.append(
            f"Top mechanism is {top.mechanism_class.value if hasattr(top.mechanism_class, 'value') else top.mechanism_class} "
            f"with score {top.score:.2f}; treat this as a hypothesis, not a conclusion."
        )
        if top.uncertainty > 0.55:
            identifiability_notes.append("Top-ranked hypothesis still has high uncertainty; add orthogonal controls.")
    else:
        plausibility_notes.append("No rankings are available yet.")
        identifiability_notes.append("Mechanism identifiability cannot be assessed without a fit.")

    recent_fits = list(fit_results[-max(1, len(rankings)):])
    for fit in recent_fits:
        if fit.ok and len(fit.parameters) >= 3:
            overfitting_notes.append(
                f"{fit.hypothesis_id} uses {len(fit.parameters)} fitted parameters; compare against simpler alternatives."
            )
        if fit.parameter_uncertainty and _mean_finite(fit.parameter_uncertainty.values()) > 0.5:
            identifiability_notes.append(f"{fit.hypothesis_id} has large parameter uncertainty.")

    if experiment is not None:
        additives = set(experiment.variables.additives)
        if "radical_trap_control" not in additives:
            missing_controls.append("radical trap control not yet included")
        if "product_spike_control" not in additives:
            missing_controls.append("product spike control not yet included")
        robot_notes.extend(experiment.safety_constraints)
        if experiment.variables.temperature > 333.15:
            robot_notes.append("experiment exceeds conservative mock temperature limit")
    else:
        robot_notes.append("no robot experiment has been proposed")

    if dft_jobs:
        for job in dft_jobs[-2:]:
            dft_notes.append(
                f"DFT job {job.id} targets {job.calculation_type}; verify it answers {job.reason_for_calculation}."
            )
    else:
        dft_notes.append("No DFT job submitted; acceptable when kinetic uncertainty is still experimentally resolvable.")

    return CriticAssessment(
        round_index=round_index,
        plausibility_notes=plausibility_notes,
        overfitting_notes=overfitting_notes,
        identifiability_notes=identifiability_notes,
        missing_controls=missing_controls[:4],
        dft_notes=dft_notes,
        robot_feasibility_notes=robot_notes,
        requires_human_review=bool(rankings and rankings[0].uncertainty > 0.75),
    )


def _aic_weights(fits: Sequence[FitResult]) -> dict[str, float]:
    if not fits:
        return {}
    min_aic = min(float(fit.aic) for fit in fits if fit.aic is not None)
    raw = {
        fit.hypothesis_id: math.exp(-0.5 * (float(fit.aic) - min_aic))
        for fit in fits
        if fit.aic is not None
    }
    total = sum(raw.values()) or 1.0
    return {hypothesis_id: value / total for hypothesis_id, value in raw.items()}


def _combined_uncertainty(hypothesis: MechanismHypothesis, fit: FitResult | None) -> float:
    if fit is None or not fit.ok:
        return hypothesis.uncertainty
    values = [value for value in fit.parameter_uncertainty.values() if math.isfinite(value)]
    fit_uncertainty = min(1.0, mean(values)) if values else 0.5
    residual_uncertainty = min(1.0, float(fit.rmse or 0.0) * 2.0)
    return max(0.05, min(1.0, 0.45 * hypothesis.uncertainty + 0.35 * fit_uncertainty + 0.20 * residual_uncertainty))


def _mean_finite(values) -> float:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return 0.0
    return mean(finite)
