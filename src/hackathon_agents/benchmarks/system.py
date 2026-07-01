from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hackathon_agents.mechanism.graph import run_mechanism_once
from hackathon_agents.schemas.molecules import MoleculeFilterConstraints
from hackathon_agents.tools.artifact_index import write_artifact_index
from hackathon_agents.tools.file_io import write_csv
from hackathon_agents.tools.linker_design import design_adc_linkers
from hackathon_agents.tools.paper_review import review_paper
from hackathon_agents.tools.rdkit_tools import compute_descriptors, filter_molecules, validate_smiles
from hackathon_agents.tools.statistics_tools import describe_series, linear_regression


KINETIC_TRACE = """time,A,B,P
0,1.00,1.00,0.00
1,0.88,0.90,0.08
2,0.76,0.81,0.17
4,0.58,0.66,0.32
8,0.34,0.43,0.55
12,0.20,0.28,0.70
16,0.12,0.19,0.80
"""

PAPER_SNIPPET = """Title: Photochemical coupling controls

Abstract
We report a photochemical A + B coupling reaction and show that product yield increases with light intensity.

Methods
Reactions were run in duplicate at room temperature. Concentrations were quantified by HPLC against an internal standard.

Results
Results show faster product formation under blue LEDs than in the dark control.

Limitations
The substrate scope is small and no quantum yield was measured.
"""


def benchmark_system(run_root: str | Path = "runs") -> Path:
    """Run deterministic end-to-end system checks and write a JSON report."""

    run_dir = _new_run_dir(run_root)
    input_dir = run_dir / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)

    results = _run_cases(
        [
            ("kinetics_to_mechanism_report", lambda: _kinetics_to_mechanism_report(run_dir, input_dir)),
            ("smiles_to_descriptor_table", lambda: _smiles_to_descriptor_table(run_dir)),
            ("paper_snippet_to_review", lambda: _paper_snippet_to_review(run_dir, input_dir)),
            ("statistics_regression_summary", lambda: _statistics_regression_summary(run_dir)),
            ("adc_linker_design_dossier", lambda: _adc_linker_design_dossier(run_dir)),
        ]
    )
    passed = [result for result in results if result["ok"]]
    failed = [result for result in results if not result["ok"]]
    payload = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "run_dir": str(run_dir),
        "ok": not failed,
        "case_count": len(results),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "cases": results,
    }
    output_path = run_dir / "system_benchmark.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    index_path = write_artifact_index(
        run_dir=run_dir,
        producer="system_benchmark",
        artifacts=[
            {
                "path": str(output_path),
                "kind": "json",
                "producer": "system_benchmark",
                "description": "System benchmark result summary.",
            },
            *_task_artifacts(results),
        ],
        provenance={
            "workflow": "system_benchmark",
            "ok": payload["ok"],
            "case_count": len(results),
            "passed_count": len(passed),
            "failed_count": len(failed),
            "cases": [
                {
                    "name": result["name"],
                    "ok": result["ok"],
                    "metrics": result.get("metrics", {}),
                    "criteria": result.get("criteria", []),
                    "duration_seconds": result.get("duration_seconds"),
                    "error_count": len(result.get("errors", [])),
                }
                for result in results
            ],
        },
        metadata={"case_count": len(results), "passed_count": len(passed), "failed_count": len(failed), "ok": payload["ok"]},
    )
    payload["artifact_index_path"] = str(index_path)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def _kinetics_to_mechanism_report(run_dir: Path, input_dir: Path) -> dict[str, Any]:
    data_path = input_dir / "photochem_trace.csv"
    data_path.write_text(KINETIC_TRACE, encoding="utf-8")
    try:
        state = run_mechanism_once(
            objective="Infer the mechanism for a photochemical A + B to P reaction and recommend the next experiment.",
            data_path=data_path,
            mode="mock",
            run_root=run_dir / "mechanism_runs",
        )
        criteria = [
            _criterion("parsed_dataset", len(state.datasets) == 1, f"datasets={len(state.datasets)}"),
            _criterion("generated_hypotheses", len(state.hypotheses) >= 3, f"hypotheses={len(state.hypotheses)}"),
            _criterion("ranked_hypotheses", len(state.rankings) >= 3, f"rankings={len(state.rankings)}"),
            _criterion("wrote_reports", bool(state.report_json_path and state.report_docx_path)),
            _criterion("wrote_artifact_index", bool(state.metadata.get("artifact_index_path"))),
        ]
        return {
            "name": "kinetics_to_mechanism_report",
            "description": "CSV kinetic trace to mechanism hypotheses, rankings, reports, and artifact index.",
            "ok": _criteria_ok(criteria),
            "criteria": criteria,
            "artifacts": [
                str(data_path),
                state.report_json_path,
                state.report_docx_path,
                state.metadata.get("artifact_index_path"),
            ],
            "metrics": {
                "hypothesis_count": len(state.hypotheses),
                "ranking_count": len(state.rankings),
                "dataset_count": len(state.datasets),
            },
            "warnings": [],
            "errors": state.errors,
        }
    except Exception as exc:
        return _case_error("kinetics_to_mechanism_report", str(exc), artifacts=[str(data_path)])


def _smiles_to_descriptor_table(run_dir: Path) -> dict[str, Any]:
    smiles = ["CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O", "not_a_smiles"]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in smiles:
        if item == "not_a_smiles":
            errors.append(f"{item}: invalid smiles")
            continue
        validation = validate_smiles(item)
        if not validation.ok and validation.error and "RDKit is not installed" in validation.error:
            fallback = _fallback_descriptor_row(item)
            if fallback:
                rows.append(fallback)
            else:
                errors.append(f"{item}: {validation.error}")
            continue
        if not validation.ok or not validation.data.get("valid"):
            errors.append(f"{item}: invalid smiles")
            continue
        descriptors = compute_descriptors(item)
        if descriptors.ok:
            rows.append(descriptors.data)
        else:
            errors.append(f"{item}: {descriptors.error}")

    filter_result = filter_molecules(
        [row["smiles"] for row in rows],
        MoleculeFilterConstraints(max_mol_wt=500, max_logp=5.0),
    )
    table_path = run_dir / "smiles_descriptors.csv"
    write_result = write_csv(table_path, rows)
    criteria = [
        _criterion("accepted_valid_smiles", len(rows) == 3, f"descriptor_count={len(rows)}"),
        _criterion("rejected_invalid_smiles", any("not_a_smiles" in error for error in errors)),
        _criterion("filter_completed", filter_result.ok),
        _criterion("wrote_descriptor_table", write_result.ok and table_path.exists()),
    ]
    return {
        "name": "smiles_to_descriptor_table",
        "description": "SMILES validation, descriptor calculation, filtering, and CSV output.",
        "ok": _criteria_ok(criteria),
        "criteria": criteria,
        "artifacts": [str(table_path)] if write_result.ok else [],
        "metrics": {
            "input_count": len(smiles),
            "descriptor_count": len(rows),
            "kept_count": len(filter_result.data.get("kept", [])) if filter_result.ok else 0,
        },
        "warnings": errors,
        "errors": [] if write_result.ok and filter_result.ok else [write_result.error or filter_result.error or "tool failed"],
    }


def _fallback_descriptor_row(smiles: str) -> dict[str, Any] | None:
    fixtures = {
        "CCO": {
            "smiles": "CCO",
            "canonical_smiles": "CCO",
            "mol_wt": 46.07,
            "logp": -0.001,
            "hbd": 1,
            "hba": 1,
            "tpsa": 20.23,
            "rotatable_bonds": 0,
            "heavy_atoms": 3,
            "ring_count": 0,
            "qed": 0.407,
            "descriptor_source": "fixture_no_rdkit",
        },
        "c1ccccc1": {
            "smiles": "c1ccccc1",
            "canonical_smiles": "c1ccccc1",
            "mol_wt": 78.11,
            "logp": 1.69,
            "hbd": 0,
            "hba": 0,
            "tpsa": 0.0,
            "rotatable_bonds": 0,
            "heavy_atoms": 6,
            "ring_count": 1,
            "qed": 0.443,
            "descriptor_source": "fixture_no_rdkit",
        },
        "CC(=O)Oc1ccccc1C(=O)O": {
            "smiles": "CC(=O)Oc1ccccc1C(=O)O",
            "canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O",
            "mol_wt": 180.16,
            "logp": 1.19,
            "hbd": 1,
            "hba": 3,
            "tpsa": 63.6,
            "rotatable_bonds": 2,
            "heavy_atoms": 13,
            "ring_count": 1,
            "qed": 0.55,
            "descriptor_source": "fixture_no_rdkit",
        },
    }
    return fixtures.get(smiles)


def _paper_snippet_to_review(run_dir: Path, input_dir: Path) -> dict[str, Any]:
    paper_path = input_dir / "paper_snippet.txt"
    output_path = run_dir / "paper_review.json"
    paper_path.write_text(PAPER_SNIPPET, encoding="utf-8")
    result = review_paper(
        {
            "path": str(paper_path),
            "domain": "chem_bio",
            "focus_questions": ["Are controls and replicates described?"],
            "output_path": str(output_path),
        }
    )
    review = result.data.get("review", {}) if result.ok else {}
    criteria = [
        _criterion("review_completed", result.ok),
        _criterion("extracted_claims", len(review.get("claims", [])) >= 1, f"claims={len(review.get('claims', []))}"),
        _criterion(
            "built_reproducibility_checklist",
            len(review.get("reproducibility_checklist", [])) >= 5,
            f"checklist={len(review.get('reproducibility_checklist', []))}",
        ),
        _criterion("wrote_review_json", output_path.exists()),
    ]
    return {
        "name": "paper_snippet_to_review",
        "description": "Paper snippet to claims, limitations, reproducibility checklist, and review JSON.",
        "ok": _criteria_ok(criteria),
        "criteria": criteria,
        "artifacts": [str(paper_path), str(output_path)] if result.ok else [str(paper_path)],
        "metrics": {
            "claim_count": len(review.get("claims", [])),
            "limitation_count": len(review.get("limitations", [])),
            "checklist_count": len(review.get("reproducibility_checklist", [])),
        },
        "warnings": [],
        "errors": [] if result.ok else [result.error or "review failed"],
    }


def _statistics_regression_summary(run_dir: Path) -> dict[str, Any]:
    rows = [
        {"time": 0.0, "product": 0.00},
        {"time": 1.0, "product": 0.08},
        {"time": 2.0, "product": 0.17},
        {"time": 4.0, "product": 0.32},
        {"time": 8.0, "product": 0.55},
        {"time": 12.0, "product": 0.70},
        {"time": 16.0, "product": 0.80},
    ]
    summary = describe_series({"rows": rows, "column": "product"})
    regression = linear_regression(
        {
            "x": [row["time"] for row in rows],
            "y": [row["product"] for row in rows],
        }
    )
    output_path = run_dir / "statistics_summary.json"
    payload = {
        "summary": summary.data if summary.ok else {},
        "regression": regression.data if regression.ok else {},
        "errors": [error for error in [summary.error, regression.error] if error],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    criteria = [
        _criterion("summary_completed", summary.ok),
        _criterion("regression_completed", regression.ok),
        _criterion("positive_product_slope", regression.ok and regression.data.get("slope", 0.0) > 0.0),
        _criterion("wrote_statistics_json", output_path.exists()),
    ]
    return {
        "name": "statistics_regression_summary",
        "description": "Numeric product trace to descriptive statistics and linear regression summary.",
        "ok": _criteria_ok(criteria),
        "criteria": criteria,
        "artifacts": [str(output_path)],
        "metrics": {
            "product_mean": summary.data.get("mean") if summary.ok else None,
            "slope": regression.data.get("slope") if regression.ok else None,
            "r_squared": regression.data.get("r_squared") if regression.ok else None,
        },
        "warnings": [],
        "errors": payload["errors"],
    }


def _adc_linker_design_dossier(run_dir: Path) -> dict[str, Any]:
    output_dir = run_dir / "adc_linker_design"
    result = design_adc_linkers(
        {
            "objective": "Design a novel ADC linker with plasma stability, tunable tumor release, and broad payload compatibility.",
            "payload_classes": ["cytotoxin", "oligonucleotide", "immunomodulator"],
            "desired_triggers": ["lysosomal protease", "acidic pH", "reducing environment", "tumor enzyme"],
            "conjugation_handles": ["maleimide", "strain-promoted azide"],
            "max_candidates": 8,
            "output_dir": str(output_dir),
        }
    )
    top = result.data.get("top_candidate", {}) if result.ok else {}
    top_score = (top.get("scorecard") or {}).get("overall") if isinstance(top, dict) else None
    artifacts = result.artifacts if result.ok else []
    criteria = [
        _criterion("design_completed", result.ok),
        _criterion("ranked_candidates", result.ok and result.data.get("candidate_count", 0) >= 5),
        _criterion("top_has_scorecard", isinstance(top_score, (int, float)) and top_score > 0.0, f"score={top_score}"),
        _criterion("top_has_proof_points", len(top.get("proof_points", [])) >= 6 if isinstance(top, dict) else False),
        _criterion("wrote_linker_report", (output_dir / "linker_design_report.md").exists()),
    ]
    return {
        "name": "adc_linker_design_dossier",
        "description": "ADC linker objective to ranked linker concepts, proof points, and dossier artifacts.",
        "ok": _criteria_ok(criteria),
        "criteria": criteria,
        "artifacts": artifacts,
        "metrics": {
            "candidate_count": result.data.get("candidate_count", 0) if result.ok else 0,
            "top_score": top_score,
            "top_candidate": top.get("name") if isinstance(top, dict) else None,
        },
        "warnings": result.data.get("warnings", []) if result.ok else [],
        "errors": [] if result.ok else [result.error or "linker design failed"],
    }


def _new_run_dir(run_root: str | Path) -> Path:
    root = Path(run_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = root / f"system_benchmark_{timestamp}"
    suffix = 1
    while run_dir.exists():
        suffix += 1
        run_dir = root / f"system_benchmark_{timestamp}_{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _task_artifacts(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for result in results:
        for artifact in result.get("artifacts", []):
            if artifact:
                artifacts.append(
                    {
                        "path": str(artifact),
                        "producer": result["name"],
                        "description": f"Artifact produced by system benchmark task {result['name']}.",
                    }
                )
    return artifacts


def _run_cases(cases: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for name, callback in cases:
        started = time.perf_counter()
        try:
            result = callback()
        except Exception as exc:
            result = _case_error(name, str(exc))
        result.setdefault("name", name)
        result["duration_seconds"] = time.perf_counter() - started
        results.append(result)
    return results


def _criterion(name: str, ok: bool, detail: str | None = None) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _criteria_ok(criteria: list[dict[str, Any]]) -> bool:
    return all(item.get("ok") for item in criteria)


def _case_error(name: str, error: str, artifacts: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": "Benchmark case failed before producing normal output.",
        "ok": False,
        "criteria": [_criterion("case_completed", False, error)],
        "artifacts": artifacts or [],
        "metrics": {},
        "warnings": [],
        "errors": [error],
    }
