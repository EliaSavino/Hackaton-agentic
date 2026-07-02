"""Benchmark designed ADC linkers against real/commercial clinical linkers.

Provides (a) a curated set of clinically-used ADC linkers with canonical SMILES,
(b) independent yardsticks the RL objective did NOT optimise (QED, physicochemical
descriptors, Morgan-Tanimoto novelty), and (c) a scorer-calibration table that
checks the plasma-stability surrogate reproduces the known ordering across
mechanistic classes. This turns "our linkers are better" into an honest,
non-circular comparison (see PLAN.md sections 2-3).
"""

from __future__ import annotations

from typing import Any

from hackathon_agents.schemas.linkers import ADCGoalProfile
from hackathon_agents.tools.adc_linker_objective import score_adc_linker


# Clinically-used / commercial ADC linkers (canonical SMILES; conjugation handle
# included where standard). class/example anchor them to real drugs.
COMMERCIAL_LINKERS: list[dict[str, str]] = [
    {"name": "mc-Val-Cit-PABC", "smiles": "O=C1C=CC(=O)N1CCCCCC(=O)NC(C(C)C)C(=O)NC(CCCNC(N)=O)C(=O)Nc1ccc(CO)cc1",
     "class": "protease-cleavable (maleimide/Cys)", "adc": "brentuximab vedotin (Adcetris)"},
    {"name": "mc-Val-Ala-PABC", "smiles": "O=C1C=CC(=O)N1CCCCCC(=O)NC(C(C)C)C(=O)NC(C)C(=O)Nc1ccc(CO)cc1",
     "class": "protease-cleavable (maleimide/Cys)", "adc": "Val-Ala class"},
    {"name": "mc-GGFG", "smiles": "O=C1C=CC(=O)N1CCCCCC(=O)NCC(=O)NCC(=O)NC(Cc1ccccc1)C(=O)NCC(=O)O",
     "class": "protease-cleavable tetrapeptide", "adc": "trastuzumab deruxtecan (Enhertu)"},
    {"name": "MCC (non-cleavable)", "smiles": "O=C(O)C1CCC(CN2C(=O)C=CC2=O)CC1",
     "class": "non-cleavable thioether", "adc": "trastuzumab emtansine (Kadcyla)"},
    {"name": "SPDB disulfide", "smiles": "O=C(O)CCCSSc1ccccn1",
     "class": "redox-cleavable disulfide", "adc": "mirvetuximab soravtansine (Elahere)"},
    {"name": "sulfo-SPDB", "smiles": "O=C(O)C(CCSSc1ccccn1)S(=O)(=O)O",
     "class": "redox-cleavable disulfide (hydrophilic)", "adc": "hindered disulfide class"},
    {"name": "AcBut hydrazone", "smiles": "CC(=NN)c1ccc(OCCCC(=O)O)cc1",
     "class": "acid-labile hydrazone", "adc": "gemtuzumab ozogamicin (Mylotarg)"},
    {"name": "beta-glucuronide", "smiles": "O=C1C=CC(=O)N1CCCCCC(=O)Nc1ccc(OC2OC(C(=O)O)C(O)C(O)C2O)cc1CO",
     "class": "glycosidase-cleavable glucuronide", "adc": "glucuronide linker class"},
    {"name": "maleimidocaproyl (mc)", "smiles": "O=C1C=CC(=O)N1CCCCCC(=O)O",
     "class": "conjugation spacer only", "adc": "mc handle"},
]

# Representative motifs per mechanistic stability class, for scorer calibration.
# Literature plasma-stability ordering: hydrazone < disulfide < peptide ~ non-cleavable.
CALIBRATION_SET: list[dict[str, str]] = [
    {"class": "acid-labile hydrazone", "smiles": "CC(=NNC(C)=O)c1ccc(OCCCC(=O)O)cc1", "expected_stability": "low"},
    {"class": "redox disulfide", "smiles": "O=C(O)CCCSSc1ccccn1", "expected_stability": "intermediate"},
    {"class": "protease dipeptide", "smiles": "O=C1C=CC(=O)N1CCCCCC(=O)NC(C(C)C)C(=O)NC(CCCNC(N)=O)C(=O)Nc1ccc(CO)cc1", "expected_stability": "high"},
    {"class": "non-cleavable thioether", "smiles": "O=C(O)C1CCC(CN2C(=O)C=CC2=O)CC1", "expected_stability": "high"},
]


def physchem(smiles: str) -> dict[str, Any]:
    """Independent physicochemical yardsticks (NOT directly in the RL objective)."""
    from rdkit import Chem
    from rdkit.Chem import QED, Crippen, Descriptors, Lipinski, rdMolDescriptors

    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return {}
    return {
        "qed": round(QED.qed(m), 4),
        "mol_wt": round(Descriptors.MolWt(m), 1),
        "logp": round(Crippen.MolLogP(m), 2),
        "tpsa": round(Descriptors.TPSA(m), 1),
        "fsp3": round(Lipinski.FractionCSP3(m), 3),
        "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(m),
        "hbd": Lipinski.NumHDonors(m),
        "hba": Lipinski.NumHAcceptors(m),
        "rot_bonds": Descriptors.NumRotatableBonds(m),
    }


def _morgan(smiles: str):
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator

    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return None
    gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    return gen.GetFingerprint(m)


def nearest_neighbor_similarity(smiles: str, reference_fps: list) -> float | None:
    """Max Morgan-Tanimoto similarity of ``smiles`` to any reference fingerprint.

    Low value => novel chemotype; high => close to a known/commercial linker.
    """
    from rdkit import DataStructs

    fp = _morgan(smiles)
    if fp is None or not reference_fps:
        return None
    sims = [DataStructs.TanimotoSimilarity(fp, r) for r in reference_fps if r is not None]
    return round(max(sims), 4) if sims else None


def score_reference_set(profile: ADCGoalProfile | None = None) -> list[dict[str, Any]]:
    """Score the commercial linkers with the same composite + yardsticks."""
    profile = profile or ADCGoalProfile()
    rows: list[dict[str, Any]] = []
    for item in COMMERCIAL_LINKERS:
        composite, subscores = score_adc_linker(item["smiles"], profile)
        rows.append({**item, "score": composite, "subscores": subscores, "physchem": physchem(item["smiles"])})
    return rows


def calibration_table(profile: ADCGoalProfile | None = None) -> dict[str, Any]:
    """Score the mechanistic-class representatives; report the stability ordering.

    ``passes`` is True iff the surrogate flags the acid-labile hydrazone as the
    least plasma-stable class (stability subscore strictly below the others) —
    the dominant premature-release liability the design objective must avoid.
    """
    profile = profile or ADCGoalProfile()
    rows: list[dict[str, Any]] = []
    for item in CALIBRATION_SET:
        composite, subscores = score_adc_linker(item["smiles"], profile)
        rows.append({**item, "stability": subscores.get("stability"), "composite": composite})
    hydrazone = next((r["stability"] for r in rows if "hydrazone" in r["class"]), None)
    others = [r["stability"] for r in rows if "hydrazone" not in r["class"] and r["stability"] is not None]
    passes = hydrazone is not None and bool(others) and all(hydrazone < o for o in others)
    return {"rows": rows, "passes": passes}


def benchmark_designed(
    designed: list[dict[str, Any]],
    profile: ADCGoalProfile | None = None,
) -> dict[str, Any]:
    """Attach independent yardsticks + novelty (vs commercial set) to designed linkers.

    ``designed`` items need at least a ``smiles`` (and optionally ``score``); this
    adds ``physchem`` and ``novelty`` (nearest-neighbour Tanimoto to the commercial
    set — low = novel chemotype).
    """
    profile = profile or ADCGoalProfile()
    ref_fps = [_morgan(item["smiles"]) for item in COMMERCIAL_LINKERS]
    out: list[dict[str, Any]] = []
    for cand in designed:
        smiles = cand.get("smiles")
        if not smiles:
            continue
        enriched = dict(cand)
        if enriched.get("score") is None:
            composite, subscores = score_adc_linker(smiles, profile)
            enriched["score"] = composite
            enriched.setdefault("subscores", subscores)
        enriched["physchem"] = physchem(smiles)
        enriched["novelty_nn_tanimoto"] = nearest_neighbor_similarity(smiles, ref_fps)
        out.append(enriched)
    return {
        "commercial": score_reference_set(profile),
        "calibration": calibration_table(profile),
        "designed": out,
    }
