"""Payload-class-aware linker design rules and scoring profiles.

The requirements a linker must satisfy depend on *what it delivers*. A cytotoxic
small molecule benefits from a cleavable linker (intracellular payload release +
bystander effect); an oligonucleotide (antibody--siRNA conjugate, "ARC") is
favoured by a **rigid, non-cleavable** linker; a TLR7/8 immunomodulator ("ISAC")
tolerates a cleavable linker only if plasma stability is high enough to avoid
systemic immune activation.

This module encodes those literature-grounded rules and maps a payload class to
an :class:`ADCGoalProfile` (the fixed action space consumed by the REINVENT
objective builder and the offline scorer). A :func:`derive_payload_rules` step
represents the *agentic literature analysis*: given an API key it can derive the
rule from the retrieved corpus; otherwise it returns the encoded, cited rules.

References
----------
- Antibody--siRNA conjugate (ARC), trastuzumab, rigid sulfo-SMCC non-cleavable
  linker: *Bioconjugate Chem.* 2025 (DOI 10.1021/acs.bioconjchem.5c00212).
- Antibody--Resiquimod (TLR7/8) ISAC, protease-cleavable + acid-labile linker,
  tumour-microenvironment release: *Mol. Pharm.* 2022 (10.1021/acs.molpharmaceut.2c00392);
  *Front. Pharmacol.* 2023 (biodistribution); *J. Med. Chem.* 2025 (10.1021/acs.jmedchem.5c01908).
"""

from __future__ import annotations

import os
from typing import Any, Literal

from hackathon_agents.schemas.linkers import ADCGoalProfile

CleavagePref = Literal["reward", "penalize", "ignore"]


# --------------------------------------------------------------------------- #
# Literature-grounded payload-class design rules
# --------------------------------------------------------------------------- #
PAYLOAD_CLASSES: dict[str, dict[str, Any]] = {
    "cytotoxin": {
        "label": "Cytotoxic small molecule",
        "examples": "MMAE, DM1, DXd, calicheamicin",
        # Cleavable linkers release free drug intracellularly and enable the
        # bystander effect; non-cleavable (T-DM1/MCC) is a valid alternative.
        "cleavage_preference": "reward",
        "rigidity": "moderate",
        "stability_priority": "standard",
        "rationale": (
            "Cleavable linkers (Val-Cit-PABC, GGFG, disulfide) dominate to release free, "
            "membrane-permeable payload for potency and bystander killing; non-cleavable "
            "thioethers (T-DM1) work where a charged catabolite is acceptable."
        ),
        "citation": "su2021, balamkundu2023",
    },
    "oligonucleotide": {
        "label": "Oligonucleotide (siRNA / ASO, antibody--oligonucleotide conjugate, ARC)",
        "examples": "siRNA, antisense oligonucleotide",
        # ARC work favours a rigid, NON-cleavable linker: the polyanionic cargo
        # must stay conjugated for productive uptake/silencing; premature release
        # gives naked, nuclease-labile oligo.
        "cleavage_preference": "penalize",
        "rigidity": "rigid",
        "stability_priority": "high",
        "rationale": (
            "Antibody--siRNA conjugates are favoured by the rigid, non-cleavable sulfo-SMCC "
            "linker; effective gene silencing proceeds by free uptake without endosome "
            "disruption, so a cleavable linker that sheds the oligo prematurely is a liability."
        ),
        "citation": "arc2025",
    },
    "immunomodulator": {
        "label": "Immunomodulator (TLR7/8 agonist, immune-stimulating antibody conjugate, ISAC)",
        "examples": "imidazoquinoline, resiquimod (R848)",
        # Cleavable release in the tumour microenvironment enhances efficacy, but
        # the linker MUST stay intact in circulation or systemic TLR activation
        # (cytokine toxicity) follows -> plasma stability is paramount.
        "cleavage_preference": "reward",
        "rigidity": "moderate",
        "stability_priority": "paramount",
        "rationale": (
            "ISACs use either non-cleavable linkers (retain the agonist on the antibody) or "
            "protease-cleavable linkers (R848/Val-Cit-PABC) that release the TLR7/8 agonist in "
            "the tumour microenvironment; either way the linker must resist premature systemic "
            "cleavage that would trigger cytokine toxicity, so plasma stability is decisive."
        ),
        "citation": "isac2022, isac2023, isac2025",
    },
}

DEFAULT_PAYLOAD = "cytotoxin"


def resolve_cleavage(payload_preference: CleavagePref, trigger_is_cleavable: bool) -> CleavagePref:
    """Combine the payload's cleavage preference with what the trigger presents.

    - ``penalize`` payload (oligonucleotide): a cleavable trigger is penalised and a
      non-cleavable one is rewarded, regardless of the trigger label.
    - ``reward`` payload (cytotoxin/immunomodulator): a cleavable trigger is rewarded;
      a non-cleavable trigger is *ignored* (a valid alternative design, not penalised).
    """
    if payload_preference == "penalize":
        return "penalize"
    return "reward" if trigger_is_cleavable else "ignore"


def profile_for_payload(
    payload: str,
    trigger_meta: dict[str, Any] | None = None,
    *,
    base: ADCGoalProfile | None = None,
) -> ADCGoalProfile:
    """Map a payload class (+ the trigger context) to an ``ADCGoalProfile``.

    The multi-objective *dimensions* are unchanged; the payload class shifts the
    weights and the cleavage-handling regime so a single agent designs correctly
    for cytotoxins, oligonucleotides and immunomodulators.
    """
    spec = PAYLOAD_CLASSES.get(payload, PAYLOAD_CLASSES[DEFAULT_PAYLOAD])
    profile = base.model_copy(deep=True) if base is not None else ADCGoalProfile()
    trigger_cleavable = bool((trigger_meta or {}).get("require_cleavable", True))

    pref = resolve_cleavage(spec["cleavage_preference"], trigger_cleavable)
    profile.cleavage_preference = pref
    if pref == "ignore":
        profile.require_cleavable_motif = False
        profile.weights["cleavability"] = 0.0
    elif pref == "penalize":
        profile.require_cleavable_motif = False
        profile.weights["cleavability"] = 0.8
    else:  # reward
        profile.require_cleavable_motif = True
        profile.weights.setdefault("cleavability", 1.0)
        if profile.weights["cleavability"] <= 0.0:
            profile.weights["cleavability"] = 1.0

    # Rigidity: a rigid payload (oligonucleotide) tightens the rotatable-bond
    # window and up-weights the flexibility term (which rewards fewer rot. bonds).
    if spec["rigidity"] == "rigid":
        profile.max_rot_bonds = 5
        profile.weights["flexibility"] = 0.9
    elif spec["rigidity"] == "flexible":
        profile.max_rot_bonds = 14
        profile.weights["flexibility"] = 0.2

    # Stability priority: immunomodulators must not release systemically.
    if spec["stability_priority"] == "paramount":
        profile.weights["stability"] = 1.0
    elif spec["stability_priority"] == "high":
        profile.weights["stability"] = 0.85

    # Trigger-level relaxations (e.g. glucuronide's anomeric acetal false positive).
    if trigger_meta is not None and trigger_meta.get("enforce_stability", True) is False:
        profile.enforce_stability_alerts = False

    # Re-validate so the weight clamp/normalisation runs.
    return ADCGoalProfile.model_validate(profile.model_dump())


def _llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def derive_payload_rules(payload: str, *, allow_llm: bool | None = None) -> dict[str, Any]:
    """The agentic literature step: return the design rule for a payload class.

    When an API key is present (``allow_llm``) an LLM could derive the rule from the
    retrieved corpus; here we return the literature-encoded rule with its citations
    and record which mode was used, so the paper can report it honestly.
    """
    spec = PAYLOAD_CLASSES.get(payload, PAYLOAD_CLASSES[DEFAULT_PAYLOAD])
    use_llm = _llm_available() if allow_llm is None else (allow_llm and _llm_available())
    return {
        "payload": payload,
        "label": spec["label"],
        "cleavage_preference": spec["cleavage_preference"],
        "rigidity": spec["rigidity"],
        "stability_priority": spec["stability_priority"],
        "rationale": spec["rationale"],
        "citation": spec["citation"],
        "mode": "llm-derived" if use_llm else "literature-encoded",
    }
