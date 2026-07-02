"""Tests for payload-class-aware linker design (Study 2 revision)."""

from __future__ import annotations

from hackathon_agents.demos.adc_grid import GRID_HANDLES, GRID_TRIGGERS, validate_warheads
from hackathon_agents.demos.adc_study2 import build_study2_cells
from hackathon_agents.tools.adc_linker_objective import (
    _effective_cleavage_pref,
    build_adc_linkinvent_objective,
    score_adc_linker,
)
from hackathon_agents.tools.payload_profiles import (
    PAYLOAD_CLASSES,
    derive_payload_rules,
    profile_for_payload,
    resolve_cleavage,
)

# Representative assembled linkers.
CLEAVABLE = "O=C1C=CC(=O)N1CCCCCC(=O)NC(C(C)C)C(=O)NC(CCCNC(N)=O)C(=O)Nc1ccc(CO)cc1"  # mc-Val-Cit-PABC
RIGID_NC = "O=C(O)C1CCC(CN2C(=O)C=CC2=O)CC1"  # MCC (rigid non-cleavable, sulfo-SMCC class)


def test_new_warheads_are_valid_single_attachment_fragments():
    assert validate_warheads() == []
    for name in ("Tetrazine", "TCO"):
        assert name in GRID_HANDLES
    assert "Non-cleavable-rigid" in GRID_TRIGGERS


def test_resolve_cleavage_polarity():
    # Oligonucleotide penalizes cleavage regardless of the trigger.
    assert resolve_cleavage("penalize", True) == "penalize"
    assert resolve_cleavage("penalize", False) == "penalize"
    # Reward payloads reward a cleavable trigger, ignore a non-cleavable one.
    assert resolve_cleavage("reward", True) == "reward"
    assert resolve_cleavage("reward", False) == "ignore"


def test_profile_for_payload_sets_expected_regime():
    # Cytotoxin + cleavable trigger -> reward.
    p = profile_for_payload("cytotoxin", GRID_TRIGGERS["Val-Cit-PABC"])
    assert _effective_cleavage_pref(p) == "reward"
    # Oligonucleotide -> penalize + rigid (tighter rotatable-bond window).
    p = profile_for_payload("oligonucleotide", GRID_TRIGGERS["Val-Cit-PABC"])
    assert _effective_cleavage_pref(p) == "penalize"
    assert p.max_rot_bonds <= 6
    # Immunomodulator -> stability paramount (max weight).
    p = profile_for_payload("immunomodulator", GRID_TRIGGERS["Val-Cit-PABC"])
    assert p.weights["stability"] >= 0.99


def test_oligonucleotide_penalizes_cleavable_linker():
    """The same cleavable linker scores lower under the oligonucleotide rule."""
    prof_cyto = profile_for_payload("cytotoxin", GRID_TRIGGERS["Val-Cit-PABC"])
    prof_oligo = profile_for_payload("oligonucleotide", GRID_TRIGGERS["Val-Cit-PABC"])
    s_cyto, _ = score_adc_linker(CLEAVABLE, prof_cyto)
    s_oligo, _ = score_adc_linker(CLEAVABLE, prof_oligo)
    assert s_cyto is not None and s_oligo is not None
    assert s_oligo < s_cyto  # cleavable motif is a liability for oligonucleotides


def test_oligonucleotide_rewards_non_cleavable_rigid():
    """Under the oligonucleotide rule the rigid non-cleavable cap beats the cleavable one."""
    prof_vc = profile_for_payload("oligonucleotide", GRID_TRIGGERS["Val-Cit-PABC"])
    prof_nc = profile_for_payload("oligonucleotide", GRID_TRIGGERS["Non-cleavable-rigid"])
    s_vc, _ = score_adc_linker(CLEAVABLE, prof_vc)
    s_nc, _ = score_adc_linker(RIGID_NC, prof_nc)
    assert s_nc > s_vc


def test_penalize_objective_emits_custom_alerts_on_cleavable():
    prof = profile_for_payload("oligonucleotide", GRID_TRIGGERS["Val-Cit-PABC"])
    obj = build_adc_linkinvent_objective(prof, run_type="staged_learning")
    names = [c["endpoints"][0]["name"] for c in obj["scoring"]]
    assert any("avoid cleavable" in n for n in names)


def test_reward_objective_still_rewards_cleavable():
    prof = profile_for_payload("cytotoxin", GRID_TRIGGERS["Val-Cit-PABC"])
    obj = build_adc_linkinvent_objective(prof, run_type="staged_learning")
    types = [c["component_type"] for c in obj["scoring"]]
    assert "MatchingSubstructure" in types


def test_glucuronide_relaxes_stability_alert_in_composite():
    prof = profile_for_payload("cytotoxin", GRID_TRIGGERS["Glucuronide"])
    composite, sub = score_adc_linker(
        "O=C1C=CC(=O)N1CCCCCC(=O)Nc1ccc(OC2OC(C(=O)O)C(O)C(O)C2O)cc1CO",
        prof,
    )
    assert composite is not None
    assert sub["stability"] == 0.0
    assert composite > 0.1


def test_derive_payload_rules_are_cited_and_deterministic():
    for payload in PAYLOAD_CLASSES:
        rule = derive_payload_rules(payload)
        assert rule["citation"]
        assert rule["cleavage_preference"] in ("reward", "penalize", "ignore")
        assert rule["mode"] in ("literature-encoded", "llm-derived")


def test_study2_cells_curated_and_deduped():
    cells = build_study2_cells()
    keys = [(c["handle"], c["trigger"], c["payload"]) for c in cells]
    assert len(keys) == len(set(keys))  # no duplicates
    payloads = {c["payload"] for c in cells}
    assert payloads == {"cytotoxin", "oligonucleotide", "immunomodulator"}
    # Both new IEDDA handles appear in the conjugation block.
    handles = {c["handle"] for c in cells}
    assert {"Tetrazine", "TCO"} <= handles


def test_legacy_profile_behaviour_unchanged():
    """A profile without cleavage_preference keeps the pre-payload semantics."""
    from hackathon_agents.schemas.linkers import ADCGoalProfile

    reward = ADCGoalProfile(require_cleavable_motif=True)
    assert _effective_cleavage_pref(reward) == "reward"
    ignore = ADCGoalProfile(require_cleavable_motif=False)
    assert _effective_cleavage_pref(ignore) == "ignore"
