SCORERS = {
    # Solubility — logP is the standard cheap proxy (lower = more soluble)
    "solubility": LogP(),
    "logp": LogP(),

    # Synthesizability — SA score, 1 (easy) to 10 (hard)
    "synthesizability": SAScore(),
    "sa_score": SAScore(),

    # Drug-likeness
    "drug_likeness": QEDScore(),
    "qed": QEDScore(),
    "lipinski_violations": LipinskiViolations(),

    # Size
    "num_atoms": NumAtoms(),
    "heavy_atoms": NumAtoms(include_h=False),

    # Permeability / polarity
    "polar_surface_area": TPSA(),
    "tpsa": TPSA(),

    # Flexibility
    "rotatable_bonds": RotatableBonds(),

    # H-bonding
    "h_bond_donors": HBondDonors(),
    "h_bond_acceptors": HBondAcceptors(),
}