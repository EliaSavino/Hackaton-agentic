from __future__ import annotations

import unittest

from pydantic import ValidationError

from hackathon_agents.mechanism.mechanism_classes import MechanismClass, all_mechanism_classes
from hackathon_agents.mechanism.schemas import (
    KineticDataset,
    KineticExperiment,
    KineticExperimentVariables,
    LiteraturePrior,
    MechanismHypothesis,
)
from hackathon_agents.schemas.molecules import MoleculeFilterConstraints, MoleculeRecord
from hackathon_agents.schemas.results import ToolResult
from hackathon_agents.schemas.tasks import CriticDecision, DiscoveryPlan, DiscoveryPlanStep
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.dft_job import DFTCalculationType, DFTJob, DFTResult


class CoreSchemaContractTests(unittest.TestCase):
    def test_discovery_state_appends_messages_errors_and_tool_results(self) -> None:
        state = DiscoveryStatePayload(original_user_request="find substrates")

        state.append_message("started")
        state.add_tool_result("ok-tool", ToolResult(ok=True, data={"value": 1}))
        state.add_tool_result("bad-tool", ToolResult(ok=False, error="boom"))

        self.assertEqual(state.messages, ["started", "error: bad-tool: boom"])
        self.assertEqual(len(state.tool_results), 2)
        self.assertEqual(state.errors, ["bad-tool: boom"])

    def test_discovery_state_run_path_is_optional_path(self) -> None:
        state = DiscoveryStatePayload(original_user_request="run")

        self.assertIsNone(state.run_path)
        state.run_dir = "/tmp/example-run"
        self.assertEqual(str(state.run_path), "/tmp/example-run")

    def test_discovery_plan_defaults_are_independent_lists(self) -> None:
        first = DiscoveryPlan(objective="a")
        second = DiscoveryPlan(objective="b")
        first.steps.append(DiscoveryPlanStep(name="plan", description="desc", agent="planner"))

        self.assertEqual(len(first.steps), 1)
        self.assertEqual(second.steps, [])

    def test_critic_decision_defaults_capture_terminal_state(self) -> None:
        decision = CriticDecision(needs_more_passes=False, reason="enough evidence", stop_reason="complete")

        self.assertFalse(decision.needs_more_passes)
        self.assertEqual(decision.requested_next_actions, [])
        self.assertEqual(decision.valid_candidate_count, 0)
        self.assertIsNone(decision.best_score)

    def test_molecule_record_and_constraints_defaults(self) -> None:
        molecule = MoleculeRecord(smiles="CCO")
        constraints = MoleculeFilterConstraints()

        self.assertEqual(molecule.source, "generated")
        self.assertEqual(molecule.notes, [])
        self.assertEqual(molecule.metadata, {})
        self.assertEqual(constraints.max_mol_wt, 650.0)
        self.assertEqual(constraints.max_logp, 6.0)

    def test_literature_prior_forbids_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            LiteraturePrior(query="q", summary="s", unexpected=True)

    def test_mechanism_hypothesis_enforces_probability_bounds(self) -> None:
        with self.assertRaises(ValidationError):
            MechanismHypothesis(
                id="h",
                title="bad",
                mechanism_class=MechanismClass.RADICAL_CHAIN,
                species=["A"],
                elementary_steps=["step"],
                rate_law_form="rate = k[A]",
                confidence=1.2,
            )

    def test_kinetic_experiment_variables_validate_positive_physical_values(self) -> None:
        with self.assertRaises(ValidationError):
            KineticExperimentVariables(temperature=0.0)

        with self.assertRaises(ValidationError):
            KineticExperimentVariables(residence_time=-1.0)

        with self.assertRaises(ValidationError):
            KineticExperimentVariables(light_intensity=-0.1)

    def test_kinetic_dataset_requires_non_empty_aligned_profiles(self) -> None:
        with self.assertRaisesRegex(ValidationError, "time_points must not be empty"):
            KineticDataset(experiment_id="empty", time_points=[], concentration_profiles={"A": []})

        with self.assertRaisesRegex(ValidationError, "expected 2"):
            KineticDataset(experiment_id="mismatch", time_points=[0.0, 1.0], concentration_profiles={"A": [1.0]})

    def test_kinetic_experiment_defaults_measured_species_and_protocol(self) -> None:
        experiment = KineticExperiment(id="exp", objective="test", variables=KineticExperimentVariables())

        self.assertEqual(experiment.measured_species, ["A", "B", "P"])
        self.assertEqual(experiment.sampling_strategy, "uniform time-resolved sampling")
        self.assertEqual(experiment.robot_protocol, {})

    def test_dft_job_and_result_defaults(self) -> None:
        job = DFTJob(id="dft", molecule_or_structure="H 0 0 0", reason_for_calculation="energy", linked_hypothesis_id="h")
        result = DFTResult(job_id="dft", status="dry-run")

        self.assertEqual(job.calculation_type, DFTCalculationType.OPTIMIZATION)
        self.assertEqual(job.method, "B3LYP")
        self.assertEqual(result.frequencies_cm1, [])
        self.assertTrue(result.parsed_ok)

    def test_dft_job_forbids_invalid_multiplicity(self) -> None:
        with self.assertRaises(ValidationError):
            DFTJob(
                id="bad",
                molecule_or_structure="H 0 0 0",
                multiplicity=0,
                reason_for_calculation="energy",
                linked_hypothesis_id="h",
            )

    def test_all_mechanism_classes_returns_display_values_in_enum_order(self) -> None:
        labels = all_mechanism_classes()

        self.assertEqual(labels[0], MechanismClass.RADICAL_CHAIN.value)
        self.assertIn(MechanismClass.UNKNOWN_MIXED.value, labels)
        self.assertEqual(len(labels), len(MechanismClass))


if __name__ == "__main__":
    unittest.main()
