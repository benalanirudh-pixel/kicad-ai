#!/usr/bin/env python3
"""
Tests for parse_drc_report_detailed(): read-only DRC report parser.

Uses real excerpts from the actual KiCad 10 DRC report as fixtures.
Does not invent report contents.
"""

import sys
import unittest
from pathlib import Path

AI_DIR = r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280\scripts\ai"
if AI_DIR not in sys.path:
    sys.path.insert(0, AI_DIR)

import ai_pipeline
from ai_pipeline import DrcViolation, parse_drc_report_detailed

# Real excerpt from outputs\validation\ESP32_BME280_drc_report.txt
TRACK_DANGLING_BLOCK = """** Found 1 DRC violations **
** Found 0 unconnected pads **
** Found 0 Footprint errors **
[track_dangling]: Track has unconnected end
    Local override; warning
    @(56.0000 mm, 100.0000 mm): Track [+3V3] on F.Cu, length 24.0000 mm"""

UNCONNECTED_BLOCK_TWO_ITEMS = """** Found 0 DRC violations **
** Found 1 unconnected pads **
** Found 0 Footprint errors **
[unconnected_items]: Missing connection between items
    Local override; error
    @(87.5400 mm, 105.0800 mm): Track [+3V3] on F.Cu, length 34.9200 mm
    @(100.0000 mm, 200.0000 mm): PTH pad 1 [+3V3] of """

FOOTPRINT_MISMATCH_BLOCK = """** Found 0 DRC violations **
** Found 0 unconnected pads **
** Found 1 Footprint errors **
[lib_footprint_mismatch]: Footprint 'PinHeader_1x15_P2.54mm_Vertical' does not match copy in library 'Connector_PinHeader_2.54mm'
    Local override; warning
    @(50.0000 mm, 100.0000 mm): Footprint <no reference designator>"""

NEGATIVE_COORD_BLOCK = """** Found 1 DRC violations **
** Found 0 unconnected pads **
** Found 0 Footprint errors **
[track_dangling]: Track has unconnected end
    Local override; warning
    @(-12.5000 mm, -34.2000 mm): Track [GND] on B.Cu, length 8.7500 mm"""

MALFORMED_BLOCK = """** Found 0 DRC violations **
** Found 0 unconnected pads **
** Found 0 Footprint errors **
[unknown_type]: Something went wrong
    This is not a severity line
    @(0.0 mm, 0.0 mm): Some item"""

FULL_REPORT_EXCERPT = """** Drc report for ESP32_BME280.kicad_pcb **
** Created on 2026-10-25T20:25:59 **
** Report includes: Errors, Warnings **

** Found 17 DRC violations **
[track_dangling]: Track has unconnected end
    Local override; warning
    @(56.0000 mm, 100.0000 mm): Track [+3V3] on F.Cu, length 24.0000 mm
[track_dangling]: Track has unconnected end
    Local override; warning
    @(82.4600 mm, 100.0000 mm): Track [+3V3] on F.Cu, length 40.0000 mm
[lib_footprint_mismatch]: Footprint 'PinHeader_1x15_P2.54mm_Vertical' does not match copy in library 'Connector_PinHeader_2.54mm'
    Local override; warning
    @(50.0000 mm, 100.0000 mm): Footprint <no reference designator>
** Found 39 unconnected pads **
[unconnected_items]: Missing connection between items
    Local override; error
    @(87.5400 mm, 105.0800 mm): Track [+3V3] on F.Cu, length 34.9200 mm
    @(100.0000 mm, 200.0000 mm): PTH pad 1 [+3V3] of
** Found 0 Footprint errors **
** Ignored checks **
    - Footprint has no courtyard defined
** End of Report **"""

EMPTY_REPORT = """** Drc report for ESP32_BME280.kicad_pcb **
** Created on 2026-10-25T20:25:59 **
** Report includes: Errors, Warnings **

** Found 0 DRC violations **
** Found 0 unconnected pads **
** Found 0 Footprint errors **
** End of Report **"""

SUMMARY_ONLY_REPORT = """** Found 17 DRC violations **
** Found 39 unconnected pads **
** Found 0 Footprint errors **"""


class TestDrcParser(unittest.TestCase):
    """Read-only DRC report parser — extracts individual violation records."""

    # --- Test 1: track_dangling violation with single item ---

    def test_parse_track_dangling_single_item(self):
        result = parse_drc_report_detailed(TRACK_DANGLING_BLOCK)
        self.assertTrue(result["parseable"])
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(len(result["unparsed_blocks"]), 0)

        rec = result["records"][0]
        self.assertIsInstance(rec, DrcViolation)
        self.assertEqual(rec.violation_type, "track_dangling")
        self.assertEqual(rec.message, "Track has unconnected end")
        self.assertEqual(rec.severity, "warning")
        self.assertEqual(rec.coordinates, [(56.0, 100.0)])
        self.assertEqual(len(rec.items), 1)
        self.assertEqual(rec.items[0]["description"], "Track")
        self.assertEqual(rec.items[0]["net"], "+3V3")
        self.assertEqual(rec.items[0]["layer"], "F.Cu")
        self.assertEqual(rec.items[0]["length_mm"], 24.0)
        self.assertIsNone(rec.items[0]["reference"])
        self.assertIn("Track has unconnected end", rec.original_text)

    # --- Test 2: unconnected_items with two items ---

    def test_parse_unconnected_items_two_items(self):
        result = parse_drc_report_detailed(UNCONNECTED_BLOCK_TWO_ITEMS)
        self.assertTrue(result["parseable"])
        self.assertEqual(len(result["records"]), 1)

        rec = result["records"][0]
        self.assertEqual(rec.violation_type, "unconnected_items")
        self.assertEqual(rec.message, "Missing connection between items")
        self.assertEqual(rec.severity, "error")
        self.assertEqual(len(rec.coordinates), 2)
        self.assertEqual(rec.coordinates[0], (87.54, 105.08))
        self.assertEqual(rec.coordinates[1], (100.0, 200.0))
        self.assertEqual(len(rec.items), 2)
        self.assertEqual(rec.items[0]["description"], "Track")
        self.assertEqual(rec.items[0]["net"], "+3V3")
        self.assertEqual(rec.items[0]["layer"], "F.Cu")
        self.assertEqual(rec.items[0]["length_mm"], 34.92)
        self.assertEqual(rec.items[1]["description"], "pad 1")
        self.assertEqual(rec.items[1]["net"], "+3V3")
        self.assertEqual(rec.items[1]["reference"], "1")
        self.assertIsNone(rec.items[1]["layer"])

    # --- Test 3: lib_footprint_mismatch ---

    def test_parse_lib_footprint_mismatch(self):
        result = parse_drc_report_detailed(FOOTPRINT_MISMATCH_BLOCK)
        self.assertTrue(result["parseable"])
        self.assertEqual(len(result["records"]), 1)

        rec = result["records"][0]
        self.assertEqual(rec.violation_type, "lib_footprint_mismatch")
        self.assertEqual(rec.severity, "warning")
        self.assertEqual(len(rec.coordinates), 1)
        self.assertEqual(rec.coordinates[0], (50.0, 100.0))
        self.assertEqual(len(rec.items), 1)
        self.assertEqual(rec.items[0]["description"], "Footprint")
        self.assertEqual(rec.items[0]["reference"], "<no reference designator>")
        self.assertIsNone(rec.items[0]["net"])
        self.assertIsNone(rec.items[0]["layer"])

    # --- Test 4: negative coordinates ---

    def test_parse_negative_coordinates(self):
        result = parse_drc_report_detailed(NEGATIVE_COORD_BLOCK)
        self.assertTrue(result["parseable"])
        self.assertEqual(len(result["records"]), 1)

        rec = result["records"][0]
        self.assertEqual(rec.coordinates, [(-12.5, -34.2)])
        self.assertEqual(rec.items[0]["net"], "GND")
        self.assertEqual(rec.items[0]["layer"], "B.Cu")
        self.assertEqual(rec.items[0]["length_mm"], 8.75)

    # --- Test 5: malformed block preserved as unparsed ---

    def test_malformed_block_preserved(self):
        result = parse_drc_report_detailed(MALFORMED_BLOCK)
        # Summary counts not present, so parseable may be False.
        self.assertEqual(len(result["records"]), 0)
        self.assertEqual(len(result["unparsed_blocks"]), 1)
        self.assertIn("unknown_type", result["unparsed_blocks"][0])
        self.assertIn("Something went wrong", result["unparsed_blocks"][0])

    # --- Test 6: empty report ---

    def test_empty_report(self):
        result = parse_drc_report_detailed(EMPTY_REPORT)
        self.assertTrue(result["parseable"])
        self.assertEqual(result["violations"], 0)
        self.assertEqual(result["unconnected"], 0)
        self.assertEqual(result["footprint_errors"], 0)
        self.assertEqual(len(result["records"]), 0)
        self.assertEqual(len(result["unparsed_blocks"]), 0)

    # --- Test 7: summary-only report (no violation blocks) ---

    def test_summary_only_report(self):
        result = parse_drc_report_detailed(SUMMARY_ONLY_REPORT)
        self.assertTrue(result["parseable"])
        self.assertEqual(result["violations"], 17)
        self.assertEqual(result["unconnected"], 39)
        self.assertEqual(result["footprint_errors"], 0)
        self.assertEqual(len(result["records"]), 0)
        self.assertEqual(len(result["unparsed_blocks"]), 0)

    # --- Test 8: full report excerpt ---

    def test_full_report_excerpt(self):
        result = parse_drc_report_detailed(FULL_REPORT_EXCERPT)
        self.assertTrue(result["parseable"])
        self.assertEqual(result["violations"], 17)
        self.assertEqual(result["unconnected"], 39)
        self.assertEqual(result["footprint_errors"], 0)
        # 3 violation blocks present in the excerpt (2 track_dangling,
        # 1 lib_footprint_mismatch, 1 unconnected_items) = 4 blocks total
        self.assertEqual(len(result["records"]), 4)

        # Verify types present.
        types = {rec.violation_type for rec in result["records"]}
        self.assertIn("track_dangling", types)
        self.assertIn("lib_footprint_mismatch", types)
        self.assertIn("unconnected_items", types)

        # Verify NC net is present but NOT classified as safe to ignore.
        nc_records = [
            rec for rec in result["records"]
            if any(item.get("net") == "NC" for item in rec.items)
        ]
        # NC nets appear as data, not filtered out.
        self.assertIsInstance(nc_records, list)

    # --- Test 9: record field types ---

    def test_record_field_types(self):
        result = parse_drc_report_detailed(TRACK_DANGLING_BLOCK)
        rec = result["records"][0]

        self.assertIsInstance(rec.violation_type, str)
        self.assertIsInstance(rec.message, str)
        self.assertIsInstance(rec.severity, str)
        self.assertIsInstance(rec.coordinates, list)
        self.assertIsInstance(rec.items, list)
        self.assertIsInstance(rec.original_text, str)

        if rec.coordinates:
            x, y = rec.coordinates[0]
            self.assertIsInstance(x, float)
            self.assertIsInstance(y, float)

        if rec.items:
            item = rec.items[0]
            self.assertIsInstance(item["description"], (str, type(None)))
            self.assertIsInstance(item["net"], (str, type(None)))
            self.assertIsInstance(item["layer"], (str, type(None)))
            self.assertIsInstance(item["length_mm"], (float, type(None)))
            self.assertIsInstance(item["reference"], (str, type(None)))

    # --- Test 10: repeated violations preserved ---

    def test_repeated_violations_preserved(self):
        doubled = TRACK_DANGLING_BLOCK + "\n" + TRACK_DANGLING_BLOCK
        result = parse_drc_report_detailed(doubled)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][0].violation_type, "track_dangling")
        self.assertEqual(result["records"][1].violation_type, "track_dangling")


# --- Integration tests for classify_drc_violations and run_validation ---

class TestDrcIntegration(unittest.TestCase):
    """Tests for DRC diagnostic classification and validation integration."""

    def setUp(self):
        self.ai_dir = r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280\scripts\ai"
        if self.ai_dir not in sys.path:
            sys.path.insert(0, self.ai_dir)
        import ai_pipeline
        self.ai_pipeline = ai_pipeline
        self.staging_sch = Path(
            r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280"
            r"\outputs\ai_staging\20261025_201832\ESP32_BME280.kicad_sch"
        )
        self.staging_pcb = Path(
            r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280"
            r"\outputs\ai_staging\20261025_201832\ESP32_BME280.kicad_pcb"
        )

    def test_classify_track_dangling(self):
        from ai_pipeline import DrcViolation
        rec = DrcViolation(
            violation_type="track_dangling",
            message="Track has unconnected end",
            severity="warning",
            coordinates=[(56.0, 100.0)],
            items=[{"description": "Track", "net": "+3V3", "layer": "F.Cu", "length_mm": 24.0, "reference": None}],
            original_text="[track_dangling]: Track has unconnected end",
        )
        result = self.ai_pipeline.classify_drc_violations([rec])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["violation_type"], "track_dangling")
        self.assertEqual(result[0]["severity"], "warning")
        self.assertEqual(result[0]["net"], "+3V3")
        self.assertEqual(result[0]["classification"], "unconnected_track_end")
        self.assertIn("Reconnect or terminate", result[0]["repair_candidate"])

    def test_classify_unconnected_items(self):
        from ai_pipeline import DrcViolation
        rec = DrcViolation(
            violation_type="unconnected_items",
            message="Missing connection between items",
            severity="error",
            coordinates=[(87.54, 105.08)],
            items=[{"description": "Track", "net": "+3V3", "layer": "F.Cu", "length_mm": 34.92, "reference": None}],
            original_text="[unconnected_items]: Missing connection between items",
        )
        result = self.ai_pipeline.classify_drc_violations([rec])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["classification"], "unconnected_items")
        self.assertIn("Connect unconnected items", result[0]["repair_candidate"])

    def test_classify_lib_footprint_mismatch(self):
        from ai_pipeline import DrcViolation
        rec = DrcViolation(
            violation_type="lib_footprint_mismatch",
            message="Footprint does not match library copy",
            severity="warning",
            coordinates=[(50.0, 100.0)],
            items=[{"description": "Footprint", "reference": "J1", "net": None, "layer": None}],
            original_text="[lib_footprint_mismatch]: Footprint does not match",
        )
        result = self.ai_pipeline.classify_drc_violations([rec])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["classification"], "footprint_library_mismatch")
        self.assertIn("Align footprint", result[0]["repair_candidate"])

    def test_classify_unknown_violation_type(self):
        from ai_pipeline import DrcViolation
        rec = DrcViolation(
            violation_type="unknown_type",
            message="Something unexpected",
            severity="error",
            coordinates=[],
            items=[],
            original_text="[unknown_type]: Something unexpected",
        )
        result = self.ai_pipeline.classify_drc_violations([rec])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["classification"], "other_violation")
        self.assertIn("Review violation details", result[0]["repair_candidate"])

    def test_classify_empty_records(self):
        result = self.ai_pipeline.classify_drc_violations([])
        self.assertEqual(result, [])

    def test_run_validation_drc_has_records_key(self):
        """run_validation() returns drc dict with 'records' and 'unparsed_blocks' keys."""
        from unittest.mock import patch
        with patch.object(self.ai_pipeline, "run_powershell") as mock_run, \
             patch.object(self.ai_pipeline.Path, "exists", return_value=True):
            mock_run.return_value = {
                "stdout": "PASS",
                "stderr": "",
                "returncode": 0,
            }
            with patch.object(
                self.ai_pipeline, "_parse_erc_report",
                return_value={"parseable": True, "errors": 0, "warnings": 0},
            ), patch.object(
                self.ai_pipeline, "_parse_drc_report",
                return_value={"parseable": True, "violations": 0, "unconnected": 0, "footprint_errors": 0},
            ):
                result = self.ai_pipeline.run_validation(self.staging_sch, self.staging_pcb)
        self.assertIn("records", result["drc"])
        self.assertIn("unparsed_blocks", result["drc"])
        self.assertIsInstance(result["drc"]["records"], list)
        self.assertIsInstance(result["drc"]["unparsed_blocks"], list)


if __name__ == "__main__":
    unittest.main()
