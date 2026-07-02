"""Analysis + publication figures for the ADC design-grid + benchmark study.

Consumes the grid sweep (``adc_grid.run_grid`` output), the commercial benchmark
(``linker_benchmark``), and optional Boltz structural results, and produces the
statistics and matplotlib figures used by ``adc_study_paper``.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- #
# Grid statistics
# --------------------------------------------------------------------------- #
def grid_stats(grid: dict[str, Any]) -> dict[str, Any]:
    """Per-context best/mean/std across seeds, pooled ranking, seed variance.

    A context is keyed by (handle, trigger, payload) so the payload-class sweep's
    ranking flips are visible; ``payload`` defaults to ``cytotoxin`` for legacy
    grids that predate the payload dimension.
    """
    by_ctx: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    pooled: list[dict[str, Any]] = []
    real = mock = 0
    for rec in grid.get("records", []):
        payload = rec.get("payload", "cytotoxin")
        if rec.get("ok") and not rec.get("mock"):
            real += 1
        else:
            mock += 1
        if rec.get("best_score") is not None:
            by_ctx[(rec["handle"], rec["trigger"], payload)].append(rec["best_score"])
        for cand in rec.get("top", []):
            pooled.append({**cand, "handle": rec["handle"], "trigger": rec["trigger"],
                           "payload": payload, "seed": rec.get("seed")})
    contexts = []
    for (handle, trigger, payload), scores in by_ctx.items():
        contexts.append({
            "handle": handle,
            "trigger": trigger,
            "payload": payload,
            "best": max(scores),
            "mean": round(statistics.mean(scores), 4),
            "std": round(statistics.pstdev(scores), 4) if len(scores) > 1 else 0.0,
            "n_seeds": len(scores),
        })
    contexts.sort(key=lambda c: c["best"], reverse=True)
    # dedupe pooled by SMILES keeping best score
    seen: dict[str, dict[str, Any]] = {}
    for c in pooled:
        s = c.get("smiles")
        if s and (s not in seen or (c.get("score") or 0) > (seen[s].get("score") or 0)):
            seen[s] = c
    pooled_unique = sorted(seen.values(), key=lambda c: c.get("score") or 0, reverse=True)
    return {"contexts": contexts, "pooled": pooled_unique, "n_real": real, "n_mock": mock}


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def render_figures(
    grid: dict[str, Any],
    stats: dict[str, Any],
    benchmark: dict[str, Any] | None,
    boltz: list[dict[str, Any]] | None,
    figdir: Path,
) -> dict[str, Path]:
    figdir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception:
        return out

    handles = grid.get("handles", [])
    triggers = grid.get("triggers", [])
    ctx_lookup = {(c["handle"], c["trigger"], c.get("payload", "cytotoxin")): c for c in stats["contexts"]}

    # Fig 1 — conjugation-chemistry heatmap: mean best-score per (handle x trigger),
    # for the cytotoxin conjugation sweep (Block 1). Only handles/triggers present
    # under the cytotoxin payload are shown.
    try:
        h_present = [h for h in handles if any((h, t, "cytotoxin") in ctx_lookup for t in triggers)]
        t_present = [t for t in triggers if any((h, t, "cytotoxin") in ctx_lookup for h in h_present)]
        mat = np.full((len(h_present), len(t_present)), np.nan)
        for i, h in enumerate(h_present):
            for j, t in enumerate(t_present):
                c = ctx_lookup.get((h, t, "cytotoxin"))
                if c:
                    mat[i, j] = c["mean"]
        fig, ax = plt.subplots(figsize=(6.8, 4.2))
        im = ax.imshow(mat, aspect="auto", cmap="viridis", vmin=0, vmax=max(0.3, np.nanmax(mat)))
        ax.set_xticks(range(len(t_present))); ax.set_xticklabels(t_present, rotation=20, ha="right", fontsize=9)
        ax.set_yticks(range(len(h_present))); ax.set_yticklabels(h_present, fontsize=9)
        for i in range(len(h_present)):
            for j in range(len(t_present)):
                if not np.isnan(mat[i, j]):
                    ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center",
                            color="white" if mat[i, j] < 0.4 else "black", fontsize=8)
        ax.set_title("Cytotoxin sweep: mean composite (conjugation x trigger)")
        fig.colorbar(im, ax=ax, shrink=0.85, label="mean best composite")
        fig.tight_layout(); p = figdir / "fig_grid_heatmap.png"; fig.savefig(p, dpi=200); plt.close(fig)
        out["heatmap"] = p
    except Exception:
        pass

    # Fig 1b — payload-class ranking flip: for the shared Block-2 trigger panel,
    # mean composite grouped by payload class. The optimum moves from cleavable
    # (cytotoxin) to non-cleavable-rigid (oligonucleotide).
    try:
        payloads = [p for p in grid.get("payloads", []) if p != "cytotoxin"] or []
        payloads = ["cytotoxin"] + [p for p in grid.get("payloads", []) if p != "cytotoxin"]
        payloads = [p for p in payloads if any(c.get("payload") == p for c in stats["contexts"])]
        # Trigger panel = triggers that appear under a non-cytotoxin payload.
        panel_triggers = list(dict.fromkeys(
            c["trigger"] for c in stats["contexts"] if c.get("payload") in payloads and c.get("payload") != "cytotoxin"
        ))
        # Representative handle for the flip figure (first Block-2 handle present).
        flip_handle = next((h for h in handles if any(
            (h, t, p) in ctx_lookup for t in panel_triggers for p in payloads)), None)
        if len(payloads) >= 2 and panel_triggers and flip_handle:
            colors = {"cytotoxin": "#3b7dd8", "oligonucleotide": "#5aa469", "immunomodulator": "#d1495b"}
            x = np.arange(len(panel_triggers)); width = 0.8 / max(1, len(payloads))
            fig, ax = plt.subplots(figsize=(7.0, 3.9))
            for k, p in enumerate(payloads):
                vals = [ (ctx_lookup.get((flip_handle, t, p)) or {}).get("mean", np.nan) for t in panel_triggers ]
                ax.bar(x + k * width, vals, width, label=p, color=colors.get(p, None), edgecolor="black", linewidth=0.4)
            ax.set_xticks(x + width * (len(payloads) - 1) / 2)
            ax.set_xticklabels(panel_triggers, rotation=12, ha="right", fontsize=8)
            ax.set_ylabel("mean composite"); ax.set_ylim(0, 1.0)
            ax.set_title(f"Payload-class ranking flip ({flip_handle} handle)")
            ax.legend(fontsize=8, title="payload", loc="upper right")
            fig.tight_layout(); p_ = figdir / "fig_payload_flip.png"; fig.savefig(p_, dpi=200); plt.close(fig)
            out["payload_flip"] = p_
    except Exception:
        pass

    # Fig 2 — per-context best with seed error bars (top 12 contexts).
    try:
        top = stats["contexts"][:12]
        def _clab(c):
            tag = "" if c.get("payload", "cytotoxin") == "cytotoxin" else f"[{c['payload'][:4]}]"
            return f"{c['handle'][:7]}/{c['trigger'][:6]}{tag}"
        labels = [_clab(c) for c in top]
        means = [c["mean"] for c in top]; errs = [c["std"] for c in top]
        fig, ax = plt.subplots(figsize=(7.0, 3.8))
        x = range(len(top))
        ax.bar(x, means, yerr=errs, capsize=3, color="#3b7dd8", edgecolor="black", linewidth=0.5)
        ax.set_xticks(list(x)); ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
        ax.set_ylabel("composite (mean ± SD over seeds)"); ax.set_ylim(0, 1.0)
        ax.set_title("Per-context optimisation (seed-averaged)")
        fig.tight_layout(); p = figdir / "fig_context_bars.png"; fig.savefig(p, dpi=200); plt.close(fig)
        out["context_bars"] = p
    except Exception:
        pass

    # Fig 3 — Pareto: composite vs synthesizability, designed vs commercial.
    try:
        fig, ax = plt.subplots(figsize=(6.4, 4.0))
        dx = [c["score"] for c in stats["pooled"] if c.get("score") is not None and c.get("subscores")]
        dy = [c["subscores"].get("synthesizability", 0) for c in stats["pooled"] if c.get("score") is not None and c.get("subscores")]
        ax.scatter(dx, dy, s=22, alpha=0.5, color="#3b7dd8", label="designed", edgecolor="none")
        if benchmark:
            cx = [r["score"] for r in benchmark.get("commercial", []) if r.get("score") is not None]
            cy = [r["subscores"].get("synthesizability", 0) for r in benchmark.get("commercial", []) if r.get("score") is not None]
            ax.scatter(cx, cy, s=90, marker="*", color="#d1495b", edgecolor="black", linewidth=0.5, label="commercial", zorder=5)
        ax.set_xlabel("composite ADC score (optimised objective)")
        ax.set_ylabel("synthesizability subscore")
        ax.set_title("Designed vs commercial: score / synthesizability trade-off")
        ax.legend(fontsize=8, loc="lower left")
        fig.tight_layout(); p = figdir / "fig_pareto.png"; fig.savefig(p, dpi=200); plt.close(fig)
        out["pareto"] = p
    except Exception:
        pass

    # Fig 4 — novelty histogram (designed nearest-neighbour Tanimoto to commercial).
    try:
        if benchmark and benchmark.get("designed"):
            nn = [d["novelty_nn_tanimoto"] for d in benchmark["designed"] if d.get("novelty_nn_tanimoto") is not None]
            if nn:
                fig, ax = plt.subplots(figsize=(5.8, 3.4))
                ax.hist(nn, bins=12, range=(0, 1), color="#5aa469", edgecolor="black", linewidth=0.5)
                ax.axvline(0.4, ls="--", color="grey", lw=1)
                ax.set_xlabel("max Tanimoto to any commercial linker")
                ax.set_ylabel("designed linkers")
                ax.set_title("Chemical novelty of designed linkers")
                fig.tight_layout(); p = figdir / "fig_novelty.png"; fig.savefig(p, dpi=200); plt.close(fig)
                out["novelty"] = p
    except Exception:
        pass

    # Fig 5 — Boltz: cathepsin-B interface confidence (ipTM) vs predicted affinity.
    try:
        if boltz:
            rows = [b for b in boltz if b.get("iptm") is not None and b.get("binding_affinity_kd_nm")]
            if rows:
                fig, ax = plt.subplots(figsize=(6.2, 4.0))
                _style = {
                    "commercial": ("*", "#d1495b", 90, 5),
                    "negative": ("s", "#8d8d8d", 60, 4),
                    "designed": ("o", "#3b7dd8", 55, 3),
                }
                for b in rows:
                    marker, color, size, z = _style.get(b.get("kind"), _style["designed"])
                    ax.scatter(b["binding_affinity_kd_nm"], b["iptm"], s=size, marker=marker,
                               color=color, edgecolor="black", linewidth=0.5, zorder=z)
                    ax.annotate(b.get("label", "")[:14], (b["binding_affinity_kd_nm"], b["iptm"]),
                                fontsize=6, xytext=(3, 3), textcoords="offset points")
                ax.set_xscale("log")
                ax.set_xlabel("predicted Kd vs cathepsin B (nM, log)")
                ax.set_ylabel("interface ipTM")
                ax.set_title("Boltz-2 co-folding: predicted affinity separates substrates")
                fig.tight_layout(); p = figdir / "fig_boltz.png"; fig.savefig(p, dpi=200); plt.close(fig)
                out["boltz"] = p
    except Exception:
        pass

    return out
