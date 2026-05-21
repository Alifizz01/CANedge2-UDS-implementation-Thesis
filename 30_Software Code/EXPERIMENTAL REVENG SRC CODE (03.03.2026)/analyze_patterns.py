"""
Reverse-engineer the unknown CAN IDs (0x065-0x06F) by analyzing
byte patterns, value ranges, frequencies, and correlations.
"""

import numpy as np
import pandas as pd
from mf4_reader import load_all


def byte_array_to_list(data):
    """Convert data_bytes to a list of ints."""
    return [int(b) for b in data]


def analyze_can_id(df, can_id):
    """Deep analysis of a single CAN ID's data patterns."""
    mask = df["can_id"] == can_id
    subset = df[mask].copy()
    hex_id = f"0x{int(can_id):03X}"

    print(f"\n{'='*70}")
    print(f"CAN ID: {hex_id}  ({len(subset)} messages)")
    print(f"{'='*70}")

    if subset.empty:
        return

    # Time analysis
    timestamps = subset.index.values
    if len(timestamps) > 1:
        intervals = np.diff(timestamps)
        print(f"\n  Timing:")
        print(f"    Time span:     {timestamps[0]:.3f}s - {timestamps[-1]:.3f}s")
        print(f"    Avg interval:  {np.mean(intervals)*1000:.1f} ms")
        print(f"    Std interval:  {np.std(intervals)*1000:.1f} ms")
        print(f"    Min interval:  {np.min(intervals)*1000:.1f} ms")
        print(f"    Max interval:  {np.max(intervals)*1000:.1f} ms")
        freq = 1.0 / np.mean(intervals) if np.mean(intervals) > 0 else 0
        print(f"    ~Frequency:    {freq:.1f} Hz")

    # DLC analysis
    dlc_vals = subset["dlc"].unique()
    print(f"\n  DLC: {sorted(dlc_vals)}")

    # Get all byte arrays
    byte_arrays = subset["data_bytes"].apply(byte_array_to_list).tolist()
    max_len = max(len(b) for b in byte_arrays)

    # Per-byte analysis
    print(f"\n  Per-byte analysis ({max_len} bytes):")
    print(f"  {'Byte':>6s} | {'Min':>5s} {'Max':>5s} {'Mean':>7s} {'Std':>7s} | {'Unique':>6s} | {'Hex Range':>12s} | Notes")
    print(f"  {'-'*6}-+-{'-'*5}-{'-'*5}-{'-'*7}-{'-'*7}-+-{'-'*6}-+-{'-'*12}-+------")

    byte_columns = {}
    for i in range(max_len):
        vals = [b[i] for b in byte_arrays if i < len(b)]
        vals = np.array(vals)
        byte_columns[i] = vals

        unique = len(np.unique(vals))
        notes = []

        if unique == 1:
            notes.append(f"CONSTANT={vals[0]:02X}")
        elif unique == 2:
            notes.append(f"BINARY: {sorted(np.unique(vals))}")
        elif unique <= 5:
            notes.append(f"FEW VALUES: {sorted(np.unique(vals))}")
        elif np.std(vals) < 1.0:
            notes.append("NEAR-CONSTANT")
        elif vals.min() == 0 and vals.max() == 255:
            notes.append("FULL RANGE")
        elif np.std(vals) > 70:
            notes.append("HIGH VARIANCE (random/encrypted?)")

        # Check for counter pattern
        if unique > 10:
            diffs = np.diff(vals.astype(int))
            if len(diffs) > 0:
                # Check if mostly incrementing by 1
                inc_by_1 = np.sum(diffs == 1)
                if inc_by_1 > len(diffs) * 0.8:
                    notes.append("COUNTER (incrementing)")
                # Check for wrapping counter
                elif inc_by_1 > len(diffs) * 0.5:
                    notes.append("COUNTER (wrapping)")

        note_str = ", ".join(notes)
        print(f"  B[{i:>2d}]  | {vals.min():5d} {vals.max():5d} {vals.mean():7.1f} {vals.std():7.1f} | {unique:6d} | 0x{vals.min():02X}-0x{vals.max():02X}   | {note_str}")

    # Check for common 16-bit signal patterns (big-endian)
    print(f"\n  Potential 16-bit signals (big-endian):")
    for i in range(max_len - 1):
        vals_16 = np.array([b[i] * 256 + b[i+1] for b in byte_arrays if len(b) > i+1])
        unique_16 = len(np.unique(vals_16))
        if unique_16 > 1 and unique_16 < len(vals_16) * 0.9:
            print(f"    B[{i}:{i+1}]: range {vals_16.min()}-{vals_16.max()}, "
                  f"mean={vals_16.mean():.1f}, std={vals_16.std():.1f}, "
                  f"unique={unique_16}")

    # Show first/last few raw frames
    print(f"\n  First 5 frames:")
    for ts, row in list(subset.iterrows())[:5]:
        print(f"    t={ts:10.5f}s  {row['data_hex']}")

    print(f"\n  Last 5 frames:")
    for ts, row in list(subset.iterrows())[-5:]:
        print(f"    t={ts:10.5f}s  {row['data_hex']}")

    # Check if data changes between sources
    if "source" in subset.columns:
        print(f"\n  Per-source breakdown:")
        for src in sorted(subset["source"].unique()):
            src_data = subset[subset["source"] == src]
            print(f"    Source {src}: {len(src_data)} messages, "
                  f"t={src_data.index.min():.1f}s-{src_data.index.max():.1f}s")

    return byte_columns


def check_correlations(df):
    """Check if any CAN IDs have correlated timing (sent together)."""
    print(f"\n{'='*70}")
    print("Cross-ID timing correlation")
    print(f"{'='*70}")

    ids = sorted(df["can_id"].unique())
    for i, id1 in enumerate(ids):
        for id2 in ids[i+1:]:
            ts1 = set(df[df["can_id"] == id1].index.values)
            ts2 = set(df[df["can_id"] == id2].index.values)
            common = ts1 & ts2
            if common:
                pct1 = len(common) / len(ts1) * 100 if ts1 else 0
                pct2 = len(common) / len(ts2) * 100 if ts2 else 0
                if pct1 > 30 or pct2 > 30:
                    print(f"  0x{int(id1):03X} <-> 0x{int(id2):03X}: "
                          f"{len(common)} shared timestamps "
                          f"({pct1:.0f}% of {int(id1):03X}, {pct2:.0f}% of {int(id2):03X})")


def check_all_zeros(df):
    """Check how many frames per ID are all-zeros."""
    print(f"\n{'='*70}")
    print("All-zeros check")
    print(f"{'='*70}")

    for can_id in sorted(df["can_id"].unique()):
        subset = df[df["can_id"] == can_id]
        zero_count = 0
        for _, row in subset.iterrows():
            if all(int(b) == 0 for b in row["data_bytes"]):
                zero_count += 1
        hex_id = f"0x{int(can_id):03X}"
        print(f"  {hex_id}: {zero_count}/{len(subset)} all-zero frames "
              f"({zero_count/len(subset)*100:.0f}%)")


if __name__ == "__main__":
    print("=== CAN ID Pattern Analysis ===")
    print("Loading data...")
    df = load_all()

    check_all_zeros(df)
    check_correlations(df)

    for can_id in sorted(df["can_id"].unique()):
        analyze_can_id(df, can_id)
