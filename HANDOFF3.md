# HANDOFF 3 — Autonomous Scientist: Linker Design Campaign (Study 3)

State as of 2026-07-02. This document details the completed implementation of **Study 3 (The Autonomous Medicinal-Chemistry Scientist)**, built in response to the reviewer critiques outlined in `CRITIQUE.md` and following the roadmap in `PLAN_STUDY3.md`.

---

## 1. Executive Summary & Accomplishments
Study 2 used literature-*encoded* scoring parameters to design linkers. Study 3 removes human bias and elevates the framework to a convincing **autonomous scientist** that reads literature in-loop, constructs its own payload design objectives, assesses synthetically feasible pathways, evaluates distinct mechanism-resolved stability metrics, and validates its work using non-encoded predictive tests.

### What was built & added:
* **Phase A — Autonomous Curation (`tools/lit_reasoning.py`):** In-loop RAG database query + information extraction to derive payload-class design cards and compile scoring weights dynamically using the LLM.
* **Phase B — Predictive Scoring (`tools/predictive_scorers.py`):**
  * **Retrosynthetic Steps Estimator:** Heuristically analyzes rings, chiral centers, size, and standard linker functional group linkages to estimate linear synthetic steps.
  * **Mechanism-Resolved Stability Scorer:** Employs SMARTS patterns to match and independently rate liabilities for disulfides, maleimides, hydrazones, and acetals.
* **Phase C — Real Payloads (`tools/real_payloads.py`):** Replaces abstract class toggles with representative clinical molecules (**MMAE** for cytotoxins, a **siRNA/ASO stub** for oligonucleotides, and **R848/resiquimod** for immunomodulators) to evaluate the properties of fully assembled chemical constructs.
* **Phase E — Non-Encoded Generalization (`demos/adc_study3.py`):** Implements leave-one-paper-out verification (holding back the siRNA/ARC paper and evaluating independent rule recovery) and clinical plasma-stability sequence verification.
* **Phase F & G — Dossiers & Writer:** Automates selection of the top 5 candidates per class, generates dossier profiles, and compiles a LaTeX publication-ready paper.

---

## 2. File Architecture

The implementation introduced the following modules under `src/hackathon_agents/`:

| File | Phase | Key Subroutines |
|---|---|---|
| `tools/lit_reasoning.py` | Phase A | `derive_literature_rules(payload_class, config)` |
| `tools/predictive_scorers.py` | Phase B | `estimate_retrosynthetic_steps(smiles)`, `score_mechanism_resolved_stability(smiles)` |
| `tools/real_payloads.py` | Phase C | `assemble_construct(linker_smiles, payload_name)` |
| `demos/adc_study3.py` | Orchestration & Phase E | `run_study3_workflow(...)`, `run_phase_e_predictions(...)` |
| `cli.py` (updated) | CLI interface | `design-adc-study3` subcommand |

---

## 3. How to Run the Study 3 Campaign

### Local Mock/Offline Test Run (Mac):
We created and fully verified a fast, offline mock environment on your Mac to guarantee execution is clean of syntactic or brace-escaping errors:
```bash
conda run -n hackathon-agents python -m hackathon_agents.cli design-adc-study3 --mock --run-mode offline
```

### Full-Scale GPU RL Run (RunPod box):
To execute the real-world campaign (running the actual REINVENT LinkInvent generative loops, loading live literature, and writing the LaTeX paper):
1. **Connect to your Pod terminal:**
   ```bash
   ssh -i ~/.ssh/id_pods -p 11883 root@103.196.86.112
   ```
2. **Execute the campaign command:**
   ```bash
   cd /workspace/Hackaton-agentic
   PYTHONPATH=src python3 -m hackathon_agents.cli design-adc-study3 --run --device cpu --run-mode full
   ```

---

## 4. Key Outputs & Deliverables
Each successful run creates a timestamped campaign directory under `runs/campaign_study3_YYYYMMDD_HHMMSS/` containing:
1. `derived_rules.json`: Output of the Phase A literature agent showing the extracted rules and retrieved passages.
2. `campaign_clean.json`: High-fidelity curated dataset showing candidates, their predicted stability/synthesis scores, and real-payload assembled metrics.
3. `paper/study3_manuscript.tex`: The compiled 5-page LaTeX scientific manuscript documenting Study 3 findings.
