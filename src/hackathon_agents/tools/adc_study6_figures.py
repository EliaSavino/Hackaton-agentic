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

# Semantic palette sampled from the *plasma* colormap (the paper's general colour map):
#   cleavable = purple, rigid/non-cleavable = orange, robust/recovers = indigo,
#   contested/flips = amber, clinical/neutral = grey. Heatmaps use cmap="plasma".
PAL_CLEAVABLE = "#8f0da4"   # plasma 0.30 (purple)
PAL_RIGID = "#fb9f3a"       # plasma 0.78 (orange)
PAL_CONTESTED = "#feba2c"   # plasma 0.85 (amber)
PAL_ROBUST = "#5601a4"      # plasma 0.15 (indigo)
PAL_SLATE = "#7a7a7a"       # neutral grey (clinical reference / full-corpus baseline)
# Per-target (class) colours, spread across plasma so the three targets are distinguishable.
_COL = {"cytotoxin": "#5601a4", "immunomodulator": "#cc4778", "oligonucleotide": "#fdae32"}
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

    # Side-by-side (left confidence / right evidence split) -- less wide and much shorter than
    # the old stacked layout, so it costs little vertical space. Plasma-derived colours.
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.2, 3.5), width_ratios=[1.28, 1.0])
    x = np.arange(len(classes)); w = 0.36

    # LEFT: confidence bars. Full-corpus muted grey; held-out coloured by outcome (indigo recover
    # / amber flip); a dotted 0.5 "contested floor" anchors the ARC flip below it.
    ax1.axhline(0.5, ls=":", lw=0.9, color="#c0c0c0", zorder=0)
    ax1.bar(x - w / 2, full_conf, w, label="full-corpus", color="#bcbcbc", edgecolor="black", lw=0.5)
    hc = [PAL_ROBUST if v == "agree" else PAL_CONTESTED for v in verdict]
    ax1.bar(x + w / 2, held_conf, w, label="held-out", color=hc, edgecolor="black", lw=0.5)
    ax1.set_ylabel("derived-rule confidence\n(disagreement-aware)", fontsize=8.5)
    ax1.set_ylim(0, 1.18); ax1.set_xlim(-0.7, 2.7)
    for i in range(len(classes)):
        ax1.text(x[i] - w / 2, full_conf[i] + 0.02, f"{full_dir[i]}\n{full_conf[i]:.2f}",
                 ha="center", va="bottom", fontsize=6.4, color="#666")
        flip = full_dir[i] != held_dir[i]
        col = "#9a6b00" if verdict[i] != "agree" else "#3d0a75"
        ax1.text(x[i] + w / 2, held_conf[i] + 0.02,
                 f"{held_dir[i]}\n{held_conf[i]:.2f}\n{'FLIPS' if flip else 'recovers'}",
                 ha="center", va="bottom", fontsize=6.4, color=col, fontweight="bold")
    ax1.set_xticks(x); ax1.set_xticklabels([_SHORT[c] for c in classes], fontsize=6.8, rotation=10, ha="right")
    ax1.legend(fontsize=7, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.12), frameon=True)

    # RIGHT: evidence-composition strip (cleavable purple vs non-cleavable orange among grounded)
    for i, c in enumerate(comps):
        n = max(1, c["n_cleavable"] + c["n_non_cleavable"])
        fc = c["n_cleavable"] / n
        ax2.barh(i, fc, color=PAL_CLEAVABLE, edgecolor="black", lw=0.5, label="cleavable" if i == 0 else None)
        ax2.barh(i, 1 - fc, left=fc, color=PAL_RIGID, edgecolor="black", lw=0.5, label="non-cleavable" if i == 0 else None)
        ax2.text(0.5, i, f"{c['n_cleavable']}/{c['n_non_cleavable']}"
                 + ("  contested" if c["contested"] else "  unanim."),
                 ha="center", va="center", fontsize=6.8, color="white" if c["contested"] else "black", fontweight="bold")
    ax2.set_yticks(range(len(classes))); ax2.set_yticklabels([_SHORT[c] for c in classes], fontsize=6.8)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 1); ax2.set_xlabel("grounded exemplars\n(cleavable vs non-cleavable)", fontsize=8.5)
    ax2.legend(fontsize=7, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.12))
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=200); plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
def fig3_rules_steer(designs, out: Path, tmp_dir: Path | None = None, per_class: int = 2) -> Path:
    """Three panels: score, values, molecules -- the whole steer-the-chemistry story in one.

    (a) the compiled objective weights heatmap (plasma; a deterministic rule-compilation);
    (b) the generated designs in rotatable-bond x SA space -- colour encodes the *target*
        (cyto/ISAC/ARC), shape encodes whether the linker is *cleavable* (o) or not (X);
    (c) the actual generated molecules (real REINVENT designs) with their scores, drawn with
        SMARTS-detected handle/scissile/spacer highlights (this absorbs the old gallery)."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    import numpy as np
    from matplotlib.lines import Line2D
    from hackathon_agents.tools.draw_linker_constructs import draw_construct

    classes = ["cytotoxin", "immunomodulator", "oligonucleotide"]
    terms = ["solubility", "flexibility", "cleavability", "stability"]
    term_labels = ["solubility", "rigidity\n(low-rot reward)", "cleavability", "stability"]
    mat = np.array([[designs[c]["weights"].get(t, 0.0) for t in terms] for c in classes])
    mrb = {c: designs[c].get("max_rot_bonds") for c in classes}
    def _cleavable(c):
        return "non-clea" not in str(designs[c].get("trigger", "")).lower()

    tmp_dir = tmp_dir or (out.parent / "_fig3_tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(9.6, 4.7))
    # Explicit margins (no tight_layout -- it can't reconcile the colorbar + image subgrid).
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.02], hspace=0.5, wspace=0.24,
                          left=0.075, right=0.97, top=0.9, bottom=0.03)
    axh = fig.add_subplot(gs[0, 0])
    axs = fig.add_subplot(gs[0, 1])
    gs_m = gs[1, :].subgridspec(per_class, len(classes), hspace=0.12, wspace=0.06)

    # (a) weight heatmap -- plasma; legible labels (dark cells -> white text).
    im = axh.imshow(mat, cmap="plasma", vmin=0, vmax=1, aspect="auto")
    axh.set_xticks(range(len(terms))); axh.set_xticklabels(term_labels, rotation=20, ha="right", fontsize=7.4)
    axh.set_yticks(range(len(classes)))
    axh.set_yticklabels([f"{_SHORT[c]}\n(rot$\\leq${mrb[c]})" for c in classes], fontsize=7.4)
    for i in range(len(classes)):
        for j in range(len(terms)):
            axh.text(j, i, f"{mat[i,j]:.2f}", ha="center", va="center", fontsize=7.6,
                     color="white" if mat[i, j] < 0.55 else "black")
    axh.set_title("(a) Compiled objective weights\n(deterministic rule-compilation, heuristic)", fontsize=8.4)
    fig.colorbar(im, ax=axh, shrink=0.82, label="weight (3 buckets)")

    # (b) scatter: x = rotatable bonds (rigidity setpoint), y = per-molecule Ertl SA subscore.
    # Colour = target class; shape = cleavable (o) vs non-cleavable (X).
    from rdkit import Chem
    from rdkit.Chem import Descriptors
    for c in classes:
        mk = "o" if _cleavable(c) else "X"
        xs, ys = [], []
        for m in designs[c]["top"]:
            mol = Chem.MolFromSmiles(m.get("smiles", ""))
            if mol is None:
                continue
            xs.append(Descriptors.NumRotatableBonds(mol))
            ys.append((m.get("subscores") or {}).get("synthesizability", 0.0))
        axs.scatter(xs, ys, s=44, color=_COL[c], marker=mk, edgecolor="black", lw=0.4, alpha=0.9)
    axs.set_xlabel("rotatable bonds  (rigidity setpoint)", fontsize=8)
    axs.set_ylabel("Ertl SA subscore", fontsize=8)
    axs.set_ylim(0, 1.05)
    axs.set_title("(b) Generated designs: colour = target,\nshape = cleavable ($\\circ$) vs non-cleavable ($\\times$)", fontsize=8.4)
    col_handles = [Line2D([0], [0], marker="s", ls="", mfc=_COL[c], mec="black", ms=6.5, label=_SHORT[c]) for c in classes]
    leg1 = axs.legend(handles=col_handles, fontsize=6.4, loc="lower left", title="target",
                      title_fontsize=6.6, framealpha=0.9, handletextpad=0.2, borderpad=0.3)
    axs.add_artist(leg1)
    shp_handles = [Line2D([0], [0], marker="o", ls="", mfc="#bdbdbd", mec="black", ms=6.5, label="cleavable"),
                   Line2D([0], [0], marker="X", ls="", mfc="#bdbdbd", mec="black", ms=6.5, label="non-cleavable")]
    axs.legend(handles=shp_handles, fontsize=6.4, loc="lower right", title="linker",
               title_fontsize=6.6, framealpha=0.9, handletextpad=0.2, borderpad=0.3)

    # (c) real generated molecules with their scores (absorbs the gallery).
    for col, c in enumerate(classes):
        top = designs[c].get("top", [])
        for row in range(per_class):
            ax = fig.add_subplot(gs_m[row, col]); ax.axis("off")
            if row == 0:
                ax.set_title(_SHORT[c], fontsize=7.6, color=_COL[c], fontweight="bold", pad=1)
            if row >= len(top):
                continue
            m = top[row]; smi = m.get("smiles", "")
            png = tmp_dir / f"_f3_{c}_{row}.png"
            if draw_construct(smi, png, legend="", size=(440, 250)) is not None:
                ax.imshow(mpimg.imread(str(png)))
            sc = m.get("score")
            ax.text(0.5, -0.02, (f"score {sc:.2f}  " if sc is not None else "") + f"motif {designs[c].get('trigger','?')}",
                    transform=ax.transAxes, ha="center", va="top", fontsize=6.0, color="#555")
    out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=200); plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# Colour = cleavage class (cleavable designs teal, rigid ARC amber, clinical substrate slate);
# marker shape alone carries the payload class. So the cleavables cluster in one colour tight to
# the left and the lone rigid design sits amber far to the right.
_KD_LABELS = {
    "cyto-Maleim": ("Val-Cit cytotoxin design", PAL_CLEAVABLE, "o"),
    "immu-Maleim": ("Val-Ala ISAC design", PAL_CLEAVABLE, "^"),
    "olig-DBCO": ("rigid non-cleavable ARC design", PAL_RIGID, "s"),
    "clinical": ("clinical Val-Cit substrate", PAL_SLATE, "*"),
    "arc-ValCit": ("cleavable Val-Cit ARC design\n(hypothesis)", PAL_CLEAVABLE, "D"),
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
    # A short 1-D strip (all markers share one y): compact height, labels alternated above /
    # below so the two tight-left cleavables (cytotoxin, hypothesis) don't collide. The marker
    # row sits above centre so the multi-line down-labels have room and clear the x-axis ticks.
    # In-plot title dropped -- the LaTeX caption carries it.
    fig, ax = plt.subplots(figsize=(8.4, 2.8))
    for i, r in enumerate(rows):
        name, col, mk = _kd_label(r.get("label", ""))
        ax.scatter(r["binding_affinity_kd_nm"], 0, s=200, marker=mk, color=col, edgecolor="black", lw=0.7, zorder=3)
        up = i % 2 == 0
        ax.annotate(f"{name}\n{r['binding_affinity_kd_nm']:.0f} nM",
                    (r["binding_affinity_kd_nm"], 0), fontsize=7.2, ha="center",
                    fontweight="bold" if "hypothesis" in name else "normal",
                    xytext=(0, 30 if up else -34), textcoords="offset points",
                    va="bottom" if up else "top",
                    arrowprops=dict(arrowstyle="-", lw=0.4, color="#999"))
    ax.set_xscale("log"); ax.set_yticks([]); ax.set_ylim(-1.5, 1.0)
    ax.set_xlabel("predicted $K_\\mathrm{d}$ vs cathepsin B (nM, log) $-$ tighter = better recognition, not cleavage", fontsize=9)
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
    # Palette-aligned robust/contested bands; in-plot title dropped (the LaTeX caption is the
    # single voice) and the height trimmed to help the main text hold five pages.
    fig, ax = plt.subplots(figsize=(7.4, 2.7))
    ax.axhspan(0.6, 1.02, color=PAL_ROBUST, alpha=0.10)
    ax.axhspan(-0.02, 0.4, color=PAL_CONTESTED, alpha=0.12)
    ax.text(6.0, 0.93, "robust", color="#3d0a75", fontsize=8, fontweight="bold")
    ax.text(6.0, 0.05, "contested / low", color="#9a6b00", fontsize=8, fontweight="bold")
    for pc in classes:
        ys = [sens["topk"][pc][str(k)]["score"] for k in topk]
        lab = f"{_SHORT[pc]}  ({min(ys):.2f}--{max(ys):.2f})"
        ax.plot(topk, ys, "-o", color=_COL[pc], lw=2, ms=6, label=lab)
    ax.set_xlabel("retrieval depth (top-$k$ passages)"); ax.set_ylabel("disagreement-aware confidence $C$")
    ax.set_ylim(0, 1.05); ax.set_xlim(5.5, 12.5); ax.set_xticks(topk)
    ax.legend(fontsize=7.6, loc="center left", title="class (conf range over $k$)")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=200); plt.close(fig)
    return out


def fig6_designs_gallery(designs, out: Path, tmp_dir: Path, per_class: int = 2) -> Path:
    """Gallery of the actual generated (trial) linkers, `per_class` per payload class.

    Each is a real REINVENT design carrying its derived motif (Val-Cit / Val-Ala / rigid cap),
    drawn with SMARTS-detected handle (blue) / scissile (red) / spacer (green) highlights."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    from hackathon_agents.tools.draw_linker_constructs import draw_construct

    classes = ["cytotoxin", "immunomodulator", "oligonucleotide"]
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(classes), per_class, figsize=(3.3 * per_class, 1.95 * len(classes)))
    if per_class == 1:
        axes = [[a] for a in axes]
    for r, c in enumerate(classes):
        top = designs[c].get("top", [])
        trig = designs[c].get("trigger", "?")
        for k in range(per_class):
            ax = axes[r][k]; ax.axis("off")
            if k >= len(top):
                continue
            m = top[k]; smi = m["smiles"]
            png = tmp_dir / f"_gal_{c}_{k}.png"
            res = draw_construct(smi, png, legend="", size=(420, 300))
            if res is not None:
                ax.imshow(mpimg.imread(str(png)))
            sc = m.get("score")
            ax.set_title(f"{_SHORT[c]} #{k+1}" + (f"  (score {sc:.2f})" if sc is not None else ""),
                         fontsize=8.2, color=_COL[c], fontweight="bold")
            ax.text(0.5, -0.06, f"welded motif: {trig}", transform=ax.transAxes,
                    ha="center", va="top", fontsize=6.8, color="#555")
    # No in-plot suptitle -- the SI LaTeX caption is the single voice (the em-dash lives there).
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

    draw_construct(smi, str(out_struct), legend="", size=(360, 300))

    fig, ax = plt.subplots(figsize=(10.2, 2.7)); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 1)
    # One neutral slate border on every box; a teal accent only on the two stages the agent
    # actually produces -- the DERIVED RULE and the GENERATED molecule (critiques XI.3).
    stages = [
        ("REAL QUOTE", f'"{quote}..."\n[{cite}]', PAL_SLATE),
        ("GROUNDED EXEMPLAR", f"{ex.get('payload','?')}\n{ex.get('linker','?')}\n(cited PDF)", PAL_SLATE),
        ("DERIVED RULE", rule_txt, PAL_CLEAVABLE),
        ("GENERATED", None, PAL_CLEAVABLE),  # structure image slot
        ("CO-FOLD", f"cathepsin B\n$K_d$ = {kd:.0f} nM\n(recognition)" if kd else "cathepsin B", PAL_SLATE),
    ]
    bw, gap = 1.72, 0.26; x = 0.15; centers = []; gen_cx = None
    for label, body, color in stages:
        box = FancyBboxPatch((x, 0.1), bw, 0.8, boxstyle="round,pad=0.02,rounding_size=0.05",
                             lw=1.3, edgecolor=color, facecolor=color + "18")
        ax.add_patch(box)
        ax.text(x + bw / 2, 0.83, label, fontsize=7.5, fontweight="bold", ha="center", va="top", color=color)
        if body:
            ax.text(x + bw / 2, 0.46, body, fontsize=6.6, ha="center", va="center")
        else:
            gen_cx = x + bw / 2
            im = plt.imread(str(out_struct))
            ax_im = fig.add_axes(_axes_frac(ax, x + 0.12, bw - 0.24))
            ax_im.imshow(im); ax_im.axis("off")
        centers.append(x + bw); x += bw + gap
    if gen_cx is not None:
        ax.text(gen_cx, 0.055, "generated Val-Cit design", fontsize=6.4, style="italic",
                ha="center", va="center", color="#333")
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
        # Fig 3 now carries score (weights) + values (scatter) + molecules (gallery panel).
        "fig3": fig3_rules_steer(designs, out / "fig3_rules_steer.png", out / "_fig3_tmp"),
        "fig4": fig4_cofold_kd(boltz, out / "fig4_cofold.png", hypothesis=hypothesis),
    }
    sens_path = Path(out_dir).parent / "sensitivity.json"
    if sens_path.exists():
        figs["fig5"] = fig5_sensitivity(json.loads(sens_path.read_text()), out / "fig5_sensitivity.png")
    return figs


if __name__ == "__main__":
    for k, v in render_study6_figures().items():
        print(k, "->", v, Path(v).stat().st_size, "bytes")
