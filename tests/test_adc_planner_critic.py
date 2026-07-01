from __future__ import annotations

import unittest

from hackathon_agents.agents import critic, planner
from hackathon_agents.schemas.linkers import ADCGoalProfile
from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.adc_linker_objective import (
    DEFAULT_ADC_GOAL_PROFILE,
    build_adc_linkinvent_objective,
    score_adc_linker,
)


class PlannerADCDefaultTests(unittest.TestCase):
    def test_planner_seeds_adc_objective_from_intent(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="Design a soluble, cathepsin-cleavable ADC linker for maleimide conjugation"
        )
        state = planner.run(state)
        self.assertIn("adc_goal_profile", state.metadata)
        self.assertIn("reinvent", state.metadata)
        self.assertEqual(state.metadata["reinvent"]["generator_type"], "linkinvent")
        # ADC active => the generic Saturn oracle must NOT be seeded.
        self.assertNotIn("saturn", state.metadata)

    def test_planner_uses_saturn_default_for_non_adc_request(self) -> None:
        state = DiscoveryStatePayload(original_user_request="Design soluble kinase inhibitors")
        state = planner.run(state)
        self.assertNotIn("adc_goal_profile", state.metadata)
        self.assertIn("saturn", state.metadata)

    def test_preseeded_profile_is_respected(self) -> None:
        profile = ADCGoalProfile(weights={"solubility": 1.0, "size": 0.0})
        state = DiscoveryStatePayload(
            original_user_request="anything",
            metadata={"adc_goal_profile": profile.model_dump(mode="json")},
        )
        state = planner.run(state)
        self.assertIn("reinvent", state.metadata)
        self.assertEqual(state.metadata["reinvent"]["generator_type"], "linkinvent")


class ADCCompositeScoringTests(unittest.TestCase):
    def test_cleavable_soluble_linker_beats_labile_one(self) -> None:
        # A short amide-containing (cleavable) linker vs a hydrazone (labile).
        cleavable = "O=C(NCC(=O)NCCO)CCO"
        labile = "CC(C)=NNC(=O)CCCO"  # hydrazone, tripped by the stability alert
        good, _ = score_adc_linker(cleavable, DEFAULT_ADC_GOAL_PROFILE)
        bad, bad_sub = score_adc_linker(labile, DEFAULT_ADC_GOAL_PROFILE)
        self.assertIsNotNone(good)
        self.assertIsNotNone(bad)
        # Stability alert on the hydrazone zeroes the composite.
        self.assertEqual(bad_sub["stability"], 0.0)
        self.assertGreater(good, bad)

    def test_subscores_cover_all_goal_keys(self) -> None:
        _, sub = score_adc_linker("O=C(NCC(=O)NCCO)CCO", DEFAULT_ADC_GOAL_PROFILE)
        for key in ("solubility", "size", "flexibility", "synthesizability", "cleavability", "stability"):
            self.assertIn(key, sub)
            self.assertGreaterEqual(sub[key], 0.0)
            self.assertLessEqual(sub[key], 1.0)

    def test_invalid_smiles_returns_none(self) -> None:
        composite, sub = score_adc_linker("not_a_smiles", DEFAULT_ADC_GOAL_PROFILE)
        self.assertIsNone(composite)
        self.assertEqual(sub, {})

    def test_critic_scores_candidates_with_adc_objective(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="Design an ADC linker",
            metadata={"adc_goal_profile": DEFAULT_ADC_GOAL_PROFILE.model_dump(mode="json")},
            candidate_molecules=[
                MoleculeRecord(smiles="O=C(NCC(=O)NCCO)CCO", name="cand-a", source="reinvent"),
                MoleculeRecord(smiles="OCCOCCOCCO", name="cand-b", source="reinvent"),
            ],
        )
        state = critic.run(state)
        top = state.candidate_molecules[0]
        self.assertIsNotNone(top.score)
        self.assertIn("adc_composite", top.descriptors)
        self.assertIn("adc_solubility", top.descriptors)


if __name__ == "__main__":
    unittest.main()
