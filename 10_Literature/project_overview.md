# Project Overview — Quick Reference

## Thesis

**Title:** "Inside the Battery: Entschluesselung von Batteriedaten ueber den CAN-Bus"
**University:** Technische Hochschule Ingolstadt (THI)
**Institute:** CARISSMA (Institute of Electric, Connected and Secure Mobility)
**Supervisors:** Markus Gregor, Prof. Dr. Hans-Georg Schweiger
**Duration:** 12 weeks, starting March 2026
**Focus:** Battery parameters (SOC, voltage, current, cell voltages, temperatures)

## The Task (from the assignment)

- Record and analyse CAN bus signals from the VW ID Buzz during driving and charging
- Reverse engineer manufacturer-specific CAN messages
- **Map raw CAN data to battery parameters** (cell voltage, temperature, SOC, current)
- Develop tools for automated data storage and visualisation
- Document and prepare the decoded signals for further research

## Thesis Focus (Updated per Lecturer Feedback)

The emphasis is on **battery data**, not general vehicle parameters. The thesis title says "Batteriedaten" and CARISSMA's research is focused on EV battery systems. Vehicle-level signals (speed, steering, lights) are only relevant as supporting context for understanding battery behaviour (e.g., correlating current draw with driving speed).

## Two-Track Data Collection

1. **UDS Diagnostic Requests (Primary):** Send UDS ReadDataByIdentifier requests to the BMS ECU (CAN ID 0x17FC007B) to get SOC, pack voltage, current, cell voltages, temperatures. These use 29-bit extended CAN IDs.

2. **Passive CAN Analysis (Secondary):** Analyse the 7 CAN IDs (0x065-0x06F) already captured. Some temperature signals may be battery-related. RE methodology still relevant for the thesis.

## Vehicle & Hardware

- **Vehicle:** Volkswagen ID Buzz (MEB platform, electric)
- **Data Logger:** CANedge2 (CSS Electronics)
- **BMS ECU Address:** Request 0x17FC007B / Response 0x17FE007B
- **UDS PIDs Available:** 145 battery-related (108 cell voltages, 18 temp points, 19 system-level)

## Current Status (Week 3)

- Initial passive CAN data analysed (7 CAN IDs, 8 signals decoded)
- Tools built (Python + Rust CAN analyzers)
- **This week:** Testing whether CANedge2 can send UDS requests to BMS
- Key question: Can I collect battery data directly via OBD, or do I need to send UDS?

## Contact

- Markus Gregor — Markus.Gregor@thi.de
- Prof. Dr. Hans-Georg Schweiger — Hans-Georg.Schweiger@thi.de
