from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from hackathon_agents.schemas.linkers import (
    LinkerCandidate,
    LinkerDesignRequest,
    LinkerProofPoint,
    LinkerScorecard,
    ReferenceLinkerClass,
)
from hackathon_agents.tools.artifact_index import write_artifact_index
from hackathon_agents.tools.base import error_result, ok_result
from hackathon_agents.tools.rdkit_tools import compute_descriptors


SCORE_WEIGHTS = {
    "plasma_stability": 0.18,
    "tumor_release": 0.20,
    "aqueous_solubility": 0.14,
    "low_aggregation_risk": 0.12,
    "payload_compatibility": 0.14,
    "manufacturability": 0.10,
    "novelty": 0.12,
}


BUILTIN_REFERENCE_LINKERS = [
    {
        "name": "Hydrazone linker",
        "linker_class": "acid-labile cleavable",
        "triggers": ["acidic pH"],
        "conjugation_handles": ["lysine", "hydrazide"],
        "payload_handles": ["aldehyde", "ketone"],
        "release_logic": "Hydrazone hydrolysis accelerates in acidic endosomes and lysosomes.",
        "strengths": ["simple chemistry", "pH responsive"],
        "limitations": ["can hydrolyze in circulation", "limited tunability"],
        "example_adcs": ["gemtuzumab ozogamicin"],
    },
    {
        "name": "Disulfide linker",
        "linker_class": "redox cleavable",
        "triggers": ["reducing environment"],
        "conjugation_handles": ["thiol"],
        "payload_handles": ["thiol", "amine"],
        "release_logic": "Disulfide exchange or reduction releases payload in high-GSH intracellular compartments.",
        "strengths": ["intracellular reducing trigger", "tunable steric shielding"],
        "limitations": ["plasma thiol exchange risk", "bystander release can be hard to tune"],
        "example_adcs": ["maytansinoid ADC linker class"],
    },
    {
        "name": "Val-Cit-PABC linker",
        "linker_class": "protease cleavable self-immolative",
        "triggers": ["lysosomal protease"],
        "conjugation_handles": ["maleimide"],
        "payload_handles": ["amine", "alcohol"],
        "release_logic": "Cathepsin cleavage exposes PABC, then 1,6-elimination releases payload.",
        "strengths": ["clinically precedented", "efficient lysosomal release"],
        "limitations": ["protease heterogeneity", "hydrophobic payload aggregation without solubilizers"],
        "example_adcs": ["brentuximab vedotin", "enfortumab vedotin"],
    },
    {
        "name": "Thioether maleimidocaproyl linker",
        "linker_class": "non-cleavable",
        "triggers": ["antibody degradation"],
        "conjugation_handles": ["maleimide"],
        "payload_handles": ["amine"],
        "release_logic": "Payload is released only after antibody degradation, retaining linker-amino acid adducts.",
        "strengths": ["high plasma stability", "simple manufacturing"],
        "limitations": ["limited bystander effect", "payload must tolerate residual linker adduct"],
        "example_adcs": ["ado-trastuzumab emtansine"],
    },
    {
        "name": "Beta-glucuronide linker",
        "linker_class": "tumor-enzyme cleavable self-immolative",
        "triggers": ["tumor beta-glucuronidase"],
        "conjugation_handles": ["maleimide", "click"],
        "payload_handles": ["amine", "alcohol"],
        "release_logic": "Beta-glucuronidase removes a hydrophilic glucuronide cap, enabling self-immolation.",
        "strengths": ["high hydrophilicity", "tumor enzyme selectivity"],
        "limitations": ["glycoside synthesis complexity", "enzyme expression heterogeneity"],
        "example_adcs": ["glucuronide linker platform examples"],
    },
]


_CANDIDATE_TEMPLATES = [
    {
        "candidate_id": "LNK-001",
        "name": "Dual-lock glucuronide-disulfide sulfo-PEG linker",
        "description": "A hydrophilic linker with an extracellular tumor-enzyme gate plus an intracellular redox gate before PABC self-immolation.",
        "model_fragment_smiles": "O=C(O)C1OC(Oc2ccc(COC(=O)NCCOCCOCCS(=O)(=O)O)cc2)C(O)C(O)C1O",
        "conjugation_handle": "maleimide or strain-promoted azide",
        "payload_handle": "self-immolative carbamate/carbonate",
        "cleavage_triggers": ["tumor beta-glucuronidase", "lysosomal reducing environment"],
        "spacer_modules": ["PEG4", "PABC", "shielded disulfide"],
        "solubilizing_groups": ["glucuronide", "sulfonate", "PEG"],
        "self_immolative_group": "PABC",
        "compatible_payload_classes": ["cytotoxin", "oligonucleotide", "immunomodulator"],
        "likely_release_mechanism": "Beta-glucuronidase removes the hydrophilic gate after tumor uptake; intracellular reduction then exposes a PABC carbonate that self-immolates.",
        "predicted_release_products": ["free amine or phenol payload", "glucuronic acid fragment", "thiol-PEG-PABC remnant"],
        "synthesis_steps": [
            "Assemble sulfo-PEG disulfide spacer.",
            "Install PABC carbonate payload handle.",
            "Glycosylate phenol with protected glucuronide donor.",
            "Deprotect acid/sulfate groups.",
            "Install antibody conjugation handle late.",
        ],
        "novelty_claim": "Combines a tumor-enzyme gate, redox gate, and hydrophilic sulfo-PEG/glucuronide shell in one tunable linker.",
        "assumptions": ["Target tumors have beta-glucuronidase exposure or uptake into glucuronidase-rich compartments."],
        "risks": ["Longer synthesis than vc-PABC", "Dual gating could slow release in enzyme-poor tumors."],
        "descriptors": {"mol_wt_estimate": 690.0, "logp_estimate": -0.9, "tpsa_estimate": 210.0, "formal_charge_estimate": -2},
    },
    {
        "candidate_id": "LNK-002",
        "name": "Zwitterionic Val-Cit-PABC protease linker",
        "description": "A clinically familiar Val-Cit-PABC release motif wrapped in a sulfobetaine spacer to reduce hydrophobic ADC aggregation.",
        "model_fragment_smiles": "CC(C)C(NC(=O)CCC(NC(=O)Cc1ccc(COC(=O)NCC[N+](C)(C)CCS(=O)(=O)[O-])cc1)C(=O)O)C(=O)N",
        "conjugation_handle": "maleimide",
        "payload_handle": "self-immolative carbamate",
        "cleavage_triggers": ["lysosomal protease"],
        "spacer_modules": ["Val-Cit", "PABC", "sulfobetaine"],
        "solubilizing_groups": ["zwitterion", "sulfonate"],
        "self_immolative_group": "PABC",
        "compatible_payload_classes": ["cytotoxin", "immunomodulator"],
        "likely_release_mechanism": "Cathepsin cleavage at Val-Cit triggers PABC 1,6-elimination and payload release.",
        "predicted_release_products": ["free amine payload", "Val-Cit remnant", "quinone methide-derived PABC remnant"],
        "synthesis_steps": [
            "Couple protected Val-Cit dipeptide.",
            "Install PABC carbonate.",
            "Attach sulfobetaine spacer.",
            "Install maleimide conjugation handle.",
        ],
        "novelty_claim": "Keeps the validated Val-Cit-PABC trigger while adding a zwitterionic developability module.",
        "assumptions": ["Cathepsin activity is sufficient after internalization."],
        "risks": ["Protease heterogeneity across tumors", "Maleimide exchange risk unless stabilized."],
        "descriptors": {"mol_wt_estimate": 760.0, "logp_estimate": 0.2, "tpsa_estimate": 240.0, "formal_charge_estimate": 0},
    },
    {
        "candidate_id": "LNK-003",
        "name": "pH-redox tandem hydrazone-disulfide PEG linker",
        "description": "A compact dual-trigger linker that requires acidic endosomal pH and an intracellular reducing environment.",
        "model_fragment_smiles": "COCCOCCNC(=O)NNC(C)=NCCSSCCOC(=O)OCc1ccc(N)cc1",
        "conjugation_handle": "thiol-maleimide",
        "payload_handle": "hydrazone or carbonate",
        "cleavage_triggers": ["acidic pH", "reducing environment"],
        "spacer_modules": ["PEG2", "hydrazone", "shielded disulfide"],
        "solubilizing_groups": ["PEG"],
        "self_immolative_group": "benzyl carbonate",
        "compatible_payload_classes": ["cytotoxin", "immunomodulator"],
        "likely_release_mechanism": "Endosomal acid weakens the hydrazone, then high intracellular thiol concentration cleaves the disulfide to accelerate payload release.",
        "predicted_release_products": ["carbonyl payload or free amine payload", "thiol PEG remnant"],
        "synthesis_steps": [
            "Prepare PEG hydrazide.",
            "Install shielded disulfide spacer.",
            "Condense payload aldehyde/ketone or install carbonate payload handle.",
            "Attach conjugation handle.",
        ],
        "novelty_claim": "Uses two weakly selective cues in series to reduce single-trigger premature release.",
        "assumptions": ["Payload tolerates hydrazone or carbonate derivatization."],
        "risks": ["Hydrazones can hydrolyze in circulation", "Disulfide exchange with serum thiols needs steric tuning."],
        "descriptors": {"mol_wt_estimate": 560.0, "logp_estimate": 1.1, "tpsa_estimate": 125.0, "formal_charge_estimate": 0},
    },
    {
        "candidate_id": "LNK-004",
        "name": "Aryl phosphate PABC PEG linker",
        "description": "A phosphatase-responsive linker for immunomodulators or oligonucleotide conjugates where high aqueous solubility is required.",
        "model_fragment_smiles": "O=P(O)(O)Oc1ccc(COC(=O)NCCOCCOCCN)cc1",
        "conjugation_handle": "strain-promoted azide",
        "payload_handle": "self-immolative carbamate",
        "cleavage_triggers": ["tumor phosphatase", "lysosomal phosphatase"],
        "spacer_modules": ["PEG3", "aryl phosphate", "PABC"],
        "solubilizing_groups": ["phosphate", "PEG"],
        "self_immolative_group": "PABC",
        "compatible_payload_classes": ["oligonucleotide", "immunomodulator", "cytotoxin"],
        "likely_release_mechanism": "Phosphatase cleavage unmasks phenol, then PABC self-immolation releases an amine payload.",
        "predicted_release_products": ["free amine payload", "phosphate", "PABC quinone methide remnant"],
        "synthesis_steps": [
            "Prepare PABC PEG spacer.",
            "Phosphorylate phenol with protected phosphate reagent.",
            "Install payload carbonate.",
            "Install azide or cyclooctyne conjugation handle.",
        ],
        "novelty_claim": "Extends enzyme-cleavable ADC linkers toward highly polar payloads using a phosphate solubility gate.",
        "assumptions": ["The target biology includes phosphatase-rich tumor or lysosomal compartments."],
        "risks": ["Extracellular phosphatases may create background release", "Phosphate protecting group chemistry adds process burden."],
        "descriptors": {"mol_wt_estimate": 520.0, "logp_estimate": -0.4, "tpsa_estimate": 155.0, "formal_charge_estimate": -2},
    },
    {
        "candidate_id": "LNK-005",
        "name": "Charge-reversal dimethylmaleate esterase linker",
        "description": "A masked anionic linker that becomes more cationic and release-prone in acidic/esterase-rich intracellular compartments.",
        "model_fragment_smiles": "COC(=O)C=C(C)C(=O)NCCOCCOCCNC(=O)OCc1ccc(N)cc1",
        "conjugation_handle": "tetrazine or maleimide",
        "payload_handle": "self-immolative carbamate",
        "cleavage_triggers": ["acidic pH", "esterase"],
        "spacer_modules": ["dimethylmaleate", "PEG3", "benzyl carbamate"],
        "solubilizing_groups": ["PEG", "masked carboxylate"],
        "self_immolative_group": "benzyl carbamate",
        "compatible_payload_classes": ["oligonucleotide", "immunomodulator"],
        "likely_release_mechanism": "Acidic pH and esterase activity unmask carboxylates and destabilize the carbamate spacer.",
        "predicted_release_products": ["amine payload", "dimethylmaleate fragment", "benzyl alcohol remnant"],
        "synthesis_steps": [
            "Install PEG spacer.",
            "Add dimethylmaleate charge-reversal module.",
            "Attach payload carbamate.",
            "Add antibody conjugation handle.",
        ],
        "novelty_claim": "Targets nontraditional payload delivery by coupling charge reversal with a standard self-immolative release handle.",
        "assumptions": ["Payload activity tolerates delayed intracellular release."],
        "risks": ["Esterase background differs by tissue", "Charge reversal can alter ADC biodistribution."],
        "descriptors": {"mol_wt_estimate": 610.0, "logp_estimate": 0.8, "tpsa_estimate": 145.0, "formal_charge_estimate": -1},
    },
    {
        "candidate_id": "LNK-006",
        "name": "Hydrophilic triazole thioether non-cleavable control",
        "description": "A stable non-cleavable comparator with PEG and triazole modules for low background release.",
        "model_fragment_smiles": "CCOC(=O)NCCOCCOCCNC(=O)c1ccc(SCC)cc1",
        "conjugation_handle": "azide-alkyne click",
        "payload_handle": "amide",
        "cleavage_triggers": ["antibody degradation"],
        "spacer_modules": ["PEG3", "triazole", "thioether"],
        "solubilizing_groups": ["PEG"],
        "self_immolative_group": None,
        "compatible_payload_classes": ["cytotoxin", "immunomodulator"],
        "likely_release_mechanism": "No designed linker cleavage; payload exposure depends on antibody catabolism.",
        "predicted_release_products": ["payload-linker-amino acid catabolite"],
        "synthesis_steps": [
            "Prepare PEG azide.",
            "Click to alkyne payload handle.",
            "Install antibody reactive group.",
        ],
        "novelty_claim": "Reference-like control for separating release benefits from hydrophilicity benefits.",
        "assumptions": ["Payload remains active as a catabolite."],
        "risks": ["Low bystander effect", "Residual linker may reduce potency."],
        "reference_control": True,
        "descriptors": {"mol_wt_estimate": 430.0, "logp_estimate": 1.6, "tpsa_estimate": 95.0, "formal_charge_estimate": 0},
    },
    {
        "candidate_id": "LNK-007",
        "name": "Val-Cit-PABC maleimide reference control",
        "description": "A clinically precedented protease-cleavable benchmark.",
        "model_fragment_smiles": "CC(C)C(NC(=O)CCC(NC(=O)NCc1ccc(COC(=O)NCC)cc1)C(=O)O)C(=O)N",
        "conjugation_handle": "maleimide",
        "payload_handle": "self-immolative carbamate",
        "cleavage_triggers": ["lysosomal protease"],
        "spacer_modules": ["Val-Cit", "PABC"],
        "solubilizing_groups": [],
        "self_immolative_group": "PABC",
        "compatible_payload_classes": ["cytotoxin", "immunomodulator"],
        "likely_release_mechanism": "Cathepsin cleavage followed by PABC self-immolation.",
        "predicted_release_products": ["free amine payload", "Val-Cit-PABC remnant"],
        "synthesis_steps": ["Couple Val-Cit-PABC", "Install maleimide", "Attach payload carbonate."],
        "novelty_claim": "Comparator, not a novel design.",
        "assumptions": ["Cathepsin-rich lysosomal processing."],
        "risks": ["Hydrophobic ADC aggregation with hydrophobic payloads."],
        "reference_control": True,
        "descriptors": {"mol_wt_estimate": 590.0, "logp_estimate": 1.8, "tpsa_estimate": 165.0, "formal_charge_estimate": 0},
    },
    {
        "candidate_id": "LNK-008",
        "name": "SMCC thioether non-cleavable reference control",
        "description": "A stable non-cleavable maleimide-thioether style control.",
        "model_fragment_smiles": "CCSC(=O)c1ccc(NC(=O)CCCCC(=O)NCCO)cc1",
        "conjugation_handle": "maleimide",
        "payload_handle": "amide",
        "cleavage_triggers": ["antibody degradation"],
        "spacer_modules": ["thioether", "alkyl spacer"],
        "solubilizing_groups": [],
        "self_immolative_group": None,
        "compatible_payload_classes": ["cytotoxin"],
        "likely_release_mechanism": "Antibody catabolism releases a payload-linker catabolite.",
        "predicted_release_products": ["payload-linker-amino acid catabolite"],
        "synthesis_steps": ["Install thioether spacer", "Couple payload amide", "Conjugate through maleimide."],
        "novelty_claim": "Comparator, not a novel design.",
        "assumptions": ["Payload catabolite remains sufficiently active."],
        "risks": ["Limited bystander effect", "Less compatible with payloads requiring traceless release."],
        "reference_control": True,
        "descriptors": {"mol_wt_estimate": 380.0, "logp_estimate": 2.4, "tpsa_estimate": 85.0, "formal_charge_estimate": 0},
    },
]


def load_reference_linker_corpus(path: str | Path | None = None) -> tuple[list[ReferenceLinkerClass], list[str]]:
    warnings: list[str] = []
    if path is None:
        return [ReferenceLinkerClass.model_validate(item) for item in BUILTIN_REFERENCE_LINKERS], warnings

    corpus_path = Path(path)
    if not corpus_path.exists():
        return [], [f"Reference corpus not found: {corpus_path}"]
    try:
        payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [f"Could not parse reference corpus {corpus_path}: {exc}"]

    records = payload.get("linker_classes", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return [], [f"Reference corpus must be a list or contain a linker_classes list: {corpus_path}"]

    references: list[ReferenceLinkerClass] = []
    for index, record in enumerate(records):
        try:
            references.append(ReferenceLinkerClass.model_validate(record))
        except Exception as exc:
            warnings.append(f"Skipped reference record {index}: {exc}")
    return references, warnings


def generate_linker_candidates(request: LinkerDesignRequest | dict[str, Any] | None = None) -> list[LinkerCandidate]:
    parsed = request if isinstance(request, LinkerDesignRequest) else LinkerDesignRequest.model_validate(request or {})
    candidates = [LinkerCandidate.model_validate(item) for item in _CANDIDATE_TEMPLATES]
    if not parsed.include_reference_controls:
        candidates = [candidate for candidate in candidates if not candidate.reference_control]
    return candidates


def score_linker_candidate(
    candidate: LinkerCandidate,
    request: LinkerDesignRequest | dict[str, Any] | None = None,
    references: list[ReferenceLinkerClass] | None = None,
) -> LinkerCandidate:
    parsed = request if isinstance(request, LinkerDesignRequest) else LinkerDesignRequest.model_validate(request or {})
    refs = references if references is not None else load_reference_linker_corpus()[0]
    scored = candidate.model_copy(deep=True)
    _attach_descriptors(scored)

    plasma = _score_plasma_stability(scored)
    release = _score_tumor_release(scored, parsed)
    solubility = _score_solubility(scored)
    aggregation = _score_low_aggregation_risk(scored)
    compatibility = _score_payload_compatibility(scored, parsed)
    manufacturing = _score_manufacturability(scored)
    novelty = _score_novelty(scored, refs)
    overall = _weighted_score(
        {
            "plasma_stability": plasma,
            "tumor_release": release,
            "aqueous_solubility": solubility,
            "low_aggregation_risk": aggregation,
            "payload_compatibility": compatibility,
            "manufacturability": manufacturing,
            "novelty": novelty,
        }
    )

    scored.scorecard = LinkerScorecard(
        plasma_stability=plasma,
        tumor_release=release,
        aqueous_solubility=solubility,
        low_aggregation_risk=aggregation,
        payload_compatibility=compatibility,
        manufacturability=manufacturing,
        novelty=novelty,
        overall=overall,
    )
    scored.proof_points = _build_proof_points(scored, parsed)
    return scored


def design_adc_linkers(tool_input: LinkerDesignRequest | dict[str, Any] | None = None):
    parsed = tool_input if isinstance(tool_input, LinkerDesignRequest) else LinkerDesignRequest.model_validate(tool_input or {})
    references, warnings = load_reference_linker_corpus(parsed.reference_corpus_path)
    if parsed.reference_corpus_path and not references:
        return error_result("No usable ADC linker reference records were loaded.", {"warnings": warnings})
    if not references:
        references = load_reference_linker_corpus()[0]

    candidates = [
        score_linker_candidate(candidate, parsed, references)
        for candidate in generate_linker_candidates(parsed)
    ]
    ranked = sorted(candidates, key=lambda item: item.scorecard.overall if item.scorecard else 0.0, reverse=True)[
        : parsed.max_candidates
    ]

    run_dir = Path(parsed.output_dir) if parsed.output_dir else Path("runs") / f"adc_linker_design_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    artifacts = _write_design_artifacts(run_dir, parsed, ranked, references, warnings)
    index_path = write_artifact_index(
        run_dir=run_dir,
        producer="linker_design",
        artifacts=[
            {"path": path, "producer": "linker_design", "description": "ADC linker design artifact."}
            for path in artifacts
        ],
        metadata={"candidate_count": len(ranked), "reference_count": len(references)},
        provenance={"workflow": "adc_linker_design", "objective": parsed.objective},
    )
    artifacts.append(str(index_path))

    top = ranked[0] if ranked else None
    return ok_result(
        {
            "request": parsed.model_dump(mode="json"),
            "candidate_count": len(ranked),
            "top_candidate": top.model_dump(mode="json") if top else None,
            "candidates": [candidate.model_dump(mode="json") for candidate in ranked],
            "reference_controls": [reference.model_dump(mode="json") for reference in references],
            "warnings": warnings,
            "output_dir": str(run_dir),
            "artifact_paths": artifacts,
        },
        artifacts,
    )


def _attach_descriptors(candidate: LinkerCandidate) -> None:
    rdkit_result = compute_descriptors(candidate.model_fragment_smiles)
    if rdkit_result.ok:
        candidate.descriptors.update(rdkit_result.data)
        candidate.descriptors["descriptor_source"] = "rdkit"
        return
    candidate.descriptors.setdefault("descriptor_source", "heuristic")
    candidate.descriptors.setdefault("descriptor_error", rdkit_result.error)


def _score_plasma_stability(candidate: LinkerCandidate) -> float:
    text = _candidate_text(candidate)
    score = 0.72
    if candidate.reference_control and "non-cleavable" in text:
        score += 0.18
    if "hydrazone" in text:
        score -= 0.14
    if "acetal" in text:
        score -= 0.10
    if "disulfide" in text:
        score -= 0.08
    if "glucuronide" in text or "phosphate" in text:
        score += 0.08
    if "protease" in text or "cathepsin" in text:
        score += 0.04
    if "shielded" in text:
        score += 0.04
    if len(candidate.cleavage_triggers) > 1:
        score -= 0.04
    return _clamp(score)


def _score_tumor_release(candidate: LinkerCandidate, request: LinkerDesignRequest) -> float:
    matched = _count_trigger_matches(candidate.cleavage_triggers, request.desired_triggers)
    score = 0.35 + 0.12 * matched
    if candidate.self_immolative_group:
        score += 0.16
    if len(candidate.cleavage_triggers) > 1:
        score += 0.12
    if "antibody degradation" in _normalized_list(candidate.cleavage_triggers):
        score -= 0.20
    if "tumor" in _candidate_text(candidate) or "lysosomal" in _candidate_text(candidate):
        score += 0.08
    return _clamp(score)


def _score_solubility(candidate: LinkerCandidate) -> float:
    text = _candidate_text(candidate)
    score = 0.42
    for group in candidate.solubilizing_groups:
        normalized = group.lower()
        if "zwitterion" in normalized or "sulfonate" in normalized:
            score += 0.18
        elif "glucuronide" in normalized or "phosphate" in normalized:
            score += 0.16
        elif "peg" in normalized:
            score += 0.10
        elif "carboxylate" in normalized:
            score += 0.08
    logp = _descriptor_float(candidate, "logp", "logp_estimate")
    tpsa = _descriptor_float(candidate, "tpsa", "tpsa_estimate")
    if logp is not None:
        if logp <= 1.5:
            score += 0.10
        elif logp >= 4.0:
            score -= 0.18
    if tpsa is not None and tpsa >= 120:
        score += 0.08
    if "alkyl spacer" in text and not candidate.solubilizing_groups:
        score -= 0.10
    return _clamp(score)


def _score_low_aggregation_risk(candidate: LinkerCandidate) -> float:
    score = 0.55
    logp = _descriptor_float(candidate, "logp", "logp_estimate")
    mol_wt = _descriptor_float(candidate, "mol_wt", "mol_wt_estimate")
    if candidate.solubilizing_groups:
        score += min(0.24, 0.08 * len(candidate.solubilizing_groups))
    if logp is not None:
        if logp <= 1.0:
            score += 0.12
        elif logp >= 3.0:
            score -= 0.18
    if mol_wt is not None and mol_wt >= 800:
        score -= 0.08
    if candidate.reference_control and not candidate.solubilizing_groups:
        score -= 0.10
    return _clamp(score)


def _score_payload_compatibility(candidate: LinkerCandidate, request: LinkerDesignRequest) -> float:
    requested = set(_normalized_list(request.payload_classes))
    supported = set(_normalized_list(candidate.compatible_payload_classes))
    if not requested:
        class_score = 0.65
    else:
        class_score = len(requested & supported) / len(requested)
    handle_text = f"{candidate.payload_handle} {candidate.conjugation_handle}".lower()
    handle_bonus = 0.0
    if "carbamate" in handle_text or "carbonate" in handle_text:
        handle_bonus += 0.10
    if "azide" in handle_text or "click" in handle_text or "tetrazine" in handle_text:
        handle_bonus += 0.08
    if "amide" in handle_text:
        handle_bonus -= 0.06
    requested_handles = _normalized_list(request.conjugation_handles)
    if _matches_any(candidate.conjugation_handle, requested_handles):
        handle_bonus += 0.08
    return _clamp(0.30 + 0.55 * class_score + handle_bonus)


def _score_manufacturability(candidate: LinkerCandidate) -> float:
    score = 0.82 - max(0, len(candidate.synthesis_steps) - 3) * 0.05
    text = _candidate_text(candidate)
    if "glucuronide" in text:
        score -= 0.12
    if "phosphate" in text:
        score -= 0.06
    if "dual" in text or len(candidate.cleavage_triggers) > 1:
        score -= 0.06
    if "maleimide" in text or "val-cit" in text or "pabc" in text:
        score += 0.05
    if candidate.reference_control:
        score += 0.08
    return _clamp(score)


def _score_novelty(candidate: LinkerCandidate, references: list[ReferenceLinkerClass]) -> float:
    if candidate.reference_control:
        return 0.18
    candidate_triggers = set(_normalized_list(candidate.cleavage_triggers))
    exact_like_reference = False
    for reference in references:
        reference_triggers = set(_normalized_list(reference.triggers))
        if candidate_triggers and candidate_triggers == reference_triggers:
            exact_like_reference = True
            break
    score = 0.56 if not exact_like_reference else 0.42
    if len(candidate.cleavage_triggers) > 1:
        score += 0.20
    if len(candidate.solubilizing_groups) >= 2:
        score += 0.10
    if "oligonucleotide" in _normalized_list(candidate.compatible_payload_classes):
        score += 0.08
    return _clamp(score)


def _build_proof_points(candidate: LinkerCandidate, request: LinkerDesignRequest) -> list[LinkerProofPoint]:
    assert candidate.scorecard is not None
    scorecard = candidate.scorecard
    descriptor_source = str(candidate.descriptors.get("descriptor_source", "heuristic"))
    return [
        LinkerProofPoint(
            name="Circulation stability",
            score=scorecard.plasma_stability,
            value=_score_label(scorecard.plasma_stability),
            rationale="Penalizes acid-labile and redox-labile motifs while rewarding enzyme-gated or non-cleavable designs.",
            evidence=[f"Triggers: {', '.join(candidate.cleavage_triggers)}", f"Descriptor source: {descriptor_source}"],
            assumptions=["No serum stability assay is present; this is a structure-rule surrogate."],
        ),
        LinkerProofPoint(
            name="Tumor or lysosomal release",
            score=scorecard.tumor_release,
            value=_score_label(scorecard.tumor_release),
            rationale="Rewards requested tumor triggers, dual gating, and self-immolative release groups.",
            evidence=[
                f"Requested triggers: {', '.join(request.desired_triggers)}",
                f"Release mechanism: {candidate.likely_release_mechanism}",
            ],
            assumptions=["Trigger abundance is inferred from the challenge prompt, not from a tumor dataset."],
        ),
        LinkerProofPoint(
            name="Aqueous solubility",
            score=scorecard.aqueous_solubility,
            value=_score_label(scorecard.aqueous_solubility),
            rationale="Rewards PEG, charged, zwitterionic, glucuronide, phosphate, or sulfonate modules.",
            evidence=[f"Solubilizing groups: {', '.join(candidate.solubilizing_groups) or 'none'}"],
        ),
        LinkerProofPoint(
            name="Low aggregation risk",
            score=scorecard.low_aggregation_risk,
            value=_score_label(scorecard.low_aggregation_risk),
            rationale="Uses hydrophilic modules and model-fragment LogP/TPSA estimates as ADC developability surrogates.",
            evidence=[
                f"LogP estimate: {_descriptor_float(candidate, 'logp', 'logp_estimate')}",
                f"TPSA estimate: {_descriptor_float(candidate, 'tpsa', 'tpsa_estimate')}",
            ],
        ),
        LinkerProofPoint(
            name="Payload compatibility",
            score=scorecard.payload_compatibility,
            value=_score_label(scorecard.payload_compatibility),
            rationale="Checks requested payload classes against supported payload handles and conjugation modes.",
            evidence=[
                f"Compatible payload classes: {', '.join(candidate.compatible_payload_classes)}",
                f"Payload handle: {candidate.payload_handle}",
            ],
        ),
        LinkerProofPoint(
            name="Manufacturability",
            score=scorecard.manufacturability,
            value=_score_label(scorecard.manufacturability),
            rationale="Penalizes long syntheses and glycoside/protected-phosphate complexity while rewarding precedented modules.",
            evidence=[f"Estimated synthesis steps: {len(candidate.synthesis_steps)}"],
        ),
        LinkerProofPoint(
            name="Novelty versus reference classes",
            score=scorecard.novelty,
            value=_score_label(scorecard.novelty),
            rationale=candidate.novelty_claim,
            evidence=[f"Reference control: {candidate.reference_control}"],
        ),
    ]


def _write_design_artifacts(
    run_dir: Path,
    request: LinkerDesignRequest,
    candidates: list[LinkerCandidate],
    references: list[ReferenceLinkerClass],
    warnings: list[str],
) -> list[str]:
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "linker_candidates.json"
    csv_path = run_dir / "linker_rankings.csv"
    report_path = run_dir / "linker_design_report.md"

    payload = {
        "request": request.model_dump(mode="json"),
        "candidate_count": len(candidates),
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "reference_controls": [reference.model_dump(mode="json") for reference in references],
        "warnings": warnings,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "rank",
            "candidate_id",
            "name",
            "overall",
            "plasma_stability",
            "tumor_release",
            "aqueous_solubility",
            "low_aggregation_risk",
            "payload_compatibility",
            "manufacturability",
            "novelty",
            "triggers",
            "payload_classes",
            "reference_control",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rank, candidate in enumerate(candidates, start=1):
            scorecard = candidate.scorecard or LinkerScorecard(
                plasma_stability=0,
                tumor_release=0,
                aqueous_solubility=0,
                low_aggregation_risk=0,
                payload_compatibility=0,
                manufacturability=0,
                novelty=0,
                overall=0,
            )
            writer.writerow(
                {
                    "rank": rank,
                    "candidate_id": candidate.candidate_id,
                    "name": candidate.name,
                    "overall": f"{scorecard.overall:.3f}",
                    "plasma_stability": f"{scorecard.plasma_stability:.3f}",
                    "tumor_release": f"{scorecard.tumor_release:.3f}",
                    "aqueous_solubility": f"{scorecard.aqueous_solubility:.3f}",
                    "low_aggregation_risk": f"{scorecard.low_aggregation_risk:.3f}",
                    "payload_compatibility": f"{scorecard.payload_compatibility:.3f}",
                    "manufacturability": f"{scorecard.manufacturability:.3f}",
                    "novelty": f"{scorecard.novelty:.3f}",
                    "triggers": "; ".join(candidate.cleavage_triggers),
                    "payload_classes": "; ".join(candidate.compatible_payload_classes),
                    "reference_control": candidate.reference_control,
                }
            )

    report_path.write_text(_render_markdown_report(request, candidates, references, warnings), encoding="utf-8")
    return [str(json_path), str(csv_path), str(report_path)]


def _render_markdown_report(
    request: LinkerDesignRequest,
    candidates: list[LinkerCandidate],
    references: list[ReferenceLinkerClass],
    warnings: list[str],
) -> str:
    lines = [
        "# ADC Linker Design Dossier",
        "",
        f"Objective: {request.objective}",
        "",
        "## Ranked Linker Concepts",
        "",
        "| Rank | Candidate | Overall | Triggers | Core proof point |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for rank, candidate in enumerate(candidates, start=1):
        score = candidate.scorecard.overall if candidate.scorecard else 0.0
        top_proof = max(candidate.proof_points, key=lambda point: point.score).name if candidate.proof_points else "not scored"
        lines.append(
            f"| {rank} | {candidate.name} | {score:.3f} | {', '.join(candidate.cleavage_triggers)} | {top_proof} |"
        )

    if candidates:
        top = candidates[0]
        lines.extend(
            [
                "",
                "## Lead Recommendation",
                "",
                f"Lead: {top.name}",
                "",
                top.description,
                "",
                f"Release logic: {top.likely_release_mechanism}",
                "",
                "Proof points:",
            ]
        )
        for proof in top.proof_points:
            lines.append(f"- {proof.name}: {proof.score:.2f} ({proof.rationale})")
        if top.risks:
            lines.extend(["", "Key risks:"])
            lines.extend(f"- {risk}" for risk in top.risks)

    lines.extend(
        [
            "",
            "## Reference Classes Used",
            "",
        ]
    )
    for reference in references:
        lines.append(f"- {reference.name}: {reference.release_logic}")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.append("")
    return "\n".join(lines)


def _weighted_score(scores: dict[str, float]) -> float:
    total = sum(SCORE_WEIGHTS.values())
    return _clamp(sum(scores[name] * weight for name, weight in SCORE_WEIGHTS.items()) / total)


def _count_trigger_matches(candidate_triggers: list[str], requested_triggers: list[str]) -> int:
    count = 0
    for requested in requested_triggers:
        if any(_trigger_matches(trigger, requested) for trigger in candidate_triggers):
            count += 1
    return count


def _trigger_matches(candidate_trigger: str, requested_trigger: str) -> bool:
    candidate = candidate_trigger.lower()
    requested = requested_trigger.lower()
    aliases = {
        "tumor enzyme": ["glucuronidase", "phosphatase", "enzyme", "esterase"],
        "lysosomal protease": ["protease", "cathepsin", "val-cit"],
        "acidic ph": ["acid", "ph", "hydrazone", "acetal"],
        "reducing environment": ["reducing", "redox", "disulfide", "gsh"],
    }
    if requested in candidate or candidate in requested:
        return True
    requested_aliases = aliases.get(requested, [requested])
    return any(alias in candidate for alias in requested_aliases)


def _matches_any(value: str, options: list[str]) -> bool:
    text = value.lower()
    return any(option in text or text in option for option in options)


def _descriptor_float(candidate: LinkerCandidate, *keys: str) -> float | None:
    for key in keys:
        value = candidate.descriptors.get(key)
        try:
            return float(value)  # type: ignore[arg-type]
        except Exception:
            continue
    return None


def _candidate_text(candidate: LinkerCandidate) -> str:
    parts = [
        candidate.name,
        candidate.description,
        candidate.conjugation_handle,
        candidate.payload_handle,
        candidate.likely_release_mechanism,
        " ".join(candidate.cleavage_triggers),
        " ".join(candidate.spacer_modules),
        " ".join(candidate.solubilizing_groups),
    ]
    return " ".join(part for part in parts if part).lower()


def _normalized_list(values: list[str]) -> list[str]:
    return [value.strip().lower() for value in values if value.strip()]


def _score_label(score: float) -> str:
    if score >= 0.80:
        return "strong"
    if score >= 0.62:
        return "moderate"
    if score >= 0.45:
        return "weak-to-moderate"
    return "weak"


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)

