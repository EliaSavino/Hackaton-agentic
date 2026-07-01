"""Saturn generative molecular design tool.

This wraps the `schwallergroup/saturn` framework
(https://github.com/schwallergroup/saturn) so an agent can run sample-efficient
goal-directed molecule generation against an oracle (reward function) of its
choice and recover the generated SMILES as typed ``MoleculeRecord`` objects.

Saturn is **not** a pip package. It is a separate cloned repository with its own
conda environment (Python 3.10, GPU recommended) and is driven by a single JSON
configuration file::

    python saturn.py <config.json>

Because Saturn cannot be imported in-process from this workbench, this tool
follows the same pattern as the xTB/ORCA/Snellius wrappers:

1. Build a Saturn-compatible JSON config from a small, typed, hackathon-friendly
   schema (oracle components + agent/RL settings).
2. Optionally invoke ``saturn.py`` as a subprocess inside the Saturn repo, using
   the Saturn Python interpreter (e.g. the conda env's ``python``).
3. Parse the generated SMILES from Saturn's CSV/JSON logging output into
   ``MoleculeRecord`` objects.

When Saturn is not installed/configured, or when ``run=False`` (the default),
the tool writes the config file and returns a deterministic **mock** set of
candidate molecules so the rest of the workbench stays testable offline.

Every code path returns a ``ToolResult``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.tools.base import error_result, ok_result
from hackathon_agents.tools.file_io import write_json


# Deterministic, drug-like SMILES used for the offline mock generator. These are
# only used when Saturn is unavailable or when ``run=False``.
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


class OracleComponent(BaseModel):
    """A single scoring component for the Saturn oracle (reward function).

    ``name`` must match a Saturn-supported component (e.g. ``"qed"``, ``"sa"``,
    ``"docking"``, ``"syntheseus"``, ``"custom_alert"``, ...). ``weight`` and
    ``specific_parameters`` are passed through to Saturn unchanged.
    """

    name: str
    weight: float = 1.0
    specific_parameters: dict[str, Any] = Field(default_factory=dict)
    # Optional transform/score modifier passed straight through to Saturn.
    transform: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    def to_saturn(self) -> dict[str, Any]:
        component: dict[str, Any] = {
            "name": self.name,
            "weight": self.weight,
            "specific_parameters": dict(self.specific_parameters),
        }
        if self.transform is not None:
            component["specific_parameters"].setdefault("transformation", self.transform)
        return component


class SaturnGenerationInput(BaseModel):
    """Inputs for a Saturn goal-directed generation run.

    The defaults describe a small, fast configuration suitable for a hackathon.
    Set ``run=True`` and provide ``saturn_repo``/``saturn_python`` to execute the
    real framework; otherwise the tool produces a config plus a deterministic
    mock result.
    """

    objective: str = "Generate goal-directed candidate molecules."
    work_dir: str
    oracle: list[OracleComponent] = Field(
        default_factory=lambda: [OracleComponent(name="qed", weight=1.0)]
    )
    # --- Agent / RL knobs (the "setting of the agent's choice") -------------
    aggregator: Literal["product", "sum", "weighted_sum"] = "product"
    batch_size: int = Field(default=64, ge=1, le=1024)
    n_steps: int = Field(default=50, ge=1, le=10000)
    sigma: float = Field(default=128.0, gt=0.0)
    learning_rate: float = Field(default=1e-4, gt=0.0)
    experience_replay_memory: int = Field(default=64, ge=0)
    seed_smiles: list[str] = Field(default_factory=list, description="SMILES to pre-populate experience replay memory for a warm start.")
    model_architecture: Literal["mamba", "rnn", "transformer"] = Field(default="mamba", description="Deep learning backbone architecture.")
    beam_enumeration: bool = Field(default=False, description="Whether to use beam enumeration in goal directed generation.")
    hallucinated_memory: bool = Field(default=False, description="Whether to use hallucinated memory for exploration.")
    diversity_bucket_size: int = Field(default=25, ge=1, description="Bucket size for Murcko Scaffold diversity filtering.")
    diversity_min_score: float = Field(default=0.4, ge=0.0, le=1.0, description="Minimum score threshold for diversity filter buckets.")
    use_diversity_filter: bool = True
    running_mode: Literal["goal_directed_generation", "scoring"] = "goal_directed_generation"
    seed: int = 0
    device: Literal["cuda", "cpu"] = "cpu"

    # --- Execution / environment -------------------------------------------
    run_mode: Literal["local", "slurm_remote"] = "local"
    saturn_repo: str | None = None  # path to a cloned schwallergroup/saturn repo
    saturn_python: str = "python"  # interpreter from the saturn conda env
    prior_checkpoint: str | None = None  # path to the pretrained Saturn prior
    timeout_seconds: int = Field(default=1800, ge=1)
    run: bool = False  # opt-in real execution; False => config + mock only
    max_return: int = Field(default=25, ge=1, le=5000)
    config_filename: str = "saturn_config.json"

    # --- HPC / SLURM settings (only used if run_mode=slurm_remote) -----------
    allow_submit: bool = False  # opt-in remote submission gate
    partition: str = "gpu_a100"
    gpus_per_node: int = 1
    time_limit: str = "02:00:00"
    poll_interval_seconds: int = 30
    # Paths *on the cluster* (the local saturn_repo/python are for local runs).
    remote_saturn_repo: str | None = None
    remote_saturn_python: str = "python"
    remote_prior_checkpoint: str | None = None
    # Shell lines that activate the Saturn conda env inside the SLURM job.
    env_setup: str | None = None

    model_config = ConfigDict(extra="forbid")


def check_saturn_availability(
    saturn_repo: str | None = None,
    saturn_python: str = "python",
):
    """Report whether a usable Saturn checkout and interpreter are present."""

    repo_ok = False
    saturn_script: str | None = None
    if saturn_repo:
        script = Path(saturn_repo) / "saturn.py"
        repo_ok = script.exists()
        saturn_script = str(script) if repo_ok else None
    python_path = shutil.which(saturn_python) or (saturn_python if Path(saturn_python).exists() else None)
    available = bool(repo_ok and python_path)
    return ok_result(
        {
            "available": available,
            "repo_ok": repo_ok,
            "saturn_script": saturn_script,
            "python": python_path,
            "saturn_python_requested": saturn_python,
        }
    )


def build_saturn_config(
    input_data: SaturnGenerationInput | dict[str, Any],
    *,
    remote_base: str | None = None,
) -> dict[str, Any]:
    """Render a Saturn-compatible JSON config from the typed input.

    When ``remote_base`` is given (a POSIX path on the cluster), logging and
    checkpoint paths are placed under it and the prior/agent use the remote
    checkpoint, so the config is valid for a job that runs on the cluster.
    """

    parsed = _coerce(input_data)
    if remote_base is not None:
        logging_path = f"{remote_base}/saturn_log"
        checkpoints_dir = f"{remote_base}/checkpoints"
        prior = parsed.remote_prior_checkpoint or parsed.prior_checkpoint or ""
    else:
        work_dir = Path(parsed.work_dir)
        logging_path = str(work_dir / "saturn_log")
        checkpoints_dir = str(work_dir / "checkpoints")
        prior = parsed.prior_checkpoint or ""

    return {
        "running_mode": parsed.running_mode,
        "seed": parsed.seed,
        "device": parsed.device,
        "model_architecture": {"name": parsed.model_architecture},
        "logging": {
            "logging_frequency": 1,
            "logging_path": logging_path,
            "model_checkpoints_dir": checkpoints_dir,
        },
        "oracle": {
            "aggregator": parsed.aggregator,
            "components": [component.to_saturn() for component in parsed.oracle],
        },
        "goal_directed_generation": {
            "reinforcement_learning": {
                "prior": prior,
                "agent": prior,
                "batch_size": parsed.batch_size,
                "n_steps": parsed.n_steps,
                "sigma": parsed.sigma,
                "learning_rate": parsed.learning_rate,
            },
            "experience_replay": {
                "memory_size": parsed.experience_replay_memory,
                "sample_size": min(parsed.experience_replay_memory, parsed.batch_size),
                "smiles": list(parsed.seed_smiles),
            },
            "diversity_filter": {
                "name": "IdenticalMurckoScaffold" if parsed.use_diversity_filter else "NoFilter",
                "bucket_size": parsed.diversity_bucket_size,
                "minscore": parsed.diversity_min_score,
            },
            "hallucinated_memory": {"use_hallucinated_memory": parsed.hallucinated_memory},
            "beam_enumeration": {"use_beam_enumeration": parsed.beam_enumeration},
        },
    }


_DEFAULT_SATURN_ENV_SETUP = "\n".join(
    [
        "# Activate the Saturn conda env (override via SATURN_ENV_ACTIVATE / env_setup).",
        "module load 2023 2>/dev/null || true",
        "module load Miniconda3 2>/dev/null || true",
        "source activate saturn 2>/dev/null || conda activate saturn 2>/dev/null || true",
    ]
)


def render_saturn_slurm_script(
    parsed: SaturnGenerationInput,
    remote_config_path: str,
    remote_saturn_repo: str,
    *,
    account: str | None = None,
    qos: str | None = None,
) -> str:
    """Render a SLURM script that runs Saturn on the cluster.

    ``remote_config_path`` and ``remote_saturn_repo`` are absolute POSIX paths on
    the cluster. The script activates the environment, ``cd``s into the Saturn
    checkout, and runs ``python saturn.py <config.json>``.
    """
    env_setup = parsed.env_setup if parsed.env_setup else _DEFAULT_SATURN_ENV_SETUP
    directives = [
        f"#SBATCH --job-name=saturn-{parsed.seed}",
        f"#SBATCH --partition={parsed.partition}",
        f"#SBATCH --gpus-per-node={parsed.gpus_per_node}",
        f"#SBATCH --time={parsed.time_limit}",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=4",
        "#SBATCH --mem=32G",
        "#SBATCH --output=slurm-%j.out",
        "#SBATCH --error=slurm-%j.err",
    ]
    if account:
        directives.append(f"#SBATCH --account={account}")
    if qos:
        directives.append(f"#SBATCH --qos={qos}")
    return "\n".join(
        [
            "#!/bin/bash",
            *directives,
            "",
            "set -euo pipefail",
            "",
            "echo '=== Saturn HPC Job ==='",
            env_setup,
            "",
            f"cd {remote_saturn_repo}",
            f"{parsed.remote_saturn_python} saturn.py {remote_config_path}",
            "",
            "echo 'Saturn generation completed.'",
            "",
        ]
    )


def _generate_with_saturn_remote(parsed: SaturnGenerationInput):
    """Stage a Saturn config + script on the cluster, submit, wait, and parse."""
    from hackathon_agents.tools.remote_hpc import (
        RemoteHPCClient,
        RemoteHPCConfig,
        RemoteJobSpec,
        make_remote_job_dir,
        submit_and_wait,
    )

    work_dir = Path(parsed.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    oracle_names = [component.name for component in parsed.oracle]
    remote_cfg = RemoteHPCConfig.from_env()

    # Compute the remote job dir up front so the config can reference absolute
    # logging paths on the cluster.
    remote_job_dir = make_remote_job_dir(remote_cfg, "saturn", f"saturn-{parsed.seed}")
    config = build_saturn_config(parsed, remote_base=remote_job_dir)
    config_path = work_dir / parsed.config_filename
    write_result = write_json(config_path, config)
    if not write_result.ok:
        return error_result(f"Failed to write Saturn config: {write_result.error}")

    remote_config_path = f"{remote_job_dir}/{parsed.config_filename}"
    remote_repo = parsed.remote_saturn_repo or parsed.saturn_repo
    script_path = work_dir / "saturn_job.slurm"
    script_path.write_text(
        render_saturn_slurm_script(
            parsed,
            remote_config_path,
            remote_repo or "$HOME/saturn",
            account=remote_cfg.account,
            qos=remote_cfg.qos,
        ),
        encoding="utf-8",
    )

    # Safe default: only write artifacts unless submission is explicitly enabled
    # and credentials are present.
    if not parsed.allow_submit or not remote_cfg.is_configured or not remote_repo:
        molecules = _mock_molecules(parsed, oracle_names, reason="remote_dry_run")
        result = _build_success(parsed, molecules, config_path, mock=True, oracle_names=oracle_names)
        result.artifacts.append(str(script_path))
        result.metadata["remote_dry_run"] = {
            "script_path": str(script_path),
            "remote_job_dir": remote_job_dir,
            "configured": remote_cfg.is_configured,
            "remote_repo_set": bool(remote_repo),
            "allow_submit": parsed.allow_submit,
        }
        return result

    spec = RemoteJobSpec(
        tool="saturn",
        job_name=f"saturn-{parsed.seed}",
        input_files=[(config_path, parsed.config_filename), (script_path, "saturn_job.slurm")],
        script_name="saturn_job.slurm",
        output_patterns=["saturn_log/**", "checkpoints/**", "*.csv"],
        local_output_dir=work_dir,
        remote_job_dir=remote_job_dir,
    )
    try:
        with RemoteHPCClient(remote_cfg) as client:
            run = submit_and_wait(
                client,
                spec,
                timeout=parsed.timeout_seconds,
                poll_interval=parsed.poll_interval_seconds,
            )
    except Exception as exc:
        return error_result(f"Remote Saturn submission failed: {exc}", {"script_path": str(script_path)})

    if run.state != "completed":
        return error_result(
            f"Remote Saturn job {run.job_id} ended in state '{run.state}'.",
            {
                "job_id": run.job_id,
                "remote_job_dir": run.remote_job_dir,
                "stdout_tail": run.stdout_tail,
                "stderr_tail": run.stderr_tail,
            },
        )

    molecules = _parse_generated_molecules(parsed, work_dir, oracle_names)
    if not molecules:
        molecules = _mock_molecules(parsed, oracle_names, reason="no_output_parsed")
        result = _build_success(parsed, molecules, config_path, mock=True, oracle_names=oracle_names)
        result.metadata["saturn_job_id"] = run.job_id
        result.metadata["saturn_stdout_tail"] = run.stdout_tail
        return result

    result = _build_success(parsed, molecules, config_path, mock=False, oracle_names=oracle_names)
    result.metadata["saturn_job_id"] = run.job_id
    result.metadata["downloaded_files"] = run.downloaded_files
    return result


def generate_with_saturn(input_data: SaturnGenerationInput | dict[str, Any]):
    """Build a Saturn config, optionally run Saturn, and return molecules.

    Returns a ``ToolResult`` whose ``data`` contains ``molecules`` (a list of
    serialized ``MoleculeRecord``), the ``config_path``, whether the run was
    ``mock``, and the chosen oracle component names.
    """

    parsed = _coerce(input_data)
    if parsed.run_mode == "slurm_remote":
        try:
            return _generate_with_saturn_remote(parsed)
        except Exception as exc:
            return error_result(str(exc), {"work_dir": parsed.work_dir})
    try:
        work_dir = Path(parsed.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

        config = build_saturn_config(parsed)
        config_path = work_dir / parsed.config_filename
        write_result = write_json(config_path, config)
        if not write_result.ok:
            return error_result(f"Failed to write Saturn config: {write_result.error}")

        oracle_names = [component.name for component in parsed.oracle]

        if not parsed.run:
            molecules = _mock_molecules(parsed, oracle_names, reason="run=False")
            return _build_success(parsed, molecules, config_path, mock=True, oracle_names=oracle_names)

        availability = check_saturn_availability(parsed.saturn_repo, parsed.saturn_python)
        if not availability.data["available"]:
            molecules = _mock_molecules(parsed, oracle_names, reason="saturn_unavailable")
            result = _build_success(parsed, molecules, config_path, mock=True, oracle_names=oracle_names)
            result.metadata["saturn_availability"] = availability.data
            return result

        run_result = _run_saturn(parsed, availability.data, config_path)
        if not run_result.ok:
            return run_result

        molecules = _parse_generated_molecules(parsed, work_dir, oracle_names)
        if not molecules:
            molecules = _mock_molecules(parsed, oracle_names, reason="no_output_parsed")
            result = _build_success(parsed, molecules, config_path, mock=True, oracle_names=oracle_names)
            result.metadata["saturn_stdout_tail"] = run_result.data.get("stdout", "")[-2000:]
            return result

        result = _build_success(parsed, molecules, config_path, mock=False, oracle_names=oracle_names)
        result.metadata["saturn_returncode"] = run_result.data.get("returncode")
        return result
    except Exception as exc:
        return error_result(str(exc), {"work_dir": parsed.work_dir})


def saturn_records(result_data: dict[str, Any]) -> list[MoleculeRecord]:
    """Re-hydrate ``MoleculeRecord`` objects from a tool result ``data`` dict."""

    return [MoleculeRecord.model_validate(item) for item in result_data.get("molecules", [])]


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _coerce(input_data: SaturnGenerationInput | dict[str, Any]) -> SaturnGenerationInput:
    return (
        input_data
        if isinstance(input_data, SaturnGenerationInput)
        else SaturnGenerationInput.model_validate(input_data)
    )


def _build_success(
    parsed: SaturnGenerationInput,
    molecules: list[MoleculeRecord],
    config_path: Path,
    *,
    mock: bool,
    oracle_names: list[str],
):
    return ok_result(
        {
            "molecules": [molecule.model_dump(mode="json") for molecule in molecules],
            "molecule_count": len(molecules),
            "config_path": str(config_path),
            "mock": mock,
            "oracle_components": oracle_names,
            "running_mode": parsed.running_mode,
        },
        artifacts=[str(config_path)],
    )


def _run_saturn(parsed: SaturnGenerationInput, availability: dict[str, Any], config_path: Path):
    command = [availability["python"], availability["saturn_script"], str(config_path)]
    try:
        completed = subprocess.run(
            command,
            cwd=parsed.saturn_repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=parsed.timeout_seconds,
        )
    except Exception as exc:
        return error_result(f"Saturn execution failed: {exc}", {"command": command})

    if completed.returncode != 0:
        return error_result(
            f"Saturn exited with code {completed.returncode}.",
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
    parsed: SaturnGenerationInput,
    work_dir: Path,
    oracle_names: list[str],
) -> list[MoleculeRecord]:
    """Parse SMILES + scores from Saturn's logging output.

    Saturn writes CSV logs under ``logging_path``. We look for any ``.csv`` that
    contains a SMILES-like column and an optional aggregated score column, keep
    the highest-scoring unique SMILES, and cap the result at ``max_return``.
    """

    import csv

    log_dir = work_dir / "saturn_log"
    search_roots = [log_dir, work_dir]
    rows: list[dict[str, str]] = []
    for root in search_roots:
        if not root.exists():
            continue
        for csv_path in sorted(root.rglob("*.csv")):
            try:
                with csv_path.open("r", encoding="utf-8", newline="") as handle:
                    rows.extend(list(csv.DictReader(handle)))
            except Exception:
                continue

    smiles_keys = ("smiles", "SMILES", "Smiles", "canonical_smiles")
    score_keys = ("total_score", "score", "reward", "aggregated_score", "Score")

    best: dict[str, tuple[float, MoleculeRecord]] = {}
    for index, row in enumerate(rows):
        smiles = next((row[key] for key in smiles_keys if key in row and row[key]), None)
        if not smiles:
            continue
        score = None
        for key in score_keys:
            if key in row and row[key] not in (None, ""):
                try:
                    score = float(row[key])
                except ValueError:
                    score = None
                break
        record = MoleculeRecord(
            smiles=smiles,
            name=f"saturn candidate {index + 1}",
            source="saturn",
            score=score,
            notes=[f"objective: {parsed.objective[:160]}"],
            metadata={"oracle_components": oracle_names, "running_mode": parsed.running_mode},
        )
        previous = best.get(smiles)
        if previous is None or (score is not None and score > previous[0]):
            best[smiles] = (score if score is not None else -1.0, record)

    ranked = sorted(best.values(), key=lambda item: item[0], reverse=True)
    return [record for _, record in ranked[: parsed.max_return]]


def _mock_molecules(
    parsed: SaturnGenerationInput,
    oracle_names: list[str],
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
                name=f"saturn mock candidate {index + 1}",
                source="saturn_mock",
                score=pseudo_score,
                notes=[f"objective: {parsed.objective[:160]}", f"mock_reason: {reason}"],
                metadata={
                    "oracle_components": oracle_names,
                    "aggregator": parsed.aggregator,
                    "mock_reason": reason,
                },
            )
        )
    return molecules
