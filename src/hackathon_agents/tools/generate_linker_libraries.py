import pandas as pd
from rdkit import Chem
from rdkit.Chem import AllChem
import os

# Define paths
csv_path = "/home/miquelaperez/Hackaton-agentic/data/linkers/linkers.csv"
output_dir = "/home/miquelaperez/Hackaton-agentic/data/linkers"

print("Loading linkers dataset...")
df = pd.read_csv(csv_path, encoding="latin-1")
print(f"Loaded {len(df)} entries from {csv_path}")

# =====================================================================
# 1. Chemical Deprotection and Cleansing
# =====================================================================

# List of deprotection reactions (Reaction SMARTS)
deprotect_reactions = [
    # Fmoc -> H
    AllChem.ReactionFromSmarts("[N:1]C(=O)OCC1C2=CC=CC=C2C3=CC=CC=C31 >> [N:1]"),
    AllChem.ReactionFromSmarts("[N:1]C(=O)OCC1c2ccccc2-c2ccccc21 >> [N:1]"),
    # Boc -> H
    AllChem.ReactionFromSmarts("[N:1]C(=O)OC(C)(C)C >> [N:1]"),
    # Alloc -> H
    AllChem.ReactionFromSmarts("[N:1]C(=O)OCC=C >> [N:1]"),
    # Trt (Trityl) -> H
    AllChem.ReactionFromSmarts("[N:1]C(c1ccccc1)(c1ccccc1)c1ccccc1 >> [N:1]"),
    # Cbz -> H
    AllChem.ReactionFromSmarts("[N:1]C(=O)OCc1ccccc1 >> [N:1]"),
    # Acetyl on sugar hydroxyls (triacetates) -> OH
    AllChem.ReactionFromSmarts("[O:1]C(=O)C >> [O:1]"),
    # Methyl ester of glucuronide -> free acid
    AllChem.ReactionFromSmarts("[C:1](=O)OC >> [C:1](=O)O"),
]

def deprotect_molecule(smiles: str) -> str:
    """Applies deprotection reactions sequentially until no more matches are found."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return smiles
    
    changed = True
    while changed:
        changed = False
        for rxn in deprotect_reactions:
            products = rxn.RunReactants((mol,))
            if products and len(products[0]) > 0:
                mol = products[0][0]
                Chem.SanitizeMol(mol)
                changed = True
                break # Start over with the new molecule structure
                
    return Chem.MolToSmiles(mol, canonical=True)


# List of deactivation/hydrolysis reactions for leaving/activating groups
deactivation_reactions = [
    # PNP carbonate -> OH (on PAB-PNP or similar carbamates)
    AllChem.ReactionFromSmarts("[C:1]OC(=O)Oc2ccc([N+](=O)[O-])cc2 >> [C:1]O"),
    AllChem.ReactionFromSmarts("[C:1]COC(=O)Oc2ccc([N+](=O)[O-])cc2 >> [C:1]CO"),
    # NHS ester -> Carboxylic Acid
    AllChem.ReactionFromSmarts("[C:1](=O)ON2C(=O)CCC2=O >> [C:1](=O)O"),
    # PFP ester (perfluorophenyl) -> Carboxylic Acid
    AllChem.ReactionFromSmarts("[C:1](=O)Oc2c(F)c(F)c(F)c(F)c2F >> [C:1](=O)O"),
    # PNP ester -> Carboxylic Acid
    AllChem.ReactionFromSmarts("[C:1](=O)Oc2ccc([N+](=O)[O-])cc2 >> [C:1](=O)O"),
]

def deactivate_leaving_groups(smiles: str) -> str:
    """Converts activated esters/carbonates to their stable acid/alcohol precursors."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return smiles
    
    changed = True
    while changed:
        changed = False
        for rxn in deactivation_reactions:
            products = rxn.RunReactants((mol,))
            if products and len(products[0]) > 0:
                mol = products[0][0]
                Chem.SanitizeMol(mol)
                changed = True
                break
                
    return Chem.MolToSmiles(mol, canonical=True)


# =====================================================================
# 2. Antibody Conjugation Warhead Definitions (Library A)
# =====================================================================

# Standardized warhead SMILES definitions for the final output
standard_warheads = {
    "DBCO": "N1Cc2ccccc2C#Cc2ccccc21",
    "BCN": "CC1C2C1CCC#CCC2",
    "Maleimide": "O=C1C=CC(=O)N1",
    "NHS_ester": "C(=O)ON1C(=O)CCC1=O",
    "Sulfo-NHS_ester": "C(=O)ON1C(=O)CC(S(=O)(=O)O)C1=O",
    "Azide": "[N-]=[N+]=N",
    "Alkyne": "C#C",
    "Pyridyldisulfanyl": "SSc1ccccn1",
    "Bromoacetamide": "NC(=O)CBr",
    "Aldehyde": "C=O",
    "Oxyamine": "CON",
    "Thiol": "CS"
}

# Substructure matching order (Checked sequentially to avoid false positives)
# e.g. checking DBCO/BCN before Alkyne because they contain alkynes
matching_patterns = [
    ("DBCO", Chem.MolFromSmiles("N1Cc2ccccc2C#Cc2ccccc21")),
    ("BCN", Chem.MolFromSmiles("CC1C2C1CCC#CCC2")),
    ("Maleimide", Chem.MolFromSmarts("[C,H]1=C[C,H](=O)N([C,H]1=O)")),
    ("NHS_ester", Chem.MolFromSmarts("C(=O)ON1C(=O)CCC1=O")),
    ("Sulfo-NHS_ester", Chem.MolFromSmarts("C(=O)ON1C(=O)CC(S(=O)(=O)O)C1=O")),
    ("Azide", Chem.MolFromSmarts("[N-]=[N+]=N")),
    ("Alkyne", Chem.MolFromSmarts("C#C")),
    ("Pyridyldisulfanyl", Chem.MolFromSmarts("SSc1ccccn1")),
    ("Bromoacetamide", Chem.MolFromSmarts("NC(=O)CBr")),
    ("Aldehyde", Chem.MolFromSmarts("[CX3H1]=O")),
    ("Oxyamine", Chem.MolFromSmarts("CON")),
    ("Thiol", Chem.MolFromSmarts("[SD2H1]"))
]

def identify_antibody_warhead(mol) -> tuple[str, str] | None:
    """Finds the antibody warhead type and returns (type, standardized smiles)."""
    if mol is None:
        return None
        
    for name, pattern in matching_patterns:
        if pattern is not None and mol.HasSubstructMatch(pattern):
            # Map Sulfo-NHS_ester to NHS_ester for simplicity, or keep distinct
            mapped_name = "NHS_ester" if name == "Sulfo-NHS_ester" else name
            return mapped_name, standard_warheads[mapped_name]
            
    return None


# =====================================================================
# 3. Cleavable Trigger Definitions (Library B)
# =====================================================================

# Standardized trigger SMILES definitions for the final output
standard_triggers = {
    "Val-Cit-PAB": "CC(C)[C@@H](C(=O)N[C@@H](CCCNC(=O)N)C(=O)Nc1ccc(CO)cc1)N",
    "Phe-Lys-PAB": "c1ccccc1C[C@@H](C(=O)N[C@@H](CCCCN)C(=O)Nc1ccc(CO)cc1)N",
    "Val-Ala-PAB": "CC(C)[C@@H](C(=O)N[C@@H](C)C(=O)Nc1ccc(CO)cc1)N",
    "Glucuronide": "OC(=O)[C@@H]1O[C@@H](Oc2ccc(CO)cc2)[C@@H](O)[C@H](O)[C@H]1O"
}

# Substructure matching for triggers (includes stereospecific and generic SMARTS fallbacks)
trigger_patterns = [
    ("Val-Cit-PAB", Chem.MolFromSmarts("NC(C(C)C)C(=O)NC(CCCNC(=O)N)C(=O)Nc1ccc(CO)cc1")),
    ("Val-Cit-PAB", Chem.MolFromSmarts("C(CCCNC(=O)N)C(C(=O)Nc1ccc(CO)cc1)NC(=O)C(C(C)C)")),
    ("Phe-Lys-PAB", Chem.MolFromSmarts("NC(Cc1ccccc1)C(=O)NC(CCCCN)C(=O)Nc1ccc(CO)cc1")),
    ("Phe-Lys-PAB", Chem.MolFromSmarts("C(CCCCN)C(C(=O)Nc1ccc(CO)cc1)NC(=O)C(Cc1ccccc1)")),
    ("Val-Ala-PAB", Chem.MolFromSmarts("NC(C(C)C)C(=O)NC(C)C(=O)Nc1ccc(CO)cc1")),
    ("Val-Ala-PAB", Chem.MolFromSmarts("C(C)C(C(=O)Nc1ccc(CO)cc1)NC(=O)C(C(C)C)")),
    ("Glucuronide", Chem.MolFromSmarts("OC(=O)C1OC(Oc2ccc(CO)cc2)C(O)C(O)C1O")),
    ("Glucuronide", Chem.MolFromSmarts("C1(C(C(C(C(O1)Oc2ccc(CO)cc2)O)O)O)C(=O)O")),
]

def identify_payload_trigger(mol) -> tuple[str, str] | None:
    """Finds the payload trigger type and returns (type, standardized smiles)."""
    if mol is None:
        return None
        
    for name, pattern in trigger_patterns:
        if pattern is not None and mol.HasSubstructMatch(pattern):
            return name, standard_triggers[name]
            
    return None


# =====================================================================
# 4. Processing Pipeline
# =====================================================================

lib_a_data = []
lib_b_data = []

for idx, row in df.iterrows():
    raw_smiles = row["smiles"]
    prod_name = str(row["Product name"])
    
    # 1. Verify SMILES validity
    mol = Chem.MolFromSmiles(raw_smiles)
    if mol is None:
        print(f"Skipping invalid SMILES at index {idx}: {raw_smiles}")
        continue
        
    canonical_raw = Chem.MolToSmiles(mol, canonical=True)
    
    # 2. Virtual Deprotection
    deprotected_smiles = deprotect_molecule(canonical_raw)
    deprotected_mol = Chem.MolFromSmiles(deprotected_smiles)
    if deprotected_mol is None:
        continue
        
    # 3. Virtual Deactivation (leaving group stripping)
    deactivated_smiles = deactivate_leaving_groups(deprotected_smiles)
    deactivated_mol = Chem.MolFromSmiles(deactivated_smiles)
    
    # 4. Extract Antibody End (Library A)
    # We use deprotected_mol so we can detect active esters (like NHS) and disulfides
    ab_info = identify_antibody_warhead(deprotected_mol)
    if ab_info:
        warhead_type, warhead_smiles = ab_info
        lib_a_data.append({
            "Original_Name": prod_name,
            "Original_SMILES": raw_smiles,
            "Deprotected_SMILES": deprotected_smiles,
            "Warhead_Type": warhead_type,
            "Warhead_SMILES": warhead_smiles
        })
        
    # 5. Extract Payload Cleavable Trigger (Library B)
    # We use deactivated_mol to get clean, ready-to-couple trigger alcohols/acids
    trigger_info = identify_payload_trigger(deactivated_mol or deprotected_mol)
    if trigger_info:
        trigger_type, trigger_smiles = trigger_info
        lib_b_data.append({
            "Original_Name": prod_name,
            "Original_SMILES": raw_smiles,
            "Cleaned_SMILES": deactivated_smiles,
            "Trigger_Type": trigger_type,
            "Trigger_SMILES": trigger_smiles
        })

print(f"Extraction complete: Found {len(lib_a_data)} raw Library A candidates and {len(lib_b_data)} raw Library B candidates.")

# Create candidate dataframes
df_a = pd.DataFrame(lib_a_data)
df_b = pd.DataFrame(lib_b_data)

# =====================================================================
# 5. De-duplication and Verification
# =====================================================================

# Keep only chemically unique deprotected/cleaned linkers to avoid duplicates
df_a_unique = df_a.drop_duplicates(subset=["Deprotected_SMILES"])
df_b_unique = df_b.drop_duplicates(subset=["Cleaned_SMILES"])

# Verify all SMILES make actual sense (RDKit can re-parse them and they are not empty)
def verify_smiles_list(smiles_list):
    for s in smiles_list:
        m = Chem.MolFromSmiles(s)
        if m is None:
            raise ValueError(f"SMILES is chemically invalid: {s}")
    return True

verify_smiles_list(df_a_unique["Deprotected_SMILES"])
verify_smiles_list(df_b_unique["Cleaned_SMILES"])

# Ensure directories exist
os.makedirs(output_dir, exist_ok=True)

# Save the finalized libraries
path_a = os.path.join(output_dir, "Library_A_Antibody_Ends.csv")
path_b = os.path.join(output_dir, "Library_B_Payload_Triggers.csv")

df_a_unique.to_csv(path_a, index=False)
df_b_unique.to_csv(path_b, index=False)

print("\nValidation Succeeded! Both libraries are clean, chemically valid, and have no duplicates.")
print(f"Library A (Antibody Ends): Saved {len(df_a_unique)} unique entries to {path_a}")
print(f"Library B (Payload Triggers): Saved {len(df_b_unique)} unique entries to {path_b}")
