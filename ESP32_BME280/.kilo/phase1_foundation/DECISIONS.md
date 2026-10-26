# ESP32_BME280 — Decisions Log

| ID | Decision | Status | Rationale |
|---|---|---|---|
| D1 | Keep automation context in `.kilo/phase1_foundation/` | Proposed | Separates state docs from KiCad source files |
| D2 | Preserve active KiCad files during Phase 1 | Approved constraint | Prevent accidental source changes |
| D3 | Preserve existing scripts and backups | Approved constraint | Retain known recovery points |
| D4 | Do not change global Kilo config or agent definitions without approval | Approved constraint | Avoid altering execution/model behavior unexpectedly |
| D5 | Do not declare fabrication-ready without reviewed ERC/DRC and output checks plus user approval | Approved constraint | Prevent premature release |
| D6 | Do not restore the provisional backup until assumptions and staging checks are complete | Proposed | Backup electrical correctness is unverified |

## Pending decisions
- Exact ESP32 DevKit variant and USB bridge.
- Exact BME280 breakout manufacturer/model.
- Breakout supply requirements and onboard regulation.
- I²C pull-up arrangement.
- I²C address selection.
- Connector and physical dimensions.
- Whether the carrier uses sockets, headers, or direct pads.
