"""
Generate tomorrow's testing strategy PDF for VW ID Buzz stationary testing.
Step-by-step plan for CANedge2 battery data extraction.

Run: cd src && python -X utf8 generate_strategy_pdf.py
"""

from fpdf import FPDF
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "10_Literature"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class StrategyPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(120, 120, 120)
            self.cell(0, 5, "VW ID Buzz - Stationary Testing Strategy - April 2026", align="C")
            self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section(self, title):
        self.ln(3)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, title)
        self.ln(10)
        self.set_draw_color(0, 51, 102)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def subsection(self, title):
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 7, title)
        self.ln(8)

    def body(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, items):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        for item in items:
            self.cell(0, 5.5, f"- {item}")
            self.ln()
        self.ln(2)

    def checkbox(self, items):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        for item in items:
            self.cell(0, 5.5, f"[ ] {item}")
            self.ln()
        self.ln(2)

    def step_box(self, number, title, content):
        y = self.get_y()
        if y > 245:
            self.add_page()
            y = self.get_y()

        self.set_fill_color(0, 51, 102)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 12)
        self.cell(12, 8, f" {number}", fill=True)
        self.set_fill_color(230, 240, 250)
        self.set_text_color(0, 51, 102)
        self.cell(0, 8, f"  {title}", fill=True)
        self.ln(10)
        self.set_text_color(30, 30, 30)
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5.5, content)
        self.ln(4)

    def result_box(self, if_text, then_text, color=(220, 240, 220)):
        self.set_fill_color(*color)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(0, 80, 0)
        self.cell(0, 6, f"  IF: {if_text}", fill=True)
        self.ln(6)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 30, 30)
        self.cell(0, 6, f"  THEN: {then_text}", fill=True)
        self.ln(8)

    def fail_box(self, if_text, then_text):
        self.result_box(if_text, then_text, color=(255, 230, 230))

    def code(self, text):
        self.set_font("Courier", "", 8.5)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(30, 30, 30)
        for line in text.strip().split("\n"):
            self.cell(0, 4.5, f"  {line}", fill=True)
            self.ln(4.5)
        self.ln(3)

    def table(self, headers, rows, col_widths=None):
        if col_widths is None:
            col_widths = [190 / len(headers)] * len(headers)
        self.set_font("Helvetica", "B", 8.5)
        self.set_fill_color(0, 51, 102)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 6.5, h, border=1, fill=True, align="C")
        self.ln()
        self.set_font("Helvetica", "", 8)
        self.set_text_color(30, 30, 30)
        fill = False
        for row in rows:
            self.set_fill_color(245, 245, 245) if fill else self.set_fill_color(255, 255, 255)
            for i, cell in enumerate(row):
                self.cell(col_widths[i], 6, str(cell), border=1, fill=True)
            self.ln()
            fill = not fill
        self.ln(3)


def build_pdf():
    pdf = StrategyPDF()
    pdf.alias_nb_pages()

    # TITLE PAGE
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(0, 51, 102)
    pdf.multi_cell(0, 13, "Tomorrow's Testing Strategy", align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(0, 10, "VW ID Buzz - Stationary Battery Data Extraction\nUsing CANedge2", align="C")
    pdf.ln(15)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, "Date: April 10, 2026", align="C")
    pdf.ln(6)
    pdf.cell(0, 8, "Condition: Stationary (car ON/OFF, no driving)", align="C")
    pdf.ln(6)
    pdf.cell(0, 8, "Goal: Extract battery parameters via UDS diagnostic protocol", align="C")

    # OVERVIEW
    pdf.add_page()
    pdf.section("Mission Overview")

    pdf.body(
        "Tomorrow you will be testing on the VW ID Buzz in stationary condition. The primary "
        "objective is to successfully extract battery data from the BMS (Battery Management System) "
        "using UDS diagnostic requests through the CANedge2."
    )

    pdf.subsection("What You Already Know")
    pdf.bullet([
        "Passive CAN recording gives only 7 CAN IDs (0x065-0x06F) - network management, not battery data",
        "Battery data requires UDS requests (service 0x22) to BMS ECU address 0x7B",
        "Request CAN ID: 0x17FC007B (29-bit extended)",
        "Response CAN ID: 0x17FE007B (29-bit extended)",
        "145 battery DIDs available (108 cell voltages, 18 temps, 19 system-level)",
        "CAN bus speed: 500 kbps",
    ])

    pdf.subsection("What You Need to Find Out Tomorrow")
    pdf.bullet([
        "Can CANedge2 transmit 29-bit extended CAN frames?",
        "Will the BMS respond to UDS requests through the OBD-II port?",
        "Do you need to open an extended diagnostic session first?",
        "Can CANedge2 handle ISO-TP flow control for multi-frame responses?",
        "How many PIDs can you poll per second without errors?",
    ])

    # EQUIPMENT CHECKLIST
    pdf.section("Equipment Checklist")

    pdf.checkbox([
        "CANedge2 device (fully charged / powered)",
        "OBD-II cable for CANedge2",
        "Laptop with WiFi (to access CANedge2 config at 192.168.65.1)",
        "SD card in CANedge2 (formatted, enough space)",
        "VW ID Buzz key fob",
        "This strategy document (printed or on phone)",
        "Notebook for writing down observations",
        "Phone camera (to photograph instrument cluster for reference values)",
        "USB cable (to download MF4 files from CANedge2 SD card)",
    ])

    # PHASE 1
    pdf.add_page()
    pdf.section("Phase 1: CANedge2 Configuration (Before Driving to Car)")

    pdf.body(
        "Do this at home/office before you go to the car. You need WiFi access to the CANedge2 "
        "to configure the transmit list."
    )

    pdf.step_box("1", "Access CANedge2 Configuration",
        "Connect to CANedge2's WiFi access point. Open browser, go to 192.168.65.1. "
        "Navigate to CAN channel configuration.")

    pdf.step_box("2", "Check Extended ID Support",
        "In the transmit list settings, check if there is an option for 'Extended Frame' or "
        "'29-bit ID'. Look for an IDE checkbox or a field that accepts IDs longer than 0x7FF. "
        "Document what you find.")

    pdf.result_box(
        "Extended ID is supported",
        "Continue to Step 3 - configure the first test request"
    )
    pdf.fail_box(
        "Extended ID is NOT supported",
        "STOP. Skip to Phase 4 (Fallback Strategy). CANedge2 transmit list only works with 11-bit IDs."
    )

    pdf.step_box("3", "Configure Test Request - Diagnostic Session",
        "Add the first transmit entry. This opens an extended diagnostic session with the BMS:\n\n"
        "CAN ID: 0x17FC007B (extended, 29-bit)\n"
        "Data: 02 10 03 55 55 55 55 55\n"
        "Interval: 2000 ms (every 2 seconds)\n"
        "Enabled: YES\n\n"
        "This sends: Service 0x10, Sub-function 0x03 (Extended Diagnostic Session)")

    pdf.step_box("4", "Configure Test Request - SOC",
        "Add a second transmit entry to request the State of Charge:\n\n"
        "CAN ID: 0x17FC007B (extended, 29-bit)\n"
        "Data: 03 22 02 8C 55 55 55 55\n"
        "Interval: 1000 ms (every 1 second)\n"
        "Enabled: YES\n\n"
        "This sends: Service 0x22, DID 0x028C (SOC)")

    pdf.step_box("5", "Configure Logging",
        "Make sure CAN logging is enabled for BOTH standard and extended frames:\n\n"
        "- Channel: CAN (whichever the OBD-II port uses)\n"
        "- Bit rate: 500 kbps\n"
        "- Accept ALL CAN IDs (no filters - you want to see everything)\n"
        "- Log format: MF4\n"
        "- Include extended frames: YES")

    pdf.step_box("6", "Save Configuration",
        "Save the configuration to the CANedge2. Verify it is stored correctly by re-opening "
        "the config page and checking the transmit list entries are there.")

    # PHASE 2
    pdf.add_page()
    pdf.section("Phase 2: First Test at the Car (The Critical Moment)")

    pdf.body(
        "This is the most important part. You will plug in the CANedge2 and see if the BMS responds. "
        "Work through these steps carefully and document every result."
    )

    pdf.step_box("1", "Connect CANedge2 to OBD-II Port",
        "Plug the CANedge2 into the VW ID Buzz OBD-II port (under the dashboard, driver side). "
        "Make sure the connection is solid. The CANedge2 should power on.")

    pdf.step_box("2", "Turn Ignition ON (Do NOT Start the Car Yet)",
        "Press the start button WITHOUT pressing the brake pedal. This turns on the electronics "
        "without engaging the motor. The instrument cluster should light up. This puts all ECUs "
        "in active mode so they can respond to diagnostic requests.")

    pdf.step_box("3", "Wait 10 Seconds",
        "Let the CANedge2 start logging and sending its first transmit list entries. "
        "The BMS needs a moment to fully initialize.")

    pdf.step_box("4", "Record for 2 Minutes (Test 1: Ignition ON, Standstill)",
        "Just let it run. The CANedge2 is simultaneously:\n"
        "- Sending diagnostic session request every 2 seconds\n"
        "- Sending SOC request every 1 second\n"
        "- Logging all CAN traffic (requests AND any responses)\n\n"
        "While waiting, photograph the instrument cluster SOC display for reference.")

    pdf.step_box("5", "Turn Car Fully ON (Press Brake + Start Button)",
        "Now fully start the car (Ready-to-Drive mode). The motor is active but the car "
        "stays in Park. This might change which ECUs are active and how the BMS responds.")

    pdf.step_box("6", "Record for 2 More Minutes (Test 2: Ready-to-Drive, Standstill)",
        "Same recording - let CANedge2 continue logging. The BMS behavior might differ "
        "between ignition-on and ready-to-drive modes.")

    pdf.step_box("7", "Turn Car OFF",
        "Turn off the car. Let the CANedge2 log for another 30 seconds to capture "
        "shutdown behavior, then unplug it.")

    pdf.step_box("8", "Extract the MF4 Log Files",
        "Remove the SD card from CANedge2 (or connect via USB) and copy all MF4 files "
        "to your laptop. Put them in data/mf4/ in your project folder.")

    # PHASE 3
    pdf.add_page()
    pdf.section("Phase 3: Analyze Results (Back at Your Computer)")

    pdf.step_box("1", "Load MF4 Files in CAN Analyzer",
        "Open the Rust CAN Analyzer (can_analyzer/target/release/can-analyzer.exe) or "
        "python CAN analyzer. Load the new MF4 files.")

    pdf.step_box("2", "Check for Extended CAN IDs",
        "Look in the sniffer/frame table for CAN IDs with 29-bit extended flag (IDE=1). "
        "Specifically look for:\n\n"
        "- 0x17FC007B (your requests - confirms CANedge2 is transmitting)\n"
        "- 0x17FE007B (BMS responses - THIS IS WHAT YOU WANT)\n\n"
        "If you only see your requests but no responses, the BMS is not answering.")

    pdf.subsection("Interpreting Results")

    pdf.result_box(
        "You see 0x17FE007B responses",
        "SUCCESS! The BMS is responding. Decode the response data (see decoding table below)."
    )

    pdf.body("If the BMS responds, check the response pattern:")

    pdf.table(
        ["Response Data Pattern", "Meaning", "Next Step"],
        [
            ["02 50 03 ...", "Diag session opened OK", "SOC request should work too"],
            ["04 62 02 8C XX ...", "SOC value returned", "XX = raw SOC, decode: XX/2.5 = %"],
            ["03 7F 10 22 ...", "Diag session rejected (conditions)", "Try with car fully ON"],
            ["03 7F 22 31 ...", "DID not found", "Try different DID (use PID list)"],
            ["03 7F 22 33 ...", "Security access needed", "Need security unlock first"],
            ["03 7F 22 22 ...", "Need diag session first", "Session request not working"],
        ],
        [40, 60, 85]
    )

    pdf.fail_box(
        "You see 0x17FC007B (your requests) but NO 0x17FE007B (no responses)",
        "The gateway might be blocking, or the BMS doesn't accept the request. Go to Phase 4."
    )

    pdf.fail_box(
        "You see NO extended CAN IDs at all",
        "The CANedge2 is not configured for extended frames, or the transmit list didn't work. "
        "Go back and check the configuration."
    )

    # PHASE 4 - FALLBACK
    pdf.add_page()
    pdf.section("Phase 4: Fallback Strategies (If Phase 2 Fails)")

    pdf.subsection("Fallback A: Try Different Diagnostic Sessions")

    pdf.body(
        "The BMS might need a specific session type or sequence. Try these variations "
        "by modifying the CANedge2 transmit list:"
    )

    pdf.table(
        ["What to Try", "Request Data", "Why"],
        [
            ["Default Session", "02 10 01 55 55 55 55 55", "Some DIDs work in default session"],
            ["TesterPresent", "02 3E 00 55 55 55 55 55", "Keep session alive - send every 2s"],
            ["Just SOC (no session)", "03 22 02 8C 55 55 55 55", "Maybe session not needed for basic DIDs"],
            ["Car Mode DID", "03 22 74 48 55 55 55 55", "Simple DID that should always work"],
        ],
        [45, 55, 85]
    )

    pdf.subsection("Fallback B: Use OBDEleven or VCDS as Sender")

    pdf.body(
        "If the CANedge2 can't send extended frames or the gateway blocks them, use a proper "
        "diagnostic tool as the sender while CANedge2 only logs:"
    )

    pdf.bullet([
        "Get a Y-splitter OBD-II cable (or use two OBD ports if available)",
        "Connect diagnostic tool (OBDEleven/VCDS) to one port",
        "Connect CANedge2 to the other port (logging only, no transmit)",
        "Use the diagnostic tool to request battery data",
        "CANedge2 captures both requests and responses passively",
        "This is Strategy B from Data_Collection_Strategy.md",
    ])

    pdf.subsection("Fallback C: Passive Recording with More Scenarios")

    pdf.body(
        "Even without UDS, capture passive CAN data under different conditions "
        "and look for battery-correlated signals:"
    )

    pdf.table(
        ["Test Scenario", "Duration", "What to Watch For"],
        [
            ["Car OFF -> ON", "2 min", "Wake-up sequence, initialization values"],
            ["Steady standstill (ON)", "5 min", "Periodic broadcast values, slow-changing temps"],
            ["AC ON / AC OFF", "2 min each", "New CAN IDs appearing, value changes"],
            ["Lights ON/OFF", "1 min each", "Distinguish electrical load vs battery signals"],
            ["Car ON -> OFF", "2 min", "Shutdown sequence, final values"],
        ],
        [50, 25, 110]
    )

    pdf.subsection("Fallback D: Check CANedge2 Second CAN Channel")

    pdf.body(
        "The CANedge2 has TWO CAN channels. Some OBD-II ports expose multiple CAN buses "
        "on different pins. Try logging on both channels simultaneously - the second channel "
        "might have different CAN IDs including battery-related broadcast messages."
    )

    # WHAT TO RECORD
    pdf.add_page()
    pdf.section("What to Document During Testing")

    pdf.body("For each test, write down:")

    pdf.checkbox([
        "Test number and timestamp (e.g., 'Test 1 - 10:30 - Ignition ON')",
        "Car state (OFF / Ignition ON / Ready-to-Drive)",
        "SOC shown on instrument cluster (e.g., '78%')",
        "Any error messages on the dashboard",
        "CANedge2 LED status (blinking = logging, solid = error)",
        "Air temperature (for reference against CAN temperature signals)",
        "Whether AC/heating was on or off",
        "Any unusual behavior",
    ])

    pdf.section("Priority PIDs for Tomorrow")

    pdf.body(
        "If the CANedge2 transmit list works, these are the most important PIDs to configure "
        "(in priority order). Start with just 2-3 and add more if everything works."
    )

    pdf.table(
        ["Priority", "Parameter", "DID", "Request Data", "Response Decode"],
        [
            ["1", "Diag Session", "-", "02 10 03 55 55 55 55 55", "Expect: 02 50 03"],
            ["2", "SOC (BMS)", "028C", "03 22 02 8C 55 55 55 55", "XX / 2.5 = %"],
            ["3", "HV Voltage", "1E3B", "03 22 1E 3B 55 55 55 55", "(XX*256+YY)*factor = V"],
            ["4", "HV Current", "1E3D", "03 22 1E 3D 55 55 55 55", "(XX*256+YY)*factor = A"],
            ["5", "Battery Temp", "2A0B", "03 22 2A 0B 55 55 55 55", "XX - 40 = C (estimate)"],
            ["6", "Car Mode", "7448", "03 22 74 48 55 55 55 55", "0=standby,1=drive,4=AC chg"],
            ["7", "Cell 1 Voltage", "1E40", "03 22 1E 40 55 55 55 55", "(XX*256+YY)/1000+1 = V"],
            ["8", "Max Temp", "1E0E", "03 22 1E 0E 55 55 55 55", "XX - 40 = C (estimate)"],
            ["9", "Pump Duty", "743B", "03 22 74 3B 55 55 55 55", "XX = %"],
        ],
        [18, 30, 18, 58, 60]
    )

    pdf.section("Quick Decision Flowchart")

    pdf.body("Follow this logic after each attempt:\n")

    pdf.code(
        "CANedge2 config supports extended IDs?\n"
        "  |-- NO  --> Use diagnostic tool as sender (Fallback B)\n"
        "  |-- YES --> Send diag session (02 10 03)\n"
        "               |\n"
        "               Response 02 50 03?\n"
        "               |-- YES --> Send SOC request (03 22 02 8C)\n"
        "               |           |\n"
        "               |           Response 04 62 02 8C XX?\n"
        "               |           |-- YES --> DONE! Add more PIDs\n"
        "               |           |-- NRC 0x33 --> Need security access\n"
        "               |           |-- NRC 0x31 --> Wrong DID, try another\n"
        "               |           |-- No response --> Gateway blocking\n"
        "               |\n"
        "               |-- NRC 0x22 --> Try with car fully ON\n"
        "               |-- No response at all --> Check CAN bus speed (500k)\n"
        "               |                          Check OBD pin assignment\n"
        "               |                          Try Channel 2"
    )

    # SAVE
    output_path = OUTPUT_DIR / "Testing_Strategy_April10.pdf"
    pdf.output(str(output_path))
    print(f"PDF saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    build_pdf()
