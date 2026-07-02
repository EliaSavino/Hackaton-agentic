# Critique of Study 3 -- Payload-Aware Autonomous ADC Linker Design

## Overall assessment

Study 3 is a clear step forward over the previous iterations. The
manuscript is beginning to resemble an autonomous scientist paper rather
than a generative chemistry paper. The central claim---an agent that
reads literature, derives payload-specific design rules, and generates
linker designs---is substantially more compelling than simply running
REINVENT with different scoring functions.

However, the manuscript still demonstrates that the workflow exists,
rather than convincingly proving that the workflow performs scientific
reasoning.

The remaining weaknesses are primarily about evidence rather than
implementation.

## 1. The literature agent is still the weakest part of the paper

The manuscript states that the agent reads literature, extracts
payload-specific rules, and compiles a scoring function, but the reader
never actually sees this reasoning process.

The paper should explicitly expose:

-   retrieved passages
-   extracted evidence
-   derived design rules
-   compiled objective
-   optimisation input

A figure showing this reasoning chain would greatly strengthen the
paper.

## 2. There is still no genuine scientific discovery

At present the work demonstrates that established medicinal chemistry
knowledge can be applied automatically.

It does not yet demonstrate that the agent can generate a genuinely new
scientific prediction or hypothesis.

Every major conclusion agrees with the literature.

A stronger paper would include at least one non-encoded prediction that
is later validated.

## 3. The held-out prediction should become the central experiment

The leave-one-paper-out validation proposed in the project plan is
exactly the right direction.

The paper should demonstrate that the agent derives design rules from
incomplete literature and independently predicts conclusions later
confirmed by the withheld publication.

That would provide strong evidence of autonomous scientific reasoning.

## 4. The medicinal chemistry still feels computational

The generated molecules are improved and appear more synthetically
realistic.

However, the paper still reports the highest-scoring molecules rather
than the molecules a medicinal chemist would actually choose to
synthesise.

The final output should be a small experimentally actionable shortlist.

## 5. The agent still executes a predefined workflow

The workflow remains developer-defined.

A stronger autonomous scientist would decide when to:

-   retrieve more literature
-   reject conflicting evidence
-   revise its own objective
-   discard candidates
-   repeat optimisation
-   terminate once sufficient confidence has been reached

## 6. Uncertainty is missing

The agent should estimate confidence in:

-   extracted rules
-   literature agreement
-   linker recommendations
-   synthesis feasibility

Scientific confidence is itself valuable output.

## 7. The paper only shows successful examples

The manuscript would be stronger if it demonstrated recovery from
failure.

For example:

-   incorrect initial rule
-   critic detects inconsistency
-   further literature retrieval
-   revised objective
-   improved final design

This would illustrate genuine iterative reasoning.

## 8. Experimental prioritisation could be stronger

Candidate dossiers should include:

-   synthesis cost
-   synthesis duration
-   probability of success
-   expected information gain
-   likely failure modes
-   recommended validation experiments

## 9. Biological realism remains simplified

Future versions should optimise complete conjugates rather than isolated
linkers by incorporating:

-   DAR
-   conjugation site
-   antibody scaffold
-   intracellular trafficking
-   Fc effects
-   target expression
-   conjugate hydrophobicity
-   payload-specific pharmacology

# Overall recommendation

The project is now approaching a much broader contribution than ADC
linker optimisation.

The manuscript should ultimately be framed as demonstrating an
autonomous medicinal chemistry scientist capable of reading literature,
deriving objectives, critiquing its own reasoning, proposing
synthetically realistic molecules, planning experiments, and justifying
every decision.

ADC linker optimisation is an excellent demonstration, but it should be
presented as the application rather than the primary contribution.
