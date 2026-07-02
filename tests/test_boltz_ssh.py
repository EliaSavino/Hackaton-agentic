"""Tests for the Boltz-2 ssh_remote mode + Boltz-2 YAML schema."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hackathon_agents.tools.boltz_tools import (
    BoltzJobInput,
    BoltzRunMode,
    run_boltz_2,
    write_boltz2_yaml_input,
)


def _job(**kw) -> BoltzJobInput:
    base = dict(
        id="t",
        work_dir=tempfile.mkdtemp(prefix="boltz_test_"),
        target_protein_sequence="LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF",
        ligand_smiles="CCO",
        single_sequence=True,
    )
    base.update(kw)
    return BoltzJobInput(**base)


def test_ssh_remote_is_a_run_mode():
    assert BoltzRunMode.SSH_REMOTE.value == "ssh_remote"


def test_boltz2_yaml_schema_has_version_ids_and_affinity():
    job = _job()
    text = write_boltz2_yaml_input(job, Path(job.work_dir), job.id).read_text()
    assert "version: 1" in text
    assert "id: A" in text  # protein chain id
    assert "id: B" in text  # ligand chain id
    assert "msa: empty" in text  # single-sequence mode
    assert "affinity:" in text and "binder: B" in text  # binding prediction on


def test_boltz2_yaml_use_msa_server_when_not_single_sequence():
    job = _job(single_sequence=False)
    text = write_boltz2_yaml_input(job, Path(job.work_dir), job.id).read_text()
    assert "msa: empty" not in text


def test_ssh_remote_dry_run_returns_mock_without_host():
    # run_mode ssh_remote but no ssh_host + run=True -> deterministic mock, no crash.
    job = _job(run_mode="ssh_remote", run=True, ssh_host=None)
    result = run_boltz_2(job)
    assert result.ok is True
    assert result.data["status"] == "mock"
    # deterministic: same inputs -> same predicted energy
    assert run_boltz_2(_job(run_mode="ssh_remote", run=True)).data["binding_energy_kcal_mol"] == (
        result.data["binding_energy_kcal_mol"]
    )
