"""
Generate a comprehensive CAN Bus guide PDF for the Bachelor Thesis project.
Covers: CAN fundamentals, CAN ID, payload, priority, PGN/SPN, CAN 2.0A vs 2.0B,
UDS protocol, ISO-TP, and battery data extraction strategy for VW ID Buzz.

Run: cd src && python -X utf8 generate_can_guide_pdf.py
"""

from fpdf import FPDF
from pathlib import Path
import textwrap

OUTPUT_DIR = Path(__file__).parent.parent / "10_Literature"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class CANGuidePDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(120, 120, 120)
            self.cell(0, 5, "CAN Bus Complete Guide - VW ID Buzz Battery Reverse Engineering", align="C")
            self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def title_page(self):
        self.add_page()
        self.ln(50)
        self.set_font("Helvetica", "B", 28)
        self.set_text_color(0, 51, 102)
        self.multi_cell(0, 14, "The Complete CAN Bus Guide", align="C")
        self.ln(5)
        self.set_font("Helvetica", "", 16)
        self.set_text_color(80, 80, 80)
        self.multi_cell(0, 10, "From Bits on the Wire to Battery Data\nin Your VW ID Buzz", align="C")
        self.ln(20)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "Bachelor Thesis - CAN Bus Reverse Engineering", align="C")
        self.ln(6)
        self.cell(0, 8, "THI / CARISSMA", align="C")
        self.ln(6)
        self.cell(0, 8, "April 2026", align="C")

    def chapter_title(self, number, title):
        self.add_page()
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(0, 51, 102)
        self.cell(0, 15, f"Chapter {number}", ln=True)
        self.set_font("Helvetica", "B", 18)
        self.cell(0, 12, title, ln=True)
        self.ln(4)
        # Underline
        self.set_draw_color(0, 51, 102)
        self.set_line_width(0.8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(8)

    def section_title(self, title):
        self.ln(4)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(0, 80, 140)
        self.cell(0, 10, title, ln=True)
        self.ln(2)

    def subsection_title(self, title):
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, title, ln=True)
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet_list(self, items):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        for item in items:
            x = self.get_x()
            self.cell(8, 5.5, "-")
            self.multi_cell(0, 5.5, item)
            self.set_x(x)
        self.ln(2)

    def key_value_block(self, pairs):
        """Display key-value pairs with bold keys."""
        for key, value in pairs:
            self.set_font("Helvetica", "B", 10)
            self.set_text_color(30, 30, 30)
            self.cell(0, 5.5, f"{key}: {value}")
            self.ln()
        self.ln(2)

    def code_block(self, text):
        self.set_font("Courier", "", 9)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(30, 30, 30)
        lines = text.strip().split("\n")
        for line in lines:
            self.cell(0, 5, f"  {line}", ln=True, fill=True)
        self.ln(3)

    def info_box(self, title, text):
        self.set_fill_color(230, 243, 255)
        self.set_draw_color(0, 100, 200)
        self.set_line_width(0.3)
        y_start = self.get_y()
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(0, 60, 120)
        self.cell(0, 7, f"  {title}", ln=True, fill=True)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5, f"  {text}", fill=True)
        self.ln(4)

    def warning_box(self, text):
        self.set_fill_color(255, 245, 230)
        self.set_draw_color(200, 150, 0)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(150, 100, 0)
        self.cell(0, 7, "  WARNING", ln=True, fill=True)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(80, 60, 0)
        self.multi_cell(0, 5, f"  {text}", fill=True)
        self.ln(4)

    def simple_table(self, headers, rows, col_widths=None):
        if col_widths is None:
            col_widths = [190 / len(headers)] * len(headers)

        # Header
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(0, 51, 102)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, border=1, fill=True, align="C")
        self.ln()

        # Rows
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(30, 30, 30)
        fill = False
        for row in rows:
            if self.get_y() > 260:
                self.add_page()
                # Repeat header
                self.set_font("Helvetica", "B", 9)
                self.set_fill_color(0, 51, 102)
                self.set_text_color(255, 255, 255)
                for i, h in enumerate(headers):
                    self.cell(col_widths[i], 7, h, border=1, fill=True, align="C")
                self.ln()
                self.set_font("Helvetica", "", 8.5)
                self.set_text_color(30, 30, 30)
                fill = False

            if fill:
                self.set_fill_color(245, 245, 245)
            else:
                self.set_fill_color(255, 255, 255)
            for i, cell in enumerate(row):
                self.cell(col_widths[i], 6.5, str(cell), border=1, fill=True)
            self.ln()
            fill = not fill
        self.ln(4)

    def diagram_can_frame(self):
        """Draw a CAN frame structure diagram."""
        y = self.get_y()
        x_start = 15

        fields = [
            ("SOF", 8, (200, 220, 240)),
            ("Arbitration\n(CAN ID)", 40, (180, 230, 180)),
            ("RTR", 8, (255, 230, 180)),
            ("CTRL", 12, (220, 200, 240)),
            ("DATA (Payload)\n0-8 bytes", 65, (180, 220, 255)),
            ("CRC", 20, (255, 220, 200)),
            ("ACK", 8, (220, 240, 220)),
            ("EOF", 12, (230, 230, 230)),
        ]

        # Draw boxes
        self.set_font("Helvetica", "", 7)
        self.set_text_color(30, 30, 30)
        x = x_start
        box_h = 22
        for label, width, color in fields:
            self.set_fill_color(*color)
            self.set_draw_color(100, 100, 100)
            self.rect(x, y, width, box_h, "DF")
            # Center text in box
            lines = label.split("\n")
            for j, line in enumerate(lines):
                tw = self.get_string_width(line)
                tx = x + (width - tw) / 2
                ty = y + 6 + j * 7
                self.set_xy(tx, ty)
                self.cell(tw, 5, line)
            x += width

        self.set_y(y + box_h + 8)

    def diagram_extended_frame(self):
        """Draw extended CAN frame with 29-bit ID."""
        y = self.get_y()
        x_start = 15

        fields = [
            ("SOF", 8, (200, 220, 240)),
            ("Base ID\n11-bit", 25, (180, 230, 180)),
            ("SRR\nIDE", 12, (255, 230, 180)),
            ("Extended ID\n18-bit", 30, (150, 210, 150)),
            ("RTR", 8, (255, 230, 180)),
            ("CTRL", 10, (220, 200, 240)),
            ("DATA\n0-8 bytes", 55, (180, 220, 255)),
            ("CRC", 18, (255, 220, 200)),
            ("ACK", 8, (220, 240, 220)),
            ("EOF", 10, (230, 230, 230)),
        ]

        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(30, 30, 30)
        x = x_start
        box_h = 22
        for label, width, color in fields:
            self.set_fill_color(*color)
            self.set_draw_color(100, 100, 100)
            self.rect(x, y, width, box_h, "DF")
            lines = label.split("\n")
            for j, line in enumerate(lines):
                tw = self.get_string_width(line)
                tx = x + (width - tw) / 2
                ty = y + 5 + j * 7
                self.set_xy(tx, ty)
                self.cell(tw, 5, line)
            x += width

        self.set_y(y + box_h + 8)


def build_pdf():
    pdf = CANGuidePDF()
    pdf.alias_nb_pages()

    # =========================================================================
    # TITLE PAGE
    # =========================================================================
    pdf.title_page()

    # =========================================================================
    # TABLE OF CONTENTS
    # =========================================================================
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 12, "Table of Contents", ln=True)
    pdf.ln(8)

    toc = [
        ("1", "What is CAN Bus?", "The basics - why CAN exists and how it works"),
        ("2", "The CAN Frame - Anatomy of a Message", "CAN ID, payload, DLC, CRC, and every field explained"),
        ("3", "CAN ID and Priority", "How arbitration works and why lower IDs win"),
        ("4", "Standard vs Extended CAN", "CAN 2.0A (11-bit) vs CAN 2.0B (29-bit)"),
        ("5", "The Payload - What the Data Means", "Raw bytes, signals, encoding, byte order"),
        ("6", "J1939: PGN and SPN", "Parameter Group Numbers and Suspect Parameter Numbers"),
        ("7", "Higher-Layer Protocols: UDS and ISO-TP", "Diagnostic communication over CAN"),
        ("8", "CAN in the VW ID Buzz (MEB Platform)", "Architecture, gateways, bus topology"),
        ("9", "Battery Data Over CAN", "What parameters exist and how to get them"),
        ("10", "Reverse Engineering Strategy", "From raw bytes to decoded battery signals"),
    ]

    pdf.set_font("Helvetica", "", 11)
    for num, title, desc in toc:
        pdf.set_text_color(0, 51, 102)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(12, 7, num)
        pdf.cell(80, 7, title)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 7, desc, ln=True)

    # =========================================================================
    # CHAPTER 1: What is CAN Bus?
    # =========================================================================
    pdf.chapter_title(1, "What is CAN Bus?")

    pdf.body_text(
        "CAN (Controller Area Network) is a communication protocol invented by Bosch in 1986. "
        "It was designed to let electronic control units (ECUs) inside a vehicle talk to each other "
        "without needing a central computer. Before CAN, every ECU needed its own dedicated wiring "
        "to every other ECU it needed to communicate with. With dozens of ECUs in a modern car, "
        "this meant hundreds of individual wires - heavy, expensive, and unreliable."
    )

    pdf.body_text(
        "CAN solved this by putting all ECUs on a shared two-wire bus. Any ECU can send a message, "
        "and every other ECU on the bus hears it. Think of it like a group chat: when one person sends "
        "a message, everyone sees it. Each ECU decides for itself whether the message is relevant."
    )

    pdf.section_title("Key Properties of CAN")

    pdf.bullet_list([
        "Two-wire bus: CAN-High and CAN-Low (differential signaling for noise immunity)",
        "Multi-master: Any node can transmit at any time (no central controller needed)",
        "Broadcast: Every node sees every message on the bus",
        "Message-based: Messages have IDs, not sender/receiver addresses",
        "Priority-based arbitration: When two nodes transmit simultaneously, the higher-priority message wins without data loss",
        "Error detection: Built-in CRC checks, error frames, and automatic retransmission",
        "Typical speeds: 125 kbps, 250 kbps, or 500 kbps (VW uses 500 kbps)",
    ])

    pdf.section_title("Why CAN Matters for Your Thesis")

    pdf.body_text(
        "The VW ID Buzz has dozens of ECUs communicating over multiple CAN buses. The Battery "
        "Management System (BMS) is one of these ECUs. It monitors every cell voltage, temperature "
        "sensor, and current measurement in the high-voltage battery pack. All this data travels "
        "over CAN - either as periodic broadcast messages, or as responses to diagnostic requests. "
        "Your job is to capture and decode these messages to understand the battery's state."
    )

    pdf.info_box("Real-World Analogy",
        "Imagine a room full of people (ECUs) who can only communicate by shouting "
        "(broadcasting on the CAN bus). Each person shouts a numbered message. Everyone hears "
        "everything, but each person only pays attention to the message numbers they care about. "
        "If two people try to shout at the same time, the one with the lower number automatically "
        "gets to go first. That is CAN in a nutshell.")

    # =========================================================================
    # CHAPTER 2: The CAN Frame
    # =========================================================================
    pdf.chapter_title(2, "The CAN Frame - Anatomy of a Message")

    pdf.body_text(
        "Every message on a CAN bus is called a 'frame'. A CAN frame is a precisely structured "
        "packet of bits that contains an identifier, the actual data, and error-checking information. "
        "Here is what a standard CAN 2.0A frame looks like:"
    )

    pdf.diagram_can_frame()

    pdf.section_title("Field-by-Field Breakdown")

    fields = [
        ("SOF (Start of Frame)", "1 bit",
         "A single dominant bit (logic 0) that marks the beginning of a frame. "
         "All nodes synchronize their clocks on this edge."),
        ("Arbitration Field (CAN ID)", "11 bits (standard) or 29 bits (extended)",
         "The message identifier. This is NOT a destination address - it identifies the TYPE of "
         "data in the message. For example, CAN ID 0x065 always means 'network management heartbeat' "
         "regardless of who sent it. The CAN ID also determines the message's priority."),
        ("RTR (Remote Transmission Request)", "1 bit",
         "Dominant (0) for a normal data frame, recessive (1) for a remote frame requesting data. "
         "Remote frames are rarely used in modern automotive CAN."),
        ("Control Field (CTRL)", "6 bits",
         "Contains the IDE bit (0=standard, 1=extended), a reserved bit, and the 4-bit DLC "
         "(Data Length Code) which specifies how many bytes of data follow (0 to 8)."),
        ("Data Field (Payload)", "0 to 8 bytes (0-64 bits)",
         "The actual data being transmitted. This is where the signal values live - temperatures, "
         "voltages, speeds, everything. The DLC field tells you how many bytes are here."),
        ("CRC (Cyclic Redundancy Check)", "16 bits (15 + delimiter)",
         "An error-detection code calculated from all preceding fields. The receiver recalculates "
         "the CRC and compares. If they don't match, the frame is rejected."),
        ("ACK (Acknowledge)", "2 bits",
         "The transmitter sends a recessive bit. Any receiver that correctly received the frame "
         "overwrites this with a dominant bit, confirming receipt. If no ACK, the transmitter "
         "knows nobody heard the message."),
        ("EOF (End of Frame)", "7 bits",
         "Seven recessive bits marking the end of the frame. After EOF, there's a minimum "
         "inter-frame gap before the next frame can start."),
    ]

    for name, size, desc in fields:
        pdf.subsection_title(f"{name} - {size}")
        pdf.body_text(desc)

    pdf.info_box("DLC (Data Length Code) - What You See in Logs",
        "When you open a CAN log in your analyzer tool, DLC is one of the columns. "
        "Almost all automotive CAN messages use DLC=8 (the maximum). Even if the actual "
        "data only needs 3 bytes, the remaining bytes are padded (usually with 0x55 or 0x00). "
        "This is because fixed-length messages are easier for ECUs to process.")

    # =========================================================================
    # CHAPTER 3: CAN ID and Priority
    # =========================================================================
    pdf.chapter_title(3, "CAN ID and Priority")

    pdf.section_title("What is the CAN ID?")

    pdf.body_text(
        "The CAN ID (also called Arbitration ID) is the identifier attached to every CAN message. "
        "It serves two critical purposes simultaneously:"
    )

    pdf.bullet_list([
        "It identifies the content of the message (what kind of data it carries)",
        "It determines the message's priority on the bus (lower number = higher priority)",
    ])

    pdf.body_text(
        "Important: The CAN ID does NOT identify the sender or receiver. It identifies the "
        "message content. CAN ID 0x065 always means the same type of data, regardless of which "
        "ECU transmitted it. This is fundamentally different from IP networking where addresses "
        "identify devices."
    )

    pdf.section_title("How Priority Arbitration Works")

    pdf.body_text(
        "CAN uses a clever mechanism called 'non-destructive bitwise arbitration'. When two or "
        "more nodes try to transmit at the same time, they don't collide and corrupt each other's "
        "data (like Ethernet would). Instead, the highest-priority message automatically wins, "
        "and the losers back off and retry."
    )

    pdf.body_text(
        "Here is how it works, step by step:"
    )

    pdf.bullet_list([
        "Each node starts transmitting its CAN ID, bit by bit, starting from the most significant bit",
        "On the CAN bus, a '0' (dominant) always overwrites a '1' (recessive) - this is a property of the electrical wiring",
        "Each transmitting node reads back the bus after each bit. If a node sent '1' but reads '0', it knows another node with a lower ID is transmitting",
        "That node immediately stops transmitting and waits. The winning node doesn't even know contention happened",
        "Result: the message with the lowest CAN ID always wins",
    ])

    pdf.body_text(
        "Example: Node A transmits CAN ID 0x065 (binary: 00001100101) and Node B transmits "
        "0x1A0 (binary: 00110100000). At the 3rd bit, Node A sends '0' while Node B sends '1'. "
        "Node B reads back '0' (dominant wins), realizes it lost arbitration, and backs off. "
        "Node A's message goes through without any delay or corruption."
    )

    pdf.section_title("Priority in Practice")

    pdf.simple_table(
        ["Priority", "CAN ID Range", "Typical Usage"],
        [
            ["Highest", "0x000 - 0x0FF", "Safety-critical: ABS, airbag, steering"],
            ["High", "0x100 - 0x2FF", "Powertrain: engine, transmission, battery"],
            ["Medium", "0x300 - 0x4FF", "Chassis: suspension, brakes, stability"],
            ["Lower", "0x500 - 0x6FF", "Body: lights, windows, doors, HVAC"],
            ["Low", "0x700 - 0x7FF", "Diagnostics (UDS/OBD-II), NM messages"],
        ],
        [25, 45, 120]
    )

    pdf.info_box("Your VW ID Buzz CAN IDs",
        "The 7 CAN IDs you captured (0x065-0x06F) are in the highest priority range. "
        "These are likely network management or safety-related messages that the gateway "
        "forwards to the OBD-II port. The actual battery data you need uses extended 29-bit "
        "CAN IDs (0x17FC007B / 0x17FE007B) which work differently - see Chapter 4.")

    # =========================================================================
    # CHAPTER 4: Standard vs Extended CAN
    # =========================================================================
    pdf.chapter_title(4, "Standard vs Extended CAN (2.0A vs 2.0B)")

    pdf.section_title("CAN 2.0A - Standard Frame (11-bit ID)")

    pdf.body_text(
        "The original CAN specification uses an 11-bit identifier, giving 2,048 possible CAN IDs "
        "(0x000 to 0x7FF). This is what you see in your current passive CAN logs: IDs like 0x065, "
        "0x066, etc. For many vehicles, 2,048 message types is enough."
    )

    pdf.key_value_block([
        ("ID Range", "0x000 to 0x7FF (0 to 2047 decimal)"),
        ("ID Length", "11 bits"),
        ("Example", "0x065 = Network Management heartbeat"),
        ("Used For", "Regular broadcast messages (periodic data)"),
    ])

    pdf.section_title("CAN 2.0B - Extended Frame (29-bit ID)")

    pdf.body_text(
        "As vehicles became more complex, 2,048 IDs were not enough. CAN 2.0B extends the "
        "identifier to 29 bits, giving over 536 million possible IDs. The extended frame has "
        "the same structure but splits the ID into two parts: an 11-bit base ID and an 18-bit "
        "extension."
    )

    pdf.diagram_extended_frame()

    pdf.key_value_block([
        ("ID Range", "0x00000000 to 0x1FFFFFFF"),
        ("ID Length", "29 bits (11 base + 18 extension)"),
        ("Example", "0x17FC007B = UDS request to BMS"),
        ("IDE Bit", "Set to 1 (recessive) to indicate extended frame"),
        ("Used For", "Diagnostic protocols (UDS), J1939, special protocols"),
    ])

    pdf.section_title("How to Tell Them Apart")

    pdf.body_text(
        "In your CAN logs and analyzer tools, you'll see a flag called 'IDE' (Identifier Extension). "
        "When IDE=0, it is a standard 11-bit frame. When IDE=1, it is an extended 29-bit frame. "
        "In MF4/MDF log files, this is stored in the CAN_DataFrame as a separate field."
    )

    pdf.info_box("Critical for Your Thesis",
        "Your passive CAN recordings only contain standard 11-bit IDs (0x065-0x06F). "
        "The battery data requires EXTENDED 29-bit IDs because VW uses UDS diagnostic "
        "protocol for BMS communication. The request ID 0x17FC007B and response ID "
        "0x17FE007B are both 29-bit extended IDs. Your CANedge2 needs to be configured "
        "to capture AND transmit extended frames.")

    pdf.section_title("Priority Between Standard and Extended")

    pdf.body_text(
        "When a standard and extended frame have the same base 11-bit ID, the standard frame "
        "wins. This is because at the IDE bit position, the standard frame sends dominant (0) "
        "while the extended frame sends recessive (1). In practice, this rarely matters because "
        "standard and extended IDs are used for completely different purposes."
    )

    # =========================================================================
    # CHAPTER 5: The Payload
    # =========================================================================
    pdf.chapter_title(5, "The Payload - What the Data Means")

    pdf.body_text(
        "The payload (data field) is where the actual information lives. A CAN frame can carry "
        "0 to 8 bytes of data. But raw bytes are meaningless without knowing how to interpret them. "
        "This section explains how ECU engineers pack real-world values into those 8 bytes."
    )

    pdf.section_title("Signals Within the Payload")

    pdf.body_text(
        "A single CAN message typically contains multiple 'signals' packed into its 8-byte payload. "
        "A signal is a specific piece of information with a defined position, length, byte order, "
        "and scaling formula."
    )

    pdf.body_text("For example, a battery status message might pack these signals into 8 bytes:")

    pdf.simple_table(
        ["Signal", "Start Byte", "Length", "Formula", "Unit"],
        [
            ["SOC", "Byte 0-1", "16 bits", "(raw) / 100", "%"],
            ["Pack Voltage", "Byte 2-3", "16 bits", "(raw) * 0.1", "V"],
            ["Pack Current", "Byte 4-5", "16 bits", "(raw - 32000) * 0.1", "A"],
            ["Temp Average", "Byte 6", "8 bits", "raw - 40", "C"],
            ["Status Flags", "Byte 7", "8 bits", "bit field", "-"],
        ],
        [35, 25, 25, 55, 20]
    )

    pdf.section_title("Byte Order (Endianness)")

    pdf.body_text(
        "When a value spans multiple bytes (like a 16-bit voltage), the byte order matters:"
    )

    pdf.subsection_title("Big-Endian (Motorola byte order)")
    pdf.body_text(
        "Most significant byte first. If bytes are [0x01, 0xF4], the 16-bit value is 0x01F4 = 500. "
        "This is the standard in most European automotive CAN (including VW)."
    )

    pdf.subsection_title("Little-Endian (Intel byte order)")
    pdf.body_text(
        "Least significant byte first. If bytes are [0xF4, 0x01], the 16-bit value is 0x01F4 = 500. "
        "Same result, but the bytes are swapped. Some Japanese and American vehicles use this."
    )

    pdf.info_box("VW Uses Big-Endian",
        "VW/Audi/Porsche (VAG group) traditionally use big-endian (Motorola) byte order. "
        "When you see a 16-bit value in your ID Buzz CAN data, read it as [MSB, LSB]. "
        "For example, cell voltage bytes [0x0E, 0xD8] = 0x0ED8 = 3800. With formula "
        "(raw/1000)+1 = 4.800V, which is a realistic LFP cell voltage... wait, actually "
        "VW MEB uses NMC cells, so expect ~3.6-4.2V per cell.")

    pdf.section_title("Common Encoding Patterns")

    pdf.subsection_title("Offset + Scale")
    pdf.body_text(
        "Physical Value = (Raw Value * Scale) + Offset\n"
        "Example: Temperature with offset -40: raw byte 0x3C (60 decimal), formula = 60 - 40 = 20 degrees C. "
        "The -40 offset allows representing temperatures from -40 to +215C in a single unsigned byte."
    )

    pdf.subsection_title("Counters")
    pdf.body_text(
        "A byte that increments by 1 each message, rolling over from 0xFF to 0x00. Used for "
        "detecting missed messages. You already found one at 0x066 bytes 1-2."
    )

    pdf.subsection_title("Checksums")
    pdf.body_text(
        "The last byte is often a checksum calculated from all other bytes. Used for error detection "
        "at the application level (on top of CAN's built-in CRC). Common algorithms: XOR of all bytes, "
        "or CRC-8."
    )

    pdf.subsection_title("Bit Fields / Flags")
    pdf.body_text(
        "Individual bits representing on/off states. For example, byte 0x05 = binary 00000101 means "
        "bit 0 (LSB) is ON and bit 2 is ON. Battery status flags often use this: bit 0 = charging, "
        "bit 1 = discharging, bit 2 = balancing, etc."
    )

    # =========================================================================
    # CHAPTER 6: J1939 - PGN and SPN
    # =========================================================================
    pdf.chapter_title(6, "J1939: PGN and SPN")

    pdf.body_text(
        "J1939 is a higher-layer protocol built on top of CAN, primarily used in heavy-duty vehicles "
        "(trucks, buses, construction equipment). It uses extended 29-bit CAN IDs and defines a "
        "standardized way to identify and interpret signals."
    )

    pdf.section_title("PGN - Parameter Group Number")

    pdf.body_text(
        "In J1939, the 29-bit CAN ID is not just a message identifier. It is a structured field "
        "broken into several parts:"
    )

    pdf.simple_table(
        ["Bits", "Field", "Description"],
        [
            ["28-26", "Priority", "3 bits, 0 = highest priority (same concept as CAN arbitration)"],
            ["25", "Reserved", "Always 0"],
            ["24", "Data Page (DP)", "Extends the PGN range"],
            ["23-16", "PDU Format (PF)", "Determines if message is broadcast or destination-specific"],
            ["15-8", "PDU Specific (PS)", "Destination address (if PF < 240) or Group Extension (if PF >= 240)"],
            ["7-0", "Source Address", "Identifies the sending ECU (0-253)"],
        ],
        [20, 40, 130]
    )

    pdf.body_text(
        "The PGN is derived from bits 24-8 of the CAN ID (the DP, PF, and PS fields combined). "
        "It identifies a 'group' of related parameters. For example:"
    )

    pdf.bullet_list([
        "PGN 65262 (0xFEEE) = Engine Temperature 1 (contains coolant temp, fuel temp, etc.)",
        "PGN 65263 (0xFEEF) = Engine Fluid Level/Pressure (oil pressure, coolant level, etc.)",
        "PGN 65271 (0xFEF7) = Vehicle Electrical Power (battery voltage, alternator current)",
    ])

    pdf.section_title("SPN - Suspect Parameter Number")

    pdf.body_text(
        "Within each PGN, individual signals are identified by SPNs. An SPN specifies exactly where "
        "a parameter sits within the 8-byte payload and how to decode it."
    )

    pdf.body_text("Example: PGN 65262 (Engine Temperature 1) contains:")

    pdf.simple_table(
        ["SPN", "Parameter", "Position", "Length", "Scale", "Offset", "Unit"],
        [
            ["110", "Engine Coolant Temp", "Byte 0", "8 bits", "1", "-40", "C"],
            ["174", "Fuel Temperature", "Byte 1", "8 bits", "1", "-40", "C"],
            ["175", "Engine Oil Temp", "Bytes 2-3", "16 bits", "0.03125", "-273", "C"],
            ["176", "Turbo Oil Temp", "Bytes 4-5", "16 bits", "0.03125", "-273", "C"],
        ],
        [18, 40, 25, 22, 22, 22, 18]
    )

    pdf.section_title("J1939 vs Your VW ID Buzz")

    pdf.warning_box(
        "The VW ID Buzz does NOT use J1939. J1939 is for commercial vehicles (trucks, buses). "
        "Passenger cars like the ID Buzz use standard CAN 2.0A/B with proprietary signal definitions "
        "and UDS (ISO 14229) for diagnostics. However, understanding PGN/SPN concepts helps you "
        "understand how CAN signals are structured in general - VW just uses their own proprietary "
        "mapping instead of the J1939 standard.")

    pdf.body_text(
        "The key takeaway: whether it is J1939 with standardized PGN/SPN definitions, or VW's "
        "proprietary scheme, the fundamental concept is the same - a CAN ID identifies the message "
        "type, and the payload bytes contain signals at specific positions with specific formulas. "
        "The difference is that J1939 signals are publicly documented, while VW's signals are not - "
        "which is exactly why you need to reverse engineer them."
    )

    # =========================================================================
    # CHAPTER 7: UDS and ISO-TP
    # =========================================================================
    pdf.chapter_title(7, "Higher-Layer Protocols: UDS and ISO-TP")

    pdf.body_text(
        "So far we have covered how CAN transmits messages. But CAN itself is just a transport "
        "mechanism - it moves bytes from A to B. For more complex communication (like requesting "
        "diagnostic data from a specific ECU), you need higher-layer protocols built on top of CAN."
    )

    pdf.section_title("UDS - Unified Diagnostic Services (ISO 14229)")

    pdf.body_text(
        "UDS is the standard diagnostic protocol used by virtually all modern passenger vehicles, "
        "including VW. It defines a set of 'services' that a diagnostic tool can request from an ECU. "
        "Think of it as an API for the car: you send a request with a service ID and parameters, "
        "and the ECU sends back a response with the requested data."
    )

    pdf.subsection_title("How UDS Works Over CAN")

    pdf.body_text(
        "UDS uses a request/response pattern with specific CAN IDs for each ECU:\n\n"
        "1. The diagnostic tool sends a request to the ECU's request CAN ID\n"
        "2. The ECU processes the request\n"
        "3. The ECU sends the response on its response CAN ID\n\n"
        "For the VW ID Buzz BMS (Battery Management System):\n"
        "  Request CAN ID:  0x17FC007B (29-bit extended)\n"
        "  Response CAN ID: 0x17FE007B (29-bit extended)"
    )

    pdf.section_title("Key UDS Services")

    pdf.simple_table(
        ["Service ID", "Service Name", "What It Does", "Relevant for Battery?"],
        [
            ["0x10", "DiagnosticSessionControl", "Opens a diagnostic session (needed before most requests)", "YES - must do first"],
            ["0x11", "ECUReset", "Resets the ECU", "NO - dangerous"],
            ["0x22", "ReadDataByIdentifier", "Reads a specific data parameter by its DID", "YES - primary service"],
            ["0x23", "ReadMemoryByAddress", "Reads raw memory from ECU", "Maybe - advanced"],
            ["0x27", "SecurityAccess", "Unlocks protected functions with a key", "Maybe - some DIDs locked"],
            ["0x2E", "WriteDataByIdentifier", "Writes data to ECU", "NO - dangerous"],
            ["0x31", "RoutineControl", "Starts/stops ECU routines", "Maybe - for tests"],
            ["0x3E", "TesterPresent", "Keeps diagnostic session alive", "YES - periodic keepalive"],
        ],
        [22, 50, 65, 45]
    )

    pdf.section_title("Service 0x22: ReadDataByIdentifier (Your Main Tool)")

    pdf.body_text(
        "This is the service you'll use the most. It takes a 2-byte DID (Data Identifier) and "
        "returns the corresponding value. Here's the exact format:"
    )

    pdf.subsection_title("Request Format")
    pdf.code_block(
        "Byte 0: Length of following data (PCI byte for single-frame)\n"
        "Byte 1: Service ID = 0x22\n"
        "Byte 2: DID high byte\n"
        "Byte 3: DID low byte\n"
        "Bytes 4-7: Padding (0x55)"
    )

    pdf.body_text("Example - Request SOC from BMS:")
    pdf.code_block(
        "CAN ID: 0x17FC007B (extended)\n"
        "Data:   03 22 02 8C 55 55 55 55\n"
        "        |  |  |-----|  padding\n"
        "        |  |  DID = 0x028C (SOC)\n"
        "        |  Service 0x22 (ReadDataByIdentifier)\n"
        "        3 bytes follow (service + DID)"
    )

    pdf.subsection_title("Positive Response Format")
    pdf.code_block(
        "Byte 0: Length (PCI)\n"
        "Byte 1: Service ID + 0x40 = 0x62 (positive response)\n"
        "Byte 2: DID high byte (echo)\n"
        "Byte 3: DID low byte (echo)\n"
        "Bytes 4+: The actual data value"
    )

    pdf.body_text("Example - BMS responds with SOC = 80%:")
    pdf.code_block(
        "CAN ID: 0x17FE007B (extended)\n"
        "Data:   04 62 02 8C C8 55 55 55\n"
        "        |  |  |-----| |  padding\n"
        "        |  |  DID echo |  \n"
        "        |  |           0xC8 = 200 decimal\n"
        "        |  Positive response (0x22 + 0x40)\n"
        "        4 bytes follow\n"
        "\n"
        "Decoding: 200 / 2.5 = 80.0% SOC"
    )

    pdf.subsection_title("Negative Response (Error)")
    pdf.code_block(
        "Data:   03 7F 22 XX 55 55 55 55\n"
        "        |  |  |  |\n"
        "        |  |  |  Error code (NRC)\n"
        "        |  |  Service that failed\n"
        "        |  Negative Response indicator\n"
        "        3 bytes follow\n"
        "\n"
        "Common NRC codes:\n"
        "  0x12 = SubFunctionNotSupported\n"
        "  0x13 = IncorrectMessageLengthOrInvalidFormat\n"
        "  0x14 = ResponseTooLong\n"
        "  0x22 = ConditionsNotCorrect (need diagnostic session first!)\n"
        "  0x31 = RequestOutOfRange (DID doesn't exist)\n"
        "  0x33 = SecurityAccessDenied (need security unlock)\n"
        "  0x78 = RequestCorrectlyReceived-ResponsePending (wait!)"
    )

    pdf.section_title("Diagnostic Session Control (Service 0x10)")

    pdf.body_text(
        "Before you can read battery data with service 0x22, you usually need to open a diagnostic "
        "session. The BMS defaults to 'Default Session' which only allows basic PIDs. For battery "
        "cell voltages and detailed data, you need 'Extended Diagnostic Session'."
    )

    pdf.code_block(
        "Open Extended Diagnostic Session:\n"
        "  Request:  02 10 03 55 55 55 55 55  to 0x17FC007B\n"
        "  Response: 02 50 03 55 55 55 55 55  from 0x17FE007B\n"
        "            |  |  |\n"
        "            |  |  Sub-function: 03 = Extended Session\n"
        "            |  Positive response (0x10 + 0x40 = 0x50)\n"
        "            2 bytes follow\n"
        "\n"
        "Session types:\n"
        "  0x01 = Default Session (limited data)\n"
        "  0x02 = Programming Session (for flashing)\n"
        "  0x03 = Extended Diagnostic Session (most data available)"
    )

    pdf.warning_box(
        "The diagnostic session times out after ~5 seconds of inactivity. You must send a "
        "'TesterPresent' message (02 3E 00 55 55 55 55 55) periodically to keep it alive. "
        "If the session drops, you'll get NRC 0x22 (ConditionsNotCorrect) and need to "
        "re-open the session.")

    pdf.section_title("ISO-TP - Transport Protocol (ISO 15765)")

    pdf.body_text(
        "CAN frames can only carry 8 bytes of data. But what if the ECU's response is longer than "
        "8 bytes? For example, reading all 108 cell voltages would require hundreds of bytes. "
        "ISO-TP (also called ISO 15765-2) solves this by splitting long messages into multiple "
        "CAN frames."
    )

    pdf.subsection_title("ISO-TP Frame Types")

    pdf.simple_table(
        ["Type", "PCI Nibble", "Description", "Max Data"],
        [
            ["Single Frame (SF)", "0x0", "Complete message fits in one CAN frame", "7 bytes"],
            ["First Frame (FF)", "0x1", "First part of a multi-frame message", "6 bytes + total length"],
            ["Consecutive Frame (CF)", "0x2", "Continuation of multi-frame message", "7 bytes each"],
            ["Flow Control (FC)", "0x3", "Receiver tells transmitter how to proceed", "Timing params"],
        ],
        [40, 25, 75, 45]
    )

    pdf.body_text("Example - Reading a long response (e.g., multi-cell voltage block):")

    pdf.code_block(
        "You send: Single Frame request\n"
        "  03 22 1E 40 55 55 55 55  (request cell 1 voltage)\n"
        "\n"
        "ECU responds: Single Frame (data fits in 1 frame)\n"
        "  05 62 1E 40 0E D8 55 55\n"
        "  |                |\n"
        "  5 bytes follow   Raw value = 0x0ED8 = 3800\n"
        "                   (3800/1000)+1 = 4.800V... hmm\n"
        "                   Or: 3800/1000 = 3.800V (more likely for NMC cell)"
    )

    pdf.body_text(
        "For multi-frame responses, the flow is:\n"
        "1. ECU sends First Frame with total length and first 6 bytes of data\n"
        "2. You (tester) send Flow Control: 'send all remaining frames with no delay'\n"
        "3. ECU sends Consecutive Frames (sequence numbered 1, 2, 3... F, 0, 1...)\n"
        "4. You reassemble all data in order"
    )

    pdf.info_box("CANedge2 and ISO-TP",
        "The CANedge2 can LOG ISO-TP frames but does NOT handle the flow control automatically. "
        "If you send a request that triggers a multi-frame response, the BMS will send the First "
        "Frame and then wait for your Flow Control frame. If the CANedge2 can't send the FC frame, "
        "the response will be incomplete. This is a key limitation to test tomorrow.")

    # =========================================================================
    # CHAPTER 8: CAN in the VW ID Buzz
    # =========================================================================
    pdf.chapter_title(8, "CAN in the VW ID Buzz (MEB Platform)")

    pdf.section_title("VW MEB Platform Architecture")

    pdf.body_text(
        "The VW ID Buzz is built on the MEB (Modularer E-Antriebs-Baukasten) platform, shared "
        "with the ID.3, ID.4, ID.5, Skoda Enyaq, Audi Q4 e-tron, and others. All these vehicles "
        "share similar CAN bus architecture and BMS communication protocols."
    )

    pdf.subsection_title("Multiple CAN Buses")
    pdf.body_text(
        "The MEB platform uses multiple separate CAN buses, each serving a different domain. "
        "These buses are interconnected through a central gateway ECU that controls which messages "
        "are forwarded between buses."
    )

    pdf.simple_table(
        ["Bus Name", "Speed", "Connected ECUs", "Battery Data?"],
        [
            ["Powertrain CAN", "500 kbps", "BMS, Motor Controller, Charger, Inverter", "YES - primary"],
            ["Comfort CAN", "500 kbps", "HVAC, Seats, Windows, Mirrors", "Temp requests maybe"],
            ["Infotainment CAN", "500 kbps", "Head Unit, Instrument Cluster, Cameras", "SOC display value"],
            ["Chassis CAN", "500 kbps", "ABS, ESP, Steering, Suspension", "No"],
            ["Diagnostics CAN", "500 kbps", "OBD-II port (via gateway)", "Via UDS only"],
        ],
        [35, 22, 75, 48]
    )

    pdf.section_title("The Gateway Problem")

    pdf.body_text(
        "This is crucial to understand: the OBD-II port in the VW ID Buzz is NOT directly connected "
        "to the powertrain CAN bus where the BMS lives. Instead, it connects through a central "
        "gateway ECU. The gateway acts as a firewall/router:"
    )

    pdf.bullet_list([
        "It BLOCKS most internal CAN messages from reaching the OBD-II port",
        "It only FORWARDS a small subset of 'allowed' messages to the diagnostic bus",
        "It ROUTES diagnostic requests (UDS) from the OBD-II port to the correct internal bus and ECU",
        "This is why passive recording on OBD-II only gives you 7 CAN IDs (0x065-0x06F) - everything else is filtered out",
    ])

    pdf.body_text(
        "However, the gateway DOES forward UDS diagnostic requests. When you send a UDS request "
        "to 0x17FC007B on the OBD-II port, the gateway recognizes this as a diagnostic request "
        "for the BMS and forwards it to the powertrain CAN bus. The BMS responds, and the gateway "
        "forwards the response back to the OBD-II port as 0x17FE007B."
    )

    pdf.info_box("Why This Matters",
        "You don't need to physically tap into the powertrain CAN bus. UDS requests through the "
        "OBD-II port WILL reach the BMS, because the gateway is designed to pass diagnostic traffic. "
        "This is how OBDEleven, VCDS, and other diagnostic tools work - they all go through the "
        "gateway. Your CANedge2 just needs to be able to send those same UDS request frames.")

    pdf.section_title("BMS ECU Addressing")

    pdf.body_text(
        "In the VW MEB platform, each ECU has a unique diagnostic address encoded in the CAN ID:"
    )

    pdf.code_block(
        "Request CAN ID format:  0x17FC00XX  (where XX = ECU address)\n"
        "Response CAN ID format: 0x17FE00XX  (where XX = ECU address)\n"
        "\n"
        "BMS ECU address: 0x7B (123 decimal)\n"
        "  Request:  0x17FC007B\n"
        "  Response: 0x17FE007B\n"
        "\n"
        "Other ECUs you might encounter:\n"
        "  0x17FC00B9 / 0x17FE00B9 = DC-DC Converter\n"
        "  0x17FC0076 / 0x17FE0076 = Motor Controller\n"
        "  0x17FC006D / 0x17FE006D = On-board Charger"
    )

    # =========================================================================
    # CHAPTER 9: Battery Data Over CAN
    # =========================================================================
    pdf.chapter_title(9, "Battery Data Over CAN")

    pdf.body_text(
        "Now let's get specific about what battery data you can actually extract from the "
        "VW ID Buzz. Based on the VW MEB UDS PID list (194 known DIDs), here are the battery-related "
        "parameters organized by category."
    )

    pdf.section_title("Category 1: State of Charge & Energy")

    pdf.simple_table(
        ["DID", "Parameter", "Formula", "Unit"],
        [
            ["0x028C", "SOC (BMS internal)", "raw / 2.5", "%"],
            ["0x028D", "SOC (displayed)", "raw / 2.5", "%"],
            ["0x1E3B", "HV Battery Voltage", "(MSB*256+LSB) * factor", "V"],
            ["0x1E3D", "HV Battery Current", "(MSB*256+LSB) * factor", "A"],
            ["0x7448", "Car Operation Mode", "0=standby,1=drive,4=AC,6=DC", "-"],
        ],
        [25, 50, 60, 20]
    )

    pdf.section_title("Category 2: Cell Voltages (108 cells)")

    pdf.body_text(
        "The VW ID Buzz battery pack contains 108 cells in series. Each cell voltage is available "
        "as a separate DID. The DIDs follow a sequential pattern:"
    )

    pdf.simple_table(
        ["DID Range", "Cells", "Formula", "Notes"],
        [
            ["0x1E40 - 0x1E49", "Cell 1 - Cell 10", "(MSB*256+LSB)/1000+1", "First 10 cells"],
            ["0x1E4A - 0x1E53", "Cell 11 - Cell 20", "(MSB*256+LSB)/1000+1", "Next 10 cells"],
            ["0x1E54 - 0x1E6B", "Cell 21 - Cell 44", "(MSB*256+LSB)/1000+1", "...continues"],
            ["0x1E6C - 0x1EAB", "Cell 45 - Cell 108", "(MSB*256+LSB)/1000+1", "Up to cell 108"],
        ],
        [40, 40, 55, 50]
    )

    pdf.body_text(
        "Each cell voltage request is a single-frame UDS request and gets a single-frame response. "
        "This means you don't need ISO-TP multi-frame support for individual cell voltages - "
        "a huge advantage for the CANedge2!"
    )

    pdf.section_title("Category 3: Temperatures (18 sensor points)")

    pdf.simple_table(
        ["DID", "Parameter", "Formula", "Unit"],
        [
            ["0x2A0B", "Battery Main Temperature", "raw - 40 (est.)", "C"],
            ["0x1E0E", "Max Battery Temperature", "raw - 40 (est.)", "C"],
            ["0x1E0F", "Min Battery Temperature", "raw - 40 (est.)", "C"],
            ["0x1E10-0x1E21", "Temp Points 1-18", "raw - 40 (est.)", "C"],
        ],
        [40, 50, 50, 20]
    )

    pdf.section_title("Category 4: System-Level Parameters")

    pdf.simple_table(
        ["DID", "Parameter", "Description"],
        [
            ["0x1E33", "Cell with Highest Voltage", "Identifies the cell number"],
            ["0x1E34", "Cell with Lowest Voltage", "Identifies the cell number"],
            ["0x743B", "Circulation Pump", "Cooling pump duty cycle (%)"],
            ["0x465B", "DC-DC Current", "HV to 12V converter current"],
            ["0x465D", "DC-DC Voltage", "HV to 12V converter voltage"],
        ],
        [25, 55, 105]
    )

    pdf.section_title("What Gets Broadcast vs What Needs UDS")

    pdf.body_text(
        "This is a critical distinction:"
    )

    pdf.subsection_title("Broadcast Messages (Passive CAN - no request needed)")
    pdf.bullet_list([
        "Network management messages (your 0x065-0x06F) - always broadcast",
        "On the INTERNAL powertrain bus: BMS probably broadcasts SOC, pack voltage, pack current at ~10-100ms intervals",
        "But the gateway BLOCKS these from the OBD-II port",
        "You can only see these if you tap directly into the powertrain CAN bus (Strategy C)",
    ])

    pdf.subsection_title("UDS Diagnostic Messages (Active - must request)")
    pdf.bullet_list([
        "ALL 145 battery DIDs in the PID list require active UDS requests",
        "You send service 0x22 + DID, the BMS responds with the value",
        "These DO work through the gateway - that's the whole point of UDS",
        "This is your primary data collection method (Strategy A or B)",
    ])

    # =========================================================================
    # CHAPTER 10: Reverse Engineering Strategy
    # =========================================================================
    pdf.chapter_title(10, "Reverse Engineering Strategy")

    pdf.body_text(
        "Reverse engineering CAN bus data means figuring out what unknown signals mean by analyzing "
        "patterns in the raw data. Here is a systematic approach."
    )

    pdf.section_title("Step 1: Passive Recording (What you have)")

    pdf.bullet_list([
        "Record CAN traffic under different conditions (standstill, driving, charging)",
        "Identify all unique CAN IDs and their transmission rates",
        "This gives you the 'landscape' of what's on the bus",
    ])

    pdf.section_title("Step 2: Pattern Recognition")

    pdf.bullet_list([
        "Look for COUNTERS: bytes that increment by 1 each message",
        "Look for CONSTANTS: bytes that never change (configuration data or padding)",
        "Look for BINARY FLAGS: bytes that are only 0x00 or 0x01 (status flags)",
        "Look for TEMPERATURE PATTERNS: bytes around 60-80 (if using offset -40, this is 20-40C)",
        "Look for VOLTAGE PATTERNS: 16-bit values that stay in a narrow range",
    ])

    pdf.section_title("Step 3: Correlation Testing")

    pdf.bullet_list([
        "Change ONE thing at a time and see what changes in the CAN data",
        "Turn on AC -> which bytes change? Those are HVAC-related",
        "Press accelerator -> which bytes change? Those are motor/power-related",
        "Temperature changes slowly over time -> correlates with thermal sensors",
        "Compare values with the instrument cluster display for validation",
    ])

    pdf.section_title("Step 4: UDS Discovery")

    pdf.bullet_list([
        "Send known UDS requests from the PID list and verify responses",
        "Cross-reference UDS response values with broadcast CAN signals",
        "If a broadcast byte matches a UDS-confirmed value, you've decoded that signal",
        "Build a DBC file mapping all confirmed signals",
    ])

    pdf.section_title("Step 5: Validation")

    pdf.bullet_list([
        "Verify decoded values make physical sense (cell voltage 3.2-4.2V, temp -20 to +60C)",
        "Compare with expected behavior (SOC decreases while driving, increases while charging)",
        "Cross-reference multiple independent measurements (pack voltage should equal sum of cell voltages)",
        "Document confidence level for each decoded signal (HIGH/MEDIUM/LOW)",
    ])

    # =========================================================================
    # SAVE
    # =========================================================================
    output_path = OUTPUT_DIR / "CAN_Bus_Complete_Guide_v2.pdf"
    pdf.output(str(output_path))
    print(f"PDF saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    build_pdf()
