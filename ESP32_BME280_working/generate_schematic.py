#!/usr/bin/env python3
"""
Reproducible Python generator for the ESP32_BME280 KiCad 10 schematic.

Generates ESP32_BME280.kicad_sch (KiCad 10 schematic format) with embedded
symbol definitions in lib_symbols. Represents:
  - ESP32 DevKit V1 30-pin as two Conn_01x15 headers (J1 left, J2 right)
  - BME280 breakout module as Conn_01x06 (J3) - breakout interface, NOT bare IC
  - Two 4k7 I2C pull-up resistors (R1 on SDA, R2 on SCL) to 3V3
  - Power symbols: +3V3, GND, PWR_FLAG on both nets

Connections (provisional, per DESIGN_REQUIREMENTS.md items U1-U7):
  3V3   : J1.1 (ESP32) -> BME280 breakout VCC (J3.1)
  GND   : J1.2 (ESP32) -> BME280 breakout GND (J3.2)
  I2C_SDA: J2.14 (GPIO21 provisional U2) -> BME280 SDA (J3.3) -> R1 -> 3V3
  I2C_SCL: J2.15 (GPIO22 provisional U2) -> BME280 SCL (J3.4) -> R2 -> 3V3

All inter-component connections use KiCad global (net) labels so the netlist
records the intended connectivity. Component placement is for readability only.
"""

import uuid
import os
import re
from pathlib import Path

SCH_PATH = r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280_working\ESP32_BME280.kicad_sch"

KICAD_SYM_DIR = Path(r"C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols")

SCH_UUID = str(uuid.uuid4())
SCH_VERSION = 20260306

REQUIRED_SYMBOLS = {
    "Connector_Generic.kicad_sym": ["Conn_01x15", "Conn_01x06"],
    "Device.kicad_sym": ["R"],
    "power.kicad_sym": ["+3V3", "GND", "PWR_FLAG"],
}


def esc(s):
    return s.replace('\\', '\\\\').replace('"', '\\"')


def read_symbol_lib(lib_path):
    """Read a .kicad_sym file and return dict of symbol_name -> full s-expression."""
    content = lib_path.read_text(encoding="utf-8")
    symbols = {}
    
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('(symbol "'):
            match = re.match(r'\(symbol\s+"([^"]+)"', line)
            if match:
                sym_name = match.group(1)
                depth = 0
                start = i
                j = i
                while j < len(lines):
                    depth += lines[j].count('(') - lines[j].count(')')
                    if depth == 0:
                        break
                    j += 1
                if j < len(lines):
                    symbol_text = '\n'.join(lines[start:j+1])
                    symbols[sym_name] = symbol_text
                    i = j + 1
                    continue
        i += 1
    return symbols


def extract_required_symbols():
    """Extract all required symbol definitions from library files."""
    all_symbols = {}
    for lib_file, sym_names in REQUIRED_SYMBOLS.items():
        lib_path = KICAD_SYM_DIR / lib_file
        if not lib_path.exists():
            print(f"WARNING: Library not found: {lib_path}")
            continue
        lib_symbols = read_symbol_lib(lib_path)
        lib_prefix = lib_file.replace('.kicad_sym', '')
        for sym_name in sym_names:
            if sym_name in lib_symbols:
                full_name = f"{lib_prefix}:{sym_name}"
                defn = lib_symbols[sym_name]
                # Replace the main symbol name to include library prefix
                defn = defn.replace(f'(symbol "{sym_name}"', f'(symbol "{full_name}"', 1)
                all_symbols[full_name] = defn
                print(f"Extracted: {full_name}")
            else:
                print(f"WARNING: Symbol not found in library: {sym_name} in {lib_file}")
    return all_symbols


def indent_lines(text, level=1):
    """Add tab indentation to each non-empty line."""
    prefix = '\t' * level
    return '\n'.join(prefix + line if line.strip() else line for line in text.split('\n'))


def build_schematic():
    lib_symbols = extract_required_symbols()
    
    # ---- Component placement ----
    j1_x, j1_y = -70, 0      # J1 left header (pins 1-15)
    j2_x, j2_y = 70, 0       # J2 right header (pins 16-30)
    j3_x, j3_y = 0, -95      # J3 breakout header
    r1_x, r1_y = 0, -170     # R1: SDA -> 3V3
    r2_x, r2_y = 40, -170    # R2: SCL -> 3V3
    pwr3v3_x, pwr3v3_y = -70, -70
    pwrgnd_x, pwrgnd_y = -70, -100
    pff3v3_x, pff3v3_y = -40, -70
    pffgnd_x, pffgnd_y = -40, -100

    # Build lib_symbols section
    lib_sym_lines = ["\t(lib_symbols"]
    for name, defn in lib_symbols.items():
        for line in defn.split('\n'):
            lib_sym_lines.append('\t\t' + line)
    lib_sym_lines.append("\t)")

    # Symbol instances (correct KiCad 6+ format with lib_id, uuid, pins)
    parts = []
    
    def make_symbol_instance(lib_id, ref, value, x, y, footprint="", dnp=False, unit=1, body_style=0):
        """Create a symbol instance with correct KiCad 6+ format."""
        inst_uuid = str(uuid.uuid4()).replace('-', '')[:32]
        # Format uuid as 8-4-4-4-12
        inst_uuid_fmt = f"{inst_uuid[0:8]}-{inst_uuid[8:12]}-{inst_uuid[12:16]}-{inst_uuid[16:20]}-{inst_uuid[20:32]}"
        
        # Generate pin uuids (simplified - same uuid for all pins of this instance)
        # In reality each pin has unique uuid, but we'll use derived ones
        pin_uuids = []
        for i in range(1, 16):  # max 15 pins for Conn_01x15
            pin_uuid = str(uuid.uuid4()).replace('-', '')[:32]
            pin_uuid_fmt = f"{pin_uuid[0:8]}-{pin_uuid[8:12]}-{pin_uuid[12:16]}-{pin_uuid[16:20]}-{pin_uuid[20:32]}"
            pin_uuids.append(pin_uuid_fmt)
        
        lines = []
        lines.append('\t(symbol')
        lines.append(f'\t\t(lib_id "{lib_id}")')
        lines.append(f'\t\t(at {x} {y} 0)')
        lines.append(f'\t\t(unit {unit})')
        lines.append(f'\t\t(body_style {body_style})')
        lines.append('\t\t(exclude_from_sim no)')
        lines.append('\t\t(in_bom yes)')
        lines.append('\t\t(on_board yes)')
        lines.append('\t\t(in_pos_files yes)')
        lines.append(f'\t\t(dnp {"yes" if dnp else "no"})')
        lines.append(f'\t\t(uuid "{inst_uuid_fmt}")')
        
        # Properties
        lines.append(f'\t\t(property "Reference" "{ref}"')
        lines.append(f'\t\t\t(at {x} {y + 5.08} 0)')
        lines.append('\t\t\t(show_name no)')
        lines.append('\t\t\t(do_not_autoplace no)')
        lines.append('\t\t\t(effects')
        lines.append('\t\t\t\t(font')
        lines.append('\t\t\t\t\t(size 1.27 1.27)')
        lines.append('\t\t\t\t)')
        lines.append('\t\t\t)')
        lines.append('\t\t)')
        lines.append(f'\t\t(property "Value" "{esc(value)}"')
        lines.append(f'\t\t\t(at {x} {y - 5.08} 0)')
        lines.append('\t\t\t(show_name yes)')
        lines.append('\t\t\t(do_not_autoplace no)')
        lines.append('\t\t\t(effects')
        lines.append('\t\t\t\t(font')
        lines.append('\t\t\t\t\t(size 1.27 1.27)')
        lines.append('\t\t\t\t)')
        lines.append('\t\t\t)')
        lines.append('\t\t)')
        if footprint:
            lines.append(f'\t\t(property "Footprint" "{esc(footprint)}"')
            lines.append(f'\t\t\t(at {x} {y} 0)')
            lines.append('\t\t\t(show_name no)')
            lines.append('\t\t\t(do_not_autoplace no)')
            lines.append('\t\t\t(hide yes)')
            lines.append('\t\t\t(effects')
            lines.append('\t\t\t\t(font')
            lines.append('\t\t\t\t\t(size 1.27 1.27)')
            lines.append('\t\t\t\t)')
            lines.append('\t\t\t)')
            lines.append('\t\t)')
        lines.append('\t\t(property "Datasheet" ""')
        lines.append(f'\t\t\t(at {x} {y} 0)')
        lines.append('\t\t\t(hide yes)')
        lines.append('\t\t\t(show_name no)')
        lines.append('\t\t\t(do_not_autoplace no)')
        lines.append('\t\t\t(effects')
        lines.append('\t\t\t\t(font')
        lines.append('\t\t\t\t\t(size 1.27 1.27)')
        lines.append('\t\t\t\t)')
        lines.append('\t\t\t)')
        lines.append('\t\t)')
        
        # Pin entries (simplified - we need pin uuids for each pin used)
        # For now, add pin entries for all possible pins
        for i in range(15):
            lines.append(f'\t\t(pin "{i+1}"')
            lines.append(f'\t\t\t(uuid "{pin_uuids[i]}")')
            lines.append('\t\t)')
        
        lines.append('\t)')
        return '\n'.join(lines)

    # J1 ESP32 left header
    parts.append(make_symbol_instance("Connector_Generic:Conn_01x15", "J1", 
        "ESP32 DevKit V1 header (pins 1-15)", j1_x, j1_y))
    
    # J2 ESP32 right header
    parts.append(make_symbol_instance("Connector_Generic:Conn_01x15", "J2",
        "ESP32 DevKit V1 header (pins 16-30)", j2_x, j2_y))
    
    # J3 BME280 breakout (6 pins)
    parts.append(make_symbol_instance("Connector_Generic:Conn_01x06", "J3",
        "BME280 breakout header (breakout module interface)", j3_x, j3_y))
    
    # R1
    parts.append(make_symbol_instance("Device:R", "R1", "4k7", r1_x, r1_y))
    
    # R2
    parts.append(make_symbol_instance("Device:R", "R2", "4k7", r2_x, r2_y))
    
    # Power symbols
    for name, ref, x, y in [
        ("power:+3V3", "PWR_+3V3", pwr3v3_x, pwr3v3_y),
        ("power:GND", "PWR_GND", pwrgnd_x, pwrgnd_y),
        ("power:PWR_FLAG", "PWR_FLAG_3V3", pff3v3_x, pff3v3_y),
        ("power:PWR_FLAG", "PWR_FLAG_GND", pffgnd_x, pffgnd_y),
    ]:
        parts.append(make_symbol_instance(name, ref, name.split(':')[1], x, y))

    # Global labels for net connections
    labels = []
    
    def conn_pin(comp_x, comp_y, n):
        return comp_x - 5.08, comp_y - (n - 1) * 2.54
    
    def r_pin1(comp_x, comp_y):
        return comp_x, comp_y + 3.81
    def r_pin2(comp_x, comp_y):
        return comp_x, comp_y - 3.81
    
    def pwr_pin(comp_x, comp_y):
        return comp_x, comp_y

    def add_label(net, x, y):
        labels.append(f'''\t(label
\t\t(at {x} {y} 0)
\t\t(type "global")
\t\t(text "{esc(net)}")
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t)
\t)''')

    # 3V3 net
    add_label("3V3", *conn_pin(j1_x, j1_y, 1))
    add_label("3V3", *pwr_pin(pwr3v3_x, pwr3v3_y))
    add_label("3V3", *pwr_pin(pff3v3_x, pff3v3_y))
    add_label("3V3", *conn_pin(j3_x, j3_y, 1))
    add_label("3V3", *r_pin2(r1_x, r1_y))
    add_label("3V3", *r_pin2(r2_x, r2_y))

    # GND net
    add_label("GND", *conn_pin(j1_x, j1_y, 2))
    add_label("GND", *pwr_pin(pwrgnd_x, pwrgnd_y))
    add_label("GND", *pwr_pin(pffgnd_x, pffgnd_y))
    add_label("GND", *conn_pin(j3_x, j3_y, 2))

    # I2C_SDA net
    add_label("I2C_SDA", *conn_pin(j2_x, j2_y, 14))
    add_label("I2C_SDA", *conn_pin(j3_x, j3_y, 3))
    add_label("I2C_SDA", *r_pin1(r1_x, r1_y))

    # I2C_SCL net
    add_label("I2C_SCL", *conn_pin(j2_x, j2_y, 15))
    add_label("I2C_SCL", *conn_pin(j3_x, j3_y, 4))
    add_label("I2C_SCL", *r_pin1(r2_x, r2_y))

    # Assemble
    out = []
    out.append("(kicad_sch")
    out.append(f"\t(version {SCH_VERSION})")
    out.append('\t(generator "eeschema")')
    out.append('\t(generator_version "10.0")')
    out.append(f"\t(uuid {SCH_UUID})")
    out.append('\t(paper "A4")')
    out.extend(lib_sym_lines)
    out.append("\t(sheet_instances")
    out.append('\t\t(path "/"')
    out.append('\t\t\t(page "1")')
    out.append("\t\t)")
    out.append("\t)")
    out.append('\t(embedded_fonts no)')
    
    for p in parts:
        out.append(p)
    for lab in labels:
        out.append(lab)
    out.append(")")
    
    return "\n".join(out) + "\n"


def main():
    sch = build_schematic()
    with open(SCH_PATH, "w", encoding="utf-8") as f:
        f.write(sch)
    print(f"Wrote schematic: {SCH_PATH}")
    print(f"Bytes: {os.path.getsize(SCH_PATH)}")


if __name__ == "__main__":
    main()