from __future__ import annotations

import ast
import math
import operator
from typing import Any, Literal

from pydantic import BaseModel, Field

from hackathon_agents.tools.base import error_result, ok_result


class ExpressionInput(BaseModel):
    expression: str = Field(..., min_length=1, max_length=1000)
    variables: dict[str, float] = Field(default_factory=dict)


class UnitConversionInput(BaseModel):
    value: float
    from_unit: str
    to_unit: str


class ReactionYieldInput(BaseModel):
    reactants: list[dict[str, float | str]]
    product_molar_mass: float = Field(..., gt=0.0)
    product_mass: float | None = Field(default=None, ge=0.0)
    product_moles: float | None = Field(default=None, ge=0.0)


class ThermochemistryInput(BaseModel):
    mode: Literal["arrhenius_rate", "eyring_rate", "delta_g_from_keq", "keq_from_delta_g"]
    temperature_k: float = Field(default=298.15, gt=0.0)
    activation_energy_kj_mol: float | None = None
    pre_exponential_factor: float | None = None
    delta_g_kj_mol: float | None = None
    equilibrium_constant: float | None = Field(default=None, gt=0.0)


class DilutionInput(BaseModel):
    stock_concentration: float | None = Field(default=None, gt=0.0)
    stock_volume: float | None = Field(default=None, gt=0.0)
    final_concentration: float | None = Field(default=None, gt=0.0)
    final_volume: float | None = Field(default=None, gt=0.0)


class BufferPHInput(BaseModel):
    pka: float
    acid_concentration: float = Field(..., gt=0.0)
    base_concentration: float = Field(..., gt=0.0)


class MassMolesInput(BaseModel):
    molar_mass: float = Field(..., gt=0.0)
    mass: float | None = Field(default=None, ge=0.0)
    moles: float | None = Field(default=None, ge=0.0)


_OPERATORS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Any] = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MATH_NAMES = {
    "acos": math.acos,
    "asin": math.asin,
    "atan": math.atan,
    "ceil": math.ceil,
    "cos": math.cos,
    "e": math.e,
    "exp": math.exp,
    "floor": math.floor,
    "log": math.log,
    "log10": math.log10,
    "pi": math.pi,
    "sin": math.sin,
    "sqrt": math.sqrt,
    "tan": math.tan,
}
_UNIT_FACTORS = {
    "mol": ("amount", 1.0),
    "mmol": ("amount", 1e-3),
    "umol": ("amount", 1e-6),
    "g": ("mass", 1.0),
    "mg": ("mass", 1e-3),
    "ug": ("mass", 1e-6),
    "l": ("volume", 1.0),
    "ml": ("volume", 1e-3),
    "ul": ("volume", 1e-6),
    "s": ("time", 1.0),
    "min": ("time", 60.0),
    "h": ("time", 3600.0),
    "kj/mol": ("energy_molar", 1.0),
    "kcal/mol": ("energy_molar", 4.184),
    "ev": ("energy_molecule", 1.0),
    "hartree": ("energy_molecule", 27.211386245988),
}
_R_KJ = 0.00831446261815324
_BOLTZMANN = 1.380649e-23
_PLANCK = 6.62607015e-34


def calculate_expression(input_data: ExpressionInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, ExpressionInput) else ExpressionInput.model_validate(input_data)
    try:
        tree = ast.parse(parsed.expression, mode="eval")
        value = _eval_node(tree.body, parsed.variables)
        return ok_result({"expression": parsed.expression, "value": float(value), "variables": parsed.variables})
    except Exception as exc:
        return error_result(str(exc), {"expression": parsed.expression})


def convert_units(input_data: UnitConversionInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, UnitConversionInput) else UnitConversionInput.model_validate(input_data)
    try:
        from_unit = _normalize_unit(parsed.from_unit)
        to_unit = _normalize_unit(parsed.to_unit)
        if from_unit not in _UNIT_FACTORS or to_unit not in _UNIT_FACTORS:
            return error_result("Unsupported unit conversion.", {"from_unit": parsed.from_unit, "to_unit": parsed.to_unit})
        from_dimension, from_factor = _UNIT_FACTORS[from_unit]
        to_dimension, to_factor = _UNIT_FACTORS[to_unit]
        if from_dimension != to_dimension:
            return error_result(
                "Cannot convert between incompatible dimensions.",
                {"from_unit": parsed.from_unit, "to_unit": parsed.to_unit},
            )
        converted = parsed.value * from_factor / to_factor
        return ok_result({"value": parsed.value, "from_unit": parsed.from_unit, "converted_value": converted, "to_unit": parsed.to_unit})
    except Exception as exc:
        return error_result(str(exc), {"from_unit": parsed.from_unit, "to_unit": parsed.to_unit})


def calculate_reaction_yield(input_data: ReactionYieldInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, ReactionYieldInput) else ReactionYieldInput.model_validate(input_data)
    try:
        entries = []
        for reactant in parsed.reactants:
            name = str(reactant.get("name", "reactant"))
            moles = float(reactant["moles"])
            coefficient = float(reactant.get("stoichiometric_coefficient", 1.0))
            if moles < 0:
                return error_result("Reactant moles must be non-negative.", {"reactant": name})
            if coefficient <= 0:
                return error_result("Stoichiometric coefficients must be positive.", {"reactant": name})
            equivalents_to_product = moles / coefficient
            entries.append({"name": name, "moles": moles, "stoichiometric_coefficient": coefficient, "equivalents_to_product": equivalents_to_product})
        if not entries:
            return error_result("At least one reactant is required.")
        limiting = min(entries, key=lambda item: item["equivalents_to_product"])
        theoretical_moles = limiting["equivalents_to_product"]
        if theoretical_moles <= 0:
            return error_result("Theoretical product moles must be positive.", {"limiting_reactant": limiting["name"]})
        theoretical_mass = theoretical_moles * parsed.product_molar_mass
        actual_moles = parsed.product_moles
        if actual_moles is None and parsed.product_mass is not None:
            actual_moles = parsed.product_mass / parsed.product_molar_mass
        percent_yield = None if actual_moles is None else 100.0 * actual_moles / theoretical_moles
        return ok_result(
            {
                "limiting_reactant": limiting["name"],
                "theoretical_product_moles": theoretical_moles,
                "theoretical_product_mass": theoretical_mass,
                "actual_product_moles": actual_moles,
                "percent_yield": percent_yield,
                "reactants": entries,
            }
        )
    except Exception as exc:
        return error_result(str(exc))


def thermochemistry(input_data: ThermochemistryInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, ThermochemistryInput) else ThermochemistryInput.model_validate(input_data)
    try:
        if parsed.mode == "arrhenius_rate":
            if parsed.activation_energy_kj_mol is None or parsed.pre_exponential_factor is None:
                return error_result("activation_energy_kj_mol and pre_exponential_factor are required.")
            rate = parsed.pre_exponential_factor * math.exp(-parsed.activation_energy_kj_mol / (_R_KJ * parsed.temperature_k))
            return ok_result({"mode": parsed.mode, "rate_constant": rate, "temperature_k": parsed.temperature_k})
        if parsed.mode == "eyring_rate":
            if parsed.delta_g_kj_mol is None:
                return error_result("delta_g_kj_mol is required.")
            prefactor = (_BOLTZMANN * parsed.temperature_k) / _PLANCK
            rate = prefactor * math.exp(-parsed.delta_g_kj_mol / (_R_KJ * parsed.temperature_k))
            return ok_result({"mode": parsed.mode, "rate_constant": rate, "temperature_k": parsed.temperature_k})
        if parsed.mode == "delta_g_from_keq":
            if parsed.equilibrium_constant is None:
                return error_result("equilibrium_constant is required.")
            delta_g = -_R_KJ * parsed.temperature_k * math.log(parsed.equilibrium_constant)
            return ok_result({"mode": parsed.mode, "delta_g_kj_mol": delta_g, "temperature_k": parsed.temperature_k})
        if parsed.delta_g_kj_mol is None:
            return error_result("delta_g_kj_mol is required.")
        equilibrium_constant = math.exp(-parsed.delta_g_kj_mol / (_R_KJ * parsed.temperature_k))
        return ok_result({"mode": parsed.mode, "equilibrium_constant": equilibrium_constant, "temperature_k": parsed.temperature_k})
    except Exception as exc:
        return error_result(str(exc), {"mode": parsed.mode})


def calculate_dilution(input_data: DilutionInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, DilutionInput) else DilutionInput.model_validate(input_data)
    try:
        values = {
            "stock_concentration": parsed.stock_concentration,
            "stock_volume": parsed.stock_volume,
            "final_concentration": parsed.final_concentration,
            "final_volume": parsed.final_volume,
        }
        missing = [key for key, value in values.items() if value is None]
        if len(missing) != 1:
            return error_result("Provide exactly three of stock_concentration, stock_volume, final_concentration, and final_volume.")
        c1 = parsed.stock_concentration
        v1 = parsed.stock_volume
        c2 = parsed.final_concentration
        v2 = parsed.final_volume
        missing_key = missing[0]
        if missing_key == "stock_concentration":
            assert v1 is not None and c2 is not None and v2 is not None
            values[missing_key] = c2 * v2 / v1
        elif missing_key == "stock_volume":
            assert c1 is not None and c2 is not None and v2 is not None
            values[missing_key] = c2 * v2 / c1
        elif missing_key == "final_concentration":
            assert c1 is not None and v1 is not None and v2 is not None
            values[missing_key] = c1 * v1 / v2
        else:
            assert c1 is not None and v1 is not None and c2 is not None
            values[missing_key] = c1 * v1 / c2
        values["solvent_volume"] = values["final_volume"] - values["stock_volume"]
        if values["solvent_volume"] < 0:
            return error_result("Computed solvent volume is negative; check dilution inputs.", values)
        values["dilution_factor"] = values["stock_concentration"] / values["final_concentration"]
        return ok_result({"solved_for": missing_key, **values})
    except Exception as exc:
        return error_result(str(exc))


def calculate_buffer_ph(input_data: BufferPHInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, BufferPHInput) else BufferPHInput.model_validate(input_data)
    try:
        ph = parsed.pka + math.log10(parsed.base_concentration / parsed.acid_concentration)
        return ok_result(
            {
                "pka": parsed.pka,
                "ph": ph,
                "acid_concentration": parsed.acid_concentration,
                "base_concentration": parsed.base_concentration,
                "base_to_acid_ratio": parsed.base_concentration / parsed.acid_concentration,
            }
        )
    except Exception as exc:
        return error_result(str(exc))


def convert_mass_moles(input_data: MassMolesInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, MassMolesInput) else MassMolesInput.model_validate(input_data)
    try:
        if (parsed.mass is None and parsed.moles is None) or (parsed.mass is not None and parsed.moles is not None):
            return error_result("Provide exactly one of mass or moles.")
        if parsed.mass is None:
            assert parsed.moles is not None
            mass = parsed.moles * parsed.molar_mass
            return ok_result({"molar_mass": parsed.molar_mass, "moles": parsed.moles, "mass": mass})
        moles = parsed.mass / parsed.molar_mass
        return ok_result({"molar_mass": parsed.molar_mass, "mass": parsed.mass, "moles": moles})
    except Exception as exc:
        return error_result(str(exc))


def _eval_node(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in variables:
            return float(variables[node.id])
        if node.id in _MATH_NAMES and isinstance(_MATH_NAMES[node.id], float):
            return float(_MATH_NAMES[node.id])
        raise ValueError(f"Unknown variable: {node.id}")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        if isinstance(node.op, ast.Pow) and abs(right) > 12:
            raise ValueError("Exponent is too large.")
        return float(_OPERATORS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return float(_UNARY_OPERATORS[type(node.op)](_eval_node(node.operand, variables)))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        func = _MATH_NAMES.get(node.func.id)
        if not callable(func):
            raise ValueError(f"Unsupported function: {node.func.id}")
        args = [_eval_node(argument, variables) for argument in node.args]
        return float(func(*args))
    raise ValueError(f"Unsupported expression syntax: {type(node).__name__}")


def _normalize_unit(unit: str) -> str:
    normalized = unit.strip().lower().replace("\u03bc", "u")
    aliases = {"liter": "l", "litre": "l", "grams": "g", "gram": "g", "minutes": "min", "minute": "min"}
    return aliases.get(normalized, normalized)
