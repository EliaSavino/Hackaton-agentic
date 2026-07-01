# HPC And Remote Terminal Guide

This guide covers two different HPC patterns:

1. Run a workflow as a batch job on the cluster.
2. Serve a model on the cluster and connect to it from your local terminal.

## Batch Workflow Job

Use this mode when the repo itself should run on the cluster, for example to
analyze kinetic data, run a mechanism loop, or prepare reports.

Start from the checked-in template:

```bash
less docs/examples/run_mechanism_once.slurm
```

Submit it as-is for a mock-safe mechanism run, or override inputs with
environment variables:

```bash
sbatch docs/examples/run_mechanism_once.slurm
```

For a custom dataset/objective:

```bash
MECHANISM_DATA=data/my_trace.csv \
MECHANISM_OBJECTIVE="Infer the rate law and propose the next experiment." \
RUN_ROOT=runs \
sbatch docs/examples/run_mechanism_once.slurm
```

Watch it:

```bash
squeue -u "$USER"
tail -f hackathon_mechanism_<jobid>.out
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
