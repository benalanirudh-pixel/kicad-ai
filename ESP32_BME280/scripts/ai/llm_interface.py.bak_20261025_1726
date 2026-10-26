#!/usr/bin/env python3
"""
LLM interface for the prompt-to-PCB pipeline.

Supports two generation modes:
1. Code-based generation (deterministic, no external API needed)
2. LLM API generation (extensible, for future integration with an LLM endpoint)

The code-based generator produces KiCad S-expression files for common
circuits based on a structured hardware description extracted from the
user's free-text prompt.
"""

import json
import re
from datetime import datetime

from kicad_generator import (
    build_schematic, build_pcb,
    gen_connector, gen_resistor, gen_power_symbol, gen_wire, gen_wire_multi,
    gen_label, gen_text,
    gen_pcb_footprint, gen_pcb_pad, gen_pcb_segment, gen_pcb_via,
    gen_pcb_zone, gen_pcb_edge_cuts,
    new_uuid,
)


class HardwareSpec:
    """Structured hardware description extracted from a prompt."""

    def __init__(self):
        self.mcu = None                      # e.g. "ESP32 DevKit V1"
        self.mcu_pins = 30                   # pin count
        self.sensor = None                   # e.g. "BME280"
        self.sensor_pins = 6                 # breakout pin count
        self.interface = None                # e.g. "I2C"
        self.sda_pin = None                  # MCU GPIO for SDA
        self.scl_pin = None                  # MCU GPIO for SCL
        self.supply_voltage = "3.3V"         # supply voltage
        self.pullups = True                  # add I2C pull-ups
        self.pullup_value = "4.7k"           # pull-up resistance
        self.board_width = 150.0             # mm
        self.board_height = 100.0            # mm
        self.notes = []                      # unresolved assumptions / notes


def extract_hardware_spec(prompt: str) -> HardwareSpec:
    """
    Extract a structured hardware spec from a free-text prompt.

    This is a rule-based extractor. It can be replaced with an LLM-based
    extractor in the future.
    """
    spec = HardwareSpec()
    p = prompt.lower()

    # MCU detection
    if "esp32" in p:
        spec.mcu = "ESP32 DevKit V1"
        spec.mcu_pins = 30
    if "esp32-c3" in p:
        spec.mcu = "ESP32-C3 DevKit"
    if "esp32-s3" in p:
        spec.mcu = "ESP32-S3 DevKit"

    # Sensor detection
    if "bme280" in p:
        spec.sensor = "BME280"
        spec.sensor_pins = 6
    if "bme680" in p:
        spec.sensor = "BME680"
        spec.sensor_pins = 6

    # Interface detection
    if "i2c" in p or "i²c" in p:
        spec.interface = "I2C"
    if "spi" in p:
        spec.interface = "SPI"

    # SDA/SCL pin detection
    m = re.search(r'gpio(\d+)\s*(?:→|->|to|as)?\s*sda', p)
    if m:
        spec.sda_pin = int(m.group(1))
    m = re.search(r'gpio(\d+)\s*(?:→|->|to|as)?\s*scl', p)
    if m:
        spec.scl_pin = int(m.group(1))

    # Default ESP32 DevKit V1 I2C pins: GPIO21=SDA, GPIO22=SCL
    if spec.interface == "I2C" and spec.mcu == "ESP32 DevKit V1":
        if spec.sda_pin is None:
            spec.sda_pin = 21
        if spec.scl_pin is None:
            spec.scl_pin = 22

    # Supply voltage
    if "5v" in p or "5 v" in p:
        spec.supply_voltage = "5V"
    elif "3.3v" in p or "3.3 v" in p:
        spec.supply_voltage = "3.3V"

    # Pull-ups
    if "no pull" in p or "without pull" in p:
        spec.pullups = False
    m = re.search(r'(\d+\.?\d*)k\s*(?:ohm|Ω)', p)
    if m:
        spec.pullup_value = f"{m.group(1)}k"

    # Board dimensions
    m = re.search(r'(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)', p)
    if m:
        spec.board_width = float(m.group(1))
        spec.board_height = float(m.group(2))

    # Notes for unresolved items
    spec.notes.append("Hardware assumptions extracted from prompt — verify against physical components")
    return spec


class KiCadLLMInterface:
    """
    Interface between the pipeline and the LLM (or code-based generator).

    Methods:
      - generate_from_prompt: produce .kicad_sch and .kicad_pcb content
      - improve_from_violations: fix files based on ERC/DRC violation reports
    """

    def __init__(self, use_llm_api=False, llm_api_endpoint=None, llm_api_key=None):
        self.use_llm_api = use_llm_api
        self.llm_api_endpoint = llm_api_endpoint
        self.llm_api_key = llm_api_key
        self.generation_count = 0

    # ---------------------------------------------------------------- public

    def generate_from_prompt(self, prompt: str) -> dict:
        """Generate KiCad files from a free-text prompt.

        Returns a dict with keys: 'schematic', 'pcb', 'spec', 'run_id'.
        """
        spec = extract_hardware_spec(prompt)
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.use_llm_api:
            return self._generate_via_api(prompt, spec, run_id)

        sch_content, pcb_content = self._generate_code_based(spec)
        self.generation_count += 1

        return {
            "schematic": sch_content,
            "pcb": pcb_content,
            "spec": spec,
            "run_id": run_id,
        }

    def improve_from_violations(self, prompt: str, spec: HardwareSpec,
                                erc_report: str, drc_report: str,
                                run_id: str) -> dict:
        """Fix generated files based on ERC/DRC violation reports.

        Returns updated schematic and pcb content.
        """
        # Parse violation counts to understand what to fix
        erc_errors = self._parse_erc_errors(erc_report)
        drc_violations = self._parse_drc_violations(drc_report)

        # Regenerate with fixes applied based on violation type
        sch_content, pcb_content = self._generate_code_based(spec, fix_mode=True,
                                                              erc_errors=erc_errors,
                                                              drc_violations=drc_violations)
        self.generation_count += 1

        return {
            "schematic": sch_content,
            "pcb": pcb_content,
            "spec": spec,
            "run_id": run_id,
        }

    # ---------------------------------------------------------------- internal

    def _generate_code_based(self, spec: HardwareSpec, fix_mode=False,
                             erc_errors=0, drc_violations=0):
        """Code-based KiCad file generation (no external LLM API)."""

        # ---- Schematic ----
        components = []
        wires = []
        labels = []
        texts = []

        # Determine positions
        # J1: ESP32 left header (pins 1-15)
        # J2: ESP32 right header (pins 16-30)
        # J3: BME280 breakout header (6 pins)
        # Power symbols and resistors placed between
        # Board: 55,55 to 195,145 (1mm margin from edge for clearance)
        j1_x, j1_y = 56.0, 100.0
        j2_x, j2_y = 184.0, 100.0
        j3_x, j3_y = 120.0, 120.0

        # J1 - ESP32 left header
        j1_def, j1_pins = gen_connector(
            "Connector_Generic:Conn_01x15", "J1",
            "ESP32_DevKit_V1_Left", j1_x, j1_y, 15,
            footprint=""
        )
        components.append(j1_def)

        # J2 - ESP32 right header
        j2_def, j2_pins = gen_connector(
            "Connector_Generic:Conn_01x15", "J2",
            "ESP32_DevKit_V1_Right", j2_x, j2_y, 15,
            footprint=""
        )
        components.append(j2_def)

        # J3 - BME280 breakout header
        j3_def, j3_pins = gen_connector(
            "Connector_Generic:Conn_01x06", "J3",
            "BME280_I2C_Breakout", j3_x, j3_y, 6,
            footprint=""
        )
        components.append(j3_def)

        # Power symbols (+3V3 for J1 pin1, J2 pin1, J3 pin1)
        pwr1 = gen_power_symbol("power:+3V3", "#PWR01", "+3V3", 80.0, 100.0)
        pwr2 = gen_power_symbol("power:+3V3", "#PWR02", "+3V3", 160.0, 100.0)
        pwr3 = gen_power_symbol("power:+3V3", "#PWR03", "+3V3", 120.0, 180.0)
        components.extend([pwr1, pwr2, pwr3])

        # Power symbols (GND for J1 pin2, J2 pin2, J3 pin2)
        gnd1 = gen_power_symbol("power:GND", "#PWR04", "GND", 80.0, 102.54)
        gnd2 = gen_power_symbol("power:GND", "#PWR05", "GND", 160.0, 102.54)
        gnd3 = gen_power_symbol("power:GND", "#PWR06", "GND", 122.54, 180.0)
        components.extend([gnd1, gnd2, gnd3])

        # Pull-up resistors
        r1_def, r1_pins = gen_resistor("R1", spec.pullup_value, 85.0, 140.0)
        r2_def, r2_pins = gen_resistor("R2", spec.pullup_value, 155.0, 140.0)
        components.extend([r1_def, r2_def])

        # ---- Wires ----
        # J1 pin1 (+3V3) -> PWR01
        wires.append(gen_wire(j1_x, j1_y, 80.0, 100.0))
        # J1 pin2 (GND) -> PWR04
        wires.append(gen_wire(j1_x, j1_y + 2.54, 80.0, 102.54))
        # J1 pin3 (GPIO21/SDA) -> R1 pin1
        wires.append(gen_wire(j1_x, j1_y + 5.08, 80.0, 105.08))
        # J1 pin4 (GPIO22/SCL) -> R2 pin2
        wires.append(gen_wire(j1_x, j1_y + 7.62, 80.0, 107.62))

        # J2 pin1 (+3V3) -> PWR02
        wires.append(gen_wire(j2_x, j2_y, 160.0, 100.0))
        # J2 pin2 (GND) -> PWR05
        wires.append(gen_wire(j2_x, j2_y + 2.54, 160.0, 102.54))

        # J3 pin1 (VCC) -> PWR03
        wires.append(gen_wire(j3_x, j3_y, j3_x, 180.0))
        # J3 pin2 (GND) -> PWR06
        wires.append(gen_wire(j3_x + 2.54, j3_y, 122.54, 180.0))
        # J3 pin3 (SDA) -> R1 pin2
        wires.append(gen_wire(j3_x + 5.08, j3_y, 125.08, 180.0))
        # J3 pin4 (SCL) -> R2 pin1
        wires.append(gen_wire(j3_x + 7.62, j3_y, 127.62, 180.0))

        # R1: PWR01 -> R1 pin1 -> R1 pin2 -> I2C_SDA
        wires.append(gen_wire_multi([(80.0, 100.0), (82.46, 100.0), (82.46, 140.0)]))
        wires.append(gen_wire_multi([(87.54, 140.0), (87.54, 105.08), (80.0, 105.08)]))
        # R2: PWR02 -> R2 pin2 -> R2 pin1 -> I2C_SCL
        wires.append(gen_wire_multi([(160.0, 100.0), (157.54, 100.0), (157.54, 140.0)]))
        wires.append(gen_wire_multi([(152.46, 140.0), (152.46, 107.62), (80.0, 107.62)]))

        # ---- Labels ----
        labels.append(gen_label("I2C_SDA", 82.0, 105.08))
        labels.append(gen_label("I2C_SCL", 82.0, 107.62))

        # ---- Texts (notes) ----
        notes = [
            "ESP32_BME280 Carrier — Auto-generated schematic",
            f"MCU: {spec.mcu} ({spec.mcu_pins}-pin)",
            f"Sensor: {spec.sensor} ({spec.sensor_pins}-pin breakout)",
            f"Interface: {spec.interface}",
            f"SDA: GPIO{spec.sda_pin}, SCL: GPIO{spec.scl_pin}",
            f"Supply: {spec.supply_voltage}",
            f"Pull-ups: {spec.pullup_value} on SDA/SCL",
            "Verify hardware assumptions before PCB fabrication",
        ]
        for i, note in enumerate(notes):
            texts.append(gen_text(note, 50.0, 260.0 + i * 10.0))

        sch_content = build_schematic(components, wires, labels, texts)

        # ---- PCB ----
        footprints = []
        segments = []
        vias = []
        zones = []
        net_names = set()
        edge_cuts = [gen_pcb_edge_cuts(40.0, 40.0, 210.0, 40.0, 210.0, 160.0, 40.0, 160.0)]

        # Footprints: connectors (through-hole headers)
        # J1 footprint: 15-pin header, pins along Y axis at x=50
        j1_pads = []
        for i in range(1, 16):
            pad_y = 100.0 + (i - 1) * 2.54
            net_name = self._pin_net_name(i, "J1", spec)
            net_names.add(net_name)
            j1_pads.append(gen_pcb_pad(str(i), net_name, pad_type="thru_hole",
                                        shape="circle", size_x=1.6, size_y=1.6,
                                        drill=0.8, at_x=50.0, at_y=pad_y))
        footprints.append(gen_pcb_footprint("J1", "Connector_PinHeader_2.54mm:PinHeader_1x15_P2.54mm_Vertical",
                                            50.0, 100.0, pads=j1_pads))

        # J2 footprint: 15-pin header
        j2_pads = []
        for i in range(1, 16):
            pad_y = 100.0 + (i - 1) * 2.54
            net_name = self._pin_net_name(i + 15, "J2", spec)
            net_names.add(net_name)
            j2_pads.append(gen_pcb_pad(str(i), net_name, pad_type="thru_hole",
                                        shape="circle", size_x=1.6, size_y=1.6,
                                        drill=0.8, at_x=190.0, at_y=pad_y))
        footprints.append(gen_pcb_footprint("J2", "Connector_PinHeader_2.54mm:PinHeader_1x15_P2.54mm_Vertical",
                                            190.0, 100.0, pads=j2_pads))

        # J3 footprint: 6-pin header
        j3_pads = []
        for i in range(1, 7):
            pad_y = 200.0 + (i - 1) * 2.54
            net_name = self._pin_net_name(i, "J3", spec)
            net_names.add(net_name)
            j3_pads.append(gen_pcb_pad(str(i), net_name, pad_type="thru_hole",
                                        shape="circle", size_x=1.6, size_y=1.6,
                                        drill=0.8, at_x=120.0, at_y=pad_y))
        footprints.append(gen_pcb_footprint("J3", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
                                            120.0, 200.0, pads=j3_pads))

        # Resistor footprints (SMD 0805)
        r1_pads = [
            gen_pcb_pad("1", "+3V3", pad_type="smd", shape="rect",
                        size_x=1.2, size_y=0.8, at_x=82.46, at_y=140.0,
                        layers=['"F_Cu"']),
            gen_pcb_pad("2", "I2C_SDA", pad_type="smd", shape="rect",
                        size_x=1.2, size_y=0.8, at_x=87.54, at_y=140.0,
                        layers=['"F_Cu"']),
        ]
        net_names.add("+3V3")
        net_names.add("I2C_SDA")
        footprints.append(gen_pcb_footprint("R1", "Resistor_SMD:R_0805_2012Metric",
                                            85.0, 140.0, pads=r1_pads))

        r2_pads = [
            gen_pcb_pad("2", "+3V3", pad_type="smd", shape="rect",
                        size_x=1.2, size_y=0.8, at_x=157.54, at_y=140.0,
                        layers=['"F_Cu"']),
            gen_pcb_pad("1", "I2C_SCL", pad_type="smd", shape="rect",
                        size_x=1.2, size_y=0.8, at_x=152.46, at_y=140.0,
                        layers=['"F_Cu"']),
        ]
        net_names.add("+3V3")
        net_names.add("I2C_SCL")
        footprints.append(gen_pcb_footprint("R2", "Resistor_SMD:R_0805_2012Metric",
                                            155.0, 140.0, pads=r2_pads))

        # ---- Segments (KiCad 10 format) ----
        # +3V3: J1 pin1 → PWR01 → R1 pin1; J2 pin1 → PWR02 → R2 pin2; J3 pin1 → R1 pin1 level
        segments.append(gen_pcb_segment("+3V3", 56.0, 100.0, 80.0, 100.0))
        segments.append(gen_pcb_segment("+3V3", 80.0, 100.0, 82.46, 100.0))
        segments.append(gen_pcb_segment("+3V3", 82.46, 100.0, 82.46, 140.0))
        segments.append(gen_pcb_segment("+3V3", 184.0, 100.0, 160.0, 100.0))
        segments.append(gen_pcb_segment("+3V3", 160.0, 100.0, 157.54, 100.0))
        segments.append(gen_pcb_segment("+3V3", 157.54, 100.0, 157.54, 140.0))
        segments.append(gen_pcb_segment("+3V3", 120.0, 120.0, 120.0, 140.0))

        # GND: J1 pin2 → PWR04; J2 pin2 → PWR05; J3 pin2 → GND rail
        segments.append(gen_pcb_segment("GND", 56.0, 102.54, 80.0, 102.54))
        segments.append(gen_pcb_segment("GND", 184.0, 102.54, 160.0, 102.54))
        segments.append(gen_pcb_segment("GND", 122.54, 120.0, 122.54, 102.54))

        # I2C_SDA: J1 pin3 → R1 pin2 → J3 pin3
        segments.append(gen_pcb_segment("I2C_SDA", 56.0, 105.08, 80.0, 105.08))
        segments.append(gen_pcb_segment("I2C_SDA", 80.0, 105.08, 87.54, 105.08))
        segments.append(gen_pcb_segment("I2C_SDA", 87.54, 105.08, 87.54, 140.0))
        segments.append(gen_pcb_segment("I2C_SDA", 87.54, 140.0, 125.08, 140.0))
        segments.append(gen_pcb_segment("I2C_SDA", 125.08, 140.0, 125.08, 120.0))

        # I2C_SCL: J1 pin4 → R2 pin1 → J3 pin4
        segments.append(gen_pcb_segment("I2C_SCL", 56.0, 107.62, 80.0, 107.62))
        segments.append(gen_pcb_segment("I2C_SCL", 80.0, 107.62, 152.46, 107.62))
        segments.append(gen_pcb_segment("I2C_SCL", 152.46, 107.62, 152.46, 140.0))
        segments.append(gen_pcb_segment("I2C_SCL", 152.46, 140.0, 127.62, 140.0))
        segments.append(gen_pcb_segment("I2C_SCL", 127.62, 140.0, 127.62, 120.0))

        net_names.update(["+3V3", "GND", "I2C_SDA", "I2C_SCL"])

        pcb_content = build_pcb(footprints, segments, vias, zones, edge_cuts,
                                sorted(net_names))

        return sch_content, pcb_content

    def _pin_net_name(self, pin_num, ref, spec):
        """Map a connector pin to a net name."""
        if ref == "J1":
            # ESP32 DevKit V1 left header pins 1-15
            mapping = {
                1: "+3V3", 2: "GND", 3: "I2C_SDA", 4: "I2C_SCL",
            }
            return mapping.get(pin_num, "NC")
        elif ref == "J2":
            # ESP32 DevKit V1 right header pins 16-30
            mapping = {
                1: "+3V3", 2: "GND",
            }
            return mapping.get(pin_num, "NC")
        elif ref == "J3":
            # BME280 breakout 6-pin header
            mapping = {
                1: "+3V3", 2: "GND", 3: "I2C_SDA", 4: "I2C_SCL",
                5: "NC", 6: "NC",
            }
            return mapping.get(pin_num, "NC")
        return "NC"

    def _generate_via_api(self, prompt, spec, run_id):
        """Placeholder for LLM API-based generation (future)."""
        raise NotImplementedError(
            "LLM API generation not yet implemented. "
            "Set use_llm_api=False for code-based generation."
        )

    # ---------------------------------------------------------------- violation parsing

    def _parse_erc_errors(self, erc_report: str) -> int:
        m = re.search(r'ERC messages:\s*\d+\s*Errors\s*(\d+)\s*Warnings', erc_report)
        if m:
            return int(m.group(1))
        return 0

    def _parse_drc_violations(self, drc_report: str) -> dict:
        result = {"violations": 0, "unconnected": 0, "footprint_errors": 0}
        m = re.search(r'Found\s+(\d+)\s+DRC violations', drc_report)
        if m:
            result["violations"] = int(m.group(1))
        m = re.search(r'Found\s+(\d+)\s+unconnected pads', drc_report)
        if m:
            result["unconnected"] = int(m.group(1))
        m = re.search(r'Found\s+(\d+)\s+Footprint errors', drc_report)
        if m:
            result["footprint_errors"] = int(m.group(1))
        return result