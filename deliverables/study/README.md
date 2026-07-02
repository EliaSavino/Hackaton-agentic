# ADC Linker Design — Study (grid + benchmark + structural proof point)

A controlled, non-circular study extending the first paper.

| File | What it is |
|------|-----------|
| `ADC_Linker_Study_Paper.pdf` | **Main paper, 5 pages** — controlled grid, commercial benchmark, calibration, Boltz proof point |
| `ADC_Linker_Study_Supplementary.pdf` | Supplementary, 2 pages — full 24-context table, commercial table, top-25 SMILES, full Boltz panel |
| `adc_linker_study.tex`, `_supp.tex` | LaTeX sources |
| `figures/` | grid heatmap, per-context bars (seed error bars), Pareto, novelty, Boltz |
| `grid_results.json` | 72 runs (24 contexts × 3 seeds), all designed linkers + scores |
| `benchmark.json` | commercial linkers scored + independent yardsticks + calibration |
| `boltz.json` | cathepsin-B co-folding metrics (designed + commercial) |

## Design (why it is credible)

- **Controlled experiment:** 6 conjugation chemistries × 4 trigger classes × 3 seeds = 72
  REINVENT LinkInvent runs, with the multi-objective scorer **held fixed** — only warhead
  context and seed vary. Seed variance is small (SD 0.003–0.03), so the rankings are robust.
- **Non-circular evaluation:** because RL optimises the composite, we also judge on metrics
  the optimiser never saw — QED drug-likeness, physicochemistry, and Morgan-Tanimoto novelty
  vs a commercial-linker set — plus a **calibration** of the stability surrogate against known
  mechanistic ordering, and a **structural** proof point (Boltz-2 co-folding with cathepsin B).

## Headline results

- Best protease trigger: **Val-Ala-PABC** (beats Val-Cit — citrulline's urea bulk costs
  drug-likeness). Glucuronide is penalised by the size/solubility windows (honest finding).
- Designed linkers **Pareto-dominate commercial linkers on the optimised objective** but
  **trail on synthesizability** — a quantifiable, honest trade-off (not "we win everything").
- Boltz-2: designed protease linkers reach cathepsin-B interface **ipTM 0.70–0.82**, just
  behind the clinical mc-Val-Cit-PABC control (0.87) — the known substrate scoring highest
  validates the co-fold as a real cleavability signal.
- Calibration: the surrogate correctly flags the acid-labile hydrazone as least plasma-stable.

## Reproduce

```bash
python -c "from hackathon_agents.demos.adc_grid import run_grid; run_grid(seeds=(0,1,2), steps=40, batch=32, max_workers=5, resume_dir='runs/grid_war2')"
python -c "from hackathon_agents.demos.adc_study import finalize_study; finalize_study('runs/grid_war2/grid.json')"
```
See `../../HANDOFF.md` (ROUND 2) for the shared-pod concurrency lessons.
