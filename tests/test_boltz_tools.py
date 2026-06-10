from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.tools.boltz_tools import (
    BoltzJobInput,
    BoltzResult,
    check_boltz_availability,
    render_boltz_slurm_script,
    run_boltz_2,
    write_boltz_yaml_input,
)


class BoltzToolTests(unittest.TestCase):
    def test_boltz_result_score_normalisation(self) -> None:
        # Check extremely strong binder
        strong = BoltzResult(
            job_id="test-1",
            status="completed",
            binding_energy_kcal_mol=-16.0,
            binding_affinity_kd_nm=0.1,
            iptm=0.9,
            plddt=95.0,
        )
        self.assertEqual(strong.normalise_score(), 1.0)

        # Check non-binder
        weak = BoltzResult(
            job_id="test-2",
            status="completed",
            binding_energy_kcal_mol=-1.0,
            binding_affinity_kd_nm=1000000.0,
            iptm=0.1,
            plddt=20.0,
        )
        self.assertEqual(weak.normalise_score(), 0.0)

        # Check middle binder (exact interpolation: (-9.0 - (-2.0)) / (-15.0 - (-2.0)) = -7.0 / -13.0 = 0.5385)
        middle = BoltzResult(
            job_id="test-3",
            status="completed",
            binding_energy_kcal_mol=-8.5,
            binding_affinity_kd_nm=500.0,
            iptm=0.6,
            plddt=75.0,
        )
        self.assertAlmostEqual(middle.normalise_score(), 0.5, delta=0.1)

    def test_write_yaml_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            yaml_path = write_boltz_yaml_input(
                work_dir,
                "test-id",
                "MTEYKLVVVG",
                "CCO"
            )
            self.assertTrue(yaml_path.exists())
            text = yaml_path.read_text(encoding="utf-8")
            self.assertIn("id: test-id", text)
            self.assertIn("sequence: MTEYKLVVVG", text)
            self.assertIn("smiles: CCO", text)

    def test_render_slurm_script(self) -> None:
        parsed = BoltzJobInput(
            id="boltz-test-slurm",
            work_dir="unused",
            partition="gpu_h100",
            gpus_per_node=2,
            time_limit="02:30:00",
            single_sequence=True,
            boltz_executable="boltz-test-cmd",
        )
        script = render_boltz_slurm_script(parsed, Path("test_input.yaml"))
        self.assertIn("#SBATCH --job-name=boltz-test-slurm", script)
        self.assertIn("#SBATCH --partition=gpu_h100", script)
        self.assertIn("#SBATCH --gpus-per-node=2", script)
        self.assertIn("#SBATCH --time=02:30:00", script)
        self.assertIn("boltz-test-cmd predict", script)
        self.assertIn("test_input.yaml", script)
        self.assertIn("--outdir output", script)
        self.assertIn("--device cpu", script)

    def test_run_boltz_mock_mode_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inp_1 = {
                "id": "job-1",
                "work_dir": tmp,
                "target_protein_sequence": "MTEYKLVVVGAGGVGKSALTIQLIQN",
                "ligand_smiles": "CC(=O)c1ccccc1",
                "run": False,
            }
            inp_2 = {
                "id": "job-2",
                "work_dir": tmp,
                "target_protein_sequence": "MTEYKLVVVGAGGVGKSALTIQLIQN",
                "ligand_smiles": "CC(=O)c1ccccc1",
                "run": False,
            }
            inp_different = {
                "id": "job-diff",
                "work_dir": tmp,
                "target_protein_sequence": "MTEYKLVVVGAGGVGKSALTIQLIQN",
                "ligand_smiles": "CCN(CC)CC",
                "run": False,
            }

            res1 = run_boltz_2(inp_1)
            res2 = run_boltz_2(inp_2)
            res_diff = run_boltz_2(inp_different)

            self.assertTrue(res1.ok)
            self.assertTrue(res2.ok)
            self.assertTrue(res_diff.ok)

            self.assertEqual(res1.data["status"], "mock")
            # Same sequence + ligand must yield same scores in mock mode
            self.assertEqual(res1.data["binding_energy_kcal_mol"], res2.data["binding_energy_kcal_mol"])
            self.assertEqual(res1.data["binding_affinity_kd_nm"], res2.data["binding_affinity_kd_nm"])

            # Different ligand must yield different mock scores
            self.assertNotEqual(res1.data["binding_energy_kcal_mol"], res_diff.data["binding_energy_kcal_mol"])

            # Verify files were generated
            pdb_path_1 = Path(res1.data["pdb_file"])
            self.assertTrue(pdb_path_1.exists())
            self.assertIn("Mock Boltz-2 complex structure", pdb_path_1.read_text(encoding="utf-8"))

    def test_run_boltz_slurm_dryrun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inp = {
                "id": "job-slurm",
                "work_dir": tmp,
                "run_mode": "slurm",
                "run": False,
            }
            res = run_boltz_2(inp)
            self.assertTrue(res.ok)
            self.assertEqual(res.data["status"], "script_written")
            self.assertIn("job-slurm.slurm", res.data["output_files"][0])
            self.assertTrue(Path(res.data["output_files"][0]).exists())


if __name__ == "__main__":
    unittest.main()
