# Data Collection Checklist & Driving Cases
# VW ID Buzz - CAN Signal Reverse Engineering

## Purpose
Controlled driving scenarios to identify unknown CAN signals by correlating
known vehicle behavior with raw CAN byte changes.

## Principle
> If you KNOW what the car is doing, you can FIND which signal reflects it.

---

## Pre-Drive Checklist

- [ ] CANedge2 SD card formatted / has free space
- [ ] CANedge2 config verified (bitrate, channels)
- [ ] CANedge2 physically connected and power LED on
- [ ] Phone ready for annotation (timestamp + action log)
- [ ] Note ambient temperature (weather app or thermometer or from dashboard)
- [ ] Note starting SoC (%) from dashboard
- [ ] Note odometer reading from dashboard
- [ ] Note point of time of Ignition/Engine ON

---

## Driving Cases

### CATEGORY A: Speed Identification (CRITICAL - Do First)

These cases let us find the speed signal by comparing known constant speeds.

| # | Case | What to Do | Duration | Why |
|---|------|-----------|----------|-----|
| A1 | **Standstill idle** | Engine ON, parked, no pedals | 3 min | Baseline: speed signal = 0 |
| A2 | **Constant 30 km/h** | Flat road, cruise control or steady pedal | 3 min | Reference point 1 |
| A3 | **Constant 50 km/h** | Flat road, cruise control | 3 min | Reference point 2 |
| A4 | **Constant 80 km/h** | Highway, cruise control | 3 min | Reference point 3 |
| A5 | **Constant 100 km/h** | Highway, cruise control | 3 min | Reference point 4 |
| A6 | **Constant 120 km/h** | Autobahn, cruise control | 3 min | Reference point 5 |

**How to identify speed:** Compare mean byte values across A1-A6. The speed signal will scale linearly (A5 value / A3 value should be approx 2.0).

**Notes during recording:**
- [ ] Use cruise control for consistency
- [ ] Log exact start/end timestamp per case
- [ ] Avoid hills - flat road only

---

### CATEGORY B: Acceleration & Braking

These cases isolate throttle, torque, braking, and regeneration signals.

| # | Case | What to Do | Duration | Why |
|---|------|-----------|----------|-----|
| B1 | **Gentle acceleration 0-50** | Slow pedal press, smooth ramp | 30 sec | Throttle + torque signals ramp up |
| B2 | **Hard acceleration 0-100** | Full pedal, max acceleration | 15 sec | Max torque, find signal limits |
| B3 | **Coasting from 80 km/h** | Release pedal completely, D mode | 30 sec | Throttle signal should = 0 |
| B4 | **Coasting from 80 km/h, B mode** | Release pedal, B (regen) mode | 30 sec | Compare regen signals vs B3 |
| B5 | **Normal braking 80-0** | Gradual brake press | 15 sec | Brake signal identification |
| B6 | **Hard braking 80-0** | Firm brake press | 10 sec | Max brake signal value |
| B7 | **Creeping forward** | Parking lot, very low speed ~5 km/h | 1 min | Near-zero speed, low torque |

**Notes during recording:**
- [ ] Log pedal press timestamps
- [ ] Note D mode vs B mode for each run
- [ ] Repeat each case 2-3x for confidence

---

### CATEGORY C: Ignition & Wake-Up Sequence

These confirm the NM heartbeat (0x065) and find boot-related signals.

| # | Case | What to Do | Duration | Why |
|---|------|-----------|----------|-----|
| C1 | **Cold start** | Car fully off for 10+ min, then start | 2 min | Full wake-up sequence |
| C2 | **Key ON, no drive** | Press start button, stay in P, wait | 2 min | Which CAN IDs appear and when |
| C3 | **Key OFF** | Turn off car, keep logging | 2 min | Shutdown sequence, NM state changes |
| C4 | **Repeat ON-OFF cycle x3** | Quick start/stop cycles | 3 min | Reproducibility check |

**Notes during recording:**
- [ ] Exact second of button press
- [ ] Note if doors open/close during test

---

### CATEGORY D: Steering

Find the steering angle signal.

| # | Case | What to Do | Duration | Why |
|---|------|-----------|----------|-----|
| D1 | **Straight driving** | Highway, hands steady | 2 min | Steering center baseline |
| D2 | **Full left lock** | Parking lot, turn wheel fully left | 10 sec | Max left value |
| D3 | **Full right lock** | Parking lot, turn wheel fully right | 10 sec | Max right value |
| D4 | **Slalom / weaving** | Slow speed, steer left-right-left | 1 min | Oscillating signal pattern |

**Notes during recording:**
- [ ] Low speed for safety
- [ ] Note wheel position at each timestamp

---

### CATEGORY E: Climate & Comfort

Identify HVAC and comfort signals.

| # | Case | What to Do | Duration | Why |
|---|------|-----------|----------|-----|
| E1 | **AC OFF** | All climate off, drive steady | 2 min | Baseline |
| E2 | **AC ON - low** | AC on, low fan, drive steady | 2 min | Compare with E1 |
| E3 | **AC ON - max** | AC max fan, drive steady | 2 min | Compare with E2 |
| E4 | **Heater ON - max** | Heat max, drive steady | 2 min | Different signal from AC |
| E5 | **All OFF again** | Turn everything off | 2 min | Confirm return to baseline |

---

### CATEGORY F: Lights & Indicators

Find lighting state signals.

| # | Case | What to Do | Duration | Why |
|---|------|-----------|----------|-----|
| F1 | **All lights off** | Parked, daytime | 1 min | Baseline |
| F2 | **Parking lights** | Toggle on | 30 sec | Step change in signal |
| F3 | **Low beam** | Toggle on | 30 sec | Different signal value |
| F4 | **High beam** | Flash or toggle | 30 sec | Another step |
| F5 | **Left indicator** | Blinker left | 30 sec | Pulsing signal expected |
| F6 | **Right indicator** | Blinker right | 30 sec | Opposite pulse pattern |
| F7 | **Hazard lights** | Toggle on | 30 sec | Both indicators active |

---

### CATEGORY G: Battery & Charging → Prio Nr. 1 for our research

Find SOC, voltage, current signals and many more → I put a list of all available parameters from the VW MEB-platform at the SharePoint (Link: [parameterliste.csv](https://thide.sharepoint.com/:x:/r/sites/GR-C-ECOS-TUEVSUEDBatterieZustand/Freigegebene%20Dokumente/General/15_Alif%20Bin%20Ibrahim/10_Literature/parameterliste.csv?d=w15ef475897764eeaa7f0d87df3384332\&csf=1\&web=1\&e=itBJJR))

| # | Case | What to Do | Duration | Why |
|---|------|-----------|----------|-----|
| G1 | **Extended drive (15+ min)** | Normal driving, mixed roads | 15-30 min | SOC should decrease slowly |
| G2 | **Note SOC every 5 min** | Check dashboard, write down % | - | Ground truth for SOC signal |
| G3 | **DC fast charging** (if possible) | Plug in, record during charge | 15 min | Charging current, SOC increasing |
| G4 | **AC charging** (if possible) | Plug in Level 2 charger | 15 min | Lower current, compare with G3 |

**Notes during recording:**
- [ ] SOC at start: ____%
- [ ] SOC at end: ____%
- [ ] Distance driven: ____ km
- [ ] Charger type (if charging): ____

---

### CATEGORY H: Drive Modes

Find drive mode / selector signals.

| # | Case | What to Do | Duration | Why |
|---|------|-----------|----------|-----|
| H1 | **D mode, constant 60 km/h** | Normal drive mode | 2 min | Baseline |
| H2 | **B mode, constant 60 km/h** | Switch to B (regen), same speed | 2 min | Compare with H1 |
| H3 | **Sport mode** (if available) | Switch to sport, same speed | 2 min | Compare |
| H4 | **Eco mode** (if available) | Switch to eco, same speed | 2 min | Compare |
| H5 | **Reverse** | Parking lot, reverse slowly | 30 sec | May trigger unique signals |
| H6 | **Park** | Shift to P | 30 sec | Gear selector signal |
| H7 | **Neutral** | Shift to N | 30 sec | Another gear state |

---

## Post-Drive Checklist

- [ ] CANedge2 LED still on (recording complete)
- [ ] Remove SD card or download data via WiFi
- [ ] Copy MF4 files to project `log/` directory
- [ ] Name folders by scenario (e.g., `session_005_speed_tests/`)
- [ ] Verify files load: `python -X utf8 mf4_reader.py`
- [ ] Save annotation notes alongside MF4 files
- [ ] Note ending SOC (%): ____
- [ ] Backup to external drive / cloud

---

## Recording Priority Order

If time is limited, do these in order of importance:

1. **A1-A5** (Speed identification) - MUST HAVE
2. **B1-B6** (Acceleration & braking) - MUST HAVE
3. **C1-C3** (Ignition cycle) - MUST HAVE
4. **G1-G2** (Extended drive for SOC) - HIGH
5. **H1-H2, H5-H7** (Drive modes & gear) - HIGH
6. **D1-D4** (Steering) - MEDIUM
7. **E1-E5** (Climate) - MEDIUM
8. **F1-F7** (Lights) - LOW (nice to have)
9. **G3-G4** (Charging) - LOW (depends on access to charger)

---

## Estimated Total Time

| Category | Cases | Est. Time |
|----------|-------|-----------|
| A - Speed | 6 | 25 min |
| B - Accel/Brake | 7 | 20 min |
| C - Ignition | 4 | 10 min |
| D - Steering | 4 | 10 min |
| E - Climate | 5 | 12 min |
| F - Lights | 7 | 8 min |
| G - Battery | 4 | 30-60 min |
| H - Drive Modes | 7 | 15 min |
| **Total** | **44 cases** | **~2.5-3 hours** |


---

## Annotation Template (Copy for Each Session)

```
SESSION: ____
DATE: ____
WEATHER: ____ C, ____
SOC START: ____%
SOC END: ____%
ODOMETER: ____ km

TIMESTAMP | ACTION                  | NOTES
----------|-------------------------|------------------
HH:MM:SS  | Start logging           |
HH:MM:SS  | Case A1 - standstill    |
HH:MM:SS  | Case A2 - 30 km/h      | cruise control on
HH:MM:SS  | Case A3 - 50 km/h      | cruise control on
...       | ...                     | ...
HH:MM:SS  | Stop logging            |
```
