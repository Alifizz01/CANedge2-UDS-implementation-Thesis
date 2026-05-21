"""
CAN Signal Reverse Engineering for VW ID Buzz
Analyzes raw CAN data to identify and decode signals without a DBC file.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from mf4_reader import load_all, OUTPUT_DIR as PROJECT_OUTPUT
import os

OUTPUT_DIR = str(PROJECT_OUTPUT / "plots")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def parse_data_bytes(val):
    """Parse data_bytes column from various formats."""
    if isinstance(val, (list, np.ndarray)):
        return [int(b) for b in val]
    s = str(val).strip()
    if s.startswith('[') and s.endswith(']'):
        parts = s[1:-1].split()
        return [int(x) for x in parts]
    return []


def prepare_df(df):
    """Add parsed byte columns to the dataframe."""
    df = df.copy()
    df['bytes_list'] = df['data_bytes'].apply(parse_data_bytes)
    max_dlc = df['bytes_list'].apply(len).max()
    for i in range(max_dlc):
        df[f'b{i}'] = df['bytes_list'].apply(lambda x: x[i] if i < len(x) else np.nan)
    return df


# =============================================================================
# 1. Byte Time Series Plots (per CAN ID, per source)
# =============================================================================
def plot_byte_timeseries(df, can_id, source=None):
    """Plot each byte over time for a CAN ID."""
    hex_id = f"0x{int(can_id):03X}"
    mask = df['can_id'] == can_id
    if source is not None:
        mask &= df['source'] == source
    sub = df[mask].copy()
    if sub.empty:
        return

    dlc = int(sub['dlc'].iloc[0])
    active_bytes = dlc  # only plot DLC-many bytes

    fig, axes = plt.subplots(active_bytes, 1, figsize=(14, 2.5 * active_bytes),
                             sharex=True)
    if active_bytes == 1:
        axes = [axes]

    title = f"CAN {hex_id} - Byte Time Series"
    if source:
        title += f" (source {source})"
    fig.suptitle(title, fontsize=14, fontweight='bold')

    ts = sub.index.values

    for i in range(active_bytes):
        ax = axes[i]
        vals = sub[f'b{i}'].values
        ax.plot(ts, vals, '.', markersize=1.5, alpha=0.7)
        ax.set_ylabel(f'B[{i}]\n(0x{int(np.nanmin(vals)):02X}-0x{int(np.nanmax(vals)):02X})',
                       fontsize=8)
        ax.set_ylim(-5, 260)
        ax.axhline(y=0, color='gray', linewidth=0.3)
        ax.axhline(y=255, color='gray', linewidth=0.3)

        # Annotate constant/near-constant bytes
        unique = len(np.unique(vals[~np.isnan(vals)]))
        if unique == 1:
            ax.text(0.98, 0.8, f'CONST=0x{int(vals[0]):02X}',
                    transform=ax.transAxes, ha='right', fontsize=9,
                    color='red', fontweight='bold')
        elif unique <= 5:
            uvals = sorted(np.unique(vals[~np.isnan(vals)]).astype(int))
            ax.text(0.98, 0.8, f'{unique} vals: {uvals}',
                    transform=ax.transAxes, ha='right', fontsize=8, color='blue')

    axes[-1].set_xlabel('Time (s)')
    plt.tight_layout()
    suffix = f"_{source}" if source else ""
    plt.savefig(f"{OUTPUT_DIR}/{hex_id}_bytes{suffix}.png", dpi=150)
    plt.close()
    print(f"  Saved {hex_id}_bytes{suffix}.png")


# =============================================================================
# 2. 16-bit Signal Combinations (Big-Endian / Motorola)
# =============================================================================
def plot_16bit_signals(df, can_id, source=None):
    """Try all adjacent 16-bit BE combinations and plot promising ones."""
    hex_id = f"0x{int(can_id):03X}"
    mask = df['can_id'] == can_id
    if source is not None:
        mask &= df['source'] == source
    sub = df[mask].copy()
    if sub.empty:
        return

    dlc = int(sub['dlc'].iloc[0])
    ts = sub.index.values

    promising = []
    for i in range(dlc - 1):
        hi = sub[f'b{i}'].values.astype(int)
        lo = sub[f'b{i+1}'].values.astype(int)
        val_be = hi * 256 + lo
        val_le = lo * 256 + hi

        for label, vals in [("BE", val_be), ("LE", val_le)]:
            unique = len(np.unique(vals))
            std = np.std(vals)
            # Promising if: not constant, not fully random, has structure
            if 3 < unique < len(vals) * 0.8 and std > 5:
                promising.append((i, label, vals, unique, std))

    if not promising:
        return

    fig, axes = plt.subplots(len(promising), 1,
                             figsize=(14, 2.5 * len(promising)), sharex=True)
    if len(promising) == 1:
        axes = [axes]

    title = f"CAN {hex_id} - 16-bit Signal Candidates"
    if source:
        title += f" (source {source})"
    fig.suptitle(title, fontsize=14, fontweight='bold')

    for idx, (i, label, vals, unique, std) in enumerate(promising):
        ax = axes[idx]
        ax.plot(ts, vals, '.', markersize=1.5, alpha=0.7)
        ax.set_ylabel(f'B[{i}:{i+1}] {label}\n{unique} uniq', fontsize=8)
        ax.text(0.98, 0.8, f'range: {vals.min()}-{vals.max()}, std={std:.0f}',
                transform=ax.transAxes, ha='right', fontsize=8, color='green')

    axes[-1].set_xlabel('Time (s)')
    plt.tight_layout()
    suffix = f"_{source}" if source else ""
    plt.savefig(f"{OUTPUT_DIR}/{hex_id}_16bit{suffix}.png", dpi=150)
    plt.close()
    print(f"  Saved {hex_id}_16bit{suffix}.png")


# =============================================================================
# 3. Nibble-level Counter Detection
# =============================================================================
def detect_counters(df, can_id, source=None):
    """Check each nibble for counter-like behavior."""
    hex_id = f"0x{int(can_id):03X}"
    mask = df['can_id'] == can_id
    if source is not None:
        mask &= df['source'] == source
    sub = df[mask].copy()
    if len(sub) < 10:
        return []

    dlc = int(sub['dlc'].iloc[0])
    counters = []

    for i in range(dlc):
        vals = sub[f'b{i}'].values.astype(int)

        # Check full byte as counter
        diffs = np.diff(vals)
        inc1 = np.sum(diffs == 1) / len(diffs) if len(diffs) > 0 else 0
        if inc1 > 0.7:
            counters.append(f"  B[{i}]: BYTE COUNTER (inc-by-1 {inc1*100:.0f}%)")

        # Check high nibble
        hi_nib = (vals >> 4) & 0x0F
        diffs_h = np.diff(hi_nib)
        inc_h = np.sum((diffs_h == 1) | (diffs_h == -15)) / len(diffs_h) if len(diffs_h) > 0 else 0
        if inc_h > 0.7:
            counters.append(f"  B[{i}] high nibble: 4-BIT COUNTER ({inc_h*100:.0f}%)")

        # Check low nibble
        lo_nib = vals & 0x0F
        diffs_l = np.diff(lo_nib)
        inc_l = np.sum((diffs_l == 1) | (diffs_l == -15)) / len(diffs_l) if len(diffs_l) > 0 else 0
        if inc_l > 0.7:
            counters.append(f"  B[{i}] low nibble: 4-BIT COUNTER ({inc_l*100:.0f}%)")

    if counters:
        print(f"\n  Counters found in {hex_id}:")
        for c in counters:
            print(c)
    return counters


# =============================================================================
# 4. Checksum Detection (XOR, sum mod 256)
# =============================================================================
def detect_checksum(df, can_id, source=None):
    """Check if the last byte is a checksum of preceding bytes."""
    hex_id = f"0x{int(can_id):03X}"
    mask = df['can_id'] == can_id
    if source is not None:
        mask &= df['source'] == source
    sub = df[mask].copy()
    if len(sub) < 10:
        return

    dlc = int(sub['dlc'].iloc[0])
    if dlc < 2:
        return

    results = []
    for check_byte in [dlc - 1, dlc - 2]:  # last and second-to-last
        actual = sub[f'b{check_byte}'].values.astype(int)
        preceding = [sub[f'b{i}'].values.astype(int) for i in range(check_byte)]

        if not preceding:
            continue

        # XOR of all preceding bytes
        xor_val = preceding[0].copy()
        for p in preceding[1:]:
            xor_val ^= p
        xor_match = np.sum(actual == xor_val) / len(actual)

        # SUM mod 256
        sum_val = np.zeros(len(actual), dtype=int)
        for p in preceding:
            sum_val = (sum_val + p) % 256
        sum_match = np.sum(actual == sum_val) / len(actual)

        # XOR with CAN ID
        xor_id = xor_val ^ (int(can_id) & 0xFF)
        xor_id_match = np.sum(actual == xor_id) / len(actual)

        if xor_match > 0.9:
            results.append(f"  B[{check_byte}]: XOR checksum ({xor_match*100:.0f}% match)")
        if sum_match > 0.9:
            results.append(f"  B[{check_byte}]: SUM checksum ({sum_match*100:.0f}% match)")
        if xor_id_match > 0.9:
            results.append(f"  B[{check_byte}]: XOR+ID checksum ({xor_id_match*100:.0f}% match)")

    if results:
        print(f"\n  Checksums in {hex_id}:")
        for r in results:
            print(r)
    return results


# =============================================================================
# 5. Bit-level Heatmap
# =============================================================================
def plot_bit_heatmap(df, can_id, source=None):
    """Show bit-level change frequency as a heatmap."""
    hex_id = f"0x{int(can_id):03X}"
    mask = df['can_id'] == can_id
    if source is not None:
        mask &= df['source'] == source
    sub = df[mask].copy()
    if len(sub) < 10:
        return

    dlc = int(sub['dlc'].iloc[0])

    # Calculate bit change rate between consecutive frames
    change_rates = np.zeros((dlc, 8))
    for byte_idx in range(dlc):
        vals = sub[f'b{byte_idx}'].values.astype(int)
        for bit in range(8):
            bits = (vals >> (7 - bit)) & 1
            changes = np.sum(np.diff(bits) != 0)
            change_rates[byte_idx, bit] = changes / (len(bits) - 1) if len(bits) > 1 else 0

    fig, ax = plt.subplots(figsize=(10, max(3, dlc * 0.6)))
    im = ax.imshow(change_rates, cmap='YlOrRd', aspect='auto', vmin=0, vmax=0.6)
    ax.set_xlabel('Bit (MSB -> LSB)')
    ax.set_ylabel('Byte')
    ax.set_yticks(range(dlc))
    ax.set_yticklabels([f'B[{i}]' for i in range(dlc)])
    ax.set_xticks(range(8))
    ax.set_xticklabels(['b7', 'b6', 'b5', 'b4', 'b3', 'b2', 'b1', 'b0'])

    # Add text annotations
    for i in range(dlc):
        for j in range(8):
            val = change_rates[i, j]
            color = 'white' if val > 0.35 else 'black'
            ax.text(j, i, f'{val:.2f}', ha='center', va='center',
                    fontsize=7, color=color)

    plt.colorbar(im, label='Bit change rate')
    title = f"CAN {hex_id} - Bit Change Heatmap"
    if source:
        title += f" (source {source})"
    ax.set_title(title, fontweight='bold')
    plt.tight_layout()
    suffix = f"_{source}" if source else ""
    plt.savefig(f"{OUTPUT_DIR}/{hex_id}_bits{suffix}.png", dpi=150)
    plt.close()
    print(f"  Saved {hex_id}_bits{suffix}.png")


# =============================================================================
# 6. ASCII Detection
# =============================================================================
def check_ascii(df, can_id):
    """Check if any bytes consistently contain ASCII characters."""
    hex_id = f"0x{int(can_id):03X}"
    mask = df['can_id'] == can_id
    sub = df[mask]
    if sub.empty:
        return

    dlc = int(sub['dlc'].iloc[0])
    print(f"\n  ASCII check for {hex_id}:")
    for i in range(dlc):
        vals = sub[f'b{i}'].values.astype(int)
        ascii_pct = np.sum((vals >= 0x20) & (vals <= 0x7E)) / len(vals) * 100
        if ascii_pct > 90:
            chars = [chr(v) for v in vals if 0x20 <= v <= 0x7E]
            unique_chars = sorted(set(chars))
            print(f"    B[{i}]: {ascii_pct:.0f}% ASCII, chars: {''.join(unique_chars)}")


# =============================================================================
# 7. Decode 0x066 - Clear Structure Visible
# =============================================================================
def decode_0x066(df):
    """
    0x066 analysis:
    B[0]: 0x01 or 0x03 (mode/state)
    B[1]: 0x00-0xFF (60 unique) - signal high byte?
    B[2]: 0x00-0xFF wrapping counter
    B[3]: 0x30-0x32 (48-50) - 3 values
    B[4]: CONST 0x54
    B[5]: CONST 0x2D
    """
    hex_id = "0x066"
    sub = df[df['can_id'] == 0x066].copy()
    if sub.empty:
        print(f"No data for {hex_id}")
        return

    ts = sub.index.values
    b0 = sub['b0'].values.astype(int)
    b1 = sub['b1'].values.astype(int)
    b2 = sub['b2'].values.astype(int)
    b3 = sub['b3'].values.astype(int)

    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(f"CAN {hex_id} - Signal Decoding Attempt", fontsize=14, fontweight='bold')

    # B[0]: state
    axes[0].plot(ts, b0, '.', markersize=3)
    axes[0].set_ylabel('B[0] State')
    axes[0].set_title('Mode/State: 0x01 vs 0x03')

    # B[2]: rolling counter
    axes[1].plot(ts, b2, '.', markersize=2, alpha=0.7)
    axes[1].set_ylabel('B[2] Counter')
    axes[1].set_title('Wrapping byte counter (0x00-0xFF)')

    # B[1]: signal - try as part of 16-bit with counter removed
    axes[2].plot(ts, b1, '.', markersize=2, alpha=0.7, label='B[1] raw')
    axes[2].set_ylabel('B[1] Value')
    axes[2].set_title('Signal byte - potential measurement high byte')
    axes[2].legend()

    # B[3]: 48-50 range
    axes[3].plot(ts, b3, '.', markersize=3)
    axes[3].set_ylabel('B[3]')
    axes[3].set_title('B[3]: 48-50 (ASCII 0-2, or temp offset?)')

    axes[-1].set_xlabel('Time (s)')
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/{hex_id}_decoded.png", dpi=150)
    plt.close()
    print(f"  Saved {hex_id}_decoded.png")

    # Try decoding B[3] as temperature
    print(f"\n  {hex_id} B[3] interpretation:")
    print(f"    Raw range: {b3.min()}-{b3.max()}")
    print(f"    As temp (offset -40): {b3.min()-40}C to {b3.max()-40}C")
    print(f"    As temp (offset  0): {b3.min()}C to {b3.max()}C")
    print(f"    As ASCII: {chr(b3.min())}-{chr(b3.max())}")


# =============================================================================
# 8. Decode 0x067 - Detailed Signal Analysis
# =============================================================================
def decode_0x067(df):
    """
    0x067 structure:
    B[0]: varies widely - signal or multiplexer
    B[1]: 11-36 narrow range
    B[2]: CONST 0x8A (138)
    B[3]: 8 values, step pattern (0x10,0x30,0x50,0x70,0x90,0xB0,0xD0,0xF0?)
    B[4]: 0x00-0xFE, 223 unique - main signal
    B[5]: 51-53, 3 values
    B[6]: CONST 0x6D
    B[7]: 0x09-0xFD, 32 unique
    """
    sub = df[df['can_id'] == 0x067].copy()
    if sub.empty:
        return

    ts = sub.index.values
    fig, axes = plt.subplots(5, 1, figsize=(14, 12), sharex=True)
    fig.suptitle("CAN 0x067 - Signal Decoding", fontsize=14, fontweight='bold')

    b0 = sub['b0'].values.astype(int)
    b1 = sub['b1'].values.astype(int)
    b3 = sub['b3'].values.astype(int)
    b4 = sub['b4'].values.astype(int)
    b5 = sub['b5'].values.astype(int)
    b7 = sub['b7'].values.astype(int)

    axes[0].plot(ts, b0, '.', markersize=2)
    axes[0].set_ylabel('B[0]')
    axes[0].set_title('B[0]: High variance signal (0x01-0xFF)')

    axes[1].plot(ts, b1, '.', markersize=2)
    axes[1].set_ylabel('B[1]')
    axes[1].set_title('B[1]: Narrow range 11-36')

    axes[2].plot(ts, b3, '.', markersize=2)
    axes[2].set_ylabel('B[3]')
    axes[2].set_title('B[3]: Step values (8 levels)')

    axes[3].plot(ts, b4, '.', markersize=2)
    axes[3].set_ylabel('B[4]')
    axes[3].set_title('B[4]: Main signal (223 unique, 0x00-0xFE)')

    # B[4] as smooth signal - try with B[3] high nibble as extension
    b3_hi = (b3 >> 4) & 0x0F
    combined = b3_hi * 256 + b4
    axes[4].plot(ts, combined, '.', markersize=2)
    axes[4].set_ylabel('B[3]hi:B[4]')
    axes[4].set_title('12-bit signal: B[3] high nibble + B[4]')

    axes[-1].set_xlabel('Time (s)')
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/0x067_decoded.png", dpi=150)
    plt.close()
    print(f"  Saved 0x067_decoded.png")

    # Print B[5] interpretation (same pattern as 0x066 B[3])
    print(f"\n  0x067 B[5] range: {b5.min()}-{b5.max()}")
    print(f"    As temp (offset -40): {b5.min()-40}C to {b5.max()-40}C")


# =============================================================================
# 9. Decode 0x068 - 4-byte message
# =============================================================================
def decode_0x068(df):
    sub = df[df['can_id'] == 0x068].copy()
    if sub.empty:
        return

    ts = sub.index.values
    b0 = sub['b0'].values.astype(int)
    b1 = sub['b1'].values.astype(int)
    b2 = sub['b2'].values.astype(int)
    b3 = sub['b3'].values.astype(int)

    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
    fig.suptitle("CAN 0x068 - Signal Decoding", fontsize=14, fontweight='bold')

    axes[0].plot(ts, b0, '.', markersize=2)
    axes[0].set_ylabel('B[0]')
    axes[0].set_title('B[0]: Main varying signal (117 unique)')

    axes[1].plot(ts, b1, '.', markersize=2)
    axes[1].set_ylabel('B[1]')
    axes[1].set_title('B[1]: Narrow range 244-246 (0xF4-0xF6)')
    axes[1].set_ylim(240, 250)

    axes[2].plot(ts, b2, '.', markersize=2)
    axes[2].set_ylabel('B[2]')
    axes[2].set_title('B[2]: Varying 17-233 (23 unique values)')

    axes[3].plot(ts, b3, '.', markersize=3)
    axes[3].set_ylabel('B[3]')
    axes[3].set_title('B[3]: Binary flag (0 or 1)')

    axes[-1].set_xlabel('Time (s)')
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/0x068_decoded.png", dpi=150)
    plt.close()
    print(f"  Saved 0x068_decoded.png")

    # B[1] interpretation
    print(f"\n  0x068 B[1] range: {b1.min()}-{b1.max()}")
    print(f"    As temp (offset -40): {b1.min()-40}C to {b1.max()-40}C")
    print(f"    As temp * 0.5 - 40:  {b1.min()*0.5-40}C to {b1.max()*0.5-40}C")


# =============================================================================
# 10. Entropy per source for 0x06F
# =============================================================================
def analyze_06f_per_source(df):
    """0x06F has data from all 4 sources - compare them."""
    sub = df[df['can_id'] == 0x06F].copy()
    if sub.empty:
        return

    sources = sorted(sub['source'].unique())
    print(f"\n{'='*70}")
    print("0x06F per-source analysis")
    print(f"{'='*70}")

    fig, axes = plt.subplots(len(sources), 8, figsize=(20, 3 * len(sources)))
    if len(sources) == 1:
        axes = [axes]

    for si, src in enumerate(sources):
        src_data = sub[sub['source'] == src]
        ts = src_data.index.values
        print(f"\n  Source {src}: {len(src_data)} msgs, {ts.min():.1f}s-{ts.max():.1f}s")

        for bi in range(8):
            vals = src_data[f'b{bi}'].values.astype(int)
            unique = len(np.unique(vals))
            std = np.std(vals)
            print(f"    B[{bi}]: min={vals.min():3d} max={vals.max():3d} "
                  f"std={std:6.1f} unique={unique:3d}")

            axes[si][bi].plot(ts, vals, '.', markersize=1, alpha=0.5)
            axes[si][bi].set_ylim(-5, 260)
            if si == 0:
                axes[si][bi].set_title(f'B[{bi}]', fontsize=9)
            if bi == 0:
                axes[si][bi].set_ylabel(f'Src {src}', fontsize=8)

    plt.suptitle("CAN 0x06F - All Sources Comparison", fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/0x06F_sources.png", dpi=150)
    plt.close()
    print(f"  Saved 0x06F_sources.png")


# =============================================================================
# 11. Signal Boundary Detection via bit correlation
# =============================================================================
def detect_signal_boundaries(df, can_id, source=None):
    """Find signal boundaries by looking at bit-level correlation between
    adjacent bits. Bits within the same signal tend to be correlated."""
    hex_id = f"0x{int(can_id):03X}"
    mask = df['can_id'] == can_id
    if source is not None:
        mask &= df['source'] == source
    sub = df[mask].copy()
    if len(sub) < 20:
        return

    dlc = int(sub['dlc'].iloc[0])

    # Extract all bits into a matrix
    n = len(sub)
    total_bits = dlc * 8
    bit_matrix = np.zeros((n, total_bits), dtype=int)

    for byte_idx in range(dlc):
        vals = sub[f'b{byte_idx}'].values.astype(int)
        for bit in range(8):
            col = byte_idx * 8 + bit
            bit_matrix[:, col] = (vals >> (7 - bit)) & 1

    # Calculate correlation between adjacent bits
    correlations = []
    for i in range(total_bits - 1):
        # Use co-change rate: how often do adjacent bits change at the same time?
        changes_i = np.diff(bit_matrix[:, i]) != 0
        changes_j = np.diff(bit_matrix[:, i + 1]) != 0
        if np.sum(changes_i) > 0 and np.sum(changes_j) > 0:
            co_change = np.sum(changes_i & changes_j) / max(np.sum(changes_i), np.sum(changes_j))
        else:
            co_change = 0
        correlations.append(co_change)

    # Plot correlation to visualize signal boundaries
    fig, ax = plt.subplots(figsize=(14, 4))
    x = range(len(correlations))
    ax.bar(x, correlations, width=1.0, color='steelblue', alpha=0.7)

    # Mark byte boundaries
    for byte_b in range(1, dlc):
        ax.axvline(x=byte_b * 8 - 0.5, color='red', linewidth=1, linestyle='--', alpha=0.5)

    ax.set_xlabel('Bit position')
    ax.set_ylabel('Adjacent bit co-change rate')
    title = f"CAN {hex_id} - Signal Boundary Detection"
    if source:
        title += f" (source {source})"
    ax.set_title(title, fontweight='bold')

    # Label byte boundaries
    for byte_b in range(dlc):
        ax.text(byte_b * 8 + 3.5, ax.get_ylim()[1] * 0.95, f'B[{byte_b}]',
                ha='center', fontsize=8, color='red')

    plt.tight_layout()
    suffix = f"_{source}" if source else ""
    plt.savefig(f"{OUTPUT_DIR}/{hex_id}_boundaries{suffix}.png", dpi=150)
    plt.close()
    print(f"  Saved {hex_id}_boundaries{suffix}.png")


# =============================================================================
# 12. Scaling Factor Guesser
# =============================================================================
def guess_scaling(df, can_id, byte_indices, endian='big', source=None):
    """Try common automotive scaling factors on a multi-byte signal."""
    hex_id = f"0x{int(can_id):03X}"
    mask = df['can_id'] == can_id
    if source:
        mask &= df['source'] == source
    sub = df[mask]
    if sub.empty:
        return

    # Combine bytes
    vals = np.zeros(len(sub))
    if endian == 'big':
        for i, bi in enumerate(byte_indices):
            shift = (len(byte_indices) - 1 - i) * 8
            vals += sub[f'b{bi}'].values.astype(int) * (2 ** shift)
    else:
        for i, bi in enumerate(byte_indices):
            shift = i * 8
            vals += sub[f'b{bi}'].values.astype(int) * (2 ** shift)

    raw_min, raw_max = vals.min(), vals.max()
    print(f"\n  {hex_id} B{byte_indices} ({endian}-endian): raw {raw_min:.0f}-{raw_max:.0f}")

    # Common VW scaling factors
    scalings = [
        (0.01, 0, "km/h (raw*0.01)"),
        (0.1, 0, "km/h (raw*0.1)"),
        (1, -40, "temp C (raw-40)"),
        (0.5, -40, "temp C (raw*0.5-40)"),
        (0.1, -40, "temp C (raw*0.1-40)"),
        (1, -50, "temp C (raw-50)"),
        (0.01, 0, "voltage (raw*0.01 V)"),
        (0.1, 0, "% (raw*0.1)"),
        (0.5, 0, "% (raw*0.5)"),
        (0.001, 0, "generic (raw*0.001)"),
        (1, 0, "raw"),
    ]

    print(f"  {'Scaling':<30s} {'Min':>10s} {'Max':>10s} {'Plausible?'}")
    print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10}")
    for factor, offset, desc in scalings:
        phys_min = raw_min * factor + offset
        phys_max = raw_max * factor + offset
        # Check plausibility
        plausible = ""
        if "km/h" in desc and 0 <= phys_min <= 300 and 0 <= phys_max <= 300:
            plausible = "YES - speed"
        elif "temp" in desc and -50 <= phys_min <= 100 and -50 <= phys_max <= 100:
            plausible = "YES - temperature"
        elif "voltage" in desc and 0 <= phys_min <= 900 and 0 <= phys_max <= 900:
            plausible = "YES - voltage"
        elif "%" in desc and 0 <= phys_min <= 100 and 0 <= phys_max <= 100:
            plausible = "YES - percentage"
        print(f"  {desc:<30s} {phys_min:10.2f} {phys_max:10.2f} {plausible}")


# =============================================================================
# 13. Summary Report
# =============================================================================
def print_summary(df):
    """Print a structured summary of all findings."""
    print(f"\n{'#'*70}")
    print("# REVERSE ENGINEERING SUMMARY")
    print(f"{'#'*70}")

    print("""
CAN ID  | DLC | Freq  | Source(s) | Notes
--------|-----|-------|-----------|------
0x065   |  1  | ~9 Hz | ALL       | Heartbeat/status. B[0] has 9 states, rest zeros.
0x066   |  6  | ~5 Hz | 00000004  | Measurement msg. B[0]=state, B[2]=counter, B[3]=value(48-50)
0x067   |  8  | ~4.5Hz| 00000004  | Multi-signal. B[2]=CONST 0x8A, B[6]=CONST 0x6D
0x068   |  4  | ~4.5Hz| 00000004  | Measurement. B[1]=244-246 (temp?), B[3]=binary flag
0x06A   |  ?  | rare  | 00000004  | Only 126 messages - event-based?
0x06B   |  5  | ~4.5Hz| 00000004  | B[3]=29-222, B[4:7]=zeros
0x06F   |  8  | ~9 Hz | ALL       | High entropy all bytes - possibly encrypted/SecOC
""")

    print("KEY OBSERVATIONS:")
    print("  1. Most IDs only appear in source 00000004 (after ~149s)")
    print("     -> Vehicle likely 'woke up' or started a mode at that time")
    print("  2. 0x065 and 0x06F are present from start across all sources")
    print("  3. 0x066 B[2] is a clear wrapping byte counter")
    print("  4. 0x06F shows very high entropy - may be SecOC-protected")
    print("  5. B[4]=0x54='T', B[5]=0x2D='-' in 0x066 are ASCII constants")


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("=== VW ID Buzz CAN Reverse Engineering ===")
    print("Loading data from MF4 files...")
    df = load_all()
    df = prepare_df(df)

    can_ids = sorted(df['can_id'].unique())
    print(f"Found {len(can_ids)} CAN IDs: {[f'0x{int(x):03X}' for x in can_ids]}")
    print(f"Total frames: {len(df)}")

    # Run analysis for each CAN ID
    for cid in can_ids:
        hex_id = f"0x{int(cid):03X}"
        print(f"\n{'='*70}")
        print(f"Analyzing {hex_id}")
        print(f"{'='*70}")

        # Get primary source for this ID
        sub = df[df['can_id'] == cid]
        sources = sorted(sub['source'].unique())

        # Byte time series
        plot_byte_timeseries(df, cid)

        # Also plot per-source if multiple sources
        if len(sources) > 1:
            for src in sources:
                if len(sub[sub['source'] == src]) > 20:
                    plot_byte_timeseries(df, cid, source=src)

        # 16-bit signals
        plot_16bit_signals(df, cid)

        # Bit heatmap
        plot_bit_heatmap(df, cid)

        # Counter detection
        detect_counters(df, cid)

        # Checksum detection
        detect_checksum(df, cid)

        # Signal boundaries
        detect_signal_boundaries(df, cid)

        # ASCII check
        check_ascii(df, cid)

    # Special decodings
    print(f"\n{'='*70}")
    print("DETAILED SIGNAL DECODING ATTEMPTS")
    print(f"{'='*70}")
    decode_0x066(df)
    decode_0x067(df)
    decode_0x068(df)

    # 0x06F per-source comparison
    analyze_06f_per_source(df)

    # Scaling factor guesses for promising signals
    print(f"\n{'='*70}")
    print("SCALING FACTOR ANALYSIS")
    print(f"{'='*70}")

    # 0x066 B[3] as single byte
    guess_scaling(df, 0x066, [3], source='00000004')

    # 0x067 B[1] as single byte
    guess_scaling(df, 0x067, [1], source='00000004')

    # 0x067 B[4] as single byte
    guess_scaling(df, 0x067, [4], source='00000004')

    # 0x068 B[0] as single byte
    guess_scaling(df, 0x068, [0], source='00000004')

    # 0x068 B[1] as single byte
    guess_scaling(df, 0x068, [1], source='00000004')

    # 0x06B B[3] as single byte
    guess_scaling(df, 0x06B, [3], source='00000004')

    # Summary
    print_summary(df)

    print(f"\nAll plots saved to '{OUTPUT_DIR}/' directory.")
    print("Open the PNG files to visually inspect signal patterns.")
