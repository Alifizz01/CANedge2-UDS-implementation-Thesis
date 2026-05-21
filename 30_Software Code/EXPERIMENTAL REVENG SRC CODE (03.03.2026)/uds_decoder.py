"""
UDS PID Decoder for VW ID Buzz (MEB platform)
Parses the UDS PIDs CSV definition file and decodes CAN bus
response frames from MF4 log files into engineering values.

Usage:
    from uds_decoder import load_pid_definitions, decode_frame, decode_all

    # Load PID definitions from CSV
    pids = load_pid_definitions()

    # Load CAN data and decode
    from mf4_reader import load_all
    can_data = load_all()
    decoded = decode_all(can_data, pids)
"""

import re
import csv
from pathlib import Path
import pandas as pd
from mf4_reader import load_all, load_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "csv" / "VW MEB UDS PIDs list.csv"


# ── CSV Parser ────────────────────────────────────────────────

def load_pid_definitions(csv_path=None):
    """
    Parse the UDS PIDs CSV and return a list of PID definitions.

    Each PID definition is a dict with:
        name, group, unit, status,
        request_id, response_id,
        request_data, response_pattern,
        calculation, info,
        variable_positions (dict mapping variable names to byte indices)
    """
    if csv_path is None:
        csv_path = str(DEFAULT_CSV)
    pids = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    # Header is at row index 4 (line 5)
    header = rows[4]
    data_rows = rows[5:]

    for row in data_rows:
        if len(row) < 13:
            continue

        status = row[0].strip()
        group = row[1].strip()
        name = row[2].strip()
        unit = row[3].strip()
        pid_type = row[4].strip()
        request_pkg = row[5].strip()
        atsh = row[7].strip()
        data_send = row[8].strip()
        response_pkg = row[9].strip()
        atcra = row[10].strip()
        data_received = row[11].strip()
        calculation = row[12].strip() if len(row) > 12 else ""
        info = row[13].strip() if len(row) > 13 else ""

        # Skip entries without a calculation formula or response pattern
        if not calculation or not atcra:
            continue

        # Parse the response CAN ID
        response_id = _parse_can_id(atcra)
        request_id = _parse_can_id(atsh)

        if response_id is None:
            continue

        # Parse the response data pattern to find variable byte positions
        var_positions = _parse_response_pattern(data_received)

        # Parse the request DID from the data_send field
        did = _extract_did(data_send)

        pids.append({
            "name": name,
            "group": group,
            "unit": unit,
            "status": status,
            "request_id": request_id,
            "response_id": response_id,
            "request_data": data_send,
            "response_pattern": data_received,
            "did": did,
            "calculation": calculation,
            "info": info,
            "variable_positions": var_positions,
        })

    return pids


def _parse_can_id(id_str):
    """Parse a CAN ID string like '17fe007b' or '000007b0' into an integer."""
    id_str = id_str.strip().lower()
    if not id_str or id_str == "ltiframe":
        return None
    # Remove 0x prefix if present
    id_str = id_str.replace("0x", "")
    try:
        return int(id_str, 16)
    except ValueError:
        return None


def _extract_did(data_send):
    """
    Extract the UDS DID from the request data.
    e.g. '03 22 46 5b 55 55 55 55' -> '465b'
    """
    parts = data_send.strip().split()
    if len(parts) >= 4 and parts[1] == "22":
        return parts[2] + parts[3]
    return None


def _parse_response_pattern(pattern):
    """
    Parse a response pattern like '05 62 46 5b XX YY aa aa'
    and return a dict mapping variable names to their byte index positions.

    Variables: XX, YY, WW, ZZ (case-insensitive)
    'aa' bytes are padding/ignored.
    """
    parts = pattern.strip().split()
    positions = {}
    for i, part in enumerate(parts):
        upper = part.upper()
        if upper == "XX":
            positions["XX"] = i
        elif upper == "YY":
            positions["YY"] = i
        elif upper == "WW":
            positions["WW"] = i
        elif upper == "ZZ":
            positions["ZZ"] = i
    return positions


# ── Calculation Engine ────────────────────────────────────────

def _evaluate_calculation(calc_str, variables):
    """
    Evaluate a calculation string from the CSV using extracted byte values.

    Examples of calc_str:
        '(XX*2^8+YY)/16 = DC-DC current in decimal value'
        'XX/2-40=temperature in C'
        'XX = speed in decimal'

    variables: dict like {'XX': 165, 'YY': 20}
    """
    # Take only the part before '=' (the formula)
    formula = calc_str.split("=")[0].strip()

    # Handle special cases
    if not formula:
        return None

    # Replace variable names with their values
    # Sort by length descending to avoid partial replacements
    for var_name in sorted(variables.keys(), key=len, reverse=True):
        formula = formula.replace(var_name, str(variables[var_name]))

    # Replace math notation: 2^8 -> 2**8
    formula = formula.replace("^", "**")

    # Replace comma decimal separator with dot (European CSV)
    formula = formula.replace(",", ".")

    # Handle 'signed(...)' wrapper
    formula = formula.replace("signed(", "(")

    try:
        result = eval(formula)
        return result
    except Exception as e:
        return None


def _match_fixed_bytes(pattern, data_bytes):
    """
    Check if the fixed bytes in the response pattern match the actual data.
    Returns True if all fixed bytes match.
    """
    parts = pattern.strip().split()
    if len(data_bytes) < len(parts):
        return False

    for i, part in enumerate(parts):
        upper = part.upper()
        # Skip variable bytes and padding
        if upper in ("XX", "YY", "WW", "ZZ", "AA"):
            continue
        # Check fixed bytes
        try:
            expected = int(part, 16)
            actual = int(data_bytes[i])
            if expected != actual:
                return False
        except (ValueError, IndexError):
            continue

    return True


def _extract_variables(pattern, data_bytes):
    """
    Extract variable byte values from data_bytes based on the response pattern.
    Returns dict like {'XX': 165, 'YY': 20}
    """
    positions = _parse_response_pattern(pattern)
    variables = {}
    for var_name, idx in positions.items():
        if idx < len(data_bytes):
            variables[var_name] = int(data_bytes[idx])
    return variables


# ── Decoder ───────────────────────────────────────────────────

def decode_frame(can_id, data_bytes, pids):
    """
    Try to decode a single CAN frame against all PID definitions.

    Args:
        can_id: integer CAN ID
        data_bytes: list/array of byte values
        pids: list of PID definitions from load_pid_definitions()

    Returns:
        list of dicts with decoded values (may match multiple PIDs)
    """
    results = []
    byte_list = [int(b) for b in data_bytes]

    for pid in pids:
        if pid["response_id"] != can_id:
            continue

        # Check if fixed bytes in the response pattern match
        if not _match_fixed_bytes(pid["response_pattern"], byte_list):
            continue

        # Extract variable values
        variables = _extract_variables(pid["response_pattern"], byte_list)
        if not variables:
            continue

        # Calculate the engineering value
        value = _evaluate_calculation(pid["calculation"], variables)

        results.append({
            "name": pid["name"],
            "group": pid["group"],
            "unit": pid["unit"],
            "value": value,
            "raw_variables": variables,
            "calculation": pid["calculation"],
        })

    return results


def decode_all(can_df, pids):
    """
    Decode all CAN frames in a DataFrame against the PID definitions.

    Args:
        can_df: DataFrame from mf4_reader (with can_id, data_bytes columns)
        pids: list of PID definitions

    Returns:
        DataFrame with decoded engineering values
    """
    # Build a set of response IDs for quick filtering
    response_ids = {pid["response_id"] for pid in pids}

    decoded_rows = []

    for timestamp, row in can_df.iterrows():
        can_id = int(row["can_id"])
        if can_id not in response_ids:
            continue

        data_bytes = row["data_bytes"]
        results = decode_frame(can_id, data_bytes, pids)

        for res in results:
            decoded_rows.append({
                "timestamp": timestamp,
                "name": res["name"],
                "group": res["group"],
                "value": res["value"],
                "unit": res["unit"],
                "can_id_hex": row.get("can_id_hex", f"0x{can_id:03X}"),
                "raw_variables": str(res["raw_variables"]),
                "source": row.get("source", ""),
            })

    if not decoded_rows:
        return pd.DataFrame()

    df = pd.DataFrame(decoded_rows)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ── Analysis helpers ──────────────────────────────────────────

def list_available_pids(pids):
    """Print all available PID definitions grouped by category."""
    groups = {}
    for pid in pids:
        g = pid["group"] or "Other"
        if g not in groups:
            groups[g] = []
        groups[g].append(pid)

    for group_name, group_pids in sorted(groups.items()):
        print(f"\n  [{group_name}]")
        for pid in group_pids:
            status_marker = "*" if pid["status"] == "Ready" else "?"
            resp_hex = f"0x{pid['response_id']:08X}" if pid['response_id'] else "N/A"
            print(f"    {status_marker} {pid['name']:45s} [{pid['unit']:5s}]  resp={resp_hex}")


def get_signal_timeseries(decoded_df, signal_name):
    """Extract a single signal as a time series from decoded data."""
    mask = decoded_df["name"] == signal_name
    ts = decoded_df[mask][["timestamp", "value", "unit"]].copy()
    ts = ts.set_index("timestamp").sort_index()
    return ts


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== VW MEB UDS PID Decoder ===\n")

    # 1) Load PID definitions
    pids = load_pid_definitions()
    print(f"Loaded {len(pids)} PID definitions with formulas\n")

    # Show available PIDs
    print("Available PIDs:")
    list_available_pids(pids)

    # Show which response CAN IDs we're looking for
    response_ids = sorted({pid["response_id"] for pid in pids})
    print(f"\n\nResponse CAN IDs to match: {[f'0x{x:08X}' for x in response_ids]}")

    # 2) Load MF4 CAN data
    print("\nLoading MF4 CAN data...")
    can_data = load_all()
    mf4_ids = sorted(can_data["can_id"].unique())
    print(f"MF4 CAN IDs present: {[f'0x{int(x):03X}' for x in mf4_ids]}")

    # Check for overlap
    mf4_id_set = set(int(x) for x in mf4_ids)
    overlap = mf4_id_set & set(response_ids)
    if overlap:
        print(f"\nMATCHING IDs found: {[f'0x{x:03X}' for x in sorted(overlap)]}")
    else:
        print("\nNo direct CAN ID matches between MF4 data and UDS response IDs.")
        print("This is expected if the MF4 logs contain regular CAN traffic")
        print("while the UDS PIDs define diagnostic request/response pairs.")
        print("\nThe MF4 data may need ISO-TP (ISO 15765) transport layer decoding,")
        print("or the logs may be from a different CAN bus than the diagnostic bus.")

    # 3) Try decoding anyway
    print("\nAttempting to decode all frames...")
    decoded = decode_all(can_data, pids)
    if decoded.empty:
        print("No frames could be decoded with current PID definitions.")
        print("\nTo decode this data you may need:")
        print("  1. A DBC file for the standard CAN IDs (0x065-0x06F)")
        print("  2. MF4 logs from a UDS diagnostic session")
    else:
        print(f"\nDecoded {len(decoded)} values!")
        print(decoded.head(20).to_string(index=False))

        # Export
        decoded.to_csv("decoded_data.csv", index=False)
        print("\nExported to decoded_data.csv")
