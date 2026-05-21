# Data Collection Procedure — Battery Focus

This is the step-by-step procedure to follow for every data collection session.
Fill this in as you go. Copy the template section at the bottom for each new session.

---

## Before You Start (One-Time Setup)

### Step 1: Verify CANedge2 Configuration
- [ ] Connect to CANedge2 config interface (WiFi or USB)
- [ ] Confirm CAN bitrate: **500 kbps** (standard for VW MEB)
- [ ] Check CAN channel config:
  - Channel 1: Standard 11-bit + Extended 29-bit frames enabled
  - Channel 2: Same (if dual-channel)
- [ ] Check SD card: formatted, enough free space (>1 GB)
- [ ] If using transmit list:
  - [ ] Diagnostic session request added: `0x17FC007B` → `02 10 03 55 55 55 55 55`
  - [ ] Battery PID requests added (see PID list below)
  - [ ] Transmit interval set (recommend: 500ms per PID, stagger them)

### Step 2: Prepare Your Equipment
- [ ] CANedge2 fully charged / powered
- [ ] OBD-II cable or Y-splitter ready
- [ ] Phone ready for manual annotation (stopwatch app open)
- [ ] This checklist printed or open on phone
- [ ] Weather app open (note ambient temperature)

---

## Standard PID Request List (for CANedge2 Transmit Config)

Configure these in the transmit list. All go to CAN ID `0x17FC007B` (29-bit extended).

**Start with the diagnostic session request — it must be sent first!**

| # | PID Name | DID | Transmit Data (hex) | Interval | Priority |
|---|----------|-----|---------------------|----------|----------|
| 0 | Diagnostic Session | - | `02 10 03 55 55 55 55 55` | Once at start | REQUIRED |
| 1 | SOC (BMS) | 02 8C | `03 22 02 8C 55 55 55 55` | 1000ms | MUST |
| 2 | HV Voltage | 1E 3B | `03 22 1E 3B 55 55 55 55` | 1000ms | MUST |
| 3 | HV Current | 1E 3D | `03 22 1E 3D 55 55 55 55` | 1000ms | MUST |
| 4 | Battery Temp | 2A 0B | `03 22 2A 0B 55 55 55 55` | 2000ms | MUST |
| 5 | Max Temp | 1E 0E | `03 22 1E 0E 55 55 55 55` | 2000ms | SHOULD |
| 6 | Min Temp | 1E 0F | `03 22 1E 0F 55 55 55 55` | 2000ms | SHOULD |
| 7 | Cooling Inlet/Outlet | 18 9D | `03 22 18 9D 55 55 55 55` | 5000ms | NICE |
| 8 | Charge Limit | 1E 1B | `03 22 1E 1B 55 55 55 55` | 5000ms | NICE |
| 9 | Discharge Limit | 1E 1C | `03 22 1E 1C 55 55 55 55` | 5000ms | NICE |
| 10 | Pump % | 74 3B | `03 22 74 3B 55 55 55 55` | 5000ms | NICE |

**Expected response CAN ID:** `0x17FE007B`
**Response format:** `05 62 [DID_hi] [DID_lo] XX YY ...` (first byte = length, 62 = positive response to 22)

---

## Test Scenarios — Battery Focused

### Scenario 1: Baseline (Standstill, Ignition ON)
**Purpose:** Get stable baseline values for all battery parameters
**Duration:** 5 minutes
**What to do:**
1. Car parked, flat surface
2. Press start button (ignition ON, not driving)
3. Don't touch anything — let everything stabilize
4. Note dashboard SOC reading

**What to expect:**
- SOC should be constant
- Voltage should be stable
- Current should be near 0 (small 12V system draw)
- Temperature should match ambient (if car hasn't been driven recently)

### Scenario 2: Driving — Constant Speed
**Purpose:** See how battery current/voltage change under steady load
**Duration:** 5-10 minutes per speed
**What to do:**
1. Drive at constant 50 km/h (cruise control if possible)
2. Drive at constant 100 km/h
3. Note SOC at start and end of each speed

**What to expect:**
- Current should be negative (discharging) and roughly constant
- Higher speed = higher current draw
- Voltage should be slightly lower than at standstill (under load)
- SOC should decrease slowly

### Scenario 3: Acceleration & Regen
**Purpose:** See peak current draw and regenerative braking
**Duration:** 15 minutes
**What to do:**
1. Accelerate hard 0-80 km/h (3 times)
2. Coast from 80 to 0 in B mode (regen braking) (3 times)
3. Normal braking from 80 to 0 (3 times)
4. Note timestamps for each event

**What to expect:**
- Hard acceleration = high negative current (big discharge)
- Regen braking = positive current (charging back)
- Normal braking = less regen current than B mode
- Voltage dips during high current draw

### Scenario 4: Temperature Under Load
**Purpose:** Watch battery temperature change during use
**Duration:** 20-30 minutes of mixed driving
**What to do:**
1. Note starting temperature
2. Drive normally (mixed city/highway)
3. Include some hard accelerations
4. Note temperature every 5 minutes from dashboard if visible

**What to expect:**
- Temperature should gradually increase during driving
- Max temp sensor might be near cells that are working hardest
- Cooling pump % should increase as temp rises

### Scenario 5: Charging Session (if possible)
**Purpose:** Capture battery behavior during charging
**Duration:** 15-30 minutes
**What to do:**
1. Start logging BEFORE plugging in
2. Plug in charger (DC fast charge preferred, AC is also fine)
3. Note SOC at plug-in
4. Let it charge for at least 15 min
5. Note SOC when unplugging
6. Keep logging for 2 min after unplugging

**What to expect:**
- Current should be positive (charging)
- DC fast charge: high current, voltage rising
- SOC should increase
- Temperature may rise during fast charging
- Cooling pump should be active

### Scenario 6: Cold Soak Start (if weather cooperates)
**Purpose:** See battery behavior at low temperature
**Duration:** 10 minutes
**What to do:**
1. Car has been parked overnight in cold weather (< 5 C)
2. Start logging immediately
3. Turn on car, drive normally
4. Watch temperature signals over time

**What to expect:**
- Low initial battery temperature
- PTC heater might be active (heating the battery)
- Battery might limit power at low temps
- Temperature should gradually increase

---

## Procedure Checklist (Follow This Every Time)

### Before Starting
```
- [ ] CANedge2 connected and power LED on
- [ ] SD card has space
- [ ] Config verified (bitrate, transmit list if applicable)
- [ ] Phone stopwatch ready
- [ ] Noted: Date, time, weather, ambient temp
- [ ] Noted: Dashboard SOC reading
- [ ] Noted: Odometer reading
```

### During Recording
```
- [ ] Start CANedge2 logging
- [ ] Wait 30 seconds for diagnostic session to establish
- [ ] Perform test scenario
- [ ] Log every action with timestamp (use stopwatch)
- [ ] Note any anomalies (warning lights, unusual behavior)
```

### After Recording
```
- [ ] Stop logging
- [ ] Note final SOC reading
- [ ] Remove SD card / download via WiFi
- [ ] Copy MF4 files to project data/mf4/ directory
- [ ] Name the folder descriptively (e.g., session_006_constant_50kmh)
- [ ] Verify files load: cd src && python -X utf8 mf4_reader.py
- [ ] Check: do I see CAN ID 0x17FE007B in the data? (= BMS responded)
- [ ] Back up to external drive
- [ ] Save annotation notes in data/annotations/
```

---

## Quick Verification Script

After collecting data, run this to check if you got battery responses:

```python
# quick_check.py - run from src/ directory
from mf4_reader import load_all
df = load_all()

# Check for UDS response from BMS
bms_responses = df[df['can_id'] == 0x17FE007B]
print(f"BMS response frames: {len(bms_responses)}")

if len(bms_responses) > 0:
    print("Battery UDS responses found!")
    print(f"Time range: {bms_responses.index[0]:.1f}s - {bms_responses.index[-1]:.1f}s")
    print(f"Sample data:")
    for _, row in bms_responses.head(5).iterrows():
        print(f"  {row['data_hex']}")
else:
    print("No BMS responses. Check:")
    print("  1. Is CANedge2 transmitting requests? (check config)")
    print("  2. Is the CAN ID filter set to accept 29-bit extended IDs?")
    print("  3. Are you connected to the right CAN bus?")

# Also check what CAN IDs ARE present
print(f"\nAll CAN IDs in recording:")
for cid in sorted(df['can_id'].unique()):
    count = len(df[df['can_id'] == cid])
    print(f"  0x{int(cid):08X} ({int(cid):>10d}) - {count} frames")
```

---

## Session Log Template (Copy For Each Session)

```
========================================
SESSION: _____ (e.g., session_006)
DATE: _____
TIME START: _____
TIME END: _____
WEATHER: _____ C, _____ (sunny/cloudy/rain)
AMBIENT TEMP: _____ C

VEHICLE STATE:
  SOC START: _____%
  SOC END: _____%
  ODOMETER: _____ km
  LAST DRIVEN: _____ (e.g., "2 hours ago" or "overnight")

CANEDGE2 CONFIG:
  Connection: OBD-II / Direct CAN tap / Y-splitter
  Transmit list: ON / OFF
  Channels: CH1 only / CH1+CH2
  Bitrate: 500 kbps

SCENARIO PERFORMED: _____ (e.g., Scenario 2 - Constant Speed)

TIMELINE:
  HH:MM:SS | Action                          | Notes
  ---------|--------------------------------|------------------
           | Started logging                 |
           | Car ignition ON                 |
           |                                 |
           |                                 |
           |                                 |
           | Stopped logging                 |

INITIAL RESULTS:
  BMS responses captured: YES / NO
  Total frames: _____
  CAN IDs seen: _____
  Any issues: _____

MF4 FILE: data/mf4/session_XXX/00000001.MF4
NOTES FILE: data/annotations/session_XXX_notes.txt
========================================
```
