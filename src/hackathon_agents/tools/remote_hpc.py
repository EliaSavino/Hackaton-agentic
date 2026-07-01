"""Clean-room SSH/SLURM remote execution layer for Snellius (and any SLURM cluster).

This module lets the workbench run heavy tools (Boltz-2, Saturn) on a remote HPC
cluster **from a laptop**: it stages input files over SFTP, submits a batch job
with ``sbatch``, polls ``squeue``/``sacct`` until the job finishes, and downloads
the outputs back for parsing.

It is a self-contained reimplementation built directly on Paramiko. It does not
import or depend on any external scheduler/bot project.

Paramiko is an *optional* dependency (``pip install 'hackathon-agents[hpc]'``). It
is imported lazily so that mock/offline code paths keep working without it.

Typical use::

    cfg = RemoteHPCConfig.from_env()
    if cfg.is_configured:
        with RemoteHPCClient(cfg) as client:
            result = submit_and_wait(
                client,
                RemoteJobSpec(
                    tool="boltz",
                    job_name="boltz-abcd",
                    input_files=[(local_yaml, "input.yaml"), (local_script, "job.slurm")],
                    script_name="job.slurm",
                    output_patterns=["output/**", "*.pdb"],
                    local_output_dir=work_dir / "output",
                ),
                timeout=1800,
            )
"""

from __future__ import annotations

import fnmatch
import os
import posixpath
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Optional Paramiko import
# --------------------------------------------------------------------------- #
def _import_paramiko():
    try:
        import paramiko  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise RuntimeError(
            "Paramiko is required for remote HPC submission but is not installed. "
            "Install it with: pip install 'hackathon-agents[hpc]' (or pip install paramiko)."
        ) from exc
    return paramiko


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
class RemoteHPCConfig(BaseModel):
    """Connection + SLURM defaults for a remote cluster, sourced from the env.

    Field names map onto the ``HPC_*`` / ``SLURM_*`` variables documented in
    ``.env.example``. Authentication prefers an SSH key (``key_path``); a
    ``password`` is used as a fallback when no key is provided.
    """

    host: str = ""
    user: str = ""
    port: int = 22
    key_path: str | None = None
    password: str | None = None
    home: str = "~"
    scratch_path: str | None = None

    # SLURM defaults (used when a job spec does not override them).
    account: str | None = None
    partition: str = "gpu_a100"
    qos: str | None = None
    time_limit: str = "02:00:00"
    gpus_per_node: int = 1
    cpus_per_task: int = 4
    mem: str = "32G"
    submit_command: str = "sbatch"

    # Polling.
    poll_interval_seconds: int = 30

    model_config = ConfigDict(extra="forbid")

    @property
    def is_configured(self) -> bool:
        """True when enough is set to attempt a connection."""
        return bool(self.host and self.user)

    @property
    def base_dir(self) -> str:
        """Base directory on the cluster under which job dirs are created."""
        return self.scratch_path or self.home or "~"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "RemoteHPCConfig":
        """Build a config from environment variables (``os.environ`` by default)."""
        env = env if env is not None else os.environ

        def _get(name: str, default: str | None = None) -> str | None:
            value = env.get(name)
            if value is None:
                return default
            value = value.strip()
            return value or default

        def _int(name: str, default: int) -> int:
            raw = _get(name)
            try:
                return int(raw) if raw is not None else default
            except ValueError:
                return default

        return cls(
            host=_get("HPC_HOST", "") or "",
            user=_get("HPC_USER", "") or "",
            port=_int("HPC_PORT", 22),
            key_path=_get("HPC_KEY_PATH"),
            password=_get("HPC_PASSWORD"),
            home=_get("HPC_HOME", "~") or "~",
            scratch_path=_get("HPC_SCRATCH_PATH"),
            account=_get("SLURM_ACCOUNT"),
            partition=_get("SLURM_PARTITION", "gpu_a100") or "gpu_a100",
            qos=_get("SLURM_QOS"),
            time_limit=_get("SLURM_TIME", "02:00:00") or "02:00:00",
            gpus_per_node=_int("SLURM_GPUS", 1),
            cpus_per_task=_int("SLURM_CPUS_PER_TASK", 4),
            mem=_get("SLURM_MEM", "32G") or "32G",
            submit_command=_get("SLURM_SUBMIT_COMMAND", "sbatch") or "sbatch",
            poll_interval_seconds=_int("HPC_POLL_INTERVAL", 30),
        )


# --------------------------------------------------------------------------- #
# Job specification + run result
# --------------------------------------------------------------------------- #
@dataclass
class RemoteJobSpec:
    """Everything needed to stage, submit, and collect one remote SLURM job."""

    tool: str
    job_name: str
    # (local_path, remote_filename) pairs uploaded into the remote job dir.
    input_files: list[tuple[str | Path, str]]
    # Name of the uploaded SBATCH script to submit (must be one of input_files).
    script_name: str
    # fnmatch-style patterns (relative to the remote job dir) to download back.
    output_patterns: list[str]
    # Local directory to download outputs into.
    local_output_dir: str | Path
    # Optional explicit remote job dir; auto-generated under base_dir when None.
    remote_job_dir: str | None = None


@dataclass
class RemoteRunResult:
    """Outcome of a remote submit-wait-fetch cycle."""

    job_id: str
    state: str  # completed, failed, timeout, unknown
    remote_job_dir: str
    downloaded_files: list[str] = field(default_factory=list)
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.state == "completed"


# --------------------------------------------------------------------------- #
# SSH client
# --------------------------------------------------------------------------- #
# SLURM state -> normalized bucket.
_ACTIVE_STATES = {"PENDING", "CONFIGURING", "RUNNING", "COMPLETING", "RESIZING", "REQUEUED", "SUSPENDED"}
_SUCCESS_STATES = {"COMPLETED"}
_FAILURE_STATES = {"FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "BOOT_FAIL", "DEADLINE", "PREEMPTED"}


class RemoteHPCClient:
    """Thin SSH/SFTP + SLURM wrapper around Paramiko."""

    def __init__(self, config: RemoteHPCConfig):
        self.config = config
        self._client: Any = None
        self._sftp: Any = None
        self._home: str | None = None

    # -- path resolution -------------------------------------------------- #
    def resolve_home(self) -> str:
        """Return the absolute remote ``$HOME`` (cached)."""
        if self._home is None:
            code, out, _ = self.run("echo $HOME")
            self._home = out.strip() if code == 0 and out.strip() else "."
        return self._home

    def resolve_path(self, path: str) -> str:
        """Expand a leading ``~`` to the absolute remote home.

        SFTP (and Python ``open`` in remote jobs) does not expand ``~``, so any
        remote path handed to SFTP or embedded in a config must be absolute.
        """
        if path == "~":
            return self.resolve_home()
        if path.startswith("~/"):
            return posixpath.join(self.resolve_home(), path[2:])
        return path

    # -- lifecycle -------------------------------------------------------- #
    def connect(self) -> "RemoteHPCClient":
        if self._client is not None:
            return self
        if not self.config.is_configured:
            raise RuntimeError("RemoteHPCConfig is not configured (HPC_HOST/HPC_USER missing).")
        paramiko = _import_paramiko()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs: dict[str, Any] = {
            "hostname": self.config.host,
            "port": self.config.port,
            "username": self.config.user,
            "timeout": 30,
            "allow_agent": True,
            "look_for_keys": True,
        }
        if self.config.key_path:
            connect_kwargs["key_filename"] = os.path.expanduser(self.config.key_path)
        if self.config.password:
            connect_kwargs["password"] = self.config.password
            # Force password auth when no explicit key is configured, so we do
            # not silently fall through to an SSH agent / discovered key.
            if not self.config.key_path:
                connect_kwargs["look_for_keys"] = False
                connect_kwargs["allow_agent"] = False
        client.connect(**connect_kwargs)
        self._client = client
        self._sftp = client.open_sftp()
        return self

    def close(self) -> None:
        if self._sftp is not None:
            try:
                self._sftp.close()
            finally:
                self._sftp = None
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def __enter__(self) -> "RemoteHPCClient":
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- primitives ------------------------------------------------------- #
    def run(self, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """Run a remote command; return (returncode, stdout, stderr)."""
        if self._client is None:
            self.connect()
        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return code, out, err

    def makedirs(self, remote_dir: str) -> None:
        remote_dir = self.resolve_path(remote_dir)
        code, _, err = self.run(f"mkdir -p {_shquote(remote_dir)}")
        if code != 0:
            raise RuntimeError(f"Failed to create remote dir {remote_dir}: {err.strip()}")

    def upload(self, local_path: str | Path, remote_path: str) -> None:
        if self._sftp is None:
            self.connect()
        self._sftp.put(str(local_path), self.resolve_path(remote_path))

    def download(self, remote_path: str, local_path: str | Path) -> None:
        if self._sftp is None:
            self.connect()
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self._sftp.get(self.resolve_path(remote_path), str(local_path))

    def list_files(self, remote_dir: str) -> list[str]:
        """List all files under ``remote_dir`` as paths relative to it."""
        remote_dir = self.resolve_path(remote_dir)
        code, out, _ = self.run(f"cd {_shquote(remote_dir)} && find . -type f")
        if code != 0:
            return []
        files = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("./"):
                line = line[2:]
            if line:
                files.append(line)
        return files

    def download_matching(
        self,
        remote_dir: str,
        patterns: list[str],
        local_dir: str | Path,
    ) -> list[str]:
        """Download every remote file (relative to ``remote_dir``) that matches
        any of ``patterns`` (fnmatch-style; ``**`` treated as ``*``)."""
        local_dir = Path(local_dir)
        downloaded: list[str] = []
        normalized = [p.replace("**", "*") for p in patterns]
        for rel in self.list_files(remote_dir):
            if not any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(posixpath.basename(rel), pat) for pat in normalized):
                continue
            remote_path = posixpath.join(remote_dir, rel)
            local_path = local_dir / rel
            try:
                self.download(remote_path, local_path)
                downloaded.append(str(local_path))
            except OSError:
                continue
        return downloaded

    # -- SLURM ------------------------------------------------------------ #
    def submit(self, remote_script_path: str, remote_job_dir: str) -> str:
        """Submit a script with sbatch (from its job dir) and return the job id."""
        command = (
            f"cd {_shquote(self.resolve_path(remote_job_dir))} && "
            f"{self.config.submit_command} {_shquote(posixpath.basename(remote_script_path))}"
        )
        code, out, err = self.run(command)
        if code != 0:
            raise RuntimeError(f"sbatch failed (rc={code}): {err.strip() or out.strip()}")
        # sbatch prints "Submitted batch job 1234567"
        for token in out.split():
            if token.isdigit():
                return token
        raise RuntimeError(f"Could not parse job id from sbatch output: {out.strip()!r}")

    def status(self, job_id: str) -> str:
        """Return a normalized job state: pending/running/completed/failed/unknown."""
        code, out, _ = self.run(f"squeue -h -j {job_id} -o %T")
        state = out.strip().split("\n")[0].strip().upper() if out.strip() else ""
        if state:
            if state in _SUCCESS_STATES:
                return "completed"
            if state in _FAILURE_STATES:
                return "failed"
            if state in _ACTIVE_STATES:
                return "running" if state != "PENDING" else "pending"
            return "running"
        # Not in the queue anymore -> consult accounting for the final state.
        code, out, _ = self.run(f"sacct -j {job_id} -X -n -o State")
        final = out.strip().split("\n")[0].strip().upper() if out.strip() else ""
        # sacct states can carry suffixes like "CANCELLED by 12345".
        final = final.split()[0] if final else ""
        if final in _SUCCESS_STATES:
            return "completed"
        if final in _FAILURE_STATES:
            return "failed"
        if final in _ACTIVE_STATES:
            return "running"
        return "unknown"

    def wait(self, job_id: str, timeout: int, poll_interval: int | None = None) -> str:
        """Poll until the job leaves the active set or ``timeout`` elapses."""
        interval = poll_interval or self.config.poll_interval_seconds
        deadline = time.monotonic() + timeout
        last = "pending"
        while time.monotonic() < deadline:
            last = self.status(job_id)
            if last in {"completed", "failed", "unknown"}:
                return last
            time.sleep(max(1, interval))
        return "timeout"


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def submit_and_wait(
    client: RemoteHPCClient,
    spec: RemoteJobSpec,
    *,
    timeout: int,
    poll_interval: int | None = None,
) -> RemoteRunResult:
    """Stage → submit → wait → download for a single remote SLURM job."""
    remote_job_dir = spec.remote_job_dir or _default_job_dir(client.config, spec)
    client.makedirs(remote_job_dir)

    remote_script_path = ""
    for local_path, remote_name in spec.input_files:
        remote_path = posixpath.join(remote_job_dir, remote_name)
        client.upload(local_path, remote_path)
        if remote_name == spec.script_name:
            remote_script_path = remote_path
    if not remote_script_path:
        raise RuntimeError(f"script_name {spec.script_name!r} was not among input_files.")

    job_id = client.submit(remote_script_path, remote_job_dir)
    state = client.wait(job_id, timeout=timeout, poll_interval=poll_interval)

    # Always try to grab SLURM logs plus the requested output patterns.
    patterns = list(spec.output_patterns) + [f"slurm-{job_id}.out", f"slurm-{job_id}.err", "slurm-*.out", "slurm-*.err"]
    downloaded = client.download_matching(remote_job_dir, patterns, spec.local_output_dir)

    stdout_tail, stderr_tail = _read_slurm_logs(spec.local_output_dir, job_id)
    return RemoteRunResult(
        job_id=job_id,
        state=state,
        remote_job_dir=remote_job_dir,
        downloaded_files=downloaded,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
    )


def render_sbatch_directives(
    config: RemoteHPCConfig,
    *,
    job_name: str,
    partition: str | None = None,
    gpus_per_node: int | None = None,
    time_limit: str | None = None,
    cpus_per_task: int | None = None,
    mem: str | None = None,
    use_gpu: bool = True,
) -> list[str]:
    """Return a list of ``#SBATCH`` lines from config + overrides.

    Shared by the Boltz and Saturn SLURM script renderers so account/qos/partition
    handling stays consistent.
    """
    lines = [
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --partition={partition or config.partition}",
        f"#SBATCH --time={time_limit or config.time_limit}",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        f"#SBATCH --cpus-per-task={cpus_per_task or config.cpus_per_task}",
        f"#SBATCH --mem={mem or config.mem}",
        "#SBATCH --output=slurm-%j.out",
        "#SBATCH --error=slurm-%j.err",
    ]
    if use_gpu:
        lines.insert(3, f"#SBATCH --gpus-per-node={gpus_per_node or config.gpus_per_node}")
    if config.account:
        lines.append(f"#SBATCH --account={config.account}")
    if config.qos:
        lines.append(f"#SBATCH --qos={config.qos}")
    return lines


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _shquote(value: str) -> str:
    """Minimal POSIX shell quoting (paths may contain ~, so expand-friendly)."""
    if value.startswith("~"):
        # Leave a leading ~ unquoted so the remote shell expands it, quote the rest.
        head, _, tail = value.partition("/")
        return head + ("/" + _shquote(tail) if tail else "")
    if all(c.isalnum() or c in "-_./" for c in value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def make_remote_job_dir(config: RemoteHPCConfig, tool: str, job_name: str) -> str:
    """Deterministic-per-call isolated remote job directory under the base dir."""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    unique = f"{job_name}_{stamp}_{os.getpid()}"
    return posixpath.join(config.base_dir, "hackathon_agents", tool, unique)


def _default_job_dir(config: RemoteHPCConfig, spec: RemoteJobSpec) -> str:
    return make_remote_job_dir(config, spec.tool, spec.job_name)


def _read_slurm_logs(local_dir: str | Path, job_id: str) -> tuple[str, str]:
    local_dir = Path(local_dir)
    out_tail = err_tail = ""
    for path in sorted(local_dir.glob(f"slurm-{job_id}.out")) + sorted(local_dir.glob("slurm-*.out")):
        try:
            out_tail = path.read_text(encoding="utf-8", errors="replace")[-4000:]
            break
        except OSError:
            continue
    for path in sorted(local_dir.glob(f"slurm-{job_id}.err")) + sorted(local_dir.glob("slurm-*.err")):
        try:
            err_tail = path.read_text(encoding="utf-8", errors="replace")[-4000:]
            break
        except OSError:
            continue
    return out_tail, err_tail
