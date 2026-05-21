"""
MF4 Data Reader
Reads MF4 (ASAM MDF4) CAN bus log files into pandas DataFrames.

Iterates over every CAN_DataFrame channel group so standard-ID frames
(CAN1_Rx / CAN9_Rx / CAN1_Tx) AND extended-ID frames (CAN1_Rx_IDE,
CAN1_Tx_IDE) are captured. Earlier versions used mdf.to_dataframe()
which silently dropped extended-ID groups, hiding all UDS traffic.

Usage:
    from mf4_reader import load_file, load_all, get_messages_by_id

    df = load_all()
    msgs = get_messages_by_id(df, 0x17FE007B)
"""

import os
import glob
from pathlib import Path

import numpy as np
import pandas as pd
from asammdf import MDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_DATA_DIR = PROJECT_ROOT / "40_Experiments" / "Exprimental Data"
DATA_DIR = EXPERIMENT_DATA_DIR / "mf4"
SD_DUMP_DIR = EXPERIMENT_DATA_DIR / "sd_dumps_2A73E1CC_20250409" / "LOG" / "2A73E1CC"
OUTPUT_DIR = PROJECT_ROOT / "40_Experiments" / "Exprimental Plots"


def _bytes_to_hex(data):
    """Convert raw data bytes to a hex string like '0A 1B 2C ...'."""
    if isinstance(data, (bytes, bytearray)):
        return " ".join(f"{b:02X}" for b in data)
    if hasattr(data, "__iter__") and not isinstance(data, str):
        try:
            return " ".join(f"{int(b):02X}" for b in data)
        except (TypeError, ValueError):
            pass
    if isinstance(data, str):
        return data
    return str(data)


def _id_hex(can_id, ide):
    """Format a CAN ID as 11-bit (0xNNN) or 29-bit (0xNNNNNNNN) hex."""
    iv = int(can_id)
    return f"0x{iv:08X}" if ide else f"0x{iv:03X}"


# ── Core functions ────────────────────────────────────────────

def find_mf4_files(log_dir=None):
    """Find every MF4 in the data directory (and the SD card dump if present).

    log_dir=None searches both data/mf4 and CANedge 09042025/LOG/2A73E1CC.
    """
    if log_dir is not None:
        roots = [str(log_dir)]
    else:
        roots = [str(DATA_DIR)]
        if SD_DUMP_DIR.exists():
            roots.append(str(SD_DUMP_DIR))
    files = []
    for root in roots:
        for ext in ("*.MF4", "*.mf4"):
            pattern = os.path.join(root, "**", ext)
            files.extend(glob.glob(pattern, recursive=True))
    return sorted(set(files))


def inspect_file(file_path):
    """Print every non-empty channel group in an MF4 file."""
    mdf = MDF(file_path)
    print(f"File: {file_path}  (MDF v{mdf.version})")
    print("-" * 60)
    for i, group in enumerate(mdf.groups):
        n = group.channel_group.cycles_nr
        if n == 0:
            continue
        name = group.channel_group.acq_name or ""
        print(f"  Group {i:3d} [{name}]: {n} cycles")
    return mdf


def _extract_can_group(mdf: MDF, group_idx: int, frame_class: str = "CAN_DataFrame"):
    """Return a DataFrame for one CAN channel group, or None if empty/wrong type."""
    g = mdf.groups[group_idx]
    if g.channel_group.cycles_nr == 0:
        return None
    ch_names = {c.name for c in g.channels}
    id_ch = f"{frame_class}.ID"
    if id_ch not in ch_names:
        return None
    cols = {}
    try:
        sig_id = mdf.get(id_ch, group=group_idx)
        cols["can_id"] = np.asarray(sig_id.samples, dtype=np.int64)
        ts = np.asarray(sig_id.timestamps, dtype=np.float64)
    except Exception:
        return None
    for ch_short, col in [
        ("BusChannel", "bus_channel"),
        ("IDE", "ide"),
        ("DLC", "dlc"),
        ("DataLength", "data_length"),
        ("Dir", "direction"),
    ]:
        full = f"{frame_class}.{ch_short}"
        if full in ch_names:
            try:
                cols[col] = np.asarray(mdf.get(full, group=group_idx).samples)
            except Exception:
                pass
    data_ch = f"{frame_class}.DataBytes"
    if data_ch in ch_names:
        try:
            samples = mdf.get(data_ch, group=group_idx).samples
            cols["data_bytes"] = [
                bytes(s.tobytes() if hasattr(s, "tobytes") else s) for s in samples
            ]
        except Exception:
            pass
    df = pd.DataFrame(cols, index=pd.Index(ts, name="timestamp"))
    df["channel_group"] = g.channel_group.acq_name or ""
    return df


def load_file(file_path, include_remote=False, include_errors=False):
    """Load a single MF4 file. Iterates EVERY CAN_DataFrame channel group so
    extended-ID frames are not dropped.

    Returns DataFrame with columns:
        bus_channel, can_id, ide, dlc, data_length, direction, data_bytes,
        channel_group, data_hex, can_id_hex
    Index is timestamp (seconds within the recording).
    """
    mdf = MDF(file_path)
    parts = []
    for i, g in enumerate(mdf.groups):
        if g.channel_group.cycles_nr == 0:
            continue
        name = g.channel_group.acq_name or ""
        if "CAN_DataFrame" in {c.name.split(".")[0] for c in g.channels}:
            sub = _extract_can_group(mdf, i, "CAN_DataFrame")
            if sub is not None and not sub.empty:
                parts.append(sub)
        elif include_remote and "RemoteFrame" in name:
            sub = _extract_can_group(mdf, i, "CAN_RemoteFrame")
            if sub is not None and not sub.empty:
                sub["frame_kind"] = "remote"
                parts.append(sub)
        elif include_errors and "Error" in name:
            # Error frames have a different schema - just record timestamps + type
            try:
                err_type = mdf.get("CAN_ErrorFrame.ErrorType", group=i)
                bus = mdf.get("CAN_ErrorFrame.BusChannel", group=i)
                df_err = pd.DataFrame(
                    {
                        "bus_channel": np.asarray(bus.samples),
                        "error_type": np.asarray(err_type.samples),
                        "channel_group": name,
                        "frame_kind": "error",
                    },
                    index=pd.Index(np.asarray(err_type.timestamps), name="timestamp"),
                )
                parts.append(df_err)
            except Exception:
                pass
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts).sort_index()
    if "data_bytes" in df.columns:
        df["data_hex"] = df["data_bytes"].apply(
            lambda b: _bytes_to_hex(b) if isinstance(b, (bytes, bytearray)) else ""
        )
    if "can_id" in df.columns:
        ide_col = df["ide"] if "ide" in df.columns else 0
        df["can_id_hex"] = [
            _id_hex(cid, int(ide) if pd.notna(ide) else 0)
            for cid, ide in zip(df["can_id"], (ide_col if hasattr(ide_col, '__iter__') else [0]*len(df)))
        ]
    return df


def load_all(log_dir=None):
    """
    Load all MF4 files and merge into one DataFrame.
    Adds a 'source' column with the parent folder name (e.g. '00000002').
    """
    files = find_mf4_files(log_dir)
    if not files:
        print("No MF4 files found.")
        return pd.DataFrame()

    frames = []
    for f in files:
        df = load_file(f)
        df["source"] = Path(f).parent.name
        frames.append(df)

    merged = pd.concat(frames, axis=0).sort_index()
    return merged


# ── CAN-specific helpers ──────────────────────────────────────

def get_messages_by_id(df, can_id):
    """Filter DataFrame for a specific CAN ID (int or hex)."""
    return df[df["can_id"] == can_id]


def list_unique_ids(df):
    """List all unique CAN IDs in the DataFrame with message counts."""
    if "ide" in df.columns:
        counts = df.groupby(["can_id", "ide"]).size().reset_index(name="count")
        counts["can_id_hex"] = [
            _id_hex(c, i) for c, i in zip(counts["can_id"], counts["ide"])
        ]
    else:
        counts = df.groupby("can_id").size().reset_index(name="count")
        counts["can_id_hex"] = counts["can_id"].apply(lambda x: f"0x{int(x):03X}")
    counts = counts.sort_values("count", ascending=False).reset_index(drop=True)
    return counts[["can_id_hex", "can_id", "count"] + (["ide"] if "ide" in df.columns else [])]


def export_to_csv(df, output_path="output.csv"):
    """Export a DataFrame to CSV for use in other tools."""
    df.to_csv(output_path)
    print(f"Exported {len(df)} rows to {output_path}")


# ── Main entry point ──────────────────────────────────────────

if __name__ == "__main__":
    files = find_mf4_files()
    if not files:
        print(f"No MF4 files found in '{DATA_DIR}'.")
        raise SystemExit(1)

    print(f"Found {len(files)} MF4 file(s):\n")

    # Inspect first file structure
    inspect_file(files[0])

    # Load all files
    print(f"\n{'='*50}")
    print("Loading all files...")
    df = load_all()
    print(f"Total rows: {len(df)}")
    print(f"Time range: {df.index.min():.3f}s - {df.index.max():.3f}s")

    # Show unique CAN IDs
    print(f"\n{'='*50}")
    print("Unique CAN IDs:")
    ids = list_unique_ids(df)
    print(ids.to_string(index=False))

    # Preview data
    print(f"\n{'='*50}")
    print("Data preview (first 20 rows):")
    preview_cols = ["can_id_hex", "dlc", "data_hex", "source"]
    print(df[preview_cols].head(20).to_string())

    # Export to CSV
    export_to_csv(df, str(OUTPUT_DIR / "can_data.csv"))
