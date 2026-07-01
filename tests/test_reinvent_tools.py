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
        self.assertIn("#SBATCH --gpus-per-node=1", script)
        self.assertIn("#SBATCH --account=proj1", script)
        self.assertIn("export REINVENT_PRIOR_BASE=/home/u/priors", script)
        self.assertIn("/opt/reinvent -f json", script)
        self.assertIn("/scratch/u/job/reinvent_config.json", script)

    def test_render_slurm_script_cpu_partition_omits_gpu(self) -> None:
        # CPU partitions (rome/genoa) must NOT carry a --gpus-per-node directive.
        parsed = ReinventInput(
            work_dir="unused",
            partition="rome",
            gpus_per_node=0,
            cpus_per_task=32,
            mem="64G",
            device="cpu",
        )
        script = render_reinvent_slurm_script(parsed, "/scratch/u/job/reinvent_config.json")
        self.assertIn("#SBATCH --partition=rome", script)
        self.assertNotIn("gpus-per-node", script)
        self.assertIn("#SBATCH --cpus-per-task=32", script)
        self.assertIn("#SBATCH --mem=64G", script)
        self.assertIn("-d cpu", script)

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


class _SSHFakeSFTP:
    def __init__(self):
        self.puts: list[tuple[str, str]] = []

    def put(self, local: str, remote: str) -> None:
        self.puts.append((str(local), remote))

    def get(self, remote: str, local: str) -> None:
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        # Simulate a downloaded RL summary CSV the parser understands.
        Path(local).write_text("SMILES,Score,NLL\nO=C(NCC(=O)NCCO)CCO,0.81,2.0\n", encoding="utf-8")

    def close(self) -> None:
        pass


class _SSHFakeClient:
    def __init__(self, holder):
        self.sftp = _SSHFakeSFTP()
        self.commands: list[str] = []
        holder["client"] = self

    def set_missing_host_key_policy(self, policy) -> None:
        pass

    def connect(self, **kwargs) -> None:
        self.connect_kwargs = kwargs

    def open_sftp(self):
        return self.sftp

    def exec_command(self, command, timeout=None):
        self.commands.append(command)
        if command.strip() == "echo $HOME":
            out = "/workspace\n"
        elif "find . -type f" in command:
            out = "./rl_output_1.csv\n./reinvent.log\n"
        else:
            out = "ok\n"

        class _Chan:
            def recv_exit_status(self_inner):
                return 0

        class _Stream:
            def __init__(self_inner, data, chan=None):
                self_inner._d = data.encode()
                self_inner.channel = chan

            def read(self_inner):
                return self_inner._d

        return None, _Stream(out, _Chan()), _Stream("")

    def close(self) -> None:
        pass


class ReinventSSHTests(unittest.TestCase):
    def test_ssh_dry_run_when_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_with_reinvent(
                {"work_dir": tmp, "run_mode": "ssh_remote", "run": True, "generator_type": "linkinvent",
                 "input_smiles": ["O=C1C=CC(=O)N1CCCCCC(=O)*|*Nc1ccccc1"]}
            )
            self.assertTrue(result.ok)
            self.assertTrue(result.data["mock"])  # no ssh_host => mock
            self.assertIn("ssh_dry_run", result.metadata)
            self.assertTrue((Path(tmp) / "reinvent_config.json").exists())

    def test_ssh_runs_command_and_parses_output(self) -> None:
        from hackathon_agents.tools import remote_hpc

        holder: dict = {}

        class _Paramiko:
            AutoAddPolicy = type("AutoAddPolicy", (), {})

            class SSHClient(_SSHFakeClient):
                def __init__(self):
                    super().__init__(holder)

        original = remote_hpc._import_paramiko
        remote_hpc._import_paramiko = lambda: _Paramiko
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = generate_with_reinvent(
                    {
                        "work_dir": tmp,
                        "run_mode": "ssh_remote",
                        "run": True,
                        "generator_type": "linkinvent",
                        "input_smiles": ["O=C1C=CC(=O)N1CCCCCC(=O)*|*Nc1ccccc1"],
                        "ssh_host": "1.2.3.4",
                        "ssh_port": 40000,
                        "device": "cuda:0",
                        "remote_reinvent_executable": "/workspace/reinvent-venv/bin/reinvent",
                        "remote_prior_base": "/workspace/reinvent_priors",
                        "remote_workdir": "~/reinvent_runs",
                    }
                )
        finally:
            remote_hpc._import_paramiko = original

        self.assertTrue(result.ok, result.error)
        self.assertFalse(result.data["mock"])  # parsed a real linker
        fake = holder["client"]
        # ~ was expanded to the resolved $HOME (/workspace) for uploads.
        self.assertTrue(all("~" not in remote for _, remote in fake.sftp.puts))
        self.assertTrue(any(r.endswith("reinvent_config.json") for _, r in fake.sftp.puts))
        # The reinvent command ran on the GPU with cuda:0 and the prior base.
        run_cmds = [c for c in fake.commands if "reinvent" in c and "-f json" in c]
        self.assertTrue(run_cmds)
        self.assertIn("-d cuda:0", run_cmds[0])
        self.assertIn("REINVENT_PRIOR_BASE=/workspace/reinvent_priors", run_cmds[0])
        mols = reinvent_records(result.data)
        self.assertTrue(mols and mols[0].smiles == "O=C(NCC(=O)NCCO)CCO")
        # GPU device must NOT hide CUDA or cap threads.
        self.assertNotIn("CUDA_VISIBLE_DEVICES", run_cmds[0])
        self.assertNotIn("OMP_NUM_THREADS", run_cmds[0])

    def test_ssh_cpu_device_hides_cuda_and_caps_threads(self) -> None:
        from hackathon_agents.tools import remote_hpc

        holder: dict = {}

        class _Paramiko:
            AutoAddPolicy = type("AutoAddPolicy", (), {})

            class SSHClient(_SSHFakeClient):
                def __init__(self):
                    super().__init__(holder)

        original = remote_hpc._import_paramiko
        remote_hpc._import_paramiko = lambda: _Paramiko
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = generate_with_reinvent(
                    {
                        "work_dir": tmp,
                        "run_mode": "ssh_remote",
                        "run": True,
                        "generator_type": "linkinvent",
                        "input_smiles": ["O=C1C=CC(=O)N1CCCCCC(=O)*|*Nc1ccccc1"],
                        "ssh_host": "1.2.3.4",
                        "device": "cpu",
                        "remote_prior_base": "/workspace/reinvent_priors",
                    }
                )
        finally:
            remote_hpc._import_paramiko = original

        self.assertTrue(result.ok, result.error)
        fake = holder["client"]
        run_cmds = [c for c in fake.commands if "reinvent" in c and "-f json" in c]
        self.assertTrue(run_cmds)
        cmd = run_cmds[0]
        self.assertIn("-d cpu", cmd)
        # CUDA hidden so torch never probes a mismatched/old driver on CPU runs.
        self.assertIn("CUDA_VISIBLE_DEVICES=''", cmd)
        # Thread count capped (avoids many-core torch thrashing on the transformer).
        self.assertIn("OMP_NUM_THREADS=$T", cmd)
        self.assertIn("MKL_NUM_THREADS=$T", cmd)


if __name__ == "__main__":
    unittest.main()
