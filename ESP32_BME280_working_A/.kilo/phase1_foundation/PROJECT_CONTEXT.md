# ESP32_BME280 — Project Context

## Project identity
- Project root: `C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280\`
- Reported KiCad version: 10.0.7 (CLI execution not independently verified)
- Reported KiCad CLI: `C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe`

## Reported active project state
- `ESP32_BME280.kicad_pro`: present; reported 679 lines.
- `ESP32_BME280.kicad_sch`: reported blank/header-only; 14 lines.
- `ESP32_BME280.kicad_pcb`: reported blank/header-only; 2 lines.
- `ESP32_BME280.kicad_prl`: present; reported 138 lines.
These are observations from the Phase 1 report, not a fresh filesystem check.

## Reported backups
- `scripts_backup\ESP32_BME280.kicad_sch.backup_20261020_125309`: reported 589 lines; provisional schematic.
- `scripts_backup\ESP32_BME280.kicad_sch.before_en_dash_`: reported 589 lines; reported identical to the dated backup. Identity has not been hash-verified.

## Existing scripts (preserve)
- `scripts/check_environment.ps1`
- `scripts/validate_project.ps1`
- `scripts/export_manufacturing.ps1`
- `scripts/check_outputs.ps1`

## Existing documentation (preserve)
- `README.md`
- `docs/AUTOMATION_GUIDE.md`
- `docs/DESIGN_REQUIREMENTS.md`

## Kilo Code configuration (preserve)
- Global config: `C:\Users\Anirudh\.config\kilo\kilo.jsonc`
- Agent definitions: `C:\Users\Anirudh\.config\kilo\agents\`
- Reported existing agents: architect, code-reviewer, code-skeptic, docs-specialist, pcb-architect.
- Reported global model: `kilo/anthropic/claude-sonnet-5`; reported session model: `nvidia/nemotron-3.5-super-vl:free`. Re-check before relying on these values.

## Safety rules
1. Do not overwrite or modify active `.kicad_sch`, `.kicad_pcb`, `.kicad_pro`, or `.kicad_prl` during Phase 1.
2. Do not modify existing automation scripts, backups, or global Kilo configuration/agents.
3. Never delete KiCad lock files or terminate KiCad processes to bypass a lock.
4. Do not claim ERC/DRC success proves electrical correctness.
5. Do not export manufacturing files until the design is verified, ERC/DRC reviewed, output checks pass, and the user explicitly approves export.
6. Use staging copies and a single-writer rule for any future source edits.
7. Mark facts as VERIFIED only when current evidence supports them; otherwise use REPORTED, UNKNOWN, or BLOCKED.
