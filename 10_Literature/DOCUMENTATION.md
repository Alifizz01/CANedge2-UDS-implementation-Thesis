# VW ID Buzz CAN Bus — Complete Documentation

## Table of Contents

1. [The Big Picture](#1-the-big-picture)
2. [Working Process — End to End](#2-working-process--end-to-end)
3. [How We Get Data Out of the Car](#3-how-we-get-data-out-of-the-car)
4. [Data Format and Structure](#4-data-format-and-structure)
5. [UDS Battery Track — How We Actively Ask the Car for Data](#5-uds-battery-track--how-we-actively-ask-the-car-for-data)
6. [Setting Up the CANedge Config (Step by Step)](#6-setting-up-the-canedge-config-step-by-step)
7. [Decoding the UDS Captures](#7-decoding-the-uds-captures)
8. [Key Findings Summary](#8-key-findings-summary)
9. [Using asammdf GUI for MF4 Analysis](#9-using-asammdf-gui-for-mf4-analysis)
10. [Running the Analysis Scripts](#10-running-the-analysis-scripts)
11. [File Reference](#11-file-reference)

---

## 1. The Big Picture

This thesis decodes the CAN bus of a **Volkswagen ID Buzz** (MEB platform EV) to extract battery data. We use a **CANedge2** data logger plugged into the car. The logger writes everything it sees on the CAN bus into MF4 files (a binary log format), and we decode those files back into something a human can read.

The approach is **active diagnostic querying via UDS**. Battery data — state of charge, pack voltage, individual cell voltages, temperatures — lives behind a diagnostic protocol called **UDS** (Unified Diagnostic Services). You have to politely ask the BMS (Battery Management System) for it, and it answers.

- The CANedge is configured to **transmit UDS request frames** on a schedule on CAN1, and the BMS replies.
- Both the questions and the answers get logged into the same MF4 file.
- We decode those answers offline using a community-sourced PID list for the VW MEB platform.

**What was captured:** multiple sessions on the SD card dump from 2025-04-09 (sessions 12, 13, 17, 18, 22, 23 contain working diagnostic captures), decoded into `output/uds_decoded/all_sessions.csv` plus per-PID plots.

---

## 2. Working Process — End to End

This is the actual day-to-day workflow. Three phases: **prepare at the desk**, **capture in the car**, **decode back at the desk**. The detail for each step lives in the sections referenced — this is the runbook that ties them together.

### Phase 1 — Pre-extraction (at the laptop)

**Goal:** produce a `config-01.08.json` that tells the CANedge exactly which PIDs to ask for, and put it on the SD card.

1. **Confirm the PID list.** The source of truth is `data/csv/VW MEB UDS PIDs list.csv` — the full ~198-entry list of UDS PIDs documented for the VW MEB platform. **For this thesis we want all of them.** No curation, no "priority subset" — every PID the community has documented gets a transmit entry, so we capture the full picture of the BMS in one go. The CSV is therefore your input as-is; you only edit it if you find a typo in a formula or want to remove a PID that produces only negative responses.

2. **Generate the transmit list.** From the repo root:
   ```powershell
   python -X utf8 src/build_canedge_transmit_config.py
   ```
   This writes `CANedge/config-01.08-built.json`. **Heads-up:** today the script emits a curated **32 entries** (TesterPresent + DiagSessionControl + 13 priority PIDs + 16 sampled cells + 6 temperature points), not the full ~198. To capture **everything** — which is the goal — you have two options:

   - **Option A (recommended):** edit `src/build_canedge_transmit_config.py` so it emits one transmit entry per row of the CSV, then re-run it. This keeps the JSON in sync with the CSV automatically next time.
   - **Option B (quick & dirty):** open `config-01.08-built.json` in the web editor and add the missing PIDs by hand under **CAN-1 → Transmit**. Tedious, but doesn't require touching the script.

   See [Section 6.7](#67-regenerating-the-transmit-list-from-the-pid-csv) for what the script outputs today.

   > **Bus-time arithmetic.** With ~198 PIDs and 150 ms stagger between entries, one full request cycle takes about 30 seconds. The default `period` of 10 000 ms (10 s) won't fit that — entries scheduled later in the cycle would collide with the next round. Either raise `period` to **≥ 35 000 ms** (every PID gets one comfortable round per cycle) or reduce the stagger to **~50 ms** if you want a tighter sample rate. Pick one, don't mix. For the curated 32-entry list the defaults are fine; for the full list, double-check `period` and `delay` spacing in the editor before saving.

3. **Open the official web editor** at https://canlogger.csselectronics.com → Config Editor. Load:
   - **schema** → `CANedge/schema-01.08.json` (the rulebook — see [Section 6.1](#61-where-the-config-lives))
   - **config** → `CANedge/config-01.08-built.json` (or `config-01.08.json` if you're starting from the canonical one)

4. **Sanity-check the form** before saving. Go to **CAN-1 → Transmit** and confirm:
   - Every entry has `id_format = 1` (29-bit extended).
   - `phy.mode = 0` (Normal). If this is `1` (Restricted) you cannot transmit.
   - Delays are staggered (0, 150, 300, …) so the BMS doesn't get hit with simultaneous requests.
   - `period` is reasonable — 10 000 ms (10 s) is the canonical value; lower means more samples but more bus load.
   - `log = 1` on every entry so your outgoing requests appear in the MF4 file.
   - Padding bytes in `data` are `0x55`.

5. **Save the config** from the editor — it downloads as `config-01.08.json`. Field-by-field reference is in [Section 6.4](#64-anatomy-of-one-transmit-entry-field-by-field).

6. **Copy the file to the SD card** root, overwriting the existing `config-01.08.json`. Eject cleanly. Put the SD card back in the CANedge.

### Phase 2 — Extraction (in the car)

**Goal:** capture an MF4 log of UDS responses while the BMS is awake.

1. **Plug the CANedge into the OBD-II port** (or the CAN tap, if you're using a custom harness on a different bus). The device powers up from the port.

2. **Get the car into READY mode.** Key in, foot on brake, press the start button — wait until the dashboard shows the full driving display (not just accessory mode). UDS only works when the BMS ECU is actually awake and ACKing.

3. **Watch the yellow LED on the CANedge.** The CANedge2 has a single yellow status LED (no green, no red). What it does tells you the device's state:
   - **Continuous (solid) yellow** → device booted, config parsed cleanly, CAN bus up, logging to SD. This is the "all good" state.
   - **Blinking yellow** → activity. Each blink corresponds to bus events / log writes. Brief blinks during a transmit cycle are normal.
   - **LED off, or stuck in a fast/irregular blink** → something is wrong. Most common causes: malformed JSON config (the editor catches most of these when you re-save), SD card not inserted or full, or the device hasn't initialized yet (give it 5–10 s after plugging in).

4. **Let the session run.** The minimum useful capture is ~1–2 minutes (you'll have ~6–12 samples per PID at the 10 s period). Drive around, idle, run the AC, plug it into a charger — anything that moves SOC, current, or temperatures so you have non-flat data to plot.

5. **End cleanly.** Park, key off. Wait ~10 s for the CANedge to flush its write buffer to the SD card before unplugging. The yellow LED goes off when the device has powered down and it's safe to disconnect.

6. **Pull the SD card.** Each ignition cycle creates a new folder `LOG/<device-id>/<NNNN>/` with `00000001.MF4` (and possibly `00000002.MF4` etc. if the file split size was exceeded).

> **If the yellow LED never settles into continuous-on, or the log file is suspiciously small,** check that the car actually reached READY mode. The classic failure is "accessory mode looks like READY mode but no ECU is ACKing" — you'll capture a session full of error frames and zero responses (recall the cautionary tale of session 19: 1.65 M error frames from no-ACK retransmission).

### Phase 3 — Post-processing (back at the laptop)

**Goal:** turn the binary MF4 into decoded values, then sanity-check that the framework actually worked.

1. **Copy the new session folders** off the SD card into the repo:
   ```
   data/sd_dumps_<device-id>_<YYYYMMDD>/LOG/<device-id>/<NNNN>/
   ```

2. **Run the decoder.** Two modes:

   **Mode A — decode every session** found under `data/mf4/` and `data/sd_dumps_*/LOG/*/`:
   ```powershell
   python -X utf8 src/uds_battery_decoder.py
   ```

   **Mode B — decode a single session only.** Pass the session folder name (the 8-digit number, e.g. `00000013`) via `--session`:
   ```powershell
   python -X utf8 src/uds_battery_decoder.py --session 00000013
   ```
   The decoder then ignores every other folder and only processes that one. Useful when you just took a fresh capture and want to see its results in isolation, without overwriting earlier output with a full re-run. The flag matches the folder name exactly — replace `00000013` with whatever number your new session got.

   What this script actually does step-by-step is documented in [Section 7](#7-decoding-the-uds-captures).

3. **Read the summary files first.** Two flavours land in `output/uds_decoded/`:
   - `summary.txt` — the **merged** view across every session in this run.
   - `<session>__summary.txt` — **one file per session** (e.g. `sd_2A73E1CC__00000013__summary.txt`).

   The per-session files exist because sessions captured on different days or in different drives don't average meaningfully — the merged summary washes that distinction out. Always check the per-session file for the capture you just took. Each summary lists every PID that produced at least one decoded sample, with counts, min/max/last value, and unit. If a PID you expected is missing or shows zero samples, the BMS didn't answer it for that session (wrong PID, ECU not awake, or session too short).

   When you run with `--session <NNNN>`, the merged `summary.txt` and the matching `<session>__summary.txt` will both contain just that one session's data — they'll be identical apart from the header line.

4. **Open `output/uds_decoded/all_sessions.csv`** for the full sample table. Columns: `timestamp, session, pid_hex, name, value, unit`. Use pandas / Excel / your tool of choice.

5. **Spot-check the per-PID plots** in `output/uds_decoded/plots/pid_*.png`. The "does this look right?" checklist:
   - **State of Charge** sits between 0–100% and moves slowly (a few % per drive).
   - **Pack voltage** is in the **350–410 V** range for the MEB 77 kWh pack.
   - **Pack current** is positive while charging, negative while discharging, zero at standstill.
   - **Cell voltages** are between **3.0 V (empty)** and **4.2 V (full)**. Cells should track each other within ~30 mV in a healthy pack.
   - **Module temperatures** are physically plausible (e.g. 5–40 °C depending on weather and load).
   - **Operating mode** transitions match what you did in the car (standby → driving → AC charging, etc.).

6. **Cross-check with the asammdf GUI** when something looks wrong. Open the MF4 directly (see [Section 9](#9-using-asammdf-gui-for-mf4-analysis)) and inspect the raw bytes of the suspect response — sometimes the value is correct and the formula is wrong, sometimes the BMS gave a negative response (`0x7F`) that the decoder logged separately.

### How we know the framework works

You're done validating when:

- `summary.txt` shows **>0 decoded samples for every active PID** in the transmit list.
- The number of responses per PID is roughly `session_duration / period`. Example: a 10-minute session at 10 s period should yield ~60 samples per PID.
- The decoded values **fall in the physically expected ranges** listed above. Out-of-range values usually mean a bad CSV formula, not a bad capture.
- **Outgoing requests appear in the MF4** under channel group `CAN1_Tx_IDE` (this is what `log: 1` enables). If they're missing, the device wasn't actually transmitting.
- **No PID is exclusively "partial / first-frame-only"** for signals that should fit in a single frame — that would mean ISO-TP framing was misinterpreted.

When all five hold, you have a working capture and the decoding pipeline is doing what it should.

---

## 3. How We Get Data Out of the Car

### Hardware
- **Vehicle:** Volkswagen ID Buzz (MEB platform)
- **Logger:** **CANedge2** by CSS Electronics — a small black box with two CAN channels and an SD card. It plugs into the OBD-II connector (or a tap on the right CAN bus) and just records.
- **Connection:** **CAN1** → vehicle CAN bus where the BMS lives.
- **Output format:** MF4 (ASAM MDF v4.11) — a binary log file. Each session is stored in its own folder on the SD card as `LOG/<device-id>/<session>/00000001.MF4`.

### What "logging" actually means here
The CANedge has two superpowers used in this project:

1. **Receive everything on the bus** and write it to the MF4 file.
2. **Transmit custom CAN frames** at scheduled intervals. We use this on CAN1 to send UDS requests to the BMS. The transmitted frames *also* end up in the log file (under a separate channel group called `CAN1_Tx_IDE`), so you can see both your question and the car's answer side by side.

The "asking" behaviour is configured through a JSON file (`config-01.08.json`) that lives on the SD card. See [Section 6](#6-setting-up-the-canedge-config-step-by-step) for how to edit and flash it.

### Storage Structure
```
log/
  00000002/
    00000001.MF4    # First recording session
  00000003/
    00000001.MF4    # Second recording session
  00000004/
    00000001.MF4    # Third recording session (longest)
  00000005/
    00000001.MF4    # Fourth recording session
```

Each MF4 file contains CAN frame groups:
- `CAN_DataFrame` - Standard CAN data frames (this is what we analyze)
- `CAN_RemoteFrame` - Remote request frames
- `CAN_ErrorFrame` - Error frames
- `LIN_Frame` - LIN bus frames (not present in our data)

---

## 4. Data Format and Structure

### Raw Data Columns (after cleanup by `mf4_reader.py`)

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | float (index) | Time in seconds from recording start |
| `can_id` | int | CAN arbitration ID (11-bit standard) |
| `can_id_hex` | string | Hex representation (e.g., "0x065") |
| `dlc` | int | Data Length Code (number of payload bytes, 1-8) |
| `data_bytes` | array | Raw payload bytes |
| `data_hex` | string | Hex representation of payload (e.g., "0A 1B 2C") |
| `bus_channel` | int | CAN bus channel number (1 for the BMS bus) |
| `direction` | int | Message direction (0 = received from the bus, 1 = transmitted by the CANedge) |
| `source` | string | Log folder name (e.g., `00000013`) |

> **Note on CAN IDs:** UDS traffic uses **29-bit extended IDs**. Requests we send go out as `0x17FC007B`; replies from the BMS come back as `0x17FE007B`. `mf4_reader.py` keeps both 11-bit and 29-bit IDs in the same `can_id` column with an `ide` column distinguishing them.

---

## 5. UDS Battery Track — How We Actively Ask the Car for Data

### 5.1 What UDS is, in plain English

**UDS** stands for **Unified Diagnostic Services** (ISO 14229). It is the standard "question-and-answer" protocol that workshops, OBD scanners, and dealership tools use to talk to a car's electronics.

The mental model is dead simple:

```
Tester (us, via CANedge):  "Hey BMS, what's the State of Charge?"
BMS (the car):             "It's 73%."
```

Every question is a single CAN frame. Every answer is one or more CAN frames. The protocol defines exactly what bytes go where so any standards-compliant ECU will understand the question.

### 5.2 The pieces of a UDS request

A UDS "Read Data By Identifier" request looks like this on the wire:

```
CAN ID:   0x17FC007B          <- "I am talking to the BMS"
Data:     03 22 1E 3B 55 55 55 55
          ^  ^  ^^^^^ ^^^^^^^^^^^
          |  |  |     padding (we use 0x55)
          |  |  PID: 0x1E3B  (= "Pack Voltage")
          |  Service ID: 0x22  (= "ReadDataByIdentifier")
          ISO-TP byte: 0x03 means "Single Frame, 3 bytes of payload follow"
```

Three things to notice:

1. **The CAN ID is a 29-bit "extended" ID, not the usual 11-bit one.** That's why the broadcast track only saw `0x065`–`0x06F` and missed all UDS traffic. UDS to the BMS uses **`0x17FC007B` for requests** and **`0x17FE007B` for responses**. (The `7B` at the end is the BMS address.)

2. **0x22 is the "service".** UDS has dozens of services (read data, write data, security access, reset ECU, …). For reading sensor values we only ever use service `0x22 = ReadDataByIdentifier`.

3. **The PID (Parameter ID) is what you actually want.** It's a 16-bit number. `0x028C` = State of Charge. `0x1E3B` = Pack Voltage. `0x1E3D` = Pack Current. The full list comes from the community-sourced CSV at `data/csv/VW MEB UDS PIDs list.csv` (~198 PIDs documented for the VW MEB platform).

### 5.3 The response, and why it sometimes spans multiple frames

A short answer fits in one CAN frame and looks like:

```
CAN ID:   0x17FE007B
Data:     05 62 02 8C 49 00 AA AA
          ^  ^  ^^^^^ ^^^^^
          |  |  |     value bytes (here SOC = 0x49 = 73%)
          |  |  echoed PID (0x028C = SOC)
          |  Positive response code: 0x62 = 0x22 + 0x40
          ISO-TP byte: "Single Frame, 5 bytes follow"
```

A longer answer (e.g. all cell voltages in one PID) doesn't fit in 8 bytes, so UDS uses a transport layer called **ISO-TP** (ISO 15765-2) that splits the answer across several CAN frames:

- The first frame ("First Frame") has type code `1x` and carries the total length plus the first 6 data bytes.
- Subsequent "Consecutive Frames" carry the rest, 7 bytes at a time.
- The tester is supposed to send a "Flow Control" frame back to give the ECU permission to keep going.

**Important limitation:** the CANedge2 cannot send Flow Control frames automatically. So for multi-frame answers we only ever capture the **First Frame** — which gives us the first 3 useful value bytes. For 1- to 3-byte signals (SOC, temperatures, single-cell voltages) this is fine. For 4-byte signals (e.g. high-resolution pack current) it's an approximation. This is a known trade-off and is annotated in the decoder.

### 5.4 What "decoding" means

Each PID in the CSV comes with:
- A **datatype description** like `WW XX YY` — placeholders saying "the answer's value bytes will be three bytes which we'll call WW, XX, YY".
- A **formula** like `(WW*256 + XX) * 0.5 - 40` — how to combine those bytes into a physical value (here, a temperature in °C).
- A **unit** like `°C` or `V` or `%`.

So the decoder simply:

1. Reads each `0x17FE007B` response from the MF4 file.
2. Looks up the PID in the CSV.
3. Plugs the value bytes into the formula.
4. Writes the result with a timestamp into a CSV.

Result: `output/uds_decoded/all_sessions.csv` with rows like
`timestamp, session, pid_hex, name, value, unit`. From there we make per-PID time-series plots.

### 5.5 Pitfalls we hit (so you don't have to re-discover them)

- **Vehicle must be in READY mode.** If the car is off, no ECU will ACK our requests and the bus produces only error frames. Session 19 of the SD dump captured **1.65 million error frames** because the car wasn't powered on — useful only as a cautionary tale.
- **Wrong PHY mode breaks transmission.** The CANedge config field `phy.mode` must be `0` (Normal). `1` (Restricted) lets you listen but blocks transmissions, so no UDS requests go out and no responses come back.
- **`mf4_reader.py` must iterate every channel group.** `asammdf.to_dataframe()` silently drops the extended-ID groups (`CAN1_Rx_IDE`, `CAN1_Tx_IDE`) — which is exactly where UDS traffic lives. The fix: loop through groups manually and concatenate. This is already done in our reader; just don't "simplify" it.
- **A few formulas in the community CSV have bugs.** Example: `WW*2^32` where it should be `2^24`. The decoder tolerates these (skips on eval failure) but be sceptical when a value looks orders of magnitude off.

---

## 6. Setting Up the CANedge Config (Step by Step)

This is the part that decides **which questions the CANedge will ask the car**. Get this wrong and you log nothing useful.

### 6.1 Where the config lives

The config is a single JSON file on the SD card of the CANedge2:

```
<SD card root>/config-01.08.json
```

The repo has several copies under `CANedge/`:

| File | Purpose |
|------|---------|
| `config-01.08.json` | **Canonical config** — 64 PIDs covering full battery capture. This is the one to flash for normal use. |
| `config-01.08-built.json` | Auto-generated by `src/build_canedge_transmit_config.py` from the PID CSV. Use as a starting point if you change which PIDs you want. |
| `config-01.08-test5.json` | Minimal 5-PID smoke test. Use to verify the BMS is responding before flashing the full list. |
| `config-01.08-testerpresent-only.json` | Archived experiment — only sends TesterPresent. Kept for reference. |
| `schema-01.08.json`, `uischema-01.08.json` | Schema files used by the official editor (next section). |

#### Config vs. schema — what's the difference?

These two files always show up together and people mix them up. They serve completely different roles:

| File | What it is | Who reads it | Goes on the SD card? |
|------|------------|--------------|----------------------|
| **`config-01.08.json`** | The **actual settings for your device** — which PIDs to send, how often, log split size, WiFi credentials, etc. Concrete values for one specific CANedge. | The CANedge firmware, every time it boots. | **Yes.** This is what gets flashed. |
| **`schema-01.08.json`** | The **rulebook** describing what a config is allowed to look like — every valid field, its type (`integer`, `string`, `boolean`), allowed value ranges, which fields are required, which are optional. A standard JSON Schema document. It contains *zero* device settings. | The web editor, to render the form UI and validate what you type. | **No.** Stays on your laptop. |
| **`uischema-01.08.json`** | A companion file that tells the editor **how to lay out** the form (grouping, tab order, field labels). Pure presentation — no rules, no values. | The web editor only. | No. |

Mental model: the **schema is the empty cookie cutter**, the **config is the cookie**. The cookie is what you actually eat (= the device runs); the cutter just makes sure your cookie has the right shape.

You only ever flash and edit the **config**. The schema and ui-schema are reference material — the web editor pulls them in so it knows e.g. that `phy.mode` must be 0, 1, or 2 and not the string `"normal"`. If you somehow corrupt your config, you can rebuild it from scratch using the schema as the structural template.

> **Version matching matters.** The `-01.08` suffix is the firmware version. A config produced for `-01.08` may silently lose fields when loaded against a `-01.09` schema (or vice versa) — the editor only validates fields it knows about. Keep config and schema versions in lockstep with whatever firmware is on the CANedge.

### 6.2 How to edit the config — use the official web editor

**Don't edit the JSON by hand.** It's long and easy to break. CSS Electronics provides a free in-browser editor that loads the schema and gives you a proper form UI.

1. Open https://canlogger.csselectronics.com
2. Choose **Config Editor** → **Open Config**.
3. Load **both** files:
   - the **schema** → `CANedge/schema-01.08.json`
   - the **config** → `CANedge/config-01.08.json` (or one of the other variants)
4. The form opens. The interesting tab is **CAN-1 → Transmit**. That's the list of UDS requests we send.
5. Edit anything you want (add a PID, change a period, disable an entry by toggling `state`).
6. Click **Save Config** — it downloads the modified JSON.

> **Tip:** keep the schema and config matched in version (`-01.08`). Mixing versions causes silent field drops.

### 6.3 The shape of the JSON file

Before touching anything, here's the bird's-eye view of `config-01.08.json` — what each top-level key controls:

```jsonc
{
  "general":        { /* device info, security, debug/syslog, restart timer */ },
  "log":            { /* file split size/time, compression, encryption, error frames */ },
  "rtc":            { /* time sync mode, NTP server, timezone */ },
  "secondaryport":  { /* power schedule for the 2nd port (rarely used here)   */ },
  "can_internal":   { /* internal GNSS/IMU CAN — leave defaults */ },
  "can_1":          { /* THE BMS BUS — receive filters + scheduled transmits */ },
  "can_2":          { /* Second CAN channel (we keep it listen-only)         */ },
  "lin_1": {}, "lin_2": {},     // LIN buses, unused in this project
  "connect":        { /* WiFi + S3 cloud upload settings (optional)          */ },
  "gnss":           { /* GPS configuration                                   */ }
}
```

The **periodic UDS requests live under `can_1.transmit[]`** — that array is what you'll touch 95% of the time.

### 6.4 Anatomy of one transmit entry (field-by-field)

Every entry in `can_1.transmit` is one scheduled CAN frame. Here's a full annotated example for "read State of Charge":

```jsonc
{
  "name":         "SOC_BMS",          // Free-text label — appears in logs and the editor UI
  "state":        1,                  // 1 = enabled, 0 = entry exists but skipped
  "id_format":    1,                  // 0 = 11-bit standard, 1 = 29-bit extended (UDS = 1)
  "frame_format": 0,                  // 0 = classic CAN 2.0, 1 = CAN-FD
  "brs":          0,                  // CAN-FD bit-rate switch (only relevant if frame_format=1)
  "log":          1,                  // 1 = also write our outgoing frame into the MF4 log
  "period":       10000,              // Repeat every N milliseconds (10000 = every 10 s)
  "delay":        0,                  // Initial offset (ms) before the first send within each cycle
  "id":           "17FC007B",         // CAN ID (hex string, no 0x prefix). 7B = BMS address.
  "data":         "0322028c55555555"  // 8 hex bytes (16 chars) of payload
}
```

The **`data` field** is the actual UDS request, broken down byte by byte:

| Bytes | Hex     | Meaning                                                            |
|-------|---------|--------------------------------------------------------------------|
| [0]   | `03`    | ISO-TP **Single Frame**, 3 useful bytes follow                     |
| [1]   | `22`    | UDS service ID = `ReadDataByIdentifier`                            |
| [2:3] | `028c`  | The PID we want — `0x028C` = State of Charge                       |
| [4:7] | `55…`   | Padding to fill the 8-byte CAN frame (any value works; `0x55` is the convention) |

To request a different PID, change just bytes [2:3]. Everything else is identical for every UDS read.

#### Periodic vs. one-shot

There is no separate "one-shot" flag — periodic transmission is the only mode. If you want to send something **once at startup**, set `period` to a very large number (e.g. `3600000` = 1 hour) and `delay` to `0`. The frame fires once at startup and then effectively never again within a normal session.

A "real" one-shot is the `control` block (see §6.6) which lets transmissions start/stop based on a received signal — useful for "only send while the car is in READY mode".

#### Rules of thumb

- **Stagger your `delay` values** (0, 150, 300, 450, …). If ten entries all fire at `delay=0` they'll collide on the bus and the BMS will only answer the first few. The canonical config uses 150 ms steps.
- **Pad `data` to a full 8 bytes** (`0x55` is what CSS uses by convention). The BMS doesn't care about the padding bytes, but a fixed pattern makes logs easier to scan visually.
- **`id_format` must be `1`** for VW MEB UDS — the BMS only accepts 29-bit addressed requests.
- **`frame_format` stays `0`** unless you explicitly want CAN-FD. The MEB diagnostic bus is classic CAN.
- **`log: 1`** is what makes your outgoing requests visible in the MF4 file (under channel group `CAN1_Tx_IDE`). Without this you'd see only the BMS responses, not your questions.

### 6.5 What else you can put in `transmit[]`

The transmit array is just a list of CAN frames; the device doesn't care what protocol they belong to. Useful things to add:

#### Diagnostic session control + TesterPresent

Some PIDs are only accessible after raising the diagnostic session level, and the BMS will drop the session after ~5 s of silence. Two extra entries fix both:

```jsonc
// 1. Open an extended diagnostic session (service 0x10, sub-function 0x03)
{ "name": "DiagSessionControl", "state": 1, "id_format": 1, "frame_format": 0,
  "brs": 0, "log": 1, "period": 5000, "delay": 0,
  "id": "17FC007B", "data": "021003555555555555" /* note: 02 length, 10 service, 03 subfunc */ },

// 2. Tester Present — keeps the session alive, fires every 2 s
{ "name": "TesterPresent",     "state": 1, "id_format": 1, "frame_format": 0,
  "brs": 0, "log": 1, "period": 2000, "delay": 50,
  "id": "17FC007B", "data": "023e00555555555555" }
```

`build_canedge_transmit_config.py` already emits these two as the first entries of any generated config.

#### Talking to ECUs other than the BMS

Each MEB ECU has its own diagnostic address. Change the last byte of the request ID:

| ECU                           | Request ID    | Response ID   |
|-------------------------------|---------------|---------------|
| BMS (Battery Management)      | `17FC007B`    | `17FE007B`    |
| Onboard charger               | `17FC008C`    | `17FE008C`    |
| DC-DC converter               | `17FC0079`    | `17FE0079`    |
| (any other ECU)               | `17FC00xx`    | `17FE00xx`    |

You can mix ECUs freely in the same `transmit` array — just remember each ECU has its own PID list and its own session timeout, so add a TesterPresent for each address you want to keep awake.

#### Other UDS services

You're not limited to `0x22 ReadDataByIdentifier`. Any service that fits in a single CAN frame works the same way — change the service ID byte:

| Service        | SID  | Use case                                                |
|----------------|------|---------------------------------------------------------|
| ReadDataByIdentifier | `22` | What we use everywhere — read a PID                |
| ECUReset       | `11` | Forces a reset; **don't** use unless you really mean it |
| ClearDTC       | `14` | Clear stored fault codes                                |
| ReadDTCInformation | `19` | Pull stored fault codes                              |
| RoutineControl | `31` | Trigger built-in service routines                       |

For this thesis we only ever use `0x22`. The others are listed here because the same JSON shape supports them.

### 6.6 Other things you can configure (outside `transmit[]`)

Most of these are set once and forgotten, but knowing they exist saves time when something behaves oddly.

#### `can_1.phy` — physical layer
| Field      | Values              | What it does                                                       |
|------------|---------------------|--------------------------------------------------------------------|
| `mode`     | `0` Normal, `1` Restricted, `2` Monitoring | **Must be 0** to transmit. Setting `1`/`2` makes us listen-only and UDS will silently fail. |
| `retransmission` | `0` / `1`     | Whether to retry a frame if the bus didn't ACK. Leave `1`.         |
| `bit_rate_cfg_mode` | `0` auto / `1` manual | Auto-detect almost always works on the MEB diagnostic bus. |

#### `can_1.filter` — what gets logged
By default we log everything (`AllStandardID` and `AllExtendedID` ranges enabled). You can:
- **Whitelist** specific IDs to shrink log file size — useful if you only care about the BMS and want to drop unrelated chatter.
- Add a filter named e.g. `"BMS_only"` with `id_format: 1`, `f1: "17FE007B"`, `f2: "17FE007B"` to log only BMS responses.
- The same filter array supports a `prescaler_type` field for downsampling chatty IDs.

#### `can_1.heartbeat` — periodic "I'm alive" frame from the device
Optional. If `state: 1`, the CANedge sends its own heartbeat frame on the bus at the configured ID. We leave this off (`state: 0`) — the car doesn't need to know we're there, and silent loggers are politer.

#### `can_1.control` — start/stop logging on a CAN signal
This is how you make the device only log (and only transmit) under certain conditions. Two trigger blocks: `start` and `stop`. Each watches a specific signal in a specific incoming CAN message, and fires when the signal crosses a threshold.

Example use case: only run UDS while ignition is on. Configure `start` to trigger on the ignition-status signal going high, and `stop` on it going low. While stopped, the device is silent — no transmits, no log writes — which protects the bus and saves SD card space.

We currently leave `control_rx_state` and `control_tx_state` at `0` (always on) because the user manually plugs the device in only when the car is in READY mode.

#### `log.file` — log rotation
| Field              | Default | Notes                                                              |
|--------------------|---------|--------------------------------------------------------------------|
| `split_size`       | `50`    | Maximum MF4 file size in MB. New file starts when reached.         |
| `split_time_period`| `0`     | Force a new file every N minutes. `0` disables.                    |
| `cyclic`           | `1`     | When the SD card fills up, overwrite the oldest session.           |

#### `log.compression` and `log.encryption`
Compression is `level: 0` (off) by default — keep it off, decoding pipelines run faster on uncompressed MF4. Encryption is also off; turning it on means you have to provide a key to every tool that reads the file.

#### `log.error_frames.state`
Set to `1` to log CAN error frames (extra channel group `CAN1_Errors`). Useful when debugging "why is no one ACKing my requests" — but enormous logs result if the bus is unhealthy (recall session 19 with 1.65 M error frames).

#### `rtc` — time stamping
The MF4 timestamps are only meaningful relative to the start of the session unless the device clock is set. Three options:
- `sync: 0` — no sync, timestamps are device-uptime-based.
- `sync: 1` — sync from GNSS at startup (needs sky view).
- `sync: 2` — sync from NTP (needs WiFi). This is what we use; `ntp_server: "*.pool.ntp.org"`.

#### `connect.s3` — automatic cloud upload
If you set up WiFi credentials and an S3 endpoint, the CANedge can upload finished MF4 files automatically. We don't use this for the thesis — manual SD card copy is simpler — but it's there if you want hands-free fleet logging.

### 6.7 Regenerating the transmit list from the PID CSV

If you fix a PID in `data/csv/VW MEB UDS PIDs list.csv` or want to refresh the JSON, regenerate it instead of editing by hand:

```powershell
python -X utf8 src/build_canedge_transmit_config.py
```

This reads the CSV and writes `CANedge/config-01.08-built.json`.

**What the script outputs today (32 entries, curated):**
- DiagnosticSessionControl + TesterPresent (the "wake the BMS up and keep it awake" frames)
- 13 priority PIDs (SOC, pack V/I, op mode, key temps)
- 16 sampled cell voltages (a representative spread across the 108 cells the BMS reports)
- 6 module temperatures

**What we actually want for this thesis: the full ~198-PID list.** The current curated output is a historical artefact — it was the smallest list that fit in a 10 s cycle while still answering the original questions. Two ways to get full coverage:

1. **Edit the script** so the priority/sampling logic is replaced with "emit every row of the CSV". Then re-run it. This is the durable fix and keeps JSON ↔ CSV in sync.
2. **Hand-extend the generated JSON** in the web editor. Add one transmit entry per missing PID, copy-pasting from existing entries. Tedious, but no script changes needed.

Either way, remember the bus-time math: ~198 entries × 150 ms stagger ≈ 30 s, so bump `period` to **≥ 35 000 ms** (or reduce the stagger). See the warning in [Section 2 → Phase 1 → step 2](#2-working-process--end-to-end).

Once the JSON has what you want, either flash that file directly (rename to `config-01.08.json`) or copy its `transmit` array into the canonical `config-01.08.json`.

### 6.8 Flashing the config to the device

1. Power down the CANedge (unplug from the OBD port).
2. Pop out the microSD card and put it in your laptop.
3. Copy your edited `config-01.08.json` to the **root of the SD card**, overwriting the old one.
4. Eject cleanly, put the SD back in the CANedge.
5. Plug the CANedge back into the car. After a few seconds the yellow LED should settle into continuous-on (with brief blinks for activity) — that means the config parsed and the CAN bus is up.

If the yellow LED stays off or flashes irregularly, the JSON is most likely malformed; reload it in the editor and re-save (it catches most schema errors). Other causes: SD card missing/full, or the bus isn't up because the car hasn't reached READY mode yet.

### 6.9 Capturing a session

1. Start the car (key in, foot on brake, button press — must reach **READY**, not just accessory).
2. Let it idle (or drive it). Each session of activity becomes its own `LOG/<device-id>/<NNNN>/00000001.MF4` folder on the SD card.
3. When done, power down, pull the SD card.
4. Copy the new session folder into `data/sd_dumps_<id>_<date>/LOG/<id>/` in the repo, or directly into `data/mf4/<session>/` if you prefer the legacy layout.

---

## 7. Decoding the UDS Captures

Once you have an MF4 file with UDS responses, decoding is a single command:

```powershell
python -X utf8 src/uds_battery_decoder.py
```

Or for a single session:

```powershell
python -X utf8 src/uds_battery_decoder.py --session 00000013
```

What this does, in order:

1. **Loads the PID database** from `data/csv/VW MEB UDS PIDs list.csv`. Each row becomes a record keyed by 16-bit PID with the value-byte layout (`labels_by_position`) parsed out of the `datareceived` column.
2. **Loads every MF4 file** under `data/mf4/` and `data/sd_dumps_*/LOG/*/`, iterating every CAN channel group (so extended-ID groups are not dropped). With `--session <label>`, only matching folders are processed.
3. **Filters to `0x17FE007B` responses** (BMS replies).
4. **Decodes each response's ISO-TP framing**:
   - `0x` → Single Frame: full payload in this one frame.
   - `1x` → First Frame: only first 3 value bytes are usable (we can't request continuation, see [Section 5.3](#53-the-response-and-why-it-sometimes-spans-multiple-frames)). Marked as *partial*.
   - `7F` → Negative Response: BMS refused (logged, but no value).
5. **Maps payload bytes onto the PID's letter labels** (`WW`, `XX`, `YY`, `ZZ`, …).
6. **Normalizes the formula** — turns `2^N` into `2**N`, swaps `,` for `.`, strips annotation comments — and `eval`s it with restricted globals.
7. **Writes results** to:
   - `output/uds_decoded/<session>.csv` — one CSV per session (raw rows).
   - `output/uds_decoded/all_sessions.csv` — merged decoded rows across every session in this run.
   - **`output/uds_decoded/<session>__summary.txt` — per-PID statistics for that session alone.** One file per session, so non-contiguous captures (different days, different drives) keep their stats separated.
   - `output/uds_decoded/summary.txt` — per-PID statistics merged across every session in this run. Header lists which sessions were folded in.
   - `output/uds_decoded/plots/pid_*.png` — a time-series plot for every decoded PID, with each session as a separate trace.

When you decode a single session with `--session`, only that session's per-session summary is meaningful — the merged `summary.txt` will contain only that one session's data too.

That's the whole pipeline. Read the CSV in pandas, feed it to the thesis plots, done.

---

## 8. Key Findings Summary

### Successfully Decoded (UDS battery PIDs)
- **State of Charge** (`0x028C`) — percentage, single-byte signal.
- **Pack voltage / current** (`0x1E3B`, `0x1E3D`) — pack-level HV measurements (current is approximate due to the multi-frame CANedge limitation).
- **Pack temperatures** (`0x2A0B`, `0x1E0E`, `0x1E0F`) — main, max, min battery temperature.
- **Cell voltages** (`0x1E40`+) — sampled set of individual cell voltages spanning the pack.
- **Per-module temperatures** (`0x1EAE`–`0x1EBD`, `0x2725`, `0x2726`) — 18 module temperature points.
- **Operating mode** (`0x7448`) — standby / driving / AC charging / DC charging.
- **Energy content & total throughput** (`0x2AB8`, `0x2AB2`, `0x1E32`).

Each decoded sample is a row in `output/uds_decoded/all_sessions.csv`; per-PID time-series plots live in `output/uds_decoded/plots/`.

### Known limitations
- **Multi-frame approximation.** Signals whose value is wider than 3 bytes (notably high-resolution pack current) are decoded from the First Frame only, because the CANedge cannot send Flow Control. See [Section 5.3](#43-the-response-and-why-it-sometimes-spans-multiple-frames).
- **Vehicle state matters.** Sessions captured with the car not in READY mode produce only error frames (e.g. session 19 of the 2025-04-09 dump: 1.65 M error frames).
- **Some CSV formulas have minor errors.** The decoder skips on eval failure rather than crashing.

---

## 9. Using asammdf GUI for MF4 Analysis

The project includes a portable version of the **asammdf GUI** application at `tools/asammdf_gui/asammdfgui.exe`. This tool provides a graphical interface for inspecting MF4 files without writing any code — useful for quick sanity checks ("did the BMS even reply?").

### 9.1 Launching the Application
1. Navigate to `tools/asammdf_gui/`
2. Double-click `asammdfgui.exe` to launch the application
3. The GUI window will open with a toolbar and empty workspace

### 9.2 Opening an MF4 File
1. Click **File > Open** (or use `Ctrl+O`)
2. Browse to the `log/` directory (e.g., `log/00000004/00000001.MF4`)
3. The file will load and display its channel groups in the left panel

### 9.3 Understanding the Channel Tree
After opening a file, the left panel shows the file structure:
- **Group 0: CAN_DataFrame** - This contains our CAN data. Expand it to see:
  - `CAN_DataFrame.BusChannel` - The CAN bus number
  - `CAN_DataFrame.ID` - CAN arbitration IDs
  - `CAN_DataFrame.DLC` - Data length codes
  - `CAN_DataFrame.DataBytes` - Raw payload data
  - `CAN_DataFrame.Dir` - Message direction
- **Group 1: CAN_RemoteFrame** - Remote frames (usually empty)
- **Group 2: CAN_ErrorFrame** - Error frames (useful for bus health check)

### 9.4 Plotting Signals
1. In the channel tree, select the signal you want to plot (e.g., `CAN_DataFrame.ID`)
2. **Drag and drop** it onto the plot area, or right-click and select **Add to Plot**
3. The signal will appear as a time series plot
4. You can add multiple signals to the same plot for comparison
5. Use the **mouse scroll wheel** to zoom in/out on the time axis
6. Click and drag to pan the view

### 9.5 Filtering by CAN ID
To view data for a specific CAN ID only:
1. Go to **View > Filter** or look for a filter option in the toolbar
2. You can apply a filter expression to show only frames matching a specific CAN ID
3. Alternatively, export the data and filter in Python (see `mf4_reader.py`)

### 9.6 Viewing Raw Hex Data
1. Switch to the **Tabular** view (look for table/grid icon in the toolbar)
2. This shows each CAN frame as a row with all its columns
3. You can see the raw hex data for each frame's payload
4. Sort by timestamp or CAN ID by clicking column headers

### 9.7 Exporting Data
1. Click **File > Export** or right-click on a channel group
2. Choose your export format:
   - **CSV** - For spreadsheet/Python analysis
   - **MAT** - For MATLAB
   - **HDF5** - For large dataset handling
   - **MDF** - To convert between MDF versions
3. Select output path and click Export

### 9.8 Comparing Multiple Files
1. Open the first MF4 file normally
2. Go to **File > Open** again to load additional files
3. Each file appears as a separate tab
4. You can plot signals from different files on the same axes for comparison

### 9.9 Tips for CAN Analysis in asammdf GUI
- **Zoom to anomalies:** If you see a spike or transition in a plotted signal, zoom in to examine the exact timestamp and value
- **Cross-reference:** Plot `CAN_DataFrame.ID` alongside `CAN_DataFrame.DataBytes` to correlate message types with their payloads
- **Check timing:** Plot message arrival times to verify bus timing (regular intervals = periodic message, irregular = event-triggered)
- **Bus load:** The CAN_ErrorFrame group can show bus errors, which might indicate bandwidth saturation or electrical issues

---

## 10. Running the Analysis Scripts

All scripts live under `src/` and are run **from the repo root**. Path resolution inside `mf4_reader.py` assumes that.

### Prerequisites
```powershell
pip install -r requirements.txt
```

**Note:** on Windows with Python 3.13, prefix every command with `-X utf8` to avoid encoding errors:
```powershell
python -X utf8 src\some_script.py
```

### Workflow

| Step | Command | Output |
|------|---------|--------|
| Decode all sessions | `python -X utf8 src/uds_battery_decoder.py` | `output/uds_decoded/all_sessions.csv`, `summary.txt`, `plots/pid_*.png` |
| Decode one session | `python -X utf8 src/uds_battery_decoder.py --session 00000013` | Same, filtered to one session |
| Regenerate transmit list | `python -X utf8 src/build_canedge_transmit_config.py` | `CANedge/config-01.08-built.json` |
| Sanity-check raw MF4 | `python -X utf8 src/mf4_reader.py` | `output/can_data.csv` — merged frames across sessions |

---

## 11. File Reference

### Source files (`src/`)
| File | Description |
|------|-------------|
| `mf4_reader.py` | Loads MF4 files into pandas. Iterates **every** CAN channel group so extended-ID UDS traffic is not dropped. |
| `uds_battery_decoder.py` | UDS decoder — reads `0x17FE007B` responses, maps bytes to formula labels, evaluates and exports CSV + plots. |
| `build_canedge_transmit_config.py` | Generates the CANedge transmit list from the PID CSV. The canonical way to keep config and decoder in sync. |

### Data
| Path | Contents |
|------|----------|
| `data/mf4/<session>/00000001.MF4` | Original CANedge logs (sessions 00000002–00000008). |
| `data/sd_dumps_2A73E1CC_20250409/LOG/2A73E1CC/<session>/` | Full SD card dump from 2025-04-09 (14 sessions). |
| `data/csv/VW MEB UDS PIDs list.csv` | Community-sourced UDS PID definitions (~198 entries). |

### CANedge configs (`CANedge/`)
| File | Purpose |
|------|---------|
| `config-01.08.json` | Canonical 64-PID transmit config — flash this on the device. |
| `config-01.08-built.json` | Auto-generated from the PID CSV (32 entries; regenerate after CSV edits). |
| `config-01.08-test5.json` | 5-PID smoke test. |
| `config-01.08-testerpresent-only.json` | Archived experiment that captured sessions 12–23. |
| `schema-01.08.json`, `uischema-01.08.json` | Schema files used by the official Config Editor at canlogger.csselectronics.com. |

### Outputs (`output/`)
| Path | Contents |
|------|----------|
| `output/uds_decoded/<session>.csv` | All raw response rows from one session (one file per session processed). |
| `output/uds_decoded/all_sessions.csv` | Decoded rows merged across every session in the last run (timestamp, session, PID, name, value, unit). |
| `output/uds_decoded/<session>__summary.txt` | Per-PID statistics for that session in isolation — separate file per session because non-contiguous captures shouldn't be averaged. |
| `output/uds_decoded/summary.txt` | Per-PID statistics merged across every session in the last run. |
| `output/uds_decoded/plots/pid_*.png` | Time-series plot per decoded PID (each session is a separate trace). |
| `output/can_data.csv` | Sanity-check dump of all frames merged across sessions (used only to verify the MF4 reader). |

### Tools
| Path | Purpose |
|------|---------|
| `tools/asammdf_gui/asammdfgui.exe` | Portable asammdf GUI for manual MF4 inspection. |
| `tools/SavvyCAN_Converter/` | Standalone tool to convert MF4 to SavvyCAN format. |
| `can_analyzer/` | Rust/egui desktop CAN viewer (independent of the Python pipeline). |
