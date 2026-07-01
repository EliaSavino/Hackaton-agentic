from __future__ import annotations

import unittest

from hackathon_agents.agents.critic import (
    CriticReviewResponse,
    _maybe_autoescalate_strategy,
    _merge_model_review,
)
from hackathon_agents.schemas.linkers import ADCGoalProfile, ADCStrategy
from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.schemas.tasks import CriticDecision
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.adc_linker_objective import render_reinvent_objective


def _adc_state(run_type: str = "staged_learning") -> DiscoveryStatePayload:
    profile = ADCGoalProfile()
    strategy = ADCStrategy(run_type=run_type)
    reinvent = render_reinvent_objective(profile, strategy, objective="Design an ADC linker")
    state = DiscoveryStatePayload(
        original_user_request="Design an ADC linker",
        max_iterations=3,
        iteration=1,
        metadata={
            "adc_goal_profile": profile.model_dump(mode="json"),
            "adc_strategy": strategy.model_dump(mode="json"),
            "adc_strategy_caps": {"max_steps": 100, "batch_size": 64},
            "reinvent": reinvent,
        },
    )
    # A prior deterministic decision (quality not yet met, but not a hard stop).
    state.critic_decisions.append(
        CriticDecision(needs_more_passes=False, reason="stub", stop_reason="quality_threshold_met", best_score=0.5)
    )
    state.stop_reason = "quality_threshold_met"
    state.needs_more_passes = False
    return state


class AutonomyTests(unittest.TestCase):
    def test_overrides_reweight_scoring_and_request_pass(self) -> None:
        state = _adc_state()
        before_weight = state.metadata["adc_goal_profile"]["weights"]["solubility"]
        review = CriticReviewResponse(
            goal_profile_overrides={"weights": {"solubility": 0.2}, "target_logp": 1.0},
            reason="candidates too lipophilic; push solubility",
        )
        _merge_model_review(state, review)

        # Profile updated + clamped, other weights preserved.
        self.assertEqual(state.metadata["adc_goal_profile"]["weights"]["solubility"], 0.2)
        self.assertNotEqual(state.metadata["adc_goal_profile"]["weights"]["solubility"], before_weight)
        self.assertEqual(state.metadata["adc_goal_profile"]["weights"]["synthesizability"], 0.8)
        self.assertEqual(state.metadata["adc_goal_profile"]["target_logp"], 1.0)

        # REINVENT scoring re-rendered with the new solubility weight.
        slogp = next(c for c in state.metadata["reinvent"]["scoring"] if c["component_type"] == "FragmentSlogP")
        self.assertEqual(slogp["endpoints"][0]["weight"], 0.2)

        # Loop requested + decision trail recorded.
        self.assertTrue(state.needs_more_passes)
        self.assertIsNone(state.stop_reason)
        trail = state.metadata["adc_decision_trail"]
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["weights_after"]["solubility"], 0.2)
        self.assertEqual(trail[0]["rationale"], "candidates too lipophilic; push solubility")

    def test_warhead_and_budget_edits_are_ignored(self) -> None:
        state = _adc_state()
        review = CriticReviewResponse(
            goal_profile_overrides={"warhead_pair": "X|Y", "batch_size": 9999, "weights": {"cleavability": 0.5}},
            reason="tweak",
        )
        _merge_model_review(state, review)
        self.assertNotIn("warhead_pair", state.metadata["adc_goal_profile"])
        # input_smiles (warheads) untouched; budget untouched.
        self.assertEqual(len(state.metadata["reinvent"]["input_smiles"]), 1)
        self.assertEqual(state.metadata["reinvent"]["batch_size"], 64)
        self.assertEqual(state.metadata["adc_goal_profile"]["weights"]["cleavability"], 0.5)

    def test_no_overrides_leaves_profile_and_no_forced_pass(self) -> None:
        state = _adc_state()
        review = CriticReviewResponse(summary_notes=["looks fine"])
        _merge_model_review(state, review)
        self.assertNotIn("adc_decision_trail", state.metadata)
        self.assertFalse(state.needs_more_passes)

    def test_hard_stop_blocks_overrides(self) -> None:
        state = _adc_state()
        state.iteration = 3  # == max_iterations => hard stop
        review = CriticReviewResponse(goal_profile_overrides={"weights": {"solubility": 0.1}})
        _merge_model_review(state, review)
        self.assertNotIn("adc_decision_trail", state.metadata)
        self.assertEqual(state.metadata["adc_goal_profile"]["weights"]["solubility"], 1.0)  # unchanged


class StrategyAutonomyTests(unittest.TestCase):
    def test_llm_escalates_sampling_to_rl(self) -> None:
        state = _adc_state("sampling")
        self.assertNotIn("scoring", state.metadata["reinvent"])  # sampling has no scoring
        review = CriticReviewResponse(
            reinvent_strategy_overrides={"run_type": "staged_learning"},
            reason="baseline captured; optimize with RL",
        )
        _merge_model_review(state, review)
        self.assertEqual(state.metadata["adc_strategy"]["run_type"], "staged_learning")
        self.assertIn("scoring", state.metadata["reinvent"])  # re-rendered as RL
        self.assertTrue(state.needs_more_passes)
        self.assertEqual(len(state.metadata["adc_decision_trail"]), 1)

    def test_budget_clamped_to_caps_and_device_run_fixed(self) -> None:
        state = _adc_state("staged_learning")
        review = CriticReviewResponse(
            reinvent_strategy_overrides={"max_steps": 99999, "batch_size": 9999, "device": "cuda:0", "run": True}
        )
        _merge_model_review(state, review)
        strat = state.metadata["adc_strategy"]
        self.assertEqual(strat["max_steps"], 100)  # clamped to cap
        self.assertEqual(strat["batch_size"], 64)  # clamped to cap
        self.assertEqual(strat["device"], "cpu")  # not editable
        self.assertFalse(strat["run"])  # not editable

    def test_deterministic_escalation_without_llm(self) -> None:
        state = _adc_state("sampling")
        state.stop_reason = None
        state.needs_more_passes = False
        state.candidate_molecules = [
            MoleculeRecord(smiles="O=C(NCC(=O)NCCO)CCO", name="s1", source="reinvent", score=0.6)
        ]
        _maybe_autoescalate_strategy(state)
        self.assertEqual(state.metadata["adc_strategy"]["run_type"], "staged_learning")
        self.assertTrue(state.needs_more_passes)
        self.assertIn("optimize_linkers_with_rl", state.requested_next_actions)

    def test_no_escalation_when_sampling_quality_met(self) -> None:
        state = _adc_state("sampling")
        state.stop_reason = "quality_threshold_met"
        state.candidate_molecules = [
            MoleculeRecord(smiles="O=C(NCC(=O)NCCO)CCO", name="s1", source="reinvent", score=0.9)
        ]
        _maybe_autoescalate_strategy(state)
        self.assertEqual(state.metadata["adc_strategy"]["run_type"], "sampling")  # left as-is


if __name__ == "__main__":
    unittest.main()
