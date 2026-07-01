from __future__ import annotations

import json
import unittest

from hackathon_agents.mechanism.experiment_design import RLExperimentDesigner
from hackathon_agents.mechanism.hypothesis import (
    generate_hypothesis_json,
    generate_initial_hypotheses,
    validate_hypothesis_json,
)
from hackathon_agents.mechanism.mechanism_classes import MechanismClass
from hackathon_agents.mechanism.schemas import (
    FitResult,
    KineticExperiment,
    KineticExperimentVariables,
    LiteraturePrior,
    MechanismRanking,
)
from hackathon_agents.mechanism.uncertainty import build_critic_assessment, rank_hypotheses
from hackathon_agents.tools.dft_job import DFTCalculationType, DFTJob


def _fit(
    hypothesis_id: str,
    *,
    ok: bool = True,
    aic: float | None = 10.0,
    rmse: float | None = 0.1,
    parameters: dict[str, float] | None = None,
    uncertainty: dict[str, float] | None = None,
    error: str | None = None,
) -> FitResult:
    return FitResult(
        hypothesis_id=hypothesis_id,
        experiment_id="exp-001",
        ok=ok,
        model_name="toy",
        parameters=parameters or {"k": 1.0},
        parameter_uncertainty=uncertainty or {"k": 0.1},
        rmse=rmse,
        aic=aic,
        bic=aic,
        error=error,
    )


class HypothesisGenerationTests(unittest.TestCase):
    def test_generate_initial_hypotheses_uses_objective_keywords(self) -> None:
        hypotheses = generate_initial_hypotheses("Nickel acid/base coupling kinetics")

        self.assertEqual(MechanismClass(hypotheses[0].mechanism_class), MechanismClass.NICKEL_CATALYTIC_CYCLE)
        self.assertEqual(MechanismClass(hypotheses[1].mechanism_class), MechanismClass.ACID_BASE_CATALYSIS)
        self.assertEqual(len(hypotheses), 5)

    def test_generate_initial_hypotheses_prefers_substitution_keyword_for_second_slot(self) -> None:
        hypotheses = generate_initial_hypotheses("nucleophilic substitution with base")

        self.assertEqual(MechanismClass(hypotheses[1].mechanism_class), MechanismClass.NUCLEOPHILIC_SUBSTITUTION)
        self.assertIn("leaving_group", hypotheses[1].species)

    def test_generate_initial_hypotheses_includes_literature_prior_support(self) -> None:
        prior = LiteraturePrior(
            query="photoredox",
            summary="Prior summary",
            key_findings=["light matters", "radical trap suppresses product", "third finding"],
            citations=["Curie 2026", "Meitner 2025", "Ignored 2024"],
        )

        hypotheses = generate_initial_hypotheses("photoredox kinetics", prior=prior)

        self.assertEqual(
            hypotheses[0].literature_support,
            ["light matters", "radical trap suppresses product", "Prior citations available: Curie 2026, Meitner 2025"],
        )

    def test_generate_hypothesis_json_returns_schema_valid_payload(self) -> None:
        payload = generate_hypothesis_json("photoredox kinetics")
        hypotheses = validate_hypothesis_json(payload)

        self.assertEqual(len(hypotheses), 5)
        self.assertEqual(hypotheses[0].id, "h-001")

    def test_validate_hypothesis_json_uses_retry_payload(self) -> None:
        hypotheses = generate_initial_hypotheses("photoredox kinetics")
        retry_payload = json.dumps([hypothesis.model_dump(mode="json") for hypothesis in hypotheses])

        validated = validate_hypothesis_json('{"not": "a list"}', retry_json=retry_payload)

        self.assertEqual([hypothesis.id for hypothesis in validated], [hypothesis.id for hypothesis in hypotheses])

    def test_validate_hypothesis_json_reports_failed_retry(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid hypothesis JSON after retry"):
            validate_hypothesis_json('{"not": "a list"}', retry_json='{"still": "bad"}')


class ExperimentDesignerTests(unittest.TestCase):
    def test_designer_uses_first_hypotheses_when_no_rankings_exist(self) -> None:
        hypotheses = generate_initial_hypotheses("photoredox radical kinetics")

        experiment = RLExperimentDesigner().propose_next_experiment(
            objective="Resolve photoredox radical kinetics",
            hypotheses=hypotheses,
            rankings=[],
            round_index=1,
        )

        self.assertEqual(experiment.id, "exp-002")
        self.assertEqual(experiment.variables.light_intensity, 1.0)
        self.assertEqual(experiment.variables.catalyst_loading, 0.05)
        self.assertIn("radical_trap_control", experiment.variables.additives)
        self.assertAlmostEqual(experiment.expected_information_gain, 0.87)
        self.assertEqual(experiment.robot_protocol["variables"]["light_intensity"], 1.0)

    def test_designer_adds_product_and_buffer_controls_for_ranked_top_classes(self) -> None:
        hypotheses = generate_initial_hypotheses("acid/base photoredox kinetics")
        rankings = [
            MechanismRanking(
                hypothesis_id="h-004",
                title="product",
                mechanism_class=MechanismClass.PRODUCT_INHIBITION,
                score=0.51,
                uncertainty=0.6,
            ),
            MechanismRanking(
                hypothesis_id="h-002",
                title="acid",
                mechanism_class=MechanismClass.ACID_BASE_CATALYSIS,
                score=0.49,
                uncertainty=0.4,
            ),
        ]

        experiment = RLExperimentDesigner().propose_next_experiment(
            objective="Resolve acid/product effects",
            hypotheses=hypotheses,
            rankings=rankings,
            round_index=2,
        )

        self.assertIn("product_spike_control", experiment.variables.additives)
        self.assertIn("buffer_strength_variant", experiment.variables.additives)
        self.assertNotIn("radical_trap_control", experiment.variables.additives)
        self.assertAlmostEqual(experiment.expected_information_gain, 0.873)

    def test_designer_caps_temperature_at_mock_robot_limit(self) -> None:
        hypotheses = generate_initial_hypotheses("photoredox kinetics")

        experiment = RLExperimentDesigner().propose_next_experiment(
            objective="hot run",
            hypotheses=hypotheses,
            rankings=[],
            round_index=99,
        )

        self.assertEqual(experiment.variables.temperature, 333.15)
        self.assertEqual(experiment.variables.concentrations, {"A": 1.8, "B": 1.8})


class UncertaintyRankingTests(unittest.TestCase):
    def test_rank_hypotheses_combines_prior_and_aic_weight(self) -> None:
        hypotheses = generate_initial_hypotheses("photoredox kinetics")
        fits = [
            _fit("h-001", aic=20.0, rmse=0.2),
            _fit("h-002", aic=1.0, rmse=0.05),
        ]

        rankings = rank_hypotheses(hypotheses[:3], fits)

        self.assertEqual(rankings[0].hypothesis_id, "h-002")
        self.assertIn("AIC=1.00", rankings[0].evidence)
        self.assertIn("least_squares RMSE=0.0500", rankings[0].evidence)
        self.assertLess(rankings[0].uncertainty, hypotheses[1].uncertainty)

    def test_rank_hypotheses_records_failed_fit_and_missing_fit_caveats(self) -> None:
        hypotheses = generate_initial_hypotheses("photoredox kinetics")
        fits = [_fit("h-001", ok=False, aic=None, rmse=None, error="singular matrix")]

        rankings = rank_hypotheses(hypotheses[:2], fits)
        by_id = {ranking.hypothesis_id: ranking for ranking in rankings}

        self.assertIn("fit failed: singular matrix", by_id["h-001"].caveats)
        self.assertIn("no kinetic fit has been run", by_id["h-002"].caveats[1])

    def test_rank_hypotheses_handles_empty_inputs(self) -> None:
        self.assertEqual(rank_hypotheses([], []), [])


class CriticAssessmentTests(unittest.TestCase):
    def test_critic_assessment_flags_high_uncertainty_and_missing_controls(self) -> None:
        experiment = KineticExperiment(
            id="exp-hot",
            objective="test",
            variables=KineticExperimentVariables(temperature=340.0, additives=[]),
            safety_constraints=["mock safety"],
        )
        rankings = [
            MechanismRanking(
                hypothesis_id="h-001",
                title="uncertain",
                mechanism_class=MechanismClass.RADICAL_CHAIN,
                score=0.4,
                uncertainty=0.8,
            )
        ]
        fits = [_fit("h-001", parameters={"k1": 1.0, "k2": 2.0, "k3": 3.0}, uncertainty={"k1": 0.9})]
        dft_job = DFTJob(
            id="dft-001",
            molecule_or_structure="H 0 0 0",
            calculation_type=DFTCalculationType.TRANSITION_STATE,
            reason_for_calculation="test barrier",
            linked_hypothesis_id="h-001",
        )

        assessment = build_critic_assessment(
            round_index=2,
            rankings=rankings,
            fit_results=fits,
            experiment=experiment,
            dft_jobs=[dft_job],
        )

        self.assertTrue(assessment.requires_human_review)
        self.assertIn("Top-ranked hypothesis still has high uncertainty", assessment.identifiability_notes[0])
        self.assertIn("radical trap control not yet included", assessment.missing_controls)
        self.assertIn("product spike control not yet included", assessment.missing_controls)
        self.assertIn("experiment exceeds conservative mock temperature limit", assessment.robot_feasibility_notes)
        self.assertIn("uses 3 fitted parameters", assessment.overfitting_notes[0])
        self.assertIn("DFT job dft-001", assessment.dft_notes[0])

    def test_critic_assessment_without_rankings_or_experiment_is_actionable(self) -> None:
        assessment = build_critic_assessment(
            round_index=0,
            rankings=[],
            fit_results=[],
            experiment=None,
            dft_jobs=[],
        )

        self.assertFalse(assessment.requires_human_review)
        self.assertEqual(assessment.plausibility_notes, ["No rankings are available yet."])
        self.assertIn("Mechanism identifiability cannot be assessed", assessment.identifiability_notes[0])
        self.assertEqual(assessment.robot_feasibility_notes, ["no robot experiment has been proposed"])
        self.assertIn("No DFT job submitted", assessment.dft_notes[0])


if __name__ == "__main__":
    unittest.main()
