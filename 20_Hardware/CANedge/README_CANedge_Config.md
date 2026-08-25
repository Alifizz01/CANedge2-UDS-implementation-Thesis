# CANedge2 Configuration for VW ID.Buzz Battery UDS Requests

## Device Info
- Device ID: 2A73E1CC
- Firmware: 01.08.01
- Config schema: 01.08

## Config Files

The folder is organised as a deployment workflow -- top entries are the first ones you copy to the SD card, bottom entries are tools/archive.

| File | Purpose |
|------|---------|
| `config-01.08-smoketest.json` | **Smoke test** -- 5 UDS reads + TesterPresent, BMS only. Verifies bus + bit rate + extended-ID addressing before deploying sweeps. |
| `config-01.08-probe-ECUs.json` | **Multi-ECU reachability probe** -- 8 entries, one read per target ECU at 2 s period. Confirms which non-BMS ECUs the OBD-II gateway routes to (DCDC / EDU / Climate / Gateway / GPS). |
| `config-01.08-drive.json` | **Drive logging** -- 64 entries: full BMS system signals, all 18 temp points, 5 non-BMS ECUs, 17 sampled cells. Deploy during active driving. |
| `config-01.08-cells-front.json` | **Cells 1-54** (DIDs 1E40-1E75) -- 61 entries: BMS keep-alive + T1 core + first pack half. Deploy while parked / charging. |
| `config-01.08-cells-rear.json` | **Cells 55-108** (DIDs 1E76-1EAB) -- 61 entries: BMS keep-alive + T1 core + second pack half. Deploy while parked / charging. Together with `cells-front` covers all 108 cells. |
| `config-01.08-keepalive-test.json` | Diagnostic tool: TesterPresent / WakeUp on multiple ECU IDs. Use if an ECU stops responding to verify session-keepalive behavior in isolation. |
| `_archive/` | Older / superseded configs kept for history; do not deploy. |
| `schema-01.08.json` | CANedge config schema (do not modify) |
| `device.json` | Device info (read-only) |

### Deployment naming

The CANedge firmware loads exactly one config file from the SD card, and it must be named `config-01.08.json` (the schema version in the filename has to match the firmware schema). So whichever of the files above you want to deploy, you copy it to the SD card root and rename to `config-01.08.json`. The library names above are just for clarity in this folder -- the firmware never sees them.

### Rotation strategy

The CANedge transmit list is capped at 64 entries, but covering all 108 cells + 18 temp points + 5 ECU groups exceeds that. The drive + cells-front + cells-rear files are rotated on the SD card between test sessions:

- **Drive tests** -> deploy `drive`. Captures real-time power flow (HV V/I, DC/DC, EDU, climate, accelerator) plus all temps; cells sampled every ~6th for module-level outliers.
- **Charging / parked tests** -> alternate `cells-front` and `cells-rear` between runs to capture both pack halves at cell granularity.
- All three share an identical `T1` core (SOC, HV V, HV I, Tmain, OpMode) at delays 300-900 ms, so logs from different rotations can be time-aligned on those signals.

### Multi-ECU addressing

`drive.json` talks to 6 different ECUs in one cycle (default UDS session, no per-ECU TesterPresent):

| ECU | CAN ID req | CAN ID resp | id_format | DIDs polled |
|---|---|---|---|---|
| BMS | `17FC007B` | `17FE007B` | 29-bit ext | T1 core + sys signals + temp points + sampled cells |
| DC/DC converter | `17FC00B9` | `17FE00B9` | 29-bit ext | `465B` current, `465D` voltage |
| Front EDU | `17FC0076` | `17FE0076` | 29-bit ext | `210E` drive mode, `0364` HV aux power, `295A` odometer |
| Climate | `0x746` | `0x7B0` | **11-bit std** | `2609` outdoor T, `2613` inside T, `F449` pedal, `42DB` CO2, `263B` recirc |
| Gateway / energy | `0x710` | `0x77A` | **11-bit std** | `2AB2` max energy content |
| Navigation / GPS | `0x767` | `0x7D1` | **11-bit std** | `2431` satellite count |

`cells-front` and `cells-rear` only address the BMS.

**Important — verify reachability first.** Whether the vehicle's gateway routes UDS requests addressed to non-BMS ECUs through the OBD-II port is vehicle-specific and not yet verified on this ID.Buzz. Deploy `config-01.08-probe-ECUs.json` (2-second period, 8 entries) and inspect the resulting MF4 for response frames on the IDs in the "CAN ID resp" column above. Any ECU that returns nothing in the probe is unreachable and the corresponding `drive.json` entries will burn slots silently -- either add a per-ECU DiagSession+TesterPresent, or drop those reads from `drive.json`.

## What Was Changed (from factory default)

### 1. CAN1 PHY Mode: Restricted -> Normal
- `can_1.phy.mode`: changed from `1` (Restricted) to `0` (Normal)
- **Why**: Restricted mode cannot transmit frames. Normal mode is required for sending UDS requests.

### 2. CAN1/2 PHY bit-rate: auto -> manual 500 kbit/s
- `can_1.phy.bit_rate_cfg_mode`: changed from `0` (auto-detect) to `1` (manual)
- Added `bit_rate_std: 500000` and `bit_rate_fd: 2000000`
- **Why**: In auto-detect, the CANedge waits for valid bus traffic to identify the rate before going active. On a quiet/bench bus or at power-on before the vehicle is fully awake, it never goes bus-active and never transmits. Manual 500 k matches the ID.Buzz powertrain/diag CAN and lets the controller go active immediately.
- Same change applied to `can_2.phy` (listen-only mode 1 still needs a defined bit rate to receive).

### 3. Transmit List structure (drive / cells-front / cells-rear)
All three rotation files begin with a 7-entry shared header before each per-file payload:

| Slot | Name | Service | ECU | Purpose |
|---|---|---|---|---|
| 1 | `BMS_DiagSessExt` | `10 03` | 17FC007B | Switch BMS to extended diagnostic session |
| 2 | `BMS_TP` | `3E 00` | 17FC007B | Keep extended session alive (S3 timer) |
| 3-7 | `T1_*` | `22 XX XX` | 17FC007B | Core BMS reads (SOC 028C, HV V 1E3B, HV I 1E3D, Tmain 2A0B, OpMode 7448) |

UDS service for reads: **ReadDataByIdentifier (0x22)**, frame `03 22 XX XX 55 55 55 55` (single-frame PCI 03, 3 payload bytes, `55` VW padding).

For multi-ECU calls in `drive.json`, requests use **default UDS session** (no per-ECU DiagSession / TesterPresent) -- the BMS extended-session switch only affects the BMS.

### 4. Timing
- **Period**: 10,000 ms per entry
- **Delay stagger**: 150 ms between consecutive entries
- `drive.json` cycle: 64 entries x 150ms = 9,600ms (last delay 9,450ms)
- `cells-front` / `cells-rear` cycle: 61 entries, last delay 9,000ms
- Both fit comfortably in the 10s period; the >400ms idle tail gives the bus time to drain the last response.

## Transmit List Contents

### Shared T1 core (in drive / cells-front / cells-rear)
| Name | DID | ECU | Unit | Calculation |
|---|---|---|---|---|
| SOC (BMS) | 028C | 17FC007B | % | XX/2.5 |
| HV Battery Voltage | 1E3B | 17FC007B | V | (XX*256+YY)/4 |
| HV Battery Current | 1E3D | 17FC007B | A | (W*2^24+X*2^16+Y*2^8+Z-150000)/100 |
| Battery Temp (main) | 2A0B | 17FC007B | C | XX/2-40 |
| Operation Mode | 7448 | 17FC007B | enum | 0=standby, 1=driving, 4=AC chg, 6=DC chg |

### drive.json -- system-wide (64 entries)
BMS system signals (in addition to T1 core):
| Name | DID | Unit | Calculation |
|---|---|---|---|
| Battery Max Temp | 1E0E | C | (W*256+X)/64, Z=temp point# |
| Battery Min Temp | 1E0F | C | (W*256+X)/64, Z=temp point# |
| Cell# Highest Voltage | 1E33 | -- | Z = cell number |
| Cell# Lowest Voltage | 1E34 | -- | Z = cell number |
| Circulation Pump | 743B | % | XX |
| Coolant Inlet/Outlet | 189D | C | inlet (Y*256+Z)/64, outlet (W*256+X)/64 |
| Dynamic Charge Limit | 1E1B | A | (X*256+Y)/5 |
| Dynamic Discharge Limit | 1E1C | A | (X*256+Y)/5 |
| BMS-reported Speed | F40D | km/h | XX |
| PTC Heater Current | 1620 | A | XX/4 |

BMS temp points 1-18 (DIDs 1EAE-1EBD, 7425, 7426), all `(X*256+Y)/8-40 = C`.

Non-BMS ECUs (default UDS session, no DiagSession/TP):
| Name | DID | ECU | id_format | Unit | Calculation |
|---|---|---|---|---|---|
| DC/DC current (HV->12V) | 465B | 17FC00B9 | 29-bit | A | (X*256+Y)/16 |
| DC/DC voltage (HV->12V) | 465D | 17FC00B9 | 29-bit | V | (X*256+Y)/512 |
| Drive mode (P/N/D/B/R) | 210E | 17FC0076 | 29-bit | enum | Y: 08=P, 05=D, 0C=B, 07=R, 06=N |
| HV auxiliary power | 0364 | 17FC0076 | 29-bit | kW | (X*256+Y)/10 |
| Odometer | 295A | 17FC0076 | 29-bit | km | X*2^16+Y*256+Z |
| Outdoor temperature | 2609 | 0x746 | 11-bit | C | X/2-50 |
| Inside temperature | 2613 | 0x746 | 11-bit | C | (X*256+Y)/5-40 |
| Accelerator pedal | F449 | 0x746 | 11-bit | % | X/2.55 |
| Cabin CO2 | 42DB | 0x746 | 11-bit | ppm | Y*100 |
| Recirculation flap | 263B | 0x746 | 11-bit | enum | 00=fresh, 04=recirc |
| Max energy content | 2AB2 | 0x710 | 11-bit | Wh | per CSV (see VW MEB UDS PIDs list) |
| GPS sat count | 2431 | 0x767 | 11-bit | count | Y |

Sampled cells in `drive.json` (17 of 108, every ~6th cell): 1, 7, 13, 19, 25, 31, 37, 43, 49, 55, 61, 67, 73, 79, 85, 91, 97. DIDs `1E40 + (cell# - 1)`. Scaling: `(X*256+Y)/1000+1 = V`.

### cells-front.json (61 entries)
T1 core (5) + DiagSession + TP (2) + cells 1-54 (DIDs 1E40-1E75).

### cells-rear.json (61 entries)
T1 core (5) + DiagSession + TP (2) + cells 55-108 (DIDs 1E76-1EAB).

Together `cells-front` and `cells-rear` cover all 108 cells with no gaps or overlap.

## Deployment Steps

### Step 1: Smoke test
1. Copy `config-01.08-smoketest.json` to SD card, rename to `config-01.08.json`.
2. Insert SD card into CANedge2, connect to OBD-II port (CAN1), power on the vehicle.
3. Wait 30 seconds, pull the card, check the MF4 log for response frames on `0x17FE007B`.
4. If responses appear: bus + bit-rate + extended-ID addressing are all working.
5. If negative response (`7F 22 XX`): check error byte -- `7F 22 31` = requestOutOfRange (wrong DID/ECU), `7F 22 13` = invalid format, `7F 22 33` = security access needed.

### Step 2: Deploy a logging config
Pick the file that matches your test plan: `drive.json` for driving, `cells-front.json` / `cells-rear.json` for cell scans while parked or charging. Copy to SD card and rename to `config-01.08.json`.

### Step 3: Rotation across sessions
For full pack characterisation, alternate `cells-front` and `cells-rear` across separate charging sessions. The T1 core in every config gives you a common time-aligned reference (SOC, V, I, Tmain, OpMode).

## Known Limitations
- **64-entry transmit cap**: drove the drive / cells-front / cells-rear split. A single config cannot cover all ECUs + all 108 cells.
- **No ISO-TP support**: the CANedge transmit list sends single CAN frames only, so multiframe DIDs (battery serial `0500`, total charge/discharge `1E32`, VIN `F802`, energy content `2AB8`, A/C compressor `0800`, PTC air heater `0801`, humidity `27C4`, chair heating `3ADF`/`3AE0`, 12V SoC `2AF7`) are intentionally NOT polled -- they would only return the first 6 bytes of a longer response.
- **Default-session non-BMS reads (drive.json)**: if any of DC/DC, EDU, climate, gateway or GPS stays silent, that ECU may require its own `10 03` DiagSession + periodic `3E 00` TesterPresent -- not currently included to save slots. Add per ECU if responses don't appear.
- **Gateway filtering**: if requests work in `smoketest` (BMS only) but additional `drive.json` ECUs return nothing, the vehicle gateway may be filtering -- a direct CAN bus tap downstream of the gateway would be needed.

## Unchanged Settings
- CAN1 filters: pass all standard + extended IDs (captures both passive bus traffic and the targeted UDS responses)
- CAN2: listen-only at 500 kbit/s -- available for a second bus tap
- GNSS/IMU: internal sensors still logging
- Logging: MF4 format, 50 MB split, cyclic, no compression/encryption
