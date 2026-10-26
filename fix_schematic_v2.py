#!/usr/bin/env python3
"""
Fix the backup schematic by embedding symbol definitions in lib_symbols
while preserving the correct instance format with lib_id.
"""

import sys

def extract_symbol(lib_content, symbol_name):
    """Extract a complete symbol definition from a library file using proper parenthesis counting."""
    start_marker = f'(symbol "{symbol_name}"'
    start_idx = lib_content.find(start_marker)
    if start_idx == -1:
        return None

    depth = 0
    i = start_idx
    while i < len(lib_content):
        if lib_content[i] == '(':
            depth += 1
        elif lib_content[i] == ')':
            depth -= 1
            if depth == 0:
                return lib_content[start_idx:i+1]
        i += 1
    return None

def read_file(path):
    with open(path, 'r') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)

def main():
    # Library files
    conn_lib = read_file(r'C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\Connector_Generic.kicad_sym')
    device_lib = read_file(r'C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\Device.kicad_sym')
    power_lib = read_file(r'C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\power.kicad_sym')

    # Extract required symbols
    symbols = {}
    for name in ['Conn_01x15', 'Conn_01x06']:
        sym = extract_symbol(conn_lib, name)
        if sym:
            symbols[f'Connector_Generic:{name}'] = sym
            print(f'Extracted Connector_Generic:{name} ({len(sym)} chars)')
        else:
            print(f'FAILED: Connector_Generic:{name}')

    for name in ['R']:
        sym = extract_symbol(device_lib, name)
        if sym:
            symbols[f'Device:{name}'] = sym
            print(f'Extracted Device:{name} ({len(sym)} chars)')
        else:
            print(f'FAILED: Device:{name}')

    for name in ['+3V3', 'GND']:
        sym = extract_symbol(power_lib, name)
        if sym:
            symbols[f'power:{name}'] = sym
            print(f'Extracted power:{name} ({len(sym)} chars)')
        else:
            print(f'FAILED: power:{name}')

    # Read the backup schematic
    backup_path = r'C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280\scripts_backup\ESP32_BME280.kicad_sch.before_en_dash_'
    schematic = read_file(backup_path)

    # Build lib_symbols section
    lib_sym_lines = ['\t(lib_symbols']
    for lib_id, defn in symbols.items():
        # Fix the symbol name in the definition to include library prefix
        simple_name = lib_id.split(':')[1]
        defn_fixed = defn.replace(f'(symbol "{simple_name}"', f'(symbol "{lib_id}"', 1)
        for line in defn_fixed.split('\n'):
            lib_sym_lines.append('\t\t' + line)
    lib_sym_lines.append('\t)')

    # Replace the empty lib_symbols in the schematic
    new_lib_symbols = '\n'.join(lib_sym_lines)
    schematic_fixed = schematic.replace('\t(lib_symbols)', new_lib_symbols)

    # Write the fixed schematic
    output_path = r'C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280_working_A\ESP32_BME280.kicad_sch'
    write_file(output_path, schematic_fixed)
    print(f'Written fixed schematic to {output_path}')

if __name__ == '__main__':
    main()