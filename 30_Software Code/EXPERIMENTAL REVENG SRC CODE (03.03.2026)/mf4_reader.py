"""
MF4 Data Reader
Reads MF4 (ASAM MDF4) CAN bus log files into pandas DataFrames.

Usage:
    from mf4_reader import load_file, load_all, get_messages_by_id

    df = load_all()
    msgs = get_messages_by_id(df, 0x065)
"""

import os
import glob
from pathlib import Path
from asammdf import MDF
import pandas as pd

# Project root is one level up from src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "mf4"
OUTPUT_DIR = PROJECT_ROOT / "output"


# ── Column name cleanup ──────────────────────────────────────

# Map the verbose asammdf column names to short, clean names
_COLUMN_RENAMES = {
    "CAN_DataFrame.CAN_DataFrame.BusChannel": "bus_channel",
    "CAN_DataFrame.CAN_DataFrame.ID": "can_id",
    "CAN_DataFrame.CAN_DataFrame.IDE": "ide",
    "CAN_DataFrame.CAN_DataFrame.DLC": "dlc",
    "CAN_DataFrame.CAN_DataFrame.DataLength": "data_length",
    "CAN_DataFrame.CAN_DataFrame.DataBytes": "data_bytes",
    "CAN_DataFrame.CAN_DataFrame.Dir": "direction",
}


def _clean_columns(df):
    """Rename verbose asammdf columns to short names."""
    renamed = {}
    for old, new in _COLUMN_RENAMES.items():
        if old in df.columns:
            renamed[old] = new
    return df.rename(columns=renamed)


def _bytes_to_hex(data):
    """Convert raw data bytes to a hex string like '0A 1B 2C ...'."""
    if isinstance(data, (bytes, bytearray)):
        return " ".join(f"{b:02X}" for b in data)
    # Handle numpy arrays from asammdf
    if hasattr(data, "__iter__") and not isinstance(data, str):
        try:
            return " ".join(f"{int(b):02X}" for b in data)
        except (TypeError, ValueError):
            pass
    if isinstance(data, str):
        return data
    return str(data)


# ── Core functions ────────────────────────────────────────────

def find_mf4_files(log_dir=None):
    """Find all MF4 files in the data directory."""
    if log_dir is None:
        log_dir = str(DATA_DIR)
    pattern = os.path.join(log_dir, "**", "*.MF4")
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        pattern = os.path.join(log_dir, "**", "*.mf4")
        files = sorted(glob.glob(pattern, recursive=True))
    return files


def inspect_file(file_path):
    """Print channel/group structure of an MF4 file."""
    mdf = MDF(file_path)
    print(f"File: {file_path}  (MDF v{mdf.version})")
    print("-" * 50)
    for i, group in enumerate(mdf.groups):
        channels = [ch.name for ch in group.channels if ch.name != "Timestamp"]
        if channels:
            print(f"  Group {i:2d}: {', '.join(channels)}")
    return mdf


def load_file(file_path):
    """
    Load a single MF4 file into a clean DataFrame.

    Returns a DataFrame with columns:
        bus_channel, can_id, ide, dlc, data_length, data_bytes, direction, data_hex
    Index is the timestamp (seconds).
    """
    mdf = MDF(file_path)
    df = mdf.to_dataframe()
    df = _clean_columns(df)

    # Add human-readable hex columns
    if "data_bytes" in df.columns:
        df["data_hex"] = df["data_bytes"].apply(_bytes_to_hex)
    if "can_id" in df.columns:
        df["can_id_hex"] = df["can_id"].apply(lambda x: f"0x{int(x):03X}")

    df.index.name = "timestamp"
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
    counts = df.groupby("can_id").size().reset_index(name="count")
    counts["can_id_hex"] = counts["can_id"].apply(lambda x: f"0x{int(x):03X}")
    counts = counts.sort_values("count", ascending=False).reset_index(drop=True)
    return counts[["can_id_hex", "can_id", "count"]]


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
