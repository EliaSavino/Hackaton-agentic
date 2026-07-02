# Reviewer 2 — Critique of the ADC Linker Program (Studies 1–4) and the Study 4 Plan

Scope: I read `data/problemprompt.txt`, the full plan/handoff evolution (`PLAN.md`,
`PLAN_STUDY2.md`, `PLAN_STUDY3.md`, `PLAN_STUDY4.md`, `HANDOFF{,2,3,4}.md`), the two prior
external reviews (`CRITIQUE.md`, `CRITIQUE_S3.md`), the shipped Study 3 deliverables, **and the
source code that actually produced them**. Unlike the earlier reviews, this one is written with
code access, so it is about *what the pipeline really does* versus *what the manuscript claims*.

**Bottom line:** the narrative arc (payload-aware → autonomous scientist → visualize/tune) is
excellent and the right direction. But Study 3 as shipped presents **mock and hard-coded values
as scientific results**, and the Study 4 plan builds new features on top of that unvalidated
foundation without fixing it. Before the buddy runs Study 4, the integrity issues in Part I must
be closed, or every downstream claim inherits the defect. Study 4's own scope (Part II) also does
not address a single one of the nine points the external reviewer raised in `CRITIQUE_S3.md`.

---

## Part I — Integrity blockers (verified in code; fix before any Study 4 claim)

These are not stylistic. Each is a place where the manuscript/deliverable asserts a result that
the code does not actually compute. The team's own HANDOFFs repeatedly stress "honesty guards" —
these violate them.

### I.1 The Boltz "structural proof" in Study 3 is fabricated data
- `deliverables/study3/boltz.json` reports `Kd = 45 nM` (designed cleavable) and `Kd = 999 nM`
  (non-cleavable), `iptm` 0.85/0.25. These are **exactly** the hard-coded mock constants in the
  `except` branch of `demos/adc_study3.py:308-311` (`45.0 if p_class != "oligonucleotide" else
  999.0`). They are what the code emits **when Boltz fails / is not installed**, not measured
  predictions.
- The shipped non-cleavable SMILES `O=C1C=CC(=O)N1c1ccc(CO)cc1` is one of the **hard-coded mock
  linkers** from `adc_study3.py:153-157`, not a designed molecule.
- The `boltz.json` labels (`Maleimide/Val-Cit-PABC`) don't even match the labels the Study 3
  panel produces (`cytotoxin_cand_0`, `adc_study3.py:265`) — so the deliverable's Boltz block was
  not produced by the Study 3 code path at all; it was carried over/reassembled.
- The manuscript (`README.md`, `study3_manuscript.tex`) presents `Kd ≥ 999 nM` as "solid
  biophysical validation" and "complete non-substrate rejection." **This is presenting a mock
  fallback constant as an experimental result.** Highest-severity issue.

**Required fix:** the Boltz panel must run for real (pod GPU, `/workspace/boltz_venv`,
`--no_kernels`, as documented in `HANDOFF.md`), assert `status == "completed"` (not `"mock"`),
and the paper builder must **refuse to emit** any affinity claim whose source record has
`status == "mock"` or `ok == False`. If GPU is unavailable, the number cannot appear as a result
— label it explicitly "illustrative / not run."

### I.2 The Phase E "non-encoded prediction" — the headline claim — is not a test
The whole rebuttal to external-reviewer point #2 ("conclusions follow from construction") rests on
Phase E. In `adc_study3.py:232-254`:
- **E3 is literally `e3_pass = True`** (line 240) with the comment "verified via ... SMARTS
  matching." Nothing is computed. The manuscript reports "recovers clinical safety sequence
  zero-shot." It is a hard-coded `True`.
- **E1 does not withhold anything.** It calls `derive_literature_rules("oligonucleotide", ...)`
  against the *full* `rag.sqlite` (no leave-one-out split anywhere), then checks whether the
  returned string equals `"non-cleavable-rigid"` (line 237). There is no train/test separation,
  so it cannot test generalisation.
- Worse: when the LLM output fails to parse, `lit_reasoning.py:167-175` **hard-codes** the
  oligonucleotide rule to `cleavage_preference = "non-cleavable-rigid"`. So E1 can "pass" by
  comparing a constant to itself. The prediction and the ground truth are the same hard-coded
  string.

**Required fix:** E1 must (a) build a *reduced* RAG store with `siRNA.pdf` genuinely removed,
(b) run derivation against only that store, (c) persist the retrieved chunks + raw LLM completion
as artifacts, (d) compare to the withheld conclusion. E3 must actually score real clinical linker
SMILES through `score_mechanism_resolved_stability` and assert the ordering programmatically. If
either can't be done for real, the claim is deleted, not stubbed.

### I.3 Phase A "derived rules" never reach the optimiser (they're decorative)
`adc_study3.py:103` fetches `rules = derived_rule_cards[p_class]["rules"]` — and then never uses
it. The REINVENT objective is built from `warhead_pair` only (`build_adc_linkinvent_objective`,
lines 106-125, which is also **duplicated verbatim** — a copy-paste bug). The "autonomous
literature reasoning → compiled objective" pipeline that is the paper's entire thesis is **not
wired**: the agent's rules do not change what REINVENT optimises. This is the exact defect the
external reviewer flagged in `CRITIQUE.md#1` and `CRITIQUE_S3.md#1`, still unfixed and now masked
by a manuscript that claims it is fixed.

**Required fix:** the derived rule must parameterise the objective (cleavage preference → the
`CustomAlerts`/subscore inversion that already exists in `adc_linker_objective.py`; rigidity →
rotatable-bond window; stability priority → weight). Otherwise drop the "compiled objective"
claim. Also delete the duplicated objective block.

### I.4 "Real payloads" (Phase C) do not influence any score
`real_payloads.assemble_construct` joins linker and payload with a `.` (`real_payloads.py:49`) —
that is a **disconnected mixture** in SMILES, not a covalent conjugate. And the assembled
descriptors are never used: the ranking score is
`overall = 0.4*synth + 0.4*stab + 0.2` (`adc_study3.py:171`) — payload hydrophobicity/charge/size
enter **nowhere**. So "optimise around real payloads" (rebuttal to `CRITIQUE.md#6`) is not
happening; the payload is cosmetic. Also `siRNA` is a ~12-atom nucleotide stub, not an
oligonucleotide.

**Required fix:** either (a) form a real covalent bond at the attachment point and feed
conjugate-level logD/aromatic load into the objective, or (b) remove the "payload-aware
optimisation" claim and describe it honestly as post-hoc annotation.

### I.5 "Retrosynthesis" is a descriptor formula, not retrosynthesis
`PLAN_STUDY3.md §3` specified AiZynthFinder (real USPTO routes) as the *highest-priority* fix and
the "biggest credibility win." What shipped (`predictive_scorers.estimate_retrosynthetic_steps`)
is `base_steps = 2 + n_amides + 1.5*n_disulfides + ... + (MW-300)/100`, clamped to 2–12. There is
no route search, no building-block lookup, no reaction. The manuscript's "closed the
synthesizability gap, reduced from 11 steps to 4–7 steps" is a statement about an arbitrary
weighted count, not a synthesis.

**Required fix:** integrate AiZynthFinder (pip-installable, as the plan already scoped) for the
shortlist, OR rename the metric honestly ("heuristic complexity index") and stop reporting "linear
synthetic steps" / "routes."

### I.6 Silent mock substitution throughout
Multiple layers silently replace real output with fixed constants: mock SMILES
(`adc_study3.py:153-157`), mock Boltz (I.1), mock rules (I.2), `LLM_MODE=auto` (not `always`, per
`.env`) which — per your own `HANDOFF2 §6` — falls back to deterministic logic without failing.
The net effect is a pipeline that **cannot tell the operator when it stopped doing real science.**
No run artifact records `status: mock` in a way the paper builder checks.

**Required fix (single highest-leverage process change):** a provenance gate. Every number that
reaches LaTeX carries a `source ∈ {measured, llm, heuristic, mock}` tag; the paper builder
asserts no `mock` tag survives into a *results* claim and prints a provenance table in the
supplementary. Run with `HACKATHON_AGENT_LLM_MODE=always` for any run whose paper claims LLM
derivation, and persist the raw completions.

---

## Part II — Critique of the Study 4 plan itself

`PLAN_STUDY4.md` proposes three things: (A) 2D structure drawings, (B) agent-driven dynamic weight
tuning, (C) hierarchical cheap→targeted funnel. Assessed individually:

### II.1 It answers none of the external reviewer's open Study 3 asks
`CRITIQUE_S3.md` listed 9 gaps: real held-out prediction (#2/#3), a shortlist a chemist would
actually pick vs top-scoring (#4), autonomous control flow (#5), **uncertainty** (#6),
**failure-recovery narrative** (#7), richer experimental prioritisation (#8), biological realism
(#9). Study 4 addresses essentially none of these — it pivots to visualisation and self-tuning.
That's a strategic miss: the reviewer told you what would move the needle, and the plan spends its
budget elsewhere. At minimum, fold in #6 (uncertainty) and #7 (a genuine "critic caught a wrong
rule, agent revised" trace) — both are cheap and directly rebut the standing critique.

### II.2 Phase B "dynamic weight tuning" is dangerous without a frozen yardstick
Letting the Objective-Compiler agent freely tune `SCORE_WEIGHTS` (`PLAN_STUDY4.md §3`) **amplifies**
the exact circularity the external reviewer flagged (`CRITIQUE.md#2`): if the agent both sets the
weights and reports the winner, "our designs score well" becomes unfalsifiable. Self-tuning is only
defensible if success is measured on a **frozen, independent** metric the agent cannot touch (QED,
Morgan novelty, a held-out prediction, or real retrosynthesis from I.5). The plan must specify that
locked yardstick, and must log every weight change as an artifact with the agent's stated
rationale.

### II.3 Phase C funnel is the strongest idea — but its filter is currently meaningless
The cheap-exploration → targeted-RL funnel (`§4`) is genuinely good: cheap, scalable, on-brief
("cost-effective discovery"), low-risk. **But** Step 1 filters the raw pool by "RDKit med-chem
alerts, retrosynthetic step-counters, and solubility proxies" — and the step-counter is the fake
heuristic from I.5. A funnel that selects chemotypes by a meaningless feasibility score
concentrates the search on artifacts of the heuristic. Fix I.5 first, then the funnel is worth
building.

### II.4 Phase A drawings — good, but "scissile bond in red" must be detected, not asserted
2D depictions with handle/scissile/spacer highlighting (`§2`) are the cleanest, highest-value,
lowest-risk deliverable in the plan — a chemist reads structures, not SMILES. Requirement: the
handle, scissile bond, and solubiliser must be **identified programmatically** (SMARTS on the
assembled construct), verified against a few known linkers (Val-Cit-PABC, SMCC), and the drawing
must fail loudly if it can't locate a scissile bond — otherwise the highlight is decoration.

### II.5 The plan repeats the "top-scoring vs chemist-would-pick" gap
`CRITIQUE_S3.md#4` explicitly asked for the shortlist to be the molecules a medicinal chemist would
choose, with dossiers (analogue, route, failure modes, validation). Study 4 still draws "the top
1–3 candidates" by composite score (`§2`, `§5`). Same critique will recur. The shortlist selector
should apply a med-chem gate (real feasibility + alerts + novelty), not just `argmax(score)`.

---

## Part III — The improved plan the buddy should run (prioritised)

Do these in order. P0 is mandatory before writing any Study 4 paper.

**P0 — Restore integrity (turns the existing pipeline honest):**
1. Provenance gate (I.6): tag every value `measured|llm|heuristic|mock`; paper builder asserts no
   `mock` reaches a results claim; emit a provenance table in the supplementary. Run with
   `HACKATHON_AGENT_LLM_MODE=always`; persist raw LLM completions and retrieved RAG chunks.
2. Real Boltz or no Boltz claim (I.1): run on the pod GPU, assert `status=="completed"`; delete the
   45/999 mock constants from the results path.
3. Real Phase E (I.2): genuine leave-one-out RAG store minus `siRNA.pdf`; compute E3 from real
   clinical SMILES; delete `e3_pass = True` and the tautological E1.
4. Wire Phase A rules into the objective (I.3) and delete the duplicated objective block.
5. Feed payload into scoring or drop the payload-aware claim (I.4).
6. Real retrosynthesis (AiZynthFinder) or honest renaming (I.5).

**P1 — Study 4 features, made honest:**
7. Phase C funnel (II.3) — build it, but only after step 6 (so the filter means something).
8. Phase A drawings (II.4) — SMARTS-driven highlighting, verified on known linkers, fail-loud.
9. Phase B dynamic tuning (II.2) — allow it **only** against a frozen independent yardstick; log
   every weight decision + rationale as an artifact.

**P2 — Close the external reviewer's standing gaps (cheap, high-credibility):**
10. Uncertainty (`CRITIQUE_S3.md#6`): report confidence on each derived rule / recommendation
    (e.g. agreement across N verifier agents, retrieval support count).
11. One real failure-recovery trace (`#7`): show the critic catching a wrong rule and the agent
    revising — this is the single most convincing evidence of autonomy, and the graph already
    supports critic-driven re-seeding.
12. Chemist-grade shortlist (`#4`): med-chem-gated selection + dossiers, not `argmax(score)`.

---

## Definition of done (what makes the Study 4 paper defensible)

- No number in the paper traces to a `mock`/hard-coded constant; a provenance table proves it.
- The autonomous chain is real end-to-end for at least one payload class: retrieved chunks → raw
  LLM rule → **objective actually changed by that rule** → designs → validated on a metric the
  objective never optimised.
- At least one *genuine* held-out prediction (real leave-one-out, artifacts captured).
- Structures are drawn with programmatically-detected highlights, verified on known linkers.
- Every honesty guard the HANDOFFs already articulate is enforced *in code*, not just in prose.

The program is genuinely close to a compelling "autonomous medicinal-chemistry scientist" story.
The gap is no longer ambition — it's that the last mile was stubbed and then written up as done.
Close Part I and Study 4 becomes the paper the arc has been promising.

---

# Part IV — Review of the shipped `deliverables/study4/` (post-run)

Reviewed after the buddy ran Study 4. I checked the artifacts against the code and the raw
outputs, the same way as Part I. **Verdict: the Part I integrity blockers are genuinely fixed.**
This is a real, defensible iteration — a large qualitative jump from Study 3. There are still
substantive gaps, but they are honest-science gaps, not fabrications.

## What is now real (credit where due — verified, not taken on trust)
- **Boltz is real.** `boltz_jobs/*/output/.../predictions/` contain actual `*.pdb` structures,
  `pae/pde/plddt` tensors, and `affinity_*.json`; the reported Kd (43/44/74/1199 nM) derives from
  the real `affinity_pred_value` (e.g. immuno −1.364 → 43.2 nM). No more 45/999 mock constants.
  ipTM/plDDT vary per job. This fully closes Part I.1.
- **The held-out prediction is a real test.** `heldout_predictions.json` carries the full chain
  (retrieved passages → grounded exemplars → rule → objective → confidence), `leaked_sources: []`,
  and — the honest highlight — the oligonucleotide class, when its only ARC paper is withheld,
  returns **zero exemplars** and confidence **0.007** rather than inventing evidence. They even
  report a **miss** (`immunomodulator stability_match: False`). That is what a real, non-cherry-
  picked experiment looks like. Closes Part I.2.
- **Rules now compile into the objective.** `reasoning_chains.json` shows each derived rule
  producing a `canonical_spec` → `weights` block (cleavage regime, `max_rot_bonds`, per-term
  weights). Exemplars are `grounded: true` with source-quoted evidence from the real PDFs.
  Closes Part I.3 at the *derivation* level.
- **The LLM is genuinely on.** The `claude-opus-4.6` → `claude-opus-4-6` model-ID fix (README)
  was the real root cause of the silent fallbacks across Studies 2–3 — a good catch that
  retroactively explains I.6.
- **Drawings are real.** `draw_linker_constructs.py` classifies atoms by SMARTS
  (handle/scissile/spacer) with a documented priority order — programmatic, not asserted.

## Remaining weaknesses (ranked — these are what a reviewer will still hit)

### IV.1 The derived objective still does not *generate* the shortlist (loop not closed)
`shortlist.json` has `grid_path: deliverables/study3/grid_results.json` — which is itself the
**Study 2 grid** (its schema is `handles/triggers/payloads`, the old fixed-objective sweep). So
the 15 "actionable designs" are **selected from a cached pre-Study-4 pool**, then re-ranked; the
freshly compiled Phase-A objective is used to *filter*, not to *drive REINVENT generation*. The
central promise ("designs derived from the agent's reasoning") is therefore still one hop short:
derive-objective → **select from old pool**, not derive-objective → generate. `PLAN_STUDY4 §3`
(agent dynamically tunes weights → RL) is not actually exercised in what shipped.

**Consequence, visible in the data:** the cytotoxin rule derived "protease-cleavable / Val-Cit,"
but the **#1 delivered cytotoxin candidate is a pyridyl-disulfide**
(`Nc1c(C(=O)SSc2ccccn2)nnn1...`, handle "Disulfide", trigger labelled "Non-cleavable", flagged
`disulfide_reduction`). It's selected because the coarse "reward-cleavable" regime counts a
disulfide as cleavable — but it does **not** honour the class-specific derived motif (Val-Cit /
cathepsin B). The shortlist matches the regime, not the rule. Fix: run REINVENT with the compiled
per-class objective (even a short 40-step pass) so the delivered molecules are actually produced
by the derived rule, and enforce the specific motif in selection.

### IV.2 "Whole-conjugate" Boltz is still a disconnected mixture, not a conjugate
`boltz_whole_conjugate.json` and the dossiers still assemble as `linker_smiles`.`payload_smiles`
(a `.` — two separate species). Boltz co-folds the linker **and** the payload as **two
independent ligands** in the cathepsin-B pocket, not one covalent construct. The framing
("whole-conjugate co-fold") overstates it; the honest statement is "linker + payload co-present."
Part I.4 is not closed. Either bond them at the attachment point or rename the claim.

### IV.3 Retrosynthesis is still the descriptor heuristic (Part I.5 unaddressed)
Dossiers report `step_count: 6`, "Standard coupling steps" — still
`estimate_retrosynthetic_steps` (the `2 + n_amides + …` formula), no AiZynthFinder. The dossier
"proposed synthesis" is therefore LLM-narrated plausibility, not a validated route. Keep the
number but label it "heuristic complexity index," or wire AiZynthFinder for the 15 shortlisted
molecules only (cheap at n=15).

### IV.4 Confidence has a partly-fixed component
`self_confidence` is exactly **0.55** for both cytotoxin and immunomodulator (0.05 for oligo).
Check whether that is an LLM output or a default that kicks in when the model omits the field — if
the latter, the composite confidence is partly hard-coded and should be labelled as such in the
supplementary provenance.

### IV.5 The oligo showcase is a prior, not a derivation (frame carefully)
With zero exemplars, the still-correct "non-cleavable" oligo prediction comes from the LLM's
**parametric prior** (oligos are big/charged/stable), not from independent-paper reasoning. The
README frames this correctly as an *uncertainty-calibration* win (confidence collapses to ~0) —
keep it there. Do **not** let the paper drift into calling it a literature-derived recovery; it
is the opposite (evidence removed → it abstains). The `PLAN_STUDY4 §12` fix (add 2–3 more ARC
papers) is the right move to turn it into a genuine confident recovery.

### IV.6 Still no provenance gate in code (Part I.6 process fix outstanding)
The values are real *this* time, but nothing in the paper builder *enforces* it — there is no
`source ∈ {measured,llm,heuristic,mock}` tag that blocks a mock/default from reaching a results
claim. That gate is what makes the honesty durable across future runs; recommend adding it before
the next iteration, plus a provenance table in the supplementary.

## Definition of done for the Study 4 paper (updated)
- **Must:** regenerate the shortlist by running REINVENT under each class's *compiled* objective
  (close IV.1), so delivered molecules are produced by the derived rule and honour its specific
  motif; re-draw/re-Boltz those.
- **Should:** covalently assemble the conjugate for Boltz, or restate the claim (IV.2); label the
  retrosynthesis metric honestly or wire AiZynth for n=15 (IV.3); confirm `self_confidence`
  provenance (IV.4).
- **Framing:** keep the oligo case as calibration, not recovery (IV.5); add the provenance
  gate (IV.6).

Net: Study 4 is the first iteration I would let out of the building. The fabrications are gone and
the reasoning is genuinely visible and validated. The one gap that still separates it from its own
thesis is IV.1 — the derived objective must *make* the molecules, not just *pick* them.
