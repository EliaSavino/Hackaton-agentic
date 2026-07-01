from __future__ import annotations

from typing import Any

from hackathon_agents.config import AppConfig, RunMode, ToolConfig


_TOOL_DESCRIPTIONS: dict[str, dict[str, Any]] = {
    "rdkit": {
        "category": "chemistry_descriptors",
        "summary": "Validate SMILES, compute molecular descriptors, and filter molecules.",
        "inputs": ["SMILES strings", "MoleculeFilterConstraints"],
        "outputs": ["canonical SMILES", "descriptor dictionaries", "kept/rejected molecule lists"],
        "failure_modes": ["RDKit import unavailable", "invalid SMILES"],
        "planner_notes": ["Use before ranking molecule candidates."],
    },
    "python_exec": {
        "category": "computation",
        "summary": "Run bounded Python snippets when explicitly enabled.",
        "inputs": ["Python code", "timeout"],
        "outputs": ["stdout", "stderr", "return code"],
        "failure_modes": ["timeout", "disallowed imports", "runtime exception"],
        "planner_notes": ["Prefer domain tools before arbitrary Python execution."],
    },
    "file_io": {
        "category": "artifact_io",
        "summary": "Read and write JSON/CSV files.",
        "inputs": ["path", "rows or JSON content"],
        "outputs": ["JSON files", "CSV files"],
        "failure_modes": ["unwritable path", "invalid file format"],
    },
    "plotting": {
        "category": "visualization",
        "summary": "Generate simple plots from tabular rows.",
        "inputs": ["tabular rows", "x/y keys", "output path"],
        "outputs": ["PNG plots"],
        "failure_modes": ["missing matplotlib backend", "invalid data key"],
    },
    "doc_writer": {
        "category": "reporting",
        "summary": "Write DOCX scientific reports from structured state.",
        "inputs": ["plan", "candidates", "tool results", "critic notes"],
        "outputs": ["report.docx"],
        "failure_modes": ["unwritable output path", "python-docx unavailable"],
    },
    "memory_writer": {
        "category": "provenance",
        "summary": "Append shared run memory as JSONL and Markdown.",
        "inputs": ["run event summary", "state metadata"],
        "outputs": ["project_memory.jsonl", "project_memory.md"],
        "failure_modes": ["unwritable memory path"],
    },
    "latex_writer": {
        "category": "reporting",
        "summary": "Write a LaTeX report from structured discovery state.",
        "inputs": ["plan", "candidates", "tool results", "critic notes"],
        "outputs": ["report.tex"],
        "failure_modes": ["unwritable output path"],
    },
    "paper_writer": {
        "category": "reporting",
        "summary": "Write a ~5-page publication-style LaTeX paper for the ADC linker-design workflow.",
        "inputs": ["user request", "goal profile", "linker candidates", "autonomous decision trail", "reference corpus"],
        "outputs": ["adc_paper.tex", "candidate score figure"],
        "failure_modes": ["unwritable output path", "LaTeX validation failure"],
        "planner_notes": ["Runs only when an ADC goal profile is active."],
    },
    "paper_review": {
        "category": "literature_review",
        "summary": "Extract sections, claims, limitations, and reproducibility notes from papers.",
        "inputs": ["text, Markdown, PDF, or DOCX paper path"],
        "outputs": ["structured paper review JSON"],
        "failure_modes": ["unreadable file", "missing PDF/DOCX dependency"],
    },
    "literature_tools": {
        "category": "literature_search",
        "summary": "Search local literature snippets and return evidence-like matches.",
        "inputs": ["query", "local corpus"],
        "outputs": ["literature snippets", "source metadata"],
        "failure_modes": ["missing corpus", "unsupported file extension"],
    },
    "linker_design": {
        "category": "adc_linker_design",
        "summary": "Generate, score, and report ADC linker concepts with deterministic in-silico proof points.",
        "inputs": ["ADC linker objective", "payload classes", "desired triggers", "conjugation handles"],
        "outputs": ["ranked linker candidates", "scorecards", "proof points", "JSON/CSV/Markdown dossier"],
        "failure_modes": ["invalid custom reference corpus", "unwritable output directory"],
        "planner_notes": ["Use for ADC/linker challenge prompts before generic molecule generation."],
    },
    "rag": {
        "category": "retrieval",
        "summary": "Index and search local documents through SQLite-backed RAG.",
        "inputs": ["documents", "query", "database path"],
        "outputs": ["retrieved chunks", "RAG context"],
        "failure_modes": ["missing database", "unsupported document type"],
    },
    "calculation_tools": {
        "category": "scientific_calculation",
        "summary": "Run deterministic chemistry/kinetics calculations.",
        "inputs": ["calculation mode", "numeric parameters"],
        "outputs": ["rate constants", "thermodynamic values"],
        "failure_modes": ["invalid numeric domain", "unsupported mode"],
    },
    "statistics_tools": {
        "category": "statistics",
        "summary": "Compute deterministic statistics and uncertainty summaries.",
        "inputs": ["numeric samples", "bootstrap settings"],
        "outputs": ["summary statistics", "confidence intervals"],
        "failure_modes": ["empty samples", "invalid confidence level"],
    },
    "robrains_bo": {
        "category": "optimization",
        "summary": "Recommend candidates via the RoBrains Bayesian optimization adapter.",
        "inputs": ["search space", "observations", "backend settings"],
        "outputs": ["optimization suggestions"],
        "failure_modes": ["missing RoBrains repo", "invalid search space", "backend import failure"],
    },
    "saturn": {
        "category": "molecule_generation",
        "summary": "Generate goal-directed molecules with Saturn or deterministic mock output.",
        "inputs": ["objective", "oracle components", "RL settings", "seed SMILES"],
        "outputs": ["saturn_config.json", "generated molecule records"],
        "failure_modes": ["missing Saturn checkout", "timeout", "invalid Saturn config"],
        "mock_behavior": "Returns deterministic molecule candidates when disabled or run=false.",
    },
    "reinvent": {
        "category": "molecule_generation",
        "summary": "Generate molecules with REINVENT4 (de novo/LibInvent/LinkInvent/Mol2Mol sampling and staged_learning RL) or deterministic mock output.",
        "inputs": ["objective", "generator_type + prior", "input SMILES (scaffolds/warheads)", "sampling or RL/scoring settings"],
        "outputs": ["reinvent_config.json", "generated molecule records"],
        "failure_modes": ["missing REINVENT install", "missing prior_base", "timeout", "invalid REINVENT config"],
        "planner_notes": [
            "Prefer REINVENT for de novo sampling, scaffold decoration (LibInvent), and linker design (LinkInvent).",
            "Use Saturn instead for sample-efficient goal-directed RL with a custom oracle.",
            "Set state.metadata['reinvent'] with ReinventInput fields to opt in.",
        ],
        "mock_behavior": "Returns deterministic molecule candidates when disabled or run=false.",
    },
    "xtb": {
        "category": "quantum_chemistry",
        "summary": "Check or run xTB calculations when enabled.",
        "inputs": ["coordinates", "charge", "multiplicity"],
        "outputs": ["xTB availability or calculation artifacts"],
        "failure_modes": ["missing executable", "timeout"],
    },
    "dft_tools": {
        "category": "quantum_chemistry",
        "summary": "Prepare and parse generic DFT calculation artifacts.",
        "inputs": ["structure", "method", "basis", "program"],
        "outputs": ["DFT inputs", "parsed energies", "comparison rows"],
        "failure_modes": ["invalid structure", "unsupported parser input"],
    },
    "orca": {
        "category": "quantum_chemistry",
        "summary": "Check or generate ORCA inputs and optional ORCA runs.",
        "inputs": ["coordinates", "method", "basis", "timeout"],
        "outputs": ["ORCA input/result files"],
        "failure_modes": ["missing executable", "timeout"],
    },
    "snellius_vllm": {
        "category": "hpc_model_serving",
        "summary": "Generate Slurm scripts for serving vLLM on Snellius.",
        "inputs": ["model checkpoint", "partition", "GPU count", "port"],
        "outputs": ["Slurm job script", "client environment commands"],
        "failure_modes": ["invalid partition", "container unavailable", "port conflict"],
    },
    "baybe": {
        "category": "experiment_design",
        "summary": "Recommend next experiments through BayBE or deterministic fallback.",
        "inputs": ["parameters", "targets", "measurements", "batch size"],
        "outputs": ["experiment recommendations"],
        "failure_modes": ["missing optional dependency", "invalid search space"],
        "mock_behavior": "Returns deterministic space-filling recommendations when disabled or run=false.",
    },
    "boltz_2": {
        "category": "structure_prediction",
        "summary": "Run or mock Boltz-2 protein-ligand co-folding predictions.",
        "inputs": ["protein sequence", "ligand SMILES", "prediction settings"],
        "outputs": ["binding metrics", "PDB artifacts"],
        "failure_modes": ["missing executable/dependency", "timeout", "GPU unavailable"],
        "mock_behavior": "Returns deterministic binding-like metrics when disabled or run=false.",
    },
}


def build_tool_registry(config: AppConfig) -> list[dict[str, Any]]:
    """Return a planner-friendly registry snapshot for configured tools."""

    return [
        _tool_entry(name, tool, config.run_mode)
        for name, tool in sorted(config.tools.items())
    ]


def _tool_entry(name: str, tool: ToolConfig, run_mode: RunMode) -> dict[str, Any]:
    description = _TOOL_DESCRIPTIONS.get(name, {})
    enabled_modes = [mode.value for mode in tool.enabled_modes] if tool.enabled_modes else None
    enabled_for_mode = tool.enabled_for_mode(run_mode)
    real_execution_allowed = bool(
        tool.model_extra.get("allow_run")
        or tool.model_extra.get("allow_submit")
        or (tool.executable and enabled_for_mode)
    )
    return {
        "name": name,
        "category": description.get("category", "general"),
        "enabled": enabled_for_mode,
        "configured_enabled": tool.enabled,
        "unavailable_reason": _unavailable_reason(tool, run_mode),
        "run_mode": run_mode.value,
        "enabled_modes": enabled_modes,
        "executable": tool.executable,
        "timeout_seconds": tool.timeout_seconds,
        "summary": description.get("summary", "Configured tool."),
        "inputs": description.get("inputs", []),
        "outputs": description.get("outputs", []),
        "failure_modes": description.get("failure_modes", []),
        "planner_notes": description.get("planner_notes", []),
        "mock_behavior": description.get("mock_behavior"),
        "mock_safe": bool(description.get("mock_behavior")) or not real_execution_allowed,
        "real_execution_allowed": real_execution_allowed,
        "external_side_effects": _external_side_effects(name, tool),
        "execution_risk": _execution_risk(name, tool, real_execution_allowed),
        "config": _safe_config(tool),
    }


def summarize_tool_registry(registry: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, int] = {}
    enabled = []
    disabled = []
    real_execution = []
    for entry in registry:
        categories[entry["category"]] = categories.get(entry["category"], 0) + 1
        if entry["enabled"]:
            enabled.append(entry["name"])
        else:
            disabled.append(entry["name"])
        if entry["real_execution_allowed"]:
            real_execution.append(entry["name"])
    return {
        "tool_count": len(registry),
        "enabled_count": len(enabled),
        "disabled_count": len(disabled),
        "enabled_tools": enabled,
        "disabled_tools": disabled,
        "categories": categories,
        "real_execution_tools": real_execution,
    }


def _unavailable_reason(tool: ToolConfig, run_mode: RunMode) -> str | None:
    if not tool.enabled:
        return "disabled in config"
    if tool.enabled_modes is not None and run_mode not in tool.enabled_modes:
        modes = ", ".join(mode.value for mode in tool.enabled_modes)
        return f"not enabled for run mode {run_mode.value}; enabled modes: {modes}"
    return None


def _external_side_effects(name: str, tool: ToolConfig) -> list[str]:
    effects = []
    if name in {"file_io", "plotting", "doc_writer", "latex_writer", "memory_writer", "rag"}:
        effects.append("writes local files")
    if tool.executable:
        effects.append("may invoke local executable")
    if name in {"xtb", "orca", "saturn", "boltz_2", "reinvent"}:
        effects.append("may run long scientific compute")
    if name in {"snellius_vllm"} or tool.model_extra.get("allow_submit"):
        effects.append("may submit or prepare HPC jobs")
    if name in {"literature_tools", "rag", "paper_review"}:
        effects.append("reads local documents")
    return effects


def _execution_risk(name: str, tool: ToolConfig, real_execution_allowed: bool) -> str:
    if name in {"python_exec", "snellius_vllm"} or tool.model_extra.get("allow_submit"):
        return "high"
    if name in {"xtb", "orca", "saturn", "boltz_2", "reinvent"} and real_execution_allowed:
        return "medium"
    if tool.executable:
        return "medium"
    return "low"


def _safe_config(tool: ToolConfig) -> dict[str, Any]:
    fields = {
        "timeout_seconds": tool.timeout_seconds,
        "allow_imports": tool.allow_imports,
        "jsonl_path": tool.jsonl_path,
        "markdown_path": tool.markdown_path,
        "max_markdown_entries": tool.max_markdown_entries,
    }
    for key, value in tool.model_extra.items():
        if "key" in key.lower() or "token" in key.lower() or "secret" in key.lower():
            fields[key] = bool(value)
        else:
            fields[key] = value
    return {key: value for key, value in fields.items() if value is not None}
