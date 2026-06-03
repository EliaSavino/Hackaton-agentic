from __future__ import annotations

import unittest

from hackathon_agents.agents import critic
from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.state import DiscoveryStatePayload


class CriticLoopTests(unittest.TestCase):
    def test_critic_requests_more_candidates_when_below_target(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="Find candidates",
            iteration=1,
            max_iterations=3,
            candidate_molecules=[
                MoleculeRecord(
                    smiles="CCO",
                    name="ethanol",
                    descriptors={"qed": 0.6, "logp": 2.0, "mol_wt": 200.0},
                )
            ],
            metadata={"min_valid_candidates": 2, "score_threshold": 0.75},
        )

        final_state = critic.run(state)

        self.assertTrue(final_state.needs_more_passes)
        self.assertEqual(final_state.requested_next_actions, ["generate_more_candidates"])
        self.assertIsNone(final_state.stop_reason)
        self.assertEqual(final_state.critic_decisions[-1].valid_candidate_count, 1)

    def test_critic_stops_at_max_iterations(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="Find candidates",
            iteration=3,
            max_iterations=3,
        )

        final_state = critic.run(state)

        self.assertFalse(final_state.needs_more_passes)
        self.assertEqual(final_state.stop_reason, "max_iterations_reached")


if __name__ == "__main__":
    unittest.main()
