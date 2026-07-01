#!/usr/bin/env bash
#SBATCH --job-name=hackathon-mechanism
#SBATCH --output=hackathon_mechanism_%j.out
#SBATCH --error=hackathon_mechanism_%j.err
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/Hackaton-agentic}"
RUN_ROOT="${RUN_ROOT:-runs}"
DATA_PATH="${MECHANISM_DATA:-data/ad_hoc/photochem_trace.csv}"
OBJECTIVE="${MECHANISM_OBJECTIVE:-Infer the mechanism for a photochemical A + B to P reaction and recommend the next experiment.}"
MODE="${MECHANISM_MODE:-mock}"

cd "$REPO_DIR"
mkdir -p "$RUN_ROOT"

# Uncomment the environment setup that matches your cluster.
# source "$HOME/miniconda3/etc/profile.d/conda.sh"
# conda activate hackathon-agents
# module load 2023 Python/3.11.3-GCCcore-12.3.0

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"

python -m hackathon_agents.cli mechanism-once \
  --data "$DATA_PATH" \
  --objective "$OBJECTIVE" \
  --mode "$MODE" \
  --run-root "$RUN_ROOT"
