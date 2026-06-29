from __future__ import annotations

from statistics import mean

from pydantic import BaseModel, Field

from hackathon_agents.agents.model_helpers import call_agent_model
from hackathon_agents.config import AppConfig
from hackathon_agents.schemas.tasks import CriticDecision
from hackathon_agents.state import DiscoveryStatePayload


class CriticReviewResponse(BaseModel):
    summary_notes: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    should_continue: bool | None = None
    reason: str | None = None


def run(state: DiscoveryStatePayload, config: AppConfig | None = None) -> DiscoveryStatePayload:
    scored = []
    for molecule in state.candidate_molecules:
        descriptors = molecule.descriptors
        qed = _float_or_none(descriptors.get("qed"))
        logp = _float_or_none(descriptors.get("logp"))
        mol_wt = _float_or_none(descriptors.get("mol_wt"))
        boltz_energy = _float_or_none(descriptors.get("boltz_energy"))

        components = []
        if qed is not None:
            components.append(qed)
        if logp is not None:
            components.append(max(0.0, 1.0 - abs(logp - 2.0) / 6.0))
        if mol_wt is not None:
            components.append(max(0.0, 1.0 - abs(mol_wt - 250.0) / 500.0))

        if boltz_energy is not None:
            # Convert predicted delta-G to 0-to-1 score where -15.0 kcal/mol is 1.0 and >= -2.0 is 0.0
            if boltz_energy >= -2.0:
                boltz_score = 0.0
            elif boltz_energy <= -15.0:
                boltz_score = 1.0
            else:
                boltz_score = (boltz_energy - (-2.0)) / (-15.0 - (-2.0))
            components.append(boltz_score)

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
    state.metadata["best_score"] = decision.best_score
    state.metadata["valid_candidate_count"] = decision.valid_candidate_count

    model_review = call_agent_model(
        state=state,
        config=config,
        agent_name="critic",
        task_type="critic",
        response_model=CriticReviewResponse,
        expected_difficulty="medium",
        user_payload={
            "objective": state.original_user_request,
            "iteration": state.iteration,
            "max_iterations": state.max_iterations,
            "deterministic_decision": decision.model_dump(mode="json"),
            "candidate_summary": [
                {
                    "name": molecule.name,
                    "smiles": molecule.smiles,
                    "score": molecule.score,
                    "descriptors": molecule.descriptors,
                    "source": molecule.source,
                    "notes": molecule.notes,
                }
                for molecule in state.candidate_molecules[:15]
            ],
            "tool_failures": [
                record.model_dump(mode="json")
                for record in state.tool_results
                if not record.result.ok
            ][-10:],
            "instructions": [
                "Check plausibility, uncertainty, missing controls, tool failures, and overclaiming.",
                "Recommend another pass only when a bounded next action can improve the result.",
                "Do not ask for another pass when max_iterations has been reached.",
            ],
        },
    )
    if model_review is not None:
        _merge_model_review(state, model_review)

    current_decision = state.critic_decisions[-1]
    history = state.metadata.setdefault("critic_history", [])
    history.append(current_decision.model_dump(mode="json"))
    state.metadata["best_score"] = current_decision.best_score
    state.metadata["valid_candidate_count"] = current_decision.valid_candidate_count

    state.append_message("critic: ranked candidates with a simple descriptor heuristic")
    state.append_message(f"critic: {current_decision.reason}")
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


def _merge_model_review(state: DiscoveryStatePayload, review: CriticReviewResponse) -> None:
    for note in review.summary_notes[:5]:
        if note:
            state.critic_notes.append(f"Model critic: {note}")
    for flag in review.risk_flags[:5]:
        if flag:
            state.critic_notes.append(f"Model risk flag: {flag}")

    state.metadata["model_critic_review"] = review.model_dump(mode="json")
    hard_stop = state.iteration >= state.max_iterations or state.stop_reason in {
        "max_iterations_reached",
        "descriptor_tools_unavailable",
        "too_many_tool_errors",
    }
    if hard_stop:
        return

    actions = [action for action in review.recommended_next_actions if action]
    if state.needs_more_passes:
        state.requested_next_actions = _dedupe([*state.requested_next_actions, *actions])
        if state.critic_decisions:
            state.critic_decisions[-1].requested_next_actions = state.requested_next_actions
        return

    if review.should_continue:
        state.needs_more_passes = True
        state.stop_reason = None
        state.requested_next_actions = actions or ["address_model_critic_concerns"]
        reason = review.reason or "Model critic requested another bounded pass."
        if state.critic_decisions:
            state.critic_decisions[-1].needs_more_passes = True
            state.critic_decisions[-1].reason = reason
            state.critic_decisions[-1].requested_next_actions = state.requested_next_actions
            state.critic_decisions[-1].stop_reason = None
        state.append_message(f"critic: model review requested another pass: {reason}")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
