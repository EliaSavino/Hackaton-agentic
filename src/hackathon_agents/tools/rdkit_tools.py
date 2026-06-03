from __future__ import annotations

from typing import Any

from hackathon_agents.schemas.molecules import MoleculeFilterConstraints
from hackathon_agents.tools.base import error_result, ok_result


def _load_rdkit() -> tuple[Any, Any, Any, Any] | None:
    try:
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, Lipinski, QED, rdMolDescriptors

        return Chem, Descriptors, Crippen, (Lipinski, QED, rdMolDescriptors)
    except Exception:
        return None


def validate_smiles(smiles: str):
    loaded = _load_rdkit()
    if loaded is None:
        return error_result("RDKit is not installed or could not be imported.", {"smiles": smiles, "valid": False})

    Chem, _, _, _ = loaded
    mol = Chem.MolFromSmiles(smiles)
    valid = mol is not None
    canonical = Chem.MolToSmiles(mol) if valid else None
    return ok_result({"smiles": smiles, "valid": valid, "canonical_smiles": canonical})


def compute_descriptors(smiles: str):
    loaded = _load_rdkit()
    if loaded is None:
        return error_result("RDKit is not installed or could not be imported.", {"smiles": smiles})

    Chem, Descriptors, Crippen, extra = loaded
    Lipinski, QED, rdMolDescriptors = extra
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return error_result("Invalid SMILES.", {"smiles": smiles})

    data = {
        "smiles": smiles,
        "canonical_smiles": Chem.MolToSmiles(mol),
        "mol_wt": float(Descriptors.MolWt(mol)),
        "logp": float(Crippen.MolLogP(mol)),
        "hbd": int(Lipinski.NumHDonors(mol)),
        "hba": int(Lipinski.NumHAcceptors(mol)),
        "tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
        "rotatable_bonds": int(Lipinski.NumRotatableBonds(mol)),
        "heavy_atoms": int(mol.GetNumHeavyAtoms()),
        "ring_count": int(rdMolDescriptors.CalcNumRings(mol)),
        "qed": float(QED.qed(mol)),
    }
    return ok_result(data)


def _passes_constraints(descriptors: dict[str, Any], constraints: MoleculeFilterConstraints) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    mol_wt = float(descriptors.get("mol_wt", 0.0))
    logp = float(descriptors.get("logp", 0.0))
    qed = float(descriptors.get("qed", 0.0))
    tpsa = float(descriptors.get("tpsa", 0.0))

    if constraints.min_mol_wt is not None and mol_wt < constraints.min_mol_wt:
        reasons.append("below_min_mol_wt")
    if constraints.max_mol_wt is not None and mol_wt > constraints.max_mol_wt:
        reasons.append("above_max_mol_wt")
    if constraints.max_logp is not None and logp > constraints.max_logp:
        reasons.append("above_max_logp")
    if constraints.min_qed is not None and qed < constraints.min_qed:
        reasons.append("below_min_qed")
    if constraints.max_tpsa is not None and tpsa > constraints.max_tpsa:
        reasons.append("above_max_tpsa")

    return not reasons, reasons


def filter_molecules(smiles_list: list[str], constraints: MoleculeFilterConstraints | dict[str, Any] | None = None):
    parsed_constraints = (
        constraints
        if isinstance(constraints, MoleculeFilterConstraints)
        else MoleculeFilterConstraints.model_validate(constraints or {})
    )

    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    errors: list[str] = []

    for smiles in smiles_list:
        result = compute_descriptors(smiles)
        if not result.ok:
            errors.append(f"{smiles}: {result.error}")
            rejected.append({"smiles": smiles, "reasons": ["invalid_or_unavailable"], "error": result.error})
            continue

        keep, reasons = _passes_constraints(result.data, parsed_constraints)
        record = {"smiles": smiles, "descriptors": result.data}
        if keep:
            kept.append(record)
        else:
            rejected.append({**record, "reasons": reasons})

    return ok_result(
        {
            "kept": kept,
            "rejected": rejected,
            "constraints": parsed_constraints.model_dump(mode="json"),
            "errors": errors,
        }
    )
