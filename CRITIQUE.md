# Critique of the ADC Linker Agent Manuscripts

## Overall assessment

The newer **Study2** version is a substantial improvement over the
original manuscript. The central narrative---**payload-aware linker
design rather than generic ADC linker generation**---is significantly
stronger and provides a much more interesting scientific contribution.

The work is promising, but it still reads more as an excellent
proof-of-concept than as a convincing demonstration of an autonomous
scientific agent. Below are the main weaknesses and suggested next
steps.

## 1. The "agentic" claim is still under-proven

The manuscript states that the payload design rules were *literature
encoded* for this run rather than autonomously extracted by the LLM.

As a result, the most interesting part of the pipeline---the autonomous
reasoning over literature---is largely hidden.

To strengthen the paper, the agent should expose:

-   retrieved literature
-   extracted design rules
-   intermediate reasoning
-   compiled scorer parameters
-   final optimisation objective

Showing this reasoning chain would make it clear that the scientific
conclusions originate from the agent rather than the human.

------------------------------------------------------------------------

## 2. The scoring function remains largely hand-designed

The six-objective geometric mean is reasonable, but many conclusions
naturally follow from how the scorer was constructed.

For example:

-   cytotoxic payloads reward cleavable linkers
-   oligonucleotides penalise cleavability
-   ISACs heavily weight plasma stability

Because these rules are explicitly encoded, the payload-dependent
ranking is not completely independent evidence.

A stronger validation would be demonstrating that the agent predicts
behaviour that was **not explicitly encoded** in the objective.

------------------------------------------------------------------------

## 3. Synthetic accessibility is the largest weakness

The manuscript honestly acknowledges that the generated molecules are
frequently amide-rich and less synthetically attractive than commercial
linkers.

This is probably the most important limitation of the current pipeline.

The next scorer should include:

-   retrosynthetic feasibility
-   estimated synthesis step count
-   commercial building block availability
-   reaction success probability
-   medicinal chemistry sanity filters

Ultimately the agent should optimise for molecules that a chemist would
actually synthesise.

------------------------------------------------------------------------

## 4. The stability surrogate is too simplistic

Currently the stability model mostly distinguishes hydrazones from
everything else.

For ADC linker design this is insufficient.

A better model should distinguish between:

-   peptide cleavage
-   disulfide reduction
-   maleimide deconjugation
-   hydrolysis
-   plasma stability
-   lysosomal stability

especially because plasma stability is central to the paper's claims.

------------------------------------------------------------------------

## 5. Boltz-2 is a useful proof point, but not proof of cleavage

The Boltz results are encouraging.

Designed Val-Cit linkers bind tightly while non-cleavable controls bind
substantially weaker.

However:

binding affinity ≠ enzymatic cleavage.

The paper should frame this as evidence for **substrate recognition** or
**structural plausibility**, not direct validation of linker cleavage.

------------------------------------------------------------------------

## 6. Payloads remain abstract

The optimisation currently targets payload classes rather than real
payload molecules.

Real ADC optimisation depends on factors such as:

-   payload hydrophobicity
-   charge
-   sterics
-   DAR
-   antibody conjugation site
-   intracellular trafficking
-   release mechanism

The next generation should optimise around representative payloads
rather than generic classes.

# What should the agent do next?

Rather than simply generating linkers, the next version of the agent
should function as a genuine medicinal chemistry design assistant.

## 1. Build a richer literature knowledge base

Automatically extract dozens of examples for each payload class
containing:

-   payload
-   linker
-   conjugation chemistry
-   stability
-   release mechanism
-   biological outcome

Use these examples to derive design principles automatically.

## 2. Improve the scoring function

Replace heuristic objectives with richer predictive models including:

-   plasma half-life
-   lysosomal release
-   aggregation risk
-   hydrophobicity
-   synthetic accessibility
-   commercial availability
-   route feasibility

## 3. Add retrosynthetic planning

Run retrosynthesis on every candidate.

Reject molecules with unrealistic routes.

Prefer molecules that can realistically be prepared in roughly three to
five synthetic steps.

## 4. Produce an experimentally actionable shortlist

Instead of returning hundreds of molecules, produce approximately:

-   5 cytotoxic linkers
-   5 oligonucleotide linkers
-   5 ISAC linkers

For each candidate provide:

-   SMILES
-   design rationale
-   closest literature analogue
-   proposed synthesis
-   expected failure modes
-   suggested validation experiments

# Overall conclusion

The project has moved well beyond "AI generates molecules."

Its real contribution is moving toward **an autonomous scientist capable
of reading literature, constructing objectives, and designing molecules
for different therapeutic contexts.**

The next major step is demonstrating that the agent does not merely
optimise a hand-written scoring function, but instead produces
**synthetically realistic, experimentally actionable designs** derived
from literature and predictive models.
