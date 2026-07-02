# HANDOFF 4 — Autonomous Linker Discovery (Study 3 Complete & Study 4 Blueprinted)

State as of 2026-07-02. This document details the handoff parameters for **Study 3 (The Autonomous Scientist)** and the strategic setup for **Study 4 (Visualizing, Tuning, and Hierarchical Discovery)**, satisfying the remaining Merck challenge objectives.

---

## 1. Accomplishments & Current Best Deliverables

### Study 3 Symmetrical Deliverables (`deliverables/study3/`):
*   **`ADC_Linker_Study3_Paper.pdf` & `_Supplementary.pdf`:** Compiled, publication-quality academic papers documenting our Phase A, B, C, D, and E steps.
*   **`grid_results.json`:** Standardized 38-context x 2-seed genuine RL grid outputs (76 runs total), with all candidates evaluated using the updated Study 3 scoring models.
*   **`benchmark.json`:** Evaluated physical, chemical, and QED yardsticks for designs.
*   **`boltz.json`:** Validated predicted binding affinities ($K_d$) and active site docking metrics against human Cathepsin B.
*   **`figures/`:** Full diagnostic plots (Pareto frontiers, payoad ranking flips, heatmaps, Boltz affinity profiles) generated cleanly with no mock or backfilled elements.

---

## 2. Updated Codebase Features

All core package files under `src/hackathon_agents/` are fully synchronized between local Mac and the Pod, and verified with a **100% successful local unit-test pass**:

*   **`tools/predictive_scorers.py`:** Integrates the retrosynthesis step-counter and mechanism-resolved stability scorer.
*   **`tools/real_payloads.py`:** Models conjoined constructs using MMAE, siRNA, and R848 drug molecules.
*   **`tools/adc_linker_objective.py`:** Integrates our newly developed predictive scorers directly into the core `score_adc_linker` scoring function.
*   **`demos/adc_grid.py`:** Upgraded with absolute directory resolutions and safe local Pod execution bypasses to resolve all `KeyError: REINVENT_SSH_HOST` issues.

---

## 3. How to Run the Study 3 Campaign on the Pod

The Pod has a fully configured environment, and can execute the complete 76-run grid campaign (rebuilding all deliverables and PDF manuscripts) cleanly in the background.

```bash
ssh -i ~/.ssh/id_pods -p 11883 root@103.196.86.112
cd /workspace/Hackaton-agentic
PYTHONPATH=src python3 -m hackathon_agents.tools.finalize_study3
```

---

## 4. Study 4 Roadmap & Blueprint (`PLAN_STUDY4.md`)

Study 4 has been fully blueprinted to address remaining visual and scoring requirements:

1.  **Phase A — Structure Galleries (Top 1–3 Molecules):** Draw high-definition 2D diagrams of top designed candidates inside the main paper PDF using RDKit, highlighting the handle (Blue), the targeted scissile bond (Red), and spacer PEG modules (Green).
2.  **Phase B — Agent-Driven Multi-Objective Weight Tuning:** Give the agent full continuous weighting autonomy to dynamically decide and adjust `SCORE_WEIGHTS` based on the targeted payload's clinical profile.
3.  **Phase C — Hierarchical Exploration (From Cheap to Target Validation):** 
    *   **Cheap Funnel:** Broad, cheap de-novo sampling pass (e.g. 1000 SMILES) in LinkInvent sampling mode (no RL) to survey structural space.
    *   **RL Funnel:** Selected chemotypes seeded into the prior for a targeted 100-step RL campaign.
    *   **Validation:** Final conjoined structures folded inside Cathepsin B with Boltz-2.
