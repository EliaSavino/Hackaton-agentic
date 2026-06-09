from __future__ import annotations

import unittest

from hackathon_agents.tools.dft_job import DFTCalculationType, DFTJob
from hackathon_agents.tools.hpc_client import MockHPCClient


class MockHPCClientTests(unittest.TestCase):
    def test_hpc_mock_returns_fake_dft_result(self) -> None:
        client = MockHPCClient()
        job = DFTJob(
            id="dft-test",
            molecule_or_structure="H 0 0 0\nH 0 0 0.74",
            charge=0,
            multiplicity=1,
            method="B3LYP",
            basis="def2-SVP",
            solvent_model=None,
            calculation_type=DFTCalculationType.SINGLE_POINT,
            reason_for_calculation="test mock DFT",
            linked_hypothesis_id="h-001",
        )
        job_id = client.submit_job(job)
        self.assertEqual(client.get_status(job_id), "completed")
        result = client.fetch_results(job_id)
        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.energy_hartree)
        self.assertTrue(result.parsed_ok)


if __name__ == "__main__":
    unittest.main()
