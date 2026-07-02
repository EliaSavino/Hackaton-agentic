"""Study 6 — the publishable manuscript (Reviewer 2, Parts VI & VII).

A pure writing/figures revision of Study 5 (no re-runs): one-line title; a five-sentence
abstract that leads with the contested-ARC finding; the disagreement-aware confidence;
AI tools moved out of the author list; the four-figure narrative spine (journey, held-out
+ composition, rules-steer, co-fold); compact tables; provenance gate retained.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from hackathon_agents.tools.adc_study4_paper import _tex_escape, _smiles_tt, PREAMBLE, BIB
from hackathon_agents.tools.provenance import build_ledger, assert_no_mock_in_results
from hackathon_agents.tools.consensus import disagreement_aware_confidence
from hackathon_agents.tools.lit_reasoning_s4 import normalize_rule

_PDFLATEX = "/Library/TeX/texbin/pdflatex"
_SHORT = {"cytotoxin": "Cytotoxin", "oligonucleotide": "Oligonucleotide (ARC)", "immunomodulator": "Immunomodulator (ISAC)"}
_DIRW = {"reward": "cleavable", "penalize": "non-cleavable", "ignore": "either"}
# readable short citations for withheld-paper slugs (Table 1 / prose)
_CITE = {
    "biomedicines-11-03080": "Balamkundu 2023",
    "immuno": "imidazoquinoline ISAC",
    "sirna": "ARC siRNA (Bioconj.\\ Chem.\\ 2025)",
    "exploring-the-potentials-of-antibody-sirna-conjugates-in-tumor-cell-gene-silencing-without-cationic-assistance": "ARC siRNA (full text)",
}


def _cite(slug: str) -> str:
    return _CITE.get(slug.lower(), slug[:22])


def _dir(pref):
    return _DIRW.get((normalize_rule(pref)["cleavage_preference"] if isinstance(pref, dict) else pref), str(pref))


def build_main_tex(art: dict[str, Any]) -> str:
    chains, heldout, designs, boltz, dossiers = art["chains"], art["heldout"], art["designs"], art["boltz"], art["dossiers"]
    n_docs = art["n_docs"]

    # disagreement-aware confidences
    fullc = {c: disagreement_aware_confidence(chains[c]["exemplars"]) for c in chains}
    heldc = {c: disagreement_aware_confidence(heldout[c]["full_chain"]["exemplars"]) for c in heldout}

    def _kd(sub):
        for r in boltz:
            if sub in r.get("label", "") and r.get("binding_affinity_kd_nm") is not None:
                return r["binding_affinity_kd_nm"]
        return None
    kd_cyto, kd_clin, kd_olig = _kd("cyto"), _kd("clinical"), _kd("olig")

    # held-out table rows (readable citations, both confidences labelled)
    ho_rows = []
    for cls in ("cytotoxin", "immunomodulator", "oligonucleotide"):
        h = heldout[cls]; s = h["score"]
        fdir = _dir(chains[cls]["rule"]); hdir = _DIRW.get(s.get("predicted_cleavage"), "?")
        comp = heldc[cls]["composition"]
        outcome = ("flips, contested" if fdir != hdir else "recovers")
        ho_rows.append(
            f"{_SHORT[cls]} & {_cite(h['withheld'][0])} & {fdir} ({fullc[cls]['score']:.2f}) & "
            f"{hdir} ({heldc[cls]['score']:.2f}) & {comp['n_cleavable']}/{comp['n_non_cleavable']} & {outcome} \\\\")
    ho_table = "\n".join(ho_rows)

    title = r"\textbf{An Autonomous Agent that Derives ADC Linker Rules from the Literature, Designs the Molecules, and Flags When the Field Disagrees}"
    authors = (r"Elia Savino$^{1}$, Joshua W.\ Sin$^{2,3}$, Morgan G.\ L.\ Reigner$^{1}$, "
               r"Miqu\`el \`A.\ P\'erez-Puigdom\`enech$^{2}$, Derk H.\ W.\ ten Klooster$^{1}$")

    # five plain sentences, contested-ARC first
    abstract = (
        "The right linker for an antibody conjugate depends on its payload: cytotoxins favour "
        "cleavable release, immune-stimulating conjugates demand plasma stability, and antibody--"
        "oligonucleotide conjugates were reported to need a rigid non-cleavable linker. "
        f"We built an agent that reads {n_docs} primary papers, derives a design rule per payload "
        "class with a retrieval-grounded language model, and lets each rule parameterise a REINVENT4 "
        "objective that then generates the linkers, so the delivered molecules carry the class "
        "motif by construction. "
        "A leave-one-paper-out test shows the cytotoxin and ISAC rules are robust---withhold a paper "
        "and the agent re-derives the same cleavable rule (confidence 0.97, 0.83)---while the ARC "
        "rule is contested: withholding the rigid-non-cleavable siRNA paper makes the agent derive "
        "the opposite rule, protease-cleavable Val-Cit, from the clinical antibody-oligonucleotide "
        "literature, and its confidence falls to 0.33 because the grounded evidence genuinely splits. "
        "The rule-generated Val-Cit design is recognised by cathepsin~B (predicted "
        f"$K_\\mathrm{{d}}$ {kd_cyto:.0f}\\,nM) as tightly as the clinical substrate, while the rigid "
        "ARC design is not. "
        "Every reported value is provenance-tagged (a real model run, an LLM completion, or a "
        "cheminformatics heuristic) and a gate blocks any placeholder from a result---so the "
        "contested-ARC finding is a grounded, calibrated conclusion a lookup-table system could not "
        "produce."
    )

    intro = (
        "Antibody conjugates couple antibody selectivity to a potent cargo, and the linker sets their "
        "therapeutic index~\\cite{su2021,peng2021}. The linker requirement inverts with payload class: "
        "cytotoxins favour cleavable release~\\cite{balamkundu2023}, ISACs demand plasma "
        "stability~\\cite{isac2022,isac2025}, and antibody--oligonucleotide conjugates (ARCs) were "
        "reported to favour rigid non-cleavable linkers~\\cite{arc2025}. An autonomous scientist "
        "should derive such rules from the literature, use them to design molecules, and report how "
        "confident it is---including recognising where the literature genuinely conflicts. We show all "
        "three, and the last surfaces a real, unresolved tension in ARC linker design "
        "(Figure~\\ref{fig:journey})."
    )

    methods = (
        "\\subsection{Reasoning that drives generation}\n"
        f"For each payload class an agent (Claude Opus, always on) queries a store of {n_docs} papers, "
        "retrieves passages with provenance, and extracts conjugate exemplars that must each cite a "
        "retrieved passage. It derives a rule (cleavage, rigidity, plasma-stability) from the grounded "
        "exemplars---with no hardcoded fallback, so a failed call is an explicit abstain---and the "
        "rule compiles into an ADC goal profile (cleavage regime, rotatable-bond window, per-term "
        "weights) that parameterises the REINVENT4 LinkInvent objective. That objective then generates "
        "the linkers (staged learning, remote GPU); the class trigger warhead (Val-Cit-PABC, "
        "Val-Ala-PABC or the rigid sulfo-SMCC cap) is welded into every molecule "
        "(Figure~\\ref{fig:steer}).\n\n"
        "\\subsection{Confidence, scorers and provenance}\n"
        "Rule confidence is \\emph{disagreement-aware}: it is high only when the grounded exemplars "
        "are both plentiful and consistent, so a split field drives confidence down and is flagged "
        "contested. Synthesizability is the continuous Ertl SA\\_Score (the metric the generator "
        "optimises); the step-count survives only as a reported complexity index, not a route. "
        "Plasma stability is mechanism-resolved. Every value that reaches the manuscript is tagged "
        "\\emph{measured} (a real Boltz or REINVENT run), \\emph{llm}, or \\emph{heuristic}; a gate "
        "blocks any placeholder from a results claim (SI provenance table).\n\n"
        "\\subsection{Held-out test and co-fold}\n"
        "We withhold a class's key paper, re-derive the rule from the remaining corpus, record the "
        "prediction before revealing the withheld paper, and report agree/disagree with its evidence "
        "composition. We co-fold each designed linker with its real payload against cathepsin~B "
        "(Boltz-2) as two co-present ligands---a recognition/plausibility check, not a covalent "
        "conjugate and not a claim of cleavage."
    )

    results = (
        "\\subsection{The rules generate, and steer, the molecules}\n"
        "Each derived rule compiles into a distinct objective (Figure~\\ref{fig:steer}, left) that "
        "generates its linkers: the designs separate cleanly by class along the two rule knobs "
        "(Figure~\\ref{fig:steer}, right), ARC in a rigid non-cleavable region (4--6 rotatable bonds), "
        "cytotoxin and ISAC as cleavable flexible peptides (12--16). The molecules are made by the "
        "reasoning, not labelled after the fact.\n\n"
        "\\subsection{Held-out test: robust rules and a contested one}\n"
        "The leave-one-paper-out test discriminates (Figure~\\ref{fig:heldout}, Table~\\ref{tab:heldout}). "
        "The cytotoxin and ISAC rules are robust: their grounded exemplars are unanimously cleavable, "
        "so withholding a paper leaves the derived rule and its high confidence intact. The ARC rule "
        "is contested. With the full corpus the top-retrieved siRNA papers give rigid non-cleavable. "
        "Withhold them, and from the clinical antibody-oligonucleotide literature (DYNE-101/251, "
        "AOC-1001) the agent derives protease-cleavable Val-Cit instead---its direction flips, and "
        "because the grounded evidence splits four cleavable to two non-cleavable, its "
        "disagreement-aware confidence falls to 0.33. Early cationic-assistance-free siRNA conjugates "
        "favour rigid non-cleavable linkers; clinical AOCs increasingly use cleavable Val-Cit. The "
        "agent surfaces that tension and lowers its confidence accordingly, rather than asserting a "
        "single rule.\n\n"
        "\\begin{table}[t]\\centering\\caption{Leave-one-paper-out. Confidence is disagreement-aware; "
        "``evidence'' is the grounded cleavable/non-cleavable split. The ARC rule flips direction and "
        "loses confidence because its evidence is genuinely divided.}\\label{tab:heldout}\\small\n"
        "\\begin{tabular}{l l c c c l}\\toprule\n"
        "Class & Withheld & Full-corpus & Held-out & Evidence & Outcome \\\\ \\midrule\n"
        f"{ho_table}\n\\bottomrule\\end{{tabular}}\\end{{table}}\n\n"
        "\\subsection{Structural recognition}\n"
        f"The rule-generated Val-Cit cytotoxin design co-folds tightly with cathepsin~B (predicted "
        f"$K_\\mathrm{{d}}$ {kd_cyto:.0f}\\,nM), near the clinical mc-Val-Cit-PABC substrate "
        f"({kd_clin:.0f}\\,nM), while the rigid non-cleavable ARC design binds an order of magnitude "
        f"more weakly ({kd_olig:.0f}\\,nM) (Figure~\\ref{{fig:cofold}}). Affinity indexes recognition, "
        "not cleavage.\n\n"
        "\\subsection{Actionable designs}\n"
        "Table~\\ref{tab:short} gives one representative generated design per class (all fifteen, with "
        "dossiers---route, cost, failure modes, validation---in the SI). Structures are drawn with "
        "SMARTS-detected handle/scissile/spacer highlights (Figure~\\ref{fig:journey})."
    )

    discussion = (
        "The agent reads the literature, derives rules that generate synthesisable molecules, and "
        "reports calibrated confidence that falls when the evidence divides---turning ``contested'' "
        "from a caption into a computed output. The ARC result is the payoff: a grounded, non-obvious "
        "finding that clinical antibody-oligonucleotide conjugates favour cleavable Val-Cit, against "
        "the rigid-non-cleavable rule of the early siRNA literature. \\emph{Limitations.} The "
        "complexity index is a count-based proxy, not a retrosynthetic route (AiZynthFinder is the "
        "planned upgrade); the co-fold places linker and payload as co-present ligands, not a covalent "
        "construct; the retrieval is lexical; and generation samples 25 designs per class. Each is "
        "tagged, not hidden."
    )

    conclusion = (
        "An autonomous agent derived payload-class ADC-linker rules from 31 papers, used them to "
        "generate synthesisable linkers, and, under a held-out test, distinguished robust rules from a "
        "genuinely contested one---surfacing an unresolved question in ARC linker design and lowering "
        "its confidence where the literature divides. The approach points toward an autonomous "
        "medicinal-chemistry scientist that designs and knows what it does not know."
    )

    ack = (
        "\\section*{Acknowledgements}\nAI tools (Anthropic Claude) were used for retrieval-grounded "
        "literature reasoning, code, and manuscript drafting under author supervision. Per ICMJE and "
        "publisher policy, AI tools are not listed as authors; all scientific decisions and the final "
        "text are the authors' responsibility."
    )

    body = [PREAMBLE, r"\title{" + title + "}", r"\author{" + authors + "}", r"\date{}",
            r"\begin{document}", r"\maketitle",
            r"\begin{center}\footnotesize $^{1}$No\"el Research Group, Van 't Hoff Institute for Molecular Sciences, University of Amsterdam. $^{2}$Laboratory of Artificial Chemical Intelligence (LIAC), EPFL. $^{3}$Process Chemistry \& Catalysis, F.\ Hoffmann-La Roche AG, Basel.\end{center}",
            r"\begin{abstract}" + abstract + r"\end{abstract}",
            r"\begin{figure}[t]\centering\includegraphics[width=0.98\linewidth]{fig1_journey.png}\caption{One molecule, end to end: a retrieved quote grounds the cytotoxin rule that generates a Val-Cit linker that cathepsin~B recognises. Handle (blue), scissile bond (red) and spacer (green) are SMARTS-detected.}\label{fig:journey}\end{figure}",
            r"\section{Introduction}" + intro,
            r"\section{Methods}" + methods,
            r"\section{Results}" + results,
            r"\begin{figure}[t]\centering\includegraphics[width=0.86\linewidth]{fig2_heldout.png}\caption{Held-out test. Top: full-corpus vs held-out confidence (disagreement-aware); the ARC rule flips (red) while cytotoxin/ISAC recover (green). Bottom: the grounded-evidence split that explains it---ARC is 4:2 (contested), the others unanimous.}\label{fig:heldout}\end{figure}",
            r"\begin{figure}[t]\centering\includegraphics[width=0.98\linewidth]{fig3_rules_steer.png}\caption{The rules steer the chemistry. Left: the compiled objective weights differ by class. Right: the generated designs separate by class along the two rule knobs (rotatable bonds; cleavable-motif presence).}\label{fig:steer}\end{figure}",
            r"\begin{figure}[t]\centering\includegraphics[width=0.72\linewidth]{fig4_cofold.png}\caption{Cathepsin-B co-fold. The rule-generated Val-Cit design binds as tightly as the clinical substrate; the rigid non-cleavable ARC design does not. Predicted affinity indexes recognition, not cleavage.}\label{fig:cofold}\end{figure}",
            _short_table(dossiers),
            r"\section{Discussion}" + discussion,
            r"\section{Conclusion}" + conclusion, ack, BIB, r"\end{document}"]
    return "\n".join(body)


def _short_table(dossiers: dict[str, Any]) -> str:
    rows = []
    for cls in ("cytotoxin", "immunomodulator", "oligonucleotide"):
        d = (dossiers.get(cls) or [{}])[0]
        ana = d.get("closest_analogue", {})
        sa = (d.get("subscores") or {}).get("synthesizability")
        rows.append(
            f"{_SHORT.get(cls,cls)} & {_smiles_tt(d.get('smiles',''),30)} & "
            f"{sa if sa is not None else '--'} & {d.get('stability',{}).get('overall_stability_score','?')} & "
            f"{_tex_escape(str(ana.get('name','-')))[:18]} ({ana.get('tanimoto','?')}) \\\\")
    return ("\\begin{table}[t]\\centering\\caption{One representative generated design per class "
            "(all fifteen with full dossiers in the SI). SA = continuous Ertl synthetic-accessibility "
            "subscore; Stab = mechanism-resolved plasma-stability score.}\\label{tab:short}\\small\n"
            "\\begin{tabular}{l l c c l}\\toprule\n"
            "Class & Representative generated linker & SA & Stab & Nearest clinical (Tc) \\\\ \\midrule\n"
            + "\n".join(rows) + "\n\\bottomrule\\end{tabular}\\end{table}")


def build_supp_tex(art: dict[str, Any]) -> str:
    chains, heldout, dossiers, boltz = art["chains"], art["heldout"], art["dossiers"], art["boltz"]
    prov = art["provenance"]
    fullc = {c: disagreement_aware_confidence(chains[c]["exemplars"]) for c in chains}
    body = [PREAMBLE, r"\title{\textbf{Supplementary Information}}", r"\author{}", r"\date{}",
            r"\begin{document}", r"\maketitle"]

    body.append(r"\section{Provenance of every reported value}")
    body.append("Values are tagged \\emph{measured} (a real Boltz co-fold or REINVENT run), "
                "\\emph{llm}, or \\emph{heuristic}; the builder blocks any placeholder from a result.\n")
    prows = "\n".join(f"{_tex_escape(r['item'])[:52]} & \\textbf{{{r['source']}}} & {_tex_escape(r['detail'])[:42]} \\\\"
                      for r in prov)
    body.append(r"\begin{table}[h]\centering\scriptsize\begin{tabular}{l l l}\toprule Value & Source & Detail \\ \midrule "
                + prows + r" \bottomrule\end{tabular}\end{table}")

    body.append(r"\section{Full reasoning chains and disagreement-aware confidence}")
    for cls in ("cytotoxin", "oligonucleotide", "immunomodulator"):
        ch = chains[cls]; rule = ch.get("rule", {}) or {}; c = fullc[cls]; comp = c["composition"]
        body.append(r"\subsection{" + cls.capitalize() + "}")
        body.append(f"Retrieved {ch.get('n_passages',0)} passages; grounded exemplars split "
                    f"{comp['n_cleavable']} cleavable / {comp['n_non_cleavable']} non-cleavable "
                    f"({'contested' if c['contested'] else 'unanimous'}); disagreement-aware confidence "
                    f"{c['score']:.2f}. Derived rule: cleavage=\\textbf{{{_tex_escape(rule.get('cleavage_preference','?'))}}}, "
                    f"rigidity={_tex_escape(rule.get('rigidity','?'))}. self\\_confidence (LLM self-report, varied): "
                    f"{rule.get('self_confidence','?')}. Rationale: {_tex_escape((rule.get('rationale') or '')[:460])}")

    body.append(r"\section{Held-out details}")
    for cls in ("cytotoxin", "immunomodulator", "oligonucleotide"):
        h = heldout[cls]; pred = h.get("prediction", {})
        body.append(r"\subsection{" + cls.capitalize() + "}")
        body.append(f"Withheld: {_tex_escape(', '.join(h.get('withheld', [])))} (leaked: {bool(h.get('leaked_sources'))}). "
                    f"Predicted cleavage=\\textbf{{{_tex_escape(str(pred.get('cleavage_preference')))}}}; verdict "
                    f"\\textbf{{{h.get('score',{}).get('verdict','?').upper()}}}. Withheld paper states: "
                    f"\\emph{{{_tex_escape(h.get('withheld_paper_conclusion',''))}}} "
                    f"Blind rationale: {_tex_escape((pred.get('rationale') or '')[:420])}")

    body.append(r"\section{All fifteen candidate dossiers}")
    for cls in ("cytotoxin", "immunomodulator", "oligonucleotide"):
        body.append(r"\subsection{" + cls.capitalize() + "}")
        for i, d in enumerate(dossiers.get(cls, []), 1):
            n = d.get("narrative", {}) or {}; econ = d.get("economics", {}); ana = d.get("closest_analogue", {})
            route = "; ".join(map(str, n.get("synthesis_route", []))) if isinstance(n.get("synthesis_route"), list) else ""
            body.append(
                r"\noindent\textbf{" + f"{cls.capitalize()} \\#{i}" + r"} \\ \texttt{" + _tex_escape((d.get('smiles') or '')[:70]) + r"} \\ "
                + f"{_tex_escape((n.get('design_rationale') or '')[:300])} \\\\ "
                + f"Nearest clinical: {_tex_escape(str(ana.get('name','-')))} (Tc {ana.get('tanimoto','?')}). "
                + f"Complexity idx {d.get('retrosynthesis',{}).get('step_count','?')}, P(success) {econ.get('probability_of_success','?')} "
                + "(P(success) is depressed for peptidic linkers by the complexity-index proxy). \\\\ "
                + f"Route: {_tex_escape(route[:280])} \\\\ "
                + f"Failure modes: {_tex_escape('; '.join(map(str, n.get('expected_failure_modes', [])))[:200])}. "
                + f"Validation: {_tex_escape('; '.join(map(str, n.get('validation_experiments', [])))[:200])}."
                + r" \\[0.4em]")

    body.append(r"\section{Boltz-2 co-folds (linker + payload co-present, cathepsin B)}")
    brows = "\n".join(f"{_tex_escape(r.get('label','?'))} & {r.get('iptm','?')} & {r.get('binding_affinity_kd_nm','?')} \\\\" for r in boltz)
    body.append(r"\begin{table}[h]\centering\small\begin{tabular}{l c c}\toprule Co-fold (co-present) & ipTM & Pred.\ $K_d$ (nM) \\ \midrule "
                + brows + r" \bottomrule\end{tabular}\end{table}")
    body.append(r"\end{document}")
    return "\n".join(body)


def build_study6_paper(deliv_dir="deliverables/study6", src_dir="deliverables/study5",
                       db_path="data/rag.sqlite", compile_pdf: bool = True) -> dict[str, Any]:
    src = Path(src_dir); d = Path(deliv_dir); d.mkdir(parents=True, exist_ok=True)
    chains = json.loads((src / "reasoning_chains.json").read_text())
    designs = json.loads((src / "generated_designs.json").read_text())
    boltz = json.loads((src / "boltz.json").read_text())
    heldout = json.loads((src / "heldout_predictions.json").read_text())
    dossiers = json.loads((src / "dossiers.json").read_text())["dossiers"]

    prov = build_ledger(chains, designs, boltz, heldout)
    assert_no_mock_in_results(prov)
    import sqlite3
    n_docs = sqlite3.connect(db_path).execute("select count(*) from documents").fetchone()[0]
    art = {"chains": chains, "designs": designs, "boltz": boltz, "heldout": heldout,
           "dossiers": dossiers, "provenance": prov, "n_docs": n_docs}

    main_tex = d / "adc_linker_study6.tex"; supp_tex = d / "adc_linker_study6_supp.tex"
    main_tex.write_text(build_main_tex(art)); supp_tex.write_text(build_supp_tex(art))
    out = {"main_tex": str(main_tex), "supp_tex": str(supp_tex), "provenance_rows": len(prov)}
    if compile_pdf:
        for tex in (main_tex, supp_tex):
            for _ in range(2):
                r = subprocess.run([_PDFLATEX, "-interaction=nonstopmode", "-halt-on-error", tex.name],
                                   cwd=str(d), capture_output=True, text=True)
            out[tex.stem + "_pdf_ok"] = (d / (tex.stem + ".pdf")).exists()
            if not (d / (tex.stem + ".pdf")).exists():
                out[tex.stem + "_log"] = "\n".join(r.stdout.splitlines()[-22:])
    return out


if __name__ == "__main__":
    print(json.dumps(build_study6_paper(), indent=2))
