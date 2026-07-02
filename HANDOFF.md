# HANDOFF — ADC Linker Design (state as of 2026-07-01, late)

Pick-up notes for whoever continues this. The 48h Merck hackathon problem
(`data/problemprompt.txt`) is **solved end-to-end**: literature → warhead
libraries → REINVENT linker design → autonomous scoring/re-seed → 5-page paper.

## TL;DR — the deliverable is done

- **The paper:** `deliverables/ADC_Linker_Design_Paper.pdf` (5 pages, publication-ready, real data).
- Everything committed on `main` (latest: `42217da "first full campaign"`).
- Reproduce the whole thing in one command:
  ```bash
  python -m hackathon_agents.cli design-adc-campaign --run --device cpu
  ```

## What runs where

- **Agent env (use this Python):** `/Users/es/miniforge3/envs/hackathon-agents/bin/python`
  (has paramiko + rdkit + hackathon_agents). Prefix package runs with `PYTHONPATH=src`.
- **REINVENT** runs on a rented **RunPod GPU box over SSH** (config in `.env`:
  `REINVENT_RUN_MODE=ssh_remote`, host `103.196.86.112:11883`, key `~/.ssh/id_pods`).
  - The pod GPU is UNUSABLE (torch cu130 vs driver 550 → "driver too old"), so we run
    **CPU** (`--device cpu`). It's auto-tuned (thread cap) and fine: ~8 min per warhead pair.
  - RunPod gotcha: must use the **direct-TCP** endpoint (real IP + high port), NOT the
    `ssh.runpod.io` proxy (proxy has no SFTP → "Channel closed").
- **LaTeX:** `pdflatex` is installed locally (`/Library/TeX/texbin`). The paper compiles here.

## The pipeline (what each piece does)

1. **Literature** → `data/rag.sqlite` (already ingested: 4 ADC reviews, 125 chunks).
   Re-ingest: `python -m hackathon_agents.cli rag-ingest <pdf> --db-path data/rag.sqlite`.
2. **Warhead libraries** → `src/hackathon_agents/tools/generate_linker_libraries.py`
   reads `data/linkers.csv` (3,679 reagents) and writes:
   - `data/linkers/Library_A_Antibody_Ends.csv` (699 conjugation handles)
   - `data/linkers/Library_B_Payload_Triggers.csv` (16 cleavable triggers)
3. **Campaign** → `src/hackathon_agents/demos/adc_campaign.py` (`run_campaign`,
   `DEFAULT_CAMPAIGN` = 4 warhead pairs). Runs the existing `design-adc-linkers`
   autonomous loop once per pair. Warheads are LinkInvent `w1(*)|w2(*)` strings.
4. **Re-aggregate** → `src/hackathon_agents/demos/adc_reaggregate.py` re-reads each
   pair's full `state.json`, filters to genuine assembled linkers (RDKit trigger match),
   writes `campaign_clean.json`.
5. **Paper** → `src/hackathon_agents/tools/adc_campaign_paper.py` (`build_campaign_paper`,
   `twocolumn` flag) → LaTeX + 3 matplotlib figures. 10pt single-column = 5 pages.
6. **One command that chains 3–5:** CLI `design-adc-campaign` (in `cli.py`).

## Files I added / changed this session

- **new:** `src/hackathon_agents/demos/adc_campaign.py`, `.../demos/adc_reaggregate.py`,
  `src/hackathon_agents/tools/adc_campaign_paper.py`, `tests/test_adc_campaign.py`,
  `deliverables/` (paper + figures + libraries + `campaign_results.json` + README).
- **edited:** `agents/planner.py` + `agents/critic.py` (thread `adc_warhead_pair` so the
  warhead pair is no longer hardcoded), `cli.py` (added `--warhead-pair` to
  `design-adc-linkers`, and the new `design-adc-campaign` command),
  `tools/generate_linker_libraries.py` (input path fix: `data/linkers.csv`).

## Latest results (this run: `runs/campaign_20260701_214434/`)

- 200 assembled linkers across 4 conjugation chemistries; all auto-escalated sampling→RL.
- **Best: maleimide–Val-Ala-PABC, composite 0.78** (solubility 0.92, stability 1.0, cleav 1.0).
- Val-Ala > Val-Cit (citrulline bulk hurts); DBCO lowest (0.57, big dibenzocyclooctyne).

## Known issues / next steps

- **3 pre-existing test failures, NOT ours:** `test_config` (×2) — working-tree
  `configs/agents.yaml` pins `opus-4.6` but tests expect `sonnet-4-6`; and a
  `test_cli_smoke` rich help-wrapping flake. Our new tests + all REINVENT/ADC tests pass
  (`pytest tests/test_adc_campaign.py tests/test_reinvent_tools.py` → green).
- **Scorer is a fast surrogate** (cLogP/TPSA + substructure alerts, not measured). The
  obvious upgrades, all already pluggable in the framework: Boltz-2 co-folding of the
  assembled ADC fragment, explicit cathepsin-cleavage / plasma-stability modelling,
  real synthetic-route scoring. RL budget was CPU-capped (60 steps/stage) — bump it if a
  working GPU pod appears.
- **More warhead pairs:** edit `DEFAULT_CAMPAIGN` in `adc_campaign.py` (Library A has
  NHS-ester/azide/oxyamine handles unused; Library B has Phe-Lys-PABC too).

## ROUND 2 — Design grid + commercial benchmark + Boltz proof point (2026-07-02)

Second, deeper study on top of Round 1. Deliverables in `deliverables/study/`:
`ADC_Linker_Study_Paper.pdf` (5pp main) + `ADC_Linker_Study_Supplementary.pdf` (2pp) +
figures + `grid_results.json` / `benchmark.json` / `boltz.json`.

**What it is:** a *controlled* sweep — 6 conjugation chemistries × 4 trigger classes × 3
seeds = **72 real REINVENT staged-learning runs**, objective held FIXED so differences are
attributable to warhead chemistry. Then a non-circular evaluation: commercial-linker
benchmark on independent yardsticks (QED, physchem, Morgan novelty), a stability-surrogate
calibration table, and a **Boltz-2 structural proof point** (co-fold designed + commercial
linkers vs cathepsin B).

**New code:**
- `demos/adc_grid.py` — the grid (6 handles × 4 triggers), resumable + incremental
  (`records.jsonl`), parallel SSH sweep. `run_grid(...)`.
- `tools/linker_benchmark.py` — commercial linkers + yardsticks + novelty + calibration.
- `tools/adc_analysis.py` — grid stats + 5 matplotlib figures.
- `tools/adc_study_paper.py` — 5pp main + supplementary (authored per AUTHORS.md).
- `demos/adc_study.py` — `finalize_study(grid.json)`: Boltz panel → benchmark → paper.
- `tools/boltz_tools.py` — new **`ssh_remote`** mode + Boltz-2 YAML writer (see
  `boltz-pod-ssh-integration` memory; pod venv `/workspace/boltz_venv`, `--no_kernels`).
- `reinvent_tools.py` — uuid suffix on remote job dir (concurrency-safe).
- Tests: `tests/test_boltz_ssh.py`, extended `tests/test_adc_campaign.py`.

**Key results:** 72/72 real, 0 failures; low seed variance (SD 0.003–0.03 → robust). Best
context Oxyamine/Non-cleavable (mean 0.84); best protease trigger is **Val-Ala** (beats
Val-Cit's citrulline bulk); **glucuronide is drug-likeness-penalised** (~0.07, honest
finding). Designed linkers Pareto-dominate commercial ones on the optimised objective but
**trail on synthesizability** (the honest trade-off). Boltz: designed protease linkers reach
cathepsin-B interface **ipTM 0.70–0.82**, just behind the clinical mc-Val-Cit control (0.87)
— positive-control validation. Calibration: surrogate correctly flags hydrazone as least
plasma-stable.

**IMPORTANT lessons for re-running the grid (hard-won):**
- The pod is **shared** — cleavable jobs (MatchingSubstructure scoring is CPU-heavy) slow
  down badly under high concurrency. Use `max_workers=5`, `steps=40`, `batch=32`,
  `timeout_seconds=1800`. 8-way + 60 steps → timeouts (empty-error failures, all cleavable).
- **Always clean pod orphans before/after** a killed run: `pkill -9 -f reinvent` over SSH.
  A killed orchestrator leaves remote REINVENT procs running that oversubscribe the box.
- Long jobs must be **detached** (`( nohup python ... & )`) — harness background jobs get
  killed. The grid is resumable (`resume_dir=`), so a kill just means re-run to continue.

**Re-run the whole study:**
```bash
# grid (detached, resumable) — see /Users/es/.claude/jobs/.../tmp/run_grid_full.py
python -c "from hackathon_agents.demos.adc_grid import run_grid; run_grid(seeds=(0,1,2), steps=40, batch=32, max_workers=5, resume_dir='runs/grid_war2')"
# then finalize (Boltz + benchmark + paper)
python -c "from hackathon_agents.demos.adc_study import finalize_study; finalize_study('runs/grid_war2/grid.json')"
```

## Fast smoke test (confirm the pod + REINVENT still work)

```bash
PYTHONPATH=src /Users/es/miniforge3/envs/hackathon-agents/bin/python -m hackathon_agents.cli \
  design-adc-linkers "protease-cleavable ADC linker" --run --device cpu --max-iterations 1 \
  --reinvent-steps 20
```
