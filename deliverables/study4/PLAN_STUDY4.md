# PLAN — Study 4: The Reasoning Scientist (Visible · Validated · Uncertainty-Aware · Actionable)

Study 4 answers **`CRITIQUE_S3.md`** head-on. Study 3 built the *machinery* of an autonomous
scientist — an in-loop literature agent (`tools/lit_reasoning.py`), mechanism-resolved stability
and a retrosynthetic step-counter (`tools/predictive_scorers.py`), real-payload assembly
(`tools/real_payloads.py`). The reviewer's verdict was blunt: *the workflow exists, but the paper
does not yet prove the workflow **reasons***. Every conclusion still agreed with the literature,
the reasoning was hidden, and the output was a leaderboard, not a chemist's shortlist.

**The reframing (from the reviewer's overall recommendation).** The contribution is no longer
"an ADC-linker optimiser." It is **an autonomous medicinal-chemistry scientist that reads
literature, derives objectives, critiques its own reasoning, proposes synthetically realistic
molecules, plans experiments, and justifies every decision.** ADC linker design is the
*application* that demonstrates it. Study 4 makes the reasoning **visible**, **validated on
held-out literature**, **uncertainty-aware**, and **actionable**.

**What changed since Study 3 that unblocks this:** the API keys are now live
(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` present, `HACKATHON_AGENT_LLM_MODE=auto`). A smoke test of
`derive_literature_rules("cytotoxin", …)` returns real LLM-extracted exemplars, a derived rule,
and the retrieved evidence with per-chunk provenance (source · chunk · score). **The "rules were
literature-encoded, not LLM-derived" caveat that haunted Studies 2–3 is gone.** This run is
LLM-driven for real, and we log the whole chain.

---

## 0. Critique → Phase map (every point is owned)

| # | `CRITIQUE_S3` point | Study 4 phase | Headline? |
|---|---|---|---|
| 1 | Literature agent's reasoning is never shown | **P1 — Reasoning-chain artifact + figure** | ★ |
| 2 | No genuine scientific discovery; everything agrees with lit | **P2 — Held-out prediction** | ★ |
| 3 | Leave-one-paper-out should be the *central* experiment | **P2 — Held-out prediction** | ★ |
| 4 | Reports top-scoring molecules, not what a chemist would make | **P6 — Actionable shortlist + dossiers** | |
| 5 | Agent still runs a developer-defined workflow | **P4 — Agent-driven control (critic retrieves/revises/terminates)** | |
| 6 | Uncertainty is missing | **P3 — Uncertainty quantification** | |
| 7 | Only successful examples shown; no failure recovery | **P4 — Recorded recovery episode** | |
| 8 | Weak experimental prioritisation | **P6 — Dossiers: cost/duration/P(success)/info-gain** | |
| 9 | Biological realism simplified (whole conjugate) | **P7 — Hierarchical + real-construct co-fold** (partial; rest = future work) | |
| — | Chemists want to *see* structures (carried from Plan 3/4) | **P5 — Structure galleries & drawn linkers** | |

**Priority order for the sprint:** P1 + P2 are the headline (do first — they are the reviewer's
two central asks and are now unblocked). Then P3 (uncertainty) + P6 (dossiers) + P5 (structures)
turn the story into a chemist-facing deliverable. P4 (failure recovery) is the "genuine iterative
reasoning" set-piece. P7/P8 (hierarchical discovery, dynamic weight tuning — the colleague's
original Plan-4 scope) land last and reuse the Study-3 pod machinery. **The headline needs no new
pod run** — it rides on the existing `deliverables/study3/grid_results.json` + `boltz.json`.

---

## 1. Study 4 multi-agent workflow (mapped onto the DiscoveryGraph)

The graph today is `planner → chemist → tool_execution → critic → (loop|writer)` with the RAG
store **CLI-only** (not wired into any node). Study 4 wires retrieval into the loop and adds
specialised roles on the existing nodes:

```
   ┌─────────────────────────────────────────────────────────────────────┐
   │ SUPERVISOR (human: Elia) — sets payload classes, approves shortlist  │
   └─────────────────────────────────────────────────────────────────────┘
                                   │
   planner ─▶ LITERATURE/EXTRACTOR AGENT  ── P1: retrieve → extract(grounded) → derive rule(+conf)
                                   │            P2: held-out re-derivation on withheld corpus
                                   ▼
             OBJECTIVE-COMPILER AGENT ── P8: derived rule → continuous SCORE_WEIGHTS + RL params
                                   │
   chemist ─▶ GENERATION (hierarchical) ── P7: cheap de-novo funnel → filters → targeted RL
                                   │
   tool_execution ─▶ SCORERS + BOLTZ ── retro steps · mechanism stability · real-construct co-fold
                                   │
   critic ─▶ SELF-CRITIQUE + RETRIEVAL ── P3: attach confidence · P4: detect inconsistency,
                                   │        retrieve more, revise objective, or terminate
                                   ▼
   RENDERING AGENT ── P5: 2D drawn constructs (handle/scissile/spacer highlighted) + 3D + poses
                                   │
   SELECTOR/DOSSIER AGENT ── P6: 5/class dossiers (synthesis, cost, P(success), failure, validation)
                                   │
   writer ─▶ MANUSCRIPT ── P9: "autonomous med-chem scientist", ADC as application
```

---

## 2. Phase 1 ★ — Make the reasoning **visible** (critique #1)

**Goal:** the reader sees the agent think. Run `lit_reasoning.derive_literature_rules` with the
LLM **on** for cytotoxin / oligonucleotide / immunomodulator and persist the full chain as one
auditable artifact per class:

```
query  →  retrieved passages [source · chunk · score · text]
       →  extracted evidence  [grounded quote → exemplar (payload, linker, cleavage, stability)]
       →  derived design rule [cleavage_pref, rigidity, stability_priority, + rationale + CONFIDENCE]
       →  compiled scorer params [weights, cleavage regime, alerts]
       →  optimisation objective [the REINVENT config actually run]
```

- **Fix grounding (honesty guard):** the smoke test showed the extractor sometimes emits
  `"citation": "Internal Reference"` and model-memory exemplars (e.g. MMAE) instead of the
  retrieved chunk. Constrain the extractor prompt so **every exemplar must cite a retrieved
  chunk id**, and drop/flag any exemplar not traceable to a passage. This is what lets us claim
  the rule came from *the corpus*, not the model's training data.
- **Deliverable:** `reasoning_chain.json` per class + a **"reasoning waterfall" figure (Fig 1)** in
  the main paper — retrieved passage → evidence → rule → objective, as a labelled cascade. This is
  the single highest-value change; the reviewer asked for exactly this figure twice.
- **Owner:** literature/extractor agent on the `planner` node. **No pod, no RL** — pure
  RAG + LLM, runs in minutes.

## 3. Phase 2 ★ — The **held-out prediction** (critique #2, #3: the central experiment)

**Goal:** prove the agent produces a conclusion it was *not* handed. Leave-one-paper-out:

1. **Withhold** a payload class's key paper(s) from the RAG corpus (rebuild a scoped store).
2. **Re-derive** the design rule from the *remaining* corpus only.
3. **Log the prediction + confidence BEFORE revealing** the withheld paper (pre-registration).
4. **Score** the prediction against the withheld paper's stated conclusion (agree / disagree / abstain).

- **The showcase is the oligonucleotide rule.** "Rigid, *non*-cleavable is better for an
  antibody–oligonucleotide conjugate" is the *surprising*, non-default conclusion (every naïve
  linker tool assumes cleavable-is-good). If the agent predicts it **without** the ARC paper and
  the withheld ARC paper then confirms it → that is genuine, non-circular scientific reasoning.
- **Immediately runnable demonstrations (no new literature needed):**
  - *Cytotoxin* — 4 papers in corpus; withhold one, re-derive, confirm. Robust but unsurprising.
  - *Immunomodulator* — 2 papers (`ISAC`, `Immuno`); withhold `Immuno`, re-derive "plasma
    stability paramount" from `ISAC`+general, confirm with the withheld paper.
- **⚠ Literature dependency (the oligo showcase):** the corpus has **only one** ARC paper
  (`siRNA.pdf`). Withholding it leaves *zero* direct oligo evidence, so the test becomes
  "predict the oligo rule from general linker chemistry" (impressive if it works, but fragile).
  A proper *train-and-confirm* held-out test needs **≥2–3 ARC / antibody-oligonucleotide-conjugate
  papers** so the agent trains on some and is confirmed by a different withheld one. **This is the
  one place we ask Elia for more literature** (see §12).
- **Deliverable:** `heldout_predictions.json` + a **held-out results table** (predicted rule,
  confidence, withheld-paper conclusion, verdict) as the paper's central experiment.
- **Owner:** literature/extractor agent, driven by a small harness (`demos/adc_heldout.py`).

## 4. Phase 3 — **Uncertainty** everywhere (critique #6)

Scientific confidence is itself an output. Attach calibrated confidence to:

- **extracted rules** — from evidence count × source agreement (do the retrieved passages
  concur?); already have the hook (add a `confidence` field to the derivation output).
- **literature agreement** — fraction of exemplars supporting the rule vs contradicting it.
- **linker recommendations** — seed variance (have it) × margin over the runner-up context.
- **synthesis feasibility** — spread of the retro step-count estimate, flagged low-confidence when
  exotic linkages are present.

Surface as a **confidence column** in the rules table and **error bars / bands** on recommendations.
Owner: extractor + critic. Pure post-processing — no pod.

## 5. Phase 4 — **Agent-driven control & failure recovery** (critique #5, #7)

**Goal:** turn the developer-defined pipeline into an agent that decides its own next move, and
**show it recover from a mistake** (the reviewer explicitly wants a failure→recovery episode).

- **Wire RAG retrieval into the `critic` node** (today the critic can reweight the objective and
  escalate strategy, but *cannot retrieve*). Give it four levers: *retrieve more literature*,
  *reject conflicting evidence*, *revise the objective*, *terminate on a confidence threshold*.
- **Recorded recovery set-piece:** start the oligo class from a deliberately *thin/biased* corpus
  slice that yields a **wrong or low-confidence** rule (e.g. "cleavable is fine"). The critic
  detects the inconsistency (low confidence / contradiction with retrieved ARC evidence),
  **triggers targeted retrieval**, **revises the objective** to non-cleavable-rigid, and the
  **redesign improves**. Log the episode as a narrative + a before/after figure.
- **Deliverable:** `recovery_episode.json` + a short "iterative reasoning" figure/box in the paper.
- Owner: `critic` node (extended). Local; optionally one small RL redesign on the pod.

## 6. Phase 5 — **Structure galleries & drawn linkers** (chemists want structures)

**Goal:** full structural transparency. New `tools/draw_linker_constructs.py` using RDKit
`rdMolDraw2D`:

- **2D depictions (.svg/.png)** of the top 1–3 designed linkers *and* the assembled
  handle–linker–payload construct, with a highlight schema:
  - **Antibody conjugation handle → blue** (e.g. maleimide head)
  - **Scissile cleavage bond → red** (the amide C–N targeted by cathepsin B)
  - **Spacer / solubilising groups → green** (PEG, sulfonate)
- **3D structures** — RDKit ETKDG-embedded, MMFF-minimised conformers; and reuse the **Study-3
  Boltz co-fold PDB poses** to show the linker seated in the cathepsin-B pocket.
- **Placement:** top 1–3 drawn constructs embedded in the **main PDF**; the broader 5/class
  shortlist rendered as **structure cards in the SI**.
- Owner: rendering agent (RDKit; optional PyMOL/py3Dmol headless for 3D). Local, no pod.

## 7. Phase 6 — **Actionable shortlist + dossiers** (critique #4, #8)

**Goal:** replace "top-scoring molecules" with "molecules a chemist would actually make." Produce
**5 cytotoxin + 5 oligonucleotide + 5 ISAC** candidates. Each **Dossier** (formal object + LaTeX
card) carries:

- SMILES + drawn structure (from P5)
- **design rationale traced to the derived rule + the evidence passage it came from** (closes the
  loop with P1 — the rationale is auditable, not asserted)
- closest literature analogue (max Tanimoto to commercial/known linkers)
- proposed synthesis (retro step count from `predictive_scorers` + a short route sketch)
- **synthesis cost + duration estimate, probability of success, expected information gain**
- expected failure modes (mechanism-stability liabilities) + recommended validation experiments
- **confidence** (from P3)

Owner: selector/dossier agent. Local; reuses Study-3 grid candidates + scorers.

## 8. Phase 7 — **Hierarchical cheap→targeted discovery** (original Plan-4 Phase C; critique #9 partial)

Protect GPU budget by funnelling:

1. **Cheap de-novo exploration** — broad LinkInvent *sampling* (no RL, ~500–1000 SMILES, low CPU).
2. **Filter** with RDKit med-chem alerts + retro step-counter + solubility proxy → surviving chemotypes.
3. **Targeted RL** — seed the prior with survivors; ~100-step campaign on the spacer region.
4. **Biophysical validation** — co-fold the **whole conjugate** (handle + linker + real payload)
   vs cathepsin B with Boltz-2 on the pod, verifying pocket docking and $K_d$.

Owner: chemist + tool_execution nodes. **Pod-dependent** — schedule after the headline lands.

## 9. Phase 8 — **Dynamic weight tuning** (original Plan-4 Phase B; critique #5)

Give the **objective-compiler agent** full continuous autonomy over `SCORE_WEIGHTS` and the
LinkInvent RL parameters, deciding weights from payload pharmacology (up-weight solubility for
hydrophobic MMAE; up-weight plasma stability for immunomodulators to bound cytokine toxicity)
rather than compiling to fixed presets. The chosen weights become part of the P1 reasoning chain
(so weight choices are *also* justified from literature). Owner: objective-compiler on the
`chemist`/`planner` boundary.

## 10. Phase 9 — **Writer + supervisor** (the reframing)

Rewrite the manuscript as **"an autonomous medicinal-chemistry scientist,"** with ADC linker design
as the demonstrating application. Main paper (5 pp): reasoning-chain figure (P1), held-out
prediction as the central result (P2), structure gallery (P5), dossier table + uncertainty (P3/P6),
Boltz proof point reframed as *substrate recognition, not cleavage* (carried honesty guard). SI:
full reasoning chains, held-out details, all 15 dossiers, recovery episode, per-context data.
Human appears only as supervisor. Owner: `writer` node + human.

---

## 11. Honesty guards to carry forward (why reviewers trust us)

- **Physicochemistry dominates** the composite; the compact non-cleavable cap wins on raw
  drug-likeness under *every* payload rule. We do **not** claim "cleavable wins for cytotoxins."
  The demonstrable result is payload-dependent *re-scoring* (Val-Cit 0.70→0.45 under the oligo rule).
- **Boltz ipTM does not discriminate** substrates (everything docks); predicted $K_d$ does. Frame
  as **substrate recognition / structural plausibility**, never as proof of enzymatic cleavage.
- **Held-out honesty:** log the prediction **before** revealing the withheld paper; report abstain
  and disagree outcomes, not just the wins. A held-out test that only ever confirms is not a test.
- **Grounding:** every extracted exemplar must trace to a retrieved chunk id, or it is flagged.

## 12. Literature ask (the one open dependency)

To make the **oligonucleotide leave-one-paper-out** a proper train-and-confirm held-out test
(§3), the corpus needs **≥2–3 more antibody–oligonucleotide-conjugate papers** (siRNA-/ASO-ADC or
ARC) that discuss **linker cleavability and plasma stability** — so the agent can train on some
ARC evidence and be confirmed by a *different* withheld ARC paper. **Nice-to-have:** 1–2 further
ISAC / immune-stimulating-conjugate papers to thicken that class. Cytotoxin coverage (4 papers) is
already sufficient. Everything else in Study 4 runs on the existing corpus + Study-3 artifacts.

## 13. Execution order (sprint)

1. **P1** reasoning-chain artifacts + Fig 1 (now; LLM on) — *headline, unblocked.*
2. **P2** held-out cytotoxin + ISAC demonstrations now; oligo showcase once literature arrives.
3. **P3** uncertainty pass over P1/P2 outputs.
4. **P5** structure-drawing tool → gallery from Study-3 candidates.
5. **P6** dossiers for 5/class.
6. **P4** failure-recovery episode.
7. **P9** write Study 4 manuscript; compile PDFs.
8. **P7/P8** hierarchical discovery + dynamic weights on the pod (if time).
