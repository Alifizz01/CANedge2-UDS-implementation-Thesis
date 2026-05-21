# UDS Working Process — VW ID. Buzz Battery Data Retrieval

**Scope.** This document explains end-to-end how battery data is retrieved from
the Volkswagen ID. Buzz (MEB platform) using the **Unified Diagnostic Services
(UDS)** protocol on the OBD-II connector, and how the retrieved data flows
through the project's analysis pipeline (`uds_decoder.py`,
`VW MEB UDS PIDs list.csv`, `mf4_reader.py`).

Companion document:
[`DOCUMENTATION.md`](DOCUMENTATION.md) — the *passive* CAN bus reverse
engineering (byte/bit analysis, counter detection, etc.). The work in this file
is *active*: we **talk to** the Battery Management Controller instead of just
listening.

---

## 1. Goal

Retrieve physical, engineering-unit battery data directly from the MEB
high-voltage battery ECU — without needing the manufacturer's DBC file — by
sending standardised UDS requests and decoding the positive responses.

Targeted parameters:

- Pack state of charge (SOC) and state of health (SOH)
- Pack terminal voltage, pack current
- Per-cell voltage (cells 1 … N) and cell-index extrema
- HV battery coolant/circulation parameters
- DC-DC converter current and voltage
- Car operation mode (standby / driving / AC charge / DC charge)

All of these are exposed by the MEB battery/HV ECUs via **service `0x22`
ReadDataByIdentifier**.

---

## 2. Why UDS (and not only passive CAN)?

The OBD-II connector of a VW MEB vehicle does **not** expose the private
battery-CAN. It exposes the emission-relevant HS-CAN bus and the **gateway
ECU**. On that gateway-routed bus you can see a small inventory of broadcast
frames (IDs `0x065` … `0x06F` in our recordings — see
[`DOCUMENTATION.md`](DOCUMENTATION.md)), but cell-level voltages, per-module
temperatures and the BMS internal SOC estimate are *not* broadcast there.

UDS solves this the other way round: instead of hoping the ECU volunteers the
information, the tester **requests** it by Data Identifier (DID). The ECU
answers with a single positive-response frame (or a multi-frame ISO-TP
sequence) containing the value in a deterministic byte layout.

---

## 3. Protocol stack recap

```
 ┌────────────────────────────────────────────────────────────┐
 │                     UDS   (ISO 14229-1)                    │   ← services, SIDs, DIDs, NRCs
 ├────────────────────────────────────────────────────────────┤
 │                  ISO-TP   (ISO 15765-2)                    │   ← fragmentation/reassembly
 ├────────────────────────────────────────────────────────────┤
 │                 CAN data link  (ISO 11898)                 │   ← 11-bit or 29-bit IDs
 ├────────────────────────────────────────────────────────────┤
 │                 CAN physical (HS-CAN, 500 kbit/s)          │   ← OBD-II pin 6/14
 └────────────────────────────────────────────────────────────┘
```

For the **MEB platform** the important detail is that Volkswagen uses **29-bit
extended CAN identifiers** for UDS, not the classic 11-bit `0x7E0/7E8`
addresses used on older OBD-II cars. Every ECU has its own 29-bit pair.

---

## 4. Hardware setup

| Item                | Role                                                             |
|---------------------|------------------------------------------------------------------|
| Volkswagen ID. Buzz | Device under test (DUT), ignition in *Ready* mode                |
| CANedge2            | Passive logger recording every frame (both broadcast and UDS)    |
| PC                  | Runs Python tools (`python-can`, `isotp`, `uds_decoder.py`)      |

> **Important.** The PCAN-USB must be set to **ISO-CAN 500 kbit/s** and
> **listen-only = OFF**. The CANedge2 stays **listen-only = ON** so that only
> the PCAN-USB ever transmits.

**Pre-measurement checklist**

1. Vehicle in *Ready* mode (not just unlocked — the brake pedal must be
   pressed and the drive selector must be in P with power button on).
2. PCAN-USB connected *before* the ignition cycle so the gateway does not
   block the adapter.
3. CANedge2 SD card formatted, configuration file with 500 kbit/s, logging
   both raw CAN and tx-direction frames from the PC.
4. Battery SOC ≥ 30 % — some DIDs are masked below that (ECU returns NRC
   `0x22 conditionsNotCorrect`).

---

## 5. Software tool chain

```
data/csv/VW MEB UDS PIDs list.csv          # authoritative PID database (164 entries, v164)
 └─▶ src/uds_decoder.py                    # parses CSV, matches CAN frames, applies formulas
src/mf4_reader.py                          # MDF4 → pandas DataFrame
src/can_analyzer.py                        # raw byte/bit statistics
src/reverse_engineer.py                    # passive RE plots
```

`uds_decoder.py` is the central module for active decoding. It loads the CSV
table of PIDs (request/response IDs, request data, response template,
calculation formula) and provides:

```python
from uds_decoder import load_pid_definitions, decode_frame, decode_all

pids    = load_pid_definitions()            # list of ~160 PID dicts
decoded = decode_all(can_data, pids)        # applies every PID to every matching frame
```

The decoder works **offline** against an MDF4 log. A separate script issues
the requests live.

---

## 6. Addressing scheme used on the ID. Buzz

Every MEB ECU has a 29-bit **request** address `0x17FC00xx` and a 29-bit
**response** address `0x17FE00xx`, where `xx` is the ECU's diagnostic address
(so called *CAN target address*).

| ECU                 | Request (ATSH)  | Response (ATCRA) | Used for                  |
|---------------------|-----------------|------------------|---------------------------|
| HV Battery (BMS)    | `0x17FC007B`    | `0x17FE007B`     | SOC, cell V, cell T, SOH  |
| DC-DC converter     | `0x17FC00B9`    | `0x17FE00B9`     | HV→12 V current, voltage  |
| ... (other ECUs)    | `0x17FC00XX`    | `0x17FE00XX`     | see CSV                   |

The pattern `FC` = *functional/request-client*, `FE` = *response-to-client*
is a VW convention (the `C` and `E` stand for the direction on the 29-bit
address).

> **Padding byte is `0x55`, not `0x00`.** MEB ECUs reject requests padded with
> `0x00`. Always fill unused bytes with `0x55`. Example: a 3-byte payload goes
> out as `03 22 46 5D 55 55 55 55`.

---

## 7. The UDS session workflow

A full interrogation of the battery ECU follows six steps.

### Step 1 — Open the CAN interface

```python
import can
bus = can.interface.Bus(bustype="pcan", channel="PCAN_USBBUS1",
                        bitrate=500_000, fd=False)
```

### Step 2 — Enter an extended diagnostic session (optional)

For *read-only* DIDs the **default session** is enough, but some DIDs are
only available in the **extendedDiagnosticSession (0x03)**:

```
TX  17FC007B   02 10 03 55 55 55 55 55        # DiagnosticSessionControl, 03
RX  17FE007B   06 50 03 00 32 01 F4 55        # + positive response, P2 timing
```

The positive response `50 03 …` confirms the session is open. The four bytes
after `50 03` are the updated P2 and P2* timing parameters.

### Step 3 — Keep the session alive

If an extended session is opened, the tester **must** send a TesterPresent
every ≤ 2 s, otherwise the ECU silently reverts to default session:

```
TX  17FC007B   02 3E 00 55 55 55 55 55        # TesterPresent, sub-function 00
RX  17FE007B   02 7E 00 00 00 00 00 00        # positive response
```

Sub-function `0x80` = *suppressPosRspMsgIndicationBit*: no response expected,
saves bus load. In our code we use `0x00` so every heartbeat is visible in the
CANedge2 log for traceability.

### Step 4 — ReadDataByIdentifier sweep

This is the heart of the battery read-out. For every PID in the CSV whose
`Status == "Ready"`, the tester sends:

```
TX  17FC00XX   03 22 HI LO 55 55 55 55        # SID=22 Read, DID=HI*256+LO
```

and expects:

```
RX  17FE00XX   0L 62 HI LO D1 D2 D3 D4        # SID=62 pos resp, DLC L, data D1…
```

A negative response looks like:

```
RX  17FE00XX   03 7F 22 NRC 00 00 00 00       # NRC telling why it failed
```

Common NRCs encountered on MEB:

| NRC    | Name                       | Practical meaning on MEB                              |
|--------|----------------------------|-------------------------------------------------------|
| `0x11` | serviceNotSupported        | DID belongs to an ECU that isn't powered on           |
| `0x12` | subFunctionNotSupported    | wrong sub-function for 0x10/0x27                      |
| `0x13` | incorrectMessageLength     | padding wrong (you probably sent `00` instead of `55`)|
| `0x22` | conditionsNotCorrect       | battery too cold / charging / wrong mode              |
| `0x31` | requestOutOfRange          | DID simply not implemented on this ECU / SW version   |
| `0x33` | securityAccessDenied       | DID requires seed/key unlock (dealer-level)           |
| `0x7F` | serviceNotSupportedInSession| retry in extendedDiagnosticSession (0x10 03)         |

### Step 5 — Match and decode the response

`uds_decoder.py` matches responses by **(response_id, SID=0x62, DID)** and
then applies the formula from the `Calculation` column of the CSV. The
placeholders `XX`, `YY`, `ZZ`, `WW` in the formula map to successive
*payload* bytes (after the `62 HI LO` header).

### Step 6 — Log and persist

Every successful decode is appended to a pandas DataFrame with columns
`timestamp, request_id, response_id, did, raw_hex, value, unit, name, group`
so it can be plotted, cross-validated and exported to CSV / DBC-style tables.

---

## 8. Worked example — DC-DC converter voltage

This walks through one PID from the CSV line-by-line.

**CSV row (simplified):**

| Field                  | Value                                            |
|------------------------|--------------------------------------------------|
| Group                  | Electrical                                       |
| Popular name           | DC-DC voltage (HV→12V)                           |
| Unit                   | V                                                |
| ATSH (request ID)      | `17FC00B9`                                       |
| data send              | `03 22 46 5D 55 55 55 55`                        |
| ATCRA (response ID)    | `17FE00B9`                                       |
| datareceived           | `05 62 46 5D XX YY aa aa`                        |
| Calculation            | `(XX*2^8 + YY) / 512 = DC-DC volt`               |

**On-bus exchange (captured by the CANedge2):**

```
TX  17FC00B9   03 22 46 5D 55 55 55 55
RX  17FE00B9   05 62 46 5D 1B 80 AA AA
```

**Decode (done by `uds_decoder.py`):**

1. Identify by response ID + SID + DID: `17FE00B9`, `62`, `46 5D` → *DC-DC voltage*.
2. Extract payload bytes `D1…D4` = `1B 80 AA AA` → `XX=0x1B`, `YY=0x80`.
3. Apply formula: `(0x1B * 256 + 0x80) / 512 = (27*256 + 128) / 512 = 7040/512 = 13.75 V`.
4. Emit decoded record `{name: "DC-DC voltage", value: 13.75, unit: "V", …}`.

This matches the ~13.8 V that the DC-DC converter feeds into the vehicle's
12 V auxiliary battery during *Ready* mode, which validates both the CSV
formula and our decoding pipeline.

---

## 9. Worked example — HV battery cell voltage (cell 1)

**CSV row (simplified):**

| Field        | Value                                         |
|--------------|-----------------------------------------------|
| ATSH         | `17FC007B`                                    |
| data send    | `03 22 1E 40 55 55 55 55`                     |
| ATCRA        | `17FE007B`                                    |
| datareceived | `05 62 1E 40 XX YY aa aa`                     |
| Calculation  | `(XX*2^8 + YY) / 1000 + 1 = Voltage [V]`      |

**Exchange:**

```
TX  17FC007B   03 22 1E 40 55 55 55 55
RX  17FE007B   05 62 1E 40 0A A8 AA AA
```

**Decode:**

- `XX = 0x0A`, `YY = 0xA8`
- `(0x0A * 256 + 0xA8) / 1000 + 1 = 2728/1000 + 1 = 3.728 V`

That's a perfectly normal single-cell voltage for an MEB Li-NMC cell that's
been at ~85 % SOC — another independent validation of the pipeline.

To sweep the entire pack, iterate the DID from `0x1E40` (cell 1) through
`0x1EXX` (cell N, where N = 108 for the 82 kWh ID. Buzz pack). The CSV
already contains every row — so the sweep is literally:

```python
cells = [p for p in pids if p["group"] == "Battery"
                         and p["name"].startswith("HV Battery cell voltage")]
for p in cells:
    send_request(p["request_id"], p["request_data"])
    frame = wait_for_response(p["response_id"])
    record = decode_response(frame, p)
    store(record)
```

---

## 10. Handling multi-frame responses (ISO-TP)

Most PIDs fit in a Single Frame (PCI byte `0L` with L ≤ 7). Some responses —
typically the BMS status block, the cell-balancing mask or the error memory —
exceed 7 bytes. In that case the ECU sends:

```
RX  17FE007B   10 0E 62 1F 11 00 00 00        # First Frame: total length 14 (0x0E)
TX  17FC007B   30 00 00 55 55 55 55 55        # Flow Control: Continue, BS=0, ST=0
RX  17FE007B   21 D1 D2 D3 D4 D5 D6 D7        # Consecutive Frame #1
RX  17FE007B   22 D8 D9 DA 00 00 00 00        # Consecutive Frame #2
```

The tester **must** send the Flow Control (PCI `0x30`) within N_BS (≤ 1 s) or
the ECU aborts. Our wrapper around `python-can` + `isotp` handles this
automatically; we only need to set the right `rxid / txid` pair.

---

## 11. Cross-validating UDS data against passive CAN

Once a UDS DID is decoded, it should agree with whatever the vehicle
*broadcasts* on its own. Two straightforward checks:

| Active (UDS)            | Passive match on HS-CAN                          |
|-------------------------|--------------------------------------------------|
| DC-DC voltage (~13.8 V) | Dashboard 12 V battery voltage, if it's on-bus   |
| Car operation mode      | Correlate with 0x065 NM_STATE transitions        |
| Pack voltage            | Slow-changing signal in `0x068 B[0]` candidates  |
| Cell temperature min/max| Offset-40 temp in `0x066 B[3]`, `0x067 B[5]`     |

The correlation analysis is performed in `can_decoder.py`'s cross-signal
function and is one of the headline figures of the thesis (Chapter 4, Cross-
Signal Correlation).

---

## 12. Full end-to-end runbook

```bash
# 1. Park the ID. Buzz, ignition in Ready mode.
# 2. Plug the Y-cable, CANedge2 (listen-only) and PCAN-USB.
# 3. Start CANedge2 logging.
# 4. Run:
python -m src.uds_tester \
    --interface pcan \
    --channel   PCAN_USBBUS1 \
    --pids-csv  "data/csv/VW MEB UDS PIDs list.csv" \
    --ecus      battery,dcdc \
    --out       output/uds_session_YYYYMMDD.csv \
    --plot
```

The script will:

1. Open the PCAN bus at 500 kbit/s.
2. For every selected ECU:
   - send DiagnosticSessionControl `0x10 03`,
   - start a 2 s TesterPresent timer,
   - iterate every `Status == "Ready"` PID in its group,
   - collect positive responses and skip / record NRCs,
3. Save a timestamped CSV with decoded values.
4. Offline-decode the CANedge2 MDF4 via `uds_decoder.decode_all()` and
   cross-check both data sources for consistency.

---

## 13. Common pitfalls seen during development

| Symptom                              | Root cause                                    | Fix                                                           |
|--------------------------------------|-----------------------------------------------|---------------------------------------------------------------|
| NRC `0x13` (incorrectMessageLength)  | Request padded with `0x00`                    | Pad with `0x55` as VW specifies                               |
| NRC `0x11` / no response             | ECU not awake (vehicle only in *Accessory*)   | Put car in *Ready* mode                                       |
| NRC `0x31` on every battery DID      | Wrong request ID                              | Re-check ATSH: it's `17FC007B`, not `17FC00B9`                |
| Random missing frames                | PCAN and CANedge2 both transmitting           | Set CANedge2 to listen-only                                   |
| Session drops after 2 s              | Forgot TesterPresent                          | Start the 2-s heartbeat before the sweep                      |
| Partial multi-frame response         | Flow Control missing                          | Use `isotp` lib or send `30 00 00 …` within 1 s of First Frame|

---

## 14. Output formats produced by the pipeline

| File                                        | Content                                                |
|---------------------------------------------|--------------------------------------------------------|
| `output/uds_session_*.csv`                  | One row per (DID, timestamp) with decoded value + unit |
| `output/decoded_plots/<did>.png`            | Time series for each battery DID                       |
| `output/partial_meb.dbc` *(future work)*    | DBC file aggregating passive + active signals          |
| `output/cross_correlation.png`              | Passive vs active comparison plot                      |

---

## 15. Relationship to the thesis

This working process directly populates two chapters of the thesis
(`thesis/thesis.tex`):

- **Chapter 3, Section 3.5** — *UDS Diagnostic Procedure for Battery Data*
  describes this runbook in academic prose.
- **Chapter 4, Section 4.4** — *Active Battery Data Retrieval via UDS*
  reports the decoded values (pack V, pack I, cell V min/max, cell T,
  SOC, SOH) and compares them with the dashboard readings for validation.

The `docs/` folder therefore splits cleanly in two:

- [`DOCUMENTATION.md`](DOCUMENTATION.md) — passive, broadcast CAN RE
- **`UDS_WORKING_PROCESS.md`** (this file) — active, UDS-driven retrieval

Together they capture the full methodology that the thesis then synthesises.

---

## 16. Key references

- ISO 14229-1:2020 — UDS application layer
- ISO 15765-2:2016 — ISO-TP transport layer
- ISO 11898-1:2015 — CAN physical / data link layer
- SAE J1962 — OBD-II diagnostic connector
- Internal: `data/csv/VW MEB UDS PIDs list.csv` (v164)
- Internal: `src/uds_decoder.py`, `src/mf4_reader.py`
