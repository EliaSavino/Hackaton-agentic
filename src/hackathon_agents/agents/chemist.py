from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

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
        state.candidate_molecules = [candidate.model_copy(deep=True) for candidate in EXAMPLE_MOLECULES]
        state.append_message("chemist: loaded hardcoded example molecules")
    elif state.requested_next_actions:
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
