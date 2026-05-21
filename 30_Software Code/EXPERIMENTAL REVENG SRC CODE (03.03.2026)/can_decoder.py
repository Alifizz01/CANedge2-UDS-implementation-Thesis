"""
CAN Signal Decoder for VW ID Buzz
Based on reverse engineering analysis of raw CAN data.

Hypothesized signal definitions derived from:
- Byte time series patterns
- Bit-level change heatmaps
- ASCII character detection
- Counter/checksum analysis
- Cross-source comparison
- Common VW/automotive signal conventions
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
    if isinstance(val, (list, np.ndarray)):
        return [int(b) for b in val]
    s = str(val).strip()
    if s.startswith('[') and s.endswith(']'):
        return [int(x) for x in s[1:-1].split()]
    return []


def prepare_df(df):
    df = df.copy()
    df['bytes_list'] = df['data_bytes'].apply(parse_data_bytes)
    max_dlc = df['bytes_list'].apply(len).max()
    for i in range(max_dlc):
        df[f'b{i}'] = df['bytes_list'].apply(lambda x: x[i] if i < len(x) else np.nan)
    return df


# =============================================================================
# Signal Definitions (hypothesized from reverse engineering)
# =============================================================================

SIGNAL_DEFS = {
    "0x065": {
        "name": "Heartbeat / Network Management",
        "description": "Keepalive message present across all sources from t=0",
        "signals": {
            "nm_state": {
                "bytes": [0],
                "type": "enum",
                "values": {0: "Sleep/Idle", 0x15: "Wakeup?", 0x2B: "Active1?",
                           0x40: "Active2?", 0x5B: "FullActive?"},
                "description": "Network management state (9 distinct values, 77% zeros=idle)"
            }
        }
    },
    "0x066": {
        "name": "Slow Measurement A (Temp/Counter)",
        "description": "5 Hz message, only source 00000004, starts at t=149s",
        "signals": {
            "mode": {
                "bytes": [0],
                "type": "enum",
                "values": {1: "Initializing", 3: "Active"},
                "description": "Operating mode (transitions 1->3 around t=175s)"
            },
            "rolling_counter_16": {
                "bytes": [1, 2],
                "endian": "big",
                "type": "counter",
                "description": "16-bit message counter (B[1]=high, B[2]=low, wrapping)"
            },
            "temperature_A": {
                "bytes": [3],
                "factor": 1,
                "offset": -40,
                "unit": "degC",
                "description": "Temperature (8-10C with offset -40). Increases slowly over time."
            },
            "msg_type_T": {"bytes": [4], "type": "const", "value": 0x54,
                           "description": "Constant 'T' (0x54) - message type marker"},
            "msg_type_dash": {"bytes": [5], "type": "const", "value": 0x2D,
                              "description": "Constant '-' (0x2D) - message type marker"},
        }
    },
    "0x067": {
        "name": "Multi-Signal Measurement",
        "description": "~4.5 Hz, only source 00000004, starts at t=177s",
        "signals": {
            "signal_A": {
                "bytes": [0],
                "description": "Dynamic signal (1-255). Shows clear physical behavior: "
                               "stable periods, transitions, and trends. Possibly motor/inverter related."
            },
            "temperature_B": {
                "bytes": [1],
                "factor": 1,
                "offset": 0,
                "unit": "degC",
                "description": "Temperature or slow param (11-36). Rises then drops - "
                               "could be component temp (battery/motor)."
            },
            "const_8A": {"bytes": [2], "type": "const", "value": 0x8A,
                         "description": "Constant 0x8A (138) - message identifier"},
            "multiplexer_or_state": {
                "bytes": [3],
                "bit_offset": 4,
                "bit_length": 4,
                "type": "enum",
                "description": "High nibble of B[3]: 3-bit state (8 levels, steps of 0x20). "
                               "Low nibble always 0x0. Possibly multiplexer index."
            },
            "signal_B": {
                "bytes": [4],
                "description": "Main measurement signal (0-254, 223 unique). "
                               "Shows smooth physical behavior - gradual changes, trends. "
                               "Could be voltage, current, or similar."
            },
            "temperature_C": {
                "bytes": [5],
                "factor": 1,
                "offset": -40,
                "unit": "degC",
                "description": "Temperature (11-13C with offset -40). Similar to 0x066.temperature_A."
            },
            "const_6D": {"bytes": [6], "type": "const", "value": 0x6D,
                         "description": "Constant 'm' (0x6D) - unit marker?"},
            "signal_C": {
                "bytes": [7],
                "description": "Slow-changing signal (9-253, mostly near 9-33). "
                               "Could be a checksum or quality indicator."
            }
        }
    },
    "0x068": {
        "name": "Measurement B (4-byte)",
        "description": "~4.5 Hz, same timing as 0x067, only source 00000004",
        "signals": {
            "signal_D": {
                "bytes": [0],
                "description": "Main signal (1-253, 117 unique). Shows clear physical trend: "
                               "initial transient, stable period, gradual decline. "
                               "Likely voltage, power, or similar measurement."
            },
            "parameter_slow": {
                "bytes": [1],
                "factor": 1,
                "offset": -40,
                "unit": "degC",
                "description": "Very narrow range 244-246. If raw value, possibly "
                               "a nearly-constant parameter. As temp*0.1-40 = -15.6 to -15.4C."
            },
            "signal_E": {
                "bytes": [2],
                "description": "Varying signal (17-233, 23 unique). Starts high (~200), "
                               "drops and stabilizes around 25-50. Could be a decaying measurement."
            },
            "status_flag": {
                "bytes": [3],
                "type": "bool",
                "description": "Binary flag (0 or 1). Briefly goes to 1, then stays 0."
            }
        }
    },
    "0x06B": {
        "name": "Measurement C (5-byte)",
        "description": "~4.5 Hz, only source 00000004",
        "signals": {
            "signal_F": {
                "bytes": [0],
                "description": "High variance signal (1-255). Wide distribution."
            },
            "signal_G": {
                "bytes": [1],
                "description": "Signal (0-123). Half-range byte."
            },
            "state_3bit": {
                "bytes": [2],
                "bit_offset": 5,
                "bit_length": 3,
                "type": "enum",
                "description": "8 discrete levels in steps of 0x20 (high variance from 8 values). "
                               "Similar structure to 0x067 B[3]."
            },
            "signal_H": {
                "bytes": [3],
                "description": "Main signal (29-222, 68 unique). Wide range, "
                               "98% printable ASCII range but likely a measurement."
            }
        }
    },
    "0x06F": {
        "name": "Multi-Signal Fast Message",
        "description": "~9 Hz, present from t=0 across all sources. NOT encrypted - "
                       "confirmed by per-source analysis showing clear state transitions "
                       "and stable periods (especially visible in source 00000002).",
        "signals": {
            "signal_main_1": {
                "bytes": [0],
                "description": "Dynamic signal (1-255). Source 00000002 shows clear "
                               "state transitions (200->25->back). Source 00000004 very stable (~147). "
                               "Likely a key vehicle parameter."
            },
            "signal_main_2": {
                "bytes": [1],
                "description": "Signal (3-252). Shows stable periods with discrete level changes."
            },
            "signal_main_3": {
                "bytes": [2],
                "description": "Signal (13-241). Discrete levels visible in source 00000004."
            },
            "signal_main_4": {
                "bytes": [3],
                "description": "Signal (53-215). Relatively stable per-source."
            },
            "signal_main_5": {
                "bytes": [4],
                "description": "Signal (0-255). High variance, many unique values. "
                               "Source 00000002 shows long stable periods at ~250."
            },
            "signal_main_6": {
                "bytes": [5],
                "description": "Signal (0-255). Similar pattern to B[4]."
            },
            "signal_main_7": {
                "bytes": [6],
                "description": "Signal (0-250). Discrete levels visible."
            },
            "signal_main_8": {
                "bytes": [7],
                "description": "Narrow range per-source (source 00000004: 88-165, std=2.6). "
                               "Could be checksum, CRC, or a very stable measurement."
            }
        }
    }
}


# =============================================================================
# Decode and Plot Functions
# =============================================================================

def decode_0x066_full(df):
    """Decode 0x066 with hypothesized signal layout."""
    sub = df[df['can_id'] == 0x066].copy()
    if sub.empty:
        return
    ts = sub.index.values

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.suptitle("CAN 0x066 - DECODED: Slow Measurement A", fontsize=14, fontweight='bold')

    # Mode
    mode = sub['b0'].values.astype(int)
    mode_labels = np.where(mode == 1, "Init(1)", "Active(3)")

    # 16-bit counter
    counter = sub['b1'].values.astype(int) * 256 + sub['b2'].values.astype(int)
    axes[0].plot(ts, counter, '-', linewidth=1, color='steelblue')
    axes[0].set_ylabel('Counter (16-bit)')
    axes[0].set_title('B[1:2] 16-bit Rolling Counter (Big-Endian)')
    # Mark mode transitions
    mode_changes = np.where(np.diff(mode) != 0)[0]
    for mc in mode_changes:
        axes[0].axvline(x=ts[mc], color='red', linewidth=1, linestyle='--', alpha=0.7)
        axes[0].text(ts[mc], axes[0].get_ylim()[1] * 0.9, f'Mode: {mode[mc]}->{mode[mc+1]}',
                     fontsize=8, color='red')

    # Temperature A
    temp_A = sub['b3'].values.astype(int) - 40
    axes[1].plot(ts, temp_A, 'o-', markersize=3, linewidth=1, color='orangered')
    axes[1].set_ylabel('Temperature (C)')
    axes[1].set_title('B[3] Temperature A (raw - 40): Outside/Ambient Temperature?')
    axes[1].axhline(y=0, color='gray', linewidth=0.5, linestyle='--')
    for y in [8, 9, 10]:
        axes[1].axhline(y=y, color='lightblue', linewidth=0.3, linestyle=':')

    # Mode as colored background
    axes[2].fill_between(ts, 0, 1, where=(mode == 1), alpha=0.3, color='yellow', label='Init (0x01)')
    axes[2].fill_between(ts, 0, 1, where=(mode == 3), alpha=0.3, color='green', label='Active (0x03)')
    axes[2].set_ylabel('Mode')
    axes[2].set_title('B[0] Operating Mode + Constants: B[4]=T(0x54), B[5]=-(0x2D)')
    axes[2].legend()
    axes[2].set_ylim(0, 1.5)

    axes[-1].set_xlabel('Time (s)')
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/0x066_DECODED.png", dpi=150)
    plt.close()
    print("  Saved 0x066_DECODED.png")

    print(f"\n  0x066 Summary:")
    print(f"    Mode transitions: Init(1) -> Active(3) at ~t=175s")
    print(f"    Counter: 16-bit wrapping, {counter.min()} to {counter.max()}")
    print(f"    Temperature A: {temp_A.min()}C to {temp_A.max()}C (likely ambient)")


def decode_0x067_full(df):
    """Decode 0x067 with signal layout."""
    sub = df[df['can_id'] == 0x067].copy()
    if sub.empty:
        return
    ts = sub.index.values

    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    fig.suptitle("CAN 0x067 - DECODED: Multi-Signal Measurement", fontsize=14, fontweight='bold')

    # Signal A - main dynamic signal
    sig_a = sub['b0'].values.astype(int)
    axes[0].plot(ts, sig_a, '.', markersize=2, color='steelblue')
    axes[0].set_ylabel('Signal A (raw)')
    axes[0].set_title('B[0] Dynamic Signal A - Motor/Inverter parameter?')

    # Temperature B
    temp_b = sub['b1'].values.astype(int)
    axes[1].plot(ts, temp_b, 'o-', markersize=2, linewidth=1, color='orangered')
    axes[1].set_ylabel('Temp B (C, raw)')
    axes[1].set_title('B[1] Temperature B (11-36C raw) - Component Temperature')
    ax1b = axes[1].twinx()
    ax1b.set_ylabel('if offset -40', color='gray')
    ax1b.set_ylim(temp_b.min() - 40, temp_b.max() - 40)
    ax1b.tick_params(axis='y', labelcolor='gray')

    # Signal B - main measurement
    sig_b = sub['b4'].values.astype(int)
    axes[2].plot(ts, sig_b, '.', markersize=2, color='forestgreen')
    axes[2].set_ylabel('Signal B (raw)')
    axes[2].set_title('B[4] Signal B - Voltage/Current/SOC measurement?')

    # Temperature C
    temp_c = sub['b5'].values.astype(int) - 40
    axes[3].plot(ts, temp_c, 'o-', markersize=2, linewidth=1, color='orangered')
    axes[3].set_ylabel('Temp C (C)')
    axes[3].set_title('B[5] Temperature C (raw-40): 11-13C - Ambient/Cabin Temperature')
    axes[3].axhline(y=0, color='gray', linewidth=0.5, linestyle='--')

    axes[-1].set_xlabel('Time (s)')
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/0x067_DECODED.png", dpi=150)
    plt.close()
    print("  Saved 0x067_DECODED.png")

    print(f"\n  0x067 Summary:")
    print(f"    Signal A (B[0]): {sig_a.min()}-{sig_a.max()} - dynamic physical signal")
    print(f"    Temp B (B[1]): {temp_b.min()}-{temp_b.max()}C raw")
    print(f"    Const B[2]=0x8A, B[6]='m'(0x6D)")
    print(f"    Signal B (B[4]): {sig_b.min()}-{sig_b.max()} - smooth measurement")
    print(f"    Temp C (B[5]-40): {temp_c.min()}-{temp_c.max()}C")


def decode_0x068_full(df):
    """Decode 0x068."""
    sub = df[df['can_id'] == 0x068].copy()
    if sub.empty:
        return
    ts = sub.index.values

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.suptitle("CAN 0x068 - DECODED: Measurement B", fontsize=14, fontweight='bold')

    # Signal D
    sig_d = sub['b0'].values.astype(int)
    axes[0].plot(ts, sig_d, '.', markersize=2, color='steelblue')
    axes[0].set_ylabel('Signal D (raw)')
    axes[0].set_title('B[0] Signal D - Main measurement (voltage/power?)')

    # Signal E with decay pattern
    sig_e = sub['b2'].values.astype(int)
    axes[1].plot(ts, sig_e, '.', markersize=2, color='forestgreen')
    axes[1].set_ylabel('Signal E (raw)')
    axes[1].set_title('B[2] Signal E - Decaying measurement (starts high, drops)')

    # B[1] narrow range + B[3] flag
    b1 = sub['b1'].values.astype(int)
    flag = sub['b3'].values.astype(int)
    axes[2].plot(ts, b1, '.', markersize=3, color='purple', label='B[1] (244-246)')
    ax2b = axes[2].twinx()
    ax2b.plot(ts, flag, 's', markersize=4, color='red', alpha=0.5, label='B[3] flag')
    ax2b.set_ylabel('Flag', color='red')
    axes[2].set_ylabel('B[1] value')
    axes[2].set_title('B[1] Slow parameter (244-246) + B[3] Status flag')
    axes[2].legend(loc='upper left')
    ax2b.legend(loc='upper right')

    axes[-1].set_xlabel('Time (s)')
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/0x068_DECODED.png", dpi=150)
    plt.close()
    print("  Saved 0x068_DECODED.png")


def decode_0x06F_full(df):
    """Decode 0x06F per source to reveal signal structure."""
    sub = df[df['can_id'] == 0x06F].copy()
    if sub.empty:
        return

    # Focus on source 00000002 which shows clearest state transitions
    for src in ['00000002', '00000004']:
        src_data = sub[sub['source'] == src]
        if src_data.empty:
            continue
        ts = src_data.index.values

        fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
        fig.suptitle(f"CAN 0x06F - DECODED (source {src}): Multi-Signal Fast Message",
                     fontsize=14, fontweight='bold')

        # Signal 1: B[0] - shows clear state transitions
        s1 = src_data['b0'].values.astype(int)
        axes[0].plot(ts, s1, '.', markersize=2, color='steelblue')
        axes[0].set_ylabel('B[0] Signal 1')
        axes[0].set_title('Signal 1 (B[0]) - Key vehicle parameter with state transitions')

        # Signal 2-3: B[1:2] as potential 16-bit BE signal
        s23_be = src_data['b1'].values.astype(int) * 256 + src_data['b2'].values.astype(int)
        axes[1].plot(ts, s23_be, '.', markersize=2, color='forestgreen')
        axes[1].set_ylabel('B[1:2] BE')
        axes[1].set_title('Signal 2 (B[1:2] big-endian 16-bit)')

        # Signal 4-5: B[4:5] as potential 16-bit BE signal
        s45_be = src_data['b4'].values.astype(int) * 256 + src_data['b5'].values.astype(int)
        axes[2].plot(ts, s45_be, '.', markersize=2, color='orangered')
        axes[2].set_ylabel('B[4:5] BE')
        axes[2].set_title('Signal 3 (B[4:5] big-endian 16-bit)')

        # B[7] - very stable per source, potential CRC/checksum
        s8 = src_data['b7'].values.astype(int)
        axes[3].plot(ts, s8, '.', markersize=2, color='purple')
        axes[3].set_ylabel('B[7]')
        axes[3].set_title(f'B[7] - Narrow range (std={np.std(s8):.1f}): CRC or stable measurement')

        axes[-1].set_xlabel('Time (s)')
        plt.tight_layout()
        plt.savefig(f"{OUTPUT_DIR}/0x06F_DECODED_{src}.png", dpi=150)
        plt.close()
        print(f"  Saved 0x06F_DECODED_{src}.png")


def decode_0x065_full(df):
    """Decode 0x065 heartbeat."""
    sub = df[df['can_id'] == 0x065].copy()
    if sub.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 4))
    fig.suptitle("CAN 0x065 - DECODED: Network Management / Heartbeat",
                 fontsize=14, fontweight='bold')

    b0 = sub['b0'].values.astype(int)
    ts = sub.index.values

    ax.plot(ts, b0, '.', markersize=3, color='steelblue')
    ax.set_ylabel('NM State (B[0])')
    ax.set_xlabel('Time (s)')
    ax.set_title('B[0] NM State (77% zeros = idle/sleep, 9 unique values)')

    # Color-code per source
    for src in sorted(sub['source'].unique()):
        src_mask = sub['source'] == src
        ax.plot(ts[src_mask], b0[src_mask], '.', markersize=3, alpha=0.7, label=f'Source {src}')
    ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/0x065_DECODED.png", dpi=150)
    plt.close()
    print("  Saved 0x065_DECODED.png")

    # Unique values analysis
    unique_vals = sorted(np.unique(b0))
    print(f"\n  0x065 NM States: {[f'0x{v:02X}({v})' for v in unique_vals]}")
    for v in unique_vals:
        count = np.sum(b0 == v)
        print(f"    0x{v:02X} ({v:3d}): {count:5d} frames ({count/len(b0)*100:.1f}%)")


def cross_signal_correlation(df):
    """Check if temperature signals across messages correlate."""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle("Cross-Message Signal Correlation", fontsize=14, fontweight='bold')

    # Temperature comparison: 0x066 B[3] vs 0x067 B[5]
    sub_066 = df[df['can_id'] == 0x066].copy()
    sub_067 = df[df['can_id'] == 0x067].copy()

    if not sub_066.empty and not sub_067.empty:
        ts_066 = sub_066.index.values
        temp_066 = sub_066['b3'].values.astype(int) - 40
        ts_067 = sub_067.index.values
        temp_067 = sub_067['b5'].values.astype(int) - 40

        axes[0].plot(ts_066, temp_066, '.', markersize=3, label='0x066 B[3]-40 (Temp A)')
        axes[0].plot(ts_067, temp_067, '.', markersize=3, label='0x067 B[5]-40 (Temp C)')
        axes[0].set_ylabel('Temperature (C)')
        axes[0].set_title('Temperature Signals Comparison (offset -40)')
        axes[0].legend()
        axes[0].set_xlabel('Time (s)')

    # Signal comparison: 0x067 B[4] vs 0x068 B[0]
    sub_068 = df[df['can_id'] == 0x068].copy()
    if not sub_067.empty and not sub_068.empty:
        ts_067 = sub_067.index.values
        sig_067 = sub_067['b4'].values.astype(int)
        ts_068 = sub_068.index.values
        sig_068 = sub_068['b0'].values.astype(int)

        axes[1].plot(ts_067, sig_067, '.', markersize=2, label='0x067 B[4] (Signal B)')
        axes[1].plot(ts_068, sig_068, '.', markersize=2, label='0x068 B[0] (Signal D)')
        axes[1].set_ylabel('Raw Value')
        axes[1].set_title('Dynamic Signals Comparison (0x067 vs 0x068)')
        axes[1].legend()
        axes[1].set_xlabel('Time (s)')

    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/cross_correlation.png", dpi=150)
    plt.close()
    print("  Saved cross_correlation.png")


def create_overview_dashboard(df):
    """Create a single dashboard showing all decoded signals."""
    fig = plt.figure(figsize=(20, 16))
    fig.suptitle("VW ID Buzz CAN Bus - Decoded Signal Overview", fontsize=16, fontweight='bold')

    gs = fig.add_gridspec(6, 2, hspace=0.4, wspace=0.3)

    # 0x065 NM State
    ax1 = fig.add_subplot(gs[0, 0])
    sub = df[df['can_id'] == 0x065]
    ax1.plot(sub.index.values, sub['b0'].values.astype(int), '.', markersize=1, color='steelblue')
    ax1.set_title('0x065 NM State', fontsize=10, fontweight='bold')
    ax1.set_ylabel('State')

    # 0x066 Counter
    ax2 = fig.add_subplot(gs[0, 1])
    sub = df[df['can_id'] == 0x066]
    if not sub.empty:
        counter = sub['b1'].values.astype(int) * 256 + sub['b2'].values.astype(int)
        ax2.plot(sub.index.values, counter, '-', linewidth=0.5, color='steelblue')
        ax2.set_title('0x066 16-bit Counter', fontsize=10, fontweight='bold')
        ax2.set_ylabel('Count')

    # 0x066 Temperature A
    ax3 = fig.add_subplot(gs[1, 0])
    sub = df[df['can_id'] == 0x066]
    if not sub.empty:
        ax3.plot(sub.index.values, sub['b3'].values.astype(int) - 40,
                 'o-', markersize=2, color='orangered')
        ax3.set_title('0x066 Temp A (B[3]-40)', fontsize=10, fontweight='bold')
        ax3.set_ylabel('degC')

    # 0x067 Temperature B+C
    ax4 = fig.add_subplot(gs[1, 1])
    sub067 = df[df['can_id'] == 0x067]
    if not sub067.empty:
        ax4.plot(sub067.index.values, sub067['b1'].values.astype(int),
                 '.', markersize=2, color='blue', label='B[1] raw')
        ax4.plot(sub067.index.values, sub067['b5'].values.astype(int) - 40,
                 '.', markersize=2, color='red', label='B[5]-40')
        ax4.set_title('0x067 Temperatures', fontsize=10, fontweight='bold')
        ax4.set_ylabel('Value')
        ax4.legend(fontsize=7)

    # 0x067 Signal A
    ax5 = fig.add_subplot(gs[2, 0])
    if not sub067.empty:
        ax5.plot(sub067.index.values, sub067['b0'].values.astype(int),
                 '.', markersize=1, color='steelblue')
        ax5.set_title('0x067 Signal A (B[0])', fontsize=10, fontweight='bold')
        ax5.set_ylabel('Raw')

    # 0x067 Signal B
    ax6 = fig.add_subplot(gs[2, 1])
    if not sub067.empty:
        ax6.plot(sub067.index.values, sub067['b4'].values.astype(int),
                 '.', markersize=1, color='forestgreen')
        ax6.set_title('0x067 Signal B (B[4])', fontsize=10, fontweight='bold')
        ax6.set_ylabel('Raw')

    # 0x068 Signal D
    ax7 = fig.add_subplot(gs[3, 0])
    sub068 = df[df['can_id'] == 0x068]
    if not sub068.empty:
        ax7.plot(sub068.index.values, sub068['b0'].values.astype(int),
                 '.', markersize=1, color='steelblue')
        ax7.set_title('0x068 Signal D (B[0])', fontsize=10, fontweight='bold')
        ax7.set_ylabel('Raw')

    # 0x068 Signal E
    ax8 = fig.add_subplot(gs[3, 1])
    if not sub068.empty:
        ax8.plot(sub068.index.values, sub068['b2'].values.astype(int),
                 '.', markersize=1, color='forestgreen')
        ax8.set_title('0x068 Signal E (B[2]) - Decay', fontsize=10, fontweight='bold')
        ax8.set_ylabel('Raw')

    # 0x06F Signal 1 per source
    ax9 = fig.add_subplot(gs[4, 0])
    sub06f = df[df['can_id'] == 0x06F]
    for src in sorted(sub06f['source'].unique()):
        s = sub06f[sub06f['source'] == src]
        ax9.plot(s.index.values, s['b0'].values.astype(int), '.', markersize=1, label=src)
    ax9.set_title('0x06F Signal 1 (B[0]) per source', fontsize=10, fontweight='bold')
    ax9.set_ylabel('Raw')
    ax9.legend(fontsize=6)

    # 0x06F B[7] per source
    ax10 = fig.add_subplot(gs[4, 1])
    for src in sorted(sub06f['source'].unique()):
        s = sub06f[sub06f['source'] == src]
        ax10.plot(s.index.values, s['b7'].values.astype(int), '.', markersize=1, label=src)
    ax10.set_title('0x06F B[7] per source (stable)', fontsize=10, fontweight='bold')
    ax10.set_ylabel('Raw')
    ax10.legend(fontsize=6)

    # 0x06B
    ax11 = fig.add_subplot(gs[5, 0])
    sub06b = df[df['can_id'] == 0x06B]
    if not sub06b.empty:
        ax11.plot(sub06b.index.values, sub06b['b3'].values.astype(int),
                  '.', markersize=1, color='purple')
        ax11.set_title('0x06B Signal H (B[3])', fontsize=10, fontweight='bold')
        ax11.set_ylabel('Raw')
        ax11.set_xlabel('Time (s)')

    # Timeline of active CAN IDs
    ax12 = fig.add_subplot(gs[5, 1])
    for i, cid in enumerate(sorted(df['can_id'].unique())):
        s = df[df['can_id'] == cid]
        ax12.plot(s.index.values, [i] * len(s), '|', markersize=2, alpha=0.3)
    ax12.set_yticks(range(len(df['can_id'].unique())))
    ax12.set_yticklabels([f'0x{int(c):03X}' for c in sorted(df['can_id'].unique())])
    ax12.set_title('Message Timeline', fontsize=10, fontweight='bold')
    ax12.set_xlabel('Time (s)')

    plt.savefig(f"{OUTPUT_DIR}/OVERVIEW_DASHBOARD.png", dpi=150)
    plt.close()
    print("  Saved OVERVIEW_DASHBOARD.png")


def print_final_report():
    """Print the final reverse engineering report."""
    print(f"""
{'#'*70}
# VW ID BUZZ CAN BUS - REVERSE ENGINEERING REPORT
{'#'*70}

RECORDING CONTEXT:
  - 4 log sources, total 333 seconds (~5.5 minutes)
  - 9,146 CAN frames across 7 unique CAN IDs (0x065-0x06F)
  - All messages on bus_channel 9, direction 0 (received)
  - Sources 00000002 and 00000005: appear to capture driving/active state
  - Source 00000004: longest recording, vehicle transitions between states
  - Source 00000003: very short (5s), startup capture only

{'='*70}
DECODED CAN MESSAGES:
{'='*70}

0x065 - NETWORK MANAGEMENT / HEARTBEAT
  DLC: 1 | Freq: ~9 Hz | Present: ALL sources from t=0
  Layout: [NM_STATE(8)] [0x00 x7]
  - B[0]: NM state with 9 values (77% idle/zero)
  - Bytes 1-7: always zero (padded)
  - Purpose: ECU alive signal / network management

0x066 - MEASUREMENT MESSAGE A
  DLC: 6 | Freq: ~5 Hz | Present: Source 00000004 only (from t=149s)
  Layout: [MODE(8)] [COUNTER_HI(8)] [COUNTER_LO(8)] [TEMP_A(8)] [0x54] [0x2D]
  - B[0]: Mode (0x01=Init, 0x03=Active)
  - B[1:2]: 16-bit rolling message counter (big-endian, wrapping)
  - B[3]: Temperature A = raw - 40 => 8-10 degC (ambient temperature)
  - B[4:5]: ASCII constants 'T-' (message type identifier)

0x067 - MULTI-SIGNAL MEASUREMENT
  DLC: 8 | Freq: ~4.5 Hz | Present: Source 00000004 only (from t=177s)
  Layout: [SIG_A(8)] [TEMP_B(8)] [0x8A] [MUX_3bit|0000] [SIG_B(8)] [TEMP_C(8)] [0x6D] [SIG_C(8)]
  - B[0]: Dynamic signal A (1-255) - shows physical behavior (motor/drive?)
  - B[1]: Temperature B (11-36 raw) - component temperature
  - B[2]: Constant 0x8A (message identifier)
  - B[3]: High nibble = 3-bit multiplexer/state (8 levels), low nibble = 0
  - B[4]: Signal B (0-254) - smooth measurement (voltage/current?)
  - B[5]: Temperature C = raw - 40 => 11-13 degC (correlates with 0x066 Temp A)
  - B[6]: Constant 0x6D = 'm' (unit: meters? Celsius?)
  - B[7]: Signal C (slowly varying, possibly CRC or quality indicator)

0x068 - MEASUREMENT MESSAGE B
  DLC: 4 | Freq: ~4.5 Hz | Same timing as 0x067 | Source 00000004 only
  Layout: [SIG_D(8)] [PARAM(8)] [SIG_E(8)] [FLAG(1)]
  - B[0]: Signal D (1-253) - clear physical trend (initial transient then gradual decline)
  - B[1]: Near-constant parameter (244-246)
  - B[2]: Signal E (17-233) - decaying measurement (starts high, drops to stable)
  - B[3]: Binary status flag (mostly 0, briefly 1)

0x06A - EVENT MESSAGE
  DLC: ? | Freq: sporadic | 126 messages only | Source 00000004
  - Likely event-triggered, not periodic
  - Needs more data to characterize

0x06B - MEASUREMENT MESSAGE C
  DLC: 5 | Freq: ~4.5 Hz | Source 00000004 only
  Layout: [SIG_F(8)] [SIG_G(8)] [STATE_3bit|00000] [SIG_H(8)] [0x00]
  - B[0]: Signal F (1-255, high variance)
  - B[1]: Signal G (0-123, half-range)
  - B[2]: 3-bit state in high nibble (8 discrete levels, like 0x067 B[3])
  - B[3]: Signal H (29-222, 68 unique)
  - B[4]: Zero padding

0x06F - MULTI-SIGNAL FAST MESSAGE
  DLC: 8 | Freq: ~9 Hz | Present: ALL sources from t=0
  NOT ENCRYPTED - confirmed by per-source analysis:
    - Source 00000002: clear state transitions in B[0] (200->25->200)
    - Source 00000004: B[0] very stable (~147), B[7] extremely narrow (std=2.6)
  Layout: 8 independent signals, likely byte-aligned
  - B[0]: Key vehicle parameter (state transitions visible)
  - B[1:2]: Possibly 16-bit signal (discrete levels)
  - B[3]: Relatively stable per source (53-215)
  - B[4:5]: Possibly 16-bit signal (high variance)
  - B[6]: Discrete levels
  - B[7]: Very stable per-source (possible CRC/checksum or slow parameter)

{'='*70}
KEY FINDINGS:
{'='*70}
  1. TEMPERATURE SIGNALS CONFIRMED:
     - 0x066 B[3] and 0x067 B[5] both increase slowly over time
     - With offset -40: 8-10C and 11-13C respectively
     - Likely ambient and cabin/component temperatures

  2. ASCII MARKERS FOUND:
     - 0x066: B[4]='T', B[5]='-'
     - 0x067: B[5]='3'/'4'/'5' (also valid as temp 51-53), B[6]='m'
     - Could indicate measurement types or units

  3. MESSAGE COUNTER:
     - 0x066 B[1:2] is a confirmed 16-bit wrapping counter

  4. 0x06F IS NOT ENCRYPTED:
     - Different sources show different but internally consistent patterns
     - State transitions and stable periods clearly visible
     - High per-byte entropy is due to independent signals spanning full range

  5. TIMING STRUCTURE:
     - 0x065 and 0x06F: always present (~9 Hz each)
     - 0x066-0x06B: appear only in source 00000004 after ~149s
     - Vehicle likely woke up or entered a diagnostic mode at that point
""")


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("=== VW ID Buzz CAN Signal Decoder ===")
    print("Loading data...")
    df = load_all()
    df = prepare_df(df)

    print("\nDecoding signals...")
    decode_0x065_full(df)
    decode_0x066_full(df)
    decode_0x067_full(df)
    decode_0x068_full(df)
    decode_0x06F_full(df)
    cross_signal_correlation(df)
    create_overview_dashboard(df)
    print_final_report()

    print(f"\nAll decoded plots saved to '{OUTPUT_DIR}/' directory.")
