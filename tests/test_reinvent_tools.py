from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.agents import chemist
from hackathon_agents.config import AppConfig, RunMode, ToolConfig
from hackathon_agents.graph import build_graph
from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.reinvent_tools import (
    ReinventInput,
    ScoringComponent,
    build_reinvent_config,
    check_reinvent_availability,
    generate_with_reinvent,
    reinvent_records,
    render_reinvent_slurm_script,
    _parse_generated_molecules,
)


def _config_with_reinvent(enabled: bool, run_mode: RunMode = RunMode.CHEAP) -> AppConfig:
    return AppConfig(
        config_dir=Path("configs"),
        run_mode=run_mode,
        models={},
        agents={},
        tools={"reinvent": ToolConfig(enabled=enabled, enabled_modes=[RunMode.FULL, RunMode.CHEAP])},
    )


class ReinventConfigTests(unittest.TestCase):
    def test_build_sampling_config_de_novo(self) -> None:
        config = build_reinvent_config(
            ReinventInput(work_dir="unused", run_type="sampling", num_smiles=64)
        )
        self.assertEqual(config["run_type"], "sampling")
        params = config["parameters"]
        self.assertEqual(params["model_file"], ".reinvent")
        self.assertEqual(params["num_smiles"], 64)
        # De novo Reinvent does not use an input SMILES file.
        self.assertNotIn("smiles_file", params)
        self.assertTrue(params["output_file"].endswith("sampling.csv"))

    def test_build_sampling_config_libinvent_uses_smiles_file(self) -> None:
        config = build_reinvent_config(
            ReinventInput(
                work_dir="unused",
                run_type="sampling",
                generator_type="libinvent",
                input_smiles=["[*:0]Cc1ccccc1[*:1]"],
            )
        )
        self.assertEqual(config["parameters"]["model_file"], ".libinvent")
        self.assertIn("smiles_file", config["parameters"])
        self.assertTrue(config["parameters"]["smiles_file"].endswith("reinvent_inputs.smi"))

    def test_build_staged_learning_config_scoring_nesting(self) -> None:
        config = build_reinvent_config(
            ReinventInput(
                work_dir="unused",
                run_type="staged_learning",
                sigma=100.0,
                max_steps=50,
                scoring=[
                    ScoringComponent(component_type="QED", endpoints=[{"name": "QED", "weight": 0.5}]),
                    ScoringComponent(
                        component_type="MolecularWeight",
                        endpoints=[{"name": "MW", "weight": 0.5, "transform": {"type": "double_sigmoid", "high": 500.0, "low": 200.0}}],
                    ),
                ],
            )
        )
        self.assertEqual(config["run_type"], "staged_learning")
        self.assertEqual(config["parameters"]["prior_file"], ".reinvent")
        self.assertEqual(config["parameters"]["agent_file"], ".reinvent")
        self.assertEqual(config["learning_strategy"]["sigma"], 100.0)
        stage = config["stage"][0]
        self.assertEqual(stage["max_steps"], 50)
        components = stage["scoring"]["component"]
        self.assertEqual(list(components[0].keys()), ["QED"])
        self.assertEqual(components[0]["QED"]["endpoint"][0]["name"], "QED")
        self.assertEqual(components[1]["MolecularWeight"]["endpoint"][0]["transform"]["type"], "double_sigmoid")
        self.assertIn("diversity_filter", config)

    def test_build_config_remote_base_uses_absolute_paths(self) -> None:
        config = build_reinvent_config(
            ReinventInput(work_dir="unused", run_type="staged_learning"),
            remote_base="/scratch/u/hackathon_agents/reinvent/job",
        )
        self.assertTrue(config["tb_logdir"].startswith("/scratch/u/hackathon_agents/reinvent/job"))
        self.assertTrue(config["parameters"]["summary_csv_prefix"].startswith("/scratch/u/hackathon_agents/reinvent/job"))


class ReinventRunTests(unittest.TestCase):
    def test_generate_writes_config_and_returns_mock_molecules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_with_reinvent(
                {
                    "work_dir": tmp,
                    "objective": "Design soluble kinase inhibitors.",
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
            self.assertEqual(config["run_type"], "sampling")
            molecules = reinvent_records(result.data)
            self.assertEqual(len(molecules), 5)
            self.assertTrue(all(isinstance(m, MoleculeRecord) for m in molecules))
            self.assertTrue(all(m.source == "reinvent_mock" for m in molecules))
            scores = [m.score for m in molecules]
            self.assertEqual(scores, sorted(scores, reverse=True))

    def test_generate_writes_smiles_file_for_libinvent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_with_reinvent(
                {
                    "work_dir": tmp,
                    "run": False,
                    "generator_type": "libinvent",
                    "input_smiles": ["[*:0]Cc1ccccc1[*:1]", "[*:0]c1ccncc1[*:1]"],
                }
            )
            self.assertTrue(result.ok)
            smiles_file = Path(tmp) / "reinvent_inputs.smi"
            self.assertTrue(smiles_file.exists())
            lines = smiles_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "[*:0]Cc1ccccc1[*:1]")

    def test_remote_dry_run_writes_script_without_submitting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_with_reinvent(
                {
                    "work_dir": tmp,
                    "objective": "Generate binders.",
                    "run_mode": "slurm_remote",
                    "allow_submit": False,
                }
            )
            self.assertTrue(result.ok)
            self.assertTrue(result.data["mock"])
            self.assertTrue((Path(tmp) / "reinvent_job.slurm").exists())
            self.assertIn("remote_dry_run", result.metadata)

    def test_render_slurm_script(self) -> None:
        parsed = ReinventInput(
            work_dir="unused",
            partition="gpu_h100",
            remote_reinvent_executable="/opt/reinvent",
            remote_prior_base="/home/u/priors",
        )
        script = render_reinvent_slurm_script(
            parsed, "/scratch/u/job/reinvent_config.json", account="proj1"
        )
        self.assertIn("#SBATCH --partition=gpu_h100", script)
        self.assertIn("#SBATCH --account=proj1", script)
        self.assertIn("export REINVENT_PRIOR_BASE=/home/u/priors", script)
        self.assertIn("/opt/reinvent -f json", script)
        self.assertIn("/scratch/u/job/reinvent_config.json", script)

    def test_check_availability_reports_missing_executable(self) -> None:
        result = check_reinvent_availability(
            reinvent_executable="/nonexistent/reinvent", reinvent_python="/nonexistent/python"
        )
        self.assertTrue(result.ok)
        self.assertFalse(result.data["available"])

    def test_parse_sampling_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "sampling.csv").write_text(
                "SMILES,SMILES_state,NLL\n"
                "CCO,VALID,2.45\n"
                "c1ccccc1C,VALID,3.12\n"
                "badsmiles,INVALID,9.99\n",
                encoding="utf-8",
            )
            parsed = ReinventInput(work_dir=tmp, run_type="sampling", max_return=10)
            molecules = _parse_generated_molecules(parsed, work_dir)
            self.assertEqual(len(molecules), 2)  # invalid dropped
            # Ranked by ascending NLL (lower = better) when no score column.
            self.assertEqual(molecules[0].smiles, "CCO")
            self.assertEqual(molecules[0].metadata["nll"], 2.45)

    def test_parse_rl_summary_csv_ranks_by_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "rl_output_1.csv").write_text(
                "SMILES,Score,NLL\n"
                "CCO,0.42,2.0\n"
                "c1ccccc1,0.88,3.0\n",
                encoding="utf-8",
            )
            parsed = ReinventInput(work_dir=tmp, run_type="staged_learning", max_return=10)
            molecules = _parse_generated_molecules(parsed, work_dir)
            self.assertEqual(molecules[0].smiles, "c1ccccc1")  # highest score first
            self.assertEqual(molecules[0].score, 0.88)


class ReinventChemistTests(unittest.TestCase):
    def test_chemist_seeds_from_reinvent_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = DiscoveryStatePayload(
                original_user_request="Generate de novo candidates",
                run_dir=tmp,
                metadata={"reinvent": {"run": False, "max_return": 4}},
            )
            state = chemist.run(state)
            self.assertEqual(len(state.candidate_molecules), 4)
            self.assertTrue(all(c.source.startswith("reinvent") for c in state.candidate_molecules))
            tool_names = [record.tool_name for record in state.tool_results]
            self.assertIn("reinvent.generate", tool_names)

    def test_chemist_default_behavior_without_reinvent(self) -> None:
        state = DiscoveryStatePayload(original_user_request="Find candidates")
        state = chemist.run(state)
        self.assertTrue(state.candidate_molecules)
        self.assertTrue(all(c.source == "example_seed" for c in state.candidate_molecules))


class ReinventGatingTests(unittest.TestCase):
    def test_graph_uses_reinvent_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_with_reinvent(enabled=True)
            state = DiscoveryStatePayload(
                original_user_request="Find candidates",
                run_dir=tmp,
                run_mode=config.run_mode,
                metadata={"reinvent": {"run": False, "max_return": 3}},
            )
            final = build_graph(config).invoke(state)
            sources = {c.source for c in final.candidate_molecules}
            self.assertTrue(any(s.startswith("reinvent") for s in sources))
            tool_names = [r.tool_name for r in final.tool_results]
            self.assertIn("reinvent.generate", tool_names)

    def test_graph_disables_reinvent_when_config_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_with_reinvent(enabled=False)
            state = DiscoveryStatePayload(
                original_user_request="Find candidates",
                run_dir=tmp,
                run_mode=config.run_mode,
                metadata={"reinvent": {"run": False, "max_return": 3}},
            )
            final = build_graph(config).invoke(state)
            self.assertFalse(any(c.source.startswith("reinvent") for c in final.candidate_molecules))
            tool_names = [r.tool_name for r in final.tool_results]
            self.assertNotIn("reinvent.generate", tool_names)
            self.assertEqual(final.metadata.get("reinvent_source"), "disabled_by_config")


if __name__ == "__main__":
    unittest.main()
