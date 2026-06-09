from __future__ import annotations

import unittest

from hackathon_agents.mechanism.hypothesis import generate_hypothesis_json, validate_hypothesis_json
from hackathon_agents.mechanism.schemas import LiteraturePrior
from hackathon_agents.mechanism.state import MechanismDiscoveryState


class MechanismStateTests(unittest.TestCase):
    def test_state_defaults_are_bounded(self) -> None:
        state = MechanismDiscoveryState(objective="Infer mechanism", max_rounds=2)
        self.assertEqual(state.mode, "mock")
        self.assertEqual(state.max_rounds, 2)
        self.assertEqual(state.round_index, 0)
        self.assertEqual(state.hypotheses, [])

    def test_hypothesis_json_is_schema_validated(self) -> None:
        prior = LiteraturePrior(query="test", summary="mock prior")
        raw_json = generate_hypothesis_json("Infer mechanism for photochemical reaction A + B -> P", prior)
        hypotheses = validate_hypothesis_json(raw_json)
        self.assertGreaterEqual(len(hypotheses), 3)
        self.assertTrue(all(hypothesis.id for hypothesis in hypotheses))

    def test_invalid_hypothesis_json_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_hypothesis_json('[{"id": "bad"}]')


if __name__ == "__main__":
    unittest.main()
