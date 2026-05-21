# Data Collection Strategy — Battery Parameters

## The Problem

Right now I have 7 CAN IDs (0x065-0x06F) captured passively from the OBD-II port. These are **11-bit standard CAN IDs** and appear to be general vehicle/network management messages — not battery data.

The battery parameters I actually need (cell voltages, SOC, pack current, temperatures) are only available via **UDS diagnostic requests** to the BMS ECU. These use **29-bit extended CAN IDs**:
- Request to BMS: `0x17FC007B`
- Response from BMS: `0x17FE007B`

UDS is request/response — the BMS won't just broadcast this data. I have to actively ask for it.

So the question is: **How do I get the CANedge2 to request and capture UDS diagnostic data from the BMS?**

---

## Strategy A: CANedge2 Transmit List (Preferred)

### Idea
The CANedge2 has a **transmit list** feature in its configuration. I can set it up to periodically send UDS request frames while simultaneously logging all traffic (including the BMS responses).

### What I Need To Check
1. Does the CANedge2 support **29-bit extended CAN IDs** in its transmit list?
2. Does it support **ISO-TP** (ISO 15765) for multi-frame responses?
   - Single-frame responses (<=7 data bytes) should work fine
   - Multi-frame responses need flow control frames — does CANedge2 handle this?
3. What's the minimum transmit interval? (I need ~100ms between requests)
4. Can I send a UDS **diagnostic session request** (0x10 0x03 = extended diagnostic session) before the actual data requests?

### How To Test
1. Open the CANedge2 config editor (browser-based at 192.168.65.1 or via config file)
2. Go to CAN channel settings > Transmit list
3. Add one simple test request:
   - CAN ID: `0x17FC007B` (29-bit extended)
   - Data: `03 22 02 8C 55 55 55 55` (this requests SOC from BMS)
   - Interval: 1000ms (once per second)
4. Start logging, check if response `0x17FE007B` appears in the log
5. If yes → this strategy works, add more PIDs

### Priority PIDs To Request (Start Simple)

| PID | DID | Request Data (8 bytes) | What It Returns |
|-----|-----|----------------------|-----------------|
| SOC (BMS) | 02 8C | `03 22 02 8C 55 55 55 55` | State of charge (%) |
| HV Voltage | 1E 3B | `03 22 1E 3B 55 55 55 55` | Pack voltage (V) |
| HV Current | 1E 3D | `03 22 1E 3D 55 55 55 55` | Pack current (A) |
| Battery Temp | 2A 0B | `03 22 2A 0B 55 55 55 55` | Main temperature (C) |
| Max Temp | 1E 0E | `03 22 1E 0E 55 55 55 55` | Hottest sensor (C) |
| Min Temp | 1E 0F | `03 22 1E 0F 55 55 55 55` | Coldest sensor (C) |

**Note:** Before sending data requests, I probably need to open an extended diagnostic session first:
- Send: `02 10 03 55 55 55 55 55` to `0x17FC007B`
- Expected response: `02 50 03` from `0x17FE007B`

### Pros
- Clean setup, just CANedge2 alone
- Automatic logging + requesting in one device
- Repeatable (same config every time)

### Cons
- May not support ISO-TP for multi-frame responses (cell voltages need this)
- Need to figure out CANedge2 config editor
- Limited number of PIDs in transmit list

---

## Strategy B: OBD-II Adapter + CANedge2 as Logger

### Idea
Use a separate diagnostic tool to send UDS requests, while the CANedge2 just logs everything passively (both the requests and responses).

### Options for the Diagnostic Tool
1. **OBDEleven** (VW-specific Android app + dongle) — supports VW UDS, easy to use
2. **VCDS / VAG-COM** (Ross-Tech) — the standard VW diagnostic tool
3. **Python + python-can + USB-CAN adapter** (like PEAK PCAN-USB) — full control, scriptable
4. **ELM327 Bluetooth adapter + custom script** — cheap but limited

### How To Set Up
1. Get a **Y-splitter** for the OBD-II port (so both the diagnostic tool and CANedge2 connect)
   - Or: Connect CANedge2 directly to CAN bus wires, diagnostic tool to OBD-II port
2. CANedge2 config: set to **listen mode** (no transmit), both channels active
3. Make sure both devices are set to the same bitrate (500 kbps for VW MEB)
4. The diagnostic tool sends requests → BMS responds → CANedge2 captures everything

### If Using Python + PCAN-USB
```python
import can
import time

bus = can.Bus(interface='pcan', channel='PCAN_USBBUS1', bitrate=500000)

# Open extended diagnostic session
diag_session = can.Message(
    arbitration_id=0x17FC007B,
    data=[0x02, 0x10, 0x03, 0x55, 0x55, 0x55, 0x55, 0x55],
    is_extended_id=True
)
bus.send(diag_session)
time.sleep(0.5)

# Request SOC
soc_request = can.Message(
    arbitration_id=0x17FC007B,
    data=[0x03, 0x22, 0x02, 0x8C, 0x55, 0x55, 0x55, 0x55],
    is_extended_id=True
)

while True:
    bus.send(soc_request)
    response = bus.recv(timeout=1.0)
    if response and response.arbitration_id == 0x17FE007B:
        # Parse SOC
        xx = response.data[3]  # Based on response pattern
        soc = xx / 2.5
        print(f"SOC: {soc:.1f}%")
    time.sleep(1.0)
```

### Pros
- CANedge2 just logs — no config changes needed
- Diagnostic tool handles all the UDS/ISO-TP complexity
- Can request cell voltages (multi-frame) properly

### Cons
- Need additional hardware (Y-splitter + diagnostic adapter)
- More complex setup
- Two devices to manage

---

## Strategy C: Direct CAN Bus Tap (Physical)

### Idea
Instead of going through the OBD-II port (which has a gateway that filters traffic), connect directly to the CAN bus wires between the BMS and the gateway.

### Why This Might Help
The gateway in VW MEB vehicles filters which CAN messages are forwarded to the OBD-II port. On the internal powertrain CAN bus, there might be **broadcast BMS messages** that never reach the OBD port. These would be 11-bit CAN IDs with regular battery data (voltage, current, SOC) sent periodically without any UDS request needed.

### How To Do It
1. Find the CAN bus connecting the BMS to the gateway (check VW wiring diagrams)
2. Use T-connectors or CAN bus taps (non-destructive)
3. Connect CANedge2 to this bus
4. Log passively — should see all BMS broadcast messages

### Pros
- Might get battery data without UDS requests
- Unfiltered access to BMS broadcast messages
- Simple passive logging

### Cons
- Need physical access to vehicle wiring
- Need wiring diagrams (may not be publicly available)
- Safety considerations (working near HV battery)
- More invasive than OBD-II connection

---

## Strategy D: Check What's Already In The Data

### Idea
Before trying new hardware setups, take another careful look at the 7 CAN IDs I already have. Some of them might actually contain battery-related parameters.

### Why
- 0x066 B[3] was decoded as temperature (8-10 C with raw-40 offset) — could this be a battery temperature?
- 0x067 B[5] was decoded as temperature (11-13 C) — same question
- 0x067 B[0], B[4] and 0x068 B[0] are dynamic signals — could these be battery voltage/current?
- The CAN IDs 0x065-0x06F are in a very specific range — maybe they're from the BMS itself?

### What To Do
1. Check the CAN ID range 0x065-0x06F against known VW MEB CAN databases (forums, opendbc, etc.)
2. Look at the temperatures more carefully — are they consistent with battery cell temperatures?
3. The dynamic signals in 0x067/0x068 — could they be battery voltage or current?

### Pros
- No additional hardware needed
- Can be done immediately
- Might find battery data hiding in plain sight

### Cons
- Only 5.5 minutes of data, limited scenarios
- Can't confirm without controlled tests

---

## Recommended Order of Action

### This Week (Week 3):

**Day 1: Check CANedge2 capabilities**
- [ ] Open CANedge2 config editor
- [ ] Check if transmit list supports 29-bit extended CAN IDs
- [ ] Check if ISO-TP is available
- [ ] Document what's possible and what's not

**Day 2: Test Strategy A (simple UDS request)**
- [ ] Configure one test request in transmit list (SOC PID: `03 22 02 8C`)
- [ ] Run a short recording (2 min)
- [ ] Check if BMS responds (look for CAN ID `0x17FE007B` in the log)
- [ ] Document result: WORKS / DOESN'T WORK

**Day 3: Based on Day 2 results**
- If Strategy A works → add more battery PIDs to transmit list
- If Strategy A doesn't work → investigate Strategy B (what hardware do I have/need?)
- Either way → also run Strategy D (re-examine existing data with battery lens)

**Day 4: First battery data collection attempt**
- [ ] Using whichever strategy works, record battery data
- [ ] Test during: standstill, driving, and if possible, charging

**Day 5: Analyse first results**
- [ ] Load new MF4 files
- [ ] Check if UDS responses are captured
- [ ] Try to decode SOC, voltage, current, temperature

---

## Decision Tree

```
Can CANedge2 send 29-bit CAN frames?
├── YES → Try sending UDS request to BMS (Strategy A)
│   ├── BMS responds? → SUCCESS - add more PIDs
│   └── No response? → Need diagnostic session first (send 0x10 0x03)
│       ├── Works now? → SUCCESS
│       └── Still nothing? → Gateway might be blocking → try Strategy C (direct tap)
│
└── NO → Need external diagnostic tool (Strategy B)
    ├── Have OBDEleven / VCDS? → Use that + CANedge2 as logger
    └── Have USB-CAN adapter? → Write Python script + CANedge2 as logger
        └── Don't have anything? → Buy PCAN-USB or ELM327 adapter
```

---

## What Battery Parameters I Need (Priority Order)

### Must Have (thesis core)
1. **SOC (State of Charge)** — % remaining
2. **HV Battery Voltage** — total pack voltage
3. **HV Battery Current** — charge/discharge current
4. **Battery Temperature** — main temp reading

### Should Have (strong thesis)
5. **Cell Voltages** — individual cell readings (need ISO-TP for this)
6. **Temperature Points** — multiple sensor locations
7. **Max/Min Cell Voltage** — identifies weakest cell
8. **Cooling liquid temps** — inlet/outlet

### Nice To Have (extra depth)
9. **Charge/discharge limits** — dynamic limits set by BMS
10. **Total energy charged/discharged** — lifetime counters
11. **Circulation pump %** — cooling system activity
12. **PTC heater current** — battery heating in cold weather
