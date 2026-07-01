# Autonomous ADC Linker Design (REINVENT4 LinkInvent)

This workflow designs antibody-drug conjugate (ADC) **linkers**: the fragment
that connects a fixed antibody-side conjugation handle to a fixed payload. The
agent generates linkers with **REINVENT4 LinkInvent**, scores them against a
multi-objective ADC profile, and — as an autonomous critic — reweights that
objective between rounds. It finishes by writing a ~5-page LaTeX paper.

- Scientific engine: REINVENT4 LinkInvent (generates the linker between two warheads).
- Autonomy: the agent chooses **what to optimize** (goal-profile weights + constraints) *and* **how to generate** (the strategy: sampling vs RL and the budget) each pass.
- Output: candidates, an auditable decision trail, and `adc_paper.tex`.

### The agent decides the generation strategy
You do not pick sampling vs RL. The planner starts with a cheap **sampling** pass
(fast, CPU-safe, yields a baseline); the critic then decides each pass whether to
escalate to **staged-learning (RL)**, resize the RL budget (steps/batch, within
the caps), reweight the objective, or stop. With an LLM this is model-driven
(`reinvent_strategy_overrides`); offline it uses a deterministic sample→RL ladder.
`--reinvent-steps` / `--reinvent-batch` set the *budget caps* the agent stays
within — not a fixed plan.

## How it fits together

```
planner ─▶ chemist (REINVENT LinkInvent) ─▶ tool exec (RDKit) ─▶ critic ─▶ writer
   │                                                              │           │
 seeds the ADC goal profile +                    scores linkers with the      writes
 reinvent objective (state.metadata)             ADC composite; may reweight  adc_paper.tex
                                                 the objective and loop  ◀────┘
```

Key pieces:

| Concern | Where |
|---|---|
| ADC objective builder (profile → REINVENT scoring) | `src/hackathon_agents/tools/adc_linker_objective.py` |
| Goal-profile schema | `ADCGoalProfile` in `src/hackathon_agents/schemas/linkers.py` |
| REINVENT tool wrapper | `src/hackathon_agents/tools/reinvent_tools.py` |
| Planner default (intent-detected) | `_set_default_adc_linker_objective` in `agents/planner.py` |
| ADC scoring + autonomy | `agents/critic.py` (`_score_adc_candidate`, `_apply_goal_profile_overrides`) |
| Paper writer | `src/hackathon_agents/tools/paper_writer.py` |
| CLI command | `design-adc-linkers` in `cli.py` |

## The goal profile

`ADCGoalProfile` is the whole action space — seven weights (0..1) plus two
toggles and target windows:

| Dimension | REINVENT component(s) | Meaning |
|---|---|---|
| `solubility` | `FragmentSlogP`, `FragmentTPSA` | soluble, low-aggregation linker |
| `size` | `FragmentMolecularWeight` | MW inside `[mw_low, mw_high]` |
| `flexibility` | `FragmentNumRotBond` | not overly floppy |
| `synthesizability` | `SAScore` | easy to make |
| `cleavability` | `MatchingSubstructure` (Val-Cit / disulfide / PABC SMARTS) | rewards a cleavable trigger |
| `stability` | `CustomAlerts` (hydrazone / acetal) | filters plasma-labile groups |
| `similarity` | `TanimotoSimilarity` | off by default (corpus has no linker SMILES yet) |

Constraints: `require_cleavable_motif`, `enforce_stability_alerts`. Warheads and
the compute budget are **fixed** and are never part of the critic's action space.

The canonical starting warhead pair is
`O=C1C=CC(=O)N1CCCCCC(=O)*|*Nc1ccccc1` (maleimidocaproyl handle | payload stub).
Swap the payload stub for a real payload (e.g. MMAE) in
`CANONICAL_WARHEAD_PAIR` when ready.

## Run it locally (mock, no GPU, offline-safe)

REINVENT stays disabled by default, so this returns deterministic mock linkers
but exercises the whole loop and writes the paper:

```bash
python -m hackathon_agents.cli design-adc-linkers \
  "Design a soluble, protease-cleavable ADC linker for maleimide conjugation" \
  --run-mode full --mock
```

Outputs land in `runs/<timestamp>/`: `adc_paper.tex`, `state.json` (with the
`adc_decision_trail`), `figures/candidate_scores.png`, plus the generic reports.

> Use `--run-mode full` or `cheap`, **not** `offline` — REINVENT is only enabled
> in `full`/`cheap` run modes.

## Run it for real on Snellius (GPU)

### One-time, on the cluster
1. Install REINVENT in its own env and note the executable path:
   ```bash
   module load 2023 && module load Miniconda3
   conda create -y -n reinvent4 python=3.11 && source activate reinvent4
   pip install reinvent4
   which reinvent          # -> REINVENT_REMOTE_EXECUTABLE
   ```
2. Download the LinkInvent prior (Zenodo DOI `10.5281/zenodo.15641296`) into a
   folder; the file must be named `linkinvent.prior`:
   ```bash
   mkdir -p $HOME/reinvent_priors && cd $HOME/reinvent_priors
   wget <linkinvent.prior URL from the Zenodo page> -O linkinvent.prior
   pwd                     # -> REINVENT_REMOTE_PRIOR_BASE
   ```
3. Find your SLURM account: `sacctmgr show user $USER withassoc format=account,partition`.

### One-time, on your laptop
Install the SSH dependency:
```bash
pip install -e '.[hpc]'   # or: pip install paramiko
```

Set these in `.env` (see `.env.example`). **Password login** is supported —
leave `HPC_KEY_PATH` empty and set `HPC_PASSWORD`:
```bash
HPC_HOST=snellius.surf.nl
HPC_USER=<you>
HPC_PASSWORD=<your password>          # or set HPC_KEY_PATH for key auth instead
HPC_HOME=/home/<you>
HPC_SCRATCH_PATH=/scratch-shared/<you>
SLURM_ACCOUNT=<account>
SLURM_PARTITION=gpu_a100
SLURM_TIME=01:00:00

REINVENT_ENABLED=true
REINVENT_RUN_MODE=slurm_remote
REINVENT_ALLOW_SUBMIT=true
REINVENT_REMOTE_EXECUTABLE=<which reinvent on the cluster>
REINVENT_REMOTE_PRIOR_BASE=<folder holding linkinvent.prior>
REINVENT_ENV_ACTIVATE=module load 2023; module load Miniconda3; source activate reinvent4
```

### Run (GPU)
```bash
python -m hackathon_agents.cli design-adc-linkers \
  "Design a soluble, protease-cleavable ADC linker for maleimide conjugation with high plasma stability" \
  --run-mode full --run --device cuda:0
```

### Run (CPU-only: rome / genoa, no GPU budget)
Set the CPU partition and **zero GPUs** in `.env` so no GPU is requested:
```bash
SLURM_PARTITION=rome        # or genoa
SLURM_GPUS=0
SLURM_CPUS_PER_TASK=8       # rome has 128 cores/node, genoa 192
SLURM_MEM=14G               # keep mem <= cpus * 1792 MiB to avoid extra charge
SLURM_TIME=04:00:00         # CPU RL is slower; give it room
SLURM_ACCOUNT=              # leave EMPTY (a project code, not your username)
```
**Budget note:** on shared nodes SLURM charges `max(cpus, mem_MiB / 1792)` CPU-cores.
`SLURM_MEM=128G` with `SLURM_CPUS_PER_TASK=32` is charged for ~73 cores — expensive.
`8 cpus + 14G` is charged for 8 cores and is plenty for LinkInvent on CPU.
Leave `SLURM_ACCOUNT` empty unless you have a real project code; the username is
**not** a valid account and will be dropped automatically (and rejected by SLURM
if forced).
Then run on CPU, with a smaller RL budget so it finishes in reasonable time:
```bash
python -m hackathon_agents.cli design-adc-linkers \
  "Design a soluble, protease-cleavable ADC linker for maleimide conjugation" \
  --run-mode full --run --device cpu \
  --reinvent-steps 20 --reinvent-batch 32
```
When `SLURM_GPUS=0`, the generated SLURM script omits `--gpus-per-node` entirely
(a GPU directive would get the job rejected on a CPU partition) **and the torch
device is forced to `cpu`** — so even `--device cuda:0` can't leak onto a
CPU-only node. Start small (`--reinvent-steps 20`) to confirm timing, then scale up.

The agent connects over SSH, uploads the config + a SLURM script, submits with
`sbatch`, polls every `HPC_POLL_INTERVAL` seconds until the job finishes,
downloads the CSV output, scores the linkers, possibly reweights and loops, and
writes the paper.

### Dry run first (recommended)
Before spending GPU hours, confirm the SSH + staging works without submitting:
set `REINVENT_ALLOW_SUBMIT=false` and run the same command. It connects, writes
the SLURM script locally, and returns mock molecules.

## Run on a rented GPU (RunPod or any single SSH GPU box)

RunPod is **not** a SLURM cluster — it is one GPU machine you SSH into. There is
no `sbatch`, no account, no budget partitions. Do **not** use `slurm_remote`.
Instead run the whole agent **on the pod** in plain `local` mode with a CUDA
device; REINVENT runs as a normal subprocess on the pod's GPU.

1. Create a GPU pod (a PyTorch/CUDA template), add your SSH key in the RunPod
   account settings, and copy the SSH command from the dashboard. Put long-lived
   files under the persistent volume (`/workspace`).
2. On the pod, install REINVENT + the prior (once):
   ```bash
   cd /workspace
   python -m venv reinvent-venv && source reinvent-venv/bin/activate
   pip install reinvent4
   which reinvent                     # -> REINVENT_EXECUTABLE
   mkdir -p /workspace/reinvent_priors && cd /workspace/reinvent_priors
   wget <linkinvent.prior URL from Zenodo> -O linkinvent.prior
   ```
3. Put the agent on the pod and configure it for a **local GPU** run:
   ```bash
   cd /workspace && git clone <this repo> && cd Hackaton-Agentic
   pip install -e .
   cp .env.example .env               # add your ANTHROPIC/OPENAI keys
   # in .env:
   #   REINVENT_ENABLED=true
   #   REINVENT_RUN_MODE=local
   #   REINVENT_EXECUTABLE=/workspace/reinvent-venv/bin/reinvent
   #   REINVENT_PRIOR_BASE=/workspace/reinvent_priors
   ```
4. Run it on the GPU:
   ```bash
   python -m hackathon_agents.cli design-adc-linkers \
     "Design a soluble, protease-cleavable ADC linker for maleimide conjugation" \
     --run-mode full --run --device cuda:0
   ```
5. Copy results back to your laptop: `scp -r -P <port> root@<ip>:/workspace/Hackaton-Agentic/runs ./`.

No SSH/SLURM env vars (`HPC_*`, `SLURM_*`) are needed for this path — those are
only for the Snellius `slurm_remote` mode.

### Alternative: drive from your laptop with `ssh_remote`
If you'd rather keep the agent on your laptop and only offload REINVENT to the
pod, use `run_mode=ssh_remote`. The agent SSHes into the pod, uploads the config,
runs `reinvent` as a command (no scheduler), and downloads the results. Steps
1–2 above (install REINVENT + prior on the pod, note the paths) still apply, then
on your **laptop** set in `.env`:
```bash
REINVENT_ENABLED=true
REINVENT_RUN_MODE=ssh_remote
REINVENT_SSH_HOST=<pod ip>           # from the RunPod dashboard
REINVENT_SSH_PORT=<pod ssh port>
REINVENT_SSH_KEY=~/.ssh/id_ed25519   # the key registered with RunPod
REINVENT_SSH_USER=root
REINVENT_REMOTE_EXECUTABLE=/workspace/reinvent-venv/bin/reinvent
REINVENT_REMOTE_PRIOR_BASE=/workspace/reinvent_priors   # ABSOLUTE path on the pod
REINVENT_REMOTE_WORKDIR=/workspace/reinvent_runs
```
and run locally with the pod's GPU:
```bash
python -m hackathon_agents.cli design-adc-linkers \
  "Design a soluble, protease-cleavable ADC linker for maleimide conjugation" \
  --run-mode full --run --device cuda:0
```
Password auth works too (set `REINVENT_SSH_PASSWORD`, leave `REINVENT_SSH_KEY`
empty). Results land in `runs/<timestamp>/` on your laptop.

## CLI flags

| Flag | Default | Notes |
|---|---|---|
| `--run-mode` | `cheap` | Use `full` or `cheap`; `offline` disables REINVENT. |
| `--run` / `--mock` | `--mock` | `--run` actually executes REINVENT. |
| `--device` | `cpu` | Use `cuda:0` on the GPU cluster. |
| `--max-iterations` | `3` | Outer autonomous-loop budget. |

## Outputs

- `runs/<ts>/adc_paper.tex` — the paper (`pdflatex adc_paper.tex` to build).
- `runs/<ts>/state.json` — full provenance: candidates, ADC subscores, and
  `metadata.adc_decision_trail` (each critic objective edit).
- `runs/<ts>/figures/candidate_scores.png` — composite-score chart.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No module named paramiko` | `pip install -e '.[hpc]'` |
| `RemoteHPCConfig is not configured` | `HPC_HOST`/`HPC_USER` not loaded from `.env`. |
| Auth fails with password | Ensure `HPC_KEY_PATH` is **empty** so password auth is forced. |
| `submission failed: [Errno 2] No such file` | A `~` in a remote path reaching SFTP. The client now expands `~` to the cluster `$HOME` and embeds absolute paths in the config; if you still hit this, set `HPC_HOME`/`HPC_SCRATCH_PATH` to absolute paths (e.g. `/home/<you>`). |
| `Invalid account or account/partition combination` | `SLURM_ACCOUNT` is wrong. It must be a **project code**, not your username. Leave it empty to use your default project (a username is auto-dropped). |
| `Your budget is running low` / `charged for N CPUs` | Lower `SLURM_CPUS_PER_TASK` and `SLURM_MEM` (charge = `max(cpus, mem/1792 MiB)`). `8` cpus + `14G` is cheap and enough. |
| Job ends `FAILED` (see printed `stderr_tail`) | Usually `REINVENT_REMOTE_PRIOR_BASE` wrong or the prior not named `linkinvent.prior`, or `REINVENT_ENV_ACTIVATE` doesn't match cluster modules. |
| Only mock molecules returned | `--mock`, `--run-mode offline`, or `REINVENT_ALLOW_SUBMIT` not `true`. |
| Job pending forever | Wrong `SLURM_ACCOUNT`/partition or no GPU allocation. |

## Caveats

- The payload stub in `CANONICAL_WARHEAD_PAIR` is a placeholder — swap in a real payload.
- The cleavable/labile SMARTS in `adc_linker_objective.py` are illustrative; a
  chemist should review them.
- Physicochemical scores (logP, TPSA, SA, substructure presence) are surrogates,
  not assays. Candidates are computational hypotheses.
