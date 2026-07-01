from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypedDict

from hackathon_agents.agents import chemist, critic, planner, writer
from hackathon_agents.config import AppConfig, RunMode
from hackathon_agents.logging_config import get_logger
from hackathon_agents.schemas.molecules import MoleculeFilterConstraints
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.task_graph import mark_task_completed, mark_task_started, task_graph_summary
from hackathon_agents.tools.doc_writer import write_scientific_report
from hackathon_agents.tools.artifact_index import discovery_provenance, tool_result_artifacts, write_artifact_index
from hackathon_agents.tools.file_io import write_csv
from hackathon_agents.tools.latex_writer import write_latex_report
from hackathon_agents.tools.memory_writer import append_project_memory
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
        self._write_memory(payload, "run_started", "Started a discovery agent run.", node="graph")
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
        state = planner.run(state, config=self.config)
        mark_task_completed(state, "plan", reason="planner node completed", artifacts=["planner_task_graph"])
        step_count = len(state.plan.steps) if state.plan else 0
        self._write_memory(state, "planner_completed", f"Created a discovery plan with {step_count} steps.", node="planner")
        return state

    def _chemist_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("chemist node")
        mark_task_started(state, "generate_candidates", reason=f"pass {state.iteration + 1}")
        state.iteration += 1
        state.append_message(f"graph: starting pass {state.iteration}/{state.max_iterations}")
        self._apply_saturn_gating(state)
        self._apply_reinvent_gating(state)
        state = chemist.run(state, config=self.config)
        mark_task_completed(
            state,
            "generate_candidates",
            reason=f"generated {len(state.candidate_molecules)} candidates on pass {state.iteration}",
            artifacts=["candidate_molecules"],
        )
        self._write_memory(
            state,
            "chemist_completed",
            f"Completed candidate-generation pass {state.iteration} with {len(state.candidate_molecules)} candidates.",
            node="chemist",
        )
        return state

    def _apply_saturn_gating(self, state: DiscoveryStatePayload) -> None:
        """Config-gate Saturn like xTB/ORCA: drop the oracle if Saturn is off.

        The planner proposes a default Saturn oracle in ``state.metadata``. Here
        the graph enforces the same config/run-mode gate used for other tools.
        When Saturn is disabled for the current run mode, the chemist falls back
        to its deterministic seed molecules instead of generating with Saturn.
        """

        if "saturn" not in state.metadata:
            return
        if not self.config.tool_enabled("saturn"):
            state.metadata.pop("saturn", None)
            state.metadata["saturn_source"] = "disabled_by_config"
            state.append_message("graph: Saturn disabled for this run mode; using seed molecules")
            return

        # Saturn is enabled: inject config-derived HPC settings so the chemist can
        # run it as a remote SLURM job on Snellius when configured. Values already
        # present in state.metadata["saturn"] (e.g. set by the planner) win.
        saturn_tool = self.config.tools.get("saturn")
        extra = saturn_tool.model_extra if saturn_tool else {}
        hpc_defaults = {
            "run_mode": extra.get("run_mode", "local"),
            "allow_submit": bool(extra.get("allow_submit", False)),
            "partition": extra.get("partition", "gpu_a100"),
            "gpus_per_node": extra.get("gpus_per_node", 1),
            "time_limit": extra.get("time_limit", "02:00:00"),
            "poll_interval_seconds": extra.get("poll_interval_seconds", 30),
            "saturn_repo": extra.get("saturn_repo") or None,
            "saturn_python": extra.get("saturn_python", "python"),
            "prior_checkpoint": extra.get("prior_checkpoint") or None,
            "remote_saturn_repo": extra.get("remote_saturn_repo") or None,
            "remote_saturn_python": extra.get("remote_saturn_python", "python"),
            "remote_prior_checkpoint": extra.get("remote_prior_checkpoint") or None,
            "env_setup": extra.get("env_setup") or None,
            "timeout_seconds": saturn_tool.timeout_seconds if saturn_tool and saturn_tool.timeout_seconds else 1800,
        }
        settings = state.metadata["saturn"]
        for key, value in hpc_defaults.items():
            settings.setdefault(key, value)

    def _apply_reinvent_gating(self, state: DiscoveryStatePayload) -> None:
        """Config-gate REINVENT4 like Saturn: drop the settings if disabled.

        Unlike Saturn, the planner does not force a default REINVENT run; the
        chemist only invokes REINVENT when ``state.metadata['reinvent']`` is
        present (opt-in). When present and enabled, we inject config-derived
        executable/env/HPC settings so the chemist can run it locally or as a
        remote SLURM job. Values already present in ``state.metadata['reinvent']``
        (e.g. set by the planner) win.
        """

        if "reinvent" not in state.metadata:
            return
        if not self.config.tool_enabled("reinvent"):
            state.metadata.pop("reinvent", None)
            state.metadata["reinvent_source"] = "disabled_by_config"
            state.append_message("graph: REINVENT disabled for this run mode; skipping")
            return

        reinvent_tool = self.config.tools.get("reinvent")
        extra = reinvent_tool.model_extra if reinvent_tool else {}
        config_defaults = {
            "run_mode": extra.get("run_mode", "local"),
            "run_type": extra.get("run_type", "sampling"),
            "device": extra.get("device", "cpu"),
            "reinvent_executable": extra.get("reinvent_executable", "reinvent"),
            "reinvent_python": extra.get("reinvent_python", "python"),
            "prior_base": extra.get("prior_base") or None,
            "allow_submit": bool(extra.get("allow_submit", False)),
            "partition": extra.get("partition", "gpu_a100"),
            "gpus_per_node": extra.get("gpus_per_node", 1),
            "time_limit": extra.get("time_limit", "02:00:00"),
            "poll_interval_seconds": extra.get("poll_interval_seconds", 30),
            "remote_reinvent_executable": extra.get("remote_reinvent_executable", "reinvent"),
            "remote_prior_base": extra.get("remote_prior_base") or None,
            "env_setup": extra.get("env_setup") or None,
            "timeout_seconds": reinvent_tool.timeout_seconds if reinvent_tool and reinvent_tool.timeout_seconds else 1800,
        }
        settings = state.metadata["reinvent"]
        for key, value in config_defaults.items():
            settings.setdefault(key, value)

    def _tool_execution_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("tool execution node")
        mark_task_started(state, "run_deterministic_tools", reason=f"pass {state.iteration}")
        run_dir = _ensure_run_dir(state)
        initial_tool_count = len(state.tool_results)

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
            boltz_extra = boltz_tool.model_extra if boltz_tool else {}
            allow_run = boltz_extra.get("allow_run", False)
            run_mode_val = boltz_extra.get("run_mode", "local")
            device_val = boltz_extra.get("device", "cpu")
            allow_submit_val = bool(boltz_extra.get("allow_submit", False))
            env_setup_val = boltz_extra.get("env_setup") or None
            poll_interval_val = boltz_extra.get("poll_interval_seconds", 30)
            partition_val = boltz_extra.get("partition", "gpu_a100")
            gpus_val = boltz_extra.get("gpus_per_node", 1)
            time_limit_val = boltz_extra.get("time_limit", "01:00:00")
            timeout_val = boltz_tool.timeout_seconds if boltz_tool and boltz_tool.timeout_seconds else 1800

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
                        "allow_submit": allow_submit_val,
                        "env_setup": env_setup_val,
                        "poll_interval_seconds": poll_interval_val,
                        "partition": partition_val,
                        "gpus_per_node": gpus_val,
                        "time_limit": time_limit_val,
                        "timeout_seconds": timeout_val,
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

        executed_count = len(state.tool_results) - initial_tool_count
        produced_artifacts = [
            str(run_dir / "descriptors.csv"),
            str(run_dir / "qed_plot.png"),
        ]
        mark_task_completed(
            state,
            "run_deterministic_tools",
            reason=f"ran {executed_count} tool calls on pass {state.iteration}",
            artifacts=[path for path in produced_artifacts if Path(path).exists()],
        )
        self._write_memory(
            state,
            "tools_completed",
            f"Ran {executed_count} deterministic tool calls for pass {state.iteration}.",
            node="tool_execution",
        )
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
        mark_task_started(state, "critique", reason=f"pass {state.iteration}")
        state = critic.run(state, config=self.config)
        decision = state.critic_decisions[-1] if state.critic_decisions else None
        reason = decision.reason if decision else "Critic completed without a recorded decision."
        mark_task_completed(state, "critique", reason=reason, artifacts=["critic_decisions"])
        self._write_memory(state, "critic_completed", reason, node="critic")
        return state

    def _writer_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("writer node")
        mark_task_started(state, "write_reports", reason="writer node started")
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
        if self.config.tool_enabled("latex_writer"):
            latex_path = run_dir / "report.tex"
            latex_result = write_latex_report(
                {
                    "output_path": str(latex_path),
                    "user_request": state.original_user_request,
                    "plan": state.plan.model_dump(mode="json") if state.plan else None,
                    "candidates": [molecule.model_dump(mode="json") for molecule in state.candidate_molecules],
                    "tool_results": [record.model_dump(mode="json") for record in state.tool_results],
                    "critic_notes": state.critic_notes,
                    "errors": state.errors,
                }
            )
            state.add_tool_result("latex_writer.write_latex_report", latex_result)
            if latex_result.ok:
                state.metadata["latex_report_path"] = latex_result.data.get("path")
        artifacts = [path for path in [state.final_report_path, state.metadata.get("latex_report_path")] if path]
        self._write_memory(
            state,
            "writer_completed",
            "Wrote final report artifacts for the discovery run.",
            node="writer",
            extra_artifacts=artifacts,
        )
        index_path = run_dir / "artifact_index.json"
        state.metadata["artifact_index_path"] = str(index_path)
        mark_task_completed(
            state,
            "write_reports",
            reason="report and artifact index written",
            artifacts=[*artifacts, str(index_path)],
        )
        write_artifact_index(
            run_dir=run_dir,
            producer="discovery_graph",
            artifacts=tool_result_artifacts(state.tool_results),
            provenance=discovery_provenance(state),
            metadata={
                "candidate_count": len(state.candidate_molecules),
                "tool_result_count": len(state.tool_results),
                "critic_decision_count": len(state.critic_decisions),
                "planner_task_graph": state.metadata.get("planner_task_graph"),
                "planner_task_summary": task_graph_summary(state),
            },
        )
        return state

    def _write_memory(
        self,
        state: DiscoveryStatePayload,
        event_type: str,
        summary: str,
        *,
        node: str,
        extra_artifacts: list[str] | None = None,
    ) -> None:
        if state.metadata.get("memory_writer_disabled"):
            return
        if not self.config.tool_enabled("memory_writer"):
            return

        tool_config = self.config.tools.get("memory_writer")
        jsonl_path = (tool_config.jsonl_path if tool_config else None) or "data/memory/project_memory.jsonl"
        markdown_path = (tool_config.markdown_path if tool_config else None) or "data/memory/project_memory.md"
        max_markdown_entries = (tool_config.max_markdown_entries if tool_config else None) or 200
        run_path = Path(state.run_dir) if state.run_dir else None
        result = append_project_memory(
            {
                "event_type": event_type,
                "summary": summary,
                "jsonl_path": jsonl_path,
                "markdown_path": markdown_path,
                "run_id": run_path.name if run_path else None,
                "run_dir": str(run_path) if run_path else None,
                "user_request": state.original_user_request,
                "node": node,
                "iteration": state.iteration,
                "run_mode": state.run_mode.value if hasattr(state.run_mode, "value") else str(state.run_mode),
                "candidate_count": len(state.candidate_molecules),
                "valid_candidate_count": state.metadata.get("valid_candidate_count"),
                "best_score": state.metadata.get("best_score"),
                "stop_reason": state.stop_reason,
                "next_actions": state.requested_next_actions,
                "artifact_paths": _artifact_paths(state, extra_artifacts),
                "recent_messages": state.messages[-5:],
                "metadata": {
                    "critic_note_count": len(state.critic_notes),
                    "error_count": len(state.errors),
                    "tool_result_count": len(state.tool_results),
                    "latest_tools": [record.tool_name for record in state.tool_results[-5:]],
                },
                "max_markdown_entries": max_markdown_entries,
            }
        )
        if result.ok:
            state.metadata["memory_jsonl_path"] = result.data.get("jsonl_path")
            if result.data.get("markdown_path"):
                state.metadata["memory_markdown_path"] = result.data.get("markdown_path")
            state.metadata["memory_event_count"] = int(state.metadata.get("memory_event_count", 0)) + 1
            return

        state.metadata["memory_writer_disabled"] = True
        state.add_error(f"memory_writer.append_project_memory: {result.error}")

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


def _artifact_paths(state: DiscoveryStatePayload, extra_artifacts: list[str] | None = None) -> list[str]:
    paths: list[str] = []
    for record in state.tool_results:
        paths.extend(str(path) for path in record.result.artifacts)
    if state.final_report_path:
        paths.append(state.final_report_path)
    latex_path = state.metadata.get("latex_report_path")
    if latex_path:
        paths.append(str(latex_path))
    if extra_artifacts:
        paths.extend(extra_artifacts)
    return sorted(dict.fromkeys(paths))
