# Phase D8 — Trusted KiCad Project Baseline Audit

**Project:** `C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280`
**Audit dir:** `.kilo\phaseD8_audit` (new, uniquely named)
**Rule:** All inspection read-only. Active `.kicad_sch` / `.kicad_pcb` NOT modified. No candidates overwritten/deleted. No KiCad lock files removed. No KiCad terminated.

---

## Task 1 — Active project inspection

### Active schematic `ESP32_BME280.kicad_sch`
- SHA-256: `0dabdaabe5d45dc1fb20f258602b99cd1f5f25076761355e451a0af7e09244a4`
- Size: 41,168 bytes
- Mtime: 2026-10-26 10:16:20
- Expected pre-D6 hash: `730a78362b8e0f384b39b98a947114af2c738c91d5ad1d719f6d3040c4e5b360` — **does NOT match** (corrupted per Phase D7)

**Content (read-only):**
- Symbols: 16 symbol references (incl. lib defs). Real placed instances: `J1` (Conn_01x15, ESP32 DevKit header pins 1-15), `J2` (Conn_01x15, pins 16-30), `J3` (Conn_01x06, BME280 breakout), `R1` (Device:R, 4k7), `R2` (Device:R, 4k7), power symbols `+3V3`, `GND`, `PWR_FLAG` x2.
- Pins: present on every symbol instance.
- Labels: global labels present (`3V3` x6, `GND` x4, `I2C_SDA` x3, `I2C_SCL` x3).
- **Wires: 0. Junctions: 0.** No `(wire` or `(junction` entries anywhere in the file.

**Assessment:** The schematic has placed symbols, pins, and global labels, but **no electrical connectivity is drawn** (no wires). Components are not wired to nets. This is NOT a complete wired circuit; it is a parts placement with net-name labels only.

### Active PCB `ESP32_BME280.kicad_pcb`
- SHA-256: `11aea2c4fe51607d5259807815a89546bf4c9b34b4513fd16c769a6fc3b8c48b` — matches expected pre-D6 hash
- Size: 80 bytes
- Content: `(kicad_pcb (version 20260206) (generator "pcbnew") (generator_version "10.0"))` — header only.
- Footprints: 0. Pads: 0. Tracks: 0. Zones: 0. Graphic lines: 0.

**Assessment:** The PCB is an empty board with no outline, footprints, pads, tracks, or zones. NOT a real PCB.

### Project file `ESP32_BME280.kicad_pro`
- References top sheet `ESP32_BME280.kicad_sch`.
- `pinned_symbol_libs`: empty. `pinned_footprint_libs`: empty.
- No `sym-lib-table` or `fp-lib-table` present in the project directory, so symbol/footprint library resolution would fall back to global KiCad configuration (not project-local/pinned). Library resolution cannot be verified from project files alone.

---

## Task 2 — Design candidates (read-only comparison)

| Candidate (SCH) | SHA-256 | Size | Wires | Symbols | Labels | Real wired circuit? |
|---|---|---|---|---|---|---|
| Active `ESP32_BME280.kicad_sch` | `0dabdaab...` | 41,168 | 0 | 16 | present | **No** (unwired) |
| `ESP32_BME280_working\ESP32_BME280.kicad_sch` | `0dabdaab...` | 41,168 | 0 | 16 | present | **No** (byte-identical to corrupted active) |
| `ESP32_BME280_working_A\ESP32_BME280.kicad_sch` | `37fc370f...` | 37,751 | 14 | 13 | 2 | **Yes** (wired; nets I2C_SCL/I2C_SDA/3V3/GND/GPIO) |
| `scripts_backup\ESP32_BME280.kicad_sch.backup_20261020_125309` | `fb4b939f...` | 16,159 | 14 | 0* | 2 | Partial / older (smaller) |
| `outputs\ai_staging\20261025_193847\ESP32_BME280.kicad_sch` | `9e0026e0...` | 15,747 | 14 | 0* | 2 | AI staging (corruption source) |
| `outputs\ai_staging\20261025_201832\ESP32_BME280.kicad_sch` | `8bb4e28b...` | 15,747 | 14 | 0* | 2 | AI staging |
| `outputs\ai_staging\20261025_202544\ESP32_BME280.kicad_sch` | `70b62e31...` | 15,747 | 14 | 0* | 2 | AI staging |

\* Symbol-instance regex count unreliable for these files, but all show wires=14 (some top-level wiring present).

| Candidate (PCB) | SHA-256 | Size | Footprints | Pads | Tracks | Zones | Gr lines | Real PCB? |
|---|---|---|---|---|---|---|---|---|
| Active `ESP32_BME280.kicad_pcb` | `11aea2c4...` | 80 | 0 | 0 | 0 | 0 | 0 | **No** (empty) |
| `working\ESP32_BME280.kicad_pcb` | `9732c378...` | 79 | 0 | 0 | 0 | 0 | 0 | **No** (empty) |
| `working_A\ESP32_BME280.kicad_pcb` | `9732c378...` | 79 | 0 | 0 | 0 | 0 | 0 | **No** (empty) |
| `ai_staging\20261025_193847\ESP32_BME280.kicad_pcb` | `b35708dd...` | 16,720 | 0 | 40 | 14 | 0 | 4 | **Inconsistent** (tracks, no footprints) |
| `ai_staging\20261025_201832\ESP32_BME280.kicad_pcb` | `6ea64574...` | 12,692 | 5 | 40 | 0 | 0 | 4 | **Inconsistent** (footprints, no tracks) |
| `ai_staging\20261025_202544\ESP32_BME280.kicad_pcb` | `4b9fc660...` | 12,692 | 5 | 40 | 0 | 0 | 4 | **Inconsistent** (footprints, no tracks) |

**Provenance:** No candidate matches the expected pre-D6 SCH hash `730a7836...`. No candidate's provenance establishes it as the original. `working_A` has a genuinely wired schematic (14 wires, meaningful net names) but an empty PCB; its origin is unverified. The `ai_staging` PCBs are internally inconsistent (tracks without footprints, or footprints without tracks), indicating partial/generated output, not a complete design.

**No single candidate pairs a complete wired schematic with a complete PCB.**

---

## Task 3 — KiCad CLI validation

KiCad CLI (`kicad-cli` / `kicad`) is **not installed** on this system (no `kicad-cli` on PATH, no KiCad program files found). Therefore read-only ERC/DRC checks or schematic exports via the KiCad CLI could **not** be performed. This limitation is noted; no CLI-based validation was run, and no manufacturing export was attempted (per safety rules). A successful file parse would not constitute proof of electrical or fabrication correctness in any case.

---

## Task 4 — Recommendation

**Choice: C. Start a new clean reference design because no candidate is suitable.**

### Evidence supporting C
1. **No verified known-good source exists.** The expected pre-D6 SCH hash `730a7836...` was not found in any project-local backup, working copy, ai_staging folder, or editor backup (Phase D7 established this). Option A (recover known-good project) is not possible.
2. **No candidate is a complete design.** The active schematic is unwired (0 wires/junctions) despite having symbols/labels. The active PCB is empty. `working_A` has a wired schematic but an empty PCB, and unverified provenance. The `ai_staging` PCBs are internally inconsistent/partial. None of the candidates pairs a complete schematic with a complete PCB.
3. **Provenance is unverified for every candidate.** Per the rules, no candidate may be claimed as the original unless provenance establishes it — none does.
4. **Repair is prohibited.** The safety rules forbid generating or repairing any schematic or PCB, so the gaps (missing wires in the sch, missing board content in the pcb) cannot be filled from within this audit.

### Not chosen
- **A (recover known-good):** No exact/verified source exists (Phase D7).
- **B (approve existing candidate):** No candidate is complete or verified; approving an unwired schematic / empty PCB / partial ai_staging board as a baseline would embed defects into the new baseline.

### Conclusion
No usable trusted baseline exists in the project. Proceed only by starting a new clean reference design, outside the constraints of this audit. Do not modify the active project or begin PCB generation from any candidate.

---

## File integrity confirmation (active project, unmodified)

| File | SHA-256 | Size |
|---|---|---|
| `ESP32_BME280.kicad_sch` | `0dabdaabe5d45dc1fb20f258602b99cd1f5f25076761355e451a0af7e09244a4` | 41,168 |
| `ESP32_BME280.kicad_pcb` | `11aea2c4fe51607d5259807815a89546bf4c9b34b4513fd16c769a6fc3b8c48b` | 80 |

Both active files were read-only inspected; no writes were made to them. No backups, journals, staging files, recovery candidates, or KiCad lock files were overwritten, deleted, or cleaned up. KiCad was not terminated.
