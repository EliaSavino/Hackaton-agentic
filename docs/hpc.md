# HPC And Remote Terminal Guide

This guide covers two different HPC patterns:

1. Run a workflow as a batch job on the cluster.
2. Serve a model on the cluster and connect to it from your local terminal.

## Batch Workflow Job

Use this mode when the repo itself should run on the cluster, for example to
analyze kinetic data, run a mechanism loop, or prepare reports.

Create a Slurm script such as `run_mechanism_once.job`:

```bash
#!/usr/bin/env bash
#SBATCH --job-name=hackathon-mechanism
#SBATCH --output=runs/hpc_%j.out
#SBATCH --error=runs/hpc_%j.err
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G

set -euo pipefail

cd "$HOME/Hackaton-agentic"

# Choose the environment style that matches your cluster setup.
# source "$HOME/miniconda3/etc/profile.d/conda.sh"
# conda activate hackathon-agents

export PYTHONPATH=src

python -m hackathon_agents.cli mechanism-once \
  --data data/ad_hoc/photochem_trace.csv \
  --objective "Infer the mechanism for a photochemical A + B to P reaction and recommend the next experiment." \
  --mode mock \
  --run-root runs
```

Submit it:

```bash
sbatch run_mechanism_once.job
```

Watch it:

```bash
squeue -u "$USER"
tail -f runs/hpc_<jobid>.out
```

The run artifacts will be under `runs/mechanism_once_<timestamp>/`, including
`state.json`, `report.json`, `report.docx`, and `artifact_index.json`.

## Serve A Model On HPC

Use this mode when the cluster has GPUs and your laptop should connect to a
remote OpenAI-compatible model server.

Generate a Snellius vLLM job:

```bash
PYTHONPATH=src python -m hackathon_agents.cli snellius-vllm-script \
  --model-checkpoint meta-llama/Llama-3.1-70B-Instruct \
  --output-dir runs/snellius_vllm \
  --partition gpu_a100 \
  --gpus-per-node 1 \
  --port 8000
```

Copy or create the generated directory on the cluster, then submit:

```bash
cd runs/snellius_vllm
sbatch run_snellius_vllm.job
```

After the job starts, identify the compute node from `squeue` or the Slurm log.
Create an SSH tunnel from your laptop:

```bash
ssh -N -L 8000:<compute-node>:8000 <user>@snellius.surf.nl
```

In your local shell:

```bash
export SNELLIUS_VLLM_ENABLED=true
export SNELLIUS_VLLM_MODEL=meta-llama/Llama-3.1-70B-Instruct
export SNELLIUS_VLLM_BASE_URL=http://localhost:8000/v1
PYTHONPATH=src python -m hackathon_agents.cli check-models
```

Then open the prompt terminal:

```bash
PYTHONPATH=src python -m hackathon_agents.cli prompt-terminal \
  --model-alias snellius_vllm \
  --no-rag
```

## Claude Code Gateway Mode

For a LiteLLM/Anthropic-compatible gateway, generate:

```bash
PYTHONPATH=src python -m hackathon_agents.cli snellius-gateway-script \
  --model-checkpoint openai/gpt-oss-120b \
  --output-dir runs/snellius_gateway \
  --gateway-port 4000
```

Submit the generated job on the cluster. After it starts, print local tunnel and
environment commands:

```bash
PYTHONPATH=src python -m hackathon_agents.cli snellius-client-env \
  --snellius-user "$USER" \
  --compute-node <compute-node> \
  --model-alias claude-snellius-local
```

Run the printed SSH tunnel command and exports in your local shell.

## Operational Notes

- Keep API keys in a protected `.env` on the machine that uses them.
- Use `chmod 600 .env` on shared systems.
- Prefer `mock` or `dry-run` modes until robot/HPC submission is explicitly
  approved.
- Check each run's `artifact_index.json` first when collecting outputs.

