# ESP32_BME280 KiCad Automation Framework

KiCad 10.0 CLI-based automation for design-rule validation and manufacturing
export of the ESP32_BME280 project.

## Verified toolchain

- KiCad CLI: `C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe` (10.0.7)
- Project: `C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280`

## Scripts

- `scripts\check_environment.ps1` — Verify CLI, project files, version.
- `scripts\validate_project.ps1` — Schematic ERC + PCB DRC, save reports, parse reports independently of exit codes. Report format: KiCad "report" text only.
- `scripts\export_manufacturing.ps1` — Gerber + drill export (`-Confirm yes`; runs fresh ERC+DRC validation before every export; refused if validation fails or design incomplete).
- `scripts\check_outputs.ps1` — Verify outputs exist, are non-empty, zero-byte Gerbers rejected, header-only drill files rejected.

## See also

- `docs\AUTOMATION_GUIDE.md` — Full usage instructions and recovery procedure.

## Safety

KiCad has the project open; the lock file exists. Do not delete it or
terminate KiCad. These scripts never modify the schematic, PCB, or project
settings.

Manufacturing export runs fresh ERC+DRC validation before every export and is
refused if validation fails, reports contain violations, or the design is
incomplete. There is no silent bypass.

ERC/DRC are design-rule checks only — not hardware testing.
