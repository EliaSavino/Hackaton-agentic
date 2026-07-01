from __future__ import annotations

from typing import Any, Mapping

from hackathon_agents.schemas.molecules import MoleculeFilterConstraints
from hackathon_agents.tools.base import error_result, ok_result


def _load_rdkit() -> tuple[Any, Any, Any, Any] | None:
    try:
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, Lipinski, QED, rdMolDescriptors

        return Chem, Descriptors, Crippen, (Lipinski, QED, rdMolDescriptors)
    except Exception:
        return None


DEFAULT_REACTIVE_ALERT_SMARTS: dict[str, str] = {
    # Strongly reactive / unstable motifs that should rarely appear in generated linkers.
    "acid_chloride": "C(=O)Cl",
    "acyl_bromide": "C(=O)Br",
    "anhydride": "C(=O)OC(=O)",
    "isocyanate": "N=C=O",
    "isothiocyanate": "N=C=S",
    "sulfonyl_chloride": "S(=O)(=O)Cl",
    "peroxide": "[OX2][OX2]",
    "diazo": "[N-]=[N+]=[*]",
    "azide": "[N-]=[N+]=N",
    "unwanted_free_thiol": "[SX2H]",
    "aldehyde": "[CX3H1](=O)[#6]",
    "epoxide": "[OX2r3]1[#6r3][#6r3]1",
    "strained_aziridine": "[NX3r3]1[#6r3][#6r3]1",
    "beta_lactone": "O=C1OCC1",
    "beta_lactam": "O=C1NCC1",
    "alkyl_halide": "[CX4][Cl,Br,I]",
}


def validate_smiles(smiles: str):
    loaded = _load_rdkit()
    if loaded is None:
        return error_result(
            "RDKit is not installed or could not be imported.",
            {"smiles": smiles, "valid": False},
        )

    Chem, _, _, _ = loaded
    mol = Chem.MolFromSmiles(smiles)
    valid = mol is not None
    canonical = Chem.MolToSmiles(mol) if valid else None

    return ok_result(
        {
            "smiles": smiles,
            "valid": valid,
            "canonical_smiles": canonical,
        }
    )


def _largest_ring_size(mol: Any) -> int:
    ring_info = mol.GetRingInfo()
    atom_rings = ring_info.AtomRings()
    if not atom_rings:
        return 0
    return max(len(ring) for ring in atom_rings)


def _element_counts(mol: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol()
        counts[symbol] = counts.get(symbol, 0) + 1
    return counts


def _hetero_atom_count(mol: Any) -> int:
    return sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() not in {1, 6})


def _halogen_count(mol: Any) -> int:
    return sum(1 for atom in mol.GetAtoms() if atom.GetSymbol() in {"F", "Cl", "Br", "I"})


def _safe_descriptor_call(func: Any, mol: Any, default: Any = None) -> Any:
    try:
        return func(mol)
    except Exception:
        return default


def _smarts_matches(mol: Any, smarts_map: Mapping[str, str]) -> dict[str, int]:
    loaded = _load_rdkit()
    if loaded is None:
        return {}

    Chem, _, _, _ = loaded
    hits: dict[str, int] = {}

    for name, smarts in smarts_map.items():
        patt = Chem.MolFromSmarts(smarts)
        if patt is None:
            continue
        matches = mol.GetSubstructMatches(patt)
        if matches:
            hits[name] = len(matches)

    return hits


def compute_descriptors(smiles: str):
    loaded = _load_rdkit()
    if loaded is None:
        return error_result(
            "RDKit is not installed or could not be imported.",
            {"smiles": smiles},
        )

    Chem, Descriptors, Crippen, extra = loaded
    Lipinski, QED, rdMolDescriptors = extra

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return error_result("Invalid SMILES.", {"smiles": smiles})

    element_counts = _element_counts(mol)
    reactive_alert_hits = _smarts_matches(mol, DEFAULT_REACTIVE_ALERT_SMARTS)

    aromatic_rings = _safe_descriptor_call(rdMolDescriptors.CalcNumAromaticRings, mol, 0)
    aliphatic_rings = _safe_descriptor_call(rdMolDescriptors.CalcNumAliphaticRings, mol, 0)
    saturated_rings = _safe_descriptor_call(rdMolDescriptors.CalcNumSaturatedRings, mol, 0)
    heterocycles = _safe_descriptor_call(rdMolDescriptors.CalcNumHeterocycles, mol, 0)
    fraction_csp3 = _safe_descriptor_call(rdMolDescriptors.CalcFractionCSP3, mol, 0.0)
    bridgehead_atoms = _safe_descriptor_call(rdMolDescriptors.CalcNumBridgeheadAtoms, mol, 0)
    spiro_atoms = _safe_descriptor_call(rdMolDescriptors.CalcNumSpiroAtoms, mol, 0)
    amide_bonds = _safe_descriptor_call(getattr(rdMolDescriptors, "CalcNumAmideBonds", None), mol, None)

    data = {
        "smiles": smiles,
        "canonical_smiles": Chem.MolToSmiles(mol),
        "formula": rdMolDescriptors.CalcMolFormula(mol),
        "mol_wt": float(Descriptors.MolWt(mol)),
        "exact_mol_wt": float(Descriptors.ExactMolWt(mol)),
        "logp": float(Crippen.MolLogP(mol)),
        "molar_refractivity": float(Crippen.MolMR(mol)),
        "hbd": int(Lipinski.NumHDonors(mol)),
        "hba": int(Lipinski.NumHAcceptors(mol)),
        "tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
        "rotatable_bonds": int(Lipinski.NumRotatableBonds(mol)),
        "heavy_atoms": int(mol.GetNumHeavyAtoms()),
        "hetero_atoms": int(_hetero_atom_count(mol)),
        "halogens": int(_halogen_count(mol)),
        "formal_charge": int(Chem.GetFormalCharge(mol)),
        "ring_count": int(rdMolDescriptors.CalcNumRings(mol)),
        "aromatic_rings": int(aromatic_rings or 0),
        "aliphatic_rings": int(aliphatic_rings or 0),
        "saturated_rings": int(saturated_rings or 0),
        "heterocycles": int(heterocycles or 0),
        "largest_ring_size": int(_largest_ring_size(mol)),
        "fraction_csp3": float(fraction_csp3 or 0.0),
        "bridgehead_atoms": int(bridgehead_atoms or 0),
        "spiro_atoms": int(spiro_atoms or 0),
        "amide_bonds": int(amide_bonds) if amide_bonds is not None else None,
        "qed": float(QED.qed(mol)),
        "element_counts": element_counts,
        "elements": sorted(element_counts.keys()),
        "reactive_alert_hits": reactive_alert_hits,
    }

    return ok_result(data)


def _normalise_constraints(
    constraints: MoleculeFilterConstraints | dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a dict of constraints.

    This keeps backward compatibility with MoleculeFilterConstraints while also
    allowing plain dict constraints that contain ADC/linker-specific keys not yet
    present in the Pydantic schema.
    """

    if constraints is None:
        try:
            return MoleculeFilterConstraints.model_validate({}).model_dump(mode="json")
        except Exception:
            return {}

    if isinstance(constraints, MoleculeFilterConstraints):
        return constraints.model_dump(mode="json")

    if isinstance(constraints, dict):
        try:
            base = MoleculeFilterConstraints.model_validate(constraints).model_dump(mode="json")
        except Exception:
            base = {}
        # Preserve extended keys even if MoleculeFilterConstraints does not know them yet.
        return {**base, **constraints}

    return {}


def _get_constraint(constraints: Mapping[str, Any], key: str, default: Any = None) -> Any:
    return constraints.get(key, default)


def _as_smarts_map(value: Any) -> dict[str, str]:
    """Accept either {"name": "SMARTS"} or ["SMARTS", ...]."""

    if value is None:
        return {}

    if isinstance(value, dict):
        return {str(name): str(smarts) for name, smarts in value.items()}

    if isinstance(value, list):
        return {str(smarts): str(smarts) for smarts in value}

    return {}


def _required_any_smarts_failures(mol: Any, required_any: Mapping[str, list[str]]) -> list[str]:
    loaded = _load_rdkit()
    if loaded is None:
        return ["rdkit_unavailable"]

    Chem, _, _, _ = loaded
    failures: list[str] = []

    for group_name, smarts_list in required_any.items():
        group_passes = False
        for smarts in smarts_list:
            patt = Chem.MolFromSmarts(str(smarts))
            if patt is not None and mol.HasSubstructMatch(patt):
                group_passes = True
                break
        if not group_passes:
            failures.append(f"missing_required_any_smarts:{group_name}")

    return failures


def _smarts_count_limit_failures(mol: Any, count_limits: Mapping[str, Any]) -> list[str]:
    """Check SMARTS-specific min/max count limits.

    Expected shape:
        {
            "maleimide": {"smarts": "...", "min": 1, "max": 1},
            "free_thiol": {"smarts": "[SX2H]", "max": 0},
        }
    """

    loaded = _load_rdkit()
    if loaded is None:
        return ["rdkit_unavailable"]

    Chem, _, _, _ = loaded
    failures: list[str] = []

    for name, spec in count_limits.items():
        if not isinstance(spec, dict):
            continue

        smarts = spec.get("smarts")
        if not smarts:
            continue

        patt = Chem.MolFromSmarts(str(smarts))
        if patt is None:
            failures.append(f"invalid_smarts_count_pattern:{name}")
            continue

        count = len(mol.GetSubstructMatches(patt))
        min_count = spec.get("min")
        max_count = spec.get("max")

        if min_count is not None and count < int(min_count):
            failures.append(f"below_min_smarts_count:{name}")
        if max_count is not None and count > int(max_count):
            failures.append(f"above_max_smarts_count:{name}")

    return failures


def _passes_constraints(
    smiles: str,
    descriptors: dict[str, Any],
    constraints: Mapping[str, Any],
) -> tuple[bool, list[str], dict[str, Any]]:
    loaded = _load_rdkit()
    if loaded is None:
        return False, ["rdkit_unavailable"], {}

    Chem, _, _, _ = loaded
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False, ["invalid_smiles"], {}

    reasons: list[str] = []
    details: dict[str, Any] = {}

    mol_wt = float(descriptors.get("mol_wt", 0.0))
    logp = float(descriptors.get("logp", 0.0))
    qed = float(descriptors.get("qed", 0.0))
    tpsa = float(descriptors.get("tpsa", 0.0))
    hbd = int(descriptors.get("hbd", 0))
    hba = int(descriptors.get("hba", 0))
    rotatable_bonds = int(descriptors.get("rotatable_bonds", 0))
    heavy_atoms = int(descriptors.get("heavy_atoms", 0))
    hetero_atoms = int(descriptors.get("hetero_atoms", 0))
    ring_count = int(descriptors.get("ring_count", 0))
    aromatic_rings = int(descriptors.get("aromatic_rings", 0))
    aliphatic_rings = int(descriptors.get("aliphatic_rings", 0))
    heterocycles = int(descriptors.get("heterocycles", 0))
    largest_ring_size = int(descriptors.get("largest_ring_size", 0))
    formal_charge = int(descriptors.get("formal_charge", 0))
    fraction_csp3 = float(descriptors.get("fraction_csp3", 0.0))
    elements = set(descriptors.get("elements", []))

    min_mol_wt = _get_constraint(constraints, "min_mol_wt")
    max_mol_wt = _get_constraint(constraints, "max_mol_wt")
    min_logp = _get_constraint(constraints, "min_logp")
    max_logp = _get_constraint(constraints, "max_logp")
    min_qed = _get_constraint(constraints, "min_qed")
    max_qed = _get_constraint(constraints, "max_qed")
    min_tpsa = _get_constraint(constraints, "min_tpsa")
    max_tpsa = _get_constraint(constraints, "max_tpsa")

    if min_mol_wt is not None and mol_wt < float(min_mol_wt):
        reasons.append("below_min_mol_wt")
    if max_mol_wt is not None and mol_wt > float(max_mol_wt):
        reasons.append("above_max_mol_wt")

    if min_logp is not None and logp < float(min_logp):
        reasons.append("below_min_logp")
    if max_logp is not None and logp > float(max_logp):
        reasons.append("above_max_logp")

    if min_qed is not None and qed < float(min_qed):
        reasons.append("below_min_qed")
    if max_qed is not None and qed > float(max_qed):
        reasons.append("above_max_qed")

    if min_tpsa is not None and tpsa < float(min_tpsa):
        reasons.append("below_min_tpsa")
    if max_tpsa is not None and tpsa > float(max_tpsa):
        reasons.append("above_max_tpsa")

    numeric_limits = {
        "hbd": hbd,
        "hba": hba,
        "rotatable_bonds": rotatable_bonds,
        "heavy_atoms": heavy_atoms,
        "hetero_atoms": hetero_atoms,
        "ring_count": ring_count,
        "aromatic_rings": aromatic_rings,
        "aliphatic_rings": aliphatic_rings,
        "heterocycles": heterocycles,
        "largest_ring_size": largest_ring_size,
        "fraction_csp3": fraction_csp3,
        "formal_charge": formal_charge,
    }

    for field, value in numeric_limits.items():
        min_key = f"min_{field}"
        max_key = f"max_{field}"

        if _get_constraint(constraints, min_key) is not None and value < float(_get_constraint(constraints, min_key)):
            reasons.append(f"below_{min_key}")

        if _get_constraint(constraints, max_key) is not None and value > float(_get_constraint(constraints, max_key)):
            reasons.append(f"above_{max_key}")

    max_abs_formal_charge = _get_constraint(constraints, "max_abs_formal_charge")
    if max_abs_formal_charge is not None and abs(formal_charge) > int(max_abs_formal_charge):
        reasons.append("above_max_abs_formal_charge")

    allowed_elements = _get_constraint(constraints, "allowed_elements")
    if allowed_elements:
        allowed = {str(symbol) for symbol in allowed_elements}
        disallowed = sorted(elements - allowed)
        details["disallowed_elements"] = disallowed
        if disallowed:
            reasons.append("contains_disallowed_elements")

    required_elements = _get_constraint(constraints, "required_elements")
    if required_elements:
        required = {str(symbol) for symbol in required_elements}
        missing = sorted(required - elements)
        details["missing_required_elements"] = missing
        if missing:
            reasons.append("missing_required_elements")

    forbidden_smarts = _as_smarts_map(_get_constraint(constraints, "forbidden_smarts"))
    if bool(_get_constraint(constraints, "reject_reactive_alerts", False)):
        forbidden_smarts = {**DEFAULT_REACTIVE_ALERT_SMARTS, **forbidden_smarts}

    forbidden_hits = _smarts_matches(mol, forbidden_smarts)
    details["forbidden_smarts_hits"] = forbidden_hits
    if forbidden_hits:
        reasons.append("forbidden_smarts_hit")

    required_smarts = _as_smarts_map(_get_constraint(constraints, "required_smarts"))
    required_hits = _smarts_matches(mol, required_smarts)
    details["required_smarts_hits"] = required_hits
    for name in required_smarts:
        if name not in required_hits:
            reasons.append(f"missing_required_smarts:{name}")

    required_any_smarts = _get_constraint(constraints, "required_any_smarts")
    if isinstance(required_any_smarts, dict):
        any_failures = _required_any_smarts_failures(mol, required_any_smarts)
        reasons.extend(any_failures)

    smarts_count_limits = _get_constraint(constraints, "smarts_count_limits")
    if isinstance(smarts_count_limits, dict):
        count_failures = _smarts_count_limit_failures(mol, smarts_count_limits)
        reasons.extend(count_failures)

    return not reasons, reasons, details


def filter_molecules(
    smiles_list: list[str],
    constraints: MoleculeFilterConstraints | dict[str, Any] | None = None,
):
    parsed_constraints = _normalise_constraints(constraints)

    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    errors: list[str] = []

    for smiles in smiles_list:
        result = compute_descriptors(smiles)
        if not result.ok:
            errors.append(f"{smiles}: {result.error}")
            rejected.append(
                {
                    "smiles": smiles,
                    "reasons": ["invalid_or_unavailable"],
                    "error": result.error,
                }
            )
            continue

        keep, reasons, details = _passes_constraints(smiles, result.data, parsed_constraints)
        record = {
            "smiles": smiles,
            "descriptors": result.data,
            "filter_details": details,
        }

        if keep:
            kept.append(record)
        else:
            rejected.append({**record, "reasons": reasons})

    return ok_result(
        {
            "kept": kept,
            "rejected": rejected,
            "constraints": parsed_constraints,
            "errors": errors,
        }
    )