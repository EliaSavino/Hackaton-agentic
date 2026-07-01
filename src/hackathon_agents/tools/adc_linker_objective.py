"""Build a REINVENT4 LinkInvent objective for ADC-linker design.

An ADC linker is the fragment between two fixed warheads (the antibody-side
conjugation handle and the payload attachment). REINVENT's **LinkInvent**
generator produces exactly that fragment, and its ``Fragment*`` scoring
components score *only the generated linker* — so the large, fixed warheads and
payload do not dominate the objective.

This module is the deterministic bridge between a compact, human/LLM-friendly
:class:`ADCGoalProfile` (seven weights + two constraint toggles + target
windows) and a fully-formed REINVENT LinkInvent scoring function. Keeping the
LLM's action space at the profile level (rather than raw REINVENT config) means
every autonomous edit still renders a valid config here.

The output is a plain ``dict`` of :class:`ReinventInput` fields, ready to drop
into ``state.metadata["reinvent"]`` and hand to
``tools/reinvent_tools.generate_with_reinvent``.
"""

from __future__ import annotations

import math
from typing import Any

from hackathon_agents.schemas.linkers import ADC_GOAL_KEYS, ADCGoalProfile


# Single canonical warhead pair for the first demo (LinkInvent format:
# ``warhead1(*)|warhead2(*)`` — one attachment point each, pipe-separated).
# warhead 1 = maleimidocaproyl antibody-side handle (Cys-reactive maleimide with
# a caproyl spacer); warhead 2 = a minimal payload stub. Swap warhead 2 for a
# real payload (e.g. MMAE) once the pipeline is validated.
CANONICAL_WARHEAD_PAIR = "O=C1C=CC(=O)N1CCCCCC(=O)*|*Nc1ccccc1"

# SMARTS that indicate a tumor-triggerable cleavable motif (rewarded when
# ``require_cleavable_motif`` is on). Illustrative, hackathon-scoped patterns
# aligned with linker_design.py's trigger vocabulary (protease, reducing).
CLEAVABLE_MOTIF_SMARTS = [
    "[NX3][CX4][CX3](=O)[NX3][CX3](=O)",  # dipeptide-like protease-cleavable amide (Val-Cit-ish)
    "[#16X2][#16X2]",  # disulfide (reducing-environment cleavable)
    "c1ccc(CO[CX3](=O))cc1",  # PABC self-immolative benzyl carbamate
]

# SMARTS for groups that are labile in circulation; filtered out (score 0) when
# ``enforce_stability_alerts`` is on, to favour plasma-stable linkers.
LABILE_ALERT_SMARTS = [
    "[CX3]=[NX2][NX3]",  # hydrazone (acid-labile, plasma-unstable)
    "[CX4]([OX2H0])[OX2H0]",  # acetal / ketal
]

# Convenient default the planner seeds and the critic edits.
DEFAULT_ADC_GOAL_PROFILE = ADCGoalProfile()


def build_adc_linkinvent_objective(
    profile: ADCGoalProfile | dict[str, Any] | None = None,
    *,
    warhead_pair: str = CANONICAL_WARHEAD_PAIR,
    run: bool = False,
    device: str = "cpu",
    max_steps: int = 100,
    min_steps: int = 25,
    batch_size: int = 64,
    max_return: int = 25,
) -> dict[str, Any]:
    """Render a REINVENT LinkInvent staged-learning objective from a profile.

    Returns a dict of :class:`ReinventInput` fields. Only components with a
    positive weight are included (plus the optional constraint filters); the
    aggregator is ``geometric_mean`` so any objective scoring ~0 strongly
    penalises the whole linker (standard REINVENT RL behaviour).
    """

    profile = _coerce_profile(profile)
    weights = profile.weights
    scoring: list[dict[str, Any]] = []

    # --- Solubility / low aggregation: low fragment logP + polar surface ------
    if weights["solubility"] > 0.0:
        scoring.append(
            _component(
                "FragmentSlogP",
                name="linker logP",
                weight=weights["solubility"],
                transform={"type": "reverse_sigmoid", "low": profile.target_logp - 1.0, "high": profile.target_logp + 2.0, "k": 0.5},
            )
        )
        scoring.append(
            _component(
                "FragmentTPSA",
                name="linker TPSA",
                weight=round(weights["solubility"] * 0.5, 4),
                transform={"type": "sigmoid", "low": 40.0, "high": 120.0, "k": 0.5},
            )
        )

    # --- Size / PK: fragment MW window ---------------------------------------
    if weights["size"] > 0.0:
        scoring.append(
            _component(
                "FragmentMolecularWeight",
                name="linker MW",
                weight=weights["size"],
                transform={"type": "double_sigmoid", "low": profile.mw_low, "high": profile.mw_high, "coef_div": 100.0, "coef_si": 150.0, "coef_se": 150.0},
            )
        )

    # --- Flexibility / spacer length -----------------------------------------
    if weights["flexibility"] > 0.0:
        scoring.append(
            _component(
                "FragmentNumRotBond",
                name="linker rotatable bonds",
                weight=weights["flexibility"],
                transform={"type": "reverse_sigmoid", "low": 2.0, "high": float(profile.max_rot_bonds), "k": 0.5},
            )
        )

    # --- Synthesizability (whole-molecule SA proxy; no fragment SA in REINVENT)
    if weights["synthesizability"] > 0.0:
        scoring.append(
            _component(
                "SAScore",
                name="synthetic accessibility",
                weight=weights["synthesizability"],
                transform={"type": "reverse_sigmoid", "low": 1.0, "high": profile.max_sa_score, "k": 0.5},
            )
        )

    # --- Cleavable trigger present (reward) ----------------------------------
    if profile.require_cleavable_motif and weights["cleavability"] > 0.0:
        scoring.append(
            _component(
                "MatchingSubstructure",
                name="cleavable motif present",
                weight=weights["cleavability"],
                params={"smarts": list(CLEAVABLE_MOTIF_SMARTS)},
            )
        )

    # --- Circulation stability: filter labile groups (global, no weight) ------
    if profile.enforce_stability_alerts:
        scoring.append(
            _component(
                "CustomAlerts",
                name="labile group alerts",
                params={"smarts": list(LABILE_ALERT_SMARTS)},
            )
        )

    # --- Novelty vs validated linkers (optional; needs reference SMILES) ------
    # Left out by default: the reference corpus does not yet carry linker SMILES.

    return {
        "generator_type": "linkinvent",
        "run_type": "staged_learning",
        "prior": ".linkinvent",
        "input_smiles": [warhead_pair],
        "scoring_aggregator": "geometric_mean",
        "scoring": scoring,
        "device": device,
        "max_steps": max_steps,
        "min_steps": min_steps,
        "batch_size": batch_size,
        "max_return": max_return,
        "run": run,
    }


def score_adc_linker(
    smiles: str,
    profile: ADCGoalProfile | dict[str, Any] | None = None,
) -> tuple[float | None, dict[str, float]]:
    """Deterministically score a generated linker against the goal profile.

    Mirrors the REINVENT objective (same dimensions, same geometric aggregation)
    so the agent's offline critic ranks candidates consistently with what the
    generator was optimising. Returns ``(composite, subscores)`` where composite
    is in [0, 1] (or ``None`` for an unparseable SMILES) and ``subscores`` maps
    each goal dimension to its [0, 1] value for transparency/reporting.
    """

    profile = _coerce_profile(profile)
    parsed = _rdkit_descriptors(smiles)
    if parsed is None:
        return None, {}
    logp, tpsa, mol_wt, rot_bonds, sa_score = parsed

    subscores: dict[str, float] = {
        "solubility": round(
            0.7 * _sigmoid_low(logp, profile.target_logp, width=2.0)
            + 0.3 * min(1.0, tpsa / 120.0),
            4,
        ),
        "size": round(_window(mol_wt, profile.mw_low, profile.mw_high), 4),
        "flexibility": round(_sigmoid_low(float(rot_bonds), float(profile.max_rot_bonds), width=3.0), 4),
        "synthesizability": round(
            max(0.0, min(1.0, (profile.max_sa_score - sa_score) / max(0.1, profile.max_sa_score - 1.0))),
            4,
        ),
        "cleavability": round(1.0 if _matches_any(smiles, CLEAVABLE_MOTIF_SMARTS) else 0.4, 4),
        "stability": round(0.0 if _matches_any(smiles, LABILE_ALERT_SMARTS) else 1.0, 4),
        "similarity": 0.5,  # neutral placeholder until the corpus carries linker SMILES
    }

    weights = profile.weights
    active = {
        key: subscores[key]
        for key in ADC_GOAL_KEYS
        if weights.get(key, 0.0) > 0.0
        and not (key == "cleavability" and not profile.require_cleavable_motif)
    }
    composite = _weighted_geomean(active, weights)
    # Stability alerts act as a hard filter (like REINVENT CustomAlerts).
    if profile.enforce_stability_alerts:
        composite *= subscores["stability"]
    return round(composite, 4), subscores


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _rdkit_descriptors(smiles: str) -> tuple[float, float, float, int, float] | None:
    try:
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

        from hackathon_agents.scoring_functions.rdkit_scorers import SAScore
    except Exception:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        sa = float(SAScore()._score(mol))
    except Exception:
        sa = 5.0
    return (
        float(Crippen.MolLogP(mol)),
        float(rdMolDescriptors.CalcTPSA(mol)),
        float(Descriptors.MolWt(mol)),
        int(Lipinski.NumRotatableBonds(mol)),
        sa,
    )


def _matches_any(smiles: str, smarts_list: list[str]) -> bool:
    try:
        from rdkit import Chem
    except Exception:
        return False
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    for smarts in smarts_list:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is not None and mol.HasSubstructMatch(pattern):
            return True
    return False


def _sigmoid_low(value: float, threshold: float, *, width: float) -> float:
    """1.0 well below ``threshold``, decaying to 0.0 above it (logistic)."""
    return 1.0 / (1.0 + math.exp((value - threshold) / max(1e-6, width)))


def _window(value: float, low: float, high: float) -> float:
    """1.0 inside [low, high], decaying linearly outside over one window width."""
    if low <= value <= high:
        return 1.0
    span = max(1e-6, high - low)
    if value < low:
        return max(0.0, 1.0 - (low - value) / span)
    return max(0.0, 1.0 - (value - high) / span)


def _weighted_geomean(subscores: dict[str, float], weights: dict[str, float]) -> float:
    total_w = sum(weights.get(key, 0.0) for key in subscores)
    if total_w <= 0.0:
        return 0.0
    acc = 0.0
    for key, score in subscores.items():
        floored = max(1e-6, score)
        acc += weights.get(key, 0.0) * math.log(floored)
    return math.exp(acc / total_w)


def _coerce_profile(profile: ADCGoalProfile | dict[str, Any] | None) -> ADCGoalProfile:
    if profile is None:
        return ADCGoalProfile()
    if isinstance(profile, ADCGoalProfile):
        return profile
    return ADCGoalProfile.model_validate(profile)


def _component(
    component_type: str,
    *,
    name: str,
    weight: float | None = None,
    transform: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ScoringComponent-compatible dict (component_type + endpoints)."""

    endpoint: dict[str, Any] = {"name": name}
    if weight is not None:
        endpoint["weight"] = weight
    if transform is not None:
        endpoint["transform"] = transform
    if params is not None:
        endpoint["params"] = params
    return {"component_type": component_type, "endpoints": [endpoint]}
