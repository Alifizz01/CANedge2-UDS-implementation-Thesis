# Thesis Plan & Methodology

## General Info

- **Title:** "Inside the Battery: Entschluesselung von Batteriedaten ueber den CAN-Bus"
- **Institution:** Technische Hochschule Ingolstadt / CARISSMA
- **Supervisors:** Markus Gregor, Prof. Dr. Hans-Georg Schweiger
- **Vehicle:** Volkswagen ID Buzz (MEB platform)
- **Start:** March 2026
- **Duration:** 12 weeks (3 months)

---

## What This Thesis Is About

The core goal is to access and decode **battery-related data** from the VW ID Buzz over its CAN bus. Things like state of charge, pack voltage, current flow, cell voltages, and battery temperatures — all the stuff that the Battery Management System (BMS) handles internally but doesn't openly share with the outside world.

VW doesn't publish their CAN signal definitions (DBC files). So there's no documentation that tells you "byte 3 of CAN ID 0x123 is the battery temperature." You have to figure it out yourself through reverse engineering, or by using known UDS diagnostic interfaces.

This thesis combines two approaches:
1. **Passive CAN bus recording** — capture whatever the vehicle broadcasts and reverse engineer the meaning
2. **Active UDS diagnostic requests** — send specific queries to the BMS ECU and decode the responses

The focus is specifically on **battery parameters**, not general vehicle signals like speed or steering. This is what matters most for CARISSMA's research on electric vehicle battery systems.

---

## Why Focus On Battery Instead Of Everything?

The thesis assignment specifically says "Entschluesselung von Batteriedaten" (decoding battery data) and lists the tasks as:
- Recording and analysis of CAN signals during driving and charging
- Reverse engineering manufacturer-specific CAN messages
- **Mapping raw CAN data to battery parameters**
- Developing tools for automated data storage and visualisation
- Documentation of decoded signals

Battery parameters are what CARISSMA needs for their research. Trying to reverse engineer every single vehicle signal (steering, lights, HVAC, etc.) would spread the thesis too thin and miss the point. Some general signals like speed or temperatures are still useful as context (e.g., correlating battery current with driving speed), but they're not the main deliverable.

The reality is also that the passive CAN recording I have (7 CAN IDs, 0x065-0x06F, all 11-bit standard) probably doesn't contain the core battery data anyway. The important battery parameters (cell voltages, SOC, pack current) are managed by the BMS ECU and are accessible through **UDS diagnostic requests** using 29-bit extended CAN IDs. So the data collection strategy has to change.

---

## The Two-Track Approach

### Track 1: UDS Diagnostic Requests (Primary)

The VW MEB UDS PIDs list I have contains **145 battery-related parameters**, including:
- 108 individual cell voltages
- 18 temperature sensor points
- SOC, pack voltage, pack current
- Charging/discharging limits
- Cooling system state

These are accessed by sending UDS ReadDataByIdentifier (service 0x22) requests to the BMS ECU at CAN ID `0x17FC007B` and reading responses from `0x17FE007B`.

The challenge: the CANedge2 is primarily a logger, not a diagnostic tool. I need to figure out if it can also send these requests (via its transmit list feature), or if I need a separate diagnostic tool.

### Track 2: Passive CAN Analysis (Secondary)

The 7 CAN IDs I already have from passive recording might contain some battery-related data — possibly temperatures (0x066 B[3] and 0x067 B[5] already decoded as temperature with raw-40 offset), or maybe voltage/current signals hiding in the unidentified dynamic bytes. I'll re-examine these with a battery-specific lens.

This is also where the reverse engineering methodology comes in. Even if these signals turn out to not be battery-related, the methodology is applicable and worth documenting.

---

## Data Collection Strategy (Updated)

### Problem
The initial passive recording only captured 11-bit standard CAN IDs. Battery data from the BMS uses 29-bit extended CAN IDs and requires active diagnostic requests.

### Strategy A (Preferred): CANedge2 Transmit List
Configure the CANedge2 to periodically send UDS requests while logging responses.
- Need to verify: does CANedge2 support 29-bit extended IDs in transmit mode?
- Need to verify: does it handle ISO-TP for multi-frame responses (cell voltages)?

### Strategy B (Fallback): External Diagnostic Tool + CANedge2 Logging
Use a separate OBD-II adapter (OBDEleven, VCDS, or Python+PCAN-USB) to send requests.
CANedge2 just logs everything passively via Y-splitter.

### Strategy C: Direct CAN Bus Tap
Connect directly to the BMS CAN bus (bypassing the gateway) to capture broadcast messages that the gateway might filter out.

See `Data_Collection_Strategy.md` for full details on each approach.

---

## Reverse Engineering Methodology (9 Techniques)

These techniques are applied to the passively recorded CAN data:

1. **Byte time series** — plot each byte over time. Smooth curves = sensors, sawtooth = counters, flat = constants, discrete steps = state machines
2. **Bit-level heatmaps** — which bits change and how often. Bits in the same signal change together
3. **Signal boundary detection** — find where signals start and end using bit co-change rates
4. **16-bit combination testing** — try big-endian and little-endian combinations for multi-byte signals
5. **Counter detection** — find rolling message sequence counters
6. **Checksum detection** — test if last byte is XOR/SUM of the others
7. **ASCII detection** — some VW messages embed ASCII text markers
8. **Scaling factor analysis** — try common automotive formulas (raw-40 for temp, raw*0.01 for speed)
9. **Per-source comparison** — analyse each recording session separately (crucial for 0x06F)

For UDS response data, the decoding is more straightforward since the PID list already provides the calculation formulas. The main work there is:
- Configuring the request setup
- Capturing clean responses
- Validating the decoded values against dashboard readings or external measurements

---

## What I've Found So Far

### Passive CAN (11-bit IDs)

| Signal | CAN ID | What It Is | Battery Relevant? |
|--------|--------|-----------|-------------------|
| NM_STATE | 0x065 B[0] | Network management heartbeat | Indirectly (shows ECU wake state) |
| OperatingMode | 0x066 B[0] | Init vs Active mode | Indirectly |
| MsgCounter | 0x066 B[1:2] | 16-bit rolling counter | No (protocol signal) |
| Temperature_A | 0x066 B[3] | Temperature, raw-40 = 8-10 C | **Maybe** — could be battery temp |
| Temperature_C | 0x067 B[5] | Temperature, raw-40 = 11-13 C | **Maybe** — could be battery temp |
| StatusFlag | 0x068 B[3] | Binary 0/1 | Unknown |
| 0x06F B[0:7] | 0x06F | 8 independent signals, NOT encrypted | Unknown — need more data |

### UDS (29-bit IDs)
Not yet captured. This is the priority for Week 3.

---

## What I Expect / Realistic Goals

**Best case:** I get UDS working, decode SOC, voltage, current, cell voltages, and battery temperatures. The thesis delivers a validated set of battery signal definitions with decoding formulas, plus the analysis tools and methodology.

**Realistic case:** I get the basic UDS parameters (SOC, voltage, current, main temp) working. Cell voltages might be tricky if ISO-TP multi-frame isn't supported by the CANedge2. I document everything thoroughly and the methodology is solid.

**Worst case:** CANedge2 can't send UDS requests and I don't have access to alternative hardware. In that case, I focus on the passive CAN analysis, the RE methodology, the tools I built, and clearly document WHY the battery data wasn't accessible (gateway filtering, UDS requirement). This is still a valid finding — it shows what you actually need to access BMS data on modern VW EVs.

---

## Risks (Updated for Battery Focus)

| Risk | Impact | What I'll Do |
|------|--------|-------------|
| CANedge2 can't send 29-bit CAN frames | HIGH — blocks UDS approach | Try Strategy B (external diagnostic tool). Check with Markus Gregor if CARISSMA has PCAN or VCDS hardware. |
| Gateway blocks UDS requests from OBD port | HIGH — BMS won't respond | Try direct CAN bus tap (Strategy C). Or try different diagnostic session modes. |
| ISO-TP not supported (no cell voltages) | MEDIUM — limits depth | Focus on single-frame responses (SOC, voltage, current, temp). Cell voltages would be nice but aren't required. |
| Passive CAN IDs not battery-related | LOW — expected | The thesis still documents what IS on this bus segment. UDS track is the main deliverable. |
| Vehicle not available for testing | HIGH — no data | Front-load data collection this week. Ask about regular vehicle access schedule. |

---

## Updated Timeline

| Week | Dates | Focus | Deliverables |
|------|-------|-------|-------------|
| 1 | 03.03 - 08.03 | Setup, MF4 reading, initial RE analysis | Python scripts, 47 plots, documentation |
| 2 | 09.03 - 15.03 | Tool development + organisation | CAN Analyzer (Python + Rust), Excel tracker |
| 3 | 16.03 - 22.03 | **Data collection + UDS strategy testing** | First battery data, strategy validation |
| 4 | 23.03 - 29.03 | Data collection round 2 (battery scenarios) | More recordings, initial UDS decoding |
| 5 | 30.03 - 05.04 | Battery data analysis + literature research | Battery signal map, CAN theory draft |
| 6 | 06.04 - 12.04 | Deep battery signal analysis | Decoded battery parameters, validation |
| 7 | 13.04 - 19.04 | Cross-validation + DBC file construction | Partial DBC, cross-validation results |
| 8 | 20.04 - 26.04 | Write methodology + analysis chapters | ~15 pages draft |
| 9 | 27.04 - 03.05 | Write results + create final figures | ~10 pages draft, publication figures |
| 10 | 04.05 - 10.05 | Validation data collection + results | Validation report, error metrics |
| 11 | 11.05 - 17.05 | Discussion + conclusion writing | ~8 pages draft |
| 12 | 18.05 - 24.05 | Final polish, proofread, submit | Complete thesis |

---

## Thesis Chapter Outline (Updated)

1. **Introduction** (3-4 pages)
   - Motivation: battery data for EV research
   - Problem: no DBC file, proprietary BMS communication
   - Research questions
   - Thesis structure

2. **Theoretical Background** (8-10 pages)
   - CAN bus protocol (ISO 11898)
   - UDS diagnostic services (ISO 14229)
   - ISO-TP transport protocol (ISO 15765)
   - VW MEB platform and BMS architecture
   - Battery fundamentals (what SOC, voltage, current, temperature mean)
   - State of the art in CAN reverse engineering

3. **Hardware & Implementation** (5-7 pages)
   - CANedge2 setup and configuration
   - Connection to VW ID Buzz (OBD-II / direct tap)
   - Data format (MF4/ASAM MDF4)
   - UDS request configuration

4. **Methodology** (8-10 pages)
   - Data collection strategy (why UDS is needed for battery data)
   - 9 reverse engineering techniques (for passive CAN)
   - UDS diagnostic approach (for battery parameters)
   - Controlled test scenarios
   - Validation approach

5. **Analysis & Results** (12-15 pages)
   - Passive CAN analysis (0x065-0x06F, what's on this bus)
   - UDS battery parameter decoding (SOC, voltage, current, temp)
   - Cell voltage analysis (if ISO-TP works)
   - Battery behavior during driving vs charging
   - Partial DBC file

6. **Discussion** (5-7 pages)
   - Limitations (gateway filtering, CAN bus access)
   - What worked vs what didn't
   - Comparison with other approaches
   - Implications for EV battery research
   - Ethical / security considerations

7. **Conclusion & Future Work** (2-3 pages)

8. **Appendix**
   - Code listings, plots, DBC file, raw data samples

**Total: ~45-60 pages**

---

## File Structure

```
Bachelor Thesis VW ID Buzz/
  src/                      - Python scripts
  can_analyzer/             - Rust native GUI (primary analysis tool)
  data/mf4/                 - Raw MF4 log files
  data/csv/                 - Reference CSVs (UDS PIDs list)
  output/plots/             - Generated plots
  output/can_data.csv       - Exported CAN data
  docs/                     - Technical documentation
  Organisation Stuff/       - Planning, tracking, procedures
  apps/                     - asammdf GUI portable
  requirements.txt          - Python dependencies
  CHANGELOG.md              - Session-by-session change log
```
