"""Study 4 figures — make the reasoning visible + the held-out result.

* ``fig_reasoning_cascade`` — the auditable reasoning chain (CRITIQUE_S3 #1): for each
  payload class, query -> retrieved passages -> grounded exemplar -> derived rule ->
  compiled objective, with real content pulled from ``reasoning_chains.json``.
* ``fig_heldout`` — the central experiment (CRITIQUE_S3 #2/#3/#6): rule confidence with the
  full corpus vs with the class's key paper withheld. The oligonucleotide confidence
  collapses (0.80 -> ~0.01) when its sole ARC paper is removed even though the point
  prediction stays correct — calibrated uncertainty that knows what it doesn't know.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any


_CLASS_COLORS = {"cytotoxin": "#3b7dd8", "oligonucleotide": "#5aa469", "immunomodulator": "#d1495b"}
_CLASS_SHORT = {"cytotoxin": "Cytotoxin", "oligonucleotide": "Oligonucleotide (ARC)", "immunomodulator": "Immunomodulator (ISAC)"}


def _wrap(s: str, w: int) -> str:
    return "\n".join(textwrap.wrap(s or "", w)) or ""


def fig_reasoning_cascade(chains: dict[str, Any], out: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

    classes = [c for c in ("cytotoxin", "oligonucleotide", "immunomodulator") if c in chains]
    stages = ["Retrieved\nliterature", "Grounded\nexemplars", "Derived\nrule", "Compiled\nobjective"]
    nrows = len(classes)
    fig, axes = plt.subplots(nrows, 1, figsize=(9.2, 2.35 * nrows))
    if nrows == 1:
        axes = [axes]

    for ax, cls in zip(axes, classes):
        ch = chains[cls]
        rule = ch.get("rule") or {}
        conf = ch.get("confidence", {})
        exs = [e for e in ch.get("exemplars", []) if e.get("grounded")]
        top_ex = exs[0] if exs else (ch.get("exemplars") or [{}])[0]
        obj = ch.get("objective") or {}
        w = obj.get("weights", {})

        src_list = sorted({p['source'] for p in ch.get('passages', [])})
        src_txt = _wrap("sources: " + ", ".join(src_list), 24)
        texts = [
            f"{ch.get('n_passages', 0)} passages\n{src_txt}",
            f"{conf.get('n_grounded', 0)}/{conf.get('n_exemplars', 0)} grounded\n" +
            _wrap(f"e.g. {top_ex.get('linker','?')} / {top_ex.get('cleavage','?')}", 26),
            _wrap(f"cleave={rule.get('cleavage_preference','?')}; rigid={rule.get('rigidity','?')}; "
                  f"stab={rule.get('stability_priority','?')}", 26) +
            f"\nconf={conf.get('score',0):.2f} ({conf.get('label','?')})",
            _wrap(f"cleavability w={w.get('cleavability','?')}, flex w={w.get('flexibility','?')}, "
                  f"stab w={w.get('stability','?')}", 28),
        ]
        color = _CLASS_COLORS.get(cls, "#666")
        ax.set_xlim(0, 10); ax.set_ylim(0, 1); ax.axis("off")
        ax.text(-0.15, 0.5, _CLASS_SHORT.get(cls, cls), fontsize=10, fontweight="bold",
                rotation=90, va="center", ha="center", color=color, transform=ax.transAxes)
        box_w, gap = 2.0, 0.5
        x = 0.2
        centers = []
        for i, (label, body) in enumerate(zip(stages, texts)):
            box = FancyBboxPatch((x, 0.12), box_w, 0.76, boxstyle="round,pad=0.03,rounding_size=0.06",
                                 linewidth=1.2, edgecolor=color, facecolor=color + "22")
            ax.add_patch(box)
            ax.text(x + box_w / 2, 0.80, label, fontsize=8, fontweight="bold", ha="center", va="top", color=color)
            ax.text(x + box_w / 2, 0.52, body, fontsize=6.6, ha="center", va="center")
            centers.append(x + box_w)
            x += box_w + gap
        for i in range(len(stages) - 1):
            ar = FancyArrowPatch((centers[i], 0.5), (centers[i] + gap, 0.5),
                                 arrowstyle="-|>", mutation_scale=12, linewidth=1.1, color="#444")
            ax.add_patch(ar)

    fig.suptitle("Autonomous literature reasoning chain (per payload class): retrieval → grounded evidence → rule → objective",
                 fontsize=10, y=0.995)
    fig.tight_layout(rect=[0.03, 0, 1, 0.97])
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200); plt.close(fig)
    return out


def fig_heldout(heldout: dict[str, Any], chains: dict[str, Any], out: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    classes = [c for c in ("cytotoxin", "immunomodulator", "oligonucleotide") if c in heldout]
    full_conf = [chains.get(c, {}).get("confidence", {}).get("score", 0.0) for c in classes]
    held_conf = [heldout.get(c, {}).get("confidence", {}).get("score", 0.0) for c in classes]
    verdicts = [heldout.get(c, {}).get("score", {}).get("verdict", "?") for c in classes]
    withheld = [", ".join(heldout.get(c, {}).get("withheld", [])) for c in classes]

    x = np.arange(len(classes)); width = 0.38
    fig, ax = plt.subplots(figsize=(8.0, 4.3))
    b1 = ax.bar(x - width / 2, full_conf, width, label="full corpus", color="#3b7dd8", edgecolor="black", linewidth=0.5)
    b2 = ax.bar(x + width / 2, held_conf, width, label="key paper withheld", color="#d1495b", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{_CLASS_SHORT.get(c,c)}\n(withhold: {w})" for c, w in zip(classes, withheld)], fontsize=8)
    ax.set_ylabel("derived-rule confidence"); ax.set_ylim(0, 1.0)
    ax.set_title("Leave-one-paper-out: the point prediction stays correct, but confidence collapses\nwhen the class's sole evidence is withheld (the agent knows what it doesn't know)",
                 fontsize=9.5)
    # annotate verdicts (all should be AGREE) and the collapse
    for i, (fc, hc, v) in enumerate(zip(full_conf, held_conf, verdicts)):
        ax.text(x[i] + width / 2, hc + 0.02, f"{v.upper()}\nconf {hc:.2f}", ha="center", va="bottom", fontsize=7.5,
                color="#7a1020", fontweight="bold")
        ax.text(x[i] - width / 2, fc + 0.02, f"{fc:.2f}", ha="center", va="bottom", fontsize=7.5, color="#12386e")
    ax.legend(fontsize=8, loc="upper right")
    ax.axhline(0.45, ls=":", color="grey", lw=0.8)
    ax.text(len(classes) - 0.5, 0.46, "low-confidence threshold", ha="right", va="bottom", fontsize=6.5, color="grey")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200); plt.close(fig)
    return out


def fig_heldout_v5(heldout: dict[str, Any], chains: dict[str, Any], out: Path) -> Path:
    """V5 held-out: discriminate ROBUST rules (recover when a paper is withheld) from
    CONTESTED ones (the rule flips because the broader literature genuinely disagrees)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    def _dir(pref):  # canonical cleavage -> readable direction
        return {"reward": "cleavable", "penalize": "non-cleavable", "ignore": "either"}.get(pref, pref or "?")

    def _rule_dir(rule):
        from hackathon_agents.tools.lit_reasoning_s4 import normalize_rule
        return _dir(normalize_rule(rule)["cleavage_preference"]) if rule else "?"

    classes = [c for c in ("cytotoxin", "immunomodulator", "oligonucleotide") if c in heldout]
    full_conf = [chains.get(c, {}).get("confidence", {}).get("score", 0.0) for c in classes]
    held_conf = [heldout.get(c, {}).get("confidence", {}).get("score", 0.0) for c in classes]
    full_dir = [_rule_dir(chains.get(c, {}).get("rule")) for c in classes]
    held_dir = [_dir(heldout.get(c, {}).get("score", {}).get("predicted_cleavage")) for c in classes]
    verdicts = [heldout.get(c, {}).get("score", {}).get("verdict", "?") for c in classes]
    withheld = [", ".join(heldout.get(c, {}).get("withheld", []))[:34] for c in classes]

    x = np.arange(len(classes)); width = 0.38
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    ax.bar(x - width / 2, full_conf, width, label="full corpus", color="#3b7dd8", edgecolor="black", linewidth=0.5)
    held_colors = ["#5aa469" if v == "agree" else "#d1495b" for v in verdicts]
    ax.bar(x + width / 2, held_conf, width, label="key paper(s) withheld", color=held_colors, edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{_CLASS_SHORT.get(c,c)}\n(withhold: {w})" for c, w in zip(classes, withheld)], fontsize=8)
    ax.set_ylabel("derived-rule confidence"); ax.set_ylim(0, 1.05)
    ax.set_title("Held-out test discriminates ROBUST rules (recover when a paper is withheld)\n"
                 "from CONTESTED ones (rule flips because the broader literature disagrees)", fontsize=9.5)
    for i in range(len(classes)):
        ax.text(x[i] - width / 2, full_conf[i] + 0.015, f"{full_dir[i]}\n{full_conf[i]:.2f}",
                ha="center", va="bottom", fontsize=7, color="#12386e")
        col = "#2e6b3e" if verdicts[i] == "agree" else "#7a1020"
        tag = "ROBUST" if verdicts[i] == "agree" else "CONTESTED"
        ax.text(x[i] + width / 2, held_conf[i] + 0.015, f"{held_dir[i]}\n{held_conf[i]:.2f}\n{tag}",
                ha="center", va="bottom", fontsize=7, color=col, fontweight="bold")
    ax.legend(fontsize=8, loc="upper center", ncol=2)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200); plt.close(fig)
    return out


def render_study5_figures(
    reasoning_path: str | Path = "deliverables/study5/reasoning_chains.json",
    heldout_path: str | Path = "deliverables/study5/heldout_predictions.json",
    out_dir: str | Path = "deliverables/study5/figures",
) -> dict[str, Path]:
    chains = json.loads(Path(reasoning_path).read_text())
    heldout = json.loads(Path(heldout_path).read_text())
    out = Path(out_dir)
    return {
        "reasoning": fig_reasoning_cascade(chains, out / "fig_reasoning_cascade.png"),
        "heldout": fig_heldout_v5(heldout, chains, out / "fig_heldout.png"),
    }


def render_study4_figures(
    reasoning_path: str | Path = "deliverables/study4/reasoning_chains.json",
    heldout_path: str | Path = "deliverables/study4/heldout_predictions.json",
    out_dir: str | Path = "deliverables/study4/figures",
) -> dict[str, Path]:
    chains = json.loads(Path(reasoning_path).read_text())
    heldout_raw = json.loads(Path(heldout_path).read_text())
    out = Path(out_dir)
    figs = {
        "reasoning": fig_reasoning_cascade(chains, out / "fig_reasoning_cascade.png"),
        "heldout": fig_heldout(heldout_raw, chains, out / "fig_heldout.png"),
    }
    return figs


if __name__ == "__main__":
    figs = render_study4_figures()
    for k, v in figs.items():
        print(k, "->", v, Path(v).stat().st_size, "bytes")
