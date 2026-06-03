from __future__ import annotations

from statistics import mean

from hackathon_agents.schemas.tasks import CriticDecision
from hackathon_agents.state import DiscoveryStatePayload


def run(state: DiscoveryStatePayload) -> DiscoveryStatePayload:
    scored = []
    for molecule in state.candidate_molecules:
        descriptors = molecule.descriptors
        qed = _float_or_none(descriptors.get("qed"))
        logp = _float_or_none(descriptors.get("logp"))
        mol_wt = _float_or_none(descriptors.get("mol_wt"))
        components = []
        if qed is not None:
            components.append(qed)
        if logp is not None:
            components.append(max(0.0, 1.0 - abs(logp - 2.0) / 6.0))
        if mol_wt is not None:
            components.append(max(0.0, 1.0 - abs(mol_wt - 250.0) / 500.0))
        molecule.score = mean(components) if components else None
        scored.append(molecule)

    state.candidate_molecules = sorted(
        scored,
        key=lambda item: item.score if item.score is not None else -1.0,
        reverse=True,
    )
    if state.candidate_molecules and state.candidate_molecules[0].score is not None:
        top = state.candidate_molecules[0]
        state.critic_notes.append(
            f"Top deterministic candidate by descriptor heuristic: {top.name or top.smiles} "
            f"(score={top.score:.3f})."
        )
    else:
        state.critic_notes.append("Descriptor scoring was unavailable; review candidates manually.")
    decision = _decide_next_pass(state)
    state.needs_more_passes = decision.needs_more_passes
    state.requested_next_actions = decision.requested_next_actions
    state.stop_reason = decision.stop_reason
    state.critic_decisions.append(decision)

    history = state.metadata.setdefault("critic_history", [])
    history.append(decision.model_dump(mode="json"))
    state.metadata["best_score"] = decision.best_score
    state.metadata["valid_candidate_count"] = decision.valid_candidate_count

    state.append_message("critic: ranked candidates with a simple descriptor heuristic")
    state.append_message(f"critic: {decision.reason}")
    return state


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return None


def _decide_next_pass(state: DiscoveryStatePayload) -> CriticDecision:
    valid_candidates = [molecule for molecule in state.candidate_molecules if molecule.score is not None]
    valid_count = len(valid_candidates)
    best_score = valid_candidates[0].score if valid_candidates else None

    min_valid_candidates = int(state.metadata.get("min_valid_candidates", 10))
    score_threshold = float(state.metadata.get("score_threshold", 0.75))
    max_tool_errors = int(state.metadata.get("max_tool_errors", 8))
    min_score_improvement = float(state.metadata.get("min_score_improvement", 0.01))
    previous_best = state.metadata.get("best_score")

    if state.iteration >= state.max_iterations:
        return CriticDecision(
            needs_more_passes=False,
            reason=f"Stopping after reaching max_iterations={state.max_iterations}.",
            stop_reason="max_iterations_reached",
            valid_candidate_count=valid_count,
            best_score=best_score,
        )

    if _deterministic_descriptor_unavailable(state):
        return CriticDecision(
            needs_more_passes=False,
            reason="Stopping because deterministic descriptor tools are unavailable.",
            stop_reason="descriptor_tools_unavailable",
            valid_candidate_count=valid_count,
            best_score=best_score,
        )

    if len(state.errors) >= max_tool_errors:
        return CriticDecision(
            needs_more_passes=False,
            reason=f"Stopping because accumulated tool errors reached {len(state.errors)}.",
            stop_reason="too_many_tool_errors",
            valid_candidate_count=valid_count,
            best_score=best_score,
        )

    if valid_count < min_valid_candidates:
        return CriticDecision(
            needs_more_passes=True,
            reason=f"Requesting another pass: {valid_count} valid candidates below target {min_valid_candidates}.",
            requested_next_actions=["generate_more_candidates"],
            valid_candidate_count=valid_count,
            best_score=best_score,
        )

    if best_score is not None and best_score < score_threshold:
        if previous_best is not None and best_score <= float(previous_best) + min_score_improvement:
            return CriticDecision(
                needs_more_passes=False,
                reason="Stopping because best score did not improve enough on the last pass.",
                stop_reason="no_material_improvement",
                valid_candidate_count=valid_count,
                best_score=best_score,
            )
        return CriticDecision(
            needs_more_passes=True,
            reason=f"Requesting another pass: best score {best_score:.3f} below target {score_threshold:.3f}.",
            requested_next_actions=["improve_candidates"],
            valid_candidate_count=valid_count,
            best_score=best_score,
        )

    return CriticDecision(
        needs_more_passes=False,
        reason="Stopping because candidate set meets deterministic quality criteria.",
        stop_reason="quality_threshold_met",
        valid_candidate_count=valid_count,
        best_score=best_score,
    )


def _deterministic_descriptor_unavailable(state: DiscoveryStatePayload) -> bool:
    return any("RDKit is not installed" in error for error in state.errors)
