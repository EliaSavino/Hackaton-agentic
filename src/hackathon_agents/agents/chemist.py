from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.state import DiscoveryStatePayload


EXAMPLE_MOLECULES = [
    MoleculeRecord(smiles="CCOC(=O)c1ccccc1", name="ethyl benzoate", source="example_seed"),
    MoleculeRecord(smiles="COc1ccc(C=O)cc1", name="p-anisaldehyde", source="example_seed"),
    MoleculeRecord(smiles="CC(=O)c1ccccc1", name="acetophenone", source="example_seed"),
    MoleculeRecord(smiles="O=C(O)c1ccccc1", name="benzoic acid", source="example_seed"),
    MoleculeRecord(smiles="CCN(CC)CC", name="triethylamine", source="example_seed"),
]

REFINEMENT_MOLECULES = [
    MoleculeRecord(smiles="CCOC(=O)c1ccc(F)cc1", name="ethyl 4-fluorobenzoate", source="refinement_seed"),
    MoleculeRecord(smiles="COc1ccc(C#N)cc1", name="4-methoxybenzonitrile", source="refinement_seed"),
    MoleculeRecord(smiles="CC(=O)c1ccc(Cl)cc1", name="4-chloroacetophenone", source="refinement_seed"),
    MoleculeRecord(smiles="O=C(O)c1ccc(F)cc1", name="4-fluorobenzoic acid", source="refinement_seed"),
    MoleculeRecord(smiles="CN(C)c1ccccc1", name="N,N-dimethylaniline", source="refinement_seed"),
]


def run(state: DiscoveryStatePayload) -> DiscoveryStatePayload:
    if not state.candidate_molecules:
        saturn_added = _maybe_generate_with_saturn(state)
        if saturn_added:
            state.append_message(f"chemist: seeded {saturn_added} candidates with Saturn")
        else:
            state.candidate_molecules = [candidate.model_copy(deep=True) for candidate in EXAMPLE_MOLECULES]
            state.append_message("chemist: loaded hardcoded example molecules")
    elif state.requested_next_actions:
        saturn_added = _maybe_generate_with_saturn(state)
        if saturn_added:
            state.append_message(f"chemist: refined and generated {saturn_added} candidates using Saturn warm start")
        else:
            added = _add_refinement_candidates(state)
            state.append_message(
                f"chemist: added {added} refinement candidates for actions {state.requested_next_actions}"
            )
    else:
        state.append_message("chemist: using candidate molecules already present in state")
    state.needs_more_passes = False
    return state


def generate_parallel_hypotheses(
    request: str,
    count: int = 50,
    workers: int = 5,
    model_alias: str = "local_large",
) -> list[MoleculeRecord]:
    """Bounded local-agent fanout hook for cheap molecule ideation.

    The default implementation is deterministic and testable. A hackathon team can
    swap the worker body for an LLM call through LLMClient while preserving the
    same aggregation contract.
    """

    bounded_count = max(1, min(count, 500))
    bounded_workers = max(1, min(workers, 32))
    hypotheses: list[MoleculeRecord] = []

    with ThreadPoolExecutor(max_workers=bounded_workers) as executor:
        futures = [
            executor.submit(_deterministic_hypothesis, request, index, model_alias)
            for index in range(bounded_count)
        ]
        for future in as_completed(futures):
            hypotheses.append(future.result())

    return sorted(hypotheses, key=lambda item: item.name or item.smiles)


def _deterministic_hypothesis(request: str, index: int, model_alias: str) -> MoleculeRecord:
    seed = EXAMPLE_MOLECULES[index % len(EXAMPLE_MOLECULES)]
    return MoleculeRecord(
        smiles=seed.smiles,
        name=f"{seed.name or 'candidate'} hypothesis {index + 1}",
        source=f"parallel_{model_alias}",
        notes=[f"Generated for request: {request[:120]}"],
        metadata={"hypothesis_index": index, "model_alias": model_alias},
    )


def _add_refinement_candidates(state: DiscoveryStatePayload) -> int:
    existing_smiles = {candidate.smiles for candidate in state.candidate_molecules}
    added = 0
    for candidate in REFINEMENT_MOLECULES:
        if candidate.smiles in existing_smiles:
            continue
        refined = candidate.model_copy(deep=True)
        refined.source = f"refinement_pass_{state.iteration}"
        refined.notes.append("; ".join(state.requested_next_actions))
        state.candidate_molecules.append(refined)
        existing_smiles.add(refined.smiles)
        added += 1
    return added


def _maybe_generate_with_saturn(state: DiscoveryStatePayload) -> int:
    """Optionally seed candidates via the Saturn generative tool.

    The chemist opts in by setting ``state.metadata["saturn"]`` to a dict of
    Saturn settings (oracle components, RL knobs, repo paths, ``run`` flag).
    Without that key the chemist keeps its deterministic default behavior. The
    Saturn tool itself falls back to a mock generator when Saturn is not
    installed, so this is always safe to call.
    """

    settings = state.metadata.get("saturn")
    if not settings:
        return 0

    # Imported lazily so the agent has no hard dependency on the tool module.
    from hackathon_agents.tools.saturn_tools import generate_with_saturn, saturn_records

    saturn_input: dict[str, Any] = dict(settings)
    saturn_input.setdefault("objective", state.original_user_request)
    if "work_dir" not in saturn_input:
        run_dir = Path(state.run_dir) if state.run_dir else Path("runs") / "adhoc"
        saturn_input["work_dir"] = str(run_dir / "saturn")

    # Pass existing candidates as seed_smiles for warm starting experience replay
    if state.candidate_molecules:
        existing_smiles = [mol.smiles for mol in state.candidate_molecules if mol.smiles]
        if existing_smiles:
            saturn_input["seed_smiles"] = existing_smiles
            state.append_message(f"chemist: warm-starting Saturn experience replay memory with {len(existing_smiles)} active candidates")

    result = generate_with_saturn(saturn_input)
    state.add_tool_result("saturn.generate", result)
    if not result.ok:
        return 0

    molecules = saturn_records(result.data)
    state.candidate_molecules = molecules
    if result.data.get("mock"):
        state.append_message("chemist: Saturn ran in mock mode (Saturn not installed or run disabled)")
    return len(molecules)
