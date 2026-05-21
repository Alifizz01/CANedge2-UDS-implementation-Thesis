# CANedge2 Configuration for VW ID.Buzz Battery UDS Requests

## Device Info
- Device ID: 2A73E1CC
- Firmware: 01.08.01
- Config schema: 01.08

## Config Files

| File | Purpose |
|------|---------|
| `config-01.08.json` | **Full config** -- 64 UDS requests covering all key battery parameters |
| `config-01.08-test5.json` | **Test config** -- only 5 PIDs (SOC, voltage, current, temp) for initial verification |
| `schema-01.08.json` | CANedge config schema (do not modify) |
| `device.json` | Device info (read-only) |

## What Was Changed (from factory default)

### 1. CAN1 PHY Mode: Restricted -> Normal
- `can_1.phy.mode`: changed from `1` (Restricted) to `0` (Normal)
- **Why**: Restricted mode cannot transmit frames. Normal mode is required for sending UDS requests.

### 2. Added Transmit List (64 entries) to CAN1
All requests target the **BMS ECU** at CAN ID `0x17FC007B` (29-bit extended).
Responses come back on `0x17FE007B`.

UDS service used: **ReadDataByIdentifier (0x22)**

Frame format: `03 22 XX XX 55 55 55 55`
- `03` = single-frame PCI, 3 payload bytes
- `22` = service ID (ReadDataByIdentifier)
- `XX XX` = DID (Data Identifier)
- `55` = VW-standard padding byte

### 3. Timing
- **Period**: 10,000 ms (each PID requested once every 10 seconds)
- **Delay stagger**: 150 ms between each request (avoids bus congestion)
- Full cycle: 64 requests x 150ms = 9,600ms, fits within 10s period

## Transmit List Contents

### System-Level Battery Parameters (PIDs 1-15)
| # | Name | DID | Unit | Calculation |
|---|------|-----|------|-------------|
| 1 | SOC (BMS) | 028C | % | XX/2.5 |
| 2 | HV Battery Voltage | 1E3B | V | (XX*256+YY)/4 |
| 3 | HV Battery Current | 1E3D | A | (WW*2^32+XX*2^16+YY*256+ZZ-150000)/100 |
| 4 | Battery Temp (main) | 2A0B | C | XX/2-40 |
| 5 | Battery Max Temp | 1E0E | C | (WW*256+XX)/64, ZZ=temp point# |
| 6 | Battery Min Temp | 1E0F | C | (WW*256+XX)/64, ZZ=temp point# |
| 7 | Cell# Highest Voltage | 1E33 | - | ZZ = cell number |
| 8 | Cell# Lowest Voltage | 1E34 | - | ZZ = cell number |
| 9 | Circulation Pump | 743B | % | XX = pump duty% |
| 10 | Coolant Inlet/Outlet | 189D | C | (YY*256+ZZ)/64 inlet, (WW*256+XX)/64 outlet |
| 11 | Total Charge/Discharge | 1E32 | kWh | multi-frame, may need ISO-TP |
| 12 | Energy Content | 2AB8 | kWh | TBD |
| 13 | Max Energy Content | 2AB2 | kWh | TBD |
| 14 | Operation Mode | 7448 | - | 0=standby, 1=driving, 4=AC charge, 6=DC charge |
| 15 | PTC Heater Current | 1620 | A | XX/4 |

### Temperature Points (PIDs 16-33)
| # | Name | DID | Calculation |
|---|------|-----|-------------|
| 16-31 | Temp Point 1-16 | 1EAE-1EBD | (XX*256+YY)/8-40 = C |
| 32 | Temp Point 17 | 7425 | (XX*256+YY)/8-40 = C |
| 33 | Temp Point 18 | 7426 | (XX*256+YY)/8-40 = C |

### Cell Voltages (PIDs 34-64, sampled 31 of 108 cells)
| # | Cells | DID range | Calculation |
|---|-------|-----------|-------------|
| 34-64 | 1,5,8,12,15,19,22,26,30,33,37,40,44,47,51,54,58,62,65,69,72,76,79,83,87,90,94,97,101,104,108 | 1E40-1EAB | (XX*256+YY)/1000+1 = V |

Cells are evenly sampled across the full 108-cell pack to cover all modules.

## Deployment Steps

### Step 1: Initial Test (use test config)
1. Copy `config-01.08-test5.json` to SD card as `config-01.08.json`
2. Insert SD card into CANedge2
3. Connect CANedge2 to OBD-II port (CAN channel 1)
4. Power on vehicle (ignition ON or charging)
5. Wait 30 seconds, then check log files
6. **Look for**: response frames on `0x17FE007B` in the MF4 log

### Step 2: Verify Responses
- If responses appear: the BMS is responding to UDS requests through the gateway
- If no responses: the gateway may be blocking requests (try Strategy B or C)
- If negative response (0x7F): check the error code (likely security access needed)

### Step 3: Full Deployment
1. If test succeeds, copy the full `config-01.08.json` to SD card
2. Monitor for any bus errors or BMS timeouts

## Known Limitations
- **Max 64 transmit entries**: only 31 of 108 cell voltages are sampled. To get all 108, you would need multiple config files rotated between tests, or a different approach.
- **No ISO-TP support**: The CANedge transmit list sends single CAN frames. PIDs that return multi-frame responses (like battery serial DID 0500, possibly total charge/discharge DID 1E32) will only get the first frame or a negative response. The CANedge cannot send flow control frames.
- **No TesterPresent**: If the BMS requires a periodic TesterPresent (0x3E) to keep the diagnostic session alive, that would consume one transmit slot. Currently not included -- add if needed.
- **Gateway filtering**: The VW gateway may block UDS requests from the OBD-II port. If so, a direct CAN bus tap (Strategy C) bypassing the gateway may be needed.

## Unchanged Settings
- CAN1 bit rate: default (500 kbit/s) -- standard for VW diagnostic CAN
- CAN1 filters: pass all standard + extended IDs (captures both passive traffic and BMS responses)
- CAN2: unchanged (available as second channel if needed)
- GNSS/IMU: unchanged (internal sensors still logging)
- Logging: MF4 format, 50MB split, cyclic, no compression/encryption
