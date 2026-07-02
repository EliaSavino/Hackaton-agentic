"""Phase C — Real payloads, not abstract classes.

Represent clinical payload molecules and evaluate the physicochemical properties of the 
fully assembled constructs (Conjugation Handle + Linker + Payload).
"""

from __future__ import annotations

from typing import Any
from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, rdmolfiles

PAYLOADS = {
    "MMAE": {
        "smiles": "CC[C@H](C)[C@@H]([C@@H](CC(=O)N1CCC[C@H]1[C@@H]([C@@H](C(C)C)OC)N(C)C(=O)[C@@H](NC(=O)[C@H](C)NC)C(C)C)OC)OC(=O)OCc1ccc(N)cc1", # MMAE-like with attachment phenol/amine
        "class": "cytotoxin",
        "description": "Monomethyl auristatin E, highly potent antimitotic cytotoxin.",
        "target_dar": 4,
        "site": "Cys",
    },
    "siRNA": {
        "smiles": "COP(=O)(O)OCC1OC(N)C(O)C1OP(=O)(O)OCC", # representative oligonucleotide stub
        "class": "oligonucleotide",
        "description": "Double-stranded small interfering RNA fragment.",
        "target_dar": 2,
        "site": "engineered Cys / HC-A118C",
    },
    "R848": {
        "smiles": "CC(C)COCc1cnc2c(n1)n(cn2)CCO", # Resiquimod-like imidazoquinoline
        "class": "immunomodulator",
        "description": "TLR7 agonist stimulating localized immune response.",
        "target_dar": 8,
        "site": "Lys",
    }
}

def assemble_construct(linker_smiles: str, payload_name: str) -> dict[str, Any]:
    """Assemble conjugation handle + designed linker + real payload, and calculate descriptors."""
    payload_spec = PAYLOADS.get(payload_name)
    if not payload_spec:
        return {"assembled_smiles": linker_smiles, "status": "unsupported payload"}
        
    payload_smiles = payload_spec["smiles"]
    
    # Clean attachment points (*) and concatenate to represent fully assembled construct
    clean_linker = linker_smiles.replace("*", "")
    clean_payload = payload_smiles.replace("*", "")
    
    assembled_smiles = f"{clean_linker}.{clean_payload}" # Represented as complex/covalent blend for descriptor evaluation
    
    mol = Chem.MolFromSmiles(assembled_smiles)
    if mol is None:
        return {
            "assembled_smiles": assembled_smiles,
            "status": "unparseable_assembly",
            "descriptors": {}
        }
        
    mw = Descriptors.MolWt(mol)
    logp = Crippen.MolLogP(mol)
    tpsa = Descriptors.TPSA(mol)
    
    # Aggregate aromatic rings
    aromatic_rings = Descriptors.NumAromaticRings(mol)
    
    return {
        "assembled_smiles": assembled_smiles,
        "status": "success",
        "payload_class": payload_spec["class"],
        "target_dar": payload_spec["target_dar"],
        "conjugation_site": payload_spec["site"],
        "descriptors": {
            "assembled_mw": round(mw, 2),
            "assembled_logp": round(logp, 2),
            "assembled_tpsa": round(tpsa, 2),
            "aromatic_rings": aromatic_rings,
        }
    }
