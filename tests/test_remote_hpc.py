from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.tools import remote_hpc
from hackathon_agents.tools.remote_hpc import (
    RemoteHPCClient,
    RemoteHPCConfig,
    RemoteJobSpec,
    make_remote_job_dir,
    submit_and_wait,
)


# --------------------------------------------------------------------------- #
# Fake Paramiko (records commands + file transfers; no network)
# --------------------------------------------------------------------------- #
class _FakeChannel:
    def __init__(self, code: int):
        self._code = code

    def recv_exit_status(self) -> int:
        return self._code


class _FakeStream:
    def __init__(self, data: str, channel: _FakeChannel | None = None):
        self._data = data.encode("utf-8")
        self.channel = channel

    def read(self) -> bytes:
        return self._data


class _FakeSFTP:
    def __init__(self):
        self.puts: list[tuple[str, str]] = []
        self.gets: list[tuple[str, str]] = []

    def put(self, local: str, remote: str) -> None:
        self.puts.append((str(local), remote))

    def get(self, remote: str, local: str) -> None:
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        # Simulate a downloaded artifact so callers see a real file.
        Path(local).write_text("smiles,total_score\nCCO,0.91\n", encoding="utf-8")
        self.gets.append((remote, str(local)))

    def close(self) -> None:
        pass


class _FakeSSHClient:
    def __init__(self, handler):
        self._handler = handler
        self.commands: list[str] = []
        self.sftp = _FakeSFTP()
        self.connect_kwargs: dict | None = None

    def set_missing_host_key_policy(self, policy) -> None:
        pass

    def connect(self, **kwargs) -> None:
        self.connect_kwargs = kwargs

    def open_sftp(self) -> _FakeSFTP:
        return self.sftp

    def exec_command(self, command: str, timeout: int | None = None):
        self.commands.append(command)
        code, out, err = self._handler(command)
        return None, _FakeStream(out, _FakeChannel(code)), _FakeStream(err)

    def close(self) -> None:
        pass


def _fake_paramiko(handler):
    """Build a fake ``paramiko`` module namespace around a command handler."""
    holder: dict[str, _FakeSSHClient] = {}

    class _SSHClient(_FakeSSHClient):
        def __init__(self):
            super().__init__(handler)
            holder["client"] = self

    class _AutoAddPolicy:
        pass

    ns = type("paramiko", (), {})()
    ns.SSHClient = _SSHClient
    ns.AutoAddPolicy = _AutoAddPolicy
    return ns, holder


def _default_handler(command: str):
    if "mkdir -p" in command:
        return 0, "", ""
    if "sbatch" in command:
        return 0, "Submitted batch job 987654\n", ""
    if command.startswith("squeue") or " squeue" in command:
        return 0, "", ""  # not in queue -> falls back to sacct
    if command.startswith("sacct") or " sacct" in command:
        return 0, "COMPLETED\n", ""
    if "find . -type f" in command:
        return 0, "./output/pred.pdb\n./output/confidence_model_0.json\n./slurm-987654.out\n", ""
    return 0, "ok\n", ""


class RemoteHPCConfigTests(unittest.TestCase):
    def test_from_env_parses_and_defaults(self) -> None:
        env = {
            "HPC_HOST": "snellius.surf.nl",
            "HPC_USER": "alice",
            "HPC_PORT": "2222",
            "SLURM_ACCOUNT": "proj123",
            "SLURM_GPUS": "2",
            "HPC_SCRATCH_PATH": "/scratch/alice",
        }
        cfg = RemoteHPCConfig.from_env(env)
        self.assertTrue(cfg.is_configured)
        self.assertEqual(cfg.port, 2222)
        self.assertEqual(cfg.account, "proj123")
        self.assertEqual(cfg.gpus_per_node, 2)
        self.assertEqual(cfg.base_dir, "/scratch/alice")

    def test_not_configured_without_host_user(self) -> None:
        self.assertFalse(RemoteHPCConfig.from_env({}).is_configured)


class SubmitAndWaitTests(unittest.TestCase):
    def _client(self, handler, monkeypatch_target) -> RemoteHPCClient:
        cfg = RemoteHPCConfig(host="snellius.surf.nl", user="alice", scratch_path="/scratch/alice")
        return RemoteHPCClient(cfg)

    def test_full_cycle_stages_submits_polls_downloads(self) -> None:
        ns, holder = _fake_paramiko(_default_handler)
        original = remote_hpc._import_paramiko
        remote_hpc._import_paramiko = lambda: ns
        try:
            cfg = RemoteHPCConfig(host="snellius.surf.nl", user="alice", scratch_path="/scratch/alice")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                local_yaml = tmp_path / "input.yaml"
                local_yaml.write_text("id: job\n", encoding="utf-8")
                local_script = tmp_path / "job.slurm"
                local_script.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
                out_dir = tmp_path / "out"

                spec = RemoteJobSpec(
                    tool="boltz",
                    job_name="job",
                    input_files=[(local_yaml, "input.yaml"), (local_script, "job.slurm")],
                    script_name="job.slurm",
                    output_patterns=["output/**"],
                    local_output_dir=out_dir,
                    remote_job_dir="/scratch/alice/hackathon_agents/boltz/job",
                )
                with RemoteHPCClient(cfg) as client:
                    result = submit_and_wait(client, spec, timeout=60, poll_interval=1)

                self.assertEqual(result.job_id, "987654")
                self.assertEqual(result.state, "completed")
                self.assertTrue(result.ok)
                # Both inputs were uploaded into the remote job dir.
                fake = holder["client"]
                uploaded_remote = {r for _, r in fake.sftp.puts}
                self.assertIn("/scratch/alice/hackathon_agents/boltz/job/input.yaml", uploaded_remote)
                self.assertIn("/scratch/alice/hackathon_agents/boltz/job/job.slurm", uploaded_remote)
                # Outputs (+ slurm log) were downloaded locally.
                self.assertTrue(result.downloaded_files)
                self.assertTrue((out_dir / "output" / "pred.pdb").exists())
        finally:
            remote_hpc._import_paramiko = original

    def test_key_auth_kwargs(self) -> None:
        ns, holder = _fake_paramiko(_default_handler)
        original = remote_hpc._import_paramiko
        remote_hpc._import_paramiko = lambda: ns
        try:
            cfg = RemoteHPCConfig(host="h", user="u", key_path="~/.ssh/id_ed25519")
            with RemoteHPCClient(cfg):
                pass
            self.assertIn("key_filename", holder["client"].connect_kwargs)
        finally:
            remote_hpc._import_paramiko = original


class HelperTests(unittest.TestCase):
    def test_make_remote_job_dir_under_base(self) -> None:
        cfg = RemoteHPCConfig(host="h", user="u", scratch_path="/scratch/u")
        path = make_remote_job_dir(cfg, "saturn", "saturn-0")
        self.assertTrue(path.startswith("/scratch/u/hackathon_agents/saturn/saturn-0_"))


if __name__ == "__main__":
    unittest.main()
