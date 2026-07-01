# Autonomous ADC Linker Design (REINVENT4 LinkInvent)

This workflow designs antibody-drug conjugate (ADC) **linkers**: the fragment
that connects a fixed antibody-side conjugation handle to a fixed payload. The
agent generates linkers with **REINVENT4 LinkInvent**, scores them against a
multi-objective ADC profile, and — as an autonomous critic — reweights that
objective between rounds. It finishes by writing a ~5-page LaTeX paper.

- Scientific engine: REINVENT4 LinkInvent (generates the linker between two warheads).
- Autonomy: the critic edits a compact goal profile (weights + constraint toggles) each pass.
- Output: candidates, an auditable decision trail, and `adc_paper.tex`.

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

### Run
```bash
python -m hackathon_agents.cli design-adc-linkers \
  "Design a soluble, protease-cleavable ADC linker for maleimide conjugation with high plasma stability" \
  --run-mode full --run --device cuda:0
```

The agent connects over SSH, uploads the config + a SLURM script, submits with
`sbatch`, polls every `HPC_POLL_INTERVAL` seconds until the job finishes,
downloads the CSV output, scores the linkers, possibly reweights and loops, and
writes the paper.

### Dry run first (recommended)
Before spending GPU hours, confirm the SSH + staging works without submitting:
set `REINVENT_ALLOW_SUBMIT=false` and run the same command. It connects, writes
the SLURM script locally, and returns mock molecules.

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
| Job ends `FAILED` (see printed `stderr_tail`) | Usually `REINVENT_REMOTE_PRIOR_BASE` wrong or the prior not named `linkinvent.prior`, or `REINVENT_ENV_ACTIVATE` doesn't match cluster modules. |
| Only mock molecules returned | `--mock`, `--run-mode offline`, or `REINVENT_ALLOW_SUBMIT` not `true`. |
| Job pending forever | Wrong `SLURM_ACCOUNT`/partition or no GPU allocation. |

## Caveats

- The payload stub in `CANONICAL_WARHEAD_PAIR` is a placeholder — swap in a real payload.
- The cleavable/labile SMARTS in `adc_linker_objective.py` are illustrative; a
  chemist should review them.
- Physicochemical scores (logP, TPSA, SA, substructure presence) are surrogates,
  not assays. Candidates are computational hypotheses.
