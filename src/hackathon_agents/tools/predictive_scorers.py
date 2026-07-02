"""Phase B — Predictive scorers for Retrosynthesis and Mechanism-Resolved Stability.

Scores structural fragments for synthetic accessibility and chemical stability liabilities.
"""

from __future__ import annotations

from typing import Any
from rdkit import Chem
from rdkit.Chem import Descriptors, RDConfig
import os

def estimate_retrosynthetic_steps(smiles: str) -> dict[str, Any]:
    """Analyze a linker fragment to estimate synthetic step count, starting materials and complexity."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"step_count": 99, "score": 0.0, "is_feasible": False, "reason": "unparseable SMILES"}
    
    # Heuristics based on fragment descriptors
    mw = Descriptors.MolWt(mol)
    chiral_centers = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
    ring_count = Descriptors.RingCount(mol)
    rotatable_bonds = Descriptors.NumRotatableBonds(mol)
    
    # Standard linkages check (amides, esters, disulfides, clicks)
    amide_query = Chem.MolFromSmarts("[NX3][CX3](=O)")
    disulfide_query = Chem.MolFromSmarts("[#16X2][#16X2]")
    ester_query = Chem.MolFromSmarts("[CX3](=O)[OX2H0][#6]")
    triazole_query = Chem.MolFromSmarts("n1nncc1")
    
    n_amides = len(mol.GetSubstructMatches(amide_query)) if amide_query else 0
    n_disulfides = len(mol.GetSubstructMatches(disulfide_query)) if disulfide_query else 0
    n_esters = len(mol.GetSubstructMatches(ester_query)) if ester_query else 0
    n_triazoles = len(mol.GetSubstructMatches(triazole_query)) if triazole_query else 0
    
    # Step estimation logic
    # Base steps is proportional to size and number of linkages to form
    base_steps = 2
    base_steps += n_amides * 1.0  # amide formation
    base_steps += n_disulfides * 1.5  # disulfide exchange
    base_steps += n_esters * 1.5  # esterification/carbamate
    base_steps += n_triazoles * 1.0  # click reaction
    base_steps += chiral_centers * 1.0  # chiral centers increase synthesis step-count or cost
    base_steps += max(0.0, (mw - 300.0) / 100.0)  # scale with size
    
    # Cap steps reasonably between 2 and 12
    step_count = int(min(12, max(2, base_steps)))
    
    # Synthesizability Score: 1.0 is very easy, 0.0 is extremely difficult
    # High score for <= 4 steps, penalties above
    if step_count <= 3:
        score = 0.95
    elif step_count <= 5:
        score = 0.85
    elif step_count <= 7:
        score = 0.65
    elif step_count <= 9:
        score = 0.40
    else:
        score = 0.15
        
    is_feasible = step_count <= 7
    reason = "Standard coupling steps" if is_feasible else "Too many linear/synthetic steps required"
    
    return {
        "step_count": step_count,
        "score": round(score, 3),
        "is_feasible": is_feasible,
        "reason": reason,
        "descriptors": {
            "mw": round(mw, 2),
            "chiral_centers": chiral_centers,
            "ring_count": ring_count,
            "rotatable_bonds": rotatable_bonds,
            "amides": n_amides,
            "disulfides": n_disulfides,
            "esters": n_esters,
            "triazoles": n_triazoles,
        }
    }

def score_mechanism_resolved_stability(smiles: str) -> dict[str, Any]:
    """Assess linker functional groups for distinct biochemical stability liabilities."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"overall_stability_score": 0.0, "liabilities": []}
        
    liabilities = []
    
    # 1. Peptide Cleavage (Cathepsin sensitivity)
    # Val-Cit, Val-Ala or general protease amide bonds
    val_cit_query = Chem.MolFromSmarts("CC(C)[C@@H](C(=O)N[C@@H](CCCNC(=O)N)C(=O)N)N")
    val_ala_query = Chem.MolFromSmarts("CC(C)[C@@H](C(=O)N[C@@H](C)C(=O)N)N")
    is_protease_cleavable = mol.HasSubstructMatch(val_cit_query) or mol.HasSubstructMatch(val_ala_query) if val_cit_query and val_ala_query else False
    
    # 2. Disulfide reduction (redox labile)
    disulfide_query = Chem.MolFromSmarts("[#16X2][#16X2]")
    is_disulfide = mol.HasSubstructMatch(disulfide_query) if disulfide_query else False
    if is_disulfide:
        liabilities.append("disulfide_reduction")
        
    # 3. Maleimide deconjugation / Thiol exchange risk
    maleimide_query = Chem.MolFromSmarts("O=C1C=CC(=O)N1")
    is_maleimide = mol.HasSubstructMatch(maleimide_query) if maleimide_query else False
    if is_maleimide:
        liabilities.append("maleimide_deconjugation")
        
    # 4. Hydrolysis / Acetal / Hydrazone stability
    hydrazone_query = Chem.MolFromSmarts("[CX3]=[NX2][NX3]")
    acetal_query = Chem.MolFromSmarts("[CX4]([OX2H0])[OX2H0]")
    is_hydrazone = mol.HasSubstructMatch(hydrazone_query) if hydrazone_query else False
    is_acetal = mol.HasSubstructMatch(acetal_query) if acetal_query else False
    if is_hydrazone:
        liabilities.append("hydrazone_acid_hydrolysis")
    if is_acetal:
        liabilities.append("acetal_hydrolysis")
        
    # Base stability score (1.0 is extremely stable in plasma)
    score = 1.0
    
    if "hydrazone_acid_hydrolysis" in liabilities:
        score -= 0.50  # severe plasma instability
    if "acetal_hydrolysis" in liabilities:
        score -= 0.40  # severe plasma instability
    if "disulfide_reduction" in liabilities:
        score -= 0.20  # moderate redox-lability in plasma
    if "maleimide_deconjugation" in liabilities:
        score -= 0.15  # thiol exchange risk
        
    return {
        "overall_stability_score": round(max(0.0, score), 3),
        "liabilities": liabilities,
        "is_protease_cleavable": is_protease_cleavable,
        "is_disulfide": is_disulfide,
        "is_maleimide": is_maleimide,
        "is_hydrazone": is_hydrazone,
    }
