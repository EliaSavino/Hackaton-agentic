from __future__ import annotations

import unittest

from hackathon_agents.tools.calculation_tools import (
    calculate_buffer_ph,
    calculate_dilution,
    calculate_expression,
    calculate_reaction_yield,
    convert_mass_moles,
    convert_units,
    thermochemistry,
)


class CalculationToolsTests(unittest.TestCase):
    def test_calculate_expression_allows_math_and_variables(self) -> None:
        result = calculate_expression({"expression": "sin(pi / 2) + x * 2", "variables": {"x": 3}})

        self.assertTrue(result.ok, result.error)
        self.assertAlmostEqual(result.data["value"], 7.0)

    def test_convert_units_rejects_incompatible_dimensions(self) -> None:
        result = convert_units({"value": 5, "from_unit": "mg", "to_unit": "g"})
        self.assertTrue(result.ok, result.error)
        self.assertAlmostEqual(result.data["converted_value"], 0.005)

        incompatible = convert_units({"value": 5, "from_unit": "mg", "to_unit": "ml"})
        self.assertFalse(incompatible.ok)

    def test_calculate_reaction_yield_finds_limiting_reactant(self) -> None:
        result = calculate_reaction_yield(
            {
                "reactants": [
                    {"name": "A", "moles": 0.010, "stoichiometric_coefficient": 1},
                    {"name": "B", "moles": 0.005, "stoichiometric_coefficient": 1},
                ],
                "product_molar_mass": 100.0,
                "product_mass": 0.25,
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["limiting_reactant"], "B")
        self.assertAlmostEqual(result.data["percent_yield"], 50.0)

    def test_thermochemistry_converts_delta_g_to_keq(self) -> None:
        result = thermochemistry({"mode": "keq_from_delta_g", "delta_g_kj_mol": 0.0})

        self.assertTrue(result.ok, result.error)
        self.assertAlmostEqual(result.data["equilibrium_constant"], 1.0)

    def test_calculate_dilution_solves_missing_stock_volume(self) -> None:
        result = calculate_dilution(
            {
                "stock_concentration": 10.0,
                "final_concentration": 1.0,
                "final_volume": 100.0,
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["solved_for"], "stock_volume")
        self.assertAlmostEqual(result.data["stock_volume"], 10.0)
        self.assertAlmostEqual(result.data["solvent_volume"], 90.0)

    def test_calculate_buffer_ph_uses_henderson_hasselbalch(self) -> None:
        result = calculate_buffer_ph({"pka": 7.2, "acid_concentration": 0.1, "base_concentration": 0.1})

        self.assertTrue(result.ok, result.error)
        self.assertAlmostEqual(result.data["ph"], 7.2)

    def test_convert_mass_moles(self) -> None:
        result = convert_mass_moles({"molar_mass": 180.0, "moles": 0.01})

        self.assertTrue(result.ok, result.error)
        self.assertAlmostEqual(result.data["mass"], 1.8)


if __name__ == "__main__":
    unittest.main()
