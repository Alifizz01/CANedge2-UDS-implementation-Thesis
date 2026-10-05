# Source dossier — factual claims in the thesis

Compiled 30.08.2026. Every source below was opened and checked; the quoted wording is
what the source actually says. The BibTeX keys already exist in `bibliography_CORRECTED.bib`
(each entry carries a `%` comment recording what was verified and when).

**Status legend**

| | meaning |
|---|---|
| ✅ | source verified, citation ready, claim matches the source |
| ⚠️ | source verified, but the thesis wording needs adjusting to match it |
| ❌ | no credible source found — the claim must be softened, or rest on own measurement |

---

## 1. Standards facts (no search needed — these are already in the bibliography)

These are all "the protocol works like this" statements. The primary source is the standard
itself; nothing else is required or expected by a reviewer.

| Claim | Section | Cite | Status |
|---|---|---|---|
| Differential CAN-H/CAN-L pair, 120 Ω termination, dominant/recessive levels | 2.1.1 | `iso11898`, `iso11898_2` | ✅ |
| Frame fields: SOF, identifier, control/DLC, data ≤ 8 byte, 15-bit CRC + delimiter, ACK, EOF | 2.1.2 | `iso11898` | ✅ *(inserted)* |
| Bit stuffing after five equal bits; CAN 2.0A 11-bit vs 2.0B 29-bit | 2.1.2 | `iso11898` | ✅ |
| CSMA/CR, non-destructive arbitration, lower ID wins, priority by identifier | 2.1.3 | `iso11898` | ✅ *(inserted)* |
| Classical CAN 8 byte / CAN-FD up to 64 byte, dual bit rate | 2.1.4 | `iso11898` | ✅ |
| ISO-TP frame types SF/FF/CF/FC, PCI, block size, `STmin` | 2.2.2 | `iso15765` | ✅ |
| UDS services, positive response = SID + 0x40, 0x7F + NRC, NRC 0x31/0x33, session control, TesterPresent, S3 timeout | 2.2.3 | `iso14229`, `iso14229_2` | ✅ |
| DID ranges: manufacturer-specific 0x0100–0xA5FF, OBD-mapped 0xF800–0xF8FF | 2.2.3 | `iso14229` | ✅ |
| OBD-II pinout: pin 6 CAN-H, pin 14 CAN-L, pin 4/5 ground, pin 16 +12 V | 2.2.1, 3.2.2 | `saej1962` | ✅ |
| **Functional request ID 0x7DF; 500 kbit/s and 11-/29-bit addressing at the connector** | 2.2.4 | **`iso15765_4` (NEW)** | ✅ — this was uncited; ISO 15765-4:2021 is exactly the standard that defines it |
| EOBD mandatory in the EU (petrol 2000/2001, diesel 2003/2004) | 2.2.1 | `eudir9869`, `eudir20011` | ✅ |

---

## 2. Volkswagen / MEB facts

| Claim | Section | Source found | Status |
|---|---|---|---|
| MEB is VW Group's dedicated BEV platform; ID.3 was the first model, series production from **4 November 2019** in Zwickau | 2.3 | `vw_id3_sop` — VW Newsroom: *"The starting signal for Zwickau into the all-electric era was given on 4 November 2019 with the official start of production of the ID.3 … the Volkswagen Group's first model based on the modular electric drive matrix (MEB)"* | ✅ *(inserted)* |
| The platform is shared across the ID family / several Group brands | 2.3 | `vw_id3_sop` (six MEB models built at Zwickau across VW, Audi, Cupra; 2.3 million MEB vehicles delivered), `vw_meb` | ✅ *(inserted)* |
| ID. Buzz: **77 kWh net / 82 kWh gross**, **twelve modules**, motor **in the rear axle**, **150 kW (204 PS)** | 3.1 | **`vw_idbuzz_drive` (NEW)** — VW Newsroom 09/07/22, verbatim | ✅ |
| The 77 kWh MEB pack = **12 modules × 24 cells = 288 cells** | 2.3 / 4.2.5 | **`vw_meb_battery` (NEW)** — VW Newsroom 05/10/21: *"each compartment holds a battery module comprising 24 cells"* | ✅ — see §5, this is your external proof of the 96 |
| Cells are **pouch** cells, **NMC** chemistry, **78 Ah** nominal | 2.4.1, 3.1 | **`guenter2022` (NEW)** — J. Electrochem. Soc. 169(3):030515: teardown of *"a large-format pouch cell with a nominal capacity of 78 Ah from the Volkswagen ID.3"*, cathode *"LiNi₀.₆₅Mn₀.₂Co₀.₁₅O₂ in between NMC622 and NMC811"* | ✅ peer-reviewed, and it is *this exact cell* |
| MEB is organised around domain controllers connected to a **central gateway** | 2.3 | **`continental_icas1` (NEW)** — Continental, 12.11.2019: *"Volkswagen uses the server as an in-car application server (ICAS1) for ID. vehicle models based on the modular electric drive matrix (MEB)"*, *"The ICAS1 covers the previous gateway functions as well as comprehensive functions from the body control domain."* | ⚠️ confirms gateway + body domain. Your list of five domains (drive, chassis, comfort, infotainment, charging) is **not** confirmed — soften to "a small number of domain controllers" |
| The gateway does not forward internal battery broadcasts to the OBD-II connector | 2.3, 3.4 | `iso15765_4` (the connector is specified for diagnostics), `continental_icas1`, `checkoway2011` (NEW, OBD-II as external interface) **+ your own Section 4.1.1** (14 921 broadcast frames on six identifiers, none battery-related) | ✅ — but lead with your own measurement; it is the strongest evidence |
| MEB designed from the ground up around the battery, skateboard chassis, flat pack between the axles | 2.3 | `vw_meb`, `wassiliadis2022` (NEW, peer-reviewed ID.3 system analysis) | ✅ |
| Powertrain-level analysis of an MEB vehicle exists in the literature | 2.3 / 5.1 | **`wassiliadis2022` (NEW)** — eTransportation 12:100167, CC-BY, 17 authors (TUM) | ✅ useful for Chapter 5 comparison |

---

## 3. Battery / BMS facts

| Claim | Section | Cite | Status |
|---|---|---|---|
| Traction battery is the most expensive subsystem of a BEV | 1.1 | `koenig2021` | ✅ *(inserted)* |
| …and the most safety-critical (thermal runaway) | 1.1 | `feng2018` | ✅ *(inserted)* |
| Nominal cell voltage depends on chemistry (NMC 3.6–3.7 V, LFP ≈ 3.2 V) | 2.4.1 | `nitta2015`, and now also `guenter2022` for *this* cell | ✅ *(inserted)* |
| Pack = several hundred cells in modules, managed by an electronic hierarchy | 2.4 | `plett2015` | ✅ *(inserted)* |
| Per-cell measurement is required because the weakest cell limits the string | 2.4.1 | `plett2015`, `plett2016` | ✅ *(inserted)* |
| BMS duties: monitoring, SOC/SOH, contactors, balancing, power limits | 2.4.2 | `plett2015`, `plett2016` | ✅ ready to insert |
| SOC estimated by coulomb counting + OCV + Kalman-type filters | 2.4.2 | `rivera2021soc` — **already in your .bib but never cited** | ⚠️ insert the citation |

---

## 4. Corrections the sources force

**a) "roughly 400 V nominal" (Sections 2.3 and 3.1) is not the nominal voltage.**
400 V is the *system class* (as opposed to 800 V). The published nominal of this pack is
**≈ 350 V**, and that is what your own data supports:

```
96 series groups × 3.6 V nominal cell   =  345.6 V   nominal
your measurement at 72–73 % SOC          =  373.4 V   (96 × 3.888 V)
96 × 4.2 V (full)                        =  403.2 V   max
```
Suggested wording: *"a nominal pack voltage of about 350 V (96 series groups), i.e. a
400-volt-class system"*. As written, a reader who checks 373.4 V against "400 V nominal"
sees a pack that looks depleted, which is the opposite of the truth.

**b) "it is not published at the detail needed here" (Section 3.1) is half right.**
The *series* count is not published — true. But the *total* cell count is (288), and it
constrains the answer. See §5.

**c) "No academic study was found that reverse engineers battery data from an MEB
vehicle" (Section 2.5) is a negative claim.** ❌ It cannot be sourced, only evidenced by
describing the search. Add one sentence: which databases (IEEE Xplore, ACM DL, Scopus,
Google Scholar), which terms, and the date. Then it is defensible.

---

## 5. The fully-sourced chain behind the 96 cell groups

Every number here except the 96 comes from a published source; the 96 is your contribution.

```
VW (vw_meb_battery)     12 modules × 24 cells        = 288 cells
your measurement                                     =  96 groups in series
                        288 / 96                     =   3 cells in parallel   <- integer
Günter & Wassiliadis    one cell = 78 Ah, NMC pouch
                        3 × 78 Ah                    = 234 Ah pack
                        96 × 3.6 V                   = 345.6 V nominal
                        345.6 V × 234 Ah             =  80.9 kWh
VW (vw_idbuzz_drive)    stated gross energy          =  82 kWh          <- agrees to 1.3 %
```

Two independent closures: the cell count divides exactly (288/96 = 3), and the energy
computed from published cell data lands on VW's published pack energy. Had you concluded
108 groups instead of 96, 288/108 = 2.67 — impossible.

This is the answer to "how do I back it up without a measurement": you do not verify the
decoding against an instrument, you verify it against **published pack architecture plus
internal consistency**, and you say so explicitly.

---

## 6. Sources added to `bibliography_CORRECTED.bib` (all verified 30.08.2026)

| Key | Source | Type |
|---|---|---|
| `iso15765_4` | ISO 15765-4:2021, DoCAN Part 4 — requirements for emissions-related systems | standard |
| `guenter2022` | Günter & Wassiliadis, *J. Electrochem. Soc.* 169(3):030515, 2022, doi 10.1149/1945-7111/ac4e11 | peer-reviewed |
| `wassiliadis2022` | Wassiliadis et al., *eTransportation* 12:100167, 2022, doi 10.1016/j.etran.2022.100167 (CC-BY) | peer-reviewed |
| `vw_idbuzz_drive` | VW Newsroom, "Electric drive system — Agile, powerful and efficient", 09/07/2022 | manufacturer |
| `vw_meb_battery` | VW Newsroom, "Long range and rapid charging: the battery system…", 05/10/2021 | manufacturer |
| `continental_icas1` | Continental AG press release, 12/11/2019 | supplier |
| `checkoway2011` | Checkoway et al., USENIX Security 2011 | peer-reviewed |
| `koenig2021` | König et al., *World Electric Vehicle Journal* 12(1):21, 2021 | peer-reviewed |
| `feng2018` | Feng et al., *Energy Storage Materials* 10:246–267, 2018 | peer-reviewed |
| `nitta2015` | Nitta et al., *Materials Today* 18(5):252–264, 2015 | peer-reviewed |
| `vw_ssp269` | VW Selbststudienprogramm 269, Wolfsburg, 2003 | manufacturer |
| `vw_id3_sop` | VW Newsroom, Zwickau one-millionth EV, 30/04/2025 | manufacturer |

---

## 7. Still unsourced — decide what to do

| Claim | Problem | Suggestion |
|---|---|---|
| VW comfort CAN at 100 kbit/s | `vw_ssp269` is from 2003; it is solid for classic VW buses, not proven for MEB-era cars | keep the citation, add "traditionally" or restrict the sentence to the powertrain bus, which your own log confirms at 500 kbit/s |
| Diagnostic addresses 0x17FC00xx / 0x17FE00xx and the ECU assignment | not published by VW | already handled correctly: attributed to `vwmebpidlist` and confirmed by your own responses |
| "ID. Software 4.x" | an observation from the vehicle, no public source | state it as read from the vehicle |
| Five MEB domains (drive, chassis, comfort, infotainment, charging) | only gateway + body confirmed by Continental | soften, or cite per-domain sources |
| Sources behind the paywall (ScienceDirect, Springer) | blocked by bot protection, could not read full text | metadata verified via Crossref/IOP; read the full texts through the THI library before citing specific numbers from them |
