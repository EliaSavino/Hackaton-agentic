# Study 2 — Revised Plan: Payload-Class-Aware ADC Linker Design

Revision driven by chemist review of Study 2. The core critique: the scorer is
**implicitly built for cytotoxin delivery**, but modern ADCs carry *non-traditional
payloads* (oligonucleotides, immunomodulators) whose linker requirements can **invert**.
We make the agentic system payload-aware and prove it handles all three classes.

## What the chemist asked for (and our answer)

1. **"Model is implicitly built for cytotoxin delivery — include non-traditional payloads
   and score linkers by payload class."** → New payload-class-aware scoring. A literature
   step decides, per payload class, whether cleavability is desired and which regime to
   favour; that decision parameterises the multi-objective scorer.
2. **"An agent could filter the literature and assess whether cleavability is important
   per application."** → `PayloadLiteratureAgent` / `derive_payload_rules()`: retrieves the
   payload-relevant passages and emits a design rule (cleavage preference, rigidity,
   stability priority) with citations. LLM-derived when an API key is present; otherwise
   the literature-encoded rules (grounded + cited) are used. This run: no key → encoded.
3. **"Add tetrazine + trans-cyclooctene (IEDDA) to Library A conjugation handles?"** → Yes.
   Tetrazine `*c1nnc(C)nn1`, TCO `*NC(=O)OCC1CCCC=CCC1`. 8 handles total.
4. **"Include non-cleavable linker types for novel payloads?"** → Yes. Added a
   **Non-cleavable-rigid** trigger `*C1CCC(CN)CC1` (the sulfo-SMCC cyclohexane, the
   ARC-favoured motif), alongside the existing flexible non-cleavable control.
5. **"Added biological context to the introduction."** → Paper intro rewritten with the
   ARC / ISAC biology and the payload-dependent linker logic.

## The three payload classes (literature-grounded rules)

| Payload class | Cleavage regime | Rigidity | Plasma stability | Basis |
|---|---|---|---|---|
| **Cytotoxin** (MMAE/DM1/DXd) | **reward cleavable** (bystander release) | moderate | standard | Val-Cit/GGFG ADCs; T-DM1 non-cleavable also valid |
| **Oligonucleotide** (siRNA/ASO, "ARC") | **penalize cleavable → favour non-cleavable** | **rigid** | high | Antibody–siRNA conjugate, rigid **sulfo-SMCC**, non-cleavable (Bioconjugate Chem. 2025) |
| **Immunomodulator** (TLR7/8, "ISAC") | reward cleavable **but** stability **paramount** | moderate | **paramount** (systemic release → cytokine toxicity) | R848/Val-Cit ISAC; controlled TME release (Mol. Pharm. 2022; Front. Pharmacol. 2023; J. Med. Chem. 2025) |

Cleavage/trigger reconciliation (payload preference × what the trigger presents):
- **penalize** payload (oligo): cleavable trigger → penalised; non-cleavable → rewarded.
- **reward** payload (cytotoxin/immuno): cleavable trigger → rewarded; non-cleavable →
  *ignored* (a valid alternative design, not penalised).

Mechanically: a new `cleavage_preference ∈ {reward, penalize, ignore}` on `ADCGoalProfile`.
`penalize` adds a REINVENT `CustomAlerts` on the cleavable SMARTS (and inverts the offline
cleavability subscore); rigidity tightens the rotatable-bond window + up-weights flexibility;
stability priority up-weights the stability term and keeps the hard labile-alert filter on.

## The revised grid (controlled, bounded ≈ Study-2 scale)

Explicit curated union of cells `(handle, trigger, payload)`, deduped, 2 seeds:

- **Block 1 — conjugation-chemistry sweep (extends Study 2 with IEDDA), payload = cytotoxin.**
  8 handles {Maleimide, Bromoacetamide, DBCO, Disulfide, NHS-ester, Oxyamine, **Tetrazine**,
  **TCO**} × 3 triggers {Val-Cit-PABC, β-glucuronide, Non-cleavable} = 24 contexts.
  → answers "do the two new IEDDA handles hold up, and does the conjugation ranking survive?"
- **Block 2 — payload-class sweep (the headline).** 2 representative handles {Maleimide, DBCO}
  × 3 triggers {Val-Cit-PABC, Non-cleavable-rigid, Non-cleavable} × 3 payloads
  {cytotoxin, oligonucleotide, immunomodulator} = 18 cells; 4 overlap Block 1 → +14 contexts.
  → shows the **same contexts re-rank** across payload classes: cleavable wins for cytotoxin,
  non-cleavable-rigid wins for oligonucleotide, cleavable-but-stable for immunomodulator.

Total ≈ **38 contexts × 2 seeds ≈ 76 REINVENT staged-learning runs** (Study 2 was 72).
Objective family held fixed *within a payload class*; only the payload profile, warhead
context, and seed vary — still a controlled experiment, now with payload as the top lever.

## Non-circular evaluation (unchanged spine + payload facets)

- Independent yardsticks (QED, physchem, Morgan novelty) vs an **expanded commercial set**
  that now includes non-cleavable (MCC/SMCC) and the ARC/ISAC-relevant references.
- Stability-surrogate calibration (hydrazone flagged least stable) — unchanged.
- **Boltz-2 structural proof point**, now payload-aware: protease-cleavable designs co-fold
  with **cathepsin B** (cleavage should be recognised → high ipTM), and the **oligo-optimal
  non-cleavable-rigid** design is co-folded as a negative control (should NOT be recognised).

## Pipeline / commands (same hard-won pod discipline)

```bash
# 0. clean any pod orphans first
ssh pod 'pkill -9 -f reinvent || true'
# 1. grid (detached, resumable) — payload-aware cells, 2 seeds, max_workers=5
python -c "from hackathon_agents.demos.adc_study2 import run_study2_grid; run_study2_grid(resume_dir='runs/grid_war3')"
# 2. finalize: payload-aware Boltz panel + benchmark + paper (main + supp)
python -c "from hackathon_agents.demos.adc_study import finalize_study; finalize_study('runs/grid_war3/grid.json')"
```

Pod rules (from Study 2, still in force): shared box → `max_workers=5`, `steps=40`,
`batch=32`, `timeout=1800`; always `pkill -9 -f reinvent` orphans; run detached
(`( nohup … & )`) because harness background jobs get killed; the grid is resumable.

## Deliverable

`deliverables/study2/` — 5-page main paper (payload-aware story) + supplementary, figures,
`grid.json` / `benchmark.json` / `boltz.json`, README. Authored per `AUTHORS.md`.
