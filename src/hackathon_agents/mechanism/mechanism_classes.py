from __future__ import annotations

from enum import Enum


class MechanismClass(str, Enum):
    """Supported high-level mechanistic classes for hypothesis generation."""

    RADICAL_CHAIN = "radical chain"
    PHOTOREDOX_CATALYTIC_CYCLE = "photoredox catalytic cycle"
    NICKEL_CATALYTIC_CYCLE = "nickel catalytic cycle"
    ORGANOCATALYTIC_CYCLE = "organocatalytic cycle"
    ACID_BASE_CATALYSIS = "acid/base catalysis"
    NUCLEOPHILIC_SUBSTITUTION = "nucleophilic substitution"
    ELIMINATION = "elimination"
    LIGAND_EXCHANGE = "ligand exchange"
    ELECTRON_TRANSFER = "electron transfer"
    MASS_TRANSFER_LIMITED_APPARENT_KINETICS = "mass-transfer-limited apparent kinetics"
    CATALYST_DEACTIVATION = "catalyst deactivation"
    PRODUCT_INHIBITION = "product inhibition"
    UNKNOWN_MIXED = "unknown / mixed"


MECHANISM_CLASS_DESCRIPTIONS: dict[MechanismClass, str] = {
    MechanismClass.RADICAL_CHAIN: "Propagation, inhibition, and light or initiator sensitivity are expected.",
    MechanismClass.PHOTOREDOX_CATALYTIC_CYCLE: "Reaction rate may depend on photon flux, quencher, and catalyst loading.",
    MechanismClass.NICKEL_CATALYTIC_CYCLE: "Oxidative addition, transmetalation or ligand exchange, and reductive elimination may control rate.",
    MechanismClass.ORGANOCATALYTIC_CYCLE: "Covalent or H-bonding activation steps can create saturation kinetics.",
    MechanismClass.ACID_BASE_CATALYSIS: "Rate is expected to depend on proton donors, bases, pH, or buffer strength.",
    MechanismClass.NUCLEOPHILIC_SUBSTITUTION: "Substrate and nucleophile order distinguish associative and dissociative variants.",
    MechanismClass.ELIMINATION: "Base strength, leaving group, and competing substitution pathways are diagnostic.",
    MechanismClass.LIGAND_EXCHANGE: "Ligand concentration and metal speciation should perturb the observed rate.",
    MechanismClass.ELECTRON_TRANSFER: "Redox potential, donor or acceptor concentration, and ionic strength may be diagnostic.",
    MechanismClass.MASS_TRANSFER_LIMITED_APPARENT_KINETICS: "Observed kinetics may track mixing, light penetration, or phase transfer instead of intrinsic chemistry.",
    MechanismClass.CATALYST_DEACTIVATION: "Rate slows disproportionately over time or with cumulative turnover.",
    MechanismClass.PRODUCT_INHIBITION: "Added product should suppress the apparent rate or change induction behavior.",
    MechanismClass.UNKNOWN_MIXED: "The current evidence is insufficient to select a single mechanistic class.",
}


def all_mechanism_classes() -> list[str]:
    """Return mechanism class labels in a stable display order."""

    return [mechanism_class.value for mechanism_class in MechanismClass]
