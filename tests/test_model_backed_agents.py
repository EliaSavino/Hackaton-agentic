from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from hackathon_agents.agents import chemist, critic, planner
from hackathon_agents.config import AgentConfig, AppConfig, ModelConfig, ModelRoutingConfig, RunMode
from hackathon_agents.llm.client import CompletionResult
from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.state import DiscoveryStatePayload


def _model_config() -> AppConfig:
    return AppConfig(
        config_dir=Path("configs"),
        run_mode=RunMode.CHEAP,
        models={
            "fake": ModelConfig(
                provider="other",
                model="fake/model",
                capabilities=["reasoning", "chemistry", "final_review", "formatting"],
                enabled=True,
            )
        },
        agents={
            "planner": AgentConfig(requires=["reasoning"], preferred_model="fake"),
            "chemist": AgentConfig(requires=["reasoning", "chemistry"], preferred_model="fake"),
            "critic": AgentConfig(requires=["reasoning", "final_review"], preferred_model="fake"),
        },
        model_routing=ModelRoutingConfig(default_alias="fake"),
    )


def _completion(payload: dict) -> CompletionResult:
    return CompletionResult(
        ok=True,
        content=json.dumps(payload),
        model_alias="fake",
        provider="other",
    )


class ModelBackedAgentTests(unittest.TestCase):
    def test_planner_accepts_validated_model_plan(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="Find photoredox substrates",
            metadata={"agent_llm_mode": "always"},
        )
        payload = {
            "objective": "Find photoredox substrates",
            "assumptions": ["model-created assumption"],
            "steps": [
                {
                    "name": "Model plan step",
                    "description": "Use model context and deterministic tools.",
                    "agent": "chemist",
                    "tool_names": ["rdkit"],
                }
            ],
        }

        with patch("hackathon_agents.agents.model_helpers.LLMClient.complete", return_value=_completion(payload)):
            final_state = planner.run(state, config=_model_config())

        self.assertEqual(final_state.plan.assumptions, ["model-created assumption"])
        self.assertEqual(final_state.plan.steps[0].name, "Model plan step")
        self.assertTrue(final_state.metadata["model_calls"][-1]["ok"])

    def test_chemist_adds_model_candidates(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="Find candidate substrates",
            metadata={"agent_llm_mode": "always"},
        )
        payload = {
            "candidates": [
                {
                    "smiles": "CCO",
                    "name": "ethanol",
                    "notes": ["small polar substrate"],
                }
            ],
            "rationale_notes": ["Model proposed a compact alcohol control."],
        }

        with patch("hackathon_agents.agents.model_helpers.LLMClient.complete", return_value=_completion(payload)):
            final_state = chemist.run(state, config=_model_config())

        self.assertEqual(len(final_state.candidate_molecules), 1)
        self.assertEqual(final_state.candidate_molecules[0].smiles, "CCO")
        self.assertEqual(final_state.candidate_molecules[0].source, "model:fake")
        self.assertIn("Model proposed", final_state.critic_notes[0])

    def test_critic_can_request_bounded_model_followup(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="Find candidate substrates",
            iteration=1,
            max_iterations=3,
            candidate_molecules=[
                MoleculeRecord(
                    smiles="CCO",
                    name="ethanol",
                    descriptors={"qed": 0.8, "logp": 2.0, "mol_wt": 250.0},
                )
            ],
            metadata={
                "agent_llm_mode": "always",
                "min_valid_candidates": 1,
                "score_threshold": 0.1,
            },
        )
        payload = {
            "summary_notes": ["Candidate set lacks structural diversity."],
            "risk_flags": ["single candidate only"],
            "recommended_next_actions": ["generate_more_scaffold_diversity"],
            "should_continue": True,
            "reason": "Need a bounded diversity pass.",
        }

        with patch("hackathon_agents.agents.model_helpers.LLMClient.complete", return_value=_completion(payload)):
            final_state = critic.run(state, config=_model_config())

        self.assertTrue(final_state.needs_more_passes)
        self.assertEqual(final_state.stop_reason, None)
        self.assertEqual(final_state.requested_next_actions, ["generate_more_scaffold_diversity"])
        self.assertIn("Model critic", final_state.critic_notes[-2])


if __name__ == "__main__":
    unittest.main()
