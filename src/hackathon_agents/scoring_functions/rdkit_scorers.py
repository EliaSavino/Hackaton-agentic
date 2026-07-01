from abc import ABC, abstractmethod
import os, sys
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, QED, rdMolDescriptors

# SA scorer lives in RDKit's Contrib folder
from rdkit.Chem import RDConfig
sys.path.append(os.path.join(RDConfig.RDContribDir, 'SA_Score'))
import sascorer  # noqa: E402


class ScoreFunction(ABC):
    """Base class: SMILES -> float."""

    @abstractmethod
    def _score(self, mol: Chem.Mol) -> float:
        ...

    def __call__(self, smiles: str) -> float:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return float("nan")
        return float(self._score(mol))


class SAScore(ScoreFunction):
    """Synthetic accessibility, 1 (easy) to 10 (hard)."""
    def _score(self, mol):
        return sascorer.calculateScore(mol)


class LogP(ScoreFunction):
    """Crippen logP (Wildman-Crippen)."""
    def _score(self, mol):
        return Descriptors.MolLogP(mol)


class NumAtoms(ScoreFunction):
    """Heavy atom count. Set include_h=True for all atoms."""
    def __init__(self, include_h: bool = False):
        self.include_h = include_h
    def _score(self, mol):
        if self.include_h:
            return Chem.AddHs(mol).GetNumAtoms()
        return mol.GetNumHeavyAtoms()


class QEDScore(ScoreFunction):
    """Quantitative Estimate of Drug-likeness, 0-1 (higher = more drug-like)."""
    def _score(self, mol):
        return QED.qed(mol)


class LipinskiViolations(ScoreFunction):
    """Number of Lipinski Ro5 violations (0-4)."""
    def _score(self, mol):
        v = 0
        if Descriptors.MolWt(mol) > 500: v += 1
        if Descriptors.MolLogP(mol) > 5: v += 1
        if Lipinski.NumHDonors(mol) > 5: v += 1
        if Lipinski.NumHAcceptors(mol) > 10: v += 1
        return v


class RotatableBonds(ScoreFunction):
    def _score(self, mol):
        return Lipinski.NumRotatableBonds(mol)


class TPSA(ScoreFunction):
    """Topological polar surface area (Å²)."""
    def _score(self, mol):
        return rdMolDescriptors.CalcTPSA(mol)


class HBondDonors(ScoreFunction):
    def _score(self, mol):
        return Lipinski.NumHDonors(mol)


class HBondAcceptors(ScoreFunction):
    def _score(self, mol):
        return Lipinski.NumHAcceptors(mol)