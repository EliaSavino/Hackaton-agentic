# PLAN — Study 4: Visualizing, Tuning, and Hierarchical Discovery (From Cheap Exploration to Target Validation)

Study 4 builds directly upon the accomplishments of **Study 3 (The Autonomous Scientist)** to satisfy the remaining Merck challenge objectives. Specifically, we address:
1.  **Suboptimal drug properties & pharmacology** (aggregation, solubility, PK);
2.  **In-silico proof points** (drawn linker structures, 3D alignments);
3.  **Cost-effective, scalable discovery workflows** (cheap de-novo exploration fanning out into target validations).

---

## 1. Study 4 Architecture: Multi-Agent Workflow

```
                        STAGE 1: CHEAP EXPLORATION
             (Broad sampling -> survey structural space, no RL)
                                     │
                                     ▼
                        STAGE 2: DYNAMIC RL TUNING
            (Agent dynamically decides and tunes scorer weights)
                                     │
                                     ▼
                         STAGE 3: TARGETED RL RUNS
                   (100 steps on selected chemotypes)
                                     │
                                     ▼
                       STAGE 4: BIOPHYSICAL VALIDATION
              (Shortlisted candidates fold vs Cathepsin B)
                                     │
                                     ▼
                          STAGE 5: VISUALIZATION
             (2D depictions of top 1-3 candidates in main PDF)
```

---

## 2. Phase A — Structure Galleries & Drawn Linkers

**Goal:** Provide full structural transparency so medicinal chemists can inspect designs.
*   **The Concept:** Create an automated tool `tools/draw_linker_constructs.py` that utilizes RDKit's `rdMolDraw2D` to output publication-quality **2D vector drawings (.svg/.png)** of the top 1 to 3 designed linkers.
*   **Highlighting Schema:**
    *   **Antibody Conjugation Handle:** Highlighted in **Blue** (e.g. maleimide head).
    *   **Scissile Cleavage Bond:** Highlighted in **Red** (e.g. the amide carbon-nitrogen bond targeted by Cathepsin B).
    *   **Spacer Module / Solubilizing Groups:** Highlighted in **Green** (e.g. PEG segments or sulfonate groups).
*   These top 1 to 3 drawn molecules are embedded directly inside the main paper PDF/manuscript, while the broader shortlist is kept as supplementary tables.

---

## 3. Phase B — Agent-Driven Multi-Objective Weight Tuning

**Goal:** Enable the agent to actively decide, re-weight, or prioritize the multi-objective scorer based on the derived design rules.
*   **The Concept:** Rather than compiling derived rules into static weights, allow the **Objective-Compiler Agent** full autonomy to dynamically decide and adjust continuous weight values for `SCORE_WEIGHTS` inside `linker_design.py` and the LinkInvent RL parameters.
*   The agent evaluates the clinical priority of the payload class (e.g., upweighting solubility for hydrophobic payloads like MMAE, or upweighting plasma stability for immunomodulators to prevent toxicity) and autonomously re-weights the optimization objective.

---

## 4. Phase C — Hierarchical Exploration (From Cheap to Target Validation)

**Goal:** Maximize search space coverage while protecting precious GPU budget.
*   **Step 1: Cheap De-Novo Exploration (The Wide Funnel)**
    *   Begin with a broad, cheap de-novo sampling pass (e.g., 500-1000 SMILES) using LinkInvent in raw sampling mode (no reinforcement learning, low CPU steps).
    *   Filter this raw pool using our RDKit med-chem alerts, retrosynthetic step-counters, and solubility proxies to identify promising chemotypes.
*   **Step 2: Targeted Reinforcement Learning (The Narrow Funnel)**
    *   Seed the reinforcement learning prior with the successful chemotypes identified in Step 1.
    *   Run the 100-step RL campaign on the selected candidates to optimize the spacer region.
*   **Step 3: Biophysical Validation**
    *   Co-fold the fully conjoined construct (conjugation handle + designed linker + drug payload) inside Cathepsin B using Boltz-2 on the RunPod GPU to verify target pocket docking and binding affinity ($K_d$).

