#!/usr/bin/env python3
"""
Standalone hardware profile gate-check entry point.

Intended to be called by scripts\\export_manufacturing.ps1 as a preflight
check. Exits with code 0 if the fabrication release gate passes,
or exit code 1 if the gate fails or the profile is missing/malformed.

This script reuses hardware_profile.py gate functions — it does NOT
reimplement U1-U7 policy. Paths resolve from the supplied --project-dir
parameter (which comes from the caller), never from the CWD.

Usage:
    python check_hardware_gates.py --project-dir DIR

Exit codes:
    0  Gate passed — profiles verified and at least one footprint verified.
    1  Gate failed — missing profile, invalid JSON, unverified assumptions,
       conflicting evidence, or no verified footprint.
    2  Unexpected error.
"""

import sys
import argparse
from pathlib import Path

# Add this directory to path for importing hardware_profile.
AI_DIR = Path(__file__).resolve().parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from hardware_profile import (
    HardwareProfile,
    gate_fabrication_release,
)


def main():
    parser = argparse.ArgumentParser(
        description="Check hardware profile gates for manufacturing release."
    )
    parser.add_argument(
        "--project-dir",
        required=True,
        help="Absolute path to the project directory (contains hardware_profile.json).",
    )
    parser.add_argument(
        "--kicad-cli",
        default="",
        help="Path to kicad-cli.exe (accepted for compatibility, not used by this check).",
    )
    args = parser.parse_args()

    profile_path = Path(args.project_dir) / "hardware_profile.json"
    try:
        profile = HardwareProfile.from_file(profile_path)
    except ValueError as exc:
        print(f"[BLOCKED] Invalid hardware profile: {exc}", file=sys.stderr)
        sys.exit(1)

    result = gate_fabrication_release(profile)
    if not result.allowed:
        print("[BLOCKED] Hardware fabrication gate failed:", file=sys.stderr)
        print(f"  {result.reason}", file=sys.stderr)
        print(f"  Blocking assumptions: {result.blocking_assumptions}", file=sys.stderr)
        if result.conflicts:
            print(f"  Conflicts: {result.conflicts}", file=sys.stderr)
        sys.exit(1)

    print("[PASS] Hardware fabrication gate passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
