"""Tests for the multi-warhead ADC campaign: warhead threading + linker filter."""

from __future__ import annotations

from hackathon_agents.agents.critic import _rerender_reinvent
from hackathon_agents.agents.planner import _set_default_adc_linker_objective
from hackathon_agents.demos.adc_campaign import (
    CLEAVABLE_TRIGGERS,
    CONJUGATION_HANDLES,
    _is_assembled_linker,
    _trigger_matcher,
    warhead_pair_smiles,
)
from hackathon_agents.schemas.linkers import ADCGoalProfile, ADCStrategy
from hackathon_agents.state import DiscoveryStatePayload

DBCO_VALCIT = warhead_pair_smiles("DBCO", "Val-Cit-PAB")


def _state_with_pair(pair: str) -> DiscoveryStatePayload:
    return DiscoveryStatePayload(
        original_user_request="Design a protease-cleavable ADC linker",
        run_dir="/tmp/adc",
        max_iterations=3,
        metadata={
            "adc_goal_profile": ADCGoalProfile().model_dump(mode="json"),
            "adc_strategy": ADCStrategy(run_type="sampling").model_dump(mode="json"),
            "adc_warhead_pair": pair,
        },
    )


def test_planner_threads_custom_warhead_pair():
    state = _state_with_pair(DBCO_VALCIT)
    assert _set_default_adc_linker_objective(state) is True
    assert state.metadata["reinvent"]["input_smiles"] == [DBCO_VALCIT]


def test_critic_rerender_preserves_warhead_pair():
    state = _state_with_pair(DBCO_VALCIT)
    _set_default_adc_linker_objective(state)
    state.metadata["adc_strategy"]["run_type"] = "staged_learning"
    _rerender_reinvent(state)
    assert state.metadata["reinvent"]["input_smiles"] == [DBCO_VALCIT]


def test_default_pair_used_when_no_warhead_metadata():
    from hackathon_agents.tools.adc_linker_objective import CANONICAL_WARHEAD_PAIR

    state = DiscoveryStatePayload(
        original_user_request="Design a cleavable ADC linker for maleimide conjugation",
        run_dir="/tmp/adc",
        max_iterations=3,
        metadata={},
    )
    assert _set_default_adc_linker_objective(state) is True
    assert state.metadata["reinvent"]["input_smiles"] == [CANONICAL_WARHEAD_PAIR]


def test_assembled_linker_filter_keeps_real_drops_junk():
    query = _trigger_matcher(CLEAVABLE_TRIGGERS["Val-Cit-PAB"]["smiles"])
    # Assembled maleimide--spacer--Val-Cit-PAB linker (contains PABC benzyl alcohol).
    real = "O=C1C=CC(=O)N1CCC(=O)NC(C(C)C)C(=O)NC(CCCNC(N)=O)C(=O)Nc1ccc(CO)cc1"
    junk = "O=C(O)c1ccc(F)cc1"  # generic seed molecule, not an ADC linker
    assert _is_assembled_linker(real, query) is True
    assert _is_assembled_linker(junk, query) is False


def test_all_default_warheads_are_valid_smiles():
    from rdkit import Chem

    for spec in (*CONJUGATION_HANDLES.values(), *CLEAVABLE_TRIGGERS.values()):
        mol = Chem.MolFromSmiles(spec["smiles"])
        assert mol is not None
        dummies = [a for a in mol.GetAtoms() if a.GetAtomicNum() == 0]
        assert len(dummies) == 1  # exactly one LinkInvent attachment point
