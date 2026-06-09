from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hackathon_agents.tools.base import ok_result


class SnelliusVLLMJobInput(BaseModel):
    """Inputs for generating a Snellius SLURM job that serves vLLM."""

    output_dir: str | Path
    model_checkpoint: str
    container_path: str = "/projects/2/managed_datasets/containers/vllm/vllm.sif"
    project_space: str = ""
    download_dir: str = "$TMPDIR/vllm_downloads"
    job_name: str = "vllm_inference"
    partition: str = "gpu_a100"
    nodes: int = Field(default=1, ge=1)
    gpus_per_node: int = Field(default=1, ge=1, le=4)
    time_limit: str = "02:00:00"
    port: int = Field(default=8000, ge=1024, le=65535)
    uvicorn_log_level: str = "warning"
    extra_vllm_args: list[str] = Field(default_factory=list)
    filename: str = "run_vllm_serve.job"

    model_config = ConfigDict(extra="forbid")


def generate_snellius_vllm_job(input_data: SnelliusVLLMJobInput | dict):
    """Generate a dry-run-safe SLURM script for Snellius vLLM serving."""

    parsed = (
        input_data
        if isinstance(input_data, SnelliusVLLMJobInput)
        else SnelliusVLLMJobInput.model_validate(input_data)
    )
    output_dir = Path(parsed.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = output_dir / parsed.filename
    script_path.write_text(render_snellius_vllm_job(parsed), encoding="utf-8")
    return ok_result(
        {
            "script_path": str(script_path),
            "base_url": f"http://localhost:{parsed.port}/v1",
            "model": parsed.model_checkpoint,
            "submit_hint": f"sbatch {script_path.name}",
            "tunnel_hint": (
                "After the job starts, expose the vLLM port with your Snellius SSH tunnel "
                f"and set SNELLIUS_VLLM_BASE_URL=http://localhost:{parsed.port}/v1."
            ),
        },
        artifacts=[str(script_path)],
    )


def render_snellius_vllm_job(input_data: SnelliusVLLMJobInput | dict) -> str:
    """Render the SLURM script text without writing it."""

    parsed = (
        input_data
        if isinstance(input_data, SnelliusVLLMJobInput)
        else SnelliusVLLMJobInput.model_validate(input_data)
    )
    bind_dirs = '"$TMPDIR"'
    if parsed.project_space:
        bind_dirs = f'"$TMPDIR",{parsed.project_space}'
    extra_args = " ".join(parsed.extra_vllm_args)
    extra_args_suffix = f" {extra_args}" if extra_args else ""
    return "\n".join(
        [
            "#!/bin/bash",
            f"#SBATCH --job-name={parsed.job_name}",
            f"#SBATCH --partition={parsed.partition}",
            f"#SBATCH --nodes={parsed.nodes}",
            "#SBATCH --ntasks=1",
            f"#SBATCH --gpus-per-node={parsed.gpus_per_node}",
            f"#SBATCH --time={parsed.time_limit}",
            "",
            "set -euo pipefail",
            "",
            f"CONTAINER_PATH={parsed.container_path}",
            f"MODEL_CHECKPOINT={parsed.model_checkpoint}",
            f"PORT={parsed.port}",
            f"DOWNLOAD_DIR={parsed.download_dir}",
            f"BIND_DIRS={bind_dirs}",
            "",
            "mkdir -p \"$DOWNLOAD_DIR\"",
            "echo \"Starting vLLM server on port $PORT for $MODEL_CHECKPOINT\"",
            "echo \"OpenAI-compatible base URL inside the job: http://localhost:$PORT/v1\"",
            "",
            "apptainer exec --nv \\",
            "  -B \"${BIND_DIRS}\" \\",
            "  \"${CONTAINER_PATH}\" \\",
            "  vllm serve \"${MODEL_CHECKPOINT}\" \\",
            "  --tensor-parallel-size \"${SLURM_GPUS_ON_NODE:-1}\" \\",
            "  --download-dir \"${DOWNLOAD_DIR}\" \\",
            f"  --uvicorn-log-level {parsed.uvicorn_log_level} \\",
            f"  --port \"${{PORT}}\"{extra_args_suffix}",
            "",
        ]
    )
