# ESP32_BME280 — Automation Plan

## Phase 1 — Audit and persistent foundation
- [x] Review supplied audit report.
- [x] Prepare foundation files in a separate package.
- [ ] Install files in project `.kilo/phase1_foundation/`.
- [ ] Verify JSON/YAML syntax and file presence.
- [ ] Re-check CLI/process/lock status and preserve source files.
- Exit condition: foundation files are present and validated; unknowns remain explicitly recorded.

## Phase 2 — Hardware identification and schematic recovery (not started)
- Identify exact ESP32 DevKit board and BME280 breakout.
- Resolve U1–U7 using physical evidence and reliable manufacturer documentation.
- Review the backup schematic in a staging copy.
- Run ERC on the staging copy if supported and accessible.
- Present a change plan and request approval before restoring to the active schematic.

## Phase 3 — Schematic verification (not started)
- Verify every symbol pin, power connection, net, connector, and pull-up decision.
- Run ERC and manually review the report.
- Request approval before writing to the active schematic.

## Phase 4 — Footprints and PCB layout (not started)
- Confirm board and breakout dimensions.
- Select verified footprints and inspect pin/pad mapping.
- Create outline, place components, and route under single-writer control.
- Obtain approval before active PCB edits and routing.

## Phase 5 — Validation and repair (not started)
- Run ERC/DRC, inspect every violation, repair in controlled iterations.
- Confirm board outline, clearances, net connectivity, and footprint/pad mappings.
- Do not treat a zero-count report alone as proof of correctness.

## Phase 6 — Manufacturing/release (not started)
- Require reviewed ERC/DRC, valid board geometry, output checks, and explicit user approval.
- Export Gerbers/drills only after approval.
- Review generated outputs before calling the board fabrication-ready.

## Stop conditions
- Unexpected destination contents or source changes.
- KiCad may be writing to files.
- Missing hardware evidence for electrical/physical assumptions.
- Permission or tool limitations.
- Any proposed action that would overwrite active files or backups without approval.
