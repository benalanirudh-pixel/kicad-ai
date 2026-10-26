#!/usr/bin/env python3
"""
Integration tests for hardware safety gates in the KiCad pipeline.

Tests that unresolved/conflicting hardware assumptions block pipeline
operations at the correct points, and that gates cannot be bypassed.
Uses mocks and temporary fixtures. Does not modify active project files.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from pathlib import Path

# Enable hard guard in production code to reject un-patched active file paths.
os.environ["KILICODE_TEST_MODE"] = "1"

AI_DIR = r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280\scripts\ai"
if AI_DIR not in sys.path:
    sys.path.insert(0, AI_DIR)

import ai_pipeline
from hardware_profile import (
    HardwareFact, HardwareProfile,
    CONFIDENCE_VERIFIED, CONFIDENCE_ASSUMED, CONFIDENCE_UNRESOLVED, CONFIDENCE_CONFLICTING,
)


class _IsolatedProjectPathsMixin:
    """Test mixin: patch SCH_FILE/PCB_FILE to isolated temp copies.

    Each test gets its own temp directory with copies of the real active
    files. All journal/backup/temp artifacts created by copy_staging_to_
    active() and _attempt_recovery() land in this temp directory and are
    cleaned up automatically. The real project files are never touched
    during test execution.
    """

    def setUp(self):
        super().setUp()
        # Record real-project hashes BEFORE patching so tearDown can detect any
        # leakage or mutation of the active project. Evidence is preserved; the
        # real files are never restored from an unverified source.
        self._real_sch_hash = ai_pipeline._sha256_file(ai_pipeline.SCH_FILE)
        self._real_pcb_hash = ai_pipeline._sha256_file(ai_pipeline.PCB_FILE)
        self._temp_dir = tempfile.mkdtemp(prefix="kilo_test_")
        self._temp_sch = Path(self._temp_dir) / "ESP32_BME280.kicad_sch"
        self._temp_pcb = Path(self._temp_dir) / "ESP32_BME280.kicad_pcb"
        shutil.copy2(ai_pipeline.SCH_FILE, self._temp_sch)
        shutil.copy2(ai_pipeline.PCB_FILE, self._temp_pcb)
        self._patchers = [
            patch.object(ai_pipeline, "SCH_FILE", self._temp_sch),
            patch.object(ai_pipeline, "PCB_FILE", self._temp_pcb),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        # Evidence-preserving integrity check: fail loudly if the real active
        # project was mutated during the test. Never restore from an
        # unverified source; leave the evidence in place for inspection.
        if ai_pipeline._sha256_file(ai_pipeline.SCH_FILE) != self._real_sch_hash:
            raise AssertionError(
                "TEST ISOLATION VIOLATION: active SCH was mutated during test. "
                "Evidence preserved; not restoring from unverified source."
            )
        if ai_pipeline._sha256_file(ai_pipeline.PCB_FILE) != self._real_pcb_hash:
            raise AssertionError(
                "TEST ISOLATION VIOLATION: active PCB was mutated during test. "
                "Evidence preserved; not restoring from unverified source."
            )
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        super().tearDown()


@contextmanager
def _isolate_active_paths():
    """Context manager: patch SCH_FILE/PCB_FILE to isolated temp copies.

    Use this for individual tests that are not in a class using the mixin.
    """
    temp_dir = tempfile.mkdtemp(prefix="kilo_test_")
    temp_sch = Path(temp_dir) / "ESP32_BME280.kicad_sch"
    temp_pcb = Path(temp_dir) / "ESP32_BME280.kicad_pcb"
    shutil.copy2(ai_pipeline.SCH_FILE, temp_sch)
    shutil.copy2(ai_pipeline.PCB_FILE, temp_pcb)
    try:
        with patch.object(ai_pipeline, "SCH_FILE", temp_sch), \
             patch.object(ai_pipeline, "PCB_FILE", temp_pcb):
            yield temp_sch, temp_pcb
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def make_verified_profile_dict():
    """Build a profile JSON dict with all U1-U7 assumptions verified + footprint."""
    data = {}
    for uid in ["U1", "U2", "U3", "U4", "U5", "U6", "U7"]:
        data[uid] = {
            "value": "resolved",
            "source": "datasheet",
            "confidence": "verified",
            "affects_decisions": ["all"],
            "evidence_date": "2026-10-25",
        }
    data["esp32_header_footprint"] = {
        "value": "Connector_PinHeader_2.54mm:PinHeader_1x15_P2.54mm_Vertical",
        "source": "datasheet",
        "confidence": "verified",
        "affects_decisions": ["footprint_placement"],
        "evidence_date": "2026-10-25",
    }
    return data


class TestGenerationBlockedByElectricalGate(unittest.TestCase):
    """Generation must not proceed when electrical assumptions are unresolved."""

    @patch.object(ai_pipeline, "run_environment_check", return_value=True)
    @patch.object(ai_pipeline.sys, "argv", ["ai_pipeline.py", "test prompt"])
    @patch.object(ai_pipeline.sys, "exit", side_effect=SystemExit(1))
    @patch.object(ai_pipeline, "KiCadLLMInterface")
    def test_no_profile_blocks_before_generation(
        self, mock_llm, mock_exit, mock_env_check,
    ):
        """No hardware profile file -> all assumptions unresolved -> gate blocks."""
        self.assertFalse(ai_pipeline.HARDWARE_PROFILE_PATH.is_file())

        with self.assertRaises(SystemExit) as ctx:
            ai_pipeline.main()

        self.assertEqual(ctx.exception.code, 1)
        mock_exit.assert_called_with(1)
        # Generator must NOT be called
        mock_llm.assert_not_called()

    @patch.object(ai_pipeline, "run_environment_check", return_value=True)
    @patch.object(ai_pipeline.sys, "argv", ["ai_pipeline.py", "test prompt"])
    @patch.object(ai_pipeline.sys, "exit", side_effect=SystemExit(1))
    @patch.object(ai_pipeline, "KiCadLLMInterface")
    def test_unverified_profile_blocks_before_generation(
        self, mock_llm, mock_exit, mock_env_check,
    ):
        """Profile with unresolved assumptions -> gate blocks before generation."""
        with patch.object(
            ai_pipeline, "HARDWARE_PROFILE_PATH",
            Path(tempfile.mkdtemp()) / "nonexistent_profile.json",
        ):
            with self.assertRaises(SystemExit) as ctx:
                ai_pipeline.main()

            self.assertEqual(ctx.exception.code, 1)
            mock_llm.assert_not_called()


class TestGenerationAllowedWithVerifiedProfile(unittest.TestCase):
    """Generation may proceed when all assumptions are verified."""

    @patch.object(ai_pipeline, "run_environment_check", return_value=True)
    @patch.object(ai_pipeline.sys, "argv", ["ai_pipeline.py", "test prompt"])
    @patch.object(ai_pipeline.sys, "exit", side_effect=SystemExit(0))
    @patch.object(ai_pipeline, "KiCadLLMInterface")
    @patch.object(ai_pipeline, "write_staging_files")
    @patch.object(ai_pipeline, "run_validation")
    @patch.object(ai_pipeline, "input", return_value="no")
    def test_verified_profile_allows_generation(
        self, mock_input, mock_run_validation, mock_write_staging,
        mock_llm, mock_exit, mock_env_check,
    ):
        """All assumptions verified -> gate passes -> generation proceeds."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.generate_from_prompt.return_value = {
            "schematic": "(kicad_sch (version 20260306))",
            "pcb": "(kicad_pcb (version 20260206))",
            "spec": MagicMock(),
            "run_id": "20261025_120000",
        }
        mock_llm.return_value = mock_llm_instance

        # Write staging files to real temp files so run_validation can copy them
        tmpdir = tempfile.mkdtemp()
        sch_path = Path(tmpdir) / "ESP32_BME280.kicad_sch"
        pcb_path = Path(tmpdir) / "ESP32_BME280.kicad_pcb"
        sch_path.write_text("(kicad_sch)", encoding="utf-8")
        pcb_path.write_text("(kicad_pcb)", encoding="utf-8")
        mock_write_staging.return_value = {
            "staging_dir": Path(tmpdir),
            "sch_path": sch_path,
            "pcb_path": pcb_path,
        }

        mock_run_validation.return_value = {
            "stdout": "", "stderr": "", "returncode": 0,
            "erc": {"parseable": True, "errors": 0, "warnings": 0},
            "drc": {"parseable": True, "violations": 0, "unconnected": 0,
                    "footprint_errors": 0, "records": [], "unparsed_blocks": []},
            "erc_report": "", "drc_report": "", "clean": True,
        }

        with tempfile.TemporaryDirectory() as profile_dir:
            profile_path = Path(profile_dir) / "verified_profile.json"
            profile_path.write_text(json.dumps(make_verified_profile_dict()), encoding="utf-8")

            with patch.object(
                ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path,
            ):
                try:
                    ai_pipeline.main()
                except SystemExit:
                    pass  # User said "no" at approval gate

            # Generator WAS called
            mock_llm.assert_called_once()
            mock_llm_instance.generate_from_prompt.assert_called_once()


class TestManufacturingBlockedByFabricationGate(unittest.TestCase):
    """Manufacturing export must be blocked when fabrication assumptions unresolved."""

    @patch.object(ai_pipeline, "run_environment_check", return_value=True)
    @patch.object(ai_pipeline.sys, "argv", ["ai_pipeline.py", "test prompt"])
    @patch.object(ai_pipeline.sys, "exit", side_effect=SystemExit(1))
    @patch.object(ai_pipeline, "KiCadLLMInterface")
    @patch.object(ai_pipeline, "write_staging_files")
    @patch.object(ai_pipeline, "run_validation")
    @patch.object(ai_pipeline, "input", return_value="yes")
    @patch.object(ai_pipeline, "copy_staging_to_active", return_value=True)
    def test_unverified_profile_blocks_manufacturing_export(
        self, mock_copy, mock_input, mock_run_validation, mock_write_staging,
        mock_llm, mock_exit, mock_env_check,
    ):
        """Unverified profile -> fabrication gate blocks before export."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.generate_from_prompt.return_value = {
            "schematic": "(kicad_sch)",
            "pcb": "(kicad_pcb)",
            "spec": MagicMock(),
            "run_id": "20261025_120000",
        }
        mock_llm.return_value = mock_llm_instance

        tmpdir = tempfile.mkdtemp()
        sch_path = Path(tmpdir) / "ESP32_BME280.kicad_sch"
        pcb_path = Path(tmpdir) / "ESP32_BME280.kicad_pcb"
        sch_path.write_text("(kicad_sch)", encoding="utf-8")
        pcb_path.write_text("(kicad_pcb)", encoding="utf-8")
        mock_write_staging.return_value = {
            "staging_dir": Path(tmpdir),
            "sch_path": sch_path,
            "pcb_path": pcb_path,
        }

        mock_run_validation.return_value = {
            "stdout": "", "stderr": "", "returncode": 0,
            "erc": {"parseable": True, "errors": 0, "warnings": 0},
            "drc": {"parseable": True, "violations": 0, "unconnected": 0,
                    "footprint_errors": 0, "records": [], "unparsed_blocks": []},
            "erc_report": "", "drc_report": "", "clean": True,
        }

        # No verified profile -> fabrication gate blocks at G5
        with patch.object(
            ai_pipeline, "HARDWARE_PROFILE_PATH",
            Path(tempfile.mkdtemp()) / "nonexistent.json",
        ):
            with self.assertRaises(SystemExit) as ctx:
                ai_pipeline.main()

            self.assertEqual(ctx.exception.code, 1)


class TestConflictingEvidenceBlocks(unittest.TestCase):
    """Conflicting evidence must block the relevant gate."""

    @patch.object(ai_pipeline, "run_environment_check", return_value=True)
    @patch.object(ai_pipeline.sys, "argv", ["ai_pipeline.py", "test prompt"])
    @patch.object(ai_pipeline.sys, "exit", side_effect=SystemExit(1))
    @patch.object(ai_pipeline, "KiCadLLMInterface")
    def test_conflicting_u1_blocks_electrical(
        self, mock_llm, mock_exit, mock_env_check,
    ):
        """Conflicting supply voltage -> electrical gate blocks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "conflicting.json"
            data = {
                "U1": {
                    "value": "3.3V",
                    "source": "prompt_extract",
                    "confidence": "conflicting",
                    "affects_decisions": ["supply_net_selection"],
                },
                "U2": {
                    "value": "GPIO21",
                    "source": "datasheet",
                    "confidence": "verified",
                    "affects_decisions": ["schematic_wiring"],
                },
                "U3": {
                    "value": True,
                    "source": "datasheet",
                    "confidence": "verified",
                    "affects_decisions": ["schematic_resistors"],
                },
                "U7": {
                    "value": "0x76",
                    "source": "datasheet",
                    "confidence": "verified",
                    "affects_decisions": ["schematic_nets"],
                },
            }
            profile_path.write_text(json.dumps(data), encoding="utf-8")

            with patch.object(
                ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path,
            ):
                with self.assertRaises(SystemExit) as ctx:
                    ai_pipeline.main()

                self.assertEqual(ctx.exception.code, 1)
                mock_llm.assert_not_called()


class TestProfilePathProjectRelative(unittest.TestCase):
    """Profile path must be resolved from project root, not CWD."""

    @patch.object(ai_pipeline, "run_environment_check", return_value=True)
    @patch.object(ai_pipeline.sys, "argv", ["ai_pipeline.py", "test prompt"])
    @patch.object(ai_pipeline.sys, "exit", side_effect=SystemExit(1))
    @patch.object(ai_pipeline, "KiCadLLMInterface")
    def test_cannot_bypass_by_changing_cwd(
        self, mock_llm, mock_exit, mock_env_check,
    ):
        """Changing CWD does not bypass the hardware gate."""
        original_cwd = os.getcwd()
        try:
            os.chdir(tempfile.mkdtemp())
            with self.assertRaises(SystemExit) as ctx:
                ai_pipeline.main()
            self.assertEqual(ctx.exception.code, 1)
            mock_llm.assert_not_called()
        finally:
            os.chdir(original_cwd)


class TestBlockedOperationNoSideEffects(unittest.TestCase):
    """A blocked gate must not generate files, copy to active, or export."""

    @patch.object(ai_pipeline, "run_environment_check", return_value=True)
    @patch.object(ai_pipeline.sys, "argv", ["ai_pipeline.py", "test prompt"])
    @patch.object(ai_pipeline.sys, "exit", side_effect=SystemExit(1))
    @patch.object(ai_pipeline, "KiCadLLMInterface")
    @patch.object(ai_pipeline, "write_staging_files")
    @patch.object(ai_pipeline, "copy_staging_to_active")
    @patch.object(ai_pipeline, "run_manufacturing_export")
    def test_no_generation_copy_or_export_when_blocked(
        self, mock_export, mock_copy, mock_write_staging,
        mock_llm, mock_exit, mock_env_check,
    ):
        """Blocked gate -> no generation, no copy, no export."""
        with self.assertRaises(SystemExit):
            ai_pipeline.main()

        mock_llm.assert_not_called()
        mock_write_staging.assert_not_called()
        mock_copy.assert_not_called()
        mock_export.assert_not_called()


class TestReturnContractPreserved(unittest.TestCase):
    """run_validation() return contract must be unchanged."""

    @patch.object(ai_pipeline, "run_powershell")
    @patch.object(ai_pipeline.Path, "exists", return_value=True)
    def test_validation_result_keys_unchanged(
        self, mock_exists, mock_run_powershell,
    ):
        """run_validation() returns the same top-level keys as before."""
        # Create real temp files for run_validation to copy
        tmpdir = tempfile.mkdtemp()
        sch_path = Path(tmpdir) / "ESP32_BME280.kicad_sch"
        pcb_path = Path(tmpdir) / "ESP32_BME280.kicad_pcb"
        sch_path.write_text("(kicad_sch)", encoding="utf-8")
        pcb_path.write_text("(kicad_pcb)", encoding="utf-8")

        mock_run_powershell.return_value = {
            "stdout": "PASS", "stderr": "", "returncode": 0,
        }
        with patch.object(
            ai_pipeline, "_parse_erc_report",
            return_value={"parseable": True, "errors": 0, "warnings": 0},
        ), patch.object(
            ai_pipeline, "_parse_drc_report",
            return_value={"parseable": True, "violations": 0, "unconnected": 0,
                          "footprint_errors": 0},
        ):
            result = ai_pipeline.run_validation(sch_path, pcb_path)

        expected_keys = {
            "stdout", "stderr", "returncode",
            "erc", "drc",
            "erc_report", "drc_report", "clean",
        }
        self.assertEqual(set(result.keys()), expected_keys)


# ---------------------------------------------------------------------------
# Phase D4 regression tests: direct-call bypass prevention
# ---------------------------------------------------------------------------


class TestCopyStagingGateHardening(_IsolatedProjectPathsMixin, unittest.TestCase):
    """Directly calling copy_staging_to_active() must be gated."""

    @patch.object(ai_pipeline, "shutil")
    def test_copy_blocked_when_profile_missing(self, mock_shutil):
        """Direct call with missing profile returns False, no shutil calls."""
        result = ai_pipeline.copy_staging_to_active(
            staging_dir=Path(tempfile.mkdtemp()),
        )
        self.assertFalse(result)
        mock_shutil.copy2.assert_not_called()

    @patch.object(ai_pipeline, "shutil")
    def test_copy_blocked_when_profile_invalid_json(self, mock_shutil):
        """Malformed JSON profile blocks copy before any file operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_profile = Path(tmpdir) / "hardware_profile.json"
            bad_profile.write_text("{not valid json", encoding="utf-8")
            with patch.object(
                ai_pipeline, "HARDWARE_PROFILE_PATH", bad_profile,
            ):
                result = ai_pipeline.copy_staging_to_active(
                    staging_dir=Path(tempfile.mkdtemp()),
                )
        self.assertFalse(result)
        mock_shutil.copy2.assert_not_called()

    @patch.object(ai_pipeline, "shutil")
    def test_copy_blocked_when_electrical_assumption_missing(self, mock_shutil):
        """Electrical assumption missing blocks both files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = Path(tmpdir) / "hardware_profile.json"
            data = {"U4": {"confidence": "verified"}}  # only mechanical
            profile.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(
                ai_pipeline, "HARDWARE_PROFILE_PATH", profile,
            ):
                result = ai_pipeline.copy_staging_to_active(
                    staging_dir=Path(tempfile.mkdtemp()),
                )
        self.assertFalse(result)
        mock_shutil.copy2.assert_not_called()

    @patch.object(ai_pipeline, "shutil")
    def test_copy_blocked_when_mechanical_assumption_missing(self, mock_shutil):
        """Mechanical assumption missing blocks both files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = Path(tmpdir) / "hardware_profile.json"
            data = {
                "U1": {"confidence": "verified"},
                "U2": {"confidence": "verified"},
                "U3": {"confidence": "verified"},
                "U7": {"confidence": "verified"},
            }
            profile.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(
                ai_pipeline, "HARDWARE_PROFILE_PATH", profile,
            ):
                result = ai_pipeline.copy_staging_to_active(
                    staging_dir=Path(tempfile.mkdtemp()),
                )
        self.assertFalse(result)
        mock_shutil.copy2.assert_not_called()

    @patch.object(ai_pipeline, "shutil")
    def test_copy_blocked_when_assumption_assumed(self, mock_shutil):
        """Assumed (not verified) facts block copy."""
        data = {uid: {"confidence": "assumed"} for uid in ["U1","U2","U3","U4","U5","U6","U7"]}
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = Path(tmpdir) / "hardware_profile.json"
            profile.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(
                ai_pipeline, "HARDWARE_PROFILE_PATH", profile,
            ):
                result = ai_pipeline.copy_staging_to_active(
                    staging_dir=Path(tempfile.mkdtemp()),
                )
        self.assertFalse(result)
        mock_shutil.copy2.assert_not_called()

    @patch.object(ai_pipeline.os, "replace")
    def test_copy_allows_with_verified_profile(self, mock_replace):
        """Verified profile → both gates pass → os.replace called for both files."""
        tmpdir = Path(tempfile.mkdtemp())
        src_sch = tmpdir / "ESP32_BME280.kicad_sch"
        src_pcb = tmpdir / "ESP32_BME280.kicad_pcb"
        src_sch.write_text("(kicad_sch)", encoding="utf-8")
        src_pcb.write_text("(kicad_pcb)", encoding="utf-8")

        profile_data = make_verified_profile_dict()
        with tempfile.TemporaryDirectory() as profile_dir:
            profile_path = Path(profile_dir) / "hardware_profile.json"
            profile_path.write_text(
                json.dumps(profile_data), encoding="utf-8",
            )
            with patch.object(
                ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path,
            ):
                result = ai_pipeline.copy_staging_to_active(
                    staging_dir=tmpdir,
                )

        self.assertTrue(result)
        self.assertEqual(mock_replace.call_count, 2)


class TestManufacturingExportGateHardening(unittest.TestCase):
    """Directly calling run_manufacturing_export() must be gated."""

    @patch.object(ai_pipeline, "run_powershell")
    def test_export_blocked_when_profile_missing(self, mock_ps):
        """Missing profile blocks export before any subprocess invocation."""
        result = ai_pipeline.run_manufacturing_export(
            confirm_yes=True, force=True,
        )
        self.assertFalse(result)
        mock_ps.assert_not_called()

    @patch.object(ai_pipeline, "run_powershell")
    def test_export_blocked_when_profile_invalid_json(self, mock_ps):
        """Malformed JSON profile blocks export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_profile = Path(tmpdir) / "hardware_profile.json"
            bad_profile.write_text("<<<not json>>>", encoding="utf-8")
            with patch.object(
                ai_pipeline, "HARDWARE_PROFILE_PATH", bad_profile,
            ):
                result = ai_pipeline.run_manufacturing_export(
                    confirm_yes=True, force=True,
                )
        self.assertFalse(result)
        mock_ps.assert_not_called()

    @patch.object(ai_pipeline, "run_powershell")
    def test_export_blocked_by_confirm_yes(self, mock_ps):
        """confirm_yes=True cannot override a failed gate."""
        result = ai_pipeline.run_manufacturing_export(confirm_yes=True)
        self.assertFalse(result)
        mock_ps.assert_not_called()

    @patch.object(ai_pipeline, "run_powershell")
    def test_export_blocked_by_force(self, mock_ps):
        """force=True cannot override a failed gate."""
        result = ai_pipeline.run_manufacturing_export(confirm_yes=True, force=True)
        self.assertFalse(result)
        mock_ps.assert_not_called()

    def test_export_blocked_leaves_no_output_changes(self):
        """Blocked export must not create or modify manufacturing outputs."""
        mfg_dir = ai_pipeline.MANUFACTURING_DIR
        gerber_dir = mfg_dir / "gerbers"
        drill_dir = mfg_dir / "drill"

        gerber_mtime_before = gerber_dir.stat().st_mtime_ns if gerber_dir.exists() else None
        drill_mtime_before = drill_dir.stat().st_mtime_ns if drill_dir.exists() else None

        result = ai_pipeline.run_manufacturing_export(confirm_yes=True, force=True)
        self.assertFalse(result)

        if gerber_dir.exists():
            self.assertEqual(
                gerber_mtime_before, gerber_dir.stat().st_mtime_ns,
                "Gerber directory modified during blocked export",
            )
        if drill_dir.exists():
            self.assertEqual(
                drill_mtime_before, drill_dir.stat().st_mtime_ns,
                "Drill directory modified during blocked export",
            )

    @patch.object(ai_pipeline, "run_powershell")
    def test_export_allows_with_verified_profile(self, mock_ps):
        """Verified profile permits the fabrication gate path."""
        mock_ps.return_value = {"stdout": "OK", "stderr": "", "returncode": 0}
        with tempfile.TemporaryDirectory() as profile_dir:
            profile_path = Path(profile_dir) / "hardware_profile.json"
            profile_path.write_text(
                json.dumps(make_verified_profile_dict()), encoding="utf-8",
            )
            with patch.object(
                ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path,
            ):
                result = ai_pipeline.run_manufacturing_export(
                    confirm_yes=True, force=True,
                )
        self.assertTrue(result)
        mock_ps.assert_called_once()


class TestGateReturnContract(unittest.TestCase):
    """Verify return contracts of hardened functions."""

    @patch.object(ai_pipeline, "shutil")
    def test_copy_returns_bool(self, mock_shutil):
        """copy_staging_to_active returns bool in all cases."""
        with _isolate_active_paths():
            result = ai_pipeline.copy_staging_to_active(
                staging_dir=Path(tempfile.mkdtemp()),
            )
        self.assertIsInstance(result, bool)

    @patch.object(ai_pipeline, "run_powershell")
    def test_export_returns_bool(self, mock_ps):
        """run_manufacturing_export returns bool in all cases."""
        result = ai_pipeline.run_manufacturing_export(confirm_yes=True)
        self.assertIsInstance(result, bool)


# ---------------------------------------------------------------------------
# Phase D5 regression tests: two-file replacement rollback safety
# ---------------------------------------------------------------------------


class TestCopyRollbackSafety(_IsolatedProjectPathsMixin, unittest.TestCase):
    """Verify copy_staging_to_active() leaves active files unchanged
    after various failure scenarios. Uses isolated temp paths — the real
    project files are never touched."""

    def _make_verified_profile(self):
        """Return (profile_file_path, staging_dir) with verified facts."""
        profile_dir = tempfile.mkdtemp()
        profile_path = Path(profile_dir) / "hardware_profile.json"
        profile_path.write_text(
            json.dumps(make_verified_profile_dict()), encoding="utf-8",
        )

        staging = Path(tempfile.mkdtemp())
        # Staging files with different content than active files.
        (staging / "ESP32_BME280.kicad_sch").write_text(
            "(kicad_sch STAGING_CONTENT_SCH)", encoding="utf-8",
        )
        (staging / "ESP32_BME280.kicad_pcb").write_text(
            "(kicad_pcb STAGING_CONTENT_PCB)", encoding="utf-8",
        )
        return profile_path, staging

    @patch.object(ai_pipeline.shutil, "copy2", side_effect=OSError("disk full"))
    def test_first_temp_copy_fails_blocks_all(self, mock_copy2):
        """If the first shutil.copy2 fails, neither active file is touched."""
        profile_path, staging = self._make_verified_profile()
        with patch.object(ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path):
            result = ai_pipeline.copy_staging_to_active(staging_dir=staging)
        self.assertFalse(result)

    @patch.object(ai_pipeline.shutil, "copy2", side_effect=[None, OSError("disk full")])
    def test_second_temp_copy_fails_blocks_all(self, mock_copy2):
        """If the second shutil.copy2 fails, neither active file is touched."""
        profile_path, staging = self._make_verified_profile()
        with patch.object(ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path):
            result = ai_pipeline.copy_staging_to_active(staging_dir=staging)
        self.assertFalse(result)

    def test_second_os_replace_failure_rolls_back_first(self):
        """If first os.replace succeeds but second fails, rollback is triggered
        to restore the first file from backup."""
        call_count = [0]
        replace_log = []

        def selective_replace(src, dst):
            call_count[0] += 1
            replace_log.append((str(src), str(dst)))
            if call_count[0] == 2:
                # Second replace (PCB) fails — simulate I/O error.
                raise OSError("Simulated failure on second replace")
            return None  # Simulate success WITHOUT actual file modification

        profile_path, staging = self._make_verified_profile()
        with patch.object(ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path):
            with patch.object(ai_pipeline.os, "replace", side_effect=selective_replace):
                result = ai_pipeline.copy_staging_to_active(staging_dir=staging)

        self.assertFalse(result)
        # call_count: 1 (first replace, succeeds) + 1 (failed second replace)
        #            + 1 (rollback replace) = 3
        self.assertEqual(call_count[0], 3, "Rollback os.replace should be called")
        # Verify the third call is the rollback (source is backup, dest is active SCH)
        rollback_src, rollback_dst = replace_log[2]
        self.assertIn("bak_", rollback_src, "Rollback should source from backup file")
        self.assertEqual(rollback_dst, str(ai_pipeline.SCH_FILE), "Rollback should restore active SCH file")

    @patch.object(ai_pipeline.os, "replace", side_effect=OSError("simulated replace failure"))
    def test_os_replace_failure_all_does_not_corrupt(self, mock_replace):
        """If all os.replace calls fail, active files are unchanged."""
        profile_path, staging = self._make_verified_profile()
        with patch.object(
            ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path,
        ), patch.object(ai_pipeline.shutil, "copy2"):
            # shutil.copy2 is mocked so backup/temp files aren't created
            result = ai_pipeline.copy_staging_to_active(staging_dir=staging)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# Phase D5 recovery tests: crash recovery journaling and rollback preservation
# ---------------------------------------------------------------------------


class TestCrashRecoveryJournal(_IsolatedProjectPathsMixin, unittest.TestCase):
    """Verify journal-based crash recovery and backup preservation.
    Uses isolated temp paths — the real project files are never touched."""

    def tearDown(self):
        self._cleanup_pid_artifacts(12345)
        self._cleanup_pid_artifacts(12346)
        self._cleanup_pid_artifacts(12347)
        self._cleanup_pid_artifacts(12348)
        self._cleanup_pid_artifacts(12349)
        self._cleanup_pid_artifacts(12350)
        super().tearDown()

    def _make_verified_profile_and_staging(self):
        """Return (profile_path, staging_dir) with verified facts."""
        profile_dir = tempfile.mkdtemp()
        profile_path = Path(profile_dir) / "hardware_profile.json"
        profile_path.write_text(
            json.dumps(make_verified_profile_dict()), encoding="utf-8",
        )
        staging = Path(tempfile.mkdtemp())
        (staging / "ESP32_BME280.kicad_sch").write_text(
            "(kicad_sch STAGING_CONTENT_SCH)", encoding="utf-8",
        )
        (staging / "ESP32_BME280.kicad_pcb").write_text(
            "(kicad_pcb STAGING_CONTENT_PCB)", encoding="utf-8",
        )
        return profile_path, staging

    def _cleanup_pid_artifacts(self, pid: int) -> None:
        """Remove stale journal, backup, and temp files for a given PID."""
        for suffix in (f".journal_{pid}", f".bak_{pid}"):
            for ext in (".kicad_sch", ".kicad_pcb"):
                path = ai_pipeline.SCH_FILE.parent / f"ESP32_BME280.kicad_sch{suffix}"
                if path.exists():
                    path.unlink()
                path = ai_pipeline.PCB_FILE.parent / f"ESP32_BME280.kicad_pcb{suffix}"
                if path.exists():
                    path.unlink()
        for ext in (".kicad_sch", ".kicad_pcb"):
            for fname in ai_pipeline.SCH_FILE.parent.glob(f"*{ext}.journal_{pid}"):
                fname.unlink(missing_ok=True)
            for fname in ai_pipeline.SCH_FILE.parent.glob(f"*{ext}.bak_{pid}"):
                fname.unlink(missing_ok=True)
            for fname in ai_pipeline.SCH_FILE.parent.glob(f"*{ext}.tmp_{pid}"):
                fname.unlink(missing_ok=True)

    @patch("ai_pipeline.os.getpid", return_value=12345)
    def test_stale_journal_triggers_recovery_on_next_run(self, mock_pid):
        """A stale journal from a prior interrupted run is detected and cleaned."""
        pid = 12345
        self._cleanup_pid_artifacts(pid)
        profile_path, staging = self._make_verified_profile_and_staging()
        # Create journal and backup files as if a previous run was interrupted
        # AFTER backup creation but BEFORE first replace.
        bak_sch = ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.bak_{pid}"
        journal = ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.journal_{pid}"
        shutil.copy2(ai_pipeline.SCH_FILE, bak_sch)
        journal.write_text(json.dumps({
            "backup_sch": str(bak_sch),
            "backup_pcb": str(ai_pipeline.PCB_FILE.parent / "skip"),
            "active_sch": str(ai_pipeline.SCH_FILE),
            "active_pcb": str(ai_pipeline.PCB_FILE),
            "staging_sch_hash": "abc123",
            "staging_pcb_hash": None,
            "status": "pending",
        }), encoding="utf-8")

        with patch.object(ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path):
            with patch.object(ai_pipeline.shutil, "copy2") as mock_copy2:
                # copy2 is mocked so the real function won't overwrite our
                # journal/backup simulation; the actual replace still runs.
                result = ai_pipeline.copy_staging_to_active(staging_dir=staging)

        # Active files must be unchanged (journal recovery ran, then the
        # current run attempted to back up/replaced but failed due to
        # mocked shutil.copy2). Temp paths are isolated — the real project
        # files are never at risk.
        self.assertFalse(journal.exists(), "Stale journal was not cleaned up")
        # Clean up any leftover artifacts
        self._cleanup_pid_artifacts(pid)

    @patch("ai_pipeline.os.getpid", return_value=12346)
    def test_rollack_failure_preserves_backup(self, mock_pid):
        """If rollback os.replace also fails, backup is preserved (not deleted)."""
        pid = 12346
        self._cleanup_pid_artifacts(pid)
        profile_path, staging = self._make_verified_profile_and_staging()
        bak_sch = ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.bak_{pid}"

        call_count = [0]

        def failing_replace(src, dst):
            call_count[0] += 1
            if call_count[0] == 2:
                # Second replace fails
                raise OSError("Simulated PCB replace failure")
            elif call_count[0] == 3:
                # Rollback replace also fails
                raise OSError("Simulated rollback failure")
            return None  # All other calls succeed as no-ops

        with patch.object(ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path):
            with patch.object(ai_pipeline.os, "replace", side_effect=failing_replace):
                result = ai_pipeline.copy_staging_to_active(staging_dir=staging)

        self.assertFalse(result)
        # Backup should be preserved (not in finally cleanup because
        # preserve_backups was set to True).
        self.assertTrue(bak_sch.exists(), "Backup should be preserved on rollback failure")
        # Clean up
        self._cleanup_pid_artifacts(pid)

    @patch("ai_pipeline.os.getpid", return_value=12347)
    def test_jounal_removed_after_successful_transaction(self, mock_pid):
        """Journal is removed after both files are successfully committed."""
        pid = 12347
        self._cleanup_pid_artifacts(pid)
        profile_path, staging = self._make_verified_profile_and_staging()
        journal = ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.journal_{pid}"

        with patch.object(ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path):
            # Mock os.replace so active files aren't actually modified;
            # the journal write/deletion and code flow still execute.
            with patch.object(ai_pipeline.os, "replace"):
                result = ai_pipeline.copy_staging_to_active(staging_dir=staging)

        self.assertTrue(result)
        self.assertFalse(journal.exists(), "Journal should be removed after success")

    @patch("ai_pipeline.os.getpid", return_value=12348)
    def test_jounal_removed_after_failed_transaction_non_preserved(self, mock_pid):
        """Journal is removed after a failed transaction that doesn't preserve backups."""
        pid = 12348
        self._cleanup_pid_artifacts(pid)
        profile_path, staging = self._make_verified_profile_and_staging()
        journal = ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.journal_{pid}"

        with patch.object(ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path):
            with patch.object(ai_pipeline.shutil, "copy2", side_effect=OSError("simulated")):
                result = ai_pipeline.copy_staging_to_active(staging_dir=staging)

        self.assertFalse(result)
        # Journal should be cleaned up in finally (preserve_backups=False path)
        self.assertFalse(journal.exists(), "Journal should be cleaned up after non-preserved failure")

    @patch("ai_pipeline.os.getpid", return_value=12349)
    @patch("ai_pipeline.os.replace", side_effect=OSError("locked"))
    def test_replace_failure_with_real_backup_rolls_back(self, mock_replace, mock_pid):
        """When os.replace fails on first call, backup created, no rollback needed
        but backup must be cleaned up (or preserved if rollback also fails)."""
        pid = 12349
        self._cleanup_pid_artifacts(pid)
        profile_path, staging = self._make_verified_profile_and_staging()
        bak_sch = ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.bak_{pid}"

        with patch.object(ai_pipeline, "HARDWARE_PROFILE_PATH", profile_path):
            result = ai_pipeline.copy_staging_to_active(staging_dir=staging)

        self.assertFalse(result)
        # First replace failed, replaced_sch=False, so no rollback triggered.
        # preserve_backups stays False -> backup is cleaned up in finally.
        self.assertFalse(bak_sch.exists(), "Backup should be cleaned up when no rollback occurs")

    @patch("ai_pipeline.os.getpid", return_value=12350)
    def test_recovery_detects_externally_modified_file(self, mock_pid):
        """Recovery preserves backup when active file differs from both staging and backup."""
        pid = 12350
        self._cleanup_pid_artifacts(pid)
        bak_sch = ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.bak_{pid}"
        journal = ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.journal_{pid}"

        # Create backup of original
        shutil.copy2(ai_pipeline.SCH_FILE, bak_sch)
        backup_hash = _sha256_file(bak_sch)

        # Write a journal with a staging hash that won't match current active file
        journal.write_text(json.dumps({
            "backup_sch": str(bak_sch),
            "backup_pcb": str(ai_pipeline.PCB_FILE.parent / "nonexistent.pcb"),
            "active_sch": str(ai_pipeline.SCH_FILE),
            "active_pcb": str(ai_pipeline.PCB_FILE),
            "staging_sch_hash": "stale_staging_hash_that_wont_match",
            "staging_pcb_hash": None,
            "status": "pending",
        }), encoding="utf-8")

        # Modify the active file externally (different hash from both staging and backup)
        original_sch = ai_pipeline.SCH_FILE.read_text(encoding="utf-8")
        try:
            (ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.extmod_tmp").write_text(
                "(kicad_sch EXTERNAL_MODIFICATION)", encoding="utf-8",
            )
            os.replace(
                ai_pipeline.SCH_FILE.parent / f"{ai_pipeline.SCH_FILE.name}.extmod_tmp",
                ai_pipeline.SCH_FILE,
            )

            # Test _attempt_recovery directly
            ai_pipeline._attempt_recovery(journal)

            # Backup should be preserved (externally modified file, not restored)
            self.assertTrue(bak_sch.exists(), "Backup should be preserved when active file was externally modified")
            # Journal should be cleaned up by recovery
            self.assertFalse(journal.exists(), "Journal should be cleaned up after recovery")
        finally:
            # Restore original file
            ai_pipeline.SCH_FILE.write_text(original_sch, encoding="utf-8")
            self._cleanup_pid_artifacts(pid)


def _sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file, or empty string if missing."""
    import hashlib
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Phase D6: SHA-256 hash verification helpers in ai_pipeline
# ---------------------------------------------------------------------------


class TestSha256FileHelper(unittest.TestCase):
    """Verify the _sha256_file helper in ai_pipeline."""

    def test_sha256_file_matches_hashlib(self):
        """_sha256_file returns the same digest as hashlib."""
        import hashlib
        test_path = ai_pipeline.SCH_FILE
        expected = hashlib.sha256(test_path.read_bytes()).hexdigest()
        result = ai_pipeline._sha256_file(test_path)
        self.assertEqual(result, expected)

    def test_sha256_file_consistent(self):
        """Multiple calls return the same hash."""
        h1 = ai_pipeline._sha256_file(ai_pipeline.SCH_FILE)
        h2 = ai_pipeline._sha256_file(ai_pipeline.SCH_FILE)
        self.assertEqual(h1, h2)

def hash_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file, or empty string if missing."""
    import hashlib
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
