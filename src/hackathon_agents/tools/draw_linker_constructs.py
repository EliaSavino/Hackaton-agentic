"""RDKit-based structure-drawing tool for ADC-linker constructs.

This module renders 2D depictions of designed ADC linker fragments with
functional-role highlighting, matching the paper's Phase A colour spec.

Highlight legend (atoms + bonds coloured by functional role):

    * BLUE  (0.6, 0.8, 1.0) -> ``handle``   : conjugation handle / warhead
      (maleimide, DBCO/cyclooctyne, pyridyl-disulfide, generic disulfide,
      NHS ester, bromoacetamide, aminooxy).
    * RED   (1.0, 0.6, 0.6) -> ``scissile`` : cleavable / scissile bond
      (dipeptide protease amide, PABC benzyl carbamate, disulfide, hydrazone).
    * GREEN (0.6, 1.0, 0.6) -> ``spacer``   : spacer / solubilizer
      (PEG, sulfonate/sulfonamide, carboxylate).

Role precedence when an atom matches multiple roles:
``handle`` > ``scissile`` > ``spacer`` (higher-priority role wins; the atom
is removed from the lower-priority role's set).

Public functions
----------------
``classify_atoms(mol) -> dict[str, list[int]]``
``draw_construct(smiles, out_path, *, legend="", size=(500, 400)) -> Path | None``
``render_gallery(shortlist_path=..., out_dir=..., top_per_class=3) -> dict``
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SMARTS definitions for each functional role.
# ---------------------------------------------------------------------------

# Conjugation handles / warheads -> BLUE.
HANDLE_SMARTS: list[str] = [
    "O=C1C=CC(=O)N1",        # maleimide
    "C#Cc",                   # DBCO / cyclooctyne (aromatic-adjacent alkyne)
    "SSc1ccccn1",            # pyridyl-disulfide
    "[#16X2][#16X2]",        # generic disulfide
    "C(=O)ON1C(=O)CCC1=O",   # NHS ester
    "[Br][CH2]C(=O)N",       # bromoacetamide
    "NO",                     # aminooxy
]

# Cleavable / scissile motifs -> RED. Tightened (Reviewer 2, Part VI-C) so red marks
# the single scissile bond (the Cit/Ala->PABC anilide amide that cathepsin B cleaves,
# or a redox disulfide / acid hydrazone), NOT every carbonyl in the peptide backbone.
SCISSILE_SMARTS: list[str] = [
    "[CX3](=O)[NX3][c]",  # anilide amide: the Cit/Ala-PABC scissile bond (protease-cleaved)
    "[#16X2][#16X2]",      # disulfide (redox-scissile)
    "[CX3]=[NX2][NX3]",    # hydrazone (acid-scissile)
]

# Spacers / solubilizers -> GREEN.
SPACER_SMARTS: list[str] = [
    "[OX2][CH2][CH2][OX2]",  # PEG
    "S(=O)(=O)",              # sulfonate / sulfonamide
    "C(=O)[OX1,OX2H1]",       # carboxylate
]

# Highlight colours (RGB, 0-1).
COLOR_HANDLE = (0.6, 0.8, 1.0)   # light blue
COLOR_SCISSILE = (1.0, 0.6, 0.6)  # light red
COLOR_SPACER = (0.6, 1.0, 0.6)   # light green

# Role ordering for precedence (highest priority first).
_ROLE_ORDER = ("handle", "scissile", "spacer")
_ROLE_COLORS = {
    "handle": COLOR_HANDLE,
    "scissile": COLOR_SCISSILE,
    "spacer": COLOR_SPACER,
}


def _match_atoms(mol: Any, smarts_list: list[str]) -> set[int]:
    """Union all atom indices matched by any SMARTS in ``smarts_list``."""
    from rdkit import Chem

    matched: set[int] = set()
    for smarts in smarts_list:
        patt = Chem.MolFromSmarts(smarts)
        if patt is None:
            logger.warning("Invalid SMARTS pattern skipped: %s", smarts)
            continue
        for match in mol.GetSubstructMatches(patt):
            matched.update(match)
    return matched


def classify_atoms(mol: Any) -> dict[str, list[int]]:
    """Classify atoms of ``mol`` into functional roles by SMARTS matching.

    Returns a dict mapping each role (``"handle"``, ``"scissile"``,
    ``"spacer"``) to a list of unique atom indices. When an atom matches
    more than one role it is assigned only to the highest-priority role
    (handle > scissile > spacer).
    """
    if mol is None:
        return {role: [] for role in _ROLE_ORDER}

    raw = {
        "handle": _match_atoms(mol, HANDLE_SMARTS),
        "scissile": _match_atoms(mol, SCISSILE_SMARTS),
        "spacer": _match_atoms(mol, SPACER_SMARTS),
    }

    # Resolve overlaps by precedence: remove atoms already claimed by a
    # higher-priority role from lower-priority roles.
    claimed: set[int] = set()
    result: dict[str, list[int]] = {}
    for role in _ROLE_ORDER:
        unique = raw[role] - claimed
        claimed.update(unique)
        result[role] = sorted(unique)
    return result


def _bonds_within(mol: Any, atom_idxs: list[int]) -> list[int]:
    """Return bond indices whose both endpoints are in ``atom_idxs``."""
    atom_set = set(atom_idxs)
    bond_idxs: list[int] = []
    for bond in mol.GetBonds():
        if bond.GetBeginAtomIdx() in atom_set and bond.GetEndAtomIdx() in atom_set:
            bond_idxs.append(bond.GetIdx())
    return bond_idxs


def draw_construct(
    smiles: str,
    out_path: str | Path,
    *,
    legend: str = "",
    size: tuple[int, int] = (500, 400),
) -> Path | None:
    """Render a highlighted 2D depiction of ``smiles`` to ``out_path`` (PNG).

    Atoms (and the bonds among each set) are highlighted by functional role:
    handle=blue, scissile=red, spacer=green. Returns the output ``Path`` on
    success, or ``None`` (with a logged warning) if the SMILES cannot be
    parsed. Never raises on bad input.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem.Draw import rdMolDraw2D

    out_path = Path(out_path)

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("Could not parse SMILES, skipping draw: %s", smiles)
        return None

    try:
        # 2D coordinates.
        AllChem.Compute2DCoords(mol)

        roles = classify_atoms(mol)

        highlight_atoms: list[int] = []
        highlight_bonds: list[int] = []
        atom_colors: dict[int, tuple[float, float, float]] = {}
        bond_colors: dict[int, tuple[float, float, float]] = {}

        for role in _ROLE_ORDER:
            color = _ROLE_COLORS[role]
            atom_idxs = roles[role]
            for idx in atom_idxs:
                highlight_atoms.append(idx)
                atom_colors[idx] = color
            for bidx in _bonds_within(mol, atom_idxs):
                highlight_bonds.append(bidx)
                bond_colors[bidx] = color

        drawer = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
        rdMolDraw2D.PrepareAndDrawMolecule(
            drawer,
            mol,
            legend=legend,
            highlightAtoms=highlight_atoms,
            highlightBonds=highlight_bonds,
            highlightAtomColors=atom_colors,
            highlightBondColors=bond_colors,
        )
        drawer.FinishDrawing()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(drawer.GetDrawingText())
        return out_path
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to draw construct for SMILES %s: %s", smiles, exc)
        return None


def _entry_legend(entry: dict[str, Any]) -> str:
    """Build a compact legend string from a shortlist entry."""
    cls = entry.get("payload_class", "?")
    score = entry.get("composite_score")
    steps = entry.get("retrosynthesis", {}).get("step_count")
    stab = entry.get("stability", {}).get("overall_stability_score")

    parts = [str(cls)]
    if score is not None:
        parts.append(f"score={score:.3f}")
    if steps is not None:
        parts.append(f"cplx idx={steps}")  # heuristic complexity index, NOT synthetic steps
    if stab is not None:
        parts.append(f"stab={stab:.2f}")
    return " | ".join(parts)


def render_gallery(
    shortlist_path: str | Path = "deliverables/study4/shortlist.json",
    out_dir: str | Path = "deliverables/study4/figures",
    top_per_class: int = 3,
) -> dict:
    """Render individual + combined gallery figures for the shortlist.

    For each payload class, draws the top ``top_per_class`` linkers as
    individual PNGs (``struct_{class}_{i}.png``) with an informative legend,
    then assembles them into a single grid image ``structure_gallery.png``
    (rows=classes, cols=top_per_class) via matplotlib.

    Returns ``{"individual": {class: {i: path}}, "gallery": path}``.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    shortlist_path = Path(shortlist_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with shortlist_path.open() as fh:
        data = json.load(fh)
    shortlist = data.get("shortlist", {})

    individual: dict[str, dict[int, str]] = {}
    for cls, entries in shortlist.items():
        individual[cls] = {}
        for i, entry in enumerate(entries[:top_per_class]):
            smiles = entry.get("smiles", "")
            legend = _entry_legend(entry)
            out_path = out_dir / f"struct_{cls}_{i}.png"
            result = draw_construct(smiles, out_path, legend=legend)
            if result is not None:
                individual[cls][i] = str(result)

    # Assemble combined gallery grid: rows = classes, cols = top_per_class.
    classes = list(shortlist.keys())
    n_rows = max(len(classes), 1)
    n_cols = max(top_per_class, 1)

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(n_cols * 4.0, n_rows * 3.4),
        squeeze=False,
    )

    for r, cls in enumerate(classes):
        for c in range(n_cols):
            ax = axes[r][c]
            ax.axis("off")
            png_path = individual.get(cls, {}).get(c)
            if png_path and Path(png_path).exists():
                img = mpimg.imread(png_path)
                ax.imshow(img)
            if c == 0:
                ax.set_ylabel(
                    cls,
                    rotation=90,
                    fontsize=12,
                    fontweight="bold",
                    labelpad=20,
                )
                # ylabel needs an axis to attach to even with axis off.
                ax.axis("on")
                ax.set_xticks([])
                ax.set_yticks([])
                for spine in ax.spines.values():
                    spine.set_visible(False)

    # Fill trailing empty axes for classes beyond the actual list.
    for r in range(len(classes), n_rows):
        for c in range(n_cols):
            axes[r][c].axis("off")

    fig.suptitle(
        "ADC Linker Constructs (blue=handle, red=scissile, green=spacer)",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    gallery_path = out_dir / "structure_gallery.png"
    fig.savefig(gallery_path, dpi=150)
    plt.close(fig)

    return {"individual": individual, "gallery": str(gallery_path)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    output = render_gallery()
    print("Gallery:", output["gallery"])
    print("Individual figures:")
    for cls, mapping in output["individual"].items():
        for i, path in mapping.items():
            print(f"  [{cls}][{i}] -> {path}")
