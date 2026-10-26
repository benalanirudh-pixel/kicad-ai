# ESP32_BME280 — Proposed Design Requirements

**Project:** `C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280\ESP32_BME280`
**KiCad version:** 10.0.7
**Status:** Proposed requirements only — no schematic/PCB changes made in this step.
**Hardware purchase:** Deferred until preliminary verification is complete.

## Inspected file status (read-only inspection)

| File | Status |
|------|--------|
| `ESP32_BME280.kicad_pro` | Project file present, minimal metadata |
| `ESP32_BME280.kicad_sch` | **Blank schematic** — contains only header, version 20260306, paper A4, empty `lib_symbols`, one empty sheet instance `/` page "1". No symbols, wires, labels, or nets. |
| `ESP32_BME280.kicad_pcb` | **Blank PCB** — header only, version 20260206. No footprints, tracks, zones, or Edge.Cuts outline. |
| `ESP32_BME280.kicad_prl` | Project preferences present |
| `~ESP32_BME280.kicad_pro.lck` | Lock file present — KiCad has the project open. Do not delete or terminate KiCad. |
| `outputs\validation\ESP32_BME280_erc_report.txt` | Pre-existing report (2026-10-18): 0 errors, 0 warnings on blank sheet |
| `outputs\validation\ESP32_BME280_drc_report.txt` | Pre-existing report (2026-10-18): 1 DRC violation — `invalid_outline`: board has malformed outline (no edges on Edge.Cuts layer) |
| `outputs\manufacturing\gerbers\` | 25 files, all header-only (444–477 bytes each), from blank board |
| `outputs\manufacturing\drill\ESP32_BME280.drl` | Header only, no drill hits |
| `scripts\` | Four PowerShell automation scripts — **not modified** |
| `scripts_backup/`, `scripts_backup_2/`, `scripts_backup_final/` | Backup directories — **not modified** |

No checks were run in this step; status above is from file inspection and pre-existing report files only.

## Hardware target

- ESP32 DevKit V1, 30-pin version
- BME280 breakout module using I²C
- Beginner-friendly carrier PCB

## Proposed connections (provisional)

| ESP32 (DevKit V1 30-pin) | BME280 breakout | Net name | Notes |
|--------------------------|-----------------|----------|-------|
| 3V3 pin | Breakout supply input (VCC/VDD/3.3V pin — verify breakout accepts 3.3V) | `3V3` | Supply voltage acceptance requires verification (item U1) |
| GND pin | Breakout GND | `GND` | Common ground |
| GPIO21 | Breakout SDA / SDIO / DATA | `I2C_SDA` | Provisional — pin assignment requires verification against DevKit V1 30-pin pinout (item U2) |
| GPIO22 | Breakout SCL / SCK / CLK | `I2C_SCL` | Provisional — pin assignment requires verification against DevKit V1 30-pin pinout (item U2) |

I²C pull-up resistors on SDA/SCL: required by I²C; presence on the breakout is unknown and requires verification (item U3). If the breakout lacks pull-ups, add them on the carrier PCB.

## Items requiring verification (unresolved assumptions)

- **U1:** Does the specific BME280 breakout accept 3.3 V on its supply input, or does it require 5 V? Does it include an onboard regulator?
- **U2:** Exact pin numbers for GPIO21/GPIO22 on the ESP32 DevKit V1 30-pin board; verify against the specific module's pinout before assigning symbol pins.
- **U3:** Does the BME280 breakout include I²C pull-up resistors on SDA/SCL? Value? Are they jumper-configurable?
- **U4:** Breakout connector type and pin spacing (e.g., 2.54 mm header vs. other). Does the carrier need a header, socket, or direct pads?
- **U5:** ESP32 DevKit V1 30-pin outline and mounting-hole dimensions for the carrier PCB.
- **U6:** BME280 breakout outline, pad positions, and mounting-hole dimensions for the carrier PCB.
- **U7:** BME280 I²C address (0x76 or 0x77, SDO-dependent) and whether the breakout exposes SDO.

## Footprint and physical-dimension information required

For the ESP32 DevKit V1 30-pin:
- Overall board dimensions (L × W)
- Pin pitch (typically 2.54 mm / 0.1 in), pin count per side (15 + 15)
- Pin hole diameter and pad size
- Mounting-hole locations and diameter
- Keep-out areas (USB connector, antenna, reset/button if relevant to carrier placement)

For the BME280 breakout:
- Overall dimensions (L × W)
- Header pitch and pin count
- Pin hole diameter and pad size
- Sensor component height (for clearance)
- Mounting-hole locations and diameter

## Scope exclusions (this step)

- No schematic symbols created
- No net connections created
- No PCB footprints placed
- No board outline (Edge.Cuts) created
- No ERC or DRC run
- No Gerber/drill generation
- No manufacturing files created or overwritten
- No physical hardware purchased

## Proposed next implementation stage

1. **Schematic symbols and net connections**
   - Place ESP32 DevKit V1 30-pin symbol (or equivalent ESP32-WROOM module symbol) in `ESP32_BME280.kicad_sch`
   - Place BME280 breakout symbol (generic I²C sensor symbol acceptable pending breakout selection)
   - Add power labels: `3V3`, `GND`
   - Add net labels: `I2C_SDA` (GPIO21), `I2C_SCL` (GPIO22)
   - Wire 3V3 → breakout supply, GND → breakout GND, GPIO21 → SDA, GPIO22 → SCL
   - Annotate provisional connections and verification items U1–U7 as schematic notes

2. **ERC**
   - Run `scripts\validate_project.ps1` for schematic ERC
   - Review `outputs\validation\ESP32_BME280_erc_report.txt`
   - Resolve ERC messages before proceeding

3. **Subsequent stages (future, out of scope for this step)**
   - Footprint assignment and validation against measured physical dimensions (U5, U6)
   - PCB layout with board outline, placement, routing
   - DRC check
   - Manufacturing file export only after design is complete and validation passes
