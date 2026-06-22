from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypedDict

from hackathon_agents.agents import chemist, critic, planner, writer
from hackathon_agents.config import AppConfig, RunMode
from hackathon_agents.logging_config import get_logger
from hackathon_agents.schemas.molecules import MoleculeFilterConstraints
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.doc_writer import write_scientific_report
from hackathon_agents.tools.file_io import write_csv
from hackathon_agents.tools.orca import check_orca_availability, run_orca
from hackathon_agents.tools.plotting import generate_plot
from hackathon_agents.tools.rdkit_tools import compute_descriptors, filter_molecules, validate_smiles
from hackathon_agents.tools.xtb import check_xtb_availability

logger = get_logger(__name__)


class _GraphState(TypedDict, total=False):
    original_user_request: str
    plan: dict[str, Any] | None
    candidate_molecules: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    errors: list[str]
    critic_notes: list[str]
    critic_decisions: list[dict[str, Any]]
    final_report_path: str | None
    messages: list[str]
    run_dir: str | None
    run_mode: str
    iteration: int
    max_iterations: int
    needs_more_passes: bool
    stop_reason: str | None
    requested_next_actions: list[str]
    metadata: dict[str, Any]


class DiscoveryGraph:
    def __init__(self, config: AppConfig):
        self.config = config
        self._compiled = self._try_build_langgraph()

    def invoke(self, state: DiscoveryStatePayload | dict[str, Any]) -> DiscoveryStatePayload:
        payload = state if isinstance(state, DiscoveryStatePayload) else DiscoveryStatePayload.model_validate(state)
        if self._compiled is not None:
            result = self._compiled.invoke(payload.model_dump(mode="json"))
            return DiscoveryStatePayload.model_validate(result)
        return self._invoke_fallback(payload)

    def _invoke_fallback(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        state = self._planner_node(state)
        while True:
            state = self._chemist_node(state)
            state = self._tool_execution_node(state)
            state = self._critic_node(state)
            if self._route_after_critic_state(state) != "chemist":
                break
            state.append_message("graph: routing back to chemist for another bounded pass")
        state = self._writer_node(state)
        return state

    def _try_build_langgraph(self):
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            logger.debug("LangGraph is not installed; using deterministic fallback runner.")
            return None

        workflow = StateGraph(_GraphState)
        workflow.add_node("planner", self._dict_node(self._planner_node))
        workflow.add_node("chemist", self._dict_node(self._chemist_node))
        workflow.add_node("tool_execution", self._dict_node(self._tool_execution_node))
        workflow.add_node("critic", self._dict_node(self._critic_node))
        workflow.add_node("writer", self._dict_node(self._writer_node))
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "chemist")
        workflow.add_edge("chemist", "tool_execution")
        workflow.add_edge("tool_execution", "critic")
        workflow.add_conditional_edges(
            "critic",
            self._route_after_critic,
            {
                "chemist": "chemist",
                "writer": "writer",
            },
        )
        workflow.add_edge("writer", END)
        return workflow.compile()

    def _dict_node(self, func: Callable[[DiscoveryStatePayload], DiscoveryStatePayload]):
        def wrapped(raw_state: dict[str, Any]) -> dict[str, Any]:
            state = DiscoveryStatePayload.model_validate(raw_state)
            return func(state).model_dump(mode="json")

        return wrapped

    def _planner_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("planner node")
        return planner.run(state)

    def _chemist_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("chemist node")
        state.iteration += 1
        state.append_message(f"graph: starting pass {state.iteration}/{state.max_iterations}")
        self._apply_saturn_gating(state)
        return chemist.run(state)

    def _apply_saturn_gating(self, state: DiscoveryStatePayload) -> None:
        """Config-gate Saturn like xTB/ORCA: drop the oracle if Saturn is off.

        The planner proposes a default Saturn oracle in ``state.metadata``. Here
        the graph enforces the same config/run-mode gate used for other tools.
        When Saturn is disabled for the current run mode, the chemist falls back
        to its deterministic seed molecules instead of generating with Saturn.
        """

        if "saturn" not in state.metadata:
            return
        if self.config.tool_enabled("saturn"):
            return
        state.metadata.pop("saturn", None)
        state.metadata["saturn_source"] = "disabled_by_config"
        state.append_message("graph: Saturn disabled for this run mode; using seed molecules")

    def _tool_execution_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("tool execution node")
        run_dir = _ensure_run_dir(state)

        descriptor_rows: list[dict[str, Any]] = []
        for molecule in state.candidate_molecules:
            if molecule.descriptors.get("qed") is not None:
                descriptor_rows.append(
                    {
                        "name": molecule.name or molecule.smiles,
                        "smiles": molecule.smiles,
                        "mol_wt": molecule.descriptors.get("mol_wt"),
                        "logp": molecule.descriptors.get("logp"),
                        "qed": molecule.descriptors.get("qed"),
                    }
                )
                continue

            validation = validate_smiles(molecule.smiles)
            state.add_tool_result("rdkit.validate_smiles", validation)
            if not validation.ok or not validation.data.get("valid"):
                continue

            descriptors = compute_descriptors(molecule.smiles)
            state.add_tool_result("rdkit.compute_descriptors", descriptors)
            if descriptors.ok:
                molecule.descriptors = descriptors.data
                descriptor_rows.append(
                    {
                        "name": molecule.name or molecule.smiles,
                        "smiles": molecule.smiles,
                        "mol_wt": descriptors.data.get("mol_wt"),
                        "logp": descriptors.data.get("logp"),
                        "qed": descriptors.data.get("qed"),
                    }
                )

        if descriptor_rows:
            csv_result = write_csv(run_dir / "descriptors.csv", descriptor_rows)
            state.add_tool_result("file_io.write_csv", csv_result)
            plot_result = generate_plot(
                {
                    "data": descriptor_rows,
                    "x_key": "name",
                    "y_key": "qed",
                    "output_path": str(run_dir / "qed_plot.png"),
                    "title": "Candidate QED scores",
                    "kind": "bar",
                }
            )
            state.add_tool_result("plotting.generate_plot", plot_result)

        filter_result = filter_molecules(
            [molecule.smiles for molecule in state.candidate_molecules],
            MoleculeFilterConstraints(max_mol_wt=500, max_logp=5.0),
        )
        state.add_tool_result("rdkit.filter_molecules", filter_result)

        if self.config.run_mode != RunMode.NO_DFT:
            if self.config.tool_enabled("xtb"):
                xtb_result = check_xtb_availability(self.config.tools.get("xtb").executable or "xtb")
                state.add_tool_result("xtb.check_availability", xtb_result)
            if self.config.tool_enabled("orca"):
                orca_tool = self.config.tools.get("orca")
                orca_result = check_orca_availability(orca_tool.executable if orca_tool else "orca")
                state.add_tool_result("orca.check_availability", orca_result)
                if state.candidate_molecules:
                    generated = run_orca(
                        {
                            "coordinates": "C 0.0 0.0 0.0\nH 0.0 0.0 1.0\nH 1.0 0.0 0.0\nH 0.0 1.0 0.0",
                            "work_dir": str(run_dir / "orca"),
                            "filename": "example.inp",
                            "executable": orca_tool.executable if orca_tool else "orca",
                            "timeout_seconds": orca_tool.timeout_seconds if orca_tool else 300,
                            "run": bool(orca_result.data.get("available")),
                        }
                    )
                    state.add_tool_result("orca.run_or_generate", generated)

        if self.config.tool_enabled("boltz_2"):
            import hashlib
            from hackathon_agents.tools.boltz_tools import run_boltz_2
            boltz_tool = self.config.tools.get("boltz_2")
            allow_run = boltz_tool.model_extra.get("allow_run", False) if boltz_tool else False
            run_mode_val = boltz_tool.model_extra.get("run_mode", "local") if boltz_tool else "local"
            device_val = boltz_tool.model_extra.get("device", "cpu") if boltz_tool else "cpu"

            target_seq = state.metadata.get("target_protein_sequence") or "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVIDGETCLLDILDTAGQEEYSAMRDQYMRTGEGFLCVFAINNTKSFEDIHQYREQIKRVKDSDDVPMVLVGNKCDLAARTVESRQAQDLARSYGIPYIETSAKTRQGVEDAFYTLVREIRQHKLRKLNPPDESGPGCMSCKCVLS"
            
            # Retrieve agent/metadata driven custom Boltz parameters if present
            recycling_steps = state.metadata.get("boltz_recycling_steps", 3)
            diffusion_steps = state.metadata.get("boltz_diffusion_steps", 200)
            cofactors = state.metadata.get("boltz_cofactors", [])
            pocket_residues = state.metadata.get("boltz_pocket_residues", [])

            state.append_message("graph: running Boltz-2 co-folding on generated candidates")
            for molecule in state.candidate_molecules:
                boltz_result = run_boltz_2(
                    {
                        "id": f"boltz-{hashlib.md5(molecule.smiles.encode('utf-8')).hexdigest()[:8]}",
                        "work_dir": str(run_dir / "boltz"),
                        "target_protein_sequence": target_seq,
                        "ligand_smiles": molecule.smiles,
                        "run": bool(allow_run),
                        "run_mode": run_mode_val,
                        "device": device_val,
                        "recycling_steps": recycling_steps,
                        "diffusion_steps": diffusion_steps,
                        "cofactors": cofactors,
                        "pocket_residues": pocket_residues,
                    }
                )
                state.add_tool_result("boltz_2.run_prediction", boltz_result)
                if boltz_result.ok:
                    molecule.descriptors["boltz_energy"] = boltz_result.data.get("binding_energy_kcal_mol")
                    molecule.descriptors["boltz_kd_nm"] = boltz_result.data.get("binding_affinity_kd_nm")
                    molecule.descriptors["boltz_plddt"] = boltz_result.data.get("plddt")
                    molecule.descriptors["boltz_iptm"] = boltz_result.data.get("iptm")
                    molecule.metadata["boltz_pdb"] = boltz_result.data.get("pdb_file")

        self._maybe_recommend_experiments(state, run_dir)

        return state

    def _maybe_recommend_experiments(self, state: DiscoveryStatePayload, run_dir: Path) -> None:
        """Optionally recommend the next experiments via BayBE (Bayesian DoE).

        Opt-in and config-gated, mirroring Saturn/Boltz. An agent (or chemist)
        requests next-experiment recommendations by setting
        ``state.metadata["baybe"]`` to a dict describing the search space
        (``parameters``), what to optimize (``targets``), the experiments run so
        far (``measurements``), and ``batch_size``. The graph enforces the same
        config/run-mode gate used for the other tools and supplies ``work_dir``
        plus the configured ``allow_run`` flag. When BayBE is disabled or not
        installed, the tool returns deterministic mock recommendations, so this
        is always safe to call.
        """

        settings = state.metadata.get("baybe")
        if not settings:
            return
        if not self.config.tool_enabled("baybe"):
            state.metadata["baybe_source"] = "disabled_by_config"
            state.append_message("graph: BayBE disabled for this run mode; skipping experiment recommendation")
            return

        from hackathon_agents.tools.baybe_tools import recommend_experiments

        baybe_tool = self.config.tools.get("baybe")
        allow_run = baybe_tool.model_extra.get("allow_run", False) if baybe_tool else False

        baybe_input: dict[str, Any] = dict(settings)
        baybe_input.setdefault("objective", state.original_user_request)
        baybe_input.setdefault("work_dir", str(run_dir / "baybe"))
        # The config gate owns the real-vs-mock decision; agents need not know it.
        baybe_input["run"] = bool(allow_run) and bool(settings.get("run", True))

        result = recommend_experiments(baybe_input)
        state.add_tool_result("baybe.recommend_experiments", result)
        if result.ok:
            state.metadata["baybe_recommendations"] = result.data.get("recommendations", [])
            mode_note = "mock" if result.data.get("mock") else result.data.get("recommender")
            state.append_message(
                f"graph: BayBE recommended {len(result.data.get('recommendations', []))} experiments ({mode_note})"
            )

    def _critic_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("critic node")
        return critic.run(state)

    def _writer_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("writer node")
        state = writer.run(state)
        run_dir = _ensure_run_dir(state)
        report_path = run_dir / "report.docx"
        result = write_scientific_report(
            {
                "output_path": str(report_path),
                "user_request": state.original_user_request,
                "plan": state.plan.model_dump(mode="json") if state.plan else None,
                "candidates": [molecule.model_dump(mode="json") for molecule in state.candidate_molecules],
                "tool_results": [record.model_dump(mode="json") for record in state.tool_results],
                "critic_notes": state.critic_notes,
                "errors": state.errors,
            }
        )
        state.add_tool_result("doc_writer.write_scientific_report", result)
        if result.ok:
            state.final_report_path = result.data.get("path")
        return state

    def _route_after_critic(self, raw_state: dict[str, Any]) -> str:
        return self._route_after_critic_state(DiscoveryStatePayload.model_validate(raw_state))

    def _route_after_critic_state(self, state: DiscoveryStatePayload) -> str:
        if state.needs_more_passes and state.iteration < state.max_iterations:
            return "chemist"
        if state.needs_more_passes and state.iteration >= state.max_iterations:
            state.needs_more_passes = False
            state.stop_reason = "max_iterations_reached"
            state.append_message("graph: max_iterations reached; routing to writer")
        return "writer"


def build_graph(config: AppConfig) -> DiscoveryGraph:
    return DiscoveryGraph(config)


def _ensure_run_dir(state: DiscoveryStatePayload) -> Path:
    if not state.run_dir:
        state.run_dir = str(Path("runs") / "adhoc")
    run_dir = Path(state.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
