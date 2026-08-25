"""
UDS Battery Decoder for VW MEB platform (ID.3, ID.4, ID Buzz).

Parses the VW MEB UDS PID list CSV into a PID database, then decodes every
0x17FE007B response captured by the CANedge into named battery signals.

Outputs:
  - output/uds_decoded/<session>.csv          : per-session decoded signal time series
  - output/uds_decoded/all_sessions.csv       : merged across sessions
  - output/uds_decoded/<session>__summary.txt : per-PID statistics for that session
  - output/uds_decoded/summary.txt            : per-PID statistics merged across all sessions
  - output/uds_decoded/plots/                 : per-signal time-series plots

The per-session summaries exist because sessions are not always on the same day
or contiguous, and the merged stats wash that distinction out. Each
`<session>__summary.txt` shows what was actually captured in that one drive.

Usage:
    python -X utf8 src/uds_battery_decoder.py
    python -X utf8 src/uds_battery_decoder.py --session 00000013
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
from asammdf import MDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "40_Experiments" / "Exprimental Data"
PID_CSV = DATA_DIR / "csv" / "VW MEB UDS PIDs list.csv"
OUTPUT_DIR = PROJECT_ROOT / "40_Experiments" / "Exprimental Plots" / "uds_decoded"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "plots").mkdir(exist_ok=True)

BMS_REQUEST_ID = 0x17FC007B
BMS_RESPONSE_ID = 0x17FE007B


# ── PID database ─────────────────────────────────────────────

def parse_pid_csv(path: Path) -> dict:
    """Parse the VW MEB UDS PIDs list into {pid_int: PidDef}.

    Each row's "data send" column gives bytes like '03 22 1e 40 55 55 55 55'.
    We extract the 16-bit PID (here 0x1E40) plus the "Calculation" formula
    that operates on response data bytes labelled XX, YY, ZZ, WW, VV, UU.
    """
    pids = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    # Header is on row index 4 (rows 0-3 are metadata/empty)
    header = rows[4]
    # ['Status','group','Popular name','Unit','type','Request package','ATCP',
    #  'ATSH','data send','Response package','ATCRA','datareceived',
    #  'Calculation','info']
    col = {name.strip(): i for i, name in enumerate(header)}

    PLACEHOLDERS = {"WW", "XX", "YY", "ZZ", "VV", "UU", "TT", "SS"}
    for r in rows[5:]:
        if len(r) <= col["Calculation"]:
            continue
        send = r[col["data send"]].strip().lower()
        if not send:
            continue
        parts = send.split()
        if len(parts) < 4 or parts[1] != "22":
            continue
        try:
            pid_hi = int(parts[2], 16)
            pid_lo = int(parts[3], 16)
        except ValueError:
            continue
        pid = (pid_hi << 8) | pid_lo

        recv = r[col["datareceived"]].strip()
        recv_parts = recv.split()
        # Strip optional response CAN-id prefix
        if recv_parts and recv_parts[0].lower().startswith("17fe"):
            recv_parts = recv_parts[1:]
        # Format now: "<len> 62 <hi> <lo> <label_1> <label_2> ..."
        # Value bytes start at index 4 in this list (after PCI-len, 0x62, hi, lo).
        labels_by_position = {}  # position-in-value-bytes -> label name (e.g. 'WW')
        for pos, tok in enumerate(recv_parts[4:]):
            tok_up = tok.upper()
            if tok_up in PLACEHOLDERS:
                labels_by_position[pos] = tok_up

        pids[pid] = {
            "pid": pid,
            "pid_hex": f"0x{pid:04X}",
            "name": r[col["Popular name"]].strip(),
            "unit": r[col["Unit"]].strip(),
            "group": r[col["group"]].strip(),
            "calc": r[col["Calculation"]].strip(),
            "labels_by_position": labels_by_position,
        }
    return pids


# ── Calculation evaluator ────────────────────────────────────

PLACEHOLDERS = ("WW", "XX", "YY", "ZZ", "VV", "UU", "TT", "SS")


def normalize_formula(formula: str) -> str:
    """Convert a CSV formula like '(XX*2^8+YY)/4 = Voltage' into a Python
    expression usable with eval. Returns just the expression part.
    """
    f = formula.strip()
    # Drop annotation after the first '=' that appears AFTER any operator,
    # but keep the LHS expression itself.
    # Strategy: find first '=' that is followed by descriptive text (a letter)
    # and not preceded by an operator placeholder.
    # Simpler: split on '=' and keep the side that contains placeholders + numbers.
    parts = re.split(r"\s*=\s*(?![=>])", f)  # don't split '=>'
    expr = parts[0]
    for p in parts:
        if any(ph in p.upper() for ph in PLACEHOLDERS):
            expr = p
            break
    # Normalize comma decimals: "/2,5" -> "/2.5"
    expr = re.sub(r"(\d),(\d)", r"\1.\2", expr)
    # 2^N -> 2**N
    expr = expr.replace("^", "**")
    # Strip trailing prose like " in decimal value", " HV current", etc.
    expr = re.split(r"\s+(?=[A-Za-z]{2,})(?!\*\*)", expr)[0]
    return expr.strip()


def decode_value(pid_def: dict, value_bytes: bytes):
    """Apply a PID's formula to a sequence of value bytes.

    Returns (value, kind) where kind is 'numeric', 'enum', 'partial', or
    'unknown'.
    """
    formula = pid_def["calc"]
    labels_by_position = pid_def.get("labels_by_position", {})
    if not formula:
        return None, "unknown"

    # Build {label: byte} from positions and available bytes
    env = {}
    missing = []
    for pos, label in labels_by_position.items():
        if pos < len(value_bytes):
            env[label] = int(value_bytes[pos])
        else:
            missing.append(label)

    # Enum form (e.g. "XX = 0 => standby, XX = 1 => driving, ...")
    if "=>" in formula:
        mapping = {}
        for m in re.finditer(
            r"([A-Z]{2})\s*=\s*(\d+)\s*=>\s*([^,;]+)", formula
        ):
            label, raw, label_val = m.group(1), int(m.group(2)), m.group(3).strip()
            if label in env:
                mapping[raw] = label_val
        if mapping:
            # Use first mapped label's value
            label = next(iter(re.findall(r"([A-Z]{2})\s*=\s*\d+\s*=>", formula)))
            if label in env:
                return mapping.get(env[label], f"unknown({env[label]})"), "enum"

    # Numeric: normalize to Python expression and eval
    expr = normalize_formula(formula)
    if not expr:
        return None, "unknown"
    referenced = [ph for ph in PLACEHOLDERS if ph in expr]
    if not referenced:
        return None, "unknown"

    # Substitute missing labels with 0 to allow partial decode of multi-frame
    eval_env = {ph: env.get(ph, 0) for ph in referenced}
    is_partial = any(ph not in env for ph in referenced)
    try:
        value = eval(expr, {"__builtins__": {}}, eval_env)
    except Exception:
        return None, "unknown"
    if not isinstance(value, (int, float)):
        return None, "unknown"
    return float(value), ("partial" if is_partial else "numeric")


# ── ISO-TP frame decoding ────────────────────────────────────

def decode_response_frame(payload: bytes):
    """Decode a single 8-byte response payload from 0x17FE007B.

    Returns dict with keys: kind ('SF'|'FF'|'CF'|'NEG'|'OTHER'),
    pid (or None), value_bytes (dict of XX/YY/ZZ/...), raw_bytes, length.
    """
    if len(payload) < 1:
        return {"kind": "OTHER"}
    pci = payload[0]
    high = (pci >> 4) & 0xF
    low = pci & 0xF

    if high == 0:  # Single Frame
        length = low
        sid = payload[1] if len(payload) > 1 else None
        if sid == 0x7F:  # Negative response
            return {
                "kind": "NEG",
                "pid": None,
                "raw_bytes": payload,
                "request_sid": payload[2] if len(payload) > 2 else None,
                "nrc": payload[3] if len(payload) > 3 else None,
            }
        if sid == 0x62 and len(payload) >= 4:  # Positive RDBI
            pid = (payload[2] << 8) | payload[3]
            value_bytes = bytes(payload[4 : 1 + length])
            return {"kind": "SF", "pid": pid, "value_bytes": value_bytes, "length": length}
        # Other positive response (e.g. 0x50 SessionControl, 0x7E TesterPresent)
        return {
            "kind": "OTHER",
            "sid": sid,
            "length": length,
            "raw_bytes": bytes(payload[: 1 + length]),
        }

    if high == 1:  # First Frame
        length = (low << 8) | payload[1]
        sid = payload[2] if len(payload) > 2 else None
        if sid == 0x62 and len(payload) >= 5:
            pid = (payload[3] << 8) | payload[4]
            value_bytes = bytes(payload[5:8])  # only the 3 value bytes in the FF
            return {
                "kind": "FF",
                "pid": pid,
                "value_bytes": value_bytes,
                "total_length": length,
                "partial": True,
            }
        return {"kind": "FF", "sid": sid, "total_length": length}

    if high == 2:  # Consecutive Frame
        return {"kind": "CF", "seq": low, "raw_bytes": payload[1:]}

    return {"kind": "OTHER"}


# ── Session loader ───────────────────────────────────────────

def find_response_groups(mdf: MDF, target_id: int):
    """Yield (group_index, channel_group_name) where ID matches target_id."""
    for i, g in enumerate(mdf.groups):
        if g.channel_group.cycles_nr == 0:
            continue
        name = g.channel_group.acq_name or ""
        if "CAN" not in name:
            continue
        ch_names = {c.name for c in g.channels}
        if "CAN_DataFrame.ID" not in ch_names:
            continue
        try:
            ids = np.asarray(mdf.get("CAN_DataFrame.ID", group=i).samples, dtype=np.int64)
        except Exception:
            continue
        if (ids == target_id).any():
            yield i, name, ids


def load_session_responses(mf4_path: Path, pids: dict):
    """Decode all 0x17FE007B responses from one MF4. Returns list of dicts."""
    mdf = MDF(str(mf4_path))
    decoded_records = []
    for gi, gname, ids in find_response_groups(mdf, BMS_RESPONSE_ID):
        ts = np.asarray(mdf.get("CAN_DataFrame.ID", group=gi).timestamps)
        data = np.asarray(mdf.get("CAN_DataFrame.DataBytes", group=gi).samples)
        mask = ids == BMS_RESPONSE_ID
        for t, payload in zip(ts[mask], data[mask]):
            if hasattr(payload, "tobytes"):
                payload = payload.tobytes()
            decoded = decode_response_frame(payload)
            decoded["timestamp"] = float(t)
            decoded["raw_hex"] = " ".join(f"{b:02X}" for b in payload)
            if decoded["kind"] in ("SF", "FF") and decoded.get("pid") in pids:
                pid_def = pids[decoded["pid"]]
                value, kind = decode_value(pid_def, decoded.get("value_bytes", b""))
                decoded["pid_name"] = pid_def["name"]
                decoded["pid_unit"] = pid_def["unit"]
                decoded["pid_group"] = pid_def["group"]
                decoded["value"] = value
                decoded["value_kind"] = kind
            decoded_records.append(decoded)
    return decoded_records


# ── Summary builders ─────────────────────────────────────────

def build_summary(records):
    """Aggregate decoded records into {pid: stats}. Skips records with no value."""
    summary = defaultdict(lambda: {
        "count": 0, "first_value": None, "last_value": None,
        "min": None, "max": None, "name": "", "unit": "", "kind": "",
    })
    for r in records:
        if r.get("value") is None:
            continue
        s = summary[r["pid"]]
        s["count"] += 1
        if s["first_value"] is None:
            s["first_value"] = r["value"]
        s["last_value"] = r["value"]
        s["name"] = r.get("pid_name", "")
        s["unit"] = r.get("pid_unit", "")
        s["kind"] = r.get("value_kind", "")
        if isinstance(r["value"], (int, float)):
            s["min"] = r["value"] if s["min"] is None else min(s["min"], r["value"])
            s["max"] = r["value"] if s["max"] is None else max(s["max"], r["value"])
    return dict(summary)


def write_summary(summary, path, header):
    """Write a per-PID summary table to a text file."""
    total = sum(s["count"] for s in summary.values())
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{header}\n")
        f.write(f"Total decoded values: {total}\n")
        f.write(f"Unique PIDs decoded: {len(summary)}\n\n")
        f.write(
            f"{'PID':<8} {'Name':<55} {'Unit':<8} {'count':>6} "
            f"{'min':>10} {'max':>10} {'last':>10}\n"
        )
        f.write("-" * 110 + "\n")
        for pid, s in sorted(summary.items()):
            mn = f"{s['min']:>10.3f}" if isinstance(s.get('min'), (int, float)) else f"{'':>10}"
            mx = f"{s['max']:>10.3f}" if isinstance(s.get('max'), (int, float)) else f"{'':>10}"
            lv = s['last_value']
            lvs = f"{lv:>10.3f}" if isinstance(lv, (int, float)) else f"{str(lv):>10}"
            f.write(
                f"0x{pid:04X}  {s['name'][:54]:<55} {s['unit'][:7]:<8} "
                f"{s['count']:>6} {mn} {mx} {lvs}\n"
            )


# ── Main pipeline ────────────────────────────────────────────

def find_all_mf4_files():
    """Return list of (session_label, path) for every MF4 under
    40_Experiments/Exprimental Data/mf4 and the SD-card dump."""
    files = []
    legacy = DATA_DIR / "mf4"
    if legacy.exists():
        for sub in sorted(legacy.iterdir()):
            mf4 = sub / "00000001.MF4"
            if mf4.exists():
                files.append((f"data_mf4/{sub.name}", mf4))
    sd = Path(r"D:\LOG\2A73E1CC")
    if sd.exists():
        for sub in sorted(sd.iterdir()):
            if not sub.is_dir():
                continue
            # Pick the first MF4 in the session folder (SD card can name it
            # 00000001.MF4, etc.)
            mf4s = sorted(sub.glob("*.MF4")) + sorted(sub.glob("*.mf4"))
            if mf4s:
                files.append((f"sd_2A73E1CC/{sub.name}", mf4s[0]))
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", help="filter to a single session label substring")
    args = parser.parse_args()

    print(f"Loading PID database from {PID_CSV.name} ...")
    pids = parse_pid_csv(PID_CSV)
    print(f"  Loaded {len(pids)} PIDs")

    files = find_all_mf4_files()
    if args.session:
        files = [f for f in files if args.session in f[0]]
    print(f"Processing {len(files)} MF4 files")

    all_records = []
    per_session_records = {}  # session label -> list of records

    for label, path in files:
        try:
            recs = load_session_responses(path, pids)
        except Exception as e:
            print(f"  {label}: ERROR {e}")
            continue
        decoded_count = sum(1 for r in recs if r.get("value") is not None)
        sf_count = sum(1 for r in recs if r["kind"] == "SF")
        ff_count = sum(1 for r in recs if r["kind"] == "FF")
        neg_count = sum(1 for r in recs if r["kind"] == "NEG")
        print(
            f"  {label}: {len(recs)} responses (SF={sf_count} FF={ff_count} "
            f"NEG={neg_count}, decoded={decoded_count})"
        )
        for r in recs:
            r["session"] = label
            all_records.append(r)
        per_session_records[label] = recs

    if not all_records:
        print("No responses decoded.")
        return

    # Per-session and merged CSV
    df = pd.DataFrame(all_records)
    df_decoded = df[df["value"].notna()].copy()
    merged_path = OUTPUT_DIR / "all_sessions.csv"
    keep_cols = [
        "session", "timestamp", "kind", "pid", "pid_name", "pid_unit", "pid_group",
        "value", "value_kind", "raw_hex",
    ]
    df_decoded[keep_cols].to_csv(merged_path, index=False)
    print(f"Wrote {merged_path} ({len(df_decoded)} decoded rows)")

    for label in df["session"].unique():
        sub = df[df["session"] == label]
        out = OUTPUT_DIR / f"{label.replace('/', '__')}.csv"
        sub.to_csv(out, index=False)

    # Per-session summaries — one .txt per session so non-contiguous sessions
    # (different days, different drives) keep their stats separated.
    for label, recs in per_session_records.items():
        s = build_summary(recs)
        if not s:
            continue
        sess_summary_path = OUTPUT_DIR / f"{label.replace('/', '__')}__summary.txt"
        write_summary(
            s,
            sess_summary_path,
            header=f"VW MEB UDS Battery Decoder Summary — session {label}",
        )
        print(f"Wrote {sess_summary_path}")

    # Merged summary across all decoded sessions
    merged_summary = build_summary(all_records)
    summary_path = OUTPUT_DIR / "summary.txt"
    write_summary(
        merged_summary,
        summary_path,
        header=(
            "VW MEB UDS Battery Decoder Summary — merged across sessions: "
            + ", ".join(sorted(per_session_records.keys()))
        ),
    )
    print(f"Wrote {summary_path}")

    # Plot each PID over merged time
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("matplotlib unavailable, skipping plots")
        return

    for pid in sorted(merged_summary):
        sub = df_decoded[df_decoded["pid"] == pid]
        if sub.empty:
            continue
        fig, ax = plt.subplots(figsize=(10, 4))
        for label, grp in sub.groupby("session"):
            ax.plot(grp["timestamp"], grp["value"], "o-", markersize=2, label=label)
        meta = merged_summary[pid]
        ax.set_title(f"0x{pid:04X}  {meta['name']}  [{meta['unit']}]")
        ax.set_xlabel("timestamp (s within session)")
        ax.set_ylabel(meta["unit"] or "value")
        ax.grid(alpha=0.3)
        if len(sub["session"].unique()) <= 6:
            ax.legend(fontsize=7, loc="best")
        fname = OUTPUT_DIR / "plots" / f"pid_0x{pid:04X}.png"
        fig.tight_layout()
        fig.savefig(fname, dpi=110)
        plt.close(fig)
    print(f"Wrote {len(merged_summary)} plots to {OUTPUT_DIR / 'plots'}")


if __name__ == "__main__":
    main()
