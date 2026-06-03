from __future__ import annotations

import importlib.util
import unittest

from hackathon_agents.tools.rdkit_tools import compute_descriptors, filter_molecules, validate_smiles


@unittest.skipUnless(importlib.util.find_spec("rdkit") is not None, "RDKit is not installed")
class RdkitToolTests(unittest.TestCase):
    def test_validate_smiles(self) -> None:
        result = validate_smiles("CCO")
        self.assertTrue(result.ok)
        self.assertTrue(result.data["valid"])

    def test_compute_descriptors(self) -> None:
        result = compute_descriptors("CCO")
        self.assertTrue(result.ok)
        self.assertGreater(result.data["mol_wt"], 40)

    def test_filter_molecules(self) -> None:
        result = filter_molecules(["CCO", "CCCCCCCCCCCCCCCC"], {"max_logp": 3.0})
        self.assertTrue(result.ok)
        self.assertGreaterEqual(len(result.data["kept"]), 1)


if __name__ == "__main__":
    unittest.main()
