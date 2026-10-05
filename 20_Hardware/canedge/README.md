# CANedge2 logger profiles

Logger: CANedge2, device `2A73E1CC`, firmware 01.08.01, config schema 01.08 (see `device.json`).

Every folder in `profiles/` is **one complete SD-card setup**: copy its `.json` files to the root of the
card (or use **CANedge Studio > Write to SD card**) and the logger runs that profile from its next power-up.

```
profiles/03_drive_logging/
  config-01.08.json      what the logger does: CAN 1 settings + the UDS request list   (name required by the logger)
  schema-01.08.json      the config schema for firmware 01.08                          (from CSS Electronics)
  uischema-01.08.json    layout hints for the CANedge config editor                   (from CSS Electronics)
  README.md              what this profile is for (not needed on the card)
```

| Profile | Use it for | Signals |
|---|---|---|
| `01_smoke_test` | First test on a new car: is the bus up, does the BMS answer 29-bit UDS? | 5 |
| `02_probe_ecus` | Which ECUs behind the gateway answer at all | 6 |
| `03_drive_logging` | Driving: BMS system signals, all 18 temperatures, other ECUs, 17 cells | 62 |
| `04_cells_front_1_to_54` | Parked / charging: cell voltages 1-54 | 59 |
| `05_cells_rear_55_to_108` | Parked / charging: cell voltages 55-108 | 59 |
| `06_thesis_selected_signals` | The 60 identifiers evaluated in the thesis | 60 |
| `07_keepalive_test` | Troubleshooting: keep-alives only, no data reads | 0 |
| `_archive/…` | Superseded profiles, kept for history. Do not deploy. | |

**Which config is on a card?** The logger stores the CRC32 of the config it booted with in the card's
`device.json` (`cfg_crc32`). CANedge Studio compares that against every profile, so it can tell you which
profile is on the card, whether the logger has actually run it yet, and when a card holds something that
matches no profile (it can then save it here as a new profile folder).

**Backups.** Every write from CANedge Studio first copies the card's previous files to
`_card_backups/<date>_<device>/`.

New profiles can be generated from the PID list with `30_Software/build_canedge_transmit_config.py`;
they appear here as `profiles/generated_*/`.
