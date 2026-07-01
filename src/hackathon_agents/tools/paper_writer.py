"""Publication-style LaTeX paper writer for the ADC linker-design workflow.

Where ``latex_writer`` emits a short generic run report, this produces a
~5-page, publication-shaped paper: Abstract, Introduction/Background (grounded in
the ADC problem statement and the reference linker corpus), Methods (agent
architecture + REINVENT LinkInvent setup + the scoring function derived from the
goal profile), Results (top-linker table with fragment/ADC subscores, a score
figure, and the autonomous decision trail), Discussion, Conclusion, and
References.

Reuses ``latex_writer._latex_escape`` and the shared ``validate_latex_output``
guard so output stays compile-safe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hackathon_agents.llm.validators import validate_latex_output
from hackathon_agents.schemas.linkers import ADC_GOAL_KEYS
from hackathon_agents.tools.base import error_result, ok_result
from hackathon_agents.tools.latex_writer import _format_value, _latex_escape


class AdcPaperInput(BaseModel):
    output_path: str
    title: str = "Autonomous Agentic Design of Next-Generation Antibody-Drug Conjugate Linkers"
    user_request: str
    goal_profile: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    decision_trail: list[dict[str, Any]] = Field(default_factory=list)
    reference_corpus_path: str | None = None
    warhead_pair: str | None = None
    max_candidates: int = 15


def write_adc_paper(input_data: AdcPaperInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, AdcPaperInput) else AdcPaperInput.model_validate(input_data)
    try:
        output = Path(parsed.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        figure_path = _maybe_render_score_figure(parsed, output.parent)
        references = _load_references(parsed.reference_corpus_path)

        rendered = _render_paper(parsed, figure_path=figure_path, references=references)
        validation = validate_latex_output(rendered)
        if not validation.ok:
            return error_result(
                "LaTeX validation failed: " + "; ".join(validation.errors),
                {"output_path": parsed.output_path, "latex_validation": {"errors": validation.errors}},
            )
        output.write_text(validation.normalized, encoding="utf-8")

        artifacts = [str(output)]
        if figure_path is not None:
            artifacts.append(str(figure_path))
        return ok_result(
            {
                "path": str(output),
                "figure_path": str(figure_path) if figure_path else None,
                "candidate_count": len(parsed.candidates),
                "decision_steps": len(parsed.decision_trail),
                "reference_count": len(references),
            },
            artifacts,
        )
    except Exception as exc:
        return error_result(str(exc), {"output_path": parsed.output_path})


# --------------------------------------------------------------------------- #
# Figure
# --------------------------------------------------------------------------- #
def _maybe_render_score_figure(parsed: AdcPaperInput, base_dir: Path) -> Path | None:
    """Best-effort bar chart of the top candidates' composite ADC scores."""

    scored = [c for c in parsed.candidates if c.get("score") is not None][: parsed.max_candidates]
    if len(scored) < 2:
        return None
    try:
        from hackathon_agents.tools.plotting import generate_plot

        figures_dir = base_dir / "figures"
        figure_path = figures_dir / "candidate_scores.png"
        rows = [
            {"candidate": c.get("name") or f"cand-{i + 1}", "score": float(c["score"])}
            for i, c in enumerate(scored)
        ]
        result = generate_plot(
            {
                "data": rows,
                "x_key": "candidate",
                "y_key": "score",
                "kind": "bar",
                "title": "Composite ADC linker score by candidate",
                "output_path": str(figure_path),
            }
        )
        return figure_path if result.ok and figure_path.exists() else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# References
# --------------------------------------------------------------------------- #
def _load_references(path: str | None) -> list[dict[str, Any]]:
    try:
        from hackathon_agents.tools.linker_design import load_reference_linker_corpus

        references, _warnings = load_reference_linker_corpus(path)
        return [ref.model_dump(mode="json") for ref in references]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _render_paper(parsed: AdcPaperInput, *, figure_path: Path | None, references: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "% Generated by hackathon_agents.tools.paper_writer.",
        "\\documentclass[11pt]{article}",
        "\\usepackage[T1]{fontenc}",
        "\\usepackage[margin=1in]{geometry}",
        "\\usepackage{longtable}",
        "\\usepackage{graphicx}",
        "\\usepackage{hyperref}",
        "",
        f"\\title{{{_latex_escape(parsed.title)}}}",
        "\\author{Hackathon Agents (Merck ADC Challenge)}",
        "\\date{\\today}",
        "",
        "\\begin{document}",
        "\\maketitle",
        "",
        "\\begin{abstract}",
        _abstract_text(parsed),
        "\\end{abstract}",
    ]

    _section(lines, "Introduction and Background")
    _paragraphs(lines, _introduction_text(parsed))
    if references:
        _reference_class_list(lines, references)

    _section(lines, "Methods")
    _paragraphs(lines, _methods_text(parsed))
    _goal_profile_table(lines, parsed.goal_profile)

    _section(lines, "Results")
    _paragraphs(lines, _results_text(parsed))
    _candidate_table(lines, parsed.candidates, parsed.max_candidates)
    if figure_path is not None:
        _figure(lines, figure_path)
    _decision_trail_table(lines, parsed.decision_trail)

    _section(lines, "Discussion")
    _paragraphs(lines, _discussion_text(parsed))

    _section(lines, "Conclusion")
    _paragraphs(lines, _conclusion_text(parsed))

    if references:
        _references_section(lines, references)

    lines.extend(["", "\\end{document}", ""])
    return "\n".join(lines)


# --- prose blocks (escaped) ------------------------------------------------- #
def _abstract_text(parsed: AdcPaperInput) -> str:
    return _latex_escape(
        "Antibody-drug conjugate (ADC) efficacy is largely governed by the linker, which "
        "must balance plasma stability with tunable, tumor-site payload release while "
        "preserving solubility and manufacturability. We present an autonomous agentic "
        "workflow that designs ADC linkers with REINVENT4 LinkInvent: given a fixed "
        "conjugation warhead and payload attachment, the agent generates the connecting "
        "linker, scores it against a multi-objective profile, and — as an autonomous "
        "critic — reweights that objective between rounds until convergence. All decisions "
        "are recorded as a provenance trail. Results here are in-silico and provisional."
    )


def _introduction_text(parsed: AdcPaperInput) -> list[str]:
    return [
        "Antibody-drug conjugates fuse the targeting selectivity of monoclonal antibodies "
        "with highly potent payloads. Their clinical performance hinges on three integrated "
        "components — the antibody, the payload, and the linker that connects them. Although "
        "the linker carries no intrinsic bioactivity, it governs plasma stability, "
        "pharmacokinetics, and the conditional release of the payload at the tumor site.",
        "Many ADCs suffer from suboptimal drug properties (instability, aggregation, poor "
        "solubility) and narrow therapeutic windows, frequently traced to premature or "
        "insufficient payload release. Existing linkers often lack the tunability needed to "
        "accommodate diverse antibody-payload combinations and heterogeneous tumor "
        "environments. There is a critical need for next-generation linkers with enhanced "
        "in-vivo stability, precise and tunable release, and broad conjugation compatibility.",
        "We frame linker design as a generative fragment problem: with the warheads fixed, "
        "the object to design is precisely the linker between them. This matches REINVENT4's "
        "LinkInvent mode and lets us score the generated linker in isolation, so the large "
        "fixed warheads and payload do not dominate the objective.",
    ]


def _methods_text(parsed: AdcPaperInput) -> list[str]:
    warhead = parsed.warhead_pair or "a maleimidocaproyl conjugation handle and a payload attachment"
    return [
        "The workflow is a bounded LangGraph pipeline (planner, chemist, tool execution, "
        "critic, writer). The chemist invokes REINVENT4 LinkInvent as a subprocess (locally "
        "or as a SLURM job on the Snellius HPC cluster), generating linkers between a fixed "
        "warhead pair " + f"({warhead}). " + "Generation is a staged reinforcement-learning "
        "run driven by a multi-component scoring function.",
        "The scoring function is derived deterministically from a compact goal profile: "
        "seven weighted objectives (solubility, size, flexibility, synthesizability, "
        "cleavability, stability, and reference similarity) plus constraint toggles. Fragment "
        "descriptors (FragmentSlogP, FragmentTPSA, FragmentMolecularWeight, FragmentNumRotBond) "
        "score the linker itself; a MatchingSubstructure term rewards a cleavable trigger "
        "motif, and CustomAlerts filter labile groups for circulation stability; SAScore "
        "penalizes hard-to-make chemistry. Components are aggregated by geometric mean.",
        "Autonomy resides in the critic. After each round it inspects the candidates' "
        "per-objective subscores and may edit the goal profile — reweighting under-performing "
        "objectives and toggling constraints — while warheads and compute budget stay fixed. "
        "Each edit is validated, re-rendered into a valid REINVENT configuration, applied on "
        "the next round, and appended to a decision trail for full provenance.",
    ]


def _results_text(parsed: AdcPaperInput) -> list[str]:
    n = len([c for c in parsed.candidates if c.get("score") is not None])
    steps = len(parsed.decision_trail)
    return [
        f"The run produced {n} scored linker candidate(s) across the bounded iteration budget. "
        "Table 1 lists the top candidates with their composite score and per-objective "
        "subscores; higher is better on all axes.",
        f"The autonomous critic performed {steps} objective adjustment(s); Table 2 records "
        "each edit and the resulting weight changes, providing an auditable account of how "
        "the design objective evolved.",
    ]


def _discussion_text(parsed: AdcPaperInput) -> list[str]:
    return [
        "Scoring the linker fragment in isolation gives a signal that is not swamped by the "
        "fixed, heavy warheads and payload — the intended benefit of the LinkInvent framing. "
        "The autonomous reweighting lets the system trade off competing ADC objectives "
        "(notably stability versus release) without hand-tuning between rounds.",
        "Limitations: the physicochemical proxies (logP, TPSA, SA score, substructure "
        "presence) are surrogates, not assays; cleavage kinetics and serum stability are not "
        "simulated; and reference-similarity scoring awaits linker SMILES in the corpus. "
        "Reported candidates are computational hypotheses requiring synthesis and validation.",
    ]


def _conclusion_text(parsed: AdcPaperInput) -> list[str]:
    return [
        "We demonstrated an autonomous agent that designs ADC linkers with REINVENT4 "
        "LinkInvent and self-steers its multi-objective goal between rounds, with a complete "
        "decision provenance trail. The approach is a reusable template for constrained, "
        "objective-driven molecular design under expert-defined guardrails.",
    ]


# --- structural helpers ----------------------------------------------------- #
def _section(lines: list[str], title: str) -> None:
    lines.extend(["", f"\\section{{{_latex_escape(title)}}}"])


def _paragraphs(lines: list[str], paragraphs: list[str]) -> None:
    for text in paragraphs:
        lines.extend(["", _latex_escape(text)])


def _reference_class_list(lines: list[str], references: list[dict[str, Any]]) -> None:
    lines.extend(["", "\\subsection{Reference linker classes}", "\\begin{itemize}"])
    for ref in references:
        name = ref.get("name", "linker")
        klass = ref.get("linker_class", "")
        logic = ref.get("release_logic", "")
        lines.append(f"\\item \\textbf{{{_latex_escape(name)}}} ({_latex_escape(klass)}): {_latex_escape(logic)}")
    lines.append("\\end{itemize}")


def _goal_profile_table(lines: list[str], profile: dict[str, Any] | None) -> None:
    if not profile:
        return
    weights = profile.get("weights") or {}
    lines.extend(
        [
            "",
            "\\subsection{Objective weights (initial goal profile)}",
            "\\begin{longtable}{p{0.4\\linewidth}r}",
            "Objective & Weight \\\\",
            "\\hline",
        ]
    )
    for key in ADC_GOAL_KEYS:
        lines.append(f"{_latex_escape(key)} & {_format_value(weights.get(key))} \\\\")
    lines.append("\\end{longtable}")


def _candidate_table(lines: list[str], candidates: list[dict[str, Any]], limit: int) -> None:
    lines.extend(["", "\\subsection{Top linker candidates (Table 1)}"])
    scored = [c for c in candidates if c.get("score") is not None][:limit]
    if not scored:
        lines.append("No scored linker candidates were produced.")
        return
    lines.extend(
        [
            "\\begin{longtable}{p{0.16\\linewidth}p{0.30\\linewidth}rrrr}",
            "Name & SMILES & Score & Solub. & Cleav. & Stab. \\\\",
            "\\hline",
        ]
    )
    for c in scored:
        desc = c.get("descriptors", {})
        row = [
            _latex_escape(c.get("name") or ""),
            _latex_escape(c.get("smiles") or ""),
            _format_value(c.get("score")),
            _format_value(desc.get("adc_solubility")),
            _format_value(desc.get("adc_cleavability")),
            _format_value(desc.get("adc_stability")),
        ]
        lines.append(" & ".join(row) + " \\\\")
    lines.append("\\end{longtable}")


def _figure(lines: list[str], figure_path: Path) -> None:
    # Reference the figure relative to the .tex file (same run directory).
    rel = f"figures/{figure_path.name}"
    lines.extend(
        [
            "",
            "\\begin{figure}[h]",
            "\\centering",
            f"\\includegraphics[width=0.8\\linewidth]{{{rel}}}",
            "\\caption{Composite ADC linker score across the top candidates.}",
            "\\end{figure}",
        ]
    )


def _decision_trail_table(lines: list[str], trail: list[dict[str, Any]]) -> None:
    lines.extend(["", "\\subsection{Autonomous decision trail (Table 2)}"])
    if not trail:
        lines.append("The critic did not adjust the objective during this run.")
        return
    lines.extend(
        [
            "\\begin{longtable}{rp{0.35\\linewidth}p{0.45\\linewidth}}",
            "Iter. & Weight changes & Rationale \\\\",
            "\\hline",
        ]
    )
    for entry in trail:
        iteration = entry.get("iteration", "")
        before = entry.get("weights_before") or {}
        after = entry.get("weights_after") or {}
        changes = "; ".join(
            f"{k}: {before.get(k)} -> {after.get(k)}" for k in sorted(after) if before.get(k) != after.get(k)
        )
        change_text = _latex_escape(changes) or "(constraints/targets only)"
        rationale = _latex_escape(entry.get("rationale") or "")
        lines.append(f"{_format_value(iteration)} & {change_text} & {rationale} \\\\")
    lines.append("\\end{longtable}")


def _references_section(lines: list[str], references: list[dict[str, Any]]) -> None:
    lines.extend(["", "\\section{References}", "\\begin{enumerate}"])
    seen: set[str] = set()
    for ref in references:
        for adc in ref.get("example_adcs", []) or []:
            if adc in seen:
                continue
            seen.add(adc)
            lines.append(f"\\item Clinical reference ADC: {_latex_escape(adc)} ({_latex_escape(ref.get('name', ''))}).")
    if not seen:
        for ref in references:
            lines.append(f"\\item {_latex_escape(ref.get('name', 'reference linker class'))}.")
    lines.append("\\end{enumerate}")
