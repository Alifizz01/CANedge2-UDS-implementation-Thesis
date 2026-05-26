# Changelog - VW ID Buzz CAN Bus Reverse Engineering

## 2026-05-05 - First decoded battery signals + project restructure

### What was done
- Imported the SD card dump from 2025-04-09 (14 new sessions, 00000007–00000023) under `data/sd_dumps_2A73E1CC_20250409/`.
- Discovered that sessions 12, 13, 17, 18, 22, 23 already contain working BMS UDS exchanges on `0x17FC007B` request → `0x17FE007B` response. The earlier broad inventory missed these because asammdf splits standard- and extended-ID frames into separate channel groups (`CAN1_Rx_IDE`, `CAN1_Tx_IDE`), and the original `mf4_reader.py` only read the first group.
- Built `src/uds_battery_decoder.py`: parses the VW MEB UDS PID CSV into a PID database (161 PIDs), decodes ISO-TP framing (SF/FF/NEG), maps payload bytes by position to formula labels (`WW`/`XX`/`YY`/`ZZ`), and evaluates the formula. Outputs `output/uds_decoded/{all_sessions.csv, summary.txt, plots/}`.
- **First decoded battery signals from VW ID Buzz** (1318 decoded values across the dataset):
  - SOC (0x028C): 66.8–68.0 %
  - HV pack voltage (0x1E3B): 368.0–368.5 V
  - HV pack current (0x1E3D): −4.96 to −2.4 A (FF partial only — multi-frame, ZZ byte missing)
  - Battery main temp (0x2A0B): 9.0–9.5 °C
  - Battery max temp + temp point (0x1E0E): 9.875–10.0 °C
  - Car operation mode (0x7448): "driving"
- Built `src/build_canedge_transmit_config.py` to generate `CANedge/config-01.08-built.json` programmatically from the PID CSV. Output: 32 entries (DiagSessionControl + TesterPresent + 13 priority PIDs + 16 sampled cell voltages + 6 temp points). Keeps the device transmit list and decoder in sync with one source of truth.
- Patched `src/mf4_reader.py` to iterate every CAN_DataFrame channel group, exposing both 11-bit and 29-bit IDs in a single DataFrame with `ide` column. The earlier `mdf.to_dataframe()` approach silently dropped extended-ID frames, which is why the Rust `can_analyzer` couldn't see UDS traffic.
- Restructured project: `Organisation Stuff/` → `admin/`, `apps/` folded into `tools/asammdf_gui/`, SD dump moved from repo root into `data/sd_dumps_2A73E1CC_20250409/`. Updated `CLAUDE.md` and path references in `src/`.

### Key technical notes
- Session 19 has 1,650,894 `CAN1_Errors` frames over 230s — bus-off from no-ACK retransmission, almost certainly captured with the vehicle off. The active 2025-04-09 device config only sent TesterPresent (now archived as `CANedge/config-01.08-testerpresent-only.json`).
- The active config that actually produced the working captures (sessions 12, 13) is **not** in the repo — neither `CANedge/config-01.08.json` nor `CANedge 09042025/config-01.08.json` matches the 8-PID schedule observed in the logs. The user iterated configs on the device beyond what was committed. The new `config-01.08-built.json` is what should go on the device next.
- VW MEB PID CSV has formula errors: `0x1E3D` HV current is documented as `(WW*2^32 + XX*2^16 + YY*2^8 + ZZ - 150000) / 100` — the `2^32` should be `2^24` for a 4-byte big-endian value. Decoder evaluates as written; at idle currents (WW=0) this doesn't matter, but it will produce wrong values at high currents. Worth fixing later.
- CANedge cannot send Flow Control frames, so 8+ byte UDS responses come back only as the First Frame (3 value bytes after `62 PID-HI PID-LO`). Decoder marks these `value_kind = 'partial'`. To get exact multi-byte values would require a real ISO-TP transmitter (e.g. a script on a Raspberry Pi / cantact attached to OBD-II).

### Files changed/created
- `src/uds_battery_decoder.py` — new
- `src/build_canedge_transmit_config.py` — new
- `src/mf4_reader.py` — rewrote to iterate all channel groups, exposes extended IDs
- `CANedge/config-01.08-built.json` — generated, 32-entry transmit list
- `CANedge/config-01.08-testerpresent-only.json` — archived 2025-04-09 experiment
- `CLAUDE.md` — updated for new layout, UDS pipeline, and findings
- Restructured: `Organisation Stuff/` → `admin/`, `apps/` → `tools/asammdf_gui/`, SD dump under `data/`

---

## 2026-04-09 - CANedge2 UDS Transmit Configuration

### What was done
- Analyzed the CANedge2 factory config (`CANedge/config-01.08.json`) from the device SD card
- Identified two critical issues preventing UDS transmit:
  1. CAN1 PHY mode was set to `Restricted` (mode=1), which blocks all transmissions
  2. No transmit list existed -- no UDS requests were being sent
- Changed CAN1 PHY mode to `Normal` (mode=0) to enable frame transmission
- Built a transmit list with **64 UDS ReadDataByIdentifier (0x22) requests** targeting the BMS ECU (`0x17FC007B`, 29-bit extended CAN ID):
  - 15 system-level battery PIDs (SOC, pack voltage, pack current, main temp, min/max temp, cell with highest/lowest voltage, circulation pump, coolant temps, energy content, operation mode, PTC heater current)
  - 18 temperature point PIDs (all temp sensors in the pack)
  - 31 cell voltage PIDs (evenly sampled across all 108 cells)
- Timing: 10-second period, 150ms stagger between each request (fits 64 requests in 9.6s)
- All transmitted frames set to `log: 1` so both requests and responses appear in MF4 logs
- Created a minimal test config (`config-01.08-test5.json`) with only 5 PIDs (SOC, voltage, current, temp main, max temp) for initial verification before deploying the full 64-PID config
- Wrote detailed deployment documentation in `CANedge/README_CANedge_Config.md`

### Key technical notes
- VW padding byte is `0x55` (not `0x00` or `0xAA`)
- Responses expected on `0x17FE007B` (29-bit extended)
- CAN1 filters already pass all extended IDs -- no filter changes needed
- ISO-TP limitation: multi-frame responses (battery serial, possibly total charge/discharge) won't work through the transmit list alone since CANedge can't send flow control frames
- Gateway may block UDS requests from OBD-II port -- test config exists to verify this quickly

### Files changed/created
- `CANedge/config-01.08.json` -- modified (PHY mode + 64 transmit entries)
- `CANedge/config-01.08-test5.json` -- new (5-PID test config)
- `CANedge/README_CANedge_Config.md` -- new (deployment docs)

All changes made across Claude sessions are logged here for cross-session reference.

---

## Session 1 - Initial Setup (prior sessions)
- Created `mf4_reader.py` to load MF4 files into pandas DataFrames
- Created `reverse_engineer.py` with 9 RE techniques (byte time series, bit heatmap, boundary detection, 16-bit candidates, counter/checksum detection, ASCII detection, scaling analysis, per-source comparison)
- Created `can_decoder.py` for signal decoding with decoded plots
- Created `uds_decoder.py` for UDS PID matching (no matches - CAN ID mismatch)
- Created `analyze_patterns.py` for statistical pattern analysis
- Generated 39 plots in `re_plots/` and 8 plots in `decoded_plots/`
- Created `DOCUMENTATION.md` with full analysis of all 7 CAN IDs
- Exported `can_data.csv` with all merged CAN data

## Session 2 - 2026-03-04
- Created `THESIS_PLAN.md` - 12-week thesis plan with 3 phases:
  - Phase 1 (Weeks 1-4): Data collection + literature review
  - Phase 2 (Weeks 5-8): Deep analysis + signal decoding
  - Phase 3 (Weeks 9-12): Validation + thesis writing
- Includes experiment matrix (14 driving scenarios), chapter outline, signal tracking table
- Created `DRIVING_CHECKLIST.md` - Concise checklist of driving cases for data collection proposal
- Created `CHANGELOG.md` (this file)
- Updated memory file with current project state and user preferences

## Session 3 - 2026-03-04 (continued)
- **Reorganized entire project folder structure:**
  - `src/` - all Python scripts (mf4_reader, reverse_engineer, can_decoder, analyze_patterns, uds_decoder)
  - `data/mf4/` - raw MF4 log files (was `log/`)
  - `data/csv/` - reference CSVs (was `csv/`)
  - `output/plots/` - all generated plots (merged `re_plots/` and `decoded_plots/`)
  - `output/can_data.csv` - exported data
  - `docs/` - all documentation (DOCUMENTATION.md, THESIS_PLAN.md, DRIVING_CHECKLIST.md)
  - `apps/` - asammdf GUI (unchanged)
  - Root: only `requirements.txt` and `CHANGELOG.md`
- Updated all script paths to use `PROJECT_ROOT` relative paths (no more hardcoded `log/`, `re_plots/`, etc.)
- Scripts now auto-resolve paths from `src/` using `Path(__file__).parent.parent`
- Run scripts from `src/` directory: `cd src && python -X utf8 mf4_reader.py`

## Session 4 - 2026-03-09
- **Built CAN Analyzer GUI** (`src/can_analyzer.py`) - SavvyCAN-like desktop application for MF4 files
  - **Sniffer tab**: Full CAN frame table with filtering by CAN ID, source, hex data search; color-coded rows; CSV export
  - **ID Analysis tab**: Per-CAN-ID statistics table (count, frequency, DLC, timing) + bar chart + pie chart
  - **Signal Plotter tab**: Interactive pyqtgraph plots with crosshair, zoom/pan; plot individual bytes or 16-bit combined (BE/LE); scaling (factor + offset); multi-signal overlay with legend; per-signal remove
  - **Payload Analysis tab**: Bit transition heatmap (which bits change most); byte statistics with pattern detection (counter, constant, binary, ASCII, enum); byte value distribution histograms
  - **Flow Analysis tab**: Message timeline scatter (time vs CAN ID); message rate chart (msgs/sec per ID); inter-message timing statistics table
  - **Hex Matrix tab**: SavvyCAN-style live byte value view with time slider playback, change highlighting, ASCII column, play/pause control
  - Dark theme (Catppuccin Mocha inspired), high-DPI support, Fusion style
  - Auto-loads MF4 from default data directory; also supports File > Open for custom MF4/CSV files
- Updated `requirements.txt` with new dependencies: PyQt5, pyqtgraph, numpy, matplotlib
- **Built Rust native CAN Analyzer v2** (`can_analyzer/`) — fast, GPU-accelerated alternative
  - Installed Rust 1.94 via rustup (winget)
  - Built with eframe/egui 0.31, egui_plot, csv crate, rfd for file dialogs
  - Reads from `output/can_data.csv` (instant load vs slow MF4 parsing)
  - **Data Flow tab** (primary feature): Real-time hex matrix with red/green byte-change highlighting, play/pause/step controls (0.5x-50x speed), change log with CAN ID filtering and CSV export
  - **Sniffer tab**: Virtual-scrolling frame table (9000+ rows at 60fps), filter by ID/source/hex
  - **Signal Plotter tab**: egui_plot interactive plots with zoom/pan, multi-signal overlay
  - **Stats tab**: Per-CAN-ID timing stats, byte change summary heatmap
  - Dark theme (Catppuccin Mocha), ~1100 lines of Rust
  - Run: `cd can_analyzer && cargo run --release` or `can_analyzer/target/release/can-analyzer.exe`
- **Added native MF4 loading** to Rust app:
  - File > Open MF4 File — loads a single .MF4 file directly
  - File > Open MF4 Directory — loads all .MF4 files from a CANedge2 log folder
  - Auto-detects `data/mf4/` directory on startup and converts automatically
  - Background conversion with spinner UI (uses Python/asammdf under the hood)
  - Seamless workflow: record with CANedge2 → open in CAN Analyzer
  - Falls back to CSV if already exported
- Updated memory file with complete project state, Rust toolchain details, and workflow notes.
