from __future__ import annotations

import unittest

from hackathon_agents.agents.critic import CriticReviewResponse, _merge_model_review
from hackathon_agents.schemas.linkers import ADCGoalProfile
from hackathon_agents.schemas.tasks import CriticDecision
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.adc_linker_objective import build_adc_linkinvent_objective


def _adc_state() -> DiscoveryStatePayload:
    profile = ADCGoalProfile()
    reinvent = build_adc_linkinvent_objective(profile, run=False)
    state = DiscoveryStatePayload(
        original_user_request="Design an ADC linker",
        max_iterations=3,
        iteration=1,
        metadata={
            "adc_goal_profile": profile.model_dump(mode="json"),
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


if __name__ == "__main__":
    unittest.main()
