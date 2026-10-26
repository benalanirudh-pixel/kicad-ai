#!/usr/bin/env python3
"""
AI Prompt-to-PCB Pipeline Orchestrator.

End-to-end flow:
  1. Accept a free-text PCB prompt
  2. Generate KiCad .kicad_sch / .kicad_pcb via LLM interface (code-based or API)
  3. Write to staging directory (outputs/ai_staging/<run_id>/)
  4. Run ERC + DRC validation via validate_project.ps1
  5. Self-healing loop: parse violations, regenerate, re-validate (max 5 iterations)
  6. Report results; await user approval before copying to active project (gate G1-G2)
  7. On approval: copy staging files to active project
  8. Export manufacturing files via export_manufacturing.ps1 (gate G5)
  9. Verify outputs via check_outputs.ps1

Safety:
  - Never modifies active .kicad_sch / .kicad_pcb without explicit approval
  - Never deletes KiCad lock files or terminates KiCad processes
  - Manufacturing export only after clean validation + approval
"""

import sys
import os
import shutil
import subprocess
import json
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path

# Add scripts/ai to path for imports
AI_DIR = os.path.dirname(os.path.abspath(__file__))
if AI_DIR not in sys.path:
    sys.path.insert(0, AI_DIR)

from llm_interface import KiCadLLMInterface, HardwareSpec, extract_hardware_spec
from hardware_profile import (
    HardwareProfile,
    gate_electrical_schematic,
    gate_mechanical_footprint,
    gate_fabrication_release,
)

# --------------------------------------------------------------------------- paths

PROJECT_ROOT = Path(r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280")
KICAD_CLI = r"C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"
SCH_FILE = PROJECT_ROOT / "ESP32_BME280.kicad_sch"
PCB_FILE = PROJECT_ROOT / "ESP32_BME280.kicad_pcb"
# Preserve original active-file paths for the test-mode guard in
# copy_staging_to_active(). Tests must patch SCH_FILE / PCB_FILE to
# isolated temporary paths; this guard prevents accidental mutation of
# the real project files during test execution.
_ORIGINAL_SCH_FILE = SCH_FILE
_ORIGINAL_PCB_FILE = PCB_FILE
STAGING_ROOT = PROJECT_ROOT / "outputs" / "ai_staging"
VALIDATION_DIR = PROJECT_ROOT / "outputs" / "validation"
MANUFACTURING_DIR = PROJECT_ROOT / "outputs" / "manufacturing"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
HARDWARE_PROFILE_PATH = PROJECT_ROOT / "hardware_profile.json"

MAX_SELF_HEAL_ITERATIONS = 5

# --------------------------------------------------------------------------- helpers

def run_powershell(script_path: Path, args: list, timeout=120) -> dict:
    """Run a PowerShell script and return stdout, stderr, returncode."""
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
        }


def run_environment_check() -> bool:
    """Run check_environment.ps1 to verify the automation environment."""
    print("\n=== Step 1: Environment Check ===")
    result = run_powershell(
        SCRIPTS_DIR / "check_environment.ps1",
        [
            "-ProjectDir", str(PROJECT_ROOT),
            "-KicadCli", KICAD_CLI,
        ],
    )
    print(result["stdout"])
    if result["stderr"]:
        print("STDERR:", result["stderr"])
    return result["returncode"] == 0


def load_hardware_profile(path: Optional[Path] = None) -> HardwareProfile:
    """Load hardware profile from project-relative path.

    Returns an empty (all-unresolved) profile if the file does not exist,
    which fail-closes every gate. Raises ValueError if the file exists
    but has invalid schema.
    """
    if path is None:
        path = HARDWARE_PROFILE_PATH
    return HardwareProfile.from_file(path)


def write_staging_files(run_id: str, sch_content: str, pcb_content: str) -> dict:
    """Write generated KiCad files to the staging directory."""
    staging_dir = STAGING_ROOT / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)

    sch_path = staging_dir / "ESP32_BME280.kicad_sch"
    pcb_path = staging_dir / "ESP32_BME280.kicad_pcb"

    sch_path.write_text(sch_content, encoding="utf-8")
    pcb_path.write_text(pcb_content, encoding="utf-8")

    return {
        "staging_dir": staging_dir,
        "sch_path": sch_path,
        "pcb_path": pcb_path,
    }


def _sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file, or empty string if missing."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _attempt_recovery(journal: Path) -> None:
    """Detect and recover from an interrupted copy_staging_to_active() run.

    Reads the journal file to find backup and active file paths. If a backup
    exists and the active file's current hash matches the staging hash (meaning
    our replace was the last write), restores the active file from backup.
    If the active file was modified externally (hash differs from both staging
    and backup), the backup is preserved and a warning is printed. Recovery
    never blindly overwrites unexpected external changes.

    The journal file is removed after recovery (success or skip). If recovery
    itself fails, the journal and backups are preserved for manual intervention.
    """
    print(f"[RECOVERY] Found stale journal from interrupted operation: {journal}")
    try:
        data = json.loads(journal.read_text(encoding="utf-8"))

        for file_key in ("sch", "pcb"):
            bak_path = Path(data[f"backup_{file_key}"])
            active_path = Path(data[f"active_{file_key}"])
            staging_hash = data.get(f"staging_{file_key}_hash")

            if not bak_path.exists() or not active_path.exists():
                continue

            if os.environ.get("KILICODE_TEST_MODE") == "1":
                try:
                    real_sch = _ORIGINAL_SCH_FILE.resolve()
                    real_pcb = _ORIGINAL_PCB_FILE.resolve()
                    if active_path.resolve() in (real_sch, real_pcb):
                        # Never recover into the real active project during tests.
                        # Preserve the backup and journal as evidence instead.
                        continue
                except Exception:
                    pass

            current_hash = _sha256_file(active_path)
            backup_hash = _sha256_file(bak_path)

            if staging_hash and current_hash == staging_hash:
                os.replace(bak_path, active_path)
                print(f"[RECOVERY] Restored {active_path} from {bak_path}")
            elif current_hash == backup_hash:
                print(f"[RECOVERY] No recovery needed for {active_path}")
            else:
                print(f"[WARN] {active_path} has been modified externally since the interrupted run.")
                print(f"  Backup preserved at {bak_path} for manual review.")

        journal.unlink()
        print("[RECOVERY] Journal cleaned up.")

    except Exception as e:
        print(f"[WARN] Could not complete recovery from journal: {e}")
        print(f"  Manual intervention may be required. Journal preserved: {journal}")


def copy_staging_to_active(staging_dir: Path) -> bool:
    """Copy staging files to the active project.

    Requires hardware electrical and mechanical gates to pass before
    any active file is written.

    Uses a backup-then-rename pattern with a journal for crash recovery:
      1. Check for stale journal from a previously interrupted run.
      2. Write a journal file recording backup paths, active paths, and
         staging content hashes (before any active file is modified).
      3. Back up originals to .bak_<pid> temp files (same directory).
      4. Write new content to .tmp_<pid> temp files (same directory).
      5. Atomically rename temp to active for each file via os.replace().
      6. If the second rename fails, restore the first file from backup.
         If the rollback also fails, the backup is preserved and its path
         is printed for manual recovery.
      7. Remove the journal only after both active files are committed.
      8. Clean up all temp/backup files in finally (unless preserved).

    Limitation: a crash between the two os.replace() calls can be recovered
    on the next run via the journal. The backup files are preserved across
    runs if needed. Full crash-atomicity for both files simultaneously is not
    possible without transactional filesystem support.
    """
    # --- Hardware gate: fail closed before any active file is written ---
    # Hard guard: in test mode, reject active-project file paths to prevent
    # accidental mutation of the real project during tests. Compares resolved
    # paths (not object identity) so a mock cannot redirect the call into
    # writing the real project.
    if os.environ.get("KILICODE_TEST_MODE") == "1":
        real_sch = _ORIGINAL_SCH_FILE.resolve()
        real_pcb = _ORIGINAL_PCB_FILE.resolve()
        cur_sch = Path(SCH_FILE).resolve()
        cur_pcb = Path(PCB_FILE).resolve()
        if cur_sch == real_sch or cur_pcb == real_pcb:
            raise RuntimeError(
                "TEST MODE guard: copy_staging_to_active() called with "
                "active-project file paths. Tests must patch "
                "ai_pipeline.SCH_FILE and ai_pipeline.PCB_FILE to isolated "
                "temporary paths before calling this function."
            )

    try:
        profile = load_hardware_profile()
    except ValueError as exc:
        print(f"\n[BLOCKED] Invalid hardware profile: {exc}")
        return False

    elec_result = gate_electrical_schematic(profile)
    if not elec_result.allowed:
        print(f"\n[BLOCKED] Hardware electrical gate failed for active file copy:")
        print(f"  {elec_result.reason}")
        return False

    mech_result = gate_mechanical_footprint(profile)
    if not mech_result.allowed:
        print(f"\n[BLOCKED] Hardware mechanical gate failed for active file copy:")
        print(f"  {mech_result.reason}")
        return False

    # --- Both gates passed: back up, then replace ---
    src_sch = staging_dir / "ESP32_BME280.kicad_sch"
    src_pcb = staging_dir / "ESP32_BME280.kicad_pcb"

    pid = os.getpid()
    tmp_sch = SCH_FILE.parent / f"{SCH_FILE.name}.tmp_{pid}"
    tmp_pcb = PCB_FILE.parent / f"{PCB_FILE.name}.tmp_{pid}"
    bak_sch = SCH_FILE.parent / f"{SCH_FILE.name}.bak_{pid}"
    bak_pcb = PCB_FILE.parent / f"{PCB_FILE.name}.bak_{pid}"
    journal = SCH_FILE.parent / f"{SCH_FILE.name}.journal_{pid}"

    replaced_sch = False
    replaced_pcb = False
    preserve_backups = False

    try:
        # Phase 0: Crash recovery - check for stale journal from a previous
        # interrupted run. Must happen before any new backups are created.
        if journal.exists():
            _attempt_recovery(journal)

        # Phase 1: Write journal BEFORE any active file is modified.
        staging_sch_hash = _sha256_file(src_sch) if src_sch.exists() else None
        staging_pcb_hash = _sha256_file(src_pcb) if src_pcb.exists() else None
        journal.write_text(json.dumps({
            "backup_sch": str(bak_sch),
            "backup_pcb": str(bak_pcb),
            "active_sch": str(SCH_FILE),
            "active_pcb": str(PCB_FILE),
            "staging_sch_hash": staging_sch_hash,
            "staging_pcb_hash": staging_pcb_hash,
            "status": "pending",
        }), encoding="utf-8")

        # Phase 2: Back up originals (only if they currently exist).
        if SCH_FILE.exists():
            shutil.copy2(SCH_FILE, bak_sch)
        if PCB_FILE.exists():
            shutil.copy2(PCB_FILE, bak_pcb)

        # Phase 3: Write new content to temp files.
        shutil.copy2(src_sch, tmp_sch)
        shutil.copy2(src_pcb, tmp_pcb)

        # Phase 4: Atomically replace active files.
        os.replace(tmp_sch, SCH_FILE)
        replaced_sch = True
        os.replace(tmp_pcb, PCB_FILE)
        replaced_pcb = True

        print(f"[APPROVED] Copied staging files to active project:")
        print(f"  {SCH_FILE}")
        print(f"  {PCB_FILE}")

        # Phase 5: Transaction committed - remove journal.
        try:
            journal.unlink()
        except Exception:
            pass

        return True

    except Exception as e:
        print(f"[FAIL] Failed to copy staging files: {e}")

        # Rollback: if first file was replaced but second failed,
        # restore the first file from its backup so both active files
        # retain their original bytes.
        if replaced_sch and not replaced_pcb and bak_sch.exists():
            try:
                os.replace(bak_sch, SCH_FILE)
                print(f"[ROLLBACK] Restored {SCH_FILE} from backup after failure.")
            except Exception as rb_exc:
                preserve_backups = True
                print(f"[ERROR] Failed to rollback {SCH_FILE}: {rb_exc}")
                print(f"  Manual restore from {bak_sch} required."
                      f" Backup preserved for manual recovery.")

        return False

    finally:
        # Always clean up temp files (safe to delete regardless of state).
        for tmp in (tmp_sch, tmp_pcb):
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

        if preserve_backups:
            # Critical: do NOT delete backup files that may be the only
            # remaining copy of the original data. Preserve them for manual
            # recovery and print their exact paths.
            if bak_sch.exists():
                print(f"[PRESERVE] Backup file retained for manual recovery: {bak_sch}")
            if bak_pcb.exists():
                print(f"[PRESERVE] Backup file retained for manual recovery: {bak_pcb}")
        else:
            # Safe to delete backup and journal files.
            for tmp in (bak_sch, bak_pcb):
                try:
                    if tmp.exists():
                        tmp.unlink()
                except Exception:
                    pass
            try:
                if journal.exists():
                    journal.unlink()
            except Exception:
                pass


def run_validation(sch_path: Path, pcb_path: Path, output_dir: Path = VALIDATION_DIR) -> dict:
    """Run validate_project.ps1 against staging files without touching active project files.

    Copies the supplied schematic and PCB into an isolated temporary workspace,
    runs validate_project.ps1 against that workspace, and writes reports to a
    dedicated staging-validation directory. The active project schematic and PCB
    paths are never write targets during validation.

    Returns parsed ERC/DRC results (same contract as before).
    """
    import tempfile
    import uuid

    # Build an isolated workspace so the active project files are never written.
    workspace = Path(tempfile.mkdtemp(prefix="kicad_val_"))
    try:
        sch_copy = workspace / "ESP32_BME280.kicad_sch"
        pcb_copy = workspace / "ESP32_BME280.kicad_pcb"
        shutil.copy2(sch_path, sch_copy)
        shutil.copy2(pcb_path, pcb_copy)

        # Dedicated staging-validation output directory, isolated from active reports.
        run_id = uuid.uuid4().hex
        report_dir = PROJECT_ROOT / "outputs" / "ai_staging_validation" / run_id
        report_dir.mkdir(parents=True, exist_ok=True)

        result = run_powershell(
            SCRIPTS_DIR / "validate_project.ps1",
            [
                "-ProjectDir", str(workspace),
                "-KicadCli", KICAD_CLI,
                "-OutputDir", str(report_dir),
            ],
        )

        erc_report = report_dir / "ESP32_BME280_erc_report.txt"
        drc_report = report_dir / "ESP32_BME280_drc_report.txt"

        erc = _parse_erc_report(erc_report) if erc_report.exists() else {"parseable": False, "errors": -1, "warnings": -1}
        drc = _parse_drc_report(drc_report) if drc_report.exists() else {"parseable": False, "violations": -1, "unconnected": -1, "footprint_errors": -1}
        drc["records"] = []
        drc["unparsed_blocks"] = []
        if drc_report.is_file():
            drc_detailed = parse_drc_report_detailed(drc_report.read_text(encoding="utf-8", errors="replace"))
            drc["records"] = drc_detailed["records"]
            drc["unparsed_blocks"] = drc_detailed["unparsed_blocks"]

        return {
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "returncode": result["returncode"],
            "erc": erc,
            "drc": drc,
            "erc_report": str(erc_report),
            "drc_report": str(drc_report),
            "clean": (
                erc.get("parseable", False)
                and erc.get("errors", 0) == 0
                and erc.get("warnings", 0) == 0
                and drc.get("parseable", False)
                and drc.get("violations", 0) == 0
                and drc.get("unconnected", 0) == 0
                and drc.get("footprint_errors", 0) == 0
            ),
        }
    finally:
        # Clean up the isolated workspace only; never touch active project files
        # or pre-existing reports.
        shutil.rmtree(workspace, ignore_errors=True)


def _parse_erc_report(path: Path) -> dict:
    content = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"ERC messages:\s*\d+\s*Errors\s*(\d+)\s*Warnings\s*(\d+)", content)
    if m:
        return {
            "parseable": True,
            "errors": int(m.group(1)),
            "warnings": int(m.group(2)),
        }
    return {"parseable": False, "errors": -1, "warnings": -1}


def _parse_drc_report(path: Path) -> dict:
    content = path.read_text(encoding="utf-8", errors="replace")
    result = {"parseable": False, "violations": -1, "unconnected": -1, "footprint_errors": -1}
    m = re.search(r"Found\s+(\d+)\s+DRC violations", content)
    if m:
        result["violations"] = int(m.group(1))
    m = re.search(r"Found\s+(\d+)\s+unconnected pads", content)
    if m:
        result["unconnected"] = int(m.group(1))
    m = re.search(r"Found\s+(\d+)\s+Footprint errors", content)
    if m:
        result["footprint_errors"] = int(m.group(1))
    if result["violations"] >= 0 and result["unconnected"] >= 0 and result["footprint_errors"] >= 0:
        result["parseable"] = True
    return result


# --------------------------------------------------------------------------- detailed DRC parser

@dataclass
class DrcViolation:
    """A single parsed DRC violation record from a KiCad 10 DRC report.

    Fields:
        violation_type:  e.g. "track_dangling", "unconnected_items",
                         "lib_footprint_mismatch"
        message:         human-readable message after the type tag
        severity:        "warning" or "error" (from "Local override; ...")
        coordinates:     list of (x_mm, y_mm) tuples; one or two items per
                         violation block
        items:           list of dicts, each with keys:
            - description: str   (e.g. "Track", "pad 1", "Footprint")
            - net:         str or None (e.g. "+3V3", "GND", "I2C_SDA", "NC")
            - layer:       str or None (e.g. "F.Cu", "B.Cu")
            - length_mm:   float or None (track length when present)
            - reference:   str or None (pad number when present)
        original_text:   full raw violation block text
    """
    violation_type: str
    message: str
    severity: str
    coordinates: List[Tuple[float, float]] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)
    original_text: str = ""


# Regex patterns for KiCad 10 DRC report format.
VIOLATION_HEADER_RE = re.compile(r"^\[([^\]]+)\]:\s*(.+)$")
SEVERITY_RE = re.compile(r"^    Local override;\s*(warning|error)$")
ITEM_RE = re.compile(
    r"^    @\(([-\d.]+)\s*mm,\s*([-\d.]+)\s*mm\):\s*(.+)$"
)
# Track item: Track [+3V3] on F.Cu, length 24.0000 mm
TRACK_ITEM_RE = re.compile(
    r"^Track\s+\[([^\]]+)\]\s+on\s+(\S+),\s*length\s+([\d.]+)\s*mm$"
)
# Pad item: PTH pad 1 [+3V3] of  or Pad 1 [+3V3] of  on F.Cu
PAD_ITEM_RE = re.compile(
    r"^(?:PTH\s+)?pad\s+(\d+)\s+\[([^\]]+)\]\s+of(?:\s+on\s+(\S+))?\s*$"
)
# Footprint item: Footprint <no reference designator>
FOOTPRINT_ITEM_RE = re.compile(r"^Footprint\s+(.+)$")


def _split_into_violation_blocks(lines: List[str]) -> List[dict]:
    """Split report lines into violation blocks.

    Each block starts at a ``[type]: message`` header line and continues
    until the next header line or end of input.
    """
    blocks: List[dict] = []
    current: Optional[dict] = None

    for line in lines:
        header_match = VIOLATION_HEADER_RE.match(line)
        if header_match:
            if current is not None:
                blocks.append(current)
            current = {
                "violation_type": header_match.group(1),
                "message": header_match.group(2),
                "lines": [line],
            }
        elif current is not None:
            current["lines"].append(line)

    if current is not None:
        blocks.append(current)

    return blocks


def _parse_item_details(details: str) -> Dict[str, Any]:
    """Parse the item detail text from a DRC item line.

    Returns a dict with keys: description, net, layer, length_mm, reference.
    Unknown fields are None.
    """
    item: Dict[str, Any] = {
        "description": None,
        "net": None,
        "layer": None,
        "length_mm": None,
        "reference": None,
    }

    # Track pattern: Track [+3V3] on F.Cu, length 24.0000 mm
    tm = TRACK_ITEM_RE.match(details)
    if tm:
        item["description"] = "Track"
        item["net"] = tm.group(1)
        item["layer"] = tm.group(2)
        item["length_mm"] = float(tm.group(3))
        return item

    # Pad pattern: PTH pad 1 [+3V3] of  or Pad 1 [+3V3] of  on F.Cu
    pm = PAD_ITEM_RE.match(details)
    if pm:
        item["description"] = f"pad {pm.group(1)}"
        item["net"] = pm.group(2)
        item["reference"] = pm.group(1)
        if pm.group(3):
            item["layer"] = pm.group(3)
        return item

    # Footprint pattern: Footprint <no reference designator>
    fm = FOOTPRINT_ITEM_RE.match(details)
    if fm:
        item["description"] = "Footprint"
        item["reference"] = fm.group(1).strip()
        return item

    # Unknown format — preserve the raw detail text.
    item["description"] = details
    return item


def _parse_violation_block(block: dict) -> Optional[DrcViolation]:
    """Parse a single violation block into a DrcViolation record.

    Returns None if the block is malformed (no severity line found).
    """
    lines = block["lines"]

    # Find severity line.
    severity: Optional[str] = None
    severity_idx = -1
    for i, line in enumerate(lines):
        sm = SEVERITY_RE.match(line)
        if sm:
            severity = sm.group(1)
            severity_idx = i
            break

    if severity is None:
        return None  # Malformed block — no severity line.

    # Parse item lines (everything after severity).
    items: List[Dict[str, Any]] = []
    coordinates: List[Tuple[float, float]] = []

    for line in lines[severity_idx + 1 :]:
        im = ITEM_RE.match(line)
        if not im:
            continue
        x_mm = float(im.group(1))
        y_mm = float(im.group(2))
        details = im.group(3)
        coordinates.append((x_mm, y_mm))
        items.append(_parse_item_details(details))

    return DrcViolation(
        violation_type=block["violation_type"],
        message=block["message"],
        severity=severity,
        coordinates=coordinates,
        items=items,
        original_text="\n".join(lines),
    )


def parse_drc_report_detailed(content: str) -> dict:
    """Parse individual DRC violation records from a KiCad 10 DRC report.

    Args:
        content: Full text content of the DRC report file.

    Returns:
        dict with keys:
            - parseable:        bool  (True if summary counts were found)
            - violations:       int   (summary count of DRC violations)
            - unconnected:      int   (summary count of unconnected pads)
            - footprint_errors: int   (summary count of footprint errors)
            - records:          list[DrcViolation]  (parsed violation records)
            - unparsed_blocks:  list[str]  (raw text of blocks that could not be parsed)

    Unknown or malformed blocks are preserved in ``unparsed_blocks``, not
    silently discarded. Empty reports and summary-only reports are handled.
    """
    result: Dict[str, Any] = {
        "parseable": False,
        "violations": -1,
        "unconnected": -1,
        "footprint_errors": -1,
        "records": [],
        "unparsed_blocks": [],
    }

    # Parse summary counts.
    m = re.search(r"Found\s+(\d+)\s+DRC violations", content)
    if m:
        result["violations"] = int(m.group(1))
    m = re.search(r"Found\s+(\d+)\s+unconnected pads", content)
    if m:
        result["unconnected"] = int(m.group(1))
    m = re.search(r"Found\s+(\d+)\s+Footprint errors", content)
    if m:
        result["footprint_errors"] = int(m.group(1))

    if (
        result["violations"] >= 0
        and result["unconnected"] >= 0
        and result["footprint_errors"] >= 0
    ):
        result["parseable"] = True

    # Split into violation blocks and parse each.
    lines = content.split("\n")
    blocks = _split_into_violation_blocks(lines)

    for block in blocks:
        record = _parse_violation_block(block)
        if record is not None:
            result["records"].append(record)
        else:
            result["unparsed_blocks"].append("\n".join(block["lines"]))

    return result


def classify_drc_violations(records: list) -> list[dict]:
    """Classify parsed DRC violation records into diagnostic categories.

    Diagnostic-only: produces candidate repair descriptions without
    modifying any schematic or PCB content.

    Args:
        records: List of DrcViolation records from parse_drc_report_detailed().

    Returns:
        List of dicts with keys: violation_type, severity, coordinates,
        net, classification, repair_candidate.
    """
    classifications: list[dict] = []
    for rec in records:
        repair = _repair_candidate_for_violation(rec)
        classifications.append({
            "violation_type": rec.violation_type,
            "severity": rec.severity,
            "coordinates": rec.coordinates,
            "net": rec.items[0]["net"] if rec.items else None,
            "classification": _classify_violation_type(rec.violation_type),
            "repair_candidate": repair,
        })
    return classifications


def _classify_violation_type(violation_type: str) -> str:
    """Map a DRC violation type to a diagnostic category."""
    type_map = {
        "track_dangling": "unconnected_track_end",
        "unconnected_items": "unconnected_items",
        "lib_footprint_mismatch": "footprint_library_mismatch",
    }
    return type_map.get(violation_type, "other_violation")


def _repair_candidate_for_violation(rec) -> str:
    """Produce a candidate repair description for a single DrcViolation."""
    vt = rec.violation_type
    if vt == "track_dangling":
        net = rec.items[0]["net"] if rec.items else None
        layer = rec.items[0]["layer"] if rec.items else None
        length = rec.items[0]["length_mm"] if rec.items else None
        return (
            f"Reconnect or terminate dangling track on net '{net}' "
            f"(layer {layer}, length {length} mm) to a valid pad or route end."
        )
    if vt == "unconnected_items":
        return (
            "Connect unconnected items to their assigned nets or add "
            "explicit no-connect markers where intentional."
        )
    if vt == "lib_footprint_mismatch":
        ref = rec.items[0]["reference"] if rec.items else None
        return (
            f"Align footprint {ref or ''} with library copy or update "
            "library reference to match placed footprint."
        )
    return "Review violation details and apply appropriate fix based on type and severity."


def run_manufacturing_export(confirm_yes=False, force=False):
    """Run export_manufacturing.ps1 to export Gerbers and drill files.

    Requires the hardware fabrication gate to pass before invoking the
    PowerShell exporter. Neither confirm_yes nor force can override a
    failed profile gate — the gate always runs first.
    """
    # --- Hardware gate: fail closed before any subprocess or output change ---
    try:
        profile = load_hardware_profile()
    except ValueError as exc:
        print(f"\n[BLOCKED] Invalid hardware profile: {exc}")
        return False

    fab_result = gate_fabrication_release(profile)
    if not fab_result.allowed:
        print(f"\n[BLOCKED] Hardware fabrication gate failed for manufacturing export:")
        print(f"  {fab_result.reason}")
        print(f"  Blocking assumptions: {fab_result.blocking_assumptions}")
        if fab_result.conflicts:
            print(f"  Conflicts: {fab_result.conflicts}")
        return False

    # --- Fabrication gate passed: build args and invoke exporter ---
    args = [
        "-ProjectDir", str(PROJECT_ROOT),
        "-KicadCli", KICAD_CLI,
    ]
    if confirm_yes:
        args += ["-Confirm", "yes"]
    if force:
        args.append("-Force")

    print("\n=== Step 5: Manufacturing Export ===")
    result = run_powershell(
        SCRIPTS_DIR / "export_manufacturing.ps1",
        args,
        timeout=300,
    )
    print(result["stdout"])
    if result["stderr"]:
        print("STDERR:", result["stderr"])
    return result["returncode"] == 0


def run_output_checks() -> bool:
    """Run check_outputs.ps1 to verify manufacturing outputs."""
    print("\n=== Step 6: Output Verification ===")
    result = run_powershell(
        SCRIPTS_DIR / "check_outputs.ps1",
        [
            "-ProjectDir", str(PROJECT_ROOT),
            "-CheckManufacturing",
            "-CheckValidation",
        ],
    )
    print(result["stdout"])
    if result["stderr"]:
        print("STDERR:", result["stderr"])
    return result["returncode"] == 0


def print_validation_results(iteration: int, validation: dict):
    """Print validation results for an iteration."""
    erc = validation["erc"]
    drc = validation["drc"]
    print(f"\n--- Validation Iteration {iteration} ---")
    print(f"  ERC: errors={erc.get('errors', '?')}, warnings={erc.get('warnings', '?')}, parseable={erc.get('parseable', False)}")
    print(f"  DRC: violations={drc.get('violations', '?')}, unconnected={drc.get('unconnected', '?')}, footprint_errors={drc.get('footprint_errors', '?')}, parseable={drc.get('parseable', False)}")
    print(f"  Clean: {validation['clean']}")
    if not validation["clean"]:
        print("  Violations detected — self-healing loop will attempt fixes.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python ai_pipeline.py \"<prompt>\"")
        print('Example: python ai_pipeline.py "ESP32 DevKit V1 with BME280 over I2C, 3.3V power, 4.7k pull-ups"')
        sys.exit(1)

    prompt = sys.argv[1]
    print(f"Prompt: {prompt}")
    print(f"Project: {PROJECT_ROOT}")
    print(f"KiCad CLI: {KICAD_CLI}")

    # ---- Step 1: Environment check ----
    if not run_environment_check():
        print("\n[FAIL] Environment check failed. Aborting.")
        sys.exit(1)

    # ---- Step 1.5: Hardware profile gate ----
    try:
        profile = load_hardware_profile()
    except ValueError as exc:
        print(f"\n[BLOCKED] Invalid hardware profile: {exc}")
        sys.exit(1)

    # Electrical gate before any schematic generation.
    elec_result = gate_electrical_schematic(profile)
    if not elec_result.allowed:
        print("\n[BLOCKED] Hardware electrical gate failed before schematic generation:")
        print(f"  {elec_result.reason}")
        print(f"  Blocking assumptions: {elec_result.blocking_assumptions}")
        if elec_result.conflicts:
            print(f"  Conflicts: {elec_result.conflicts}")
        sys.exit(1)

    # Mechanical gate before any PCB/footprint generation.
    mech_result = gate_mechanical_footprint(profile)
    if not mech_result.allowed:
        print("\n[BLOCKED] Hardware mechanical gate failed before footprint placement:")
        print(f"  {mech_result.reason}")
        print(f"  Blocking assumptions: {mech_result.blocking_assumptions}")
        if mech_result.conflicts:
            print(f"  Conflicts: {mech_result.conflicts}")
        sys.exit(1)

    # ---- Step 2-4: Generate, stage, validate, self-heal ----
    llm = KiCadLLMInterface(use_llm_api=False)
    result = llm.generate_from_prompt(prompt)
    spec = result["spec"]
    run_id = result["run_id"]

    print(f"\nRun ID: {run_id}")
    print(f"Hardware spec: MCU={spec.mcu}, Sensor={spec.sensor}, Interface={spec.interface}")
    print(f"  SDA=GPIO{spec.sda_pin}, SCL=GPIO{spec.scl_pin}, Supply={spec.supply_voltage}, Pull-ups={spec.pullup_value}")

    staging = write_staging_files(run_id, result["schematic"], result["pcb"])
    print(f"Staging directory: {staging['staging_dir']}")

    validation = None
    iteration = 0

    for iteration in range(1, MAX_SELF_HEAL_ITERATIONS + 1):
        print(f"\n=== Generation {iteration} / Validation ===")
        validation = run_validation(staging["sch_path"], staging["pcb_path"])
        print_validation_results(iteration, validation)

        if validation["clean"]:
            print(f"\n[PASS] Design is clean after {iteration} iteration(s).")
            break

        if iteration < MAX_SELF_HEAL_ITERATIONS:
            print(f"\n[HEAL] Attempting self-healing iteration {iteration + 1}...")
            erc_report_path = Path(validation["erc_report"])
            drc_report_path = Path(validation["drc_report"])
            erc_content = erc_report_path.read_text(encoding="utf-8", errors="replace") if erc_report_path.exists() else ""
            drc_content = drc_report_path.read_text(encoding="utf-8", errors="replace") if drc_report_path.exists() else ""

            # Parse DRC report into structured records for diagnostic classification.
            drc_detailed = parse_drc_report_detailed(drc_content) if drc_content else {
                "parseable": False, "violations": -1, "unconnected": -1,
                "footprint_errors": -1, "records": [], "unparsed_blocks": [],
            }
            drc_classifications = classify_drc_violations(drc_detailed["records"])

            print(f"\n  DRC Diagnostic Classifications ({len(drc_classifications)} records):")
            for cls in drc_classifications:
                print(f"    - {cls['violation_type']} ({cls['severity']}): {cls['repair_candidate']}")

            result = llm.improve_from_violations(
                prompt, spec, erc_content, drc_content, run_id
            )
            staging = write_staging_files(run_id, result["schematic"], result["pcb"])
            spec = result["spec"]
        else:
            print(f"\n[WARN] Max self-healing iterations ({MAX_SELF_HEAL_ITERATIONS}) reached.")
            break

    if not validation or not validation["clean"]:
        print(f"\n[FAIL] Design could not be made clean after {iteration} iteration(s).")
        print(f"Review reports at: {VALIDATION_DIR}")
        sys.exit(1)

    # Re-check electrical gate before schematic approval (G1-G2).
    elec_result = gate_electrical_schematic(profile)
    if not elec_result.allowed:
        print("\n[BLOCKED] Hardware electrical gate failed before schematic approval (G1-G2):")
        print(f"  {elec_result.reason}")
        print(f"  Blocking assumptions: {elec_result.blocking_assumptions}")
        if elec_result.conflicts:
            print(f"  Conflicts: {elec_result.conflicts}")
        sys.exit(1)

    # ---- Step 6: User approval gate ----
    print("\n" + "=" * 60)
    print("APPROVAL GATE (G1-G2): Copy staging to active project?")
    print("=" * 60)
    print(f"Staging: {staging['staging_dir']}")
    print(f"Active:  {PROJECT_ROOT}")
    print()
    print("This will overwrite:")
    print(f"  {SCH_FILE}")
    print(f"  {PCB_FILE}")
    print()
    response = input("Type 'yes' to approve and proceed: ").strip().lower()
    if response != "yes":
        print("[ABORTED] User did not approve. Staging files preserved at:", staging["staging_dir"])
        sys.exit(0)

    if not copy_staging_to_active(staging["staging_dir"]):
        print("[FAIL] Failed to copy staging files to active project.")
        sys.exit(1)

    # ---- Step 7: Manufacturing export (gate G5) ----
    # Fabrication gate before manufacturing export.
    fab_result = gate_fabrication_release(profile)
    if not fab_result.allowed:
        print("\n[BLOCKED] Hardware fabrication gate failed before manufacturing export:")
        print(f"  {fab_result.reason}")
        print(f"  Blocking assumptions: {fab_result.blocking_assumptions}")
        if fab_result.conflicts:
            print(f"  Conflicts: {fab_result.conflicts}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("MANUFACTURING EXPORT GATE (G5)")
    print("=" * 60)
    response = input("Type 'yes' to export Gerbers and drill files: ").strip().lower()
    if response != "yes":
        print("[SKIPPED] Manufacturing export skipped by user.")
        print("Active project files are updated but not exported.")
        sys.exit(0)

    if not run_manufacturing_export(confirm_yes=True):
        print("[FAIL] Manufacturing export failed.")
        sys.exit(1)

    # ---- Step 8: Output verification ----
    if not run_output_checks():
        print("[FAIL] Output verification failed.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Prompt: {prompt}")
    print(f"Run ID: {run_id}")
    print(f"Schematic: {SCH_FILE}")
    print(f"PCB: {PCB_FILE}")
    print(f"Manufacturing: {MANUFACTURING_DIR}")
    print()
    print("NOTE: ERC/DRC are design-rule checks only. They do NOT replace")
    print("hardware testing or functional verification (e.g., Wokwi simulation).")


if __name__ == "__main__":
    main()