"""Study 6 (publication) figures — Reviewer 2 Part VII.

Four figures, all from the shipped Study-5 JSON (no re-runs):
  Fig 1  journey   — one molecule from real quote -> exemplar -> rule -> structure -> Kd
  Fig 2  held-out  — the money figure: robust vs contested + evidence-composition strip
  Fig 3  steer     — objective weight heatmap + generated designs in subscore space
  Fig 4  cofold    — cathepsin-B recognition (Kd dot plot, log)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hackathon_agents.tools.consensus import disagreement_aware_confidence, evidence_composition

_COL = {"cytotoxin": "#3b7dd8", "oligonucleotide": "#5aa469", "immunomodulator": "#d1495b"}
_SHORT = {"cytotoxin": "Cytotoxin", "oligonucleotide": "Oligonucleotide (ARC)", "immunomodulator": "Immunomodulator (ISAC)"}
_DIRW = {"reward": "cleavable", "penalize": "non-cleavable", "ignore": "either"}


def _norm_dir(rule):
    from hackathon_agents.tools.lit_reasoning_s4 import normalize_rule
    return _DIRW.get(normalize_rule(rule)["cleavage_preference"], "?") if rule else "?"


# --------------------------------------------------------------------------- #
def fig2_heldout_composition(chains, heldout, out: Path) -> Path:
    """THE money figure: held-out confidence (disagreement-aware) + why (evidence split)."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    classes = ["cytotoxin", "immunomodulator", "oligonucleotide"]
    full_conf = [disagreement_aware_confidence(chains[c]["exemplars"])["score"] for c in classes]
    held = [disagreement_aware_confidence(heldout[c]["full_chain"]["exemplars"]) for c in classes]
    held_conf = [h["score"] for h in held]
    verdict = [heldout[c]["score"]["verdict"] for c in classes]
    full_dir = [_norm_dir(chains[c]["rule"]) for c in classes]
    held_dir = [_DIRW.get(heldout[c]["score"].get("predicted_cleavage"), "?") for c in classes]
    comps = [h["composition"] for h in held]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.8, 6.6), height_ratios=[2.15, 1.0])
    x = np.arange(len(classes)); w = 0.36

    # top: confidence bars (independent x; margins so edge bars aren't clipped)
    ax1.bar(x - w / 2, full_conf, w, label="full-corpus confidence", color="#9db8d9", edgecolor="black", lw=0.5)
    hc = ["#5aa469" if v == "agree" else "#d1495b" for v in verdict]
    ax1.bar(x + w / 2, held_conf, w, label="held-out confidence", color=hc, edgecolor="black", lw=0.5)
    ax1.set_ylabel("derived-rule confidence\n(disagreement-aware)"); ax1.set_ylim(0, 1.22); ax1.set_xlim(-0.7, 2.7)
    for i in range(len(classes)):
        ax1.text(x[i] - w / 2, full_conf[i] + 0.02, f"{full_dir[i]}\n{full_conf[i]:.2f}",
                 ha="center", va="bottom", fontsize=7, color="#555")
        flip = full_dir[i] != held_dir[i]
        col = "#7a1020" if verdict[i] != "agree" else "#2e6b3e"
        ax1.text(x[i] + w / 2, held_conf[i] + 0.02,
                 f"{held_dir[i]}\n{held_conf[i]:.2f}\n{'FLIPS' if flip else 'recovers'}",
                 ha="center", va="bottom", fontsize=7, color=col, fontweight="bold")
    ax1.set_xticks(x); ax1.set_xticklabels([_SHORT[c] for c in classes], fontsize=8)
    ax1.legend(fontsize=8, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.0), frameon=True)
    ax1.set_title("Held-out test: robust rules recover; the ARC rule flips and its confidence collapses",
                  fontsize=10.5, pad=8)

    # bottom: evidence-composition strip (fraction cleavable vs non-cleavable among grounded)
    for i, c in enumerate(comps):
        n = max(1, c["n_cleavable"] + c["n_non_cleavable"])
        fc = c["n_cleavable"] / n
        ax2.barh(i, fc, color="#3b7dd8", edgecolor="black", lw=0.5, label="favour cleavable" if i == 0 else None)
        ax2.barh(i, 1 - fc, left=fc, color="#e08a3c", edgecolor="black", lw=0.5, label="favour non-cleavable" if i == 0 else None)
        ax2.text(0.5, i, f"{c['n_cleavable']} cleavable / {c['n_non_cleavable']} non-cleavable"
                 + ("  (CONTESTED)" if c["contested"] else "  (unanimous)"),
                 ha="center", va="center", fontsize=7.5, color="white" if c["contested"] else "black", fontweight="bold")
    ax2.set_yticks(range(len(classes))); ax2.set_yticklabels([_SHORT[c] for c in classes], fontsize=8)
    ax2.set_xlim(0, 1); ax2.set_xlabel("fraction of grounded exemplars (held-out)")
    ax2.legend(fontsize=7.5, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 1.0))
    ax1.set_xticks(x); ax1.set_xticklabels([_SHORT[c] for c in classes], fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=200); plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
def fig3_rules_steer(designs, out: Path) -> Path:
    """Weight heatmap (class x term) + generated designs in (cleavability, flexibility) space."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    classes = ["cytotoxin", "immunomodulator", "oligonucleotide"]
    terms = ["solubility", "flexibility", "cleavability", "stability"]
    mat = np.array([[designs[c]["weights"].get(t, 0.0) for t in terms] for c in classes])

    fig, (axh, axs) = plt.subplots(1, 2, figsize=(9.6, 3.9), width_ratios=[1.0, 1.25])
    im = axh.imshow(mat, cmap="viridis", vmin=0, vmax=1, aspect="auto")
    axh.set_xticks(range(len(terms))); axh.set_xticklabels(terms, rotation=20, ha="right", fontsize=8)
    axh.set_yticks(range(len(classes))); axh.set_yticklabels([_SHORT[c] for c in classes], fontsize=8)
    for i in range(len(classes)):
        for j in range(len(terms)):
            axh.text(j, i, f"{mat[i,j]:.2f}", ha="center", va="center", fontsize=8,
                     color="white" if mat[i, j] < 0.55 else "black")
    axh.set_title("Compiled objective weights\n(differ by derived rule)", fontsize=9)
    fig.colorbar(im, ax=axh, shrink=0.8, label="weight")

    # Plot the two RAW, rule-driven properties (not the regime-normalised subscores,
    # which are ~1.0 for every design): rotatable-bond count (the rigidity knob) and
    # whether a cleavable motif is present (the cleavage knob).
    from rdkit import Chem
    from rdkit.Chem import Descriptors
    from hackathon_agents.tools.adc_shortlist import has_cleavable_motif
    rng = 0
    for c in classes:
        xs, ys = [], []
        for m in designs[c]["top"]:
            mol = Chem.MolFromSmiles(m.get("smiles", ""))
            if mol is None:
                continue
            xs.append(Descriptors.NumRotatableBonds(mol))
            # jitter the binary cleavable flag so overlapping points are visible
            rng = (rng * 1103515245 + 12345) & 0x7fffffff
            ys.append((1 if has_cleavable_motif(m["smiles"]) else 0) + ((rng % 100) / 100.0 - 0.5) * 0.22)
        axs.scatter(xs, ys, s=34, color=_COL[c], edgecolor="black", lw=0.4, alpha=0.8, label=_SHORT[c])
    axs.set_xlabel("rotatable bonds  (rigidity knob)")
    axs.set_yticks([0, 1]); axs.set_yticklabels(["non-\ncleavable", "cleavable"], fontsize=8)
    axs.set_ylim(-0.6, 1.6)
    axs.set_title("Generated designs separate by class\nalong the two rule knobs", fontsize=9)
    axs.legend(fontsize=7.5, loc="center right")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=200); plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
_KD_LABELS = {
    "cyto-Maleim": ("Val-Cit cytotoxin design", "#3b7dd8", "o"),
    "immu-Maleim": ("Val-Ala ISAC design", "#8a4fbf", "^"),
    "olig-DBCO": ("rigid non-cleavable ARC design", "#5aa469", "s"),
    "clinical": ("clinical Val-Cit substrate", "#d1495b", "*"),
    "arc-ValCit": ("cleavable Val-Cit ARC design\n(hypothesis)", "#e08a3c", "D"),
}


def _kd_label(raw: str):
    for k, v in _KD_LABELS.items():
        if k in raw:
            return v
    return (raw[:16], "#666", "o")


def fig4_cofold_kd(boltz, out: Path, hypothesis: dict | None = None) -> Path:
    """Cathepsin-B recognition: predicted Kd dot plot (log), humanised labels. Affinity != cleavage.

    If `hypothesis` (a co-fold record for the cleavable Val-Cit ARC design) is supplied, it is
    added — the in-silico feasibility point for the falsifiable ARC prediction.
    """
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [r for r in boltz if r.get("binding_affinity_kd_nm")]
    if hypothesis and hypothesis.get("binding_affinity_kd_nm"):
        rows = rows + [hypothesis]
    rows = sorted(rows, key=lambda r: r["binding_affinity_kd_nm"])
    fig, ax = plt.subplots(figsize=(8.0, 3.4))
    for i, r in enumerate(rows):
        name, col, mk = _kd_label(r.get("label", ""))
        ax.scatter(r["binding_affinity_kd_nm"], 0, s=190, marker=mk, color=col, edgecolor="black", lw=0.7, zorder=3)
        ax.annotate(f"{name}\n{r['binding_affinity_kd_nm']:.0f} nM",
                    (r["binding_affinity_kd_nm"], 0), fontsize=7.4, ha="center", fontweight="bold" if "hypothesis" in name else "normal",
                    xytext=(0, 20 if i % 2 == 0 else -34), textcoords="offset points",
                    arrowprops=dict(arrowstyle="-", lw=0.4, color="#999"))
    ax.set_xscale("log"); ax.set_yticks([]); ax.set_ylim(-0.9, 0.9)
    ax.set_xlabel("predicted $K_\\mathrm{d}$ vs cathepsin B (nM, log) $-$ tighter = better recognition, not cleavage", fontsize=9)
    ttl = "Cleavable Val-Cit designs are recognised like the clinical substrate; the rigid ARC design is not"
    if hypothesis:
        ttl += ".\nThe cleavable ARC design (derived from clinical AOC literature) is recognised too $-$ the hypothesis proof-point."
    ax.set_title(ttl, fontsize=8.8)
    ax.grid(axis="x", ls=":", alpha=0.5)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=200); plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
def fig5_sensitivity(sens, out: Path) -> Path:
    """Stress-test: confidence vs retrieval perturbation. Robust classes stay high; the
    contested ARC class stays low/contested across top-k and a drop-top-source jackknife."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    classes = ["cytotoxin", "immunomodulator", "oligonucleotide"]
    topk = [6, 8, 10, 12]
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    ax.axhspan(0.6, 1.02, color="#5aa469", alpha=0.08)
    ax.axhspan(-0.02, 0.4, color="#d1495b", alpha=0.08)
    ax.text(6.0, 0.93, "robust", color="#2e6b3e", fontsize=8, fontweight="bold")
    ax.text(6.0, 0.05, "contested / low", color="#7a1020", fontsize=8, fontweight="bold")
    for pc in classes:
        ys = [sens["topk"][pc][str(k)]["score"] for k in topk]
        lab = f"{_SHORT[pc]}  ({min(ys):.2f}--{max(ys):.2f})"
        ax.plot(topk, ys, "-o", color=_COL[pc], lw=2, ms=6, label=lab)
    ax.set_xlabel("retrieval depth (top-$k$ passages)"); ax.set_ylabel("disagreement-aware confidence $C$")
    ax.set_ylim(0, 1.05); ax.set_xlim(5.5, 12.5); ax.set_xticks(topk)
    ax.set_title("Confidence is stable across retrieval depth: the ARC rule stays contested ($\\approx$0.33)\n"
                 "at every $k$, cytotoxin medium, ISAC high $-$ the ordering is reproducible, not a lucky $k$", fontsize=9.3)
    ax.legend(fontsize=8, loc="center left", title="class (conf range over $k$)")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=200); plt.close(fig)
    return out


def fig1_journey(chains, designs, boltz, out: Path, out_struct: Path) -> Path:
    """Hero: one cytotoxin molecule threaded from real quote -> exemplar -> rule -> structure -> Kd."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    from hackathon_agents.tools.draw_linker_constructs import draw_construct

    import textwrap
    _CITE = {"biomedicines-11-03080": "Balamkundu 2023"}
    ch = chains["cytotoxin"]; rule = ch["rule"]
    grounded = [e for e in ch["exemplars"] if e.get("grounded")]
    ex = next((e for e in grounded if e.get("evidence")), grounded[0])
    quote = "\n".join(textwrap.wrap((ex.get("evidence") or "")[:90], 24))
    cite = _CITE.get(ex.get("source", ""), ex.get("source", "?")[:18])
    rule_txt = (f"{rule.get('cleavage_preference','?')},\n{rule.get('rigidity','?')}\n"
                r"$\rightarrow$ objective")
    smi = designs["cytotoxin"]["top"][0]["smiles"]
    kd = next((r["binding_affinity_kd_nm"] for r in boltz if "cyto" in r.get("label", "")), None)

    draw_construct(smi, str(out_struct), legend="generated Val-Cit design", size=(360, 300))

    fig, ax = plt.subplots(figsize=(10.2, 2.7)); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 1)
    stages = [
        ("REAL QUOTE", f'"{quote}..."\n[{cite}]', "#6a6a6a"),
        ("GROUNDED EXEMPLAR", f"{ex.get('payload','?')}\n{ex.get('linker','?')}\n(cited PDF)", "#3b7dd8"),
        ("DERIVED RULE", rule_txt, "#5aa469"),
        ("GENERATED", None, "#d18a3c"),  # structure image slot
        ("CO-FOLD", f"cathepsin B\n$K_d$ = {kd:.0f} nM\n(recognition)" if kd else "cathepsin B", "#d1495b"),
    ]
    bw, gap = 1.72, 0.26; x = 0.15; centers = []
    for label, body, color in stages:
        box = FancyBboxPatch((x, 0.1), bw, 0.8, boxstyle="round,pad=0.02,rounding_size=0.05",
                             lw=1.3, edgecolor=color, facecolor=color + "18")
        ax.add_patch(box)
        ax.text(x + bw / 2, 0.83, label, fontsize=7.5, fontweight="bold", ha="center", va="top", color=color)
        if body:
            ax.text(x + bw / 2, 0.46, body, fontsize=6.6, ha="center", va="center")
        else:
            im = plt.imread(str(out_struct))
            ax_im = fig.add_axes(_axes_frac(ax, x + 0.12, bw - 0.24))
            ax_im.imshow(im); ax_im.axis("off")
        centers.append(x + bw); x += bw + gap
    for i in range(len(stages) - 1):
        ax.add_patch(FancyArrowPatch((centers[i], 0.5), (centers[i] + gap, 0.5),
                                     arrowstyle="-|>", mutation_scale=11, lw=1.1, color="#444"))
    ax.set_title("One molecule, end to end: a retrieved quote grounds the rule that generates the linker that cathepsin B recognises",
                 fontsize=9.5)
    fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)
    return out


def _axes_frac(ax, x_data, w_data):
    """Convert data-x span on `ax` to a figure-fraction rect for an inset image axis."""
    fig = ax.figure
    p = ax.get_position()
    x0 = p.x0 + (x_data / 10.0) * p.width
    return [x0, p.y0 + 0.12 * p.height, (w_data / 10.0) * p.width, 0.62 * p.height]


# --------------------------------------------------------------------------- #
def render_study6_figures(src="deliverables/study5", out_dir="deliverables/study6/figures") -> dict[str, Path]:
    src = Path(src); out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    chains = json.loads((src / "reasoning_chains.json").read_text())
    heldout = json.loads((src / "heldout_predictions.json").read_text())
    designs = json.loads((src / "generated_designs.json").read_text())
    boltz = json.loads((src / "boltz.json").read_text())
    # the Val-Cit ARC hypothesis co-fold, if it has been run
    hyp_path = Path(out_dir).parent / "hypothesis_arc.json"
    hypothesis = None
    if hyp_path.exists():
        hyp = json.loads(hyp_path.read_text())
        hypothesis = hyp.get("cofold")
    figs = {
        "fig1": fig1_journey(chains, designs, boltz, out / "fig1_journey.png", out / "_struct_cyto.png"),
        "fig2": fig2_heldout_composition(chains, heldout, out / "fig2_heldout.png"),
        "fig3": fig3_rules_steer(designs, out / "fig3_rules_steer.png"),
        "fig4": fig4_cofold_kd(boltz, out / "fig4_cofold.png", hypothesis=hypothesis),
    }
    sens_path = Path(out_dir).parent / "sensitivity.json"
    if sens_path.exists():
        figs["fig5"] = fig5_sensitivity(json.loads(sens_path.read_text()), out / "fig5_sensitivity.png")
    return figs


if __name__ == "__main__":
    for k, v in render_study6_figures().items():
        print(k, "->", v, Path(v).stat().st_size, "bytes")
