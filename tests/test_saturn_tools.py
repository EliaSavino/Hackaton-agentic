from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.agents import chemist, planner
from hackathon_agents.config import AppConfig, RunMode, ToolConfig
from hackathon_agents.graph import build_graph
from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.saturn_tools import (
    OracleComponent,
    SaturnGenerationInput,
    build_saturn_config,
    check_saturn_availability,
    generate_with_saturn,
    saturn_records,
)


def _config_with_saturn(enabled: bool, run_mode: RunMode = RunMode.NO_DFT) -> AppConfig:
    return AppConfig(
        config_dir=Path("configs"),
        run_mode=run_mode,
        models={},
        agents={},
        tools={"saturn": ToolConfig(enabled=enabled, enabled_modes=[RunMode.FULL, RunMode.CHEAP, RunMode.NO_DFT])},
    )


class SaturnToolTests(unittest.TestCase):
    def test_build_config_includes_oracle_and_agent_settings(self) -> None:
        config = build_saturn_config(
            SaturnGenerationInput(
                work_dir="unused",
                oracle=[
                    OracleComponent(name="qed", weight=1.0),
                    OracleComponent(name="sa", weight=0.5, specific_parameters={"max": 4.0}),
                ],
                aggregator="product",
                n_steps=42,
                batch_size=32,
            )
        )
        self.assertEqual(config["running_mode"], "goal_directed_generation")
        self.assertEqual(config["oracle"]["aggregator"], "product")
        names = [component["name"] for component in config["oracle"]["components"]]
        self.assertEqual(names, ["qed", "sa"])
        rl = config["goal_directed_generation"]["reinforcement_learning"]
        self.assertEqual(rl["n_steps"], 42)
        self.assertEqual(rl["batch_size"], 32)

    def test_generate_writes_config_and_returns_mock_molecules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_with_saturn(
                {
                    "work_dir": tmp,
                    "objective": "Design soluble kinase inhibitors.",
                    "oracle": [{"name": "qed"}],
                    "run": False,
                    "max_return": 5,
                }
            )
            self.assertTrue(result.ok)
            self.assertTrue(result.data["mock"])
            self.assertEqual(result.data["molecule_count"], 5)
            config_path = Path(result.data["config_path"])
            self.assertTrue(config_path.exists())
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertIn("oracle", config)
            molecules = saturn_records(result.data)
            self.assertEqual(len(molecules), 5)
            self.assertTrue(all(isinstance(m, MoleculeRecord) for m in molecules))
            self.assertTrue(all(m.source == "saturn_mock" for m in molecules))
            # mock scores are monotonically decreasing => already ranked
            scores = [m.score for m in molecules]
            self.assertEqual(scores, sorted(scores, reverse=True))

    def test_remote_dry_run_writes_script_without_submitting(self) -> None:
        # slurm_remote with allow_submit=False must write the SLURM script and
        # return mock molecules without any network access.
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_with_saturn(
                {
                    "work_dir": tmp,
                    "objective": "Generate binders.",
                    "run_mode": "slurm_remote",
                    "allow_submit": False,
                }
            )
            self.assertTrue(result.ok)
            self.assertTrue(result.data["mock"])
            self.assertTrue((Path(tmp) / "saturn_job.slurm").exists())
            self.assertIn("remote_dry_run", result.metadata)

    def test_build_config_remote_base_uses_absolute_paths(self) -> None:
        config = build_saturn_config(
            SaturnGenerationInput(work_dir="unused", remote_prior_checkpoint="/home/u/prior.ckpt"),
            remote_base="/scratch/u/hackathon_agents/saturn/job",
        )
        self.assertEqual(config["logging"]["logging_path"], "/scratch/u/hackathon_agents/saturn/job/saturn_log")
        rl = config["goal_directed_generation"]["reinforcement_learning"]
        self.assertEqual(rl["prior"], "/home/u/prior.ckpt")

    def test_render_saturn_slurm_script(self) -> None:
        from hackathon_agents.tools.saturn_tools import render_saturn_slurm_script

        parsed = SaturnGenerationInput(work_dir="unused", partition="gpu_h100", remote_saturn_python="/opt/py")
        script = render_saturn_slurm_script(
            parsed, "/scratch/u/job/saturn_config.json", "/home/u/saturn", account="proj1"
        )
        self.assertIn("#SBATCH --partition=gpu_h100", script)
        self.assertIn("#SBATCH --account=proj1", script)
        self.assertIn("cd /home/u/saturn", script)
        self.assertIn("/opt/py saturn.py /scratch/u/job/saturn_config.json", script)

    def test_check_availability_reports_missing_repo(self) -> None:
        result = check_saturn_availability(saturn_repo="/nonexistent/saturn", saturn_python="python")
        self.assertTrue(result.ok)
        self.assertFalse(result.data["available"])
        self.assertFalse(result.data["repo_ok"])

    def test_build_config_supports_advanced_parameters(self) -> None:
        config = build_saturn_config(
            SaturnGenerationInput(
                work_dir="unused",
                seed_smiles=["CCO", "CCN"],
                model_architecture="transformer",
                beam_enumeration=True,
                hallucinated_memory=True,
                diversity_bucket_size=15,
                diversity_min_score=0.6,
            )
        )
        self.assertEqual(config["model_architecture"]["name"], "transformer")
        self.assertEqual(config["goal_directed_generation"]["experience_replay"]["smiles"], ["CCO", "CCN"])
        self.assertEqual(config["goal_directed_generation"]["diversity_filter"]["bucket_size"], 15)
        self.assertEqual(config["goal_directed_generation"]["diversity_filter"]["minscore"], 0.6)
        self.assertTrue(config["goal_directed_generation"]["beam_enumeration"]["use_beam_enumeration"])
        self.assertTrue(config["goal_directed_generation"]["hallucinated_memory"]["use_hallucinated_memory"])

    def test_chemist_warm_starts_saturn_when_candidates_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = DiscoveryStatePayload(
                original_user_request="Refine existing hits.",
                run_dir=tmp,
                candidate_molecules=[MoleculeRecord(smiles="CC(C)Cc1ccc(C(C)C(=O)O)cc1", name="ibuprofen")],
                metadata={"saturn": {"oracle": [{"name": "qed"}], "run": False, "max_return": 3}},
                requested_next_actions=["improve_candidates"],
            )
            state = chemist.run(state)
            self.assertEqual(len(state.candidate_molecules), 3)
            # Verify the warm-start message is in the message trail
            self.assertTrue(any("warm-starting Saturn experience replay memory" in msg for msg in state.messages))

    def test_chemist_seeds_from_saturn_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = DiscoveryStatePayload(
                original_user_request="Find candidates for reaction X",
                run_dir=tmp,
                metadata={"saturn": {"oracle": [{"name": "qed"}], "run": False, "max_return": 4}},
            )
            state = chemist.run(state)
            self.assertEqual(len(state.candidate_molecules), 4)
            self.assertTrue(all(c.source.startswith("saturn") for c in state.candidate_molecules))
            tool_names = [record.tool_name for record in state.tool_results]
            self.assertIn("saturn.generate", tool_names)

    def test_chemist_keeps_default_behavior_without_saturn(self) -> None:
        state = DiscoveryStatePayload(original_user_request="Find candidates")
        # The chemist alone (no planner) does not auto-seed Saturn metadata.
        state = chemist.run(state)
        self.assertTrue(state.candidate_molecules)
        self.assertTrue(all(c.source == "example_seed" for c in state.candidate_molecules))


class SaturnTier1GatingTests(unittest.TestCase):
    """Saturn should be config-gated like xTB/ORCA, with no human input."""

    def test_planner_sets_default_oracle(self) -> None:
        state = DiscoveryStatePayload(original_user_request="Design soluble inhibitors")
        state = planner.run(state)
        self.assertIn("saturn", state.metadata)
        oracle_names = [c["name"] for c in state.metadata["saturn"]["oracle"]]
        self.assertEqual(oracle_names, ["qed", "sa"])
        self.assertEqual(state.metadata["saturn_source"], "planner_default")
        # Default config must be valid for the Saturn tool schema.
        SaturnGenerationInput.model_validate({**state.metadata["saturn"], "work_dir": "x"})

    def test_planner_does_not_overwrite_existing_oracle(self) -> None:
        state = DiscoveryStatePayload(
            original_user_request="x",
            metadata={"saturn": {"oracle": [{"name": "docking"}], "run": False}},
        )
        state = planner.run(state)
        names = [c["name"] for c in state.metadata["saturn"]["oracle"]]
        self.assertEqual(names, ["docking"])

    def test_graph_uses_saturn_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_with_saturn(enabled=True)
            state = DiscoveryStatePayload(
                original_user_request="Find candidates",
                run_dir=tmp,
                run_mode=config.run_mode,
            )
            final = build_graph(config).invoke(state)
            sources = {c.source for c in final.candidate_molecules}
            self.assertTrue(any(s.startswith("saturn") for s in sources))
            tool_names = [r.tool_name for r in final.tool_results]
            self.assertIn("saturn.generate", tool_names)

    def test_graph_falls_back_to_seeds_when_saturn_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_with_saturn(enabled=False)
            state = DiscoveryStatePayload(
                original_user_request="Find candidates",
                run_dir=tmp,
                run_mode=config.run_mode,
            )
            final = build_graph(config).invoke(state)
            self.assertTrue(final.candidate_molecules)
            # No Saturn-sourced molecules; chemist used its deterministic seeds
            # (and possibly refinement seeds on later bounded passes).
            self.assertFalse(any(c.source.startswith("saturn") for c in final.candidate_molecules))
            tool_names = [r.tool_name for r in final.tool_results]
            self.assertNotIn("saturn.generate", tool_names)
            self.assertEqual(final.metadata.get("saturn_source"), "disabled_by_config")


if __name__ == "__main__":
    unittest.main()
