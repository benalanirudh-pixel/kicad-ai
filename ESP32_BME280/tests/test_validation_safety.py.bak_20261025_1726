#!/usr/bin/env python3
"""
Tests for run_validation() safety: active project files must never be
modified during validation. Uses Python standard unittest only.
"""

import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

AI_DIR = r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280\scripts\ai"
if AI_DIR not in sys.path:
    sys.path.insert(0, AI_DIR)

import ai_pipeline

STAGING_SCH = Path(
    r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280"
    r"\outputs\ai_staging\20261025_201832\ESP32_BME280.kicad_sch"
)
STAGING_PCB = Path(
    r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280"
    r"\outputs\ai_staging\20261025_201832\ESP32_BME280.kicad_pcb"
)


def file_hash(path: Path):
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestValidationSafety(unittest.TestCase):
    """Active schematic/PCB must never be write targets during validation."""

    def setUp(self):
        self.sch_hash_before = file_hash(ai_pipeline.SCH_FILE)
        self.pcb_hash_before = file_hash(ai_pipeline.PCB_FILE)

    def tearDown(self):
        # Confirm active files unchanged after every test.
        self.assertEqual(
            self.sch_hash_before,
            file_hash(ai_pipeline.SCH_FILE),
            "Active schematic hash changed during test",
        )
        self.assertEqual(
            self.pcb_hash_before,
            file_hash(ai_pipeline.PCB_FILE),
            "Active PCB hash changed during test",
        )
        # Clean up the staging-validation report directory created during tests.
        # This directory is created by run_validation itself; no pre-existing
        # user files live here.
        import shutil
        sv_dir = ai_pipeline.PROJECT_ROOT / "outputs" / "ai_staging_validation"
        if sv_dir.exists():
            shutil.rmtree(sv_dir, ignore_errors=True)

    # --- Test 1: hashes unchanged after successful validation ---

    @patch.object(ai_pipeline, "run_powershell")
    @patch.object(ai_pipeline.Path, "exists", return_value=True)
    def test_hashes_unchanged_after_successful_validation(self, mock_exists, mock_run):
        mock_run.return_value = {
            "stdout": "PASS",
            "stderr": "",
            "returncode": 0,
        }
        with patch.object(
            ai_pipeline, "_parse_erc_report",
            return_value={"parseable": True, "errors": 0, "warnings": 0},
        ), patch.object(
            ai_pipeline, "_parse_drc_report",
            return_value={"parseable": True, "violations": 0, "unconnected": 0, "footprint_errors": 0},
        ):
            result = ai_pipeline.run_validation(STAGING_SCH, STAGING_PCB)
        self.assertTrue(result["clean"])
        self.assertEqual(result["returncode"], 0)

    # --- Test 2: hashes unchanged if validation fails ---

    @patch.object(ai_pipeline, "run_powershell")
    @patch.object(ai_pipeline.Path, "exists", return_value=True)
    def test_hashes_unchanged_on_validation_failure(self, mock_exists, mock_run):
        mock_run.return_value = {
            "stdout": "FAIL",
            "stderr": "violations found",
            "returncode": 1,
        }
        with patch.object(
            ai_pipeline, "_parse_erc_report",
            return_value={"parseable": True, "errors": 5, "warnings": 0},
        ), patch.object(
            ai_pipeline, "_parse_drc_report",
            return_value={"parseable": True, "violations": 3, "unconnected": 0, "footprint_errors": 0},
        ):
            result = ai_pipeline.run_validation(STAGING_SCH, STAGING_PCB)
        self.assertFalse(result["clean"])
        self.assertEqual(result["returncode"], 1)

    # --- Test 3: hashes unchanged if validator raises exception ---

    @patch.object(ai_pipeline, "run_powershell")
    @patch.object(ai_pipeline.Path, "exists", return_value=True)
    def test_hashes_unchanged_on_validator_exception(self, mock_exists, mock_run):
        mock_run.side_effect = RuntimeError("Validator process crashed")
        with patch.object(
            ai_pipeline, "_parse_erc_report",
            return_value={"parseable": True, "errors": 0, "warnings": 0},
        ), patch.object(
            ai_pipeline, "_parse_drc_report",
            return_value={"parseable": True, "violations": 0, "unconnected": 0, "footprint_errors": 0},
        ):
            with self.assertRaises(RuntimeError):
                ai_pipeline.run_validation(STAGING_SCH, STAGING_PCB)

    # --- Test 4: validation receives staging design, not active blank ---

    @patch.object(ai_pipeline, "run_powershell")
    @patch.object(ai_pipeline.Path, "exists", return_value=True)
    def test_validation_receives_staging_not_active(self, mock_exists, mock_run):
        mock_run.return_value = {
            "stdout": "PASS",
            "stderr": "",
            "returncode": 0,
        }
        with patch.object(
            ai_pipeline, "_parse_erc_report",
            return_value={"parseable": True, "errors": 0, "warnings": 0},
        ), patch.object(
            ai_pipeline, "_parse_drc_report",
            return_value={"parseable": True, "violations": 0, "unconnected": 0, "footprint_errors": 0},
        ):
            ai_pipeline.run_validation(STAGING_SCH, STAGING_PCB)

        call_args = mock_run.call_args
        args_list = call_args[0][1]
        self.assertIn("-ProjectDir", args_list)
        idx = args_list.index("-ProjectDir")
        project_dir_arg = args_list[idx + 1]
        # Must be a temp workspace, not the active project root.
        self.assertNotEqual(project_dir_arg, str(ai_pipeline.PROJECT_ROOT))
        self.assertIn("kicad_val_", project_dir_arg)

    # --- Test 5: reports written to isolated location ---

    @patch.object(ai_pipeline, "run_powershell")
    @patch.object(ai_pipeline.Path, "exists", return_value=True)
    def test_reports_written_to_isolated_location(self, mock_exists, mock_run):
        mock_run.return_value = {
            "stdout": "PASS",
            "stderr": "",
            "returncode": 0,
        }
        with patch.object(
            ai_pipeline, "_parse_erc_report",
            return_value={"parseable": True, "errors": 0, "warnings": 0},
        ), patch.object(
            ai_pipeline, "_parse_drc_report",
            return_value={"parseable": True, "violations": 0, "unconnected": 0, "footprint_errors": 0},
        ):
            result = ai_pipeline.run_validation(STAGING_SCH, STAGING_PCB)

        self.assertIn("ai_staging_validation", result["erc_report"])
        self.assertIn("ai_staging_validation", result["drc_report"])
        self.assertNotEqual(
            str(ai_pipeline.VALIDATION_DIR),
            result["erc_report"].split("ai_staging_validation")[0]
            if "ai_staging_validation" in result["erc_report"] else result["erc_report"],
        )

    # --- Test 6: does not copy staging files to active project paths ---

    @patch.object(ai_pipeline, "run_powershell")
    @patch.object(ai_pipeline.Path, "exists", return_value=True)
    @patch.object(ai_pipeline.shutil, "copy2")
    def test_does_not_copy_to_active_paths(self, mock_copy2, mock_exists, mock_run):
        mock_run.return_value = {
            "stdout": "PASS",
            "stderr": "",
            "returncode": 0,
        }
        with patch.object(
            ai_pipeline, "_parse_erc_report",
            return_value={"parseable": True, "errors": 0, "warnings": 0},
        ), patch.object(
            ai_pipeline, "_parse_drc_report",
            return_value={"parseable": True, "violations": 0, "unconnected": 0, "footprint_errors": 0},
        ):
            ai_pipeline.run_validation(STAGING_SCH, STAGING_PCB)

        for call in mock_copy2.call_args_list:
            src, dst = call[0]
            self.assertNotEqual(Path(dst), ai_pipeline.SCH_FILE)
            self.assertNotEqual(Path(dst), ai_pipeline.PCB_FILE)

    # --- Test 7: cleanup only removes temp workspace ---

    @patch.object(ai_pipeline, "run_powershell")
    @patch.object(ai_pipeline.Path, "exists", return_value=True)
    @patch.object(ai_pipeline.shutil, "rmtree")
    def test_cleanup_only_removes_temp_workspace(self, mock_rmtree, mock_exists, mock_run):
        mock_run.return_value = {
            "stdout": "PASS",
            "stderr": "",
            "returncode": 0,
        }
        with patch.object(
            ai_pipeline, "_parse_erc_report",
            return_value={"parseable": True, "errors": 0, "warnings": 0},
        ), patch.object(
            ai_pipeline, "_parse_drc_report",
            return_value={"parseable": True, "violations": 0, "unconnected": 0, "footprint_errors": 0},
        ):
            ai_pipeline.run_validation(STAGING_SCH, STAGING_PCB)

        mock_rmtree.assert_called_once()
        removed_path = Path(mock_rmtree.call_args[0][0])
        self.assertNotEqual(removed_path, ai_pipeline.PROJECT_ROOT)
        self.assertNotEqual(removed_path, ai_pipeline.VALIDATION_DIR)
        self.assertIn("kicad_val_", str(removed_path))

    # --- Test 8: result contract preserved ---

    @patch.object(ai_pipeline, "run_powershell")
    @patch.object(ai_pipeline.Path, "exists", return_value=True)
    def test_result_contract_preserved(self, mock_exists, mock_run):
        mock_run.return_value = {
            "stdout": "CLI output",
            "stderr": "CLI stderr",
            "returncode": 0,
        }
        with patch.object(
            ai_pipeline, "_parse_erc_report",
            return_value={"parseable": True, "errors": 0, "warnings": 0},
        ), patch.object(
            ai_pipeline, "_parse_drc_report",
            return_value={"parseable": True, "violations": 0, "unconnected": 0, "footprint_errors": 0},
        ):
            result = ai_pipeline.run_validation(STAGING_SCH, STAGING_PCB)

        expected_keys = {
            "stdout", "stderr", "returncode",
            "erc", "drc",
            "erc_report", "drc_report", "clean",
        }
        self.assertEqual(set(result.keys()), expected_keys)
        self.assertEqual(result["stdout"], "CLI output")
        self.assertEqual(result["stderr"], "CLI stderr")
        self.assertEqual(result["returncode"], 0)
        self.assertIsInstance(result["clean"], bool)
        self.assertIsInstance(result["erc"], dict)
        self.assertIsInstance(result["drc"], dict)


if __name__ == "__main__":
    unittest.main()
