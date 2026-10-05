# Identification and Interpretation of BMS Signals Through CAN Bus Reverse Engineering on the VW ID. Buzz

Bachelor thesis, B.Eng. Electrical Engineering and Electromobility, Technische Hochschule Ingolstadt (2026).
Author: Muhamad Alif Izzuwan Bin Ibrahim.

**Read the thesis:** [`50_Thesis/latex/thesis.pdf`](50_Thesis/latex/thesis.pdf) (62 pages, built from the sources in the same folder).

## In one paragraph

On the Volkswagen MEB platform the battery-management CAN frames never reach the diagnostic connector: a central gateway keeps the powertrain networks private. This work therefore reads the traction-battery state of a VW ID. Buzz **actively**, by sending UDS *ReadDataByIdentifier* (0x22) requests from a **CANedge2** logger on the OBD-II port, so requests and responses are recorded on one hardware time base without a second tester. A public identifier list for the related ID.3 is treated as an unverified hypothesis and tested against the vehicle.

| Result | |
|---|---|
| Identifiers requested per cycle | 60, across 4 ECUs |
| Positive single-frame responses | 52, of which 49 carried a usable value |
| Truncated to the first frame | 6 (the logger's transmit engine has no ISO-TP flow control) |
| Never answered | 2 |
| Pack voltage | 373.25 to 373.75 V |
| Cell voltages (28 sampled) | 3.888 to 3.890 V, inter-cell spread 2.8 mV |
| Pack temperatures | 16.0 to 16.4 °C, consistent over 3 sessions |

Beyond the source list: the raw code `0x0FFE` is a reserved *not-available* marker of unpopulated cell slots, the cell-extreme identifiers carry the cell voltage scaled by 1/4096, and the pack exposes exactly **96** cell-voltage channels. Limits: all recordings were taken drive-ready but stationary, so current- and power-related identifiers stayed at idle.

## Repository layout

```
00_Organization/        topic description, weekly progress tracker
10_Literature/          working notes: CAN reading guide, UDS process, project overview
20_Hardware/
  CANedge/              CANedge2 device configurations (transmit lists for UDS requests) + archive
  can_analyzer/         Rust tool for fast inspection of the CAN logs
30_Software/            Python: MF4 reader, UDS battery decoder, transmit-config generator, BMS app
40_Experiments/
  data/                 PID list, converted logs, SD-card dump metadata
  plots/                decoded signals and analysis figures
50_Thesis/
  latex/                the final thesis: thesis.tex, references.bib, selected_signals.tex, figures/
  OPUS_abstract.txt     abstract as submitted to the university repository
CHANGELOG.md            what was done when
```

## Build the thesis

```bash
cd 50_Thesis/latex
pdflatex thesis && bibtex thesis && pdflatex thesis && pdflatex thesis
```

Needs a TeX distribution with KOMA-Script, EB Garamond and `IEEEtran` (MiKTeX or TeX Live).

## Run the decoder

```bash
pip install -r requirements.txt
python 30_Software/uds_battery_decoder.py      # decodes the UDS exchanges in 40_Experiments/data
```

Raw MF4 recordings and the vendor tools in `20_Hardware/tools/` are not in the repository (size); see `.gitignore`.
