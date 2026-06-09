from __future__ import annotations

import json
from typing import Iterable

from pydantic import TypeAdapter, ValidationError

from hackathon_agents.mechanism.mechanism_classes import MechanismClass
from hackathon_agents.mechanism.schemas import LiteraturePrior, MechanismHypothesis

_HYPOTHESIS_LIST = TypeAdapter(list[MechanismHypothesis])


def validate_hypothesis_json(raw_json: str, retry_json: str | None = None) -> list[MechanismHypothesis]:
    """Validate hypothesis JSON, retrying once when a second payload is supplied."""

    try:
        return _HYPOTHESIS_LIST.validate_json(raw_json)
    except ValidationError as first_error:
        if retry_json is None:
            raise ValueError(f"invalid hypothesis JSON: {first_error}") from first_error
        try:
            return _HYPOTHESIS_LIST.validate_json(retry_json)
        except ValidationError as second_error:
            raise ValueError(f"invalid hypothesis JSON after retry: {second_error}") from second_error


def generate_hypothesis_json(objective: str, prior: LiteraturePrior | None = None) -> str:
    """Return deterministic JSON for initial mechanism hypotheses.

    This function stands in for an LLM-backed HypothesisAgent.  The graph still
    validates its JSON output with Pydantic before accepting it into state.
    """

    hypotheses = generate_initial_hypotheses(objective=objective, prior=prior)
    return json.dumps([hypothesis.model_dump(mode="json") for hypothesis in hypotheses], indent=2)


def generate_initial_hypotheses(objective: str, prior: LiteraturePrior | None = None) -> list[MechanismHypothesis]:
    """Generate a compact, schema-valid hypothesis set for the objective."""

    objective_lower = objective.lower()
    selected_classes: list[MechanismClass] = [
        MechanismClass.PHOTOREDOX_CATALYTIC_CYCLE,
        MechanismClass.RADICAL_CHAIN,
        MechanismClass.CATALYST_DEACTIVATION,
        MechanismClass.PRODUCT_INHIBITION,
        MechanismClass.MASS_TRANSFER_LIMITED_APPARENT_KINETICS,
    ]
    if "nickel" in objective_lower or "ni" in objective_lower:
        selected_classes[0] = MechanismClass.NICKEL_CATALYTIC_CYCLE
    if "acid" in objective_lower or "base" in objective_lower:
        selected_classes[1] = MechanismClass.ACID_BASE_CATALYSIS
    if "substitution" in objective_lower:
        selected_classes[1] = MechanismClass.NUCLEOPHILIC_SUBSTITUTION

    support = _prior_support(prior)
    return [
        _build_hypothesis(index=index + 1, mechanism_class=mechanism_class, objective=objective, literature_support=support)
        for index, mechanism_class in enumerate(selected_classes)
    ]


def _prior_support(prior: LiteraturePrior | None) -> list[str]:
    if prior is None:
        return []
    support = prior.key_findings[:2]
    if prior.citations:
        support.append(f"Prior citations available: {', '.join(prior.citations[:2])}")
    return support


def _build_hypothesis(
    *,
    index: int,
    mechanism_class: MechanismClass,
    objective: str,
    literature_support: Iterable[str],
) -> MechanismHypothesis:
    species = ["A", "B", "P"]
    common_assumptions = [
        "Kinetic traces are treated as concentration-calibrated and time-aligned.",
        "Claims remain provisional until falsifying controls are run.",
    ]
    class_details = _class_details(mechanism_class)
    return MechanismHypothesis(
        id=f"h-{index:03d}",
        title=f"{mechanism_class.value.title()} hypothesis",
        mechanism_class=mechanism_class,
        species=species + class_details["extra_species"],
        elementary_steps=class_details["steps"],
        rate_law_form=class_details["rate_law"],
        assumptions=common_assumptions + class_details["assumptions"],
        required_observables=class_details["observables"],
        predicted_signatures=class_details["signatures"],
        confidence=0.28 if index <= 2 else 0.18,
        uncertainty=0.72 if index <= 2 else 0.82,
        literature_support=list(literature_support),
        dft_requirements=class_details["dft"],
        falsifying_experiments=class_details["falsifying"],
    )


def _class_details(mechanism_class: MechanismClass) -> dict[str, list[str] | str]:
    details: dict[MechanismClass, dict[str, list[str] | str]] = {
        MechanismClass.PHOTOREDOX_CATALYTIC_CYCLE: {
            "extra_species": ["PC", "PC*", "quencher"],
            "steps": ["photoexcitation of PC", "quenching by substrate or reagent", "radical capture", "catalyst turnover"],
            "rate_law": "rate = k_obs[A]^a[B]^b[PC]^c I_light^d",
            "assumptions": ["Photon flux is stable over the experiment."],
            "observables": ["A", "B", "P", "light_intensity", "catalyst_loading"],
            "signatures": ["rate increases with light intensity", "dark control suppresses product formation"],
            "dft": ["redox potentials for donor and acceptor states"],
            "falsifying": ["run matched dark and illuminated controls", "vary photocatalyst loading at fixed photon flux"],
        },
        MechanismClass.RADICAL_CHAIN: {
            "extra_species": ["R_radical", "inhibitor"],
            "steps": ["initiation", "propagation", "chain transfer", "termination"],
            "rate_law": "rate = k_p[A][B] f(initiation, inhibition)",
            "assumptions": ["Initiation is slow relative to propagation."],
            "observables": ["A", "B", "P", "induction_time"],
            "signatures": ["inhibitor creates induction period", "quantum yield may exceed unity"],
            "dft": ["bond dissociation energies for radical-forming steps"],
            "falsifying": ["add radical trap", "measure rate under varied initiator or photon flux"],
        },
        MechanismClass.NICKEL_CATALYTIC_CYCLE: {
            "extra_species": ["Ni(0)", "Ni(II)", "ligand"],
            "steps": ["oxidative addition", "ligand exchange", "transmetalation", "reductive elimination"],
            "rate_law": "rate = k_cat[A][B][Ni] / (1 + K_L[L])",
            "assumptions": ["Active nickel concentration is proportional to catalyst loading."],
            "observables": ["A", "B", "P", "catalyst_loading", "ligand"],
            "signatures": ["ligand concentration changes apparent order", "catalyst loading affects initial rate"],
            "dft": ["barriers for oxidative addition and reductive elimination"],
            "falsifying": ["vary ligand loading", "run catalyst-loading order experiment"],
        },
        MechanismClass.ACID_BASE_CATALYSIS: {
            "extra_species": ["acid", "base", "conjugate_pair"],
            "steps": ["pre-equilibrium proton transfer", "rate-limiting conversion", "catalyst regeneration"],
            "rate_law": "rate = k[A][B] f([acid], [base])",
            "assumptions": ["Activities are approximated by concentrations."],
            "observables": ["A", "B", "P", "acid", "base"],
            "signatures": ["rate changes with acid or base equivalents", "buffer strength affects apparent rate"],
            "dft": ["relative proton affinities for catalytic intermediates"],
            "falsifying": ["vary acid/base loading at fixed ionic strength"],
        },
        MechanismClass.NUCLEOPHILIC_SUBSTITUTION: {
            "extra_species": ["leaving_group", "nucleophile"],
            "steps": ["nucleophile approach", "leaving group departure", "product formation"],
            "rate_law": "rate = k[A]^a[nucleophile]^b",
            "assumptions": ["Competing elimination is minor in the measured window."],
            "observables": ["A", "nucleophile", "P", "leaving_group"],
            "signatures": ["nucleophile order distinguishes associative character", "leaving group affects rate"],
            "dft": ["transition-state barrier for substitution"],
            "falsifying": ["vary nucleophile concentration", "compare leaving groups"],
        },
        MechanismClass.CATALYST_DEACTIVATION: {
            "extra_species": ["active_catalyst", "inactive_catalyst"],
            "steps": ["productive turnover", "irreversible deactivation"],
            "rate_law": "rate = k_cat[A][cat_active], d[cat_active]/dt = -k_d[cat_active]",
            "assumptions": ["Deactivation is not reversed during the experiment."],
            "observables": ["A", "P", "catalyst_loading", "time_on_stream"],
            "signatures": ["rate declines with cumulative turnover", "fresh catalyst restores rate"],
            "dft": ["stability of likely off-cycle catalyst states"],
            "falsifying": ["restart with fresh catalyst after partial conversion", "vary catalyst age"],
        },
        MechanismClass.PRODUCT_INHIBITION: {
            "extra_species": ["product_bound_catalyst"],
            "steps": ["productive conversion", "reversible product binding"],
            "rate_law": "rate = k[A][B] / (1 + K_i[P])",
            "assumptions": ["Product binding reaches quasi-equilibrium."],
            "observables": ["A", "B", "P", "added_product"],
            "signatures": ["added product lowers initial rate", "late-time rate slows beyond substrate depletion"],
            "dft": ["binding energy of product to catalyst or active site"],
            "falsifying": ["spike product at t=0", "compare initial rates at fixed substrate"],
        },
        MechanismClass.MASS_TRANSFER_LIMITED_APPARENT_KINETICS: {
            "extra_species": ["interfacial_reagent"],
            "steps": ["mixing or transport", "fast intrinsic conversion"],
            "rate_law": "rate_obs = k_transfer a_interfacial driving_force",
            "assumptions": ["Intrinsic chemistry may be faster than measured transport."],
            "observables": ["A", "B", "P", "flow_rate_profile", "mixing_time"],
            "signatures": ["rate depends on flow or mixing geometry", "apparent order changes with residence time"],
            "dft": [],
            "falsifying": ["vary flow rate at fixed residence time", "compare reactor geometries"],
        },
    }
    fallback = {
        "extra_species": [],
        "steps": ["unassigned elementary step"],
        "rate_law": "rate = f(concentrations, time)",
        "assumptions": ["Mechanism class is unresolved."],
        "observables": ["A", "B", "P"],
        "signatures": ["multiple signatures remain compatible with data"],
        "dft": [],
        "falsifying": ["run orthogonal controls for concentration, temperature, and residence time"],
    }
    return details.get(mechanism_class, fallback)
