#!/usr/bin/env python3
"""Test minimal schematic with just Device:R symbol."""

import uuid
import os

SCH_PATH = r"C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280_working\test_r.kicad_sch"

SCH_UUID = str(uuid.uuid4())
SCH_VERSION = 20260306

# Device:R symbol definition (from library)
DEVICE_R = '''(symbol "Device:R"
	(pin_numbers
		(hide yes)
	)
	(pin_names
		(offset 0)
	)
	(exclude_from_sim no)
	(in_bom yes)
	(on_board yes)
	(in_pos_files yes)
	(duplicate_pin_numbers_are_jumpers no)
	(property "Reference" "R"
		(at 2.032 0 90)
		(show_name no)
		(do_not_autoplace no)
		(effects
			(font
				(size 1.27 1.27)
			)
		)
	)
	(property "Value" "R"
		(at 0 0 90)
		(show_name no)
		(do_not_autoplace no)
		(effects
			(font
				(size 1.27 1.27)
			)
		)
	)
	(property "Footprint" ""
		(at -1.778 0 90)
		(show_name no)
		(do_not_autoplace no)
		(hide yes)
		(effects
			(font
				(size 1.27 1.27)
			)
		)
	)
	(property "Datasheet" ""
		(at 0 0 0)
		(show_name no)
		(do_not_autoplace no)
		(hide yes)
		(effects
			(font
				(size 1.27 1.27)
			)
		)
	)
	(property "Description" "Resistor"
		(at 0 0 0)
		(show_name no)
		(do_not_autoplace no)
		(hide yes)
		(effects
			(font
				(size 1.27 1.27)
			)
		)
	)
	(property "ki_keywords" "R res resistor"
		(at 0 0 0)
		(show_name no)
		(do_not_autoplace no)
		(hide yes)
		(effects
			(font
				(size 1.27 1.27)
			)
		)
	)
	(property "ki_fp_filters" "R_*"
		(at 0 0 0)
		(show_name no)
		(do_not_autoplace no)
		(hide yes)
		(effects
			(font
				(size 1.27 1.27)
			)
		)
	)
	(symbol "Device:R_0_1"
		(rectangle
			(start -1.016 -2.54)
			(end 1.016 2.54)
			(stroke
				(width 0.254)
				(type default)
			)
			(fill
				(type none)
			)
		)
	)
	(symbol "Device:R_1_1"
		(pin passive line
			(at 0 3.81 270)
			(length 1.27)
			(name ""
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(number "1"
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
		)
		(pin passive line
			(at 0 -3.81 90)
			(length 1.27)
			(name ""
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(number "2"
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
		)
	)
	(embedded_fonts no)
)'''

out = []
out.append("(kicad_sch")
out.append(f"\t(version {SCH_VERSION})")
out.append('\t(generator "eeschema")')
out.append('\t(generator_version "10.0")')
out.append(f"\t(uuid {SCH_UUID})")
out.append('\t(paper "A4")')
out.append("\t(lib_symbols")
out.append('\t\t' + DEVICE_R.replace('\n', '\n\t\t'))
out.append("\t)")
out.append("\t(sheet_instances")
out.append('\t\t(path "/"')
out.append('\t\t\t(page "1")')
out.append("\t\t)")
out.append("\t)")
out.append('\t(embedded_fonts no)')
out.append('\t(symbol "Device:R"')
out.append('\t\t(at 0 0 0)')
out.append('\t\t(unit 1)')
out.append('\t\t(in_bom yes)')
out.append('\t\t(on_board yes)')
out.append('\t\t(property "Reference" "R1"')
out.append('\t\t\t(at 0 5.08 0)')
out.append('\t\t\t(show_name no)')
out.append('\t\t\t(do_not_autoplace no)')
out.append('\t\t\t(effects')
out.append('\t\t\t\t(font')
out.append('\t\t\t\t\t(size 1.27 1.27)')
out.append('\t\t\t\t)')
out.append('\t\t\t)')
out.append('\t\t)')
out.append('\t\t(property "Value" "4k7"')
out.append('\t\t\t(at 0 -5.08 0)')
out.append('\t\t\t(show_name yes)')
out.append('\t\t\t(do_not_autoplace no)')
out.append('\t\t\t(effects')
out.append('\t\t\t\t(font')
out.append('\t\t\t\t\t(size 1.27 1.27)')
out.append('\t\t\t\t)')
out.append('\t\t\t)')
out.append('\t\t)')
out.append('\t\t(property "Footprint" ""')
out.append('\t\t\t(at 0 0 0)')
out.append('\t\t\t(show_name no)')
out.append('\t\t\t(do_not_autoplace no)')
out.append('\t\t\t(hide yes)')
out.append('\t\t\t(effects')
out.append('\t\t\t\t(font')
out.append('\t\t\t\t\t(size 1.27 1.27)')
out.append('\t\t\t\t)')
out.append('\t\t\t)')
out.append('\t\t)')
out.append('\t\t(property "Datasheet" ""')
out.append('\t\t\t(at 0 0 0)')
out.append('\t\t\t(show_name no)')
out.append('\t\t\t(do_not_autoplace no)')
out.append('\t\t\t(hide yes)')
out.append('\t\t\t(effects')
out.append('\t\t\t\t(font')
out.append('\t\t\t\t\t(size 1.27 1.27)')
out.append('\t\t\t\t)')
out.append('\t\t\t)')
out.append('\t\t)')
out.append('\t)')
out.append(")")

sch = "\n".join(out) + "\n"
with open(SCH_PATH, "w", encoding="utf-8") as f:
    f.write(sch)
print(f"Wrote: {SCH_PATH}")
print(f"Bytes: {os.path.getsize(SCH_PATH)}")