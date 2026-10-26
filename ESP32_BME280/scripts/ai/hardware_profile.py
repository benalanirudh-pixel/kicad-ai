#!/usr/bin/env python3
"""
Hardware-profile model and mandatory gate functions for the ESP32_BME280
automation pipeline.

This module provides:
  - HardwareFact: a single typed hardware fact with source, confidence, and
    affected decisions.
  - HardwareProfile: a validated collection of hardware facts loaded from a
    YAML profile file.
  - Gate functions for electrical schematic approval, mechanical footprint
    placement, and fabrication release.

All functions are pure and independently testable. A missing profile file or
missing required fact defaults to a blocked (fail-closed) state. No gate may
be silently overridden by a skip_gates flag or user confirmation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path
import json

# --------------------------------------------------------------------------- confidence levels

CONFIDENCE_VERIFIED = "verified"
CONFIDENCE_ASSUMED = "assumed"
CONFIDENCE_UNRESOLVED = "unresolved"
CONFIDENCE_CONFLICTING = "conflicting"

VALID_CONFIDENCES = {
    CONFIDENCE_VERIFIED,
    CONFIDENCE_ASSUMED,
    CONFIDENCE_UNRESOLVED,
    CONFIDENCE_CONFLICTING,
}

# --------------------------------------------------------------------------- assumption IDs (U1–U7)

ASSUMPTIONS = ["U1", "U2", "U3", "U4", "U5", "U6", "U7"]

# Electrical assumptions (gate schematic approval)
ELECTRICAL_ASSUMPTIONS = ["U1", "U2", "U3", "U7"]

# Mechanical assumptions (gate footprint placement)
MECHANICAL_ASSUMPTIONS = ["U4", "U5", "U6"]

# --------------------------------------------------------------------------- fact field names

FIELD_SUPPLY_RANGE = "supply_range"
FIELD_ONBOARD_REGULATOR = "onboard_regulator"
FIELD_SDA_GPIO = "sda_gpio"
FIELD_SCL_GPIO = "scl_gpio"
FIELD_ONBOARD_PULLUPS = "onboard_pullups"
FIELD_I2C_ADDRESS = "i2c_address"
FIELD_MCU_IDENTITY = "mcu_identity"
FIELD_MCU_PIN_COUNT = "mcu_pin_count"
FIELD_PULLUP_RESISTANCE = "pullup_resistance"
FIELD_CONNECTOR_TYPE = "connector_type"
FIELD_CONNECTOR_PITCH = "connector_pitch"
FIELD_BOARD_WIDTH = "board_width"
FIELD_BOARD_HEIGHT = "board_height"
FIELD_MOUNTING_HOLES = "mounting_holes"


@dataclass
class HardwareFact:
    """A single typed hardware fact.

    value:        The fact value (any type). None means unresolved.
    source:       Where the fact came from (datasheet, user_selection,
                  prompt_extract, measurement, etc.). None if unknown.
    confidence:   One of verified / assumed / unresolved / conflicting.
    affects_decisions: List of decision IDs this fact gates.
    evidence_date: Optional ISO-8601 date string for when the fact was
                   confirmed.
    """

    value: Any = None
    source: Optional[str] = None
    confidence: str = CONFIDENCE_UNRESOLVED
    affects_decisions: List[str] = field(default_factory=list)
    evidence_date: Optional[str] = None

    def __post_init__(self) -> None:
        if self.confidence not in VALID_CONFIDENCES:
            raise ValueError(
                f"Invalid confidence '{self.confidence}'. "
                f"Must be one of {sorted(VALID_CONFIDENCES)}"
            )


@dataclass
class GateResult:
    """Structured result of a gate check.

    allowed:          True if the gate passes (all required facts verified).
    blocking_assumptions: List of assumption IDs that block the gate.
    conflicts:        List of conflict descriptions.
    reason:           Human-readable explanation.
    """

    allowed: bool
    blocking_assumptions: List[str]
    conflicts: List[str]
    reason: str


# --------------------------------------------------------------------------- profile

class HardwareProfile:
    """A validated collection of hardware facts.

    Facts are stored keyed by fact name (e.g. "supply_range", "mcu_identity").
    Each fact is a HardwareFact with value, source, confidence, and
    affects_decisions.

    A missing profile file defaults to an empty profile — all facts unresolved,
    which fail-closes every gate.
    """

    def __init__(self, facts: Optional[Dict[str, HardwareFact]] = None) -> None:
        self._facts: Dict[str, HardwareFact] = facts or {}

    @classmethod
    def from_file(cls, path: Path) -> "HardwareProfile":
        """Load a hardware profile from a JSON file.

        Returns an empty (all-unresolved) profile if the file does not exist.
        Raises ValueError if the file exists but has invalid schema.
        """
        if not path.is_file():
            return cls()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in hardware profile {path}: {exc}")

        if not isinstance(data, dict):
            raise ValueError(
                f"Hardware profile root must be a JSON object, got {type(data).__name__}"
            )

        facts: Dict[str, HardwareFact] = {}
        for key, entry in data.items():
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Profile entry '{key}' must be an object, got {type(entry).__name__}"
                )
            facts[key] = HardwareFact(
                value=entry.get("value"),
                source=entry.get("source"),
                confidence=entry.get("confidence", CONFIDENCE_UNRESOLVED),
                affects_decisions=entry.get("affects_decisions", []),
                evidence_date=entry.get("evidence_date"),
            )
        return cls(facts)

    def fact(self, name: str) -> Optional[HardwareFact]:
        """Return the HardwareFact for a given fact name, or None if absent."""
        return self._facts.get(name)

    def confidence_of(self, name: str) -> str:
        """Return the confidence level for a fact name, defaulting to unresolved."""
        fact = self.fact(name)
        if fact is None:
            return CONFIDENCE_UNRESOLVED
        return fact.confidence

    def is_blocked(self, assumption_ids: List[str]) -> List[str]:
        """Return the list of assumption IDs that are not verified.

        An assumption is considered blocked if its corresponding fact is
        missing, unresolved, conflicting, or merely assumed. Only
        CONFIDENCE_VERIFIED facts pass a gate. An assumed fact is NOT
        treated as verified.
        """
        blocked: List[str] = []
        for assumption_id in assumption_ids:
            fact = self.fact(assumption_id)
            if fact is None or fact.confidence != CONFIDENCE_VERIFIED:
                blocked.append(assumption_id)
        return blocked

    def conflicts(self) -> List[str]:
        """Return descriptions of all conflicting facts in the profile."""
        conflict_descriptions: List[str] = []
        for name, fact in self._facts.items():
            if fact.confidence == CONFIDENCE_CONFLICTING:
                conflict_descriptions.append(
                    f"'{name}' has conflicting evidence (value={fact.value}, "
                    f"sources={fact.source})"
                )
        return conflict_descriptions

    @property
    def facts(self) -> Dict[str, HardwareFact]:
        return dict(self._facts)


# --------------------------------------------------------------------------- gate functions


def gate_electrical_schematic(profile: HardwareProfile) -> GateResult:
    """Check whether electrical assumptions are complete for schematic approval.

    Required facts: U1 (supply_range), U2 (sda_gpio / scl_gpio),
    U3 (onboard_pullups), U7 (i2c_address).

    All must be verified (CONFIDENCE_VERIFIED). Assumed facts are NOT
    treated as verified. Unresolved or conflicting facts block the gate.
    """
    blocking = profile.is_blocked(ELECTRICAL_ASSUMPTIONS)
    conflicts = profile.conflicts()
    if blocking or conflicts:
        reason = (
            "Electrical schematic approval blocked: unresolved or conflicting "
            f"assumptions {blocking}. "
            f"Conflicts: {conflicts}. "
            "Resolve U1 (supply range/regulator), U2 (GPIO21/GPIO22 mapping), "
            "U3 (I2C pull-ups), U7 (I2C address/SDO) before schematic approval."
        )
        return GateResult(
            allowed=False,
            blocking_assumptions=blocking,
            conflicts=conflicts,
            reason=reason,
        )
    return GateResult(
        allowed=True,
        blocking_assumptions=[],
        conflicts=[],
        reason="All electrical assumptions resolved for schematic approval.",
    )


def gate_mechanical_footprint(profile: HardwareProfile) -> GateResult:
    """Check whether mechanical assumptions are complete for footprint placement.

    Required facts: U4 (connector type/pitch), U5 (ESP32 dimensions/mounting),
    U6 (breakout dimensions/pads/mounting).

    All must be verified (CONFIDENCE_VERIFIED). Assumed facts are NOT
    treated as verified. Unresolved or conflicting facts block the gate.
    """
    blocking = profile.is_blocked(MECHANICAL_ASSUMPTIONS)
    conflicts = profile.conflicts()
    if blocking or conflicts:
        reason = (
            "Mechanical footprint placement blocked: unresolved or conflicting "
            f"assumptions {blocking}. "
            f"Conflicts: {conflicts}. "
            "Resolve U4 (connector type/pitch), U5 (ESP32 dimensions/mounting), "
            "U6 (breakout dimensions/pads/mounting) before footprint placement."
        )
        return GateResult(
            allowed=False,
            blocking_assumptions=blocking,
            conflicts=conflicts,
            reason=reason,
        )
    return GateResult(
        allowed=True,
        blocking_assumptions=[],
        conflicts=[],
        reason="All mechanical assumptions resolved for footprint placement.",
    )


def gate_fabrication_release(profile: HardwareProfile) -> GateResult:
    """Check whether all requirements are complete for fabrication release.

    Required facts: all electrical (U1–U3, U7) and mechanical (U4–U6)
    assumptions must be verified (CONFIDENCE_VERIFIED). Assumed facts
    are NOT treated as verified. Additionally, at least one footprint
    must be verified before fabrication release.
    """
    all_assumptions = ELECTRICAL_ASSUMPTIONS + MECHANICAL_ASSUMPTIONS
    blocking = profile.is_blocked(all_assumptions)
    conflicts = profile.conflicts()

    if blocking or conflicts:
        reason = (
            "Fabrication release blocked: unresolved or conflicting assumptions "
            f"{blocking}. Conflicts: {conflicts}. "
            "All hardware assumptions U1–U7 must be resolved before manufacturing "
            "export."
        )
        return GateResult(
            allowed=False,
            blocking_assumptions=blocking,
            conflicts=conflicts,
            reason=reason,
        )

    # Fabrication also requires at least one verified footprint footprint fact.
    verified_footprints = [
        name
        for name, fact in profile.facts.items()
        if "footprint" in name.lower()
        and fact.confidence == CONFIDENCE_VERIFIED
    ]
    if not verified_footprints:
        return GateResult(
            allowed=False,
            blocking_assumptions=[],
            conflicts=[],
            reason=(
                "Fabrication release blocked: no verified footprint facts found. "
                "At least one footprint must be verified before manufacturing export."
            ),
        )

    return GateResult(
        allowed=True,
        blocking_assumptions=[],
        conflicts=[],
        reason="All hardware assumptions and at least one verified footprint ready for fabrication release.",
    )


# --------------------------------------------------------------------------- convenience


def gate_all(profile: HardwareProfile) -> Dict[str, GateResult]:
    """Run all three gate checks and return a dict of results."""
    return {
        "electrical_schematic": gate_electrical_schematic(profile),
        "mechanical_footprint": gate_mechanical_footprint(profile),
        "fabrication_release": gate_fabrication_release(profile),
    }
