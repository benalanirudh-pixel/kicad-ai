#!/usr/bin/env python3
"""
KiCad S-expression generator for the AI prompt-to-PCB pipeline.

Generates valid KiCad 10.0 .kicad_sch and .kicad_pcb files from a
structured hardware description. Output is written to a staging directory;
the pipeline orchestrator handles validation, self-healing, and approval.
"""

import uuid
import math
from datetime import datetime


def new_uuid():
    return str(uuid.uuid4())


def sexpr_escape(s):
    return s.replace('\\', '\\\\').replace('"', '\\"')


def sexpr_list(items, indent=0):
    pad = '\t' * indent
    inner_pad = '\t' * (indent + 1)
    lines = ['(']
    for i, item in enumerate(items):
        if isinstance(item, list):
            lines.append(inner_pad + sexpr_list(item, indent + 1))
        else:
            lines.append(inner_pad + str(item))
        if i < len(items) - 1:
            lines[-1] += ''
    lines.append(pad + ')')
    return '\n'.join(lines)


def sexpr(items):
    """Flat single-line S-expression."""
    return '(' + ' '.join(str(i) for i in items) + ')'


# ---------------------------------------------------------------- schematic

def gen_schematic_header(paper="A4"):
    return f"""(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "{new_uuid()}")
	(paper "{paper}")
	(lib_symbols
"""

def gen_schematic_footer():
    return """	(embedded_fonts no)
)
"""


def gen_symbol_def(lib_id, ref, value, at_x, at_y, footprint="", pins=None,
                   properties=None, uuid_str=None):
    """Generate a complete symbol definition including lib_symbols wrapper."""
    if uuid_str is None:
        uuid_str = new_uuid()
    if pins is None:
        pins = []
    if properties is None:
        properties = {}

    lines = []
    lines.append('\t\t(symbol')
    lines.append(f'\t\t\t(lib_id "{lib_id}")')
    lines.append(f'\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t(unit 1)')
    lines.append('\t\t\t(exclude_from_sim no)')
    lines.append('\t\t\t(in_bom yes)')
    lines.append('\t\t\t(on_board yes)')
    lines.append('\t\t\t(dnp no)')
    lines.append(f'\t\t\t(uuid "{uuid_str}")')

    # Reference property
    ref_prop_at_y = at_y - 15.0
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Reference "{ref}")')
    lines.append(f'\t\t\t\t(at {at_x} {ref_prop_at_y} 0)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')

    # Value property
    val_prop_at_y = at_y + 15.0
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Value "{value}")')
    lines.append(f'\t\t\t\t(at {at_x} {val_prop_at_y} 0)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')

    # Footprint property
    if footprint:
        lines.append('\t\t\t(property')
        lines.append(f'\t\t\t\t(Footprint "{footprint}")')
        lines.append(f'\t\t\t\t(at {at_x} {at_y} 0)')
        lines.append('\t\t\t\t(hide yes)')
        lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
        lines.append('\t\t\t)')

    # Datasheet property
    lines.append('\t\t\t(property')
    lines.append('\t\t\t\t(Datasheet "")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t\t(hide yes)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')

    # Pins
    for pin_num, pin_uuid in pins:
        lines.append(f'\t\t\t(pin "{pin_num}" (uuid "{pin_uuid}"))')

    # Instances
    lines.append('\t\t\t(instances')
    lines.append('\t\t\t\t(project ""')
    lines.append(f'\t\t\t\t\t(path "/{gen_schematic_header.__globals__["_sch_uuid"]}/"')
    lines.append(f'\t\t\t\t\t\t(reference "{ref}")')
    lines.append('\t\t\t\t\t\t(unit 1)')
    lines.append('\t\t\t\t\t)')
    lines.append('\t\t\t\t)')
    lines.append('\t\t\t)')

    lines.append('\t\t)')
    return '\n'.join(lines)


# Track schematic UUID for symbol instance paths
_sch_uuid = new_uuid()


def gen_power_symbol(lib_id, ref, value, at_x, at_y):
    """Generate a power symbol (+3V3, GND)."""
    pin_uuid = new_uuid()
    sym_uuid = new_uuid()
    lines = []
    lines.append('\t\t(symbol')
    lines.append(f'\t\t\t(lib_id "{lib_id}")')
    lines.append(f'\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t(unit 1)')
    lines.append('\t\t\t(exclude_from_sim no)')
    lines.append('\t\t\t(in_bom yes)')
    lines.append('\t\t\t(on_board yes)')
    lines.append('\t\t\t(dnp no)')
    lines.append(f'\t\t\t(uuid "{sym_uuid}")')
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Reference "{ref}")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y + 6.35} 0)')
    lines.append('\t\t\t\t(hide yes)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Value "{value}")')
    lines.append(f'\t\t\t\t(at {at_x + 0.127} {at_y - 2.656} 0)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append('\t\t\t(property')
    lines.append('\t\t\t\t(Footprint "")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t\t(hide yes)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append('\t\t\t(property')
    lines.append('\t\t\t\t(Datasheet "")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t\t(hide yes)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Description "Power symbol creates a global label with name \\"{value}\\"")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t\t(hide yes)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append(f'\t\t\t(pin "1" (uuid "{pin_uuid}"))')
    lines.append('\t\t\t(instances')
    lines.append('\t\t\t\t(project ""')
    lines.append(f'\t\t\t\t\t(path "/{_sch_uuid}/"')
    lines.append(f'\t\t\t\t\t\t(reference "{ref}")')
    lines.append('\t\t\t\t\t\t(unit 1)')
    lines.append('\t\t\t\t\t)')
    lines.append('\t\t\t\t)')
    lines.append('\t\t\t)')
    lines.append('\t\t)')
    return '\n'.join(lines)


def gen_connector(lib_id, ref, value, at_x, at_y, pin_count, footprint=""):
    """Generate a connector symbol with numbered pins."""
    pins = []
    pin_uuids = []
    for i in range(1, pin_count + 1):
        pin_uuids.append(new_uuid())
        pins.append((str(i), pin_uuids[-1]))

    lines = []
    lines.append('\t\t(symbol')
    lines.append(f'\t\t\t(lib_id "{lib_id}")')
    lines.append(f'\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t(unit 1)')
    lines.append('\t\t\t(exclude_from_sim no)')
    lines.append('\t\t\t(in_bom yes)')
    lines.append('\t\t\t(on_board yes)')
    lines.append('\t\t\t(dnp no)')
    lines.append(f'\t\t\t(uuid "{new_uuid()}")')
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Reference "{ref}")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y - 15.0} 0)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Value "{value}")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y + 15.0} 0)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    if footprint:
        lines.append('\t\t\t(property')
        lines.append('\t\t\t\t(Footprint "")')
        lines.append(f'\t\t\t\t(at {at_x} {at_y} 0)')
        lines.append('\t\t\t\t(hide yes)')
        lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
        lines.append('\t\t\t)')
    lines.append('\t\t\t(property')
    lines.append('\t\t\t\t(Datasheet "")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t\t(hide yes)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    for pin_num, pin_uuid in pins:
        lines.append(f'\t\t\t(pin "{pin_num}" (uuid "{pin_uuid}"))')
    lines.append('\t\t\t(instances')
    lines.append('\t\t\t\t(project ""')
    lines.append(f'\t\t\t\t\t(path "/{_sch_uuid}/"')
    lines.append(f'\t\t\t\t\t\t(reference "{ref}")')
    lines.append('\t\t\t\t\t\t(unit 1)')
    lines.append('\t\t\t\t\t)')
    lines.append('\t\t\t\t)')
    lines.append('\t\t\t)')
    lines.append('\t\t)')
    return '\n'.join(lines), pins


def gen_resistor(ref, value, at_x, at_y, footprint="Resistor_SMD:R_0805"):
    """Generate a resistor symbol."""
    pin1_uuid = new_uuid()
    pin2_uuid = new_uuid()
    sym_uuid = new_uuid()
    lines = []
    lines.append('\t\t(symbol')
    lines.append('\t\t\t(lib_id "Device:R")')
    lines.append(f'\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t(unit 1)')
    lines.append('\t\t\t(exclude_from_sim no)')
    lines.append('\t\t\t(in_bom yes)')
    lines.append('\t\t\t(on_board yes)')
    lines.append('\t\t\t(dnp no)')
    lines.append(f'\t\t\t(uuid "{sym_uuid}")')
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Reference "{ref}")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y + 6.35} 0)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Value "{value}")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y - 6.35} 0)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append('\t\t\t(property')
    lines.append(f'\t\t\t\t(Footprint "{footprint}")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t\t(hide yes)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append('\t\t\t(property')
    lines.append('\t\t\t\t(Datasheet "")')
    lines.append(f'\t\t\t\t(at {at_x} {at_y} 0)')
    lines.append('\t\t\t\t(hide yes)')
    lines.append('\t\t\t\t(effects (font (size 1.27 1.27)))')
    lines.append('\t\t\t)')
    lines.append(f'\t\t\t(pin "1" (uuid "{pin1_uuid}"))')
    lines.append(f'\t\t\t(pin "2" (uuid "{pin2_uuid}"))')
    lines.append('\t\t\t(instances')
    lines.append('\t\t\t\t(project ""')
    lines.append(f'\t\t\t\t\t(path "/{_sch_uuid}/"')
    lines.append(f'\t\t\t\t\t\t(reference "{ref}")')
    lines.append('\t\t\t\t\t\t(unit 1)')
    lines.append('\t\t\t\t\t)')
    lines.append('\t\t\t\t)')
    lines.append('\t\t\t)')
    lines.append('\t\t)')
    return '\n'.join(lines), (pin1_uuid, pin2_uuid)


def gen_wire(x1, y1, x2, y2, uuid_str=None):
    if uuid_str is None:
        uuid_str = new_uuid()
    return f'\t\t(wire (pts (xy {x1} {y1}) (xy {x2} {y2})) (uuid "{uuid_str}"))'


def gen_wire_multi(points, uuid_str=None):
    """points: list of (x, y) tuples."""
    if uuid_str is None:
        uuid_str = new_uuid()
    pts = ' '.join(f'(xy {x} {y})' for x, y in points)
    return f'\t\t(wire (pts {pts}) (uuid "{uuid_str}"))'


def gen_label(text, at_x, at_y, uuid_str=None):
    if uuid_str is None:
        uuid_str = new_uuid()
    return f"""\t\t(label "{text}"
		(at {at_x} {at_y} 0)
		(effects
			(font (size 1.27 1.27))
			(justify left bottom)
		)
		(uuid "{uuid_str}")
	)"""


def gen_text(text, at_x, at_y, size=1.27, uuid_str=None):
    if uuid_str is None:
        uuid_str = new_uuid()
    return f"""\t\t(text "{text}"
		(at {at_x} {at_y} 0)
		(effects (font (size {size} {size})))
		(uuid "{uuid_str}")
	)"""


def build_schematic(components, wires, labels, texts):
    """Assemble a complete .kicad_sch file.

    Format matches the backup schematic: empty lib_symbols, then top-level
    symbols after (embedded_fonts no).
    """
    lines = []
    lines.append(gen_schematic_header_no_libs())
    lines.append('\t(sheet_instances')
    lines.append('\t\t(path "/"')
    lines.append('\t\t\t(page "1")')
    lines.append('\t\t)')
    lines.append('\t)')
    lines.append('\t(embedded_fonts no)')
    lines.append('')
    for comp in components:
        lines.append(comp)
    for w in wires:
        lines.append(w)
    for lbl in labels:
        lines.append(lbl)
    for txt in texts:
        lines.append(txt)
    lines.append(gen_schematic_footer())
    return '\n'.join(lines)


def gen_schematic_header_no_libs():
    """Header with empty lib_symbols (symbols go at top level)."""
    return f"""(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "{new_uuid()}")
	(paper "A4")
	(lib_symbols)
"""


# ---------------------------------------------------------------- pcb

def gen_pcb_header():
    return f"""(kicad_pcb (version 20260206) (generator "pcbnew") (generator_version "10.0")
  (general (thickness 1.6) (legacy_teardrops no))
  (paper "A4")
"""


def gen_pcb_layers():
    """Generate the (layers ...) section for KiCad 10.0."""
    lines = []
    lines.append('  (layers')
    lines.append('    (0 "F_Cu" signal)')
    lines.append('    (1 "B_Cu" signal)')
    lines.append('    (2 "Edge.Cuts" user)')
    lines.append('  )')
    return '\n'.join(lines)


def gen_pcb_nets(net_names):
    """Generate net declarations for KiCad 10.0."""
    lines = []
    for i, name in enumerate(sorted(set(net_names)), start=1):
        lines.append(f'  (net {i} "{name}")')
    return '\n'.join(lines)


def gen_pcb_setup():
    return """  (setup
    (stackup)
  )
"""


def gen_pcb_footer():
    return """)"""


def gen_pcb_footprint(ref, footprint_lib, at_x, at_y, rotation=0, pads=None):
    """Generate a footprint instance (KiCad 10 format)."""
    if pads is None:
        pads = []
    fp_uuid = new_uuid()
    lines = []
    lines.append(f'  (footprint "{footprint_lib}"')
    lines.append(f'    (at {at_x} {at_y} {rotation})')
    lines.append(f'    (uuid "{fp_uuid}")')
    for pad in pads:
        lines.append(pad)
    lines.append('  )')
    return '\n'.join(lines)


def gen_pcb_pad(num, net_name, pad_type="thru_hole", shape="circle", size_x=1.0, size_y=1.0,
                drill=0.0, at_x=0.0, at_y=0.0, layers=None, uuid_str=None):
    """Generate a footprint pad (KiCad 10 format)."""
    if uuid_str is None:
        uuid_str = new_uuid()
    if layers is None:
        layers = ['"F_Cu"', '"B_Cu"']
    layers_str = ' '.join(layers)
    lines = []
    lines.append(f'    (pad "{num}" {pad_type} {shape}')
    lines.append(f'      (at {at_x} {at_y} 0)')
    lines.append(f'      (size {size_x} {size_y})')
    if drill > 0:
        lines.append(f'      (drill {drill})')
    lines.append(f'      (layers {layers_str})')
    lines.append(f'      (net "{net_name}")')
    lines.append(f'      (tstamp "{uuid_str}")')
    lines.append('    )')
    return '\n'.join(lines)


def gen_pcb_segment(net_name, start_x, start_y, end_x, end_y, width=0.25, layer="F_Cu",
                    uuid_str=None):
    """Generate a PCB track segment (KiCad 10 format)."""
    if uuid_str is None:
        uuid_str = new_uuid()
    return f'''  (segment (start {start_x} {start_y}) (end {end_x} {end_y}) (width {width}) (layer "{layer}") (net "{net_name}") (tstamp "{uuid_str}"))'''


def gen_pcb_via(net_ordinal, at_x, at_y, size=0.8, drill=0.4, layers='("F_Cu" "B_Cu")',
                uuid_str=None):
    """Generate a PCB via (KiCad 10 format)."""
    if uuid_str is None:
        uuid_str = new_uuid()
    return f'''  (via (at {at_x} {at_y} 0) (size {size}) (drill {drill}) (layers {layers}) (net {net_ordinal}) (tstamp "{uuid_str}"))'''


def gen_pcb_zone(net, layer, name="", uuid_str=None):
    """Generate a PCB zone (filled polygon)."""
    if uuid_str is None:
        uuid_str = new_uuid()
    return f'''  (zone (net {net}) (layer "{layer}") (net_name "{name}") (hatch edge) (pad_clearance 0.2) (via_clearance 0.3) (isolate 0.2) (min_thickness 0.0) (filled_areas_thickness 0.0) (smoothing_arc_deviation 0.01) (smoothing_level 0) (priority 0) (uuid "{uuid_str}") (fill (tenting_vias no) (filler_finish (top (pad_clearance 0.0) (via_clearance 0.0)) (bottom (pad_clearance 0.0) (via_clearance 0.0))) (filler_border (top (pad_clearance 0.0) (via_clearance 0.0)) (bottom (pad_clearance 0.0) (via_clearance 0.0))) (filler_escape (top (pad_clearance 0.0) (via_clearance 0.0)) (bottom (pad_clearance 0.0) (via_clearance 0.0))) (filler_thickness 0.0) (filler_smoothing_level 0) (filler_smoothing_arc_deviation 0.01)) (polygon (pts)) (island_remove_skinny_corners no) (island_min_area 0.0) (island_remove_thin_tracks no) (island_remove_stubs no) (island_remove_acute_angles no))'''


def gen_pcb_edge_cuts(x1, y1, x2, y2, x3, y3, x4, y4, uuid_str=None):
    """Generate a rectangular board outline on Edge.Cuts."""
    if uuid_str is None:
        uuid_str = new_uuid()
    lines = []
    lines.append(f'  (gr_line (start {x1} {y1}) (end {x2} {y2}) (layer "Edge.Cuts") (width 0.1) (tstamp "{uuid_str}"))')
    lines.append(f'  (gr_line (start {x2} {y2}) (end {x3} {y3}) (layer "Edge.Cuts") (width 0.1) (tstamp "{new_uuid()}"))')
    lines.append(f'  (gr_line (start {x3} {y3}) (end {x4} {y4}) (layer "Edge.Cuts") (width 0.1) (tstamp "{new_uuid()}"))')
    lines.append(f'  (gr_line (start {x4} {y4}) (end {x1} {y1}) (layer "Edge.Cuts") (width 0.1) (tstamp "{new_uuid()}"))')
    return '\n'.join(lines)


def build_pcb(footprints, segments, vias, zones, edge_cuts, net_names):
    """Assemble a complete .kicad_pcb file (KiCad 10 format)."""
    lines = []
    lines.append(gen_pcb_header())
    lines.append(gen_pcb_layers())
    lines.append(gen_pcb_nets(net_names))
    lines.append(gen_pcb_setup())
    for fp in footprints:
        lines.append(fp)
    for s in segments:
        lines.append(s)
    for v in vias:
        lines.append(v)
    for z in zones:
        lines.append(z)
    for e in edge_cuts:
        lines.append(e)
    lines.append(gen_pcb_footer())
    return '\n'.join(lines)