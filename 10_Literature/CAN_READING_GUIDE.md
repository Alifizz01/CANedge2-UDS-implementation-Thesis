# How to Read CAN IDs and Signals

A practical reading guide for the captures in this project. Uses real frames from session `00000013` of the ID Buzz dataset as worked examples.

---

## 1. The CAN frame

Every CAN message is a small packet with this structure:

```
┌─────────┬─────┬─────────────────────────┐
│  ID     │ DLC │   Data (0–8 bytes)      │
└─────────┴─────┴─────────────────────────┘
   who         how-many       the payload
```

- **ID** — *who is talking*. A number that identifies the message type (and indirectly the sender). Lower numbers have higher priority on the wire.
- **DLC** (Data Length Code) — number of payload bytes (0–8 for classic CAN).
- **Data** — the actual bytes. A signal (temperature, voltage, …) is encoded somewhere inside these bytes.

There's also a CRC and a few ACK bits but the logger handles those for you. As an analyst you only ever see ID + DLC + data.

---

## 2. Standard vs Extended IDs (11-bit vs 29-bit)

Two flavours of ID exist on the same bus:

| Type | Width | Range | Hex format | Used for |
|---|---|---|---|---|
| **Standard** | 11-bit | 0…0x7FF | `0x065`, `0x6F` | Periodic broadcast traffic (sensors, status) |
| **Extended** | 29-bit | 0…0x1FFF FFFF | `0x17FE007B` | UDS diagnostic traffic, J1939, tester→ECU |

The capture files mark this with an **`IDE` flag** (0 = standard, 1 = extended). In our project's `output/can_data.csv`, the `ide` column tells you which it is. Extended IDs are written as 8-digit hex (`0x17FC007B`), standard as 3-digit (`0x065`).

> **Why this matters for us:** the legacy `mf4_reader.py` only read the first channel group, which is standard-ID frames. All UDS traffic (extended) was hidden. The fixed reader iterates every group and shows both kinds in one table.

---

## 3. From bytes to a signal

A "signal" is a meaningful quantity (km/h, °C, V, %) encoded as one or more bits inside the data field. To read it you need four pieces of info:

1. **Start byte / start bit** — where does it begin
2. **Length** — how many bits wide
3. **Byte order** — Big-endian (Motorola, MSB first) or Little-endian (Intel, LSB first). VW Group uses **big-endian** by default.
4. **Scaling** — formula `physical = raw × factor + offset`

If you have a DBC file these come from the database. We don't, so we either reverse-engineer them (broadcast track) or look them up in the PID list (UDS track).

### A worked example (single byte)

Frame: `0x028C` SOC response

```
ID  = 0x17FE007B    (29-bit, BMS response)
DLC = 8
Data = 04 62 02 8C A9 AA AA AA
```

Layer by layer:

```
04            <- ISO-TP length: "the next 4 bytes are real data"
   62         <- UDS positive response to service 0x22 (ReadDataByIdentifier)
      02 8C   <- the PID being answered (0x028C = SOC)
            A9   <- THE VALUE BYTE (one byte of payload)
              AA AA AA  <- VW padding (0xAA, ignore)
```

The CSV says SOC formula is `XX / 2.5`. Apply it:

```
0xA9 = 169
169 / 2.5 = 67.6 %  ← State of Charge
```

That's it. One byte, one division, one human-readable answer.

### A worked example (two bytes, big-endian)

Frame: `0x1E3B` HV pack voltage response

```
Data = 05 62 1E 3B 05 C1 AA AA
       │  │  │  │  │  │
       │  │  │  │  XX YY        <- two value bytes
       │  │  └──┴── PID 0x1E3B
       │  └── 0x62 positive RDBI response
       └── ISO-TP length 5
```

CSV formula: `(XX × 2^8 + YY) / 4 = Voltage`

```
XX = 0x05 = 5
YY = 0xC1 = 193
(5 × 256 + 193) / 4 = (1280 + 193) / 4 = 1473 / 4 = 368.25 V
```

Perfect: a fully charged MEB pack is ~410 V, a flat one ~330 V, so 368 V at ~67 % SOC is exactly what you'd expect.

> **Endianness check:** if you swapped XX and YY (little-endian), you'd get `(193 × 256 + 5) / 4 = 12354.25 V` — clearly wrong. That's how you know the byte order at a glance: only one ordering produces a physically sensible value.

### A worked example (enum / state)

Frame: `0x7448` car operation mode

```
Data = 04 62 74 48 01 AA AA AA
                    XX
```

CSV: `XX = 0 ⇒ standby, XX = 1 ⇒ driving, XX = 4 ⇒ AC charging, XX = 6 ⇒ DC charging`

```
XX = 0x01 → "driving"
```

No arithmetic — just a lookup. State variables (mode, gear, error flags) are usually like this.

---

## 4. Reading raw broadcast frames (no DBC, no UDS)

The other half of this project is the periodic broadcast traffic on standard IDs `0x065`–`0x06F`. These have no PID list, so we reverse-engineer the layout. The technique is documented in detail in `docs/DOCUMENTATION.md`. Quick version:

1. Plot every byte over time. Smooth curves = analog signal. Flat = constant or padding. Sawtooth = counter.
2. Combine adjacent bytes as 16-bit big-endian and 16-bit little-endian and plot — only one ordering will look like a real signal.
3. Try standard automotive scaling factors (`raw - 40 = °C`, `raw / 2.5 = %`, `raw × 0.01 = V`) and see which produces a plausible value.
4. If a byte is constant ASCII (e.g. `0x54 = 'T'`), it's a message-type marker, not a signal.

---

## 5. UDS — request/response on extended IDs

CAN broadcast is "shouting in the room": every ECU just talks. UDS (ISO 14229) is "asking a question": the tester sends a request to one specific ECU, the ECU replies. The pattern on our CAN1 bus:

```
Tester (CANedge) ──── 0x17FC007B ────►  BMS         "Read PID 0x028C"
Tester (CANedge) ◄─── 0x17FE007B ────   BMS         "Here's 0xA9"
```

The two IDs are paired: `0x17FC007B` is the request channel, `0x17FE007B` is the response. The trailing `7B` is the BMS ECU address. Every VW MEB ECU has its own pair of addresses.

### The request

ReadDataByIdentifier (RDBI) request format:

```
03 22 02 8C 55 55 55 55
│  │  │  │  └── VW padding (0x55 fills unused bytes)
│  │  └──┴── PID being requested (0x028C)
│  └── 0x22 = service "ReadDataByIdentifier"
└── ISO-TP length: "3 real bytes follow"
```

That's all a request is: tell the ECU which PID you want.

### The response

Three possible shapes:

| First byte | Meaning |
|---|---|
| `0x0X` | **Single Frame** (≤7 useful bytes) — `0x` is a literal `0`, `X` is the length |
| `0x1X XX` | **First Frame** of a multi-frame response — `XXX` is the total length in bytes (12-bit) |
| `0x2X` | **Consecutive Frame** — `X` is a sequence counter |

Examples from session 13:

```
04 62 02 8C A9 AA AA AA       Single Frame, 4 bytes payload (62 02 8C A9)
05 62 1E 3B 05 C1 AA AA       Single Frame, 5 bytes payload
10 08 62 1E 3D 00 02 49       First Frame: total 8 bytes, only first 6 carried
03 7F 22 11                    Negative Response (more on this below)
```

A **negative response** starts with `7F` and tells you the request failed:

```
03 7F 22 31     "Service 0x22 rejected: NRC 0x31 = requestOutOfRange"
```

NRCs (Negative Response Codes) you'll see most:
- `0x11` serviceNotSupported — ECU doesn't know that service
- `0x12` subFunctionNotSupported — ECU knows the service but not that variant
- `0x13` incorrectMessageLengthOrInvalidFormat — bad framing
- `0x22` conditionsNotCorrect — ECU is in the wrong state (e.g. not in extended session)
- `0x31` requestOutOfRange — that PID doesn't exist on this ECU
- `0x33` securityAccessDenied — ECU requires unlock

### ISO-TP and the multi-frame trap

ISO-TP (ISO 15765-2) is the protocol that lets UDS responses longer than 7 bytes span multiple CAN frames. The catch: **after a First Frame, the receiver must send a Flow Control frame** (`0x30 ...`) telling the sender to continue. The CANedge cannot send Flow Control. So for any PID whose response is >7 bytes, we get **only the First Frame** — three value bytes — and the BMS times out waiting for FC.

That's why our HV current readings are flagged `value_kind: partial` in `output/uds_decoded/all_sessions.csv`. To capture the full multi-frame response you need a real ISO-TP transmitter (a Pi running `python-can` with the `isotp` module, for example).

---

## 6. The end-to-end flow used in this project

```
   CAR (BMS ECU)
       │
       │  CAN1, extended IDs 0x17FC007B / 0x17FE007B
       ▼
   CANedge2 logger
       │  records both Rx and self-Tx (log:1)
       │  saves as MF4 files on SD card
       ▼
   data/.../00000001.MF4
       │
       │  src/mf4_reader.py iterates every channel group
       │  → DataFrame with can_id, ide, dlc, data_bytes, data_hex
       ▼
   src/uds_battery_decoder.py
       │  parses VW MEB UDS PIDs CSV → PID database
       │  decodes ISO-TP framing per response
       │  applies the formula from the CSV
       ▼
   output/uds_decoded/
     ├─ all_sessions.csv  (timestamp, pid, name, value, unit)
     ├─ summary.txt        (min/max/last per PID)
     └─ plots/pid_*.png    (one time-series plot per signal)
```

---

## 7. Putting it into practice with the sweep configs

`CANedge/config-01.08-full-sweep.json` requests 57 hand-picked PIDs at three rates (1 s / 5 s / 20 s). For complete coverage of all 161 PIDs, three configs together — `sweep-S1.json`, `sweep-S2.json`, `sweep-S3.json` — cover everything; flash one at a time, drive a session, swap, repeat. Each config also has the same Tier 1 fast loop (SOC, V, I, op mode, main temp) so you always get the basics.

After capturing, run:

```
python -X utf8 src/uds_battery_decoder.py
```

The decoder identifies every response, looks up the PID in the CSV, applies the formula, and writes the merged CSV + plots. PIDs that returned a negative response (`7F`) appear with `kind=NEG` and tell you why the ECU refused — useful for narrowing down which PIDs from the list are actually supported on the ID Buzz.

---

## 8. Quick reference: IDs on this vehicle

| ID | Kind | Source | What it carries |
|---|---|---|---|
| `0x065` | std | broadcast | NM heartbeat (1 byte enum) |
| `0x066` | std | broadcast | Mode flag + 16-bit counter + temperature + ASCII markers |
| `0x067` | std | broadcast | Multi-signal: SIG_A, temperatures, multiplexer state |
| `0x068` | std | broadcast | 4-byte measurement + status flag |
| `0x06A` | std | broadcast | Event-triggered (sporadic, 126 frames total) |
| `0x06B` | std | broadcast | Multi-signal with 3-bit state in B[2] |
| `0x06F` | std | broadcast | 8 independent signals — initially looked encrypted, isn't |
| `0x17FC007B` | ext | tester→BMS | UDS request (we send these) |
| `0x17FE007B` | ext | BMS→tester | UDS response (we decode these) |
| `0x7DF` | std | tester | OBD-II broadcast request |
| `0x7E0`/`0x7E7` | std | tester | OBD-II ECU-specific TesterPresent |
| `0x7E8`/`0x7EF` | std | ECU→tester | OBD-II response (not seen yet — gateway likely blocks) |

For the broadcast frames, see `docs/DOCUMENTATION.md` for per-byte signal hypotheses and the evidence behind each one.
