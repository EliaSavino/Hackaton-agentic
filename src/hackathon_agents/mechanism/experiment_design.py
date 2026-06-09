from __future__ import annotations

from typing import Protocol, Sequence

from hackathon_agents.mechanism.mechanism_classes import MechanismClass
from hackathon_agents.mechanism.schemas import (
    KineticExperiment,
    KineticExperimentVariables,
    MechanismHypothesis,
    MechanismRanking,
)


class ActiveLearningPolicy(Protocol):
    """Replacement point for a learned RL policy."""

    def propose_next_experiment(
        self,
        *,
        objective: str,
        hypotheses: Sequence[MechanismHypothesis],
        rankings: Sequence[MechanismRanking],
        round_index: int,
    ) -> KineticExperiment:
        """Return the next bounded experiment proposal."""


class RLExperimentDesigner:
    """Heuristic active-learning designer with an RL-compatible interface.

    The heuristic prioritizes disagreement between leading mechanism classes,
    parameter uncertainty, and robot-feasible conditions.  A real RL policy can
    implement the same method signature and be injected into the graph.
    """

    def propose_next_experiment(
        self,
        *,
        objective: str,
        hypotheses: Sequence[MechanismHypothesis],
        rankings: Sequence[MechanismRanking],
        round_index: int,
    ) -> KineticExperiment:
        top_classes = _top_mechanism_classes(hypotheses=hypotheses, rankings=rankings)
        uncertainty = _ranking_uncertainty(rankings)
        disagreement = _class_disagreement(rankings)
        expected_information_gain = min(1.0, 0.35 + 0.35 * disagreement + 0.30 * uncertainty)
        concentration_scale = 1.0 + 0.2 * min(round_index, 4)
        light_intensity = 1.0 if MechanismClass.PHOTOREDOX_CATALYTIC_CYCLE in top_classes else 0.4
        if MechanismClass.RADICAL_CHAIN in top_classes:
            light_intensity = max(light_intensity, 0.8)
        catalyst_loading = 0.02
        if any(
            mechanism_class in top_classes
            for mechanism_class in (
                MechanismClass.PHOTOREDOX_CATALYTIC_CYCLE,
                MechanismClass.NICKEL_CATALYTIC_CYCLE,
                MechanismClass.CATALYST_DEACTIVATION,
            )
        ):
            catalyst_loading = 0.05

        variables = KineticExperimentVariables(
            concentrations={"A": concentration_scale, "B": concentration_scale},
            temperature=min(333.15, 298.15 + 5.0 * round_index),
            residence_time=10.0 + 3.0 * round_index,
            flow_rate_profile=[1.0, 0.8 + 0.05 * round_index, 1.2],
            light_intensity=light_intensity,
            catalyst_loading=catalyst_loading,
            solvent="MeCN",
            additives=_diagnostic_additives(top_classes, round_index),
        )
        experiment_id = f"exp-{round_index + 1:03d}"
        return KineticExperiment(
            id=experiment_id,
            objective=f"Resolve mechanism disagreement for: {objective}",
            variables=variables,
            measured_species=["A", "B", "P"],
            sampling_strategy="12-24 point uniform time-resolved sampling across residence time",
            expected_information_gain=expected_information_gain,
            safety_constraints=[
                "temperature <= 333.15 K",
                "catalyst_loading <= 0.05 equiv",
                "light_intensity <= calibrated mock maximum",
                "no real robot submission unless explicitly enabled",
            ],
            robot_protocol={
                "schema_version": "mechanism-v1",
                "experiment_id": experiment_id,
                "mode": "mockable",
                "measured_species": ["A", "B", "P"],
                "variables": variables.model_dump(mode="json"),
            },
        )


def _top_mechanism_classes(
    *,
    hypotheses: Sequence[MechanismHypothesis],
    rankings: Sequence[MechanismRanking],
) -> set[MechanismClass]:
    if rankings:
        top_ids = {ranking.hypothesis_id for ranking in rankings[:2]}
        return {MechanismClass(hypothesis.mechanism_class) for hypothesis in hypotheses if hypothesis.id in top_ids}
    return {MechanismClass(hypothesis.mechanism_class) for hypothesis in hypotheses[:2]}


def _ranking_uncertainty(rankings: Sequence[MechanismRanking]) -> float:
    if not rankings:
        return 0.8
    return max(ranking.uncertainty for ranking in rankings[:3])


def _class_disagreement(rankings: Sequence[MechanismRanking]) -> float:
    if len(rankings) < 2:
        return 0.8
    top_score = rankings[0].score
    second_score = rankings[1].score
    return max(0.0, 1.0 - abs(top_score - second_score))


def _diagnostic_additives(top_classes: set[MechanismClass], round_index: int) -> list[str]:
    additives: list[str] = []
    if MechanismClass.RADICAL_CHAIN in top_classes and round_index % 2 == 1:
        additives.append("radical_trap_control")
    if MechanismClass.PRODUCT_INHIBITION in top_classes:
        additives.append("product_spike_control")
    if MechanismClass.ACID_BASE_CATALYSIS in top_classes:
        additives.append("buffer_strength_variant")
    return additives
