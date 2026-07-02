"""REINVENT4 generative molecular design tool.

This wraps the `MolecularAI/REINVENT4` framework
(https://github.com/MolecularAI/REINVENT4) so an agent can run de novo
generation, scaffold decoration (LibInvent), linker design (LinkInvent),
scaffold hopping (Mol2Mol) and goal-directed reinforcement learning
(``staged_learning``), and recover the generated SMILES as typed
``MoleculeRecord`` objects.

REINVENT4 is a heavy, GPU-oriented framework installed into its own Python
environment. It exposes a ``reinvent`` console script driven by a single config
file::

    reinvent [-f json] [-d cuda:0|cpu] [-l run.log] <config>

Because REINVENT cannot reliably be imported in-process from this workbench,
this tool follows the same pattern as the Saturn/xTB/ORCA/Boltz-2 wrappers:

1. Build a REINVENT-compatible **JSON** config from a small, typed,
   hackathon-friendly schema (REINVENT accepts JSON via ``-f json``, so we reuse
   the existing ``write_json`` helper — no TOML-writer dependency needed).
2. Optionally invoke ``reinvent`` as a subprocess (locally) or stage + submit it
   as a SLURM job on an HPC cluster.
3. Parse the generated SMILES from REINVENT's CSV output into
   ``MoleculeRecord`` objects.

When REINVENT is not installed/configured, or when ``run=False`` (the default),
the tool writes the config file and returns a deterministic **mock** set of
candidate molecules so the rest of the workbench stays testable offline.

Every code path returns a ``ToolResult``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.tools.base import error_result, ok_result
from hackathon_agents.tools.file_io import write_json


# Deterministic, drug-like SMILES used for the offline mock generator. These are
# only used when REINVENT is unavailable or when ``run=False``.
_MOCK_GENERATED_SMILES = [
    "CCOC(=O)c1ccc(N)cc1",
    "COc1ccc(CCN)cc1",
    "O=C(Nc1ccccc1)c1ccccc1",
    "CC(=O)Nc1ccc(O)cc1",
    "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "OC(=O)c1ccc(Cl)c(Cl)c1",
    "Cc1ccc(S(=O)(=O)N)cc1",
    "Clc1ccccc1Nc1ncccn1",
    "NC(=O)c1cccnc1",
    "COc1cc(CC(N)C(=O)O)ccc1O",
    "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
    "O=C1CCCN1c1ccccc1",
]


# Map a friendly generator type to REINVENT's built-in prior dot-name. These
# resolve to files under ``REINVENT_PRIOR_BASE`` (see REINVENT's prior_registry).
# ``pepinvent`` has no bundled dot-name, so a ``prior`` path must be supplied.
_DEFAULT_PRIORS: dict[str, str | None] = {
    "reinvent": ".reinvent",
    "libinvent": ".libinvent",
    "linkinvent": ".linkinvent",
    "mol2mol": ".m2m_scaffold",
    "pepinvent": None,
}

# Generators that consume an input SMILES file (scaffolds/warheads/inputs).
_NEEDS_SMILES_INPUT = {"libinvent", "linkinvent", "mol2mol", "pepinvent"}
# Generators that accept a sampling strategy knob.
_USES_SAMPLE_STRATEGY = {"mol2mol", "pepinvent"}


class ScoringComponent(BaseModel):
    """A single REINVENT scoring component (used in ``staged_learning``).

    ``component_type`` must match a REINVENT scoring component (e.g. ``"QED"``,
    ``"MolecularWeight"``, ``"TanimotoSimilarity"``, ``"CustomAlerts"``).
    ``endpoints`` is a list of endpoint dicts, each with ``name`` and optional
    ``weight``/``params``/``transform`` passed through to REINVENT unchanged.
    """

    component_type: str
    endpoints: list[dict[str, Any]] = Field(
        default_factory=lambda: [{"name": "endpoint", "weight": 1.0}]
    )

    model_config = ConfigDict(extra="allow")

    def to_reinvent(self) -> dict[str, Any]:
        return {self.component_type: {"endpoint": [dict(ep) for ep in self.endpoints]}}


class ReinventInput(BaseModel):
    """Inputs for a REINVENT4 sampling or staged-learning run.

    The defaults describe a small, fast configuration suitable for a hackathon.
    Set ``run=True`` and provide ``reinvent_executable`` (or ``reinvent_python``)
    plus ``prior_base`` to execute the real framework; otherwise the tool
    produces a config plus a deterministic mock result.
    """

    objective: str = "Generate candidate molecules with REINVENT4."
    work_dir: str
    run_type: Literal["sampling", "staged_learning"] = "sampling"
    seed: int = 0
    device: Literal["cuda:0", "cpu", "mps"] = "cpu"
    max_return: int = Field(default=25, ge=1, le=5000)
    config_filename: str = "reinvent_config.json"

    # --- Generator / prior --------------------------------------------------
    generator_type: Literal["reinvent", "libinvent", "linkinvent", "mol2mol", "pepinvent"] = "reinvent"
    prior: str | None = Field(
        default=None,
        description="REINVENT prior dot-name (e.g. '.reinvent') or a path. Defaults from generator_type.",
    )
    input_smiles: list[str] = Field(
        default_factory=list,
        description="Scaffolds (LibInvent), warheads (LinkInvent), or input compounds (Mol2Mol/Pepinvent).",
    )
    sample_strategy: Literal["multinomial", "beamsearch"] = "multinomial"

    # --- Sampling knobs -----------------------------------------------------
    num_smiles: int = Field(default=128, ge=1, le=100000)
    unique_molecules: bool = True
    randomize_smiles: bool = True

    # --- Staged-learning (RL) knobs -----------------------------------------
    batch_size: int = Field(default=64, ge=1, le=1024)
    max_steps: int = Field(default=100, ge=1, le=100000)
    min_steps: int = Field(default=25, ge=0, le=100000)
    max_score: float = Field(default=0.6, ge=0.0, le=1.0)
    sigma: float = Field(default=128.0, gt=0.0)
    learning_rate: float = Field(default=1e-4, gt=0.0)
    learning_strategy: Literal["dap"] = "dap"
    use_diversity_filter: bool = True
    diversity_filter_type: str = "IdenticalMurckoScaffold"
    diversity_bucket_size: int = Field(default=25, ge=1)
    diversity_min_score: float = Field(default=0.4, ge=0.0, le=1.0)
    scoring_aggregator: Literal["geometric_mean", "arithmetic_mean"] = "geometric_mean"
    scoring: list[ScoringComponent] = Field(
        default_factory=lambda: [ScoringComponent(component_type="QED", endpoints=[{"name": "QED", "weight": 1.0}])]
    )
    summary_csv_prefix: str = "rl_output"

    # --- Execution / environment -------------------------------------------
    run_mode: Literal["local", "slurm_remote", "ssh_remote"] = "local"
    reinvent_executable: str = "reinvent"  # console script from the REINVENT env
    reinvent_python: str = "python"  # interpreter from the REINVENT env (fallback probe)
    prior_base: str | None = None  # REINVENT_PRIOR_BASE for the subprocess
    timeout_seconds: int = Field(default=1800, ge=1)
    run: bool = False  # opt-in real execution; False => config + mock only

    # --- HPC / SLURM settings (only used if run_mode=slurm_remote) -----------
    allow_submit: bool = False  # opt-in remote submission gate
    partition: str = "gpu_a100"
    gpus_per_node: int = 1  # set to 0 for CPU-only partitions (rome/genoa)
    cpus_per_task: int = 4
    mem: str = "32G"
    time_limit: str = "02:00:00"
    poll_interval_seconds: int = 30
    remote_reinvent_executable: str = "reinvent"
    remote_prior_base: str | None = None
    # Shell lines that activate the REINVENT env inside the SLURM job.
    env_setup: str | None = None

    # --- Direct SSH execution (run_mode="ssh_remote"): a rented GPU box (RunPod,
    # Lambda, a bare VM) with no scheduler. reinvent runs as a command over SSH.
    ssh_host: str | None = None
    ssh_user: str = "root"
    ssh_port: int = 22
    ssh_key_path: str | None = None
    ssh_password: str | None = None
    remote_workdir: str = "~/reinvent_runs"

    model_config = ConfigDict(extra="forbid")


def check_reinvent_availability(
    reinvent_executable: str = "reinvent",
    reinvent_python: str = "python",
):
    """Report whether a usable ``reinvent`` executable or importable env exists."""

    executable = shutil.which(reinvent_executable) or (
        reinvent_executable if Path(reinvent_executable).exists() else None
    )
    python_path = shutil.which(reinvent_python) or (
        reinvent_python if Path(reinvent_python).exists() else None
    )
    import_ok = False
    if executable is None and python_path is not None:
        try:
            probe = subprocess.run(
                [python_path, "-c", "import reinvent"],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            import_ok = probe.returncode == 0
        except Exception:
            import_ok = False
    available = bool(executable) or import_ok
    return ok_result(
        {
            "available": available,
            "executable": executable,
            "python": python_path,
            "import_ok": import_ok,
            "reinvent_executable_requested": reinvent_executable,
        }
    )


def _resolve_prior(parsed: ReinventInput, *, remote: bool = False) -> str:
    """Resolve the prior/model reference (dot-name or path) for the config."""

    if parsed.prior:
        return parsed.prior
    default = _DEFAULT_PRIORS.get(parsed.generator_type)
    return default or ""


def build_reinvent_config(
    input_data: ReinventInput | dict[str, Any],
    *,
    remote_base: str | None = None,
) -> dict[str, Any]:
    """Render a REINVENT-compatible JSON/TOML config from the typed input.

    When ``remote_base`` is given (a POSIX path on the cluster), output/log paths
    are placed under it so the config is valid for a job that runs on the
    cluster.
    """

    parsed = _coerce(input_data)
    if remote_base is not None:
        base = remote_base
        join = lambda name: f"{base}/{name}"  # noqa: E731 - POSIX paths on cluster
    else:
        base = str(Path(parsed.work_dir))
        join = lambda name: str(Path(parsed.work_dir) / name)  # noqa: E731

    prior = _resolve_prior(parsed, remote=remote_base is not None)
    smiles_file = join("reinvent_inputs.smi") if parsed.generator_type in _NEEDS_SMILES_INPUT else None

    if parsed.run_type == "sampling":
        parameters: dict[str, Any] = {
            "model_file": prior,
            "output_file": join("sampling.csv"),
            "num_smiles": parsed.num_smiles,
            "unique_molecules": parsed.unique_molecules,
            "randomize_smiles": parsed.randomize_smiles,
        }
        if smiles_file:
            parameters["smiles_file"] = smiles_file
        if parsed.generator_type in _USES_SAMPLE_STRATEGY:
            parameters["sample_strategy"] = parsed.sample_strategy
        return {
            "run_type": "sampling",
            "device": parsed.device,
            "seed": parsed.seed,
            "parameters": parameters,
        }

    # staged_learning (reinforcement / curriculum learning)
    parameters = {
        "prior_file": prior,
        "agent_file": prior,
        "summary_csv_prefix": join(parsed.summary_csv_prefix),
        "batch_size": parsed.batch_size,
        "randomize_smiles": parsed.randomize_smiles,
        "use_checkpoint": False,
        "purge_memories": False,
    }
    if smiles_file:
        parameters["smiles_file"] = smiles_file
    if parsed.generator_type in _USES_SAMPLE_STRATEGY:
        parameters["sample_strategy"] = parsed.sample_strategy

    config: dict[str, Any] = {
        "run_type": "staged_learning",
        "device": parsed.device,
        "seed": parsed.seed,
        "tb_logdir": join("tb_logs"),
        "parameters": parameters,
        "learning_strategy": {
            "type": parsed.learning_strategy,
            "sigma": parsed.sigma,
            "rate": parsed.learning_rate,
        },
        "stage": [
            {
                "chkpt_file": join("stage1.chkpt"),
                "termination": "simple",
                "max_score": parsed.max_score,
                "min_steps": parsed.min_steps,
                "max_steps": parsed.max_steps,
                "scoring": {
                    "type": parsed.scoring_aggregator,
                    "component": [component.to_reinvent() for component in parsed.scoring],
                },
            }
        ],
    }
    if parsed.use_diversity_filter:
        config["diversity_filter"] = {
            "type": parsed.diversity_filter_type,
            "bucket_size": parsed.diversity_bucket_size,
            "minscore": parsed.diversity_min_score,
        }
    return config


_DEFAULT_REINVENT_ENV_SETUP = "\n".join(
    [
        "# Activate the REINVENT4 env (override via REINVENT_ENV_ACTIVATE / env_setup).",
        "module load 2023 2>/dev/null || true",
        "module load Miniconda3 2>/dev/null || true",
        "source activate reinvent4 2>/dev/null || conda activate reinvent4 2>/dev/null || true",
    ]
)


def render_reinvent_slurm_script(
    parsed: ReinventInput,
    remote_config_path: str,
    *,
    account: str | None = None,
    qos: str | None = None,
) -> str:
    """Render a SLURM script that runs REINVENT on the cluster.

    ``remote_config_path`` is an absolute POSIX path on the cluster. The script
    activates the environment, exports ``REINVENT_PRIOR_BASE`` (so dot-name
    priors resolve), and runs ``reinvent -f json <config>``.
    """

    env_setup = parsed.env_setup if parsed.env_setup else _DEFAULT_REINVENT_ENV_SETUP
    directives = [
        f"#SBATCH --job-name=reinvent-{parsed.seed}",
        f"#SBATCH --partition={parsed.partition}",
        f"#SBATCH --time={parsed.time_limit}",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        f"#SBATCH --cpus-per-task={parsed.cpus_per_task}",
        f"#SBATCH --mem={parsed.mem}",
        "#SBATCH --output=slurm-%j.out",
        "#SBATCH --error=slurm-%j.err",
    ]
    # Only request a GPU when one is asked for. CPU partitions (rome/genoa)
    # reject jobs that carry a --gpus-per-node directive.
    if parsed.gpus_per_node and parsed.gpus_per_node > 0:
        directives.insert(3, f"#SBATCH --gpus-per-node={parsed.gpus_per_node}")
    if account:
        directives.append(f"#SBATCH --account={account}")
    if qos:
        directives.append(f"#SBATCH --qos={qos}")

    prior_base = parsed.remote_prior_base or parsed.prior_base
    lines = [
        "#!/bin/bash",
        *directives,
        "",
        "set -euo pipefail",
        "",
        "echo '=== REINVENT4 HPC Job ==='",
        env_setup,
        "",
    ]
    if prior_base:
        lines.append(f"export REINVENT_PRIOR_BASE={prior_base}")
    lines.extend(
        [
            f"{parsed.remote_reinvent_executable} -f json -d {parsed.device} -l reinvent.log {remote_config_path}",
            "",
            "echo 'REINVENT generation completed.'",
            "",
        ]
    )
    return "\n".join(lines)


def _write_smiles_file(parsed: ReinventInput, work_dir: Path) -> Path | None:
    """Write the input SMILES file for lib/link/mol2mol/pepinvent generators."""

    if parsed.generator_type not in _NEEDS_SMILES_INPUT or not parsed.input_smiles:
        return None
    smiles_path = work_dir / "reinvent_inputs.smi"
    smiles_path.write_text("\n".join(parsed.input_smiles) + "\n", encoding="utf-8")
    return smiles_path


def _stage_reinvent_config(parsed: ReinventInput, work_dir: Path, remote_job_dir: str):
    """Write the config JSON (with ``remote_job_dir`` paths) and the warhead .smi
    locally. Returns ``(config_path, smiles_path | None)``."""

    config = build_reinvent_config(parsed, remote_base=remote_job_dir)
    config_path = work_dir / parsed.config_filename
    write_result = write_json(config_path, config)
    if not write_result.ok:
        raise RuntimeError(f"Failed to write REINVENT config: {write_result.error}")

    smiles_path: Path | None = None
    if parsed.generator_type in _NEEDS_SMILES_INPUT and parsed.input_smiles:
        smiles_path = work_dir / "reinvent_inputs.smi"
        smiles_path.write_text("\n".join(parsed.input_smiles) + "\n", encoding="utf-8")
    return config_path, smiles_path


def _stage_reinvent_job(parsed: ReinventInput, work_dir: Path, remote_job_dir: str, *, account, qos):
    """Write the config JSON (with ``remote_job_dir`` paths), warhead .smi, and
    SLURM script locally; return (config_path, script_path, input_files)."""

    config_path, smiles_path = _stage_reinvent_config(parsed, work_dir, remote_job_dir)
    input_files: list[tuple[str | Path, str]] = [(config_path, parsed.config_filename)]
    if smiles_path is not None:
        input_files.append((smiles_path, "reinvent_inputs.smi"))

    remote_config_path = f"{remote_job_dir}/{parsed.config_filename}"
    script_path = work_dir / "reinvent_job.slurm"
    script_path.write_text(
        render_reinvent_slurm_script(parsed, remote_config_path, account=account, qos=qos),
        encoding="utf-8",
    )
    input_files.append((script_path, "reinvent_job.slurm"))
    return config_path, script_path, input_files


def _generate_with_reinvent_ssh(parsed: ReinventInput):
    """Run REINVENT directly over SSH on a rented GPU box (RunPod etc.).

    No scheduler: connect, upload the config (+ warhead file), run ``reinvent``
    as a command, then download the outputs and parse them. When SSH is not
    configured or ``run`` is off, writes the config and returns mock molecules.
    """
    import posixpath

    from hackathon_agents.tools.remote_hpc import RemoteHPCClient, RemoteHPCConfig, _shquote

    work_dir = Path(parsed.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    if not parsed.run or not parsed.ssh_host:
        remote_job_dir = f"{parsed.remote_workdir}/reinvent-{parsed.seed}"
        config_path, _ = _stage_reinvent_config(parsed, work_dir, remote_job_dir)
        reason = "ssh_not_configured" if not parsed.ssh_host else "run=False"
        molecules = _mock_molecules(parsed, reason=reason)
        result = _build_success(parsed, molecules, config_path, mock=True)
        result.metadata["ssh_dry_run"] = {"remote_job_dir": remote_job_dir, "ssh_host": parsed.ssh_host}
        return result

    cfg = RemoteHPCConfig(
        host=parsed.ssh_host,
        user=parsed.ssh_user,
        port=parsed.ssh_port,
        key_path=parsed.ssh_key_path,
        password=parsed.ssh_password,
    )
    with RemoteHPCClient(cfg) as client:
        base = client.resolve_path(parsed.remote_workdir)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        # A uuid suffix keeps the remote dir unique when many jobs run concurrently
        # (ThreadPoolExecutor shares pid, and stamp is only per-second, so matched
        # seeds across contexts would otherwise collide and clobber each other).
        uniq = uuid.uuid4().hex[:8]
        remote_job_dir = posixpath.join(base, f"reinvent-{parsed.seed}_{stamp}_{os.getpid()}_{uniq}")
        client.makedirs(remote_job_dir)

        config_path, smiles_path = _stage_reinvent_config(parsed, work_dir, remote_job_dir)
        client.upload(config_path, f"{remote_job_dir}/{parsed.config_filename}")
        if smiles_path is not None:
            client.upload(smiles_path, f"{remote_job_dir}/reinvent_inputs.smi")

        remote_config = f"{remote_job_dir}/{parsed.config_filename}"
        prior_base = parsed.remote_prior_base or parsed.prior_base
        prefix = f"export REINVENT_PRIOR_BASE={_shquote(prior_base)} && " if prior_base else ""
        # On a CPU device, hide CUDA so torch never probes the GPU. Without this,
        # torch's optimizer (staged learning) runs an accelerator health check
        # that calls into CUDA even for CPU tensors and crashes when the box's
        # NVIDIA driver is older than the torch CUDA build (common on rented pods).
        # Also cap the thread count: on a many-core box (e.g. a 192-core pod)
        # torch spawns one thread per core and thrashes on the small LinkInvent
        # transformer batch — capping to ~16 makes CPU staged learning ~4x faster
        # (measured 297s -> 74s for 60 RL steps). Override via REINVENT_CPU_THREADS.
        if str(parsed.device).lower().startswith("cpu"):
            prefix += (
                "export CUDA_VISIBLE_DEVICES='' && "
                'T=${REINVENT_CPU_THREADS:-$(c=$(nproc 2>/dev/null || echo 8); '
                '[ "$c" -lt 16 ] && echo "$c" || echo 16)} && '
                "export OMP_NUM_THREADS=$T MKL_NUM_THREADS=$T && "
            )
        command = (
            f"cd {_shquote(remote_job_dir)} && {prefix}"
            f"{parsed.remote_reinvent_executable} -f json -d {parsed.device} "
            f"-l reinvent.log {_shquote(remote_config)}"
        )
        code, out, err = client.run(command, timeout=parsed.timeout_seconds)
        if code != 0:
            return error_result(
                f"Remote REINVENT (ssh) exited with code {code}.",
                {"command": command, "returncode": code, "stdout": out[-4000:], "stderr": err[-4000:]},
            )
        # Only the CSVs (parsed) and the log (diagnostics) are needed. The
        # ``*.chkpt`` is ~90 MB of model weights we never read; skipping it makes
        # each CPU pass noticeably faster over SSH.
        client.download_matching(
            remote_job_dir,
            ["*.csv", f"{parsed.summary_csv_prefix}*", "sampling.csv", "reinvent.log"],
            work_dir,
        )

    molecules = _parse_generated_molecules(parsed, work_dir)
    if not molecules:
        molecules = _mock_molecules(parsed, reason="no_output_parsed")
        result = _build_success(parsed, molecules, config_path, mock=True)
        result.metadata["reinvent_stdout_tail"] = out[-2000:]
        return result
    result = _build_success(parsed, molecules, config_path, mock=False)
    result.metadata["reinvent_returncode"] = code
    result.metadata["ssh_host"] = parsed.ssh_host
    return result


def _generate_with_reinvent_remote(parsed: ReinventInput):
    """Stage a REINVENT config + script on the cluster, submit, wait, and parse."""
    import posixpath

    from hackathon_agents.tools.remote_hpc import (
        RemoteHPCClient,
        RemoteHPCConfig,
        RemoteJobSpec,
        make_remote_job_dir,
        submit_and_wait,
    )

    work_dir = Path(parsed.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    remote_cfg = RemoteHPCConfig.from_env()

    # Safe default: only submit when explicitly enabled and credentials present.
    # The dry run does not connect, so it keeps ``~`` (the shell expands it in the
    # SLURM script); no SFTP happens.
    if not parsed.allow_submit or not remote_cfg.is_configured:
        remote_job_dir = make_remote_job_dir(remote_cfg, "reinvent", f"reinvent-{parsed.seed}")
        config_path, script_path, _ = _stage_reinvent_job(
            parsed, work_dir, remote_job_dir, account=remote_cfg.account, qos=remote_cfg.qos
        )
        molecules = _mock_molecules(parsed, reason="remote_dry_run")
        result = _build_success(parsed, molecules, config_path, mock=True)
        result.artifacts.append(str(script_path))
        result.metadata["remote_dry_run"] = {
            "script_path": str(script_path),
            "remote_job_dir": remote_job_dir,
            "configured": remote_cfg.is_configured,
            "allow_submit": parsed.allow_submit,
        }
        return result

    # Real submission: connect first so we can resolve ``~`` to the absolute
    # cluster $HOME. The job dir must be absolute because it is embedded in the
    # config (SFTP and REINVENT's Python file I/O do not expand ``~``).
    try:
        with RemoteHPCClient(remote_cfg) as client:
            base = client.resolve_path(remote_cfg.base_dir)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            remote_job_dir = posixpath.join(
                base, "hackathon_agents", "reinvent", f"reinvent-{parsed.seed}_{stamp}_{os.getpid()}"
            )
            config_path, script_path, input_files = _stage_reinvent_job(
                parsed, work_dir, remote_job_dir, account=remote_cfg.account, qos=remote_cfg.qos
            )
            spec = RemoteJobSpec(
                tool="reinvent",
                job_name=f"reinvent-{parsed.seed}",
                input_files=input_files,
                script_name="reinvent_job.slurm",
                output_patterns=["*.csv", f"{parsed.summary_csv_prefix}*", "tb_logs/**", "*.chkpt", "sampling.csv"],
                local_output_dir=work_dir,
                remote_job_dir=remote_job_dir,
            )
            run = submit_and_wait(
                client,
                spec,
                timeout=parsed.timeout_seconds,
                poll_interval=parsed.poll_interval_seconds,
            )
    except Exception as exc:
        return error_result(f"Remote REINVENT submission failed: {exc}", {"work_dir": str(work_dir)})

    if run.state != "completed":
        return error_result(
            f"Remote REINVENT job {run.job_id} ended in state '{run.state}'.",
            {
                "job_id": run.job_id,
                "remote_job_dir": run.remote_job_dir,
                "stdout_tail": run.stdout_tail,
                "stderr_tail": run.stderr_tail,
            },
        )

    molecules = _parse_generated_molecules(parsed, work_dir)
    if not molecules:
        molecules = _mock_molecules(parsed, reason="no_output_parsed")
        result = _build_success(parsed, molecules, config_path, mock=True)
        result.metadata["reinvent_job_id"] = run.job_id
        result.metadata["reinvent_stdout_tail"] = run.stdout_tail
        return result

    result = _build_success(parsed, molecules, config_path, mock=False)
    result.metadata["reinvent_job_id"] = run.job_id
    result.metadata["downloaded_files"] = run.downloaded_files
    return result


def generate_with_reinvent(input_data: ReinventInput | dict[str, Any]):
    """Build a REINVENT config, optionally run REINVENT, and return molecules.

    Returns a ``ToolResult`` whose ``data`` contains ``molecules`` (a list of
    serialized ``MoleculeRecord``), the ``config_path``, whether the run was
    ``mock``, and the run/generator settings used.
    """

    parsed = _coerce(input_data)
    if parsed.run_mode == "slurm_remote":
        try:
            return _generate_with_reinvent_remote(parsed)
        except Exception as exc:
            return error_result(str(exc), {"work_dir": parsed.work_dir})
    if parsed.run_mode == "ssh_remote":
        try:
            return _generate_with_reinvent_ssh(parsed)
        except Exception as exc:
            return error_result(str(exc), {"work_dir": parsed.work_dir})
    try:
        work_dir = Path(parsed.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

        _write_smiles_file(parsed, work_dir)
        config = build_reinvent_config(parsed)
        config_path = work_dir / parsed.config_filename
        write_result = write_json(config_path, config)
        if not write_result.ok:
            return error_result(f"Failed to write REINVENT config: {write_result.error}")

        if not parsed.run:
            molecules = _mock_molecules(parsed, reason="run=False")
            return _build_success(parsed, molecules, config_path, mock=True)

        availability = check_reinvent_availability(parsed.reinvent_executable, parsed.reinvent_python)
        if not availability.data["available"]:
            molecules = _mock_molecules(parsed, reason="reinvent_unavailable")
            result = _build_success(parsed, molecules, config_path, mock=True)
            result.metadata["reinvent_availability"] = availability.data
            return result

        run_result = _run_reinvent(parsed, availability.data, config_path)
        if not run_result.ok:
            return run_result

        molecules = _parse_generated_molecules(parsed, work_dir)
        if not molecules:
            molecules = _mock_molecules(parsed, reason="no_output_parsed")
            result = _build_success(parsed, molecules, config_path, mock=True)
            result.metadata["reinvent_stdout_tail"] = run_result.data.get("stdout", "")[-2000:]
            return result

        result = _build_success(parsed, molecules, config_path, mock=False)
        result.metadata["reinvent_returncode"] = run_result.data.get("returncode")
        return result
    except Exception as exc:
        return error_result(str(exc), {"work_dir": parsed.work_dir})


def reinvent_records(result_data: dict[str, Any]) -> list[MoleculeRecord]:
    """Re-hydrate ``MoleculeRecord`` objects from a tool result ``data`` dict."""

    return [MoleculeRecord.model_validate(item) for item in result_data.get("molecules", [])]


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _coerce(input_data: ReinventInput | dict[str, Any]) -> ReinventInput:
    return (
        input_data
        if isinstance(input_data, ReinventInput)
        else ReinventInput.model_validate(input_data)
    )


def _build_success(
    parsed: ReinventInput,
    molecules: list[MoleculeRecord],
    config_path: Path,
    *,
    mock: bool,
):
    return ok_result(
        {
            "molecules": [molecule.model_dump(mode="json") for molecule in molecules],
            "molecule_count": len(molecules),
            "config_path": str(config_path),
            "mock": mock,
            "run_type": parsed.run_type,
            "generator_type": parsed.generator_type,
        },
        artifacts=[str(config_path)],
    )


def _run_reinvent(parsed: ReinventInput, availability: dict[str, Any], config_path: Path):
    work_dir = Path(parsed.work_dir)
    log_path = work_dir / "reinvent.log"
    executable = availability.get("executable")
    if executable:
        command = [executable, "-f", "json", "-d", parsed.device, "-l", str(log_path), str(config_path)]
    else:
        # Fall back to invoking the module through the env interpreter.
        command = [
            availability["python"],
            "-m",
            "reinvent",
            "-f",
            "json",
            "-d",
            parsed.device,
            "-l",
            str(log_path),
            str(config_path),
        ]

    env = dict(os.environ)
    if str(parsed.device).lower().startswith("cpu"):
        env["CUDA_VISIBLE_DEVICES"] = ""
    if parsed.prior_base:
        env["REINVENT_PRIOR_BASE"] = parsed.prior_base

    try:
        completed = subprocess.run(
            command,
            cwd=parsed.work_dir,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=parsed.timeout_seconds,
        )
    except Exception as exc:
        return error_result(f"REINVENT execution failed: {exc}", {"command": command})

    if completed.returncode != 0:
        return error_result(
            f"REINVENT exited with code {completed.returncode}.",
            {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            },
        )
    return ok_result(
        {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    )


def _parse_generated_molecules(
    parsed: ReinventInput,
    work_dir: Path,
) -> list[MoleculeRecord]:
    """Parse SMILES + scores/NLL from REINVENT's CSV output.

    Sampling writes ``sampling.csv`` (columns ``SMILES``, ``SMILES_state``,
    ``NLL`` plus generator extras). Staged learning writes
    ``{summary_csv_prefix}_*.csv`` with per-step scores. We keep the best unique
    valid SMILES (highest score, else lowest NLL) and cap at ``max_return``.
    """

    import csv

    rows: list[dict[str, str]] = []
    if work_dir.exists():
        for csv_path in sorted(work_dir.rglob("*.csv")):
            try:
                with csv_path.open("r", encoding="utf-8", newline="") as handle:
                    rows.extend(list(csv.DictReader(handle)))
            except Exception:
                continue

    smiles_keys = ("SMILES", "Smiles", "smiles", "canonical_smiles")
    state_keys = ("SMILES_state", "smiles_state", "State")
    score_keys = ("Score", "total_score", "score", "aggregated_score", "reward")
    nll_keys = ("NLL", "nll", "negative_log_likelihood")

    best: dict[str, tuple[float, float, MoleculeRecord]] = {}
    any_score = False
    for index, row in enumerate(rows):
        smiles = next((row[key] for key in smiles_keys if key in row and row[key]), None)
        if not smiles:
            continue
        # Keep valid molecules; REINVENT marks state as "0" (valid) or "VALID".
        state = next((row[key] for key in state_keys if key in row and row[key] not in (None, "")), None)
        if state is not None and str(state).upper() not in ("0", "VALID", "TRUE", "1"):
            continue

        score = _first_float(row, score_keys)
        nll = _first_float(row, nll_keys)
        if score is not None:
            any_score = True

        record = MoleculeRecord(
            smiles=smiles,
            name=f"reinvent candidate {index + 1}",
            source="reinvent",
            score=score,
            notes=[f"objective: {parsed.objective[:160]}"],
            metadata={
                "generator_type": parsed.generator_type,
                "run_type": parsed.run_type,
                "nll": nll,
            },
        )
        # Ranking keys: higher score first, then lower NLL.
        rank_score = score if score is not None else -1.0
        rank_nll = nll if nll is not None else float("inf")
        previous = best.get(smiles)
        candidate_key = (rank_score, -rank_nll)
        if previous is None or candidate_key > (previous[0], -previous[1]):
            best[smiles] = (rank_score, rank_nll, record)

    if any_score:
        ranked = sorted(best.values(), key=lambda item: item[0], reverse=True)
    else:
        ranked = sorted(best.values(), key=lambda item: item[1])  # ascending NLL
    return [record for _, _, record in ranked[: parsed.max_return]]


def _first_float(row: dict[str, str], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            try:
                return float(row[key])
            except (TypeError, ValueError):
                return None
    return None


def _mock_molecules(
    parsed: ReinventInput,
    *,
    reason: str,
) -> list[MoleculeRecord]:
    count = min(parsed.max_return, len(_MOCK_GENERATED_SMILES))
    molecules: list[MoleculeRecord] = []
    for index in range(count):
        smiles = _MOCK_GENERATED_SMILES[index]
        # Deterministic, monotonically decreasing pseudo-score for ranking.
        pseudo_score = round(1.0 - index / max(1, len(_MOCK_GENERATED_SMILES)), 4)
        molecules.append(
            MoleculeRecord(
                smiles=smiles,
                name=f"reinvent mock candidate {index + 1}",
                source="reinvent_mock",
                score=pseudo_score,
                notes=[f"objective: {parsed.objective[:160]}", f"mock_reason: {reason}"],
                metadata={
                    "generator_type": parsed.generator_type,
                    "run_type": parsed.run_type,
                    "mock_reason": reason,
                },
            )
        )
    return molecules
