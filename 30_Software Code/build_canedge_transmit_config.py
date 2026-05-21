"""
Build a CANedge transmit-list config from the VW MEB UDS PIDs CSV.

Reads CANedge/config-01.08.json as the base, replaces the can_1.transmit
list with a curated set of ReadDataByIdentifier requests (and the required
DiagnosticSessionControl + TesterPresent keepalives), and writes the result
to CANedge/config-01.08-built.json.

Why programmatic: when a PID is added to the CSV (or fixed), running this
script propagates the change to the device config so the decoder and the
transmit list never drift.

Usage:
    python -X utf8 src/build_canedge_transmit_config.py
"""

import json
from pathlib import Path

from uds_battery_decoder import parse_pid_csv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PID_CSV = PROJECT_ROOT / "40_Experiments" / "Exprimental Data" / "csv" / "VW MEB UDS PIDs list.csv"
CANEDGE_DIR = PROJECT_ROOT / "20_Hardware" / "CANedge"
BASE_CONFIG = CANEDGE_DIR / "config-01.08.json"
OUT_CONFIG_CURATED = CANEDGE_DIR / "config-01.08-built.json"
OUT_CONFIG_FULL = CANEDGE_DIR / "config-01.08-full-sweep.json"

# CANedge schema hard limit: 64 transmit entries per CAN channel.
MAX_TRANSMIT_ENTRIES = 64

# Curated PID set: prioritize whole-pack signals, sample temps and cells.
# Cell voltage PIDs run 0x1E40..0x1EAB (108 cells); we sample every 4th cell.
PRIORITY_PIDS = [
    # Pack-level
    0x028C,  # SOC
    0x1E3B,  # HV Battery voltage
    0x1E3D,  # HV Battery current
    0x2A0B,  # HV Battery temp (main)
    0x1E0E,  # HV Battery max temp + temp point
    0x1E0F,  # HV Battery min temp + temp point (likely)
    0x1E33,  # cell # with highest voltage
    0x1E34,  # cell # with lowest voltage
    0x7448,  # Car operation mode
    0x743B,  # circulation pump
    0x46B3,  # SOC pack (if present)
    # DC-DC converter
    0x465B,  # DC-DC current
    0x465D,  # DC-DC voltage
]

# How many BMS cell-voltage PIDs to sample (evenly spaced)
CELL_SAMPLE_COUNT = 16


def make_transmit_entry(name, can_id, data_bytes, period_ms, delay_ms, extended=False):
    """Return one CANedge transmit list dict."""
    return {
        "name": name,
        "state": 1,
        "id_format": 1 if extended else 0,
        "frame_format": 0,
        "brs": 0,
        "log": 1,
        "period": period_ms,
        "delay": delay_ms,
        "id": can_id,
        "data": data_bytes,
    }


def rdbi_request_bytes(pid: int) -> str:
    """Return 8-byte hex string for ReadDataByIdentifier request, padded with VW 0x55."""
    hi = (pid >> 8) & 0xFF
    lo = pid & 0xFF
    # 03 22 hi lo 55 55 55 55
    return f"032 2{hi:02x}{lo:02x}55555555".replace(" ", "")  # safe-format


def rdbi_request_bytes_clean(pid: int) -> str:
    hi = (pid >> 8) & 0xFF
    lo = pid & 0xFF
    return f"0322{hi:02x}{lo:02x}55555555"


def build_transmit_list(pids_db: dict):
    """Construct the can_1.transmit list."""
    entries = []

    # Establish session
    entries.append(
        make_transmit_entry(
            "DiagSessionExt_BMS",
            "17FC007B",
            "021003555555555555"[:16],  # 02 10 03 55 55 55 55 55
            period_ms=2000,
            delay_ms=0,
            extended=True,
        )
    )
    # Keep session alive
    entries.append(
        make_transmit_entry(
            "TesterPresent_BMS",
            "17FC007B",
            "023e00555555555555"[:16],
            period_ms=2000,
            delay_ms=50,
            extended=True,
        )
    )

    # Curated priority PIDs (stagger by 100ms each)
    delay = 200
    for pid in PRIORITY_PIDS:
        if pid not in pids_db:
            continue
        meta = pids_db[pid]
        name = (meta["name"][:24] or f"PID_{pid:04X}").replace(" ", "_").replace("/", "_")
        entries.append(
            make_transmit_entry(
                f"P_{pid:04X}_{name}",
                "17FC007B",
                rdbi_request_bytes_clean(pid),
                period_ms=2000,
                delay_ms=delay,
                extended=True,
            )
        )
        delay += 100

    # Sample cell voltages: 0x1E40..0x1EAB = 108 cells
    cell_pids = [p for p in range(0x1E40, 0x1EAC) if p in pids_db]
    if cell_pids and CELL_SAMPLE_COUNT:
        step = max(1, len(cell_pids) // CELL_SAMPLE_COUNT)
        sampled = cell_pids[::step][:CELL_SAMPLE_COUNT]
        for pid in sampled:
            entries.append(
                make_transmit_entry(
                    f"Cell_{pid - 0x1E3F:03d}",
                    "17FC007B",
                    rdbi_request_bytes_clean(pid),
                    period_ms=10000,  # cells less frequent
                    delay_ms=delay,
                    extended=True,
                )
            )
            delay += 100

    # Sample temp-point PIDs: 0x1E0E..0x1E1F if present
    temp_pids = [p for p in range(0x1E0E, 0x1E20) if p in pids_db]
    for pid in temp_pids[:6]:
        entries.append(
            make_transmit_entry(
                f"Temp_{pid:04X}",
                "17FC007B",
                rdbi_request_bytes_clean(pid),
                period_ms=5000,
                delay_ms=delay,
                extended=True,
            )
        )
        delay += 100

    return entries


def safe_short_name(name: str, max_len: int = 18) -> str:
    """Sanitize a PID name into a short transmit-list entry name."""
    s = "".join(c if c.isalnum() else "_" for c in name)
    s = s.strip("_")
    return s[:max_len] or "PID"


TIER1 = {0x028C, 0x1E3B, 0x1E3D, 0x2A0B, 0x7448}
TIER2_PIDS_RANGES = [(0x1E0E, 0x1E40), (0x4600, 0x4700)]
TIER2_EXTRA = {0x743B, 0x46B3, 0x46B4, 0x1E33, 0x1E34}


def is_tier2(pid: int) -> bool:
    if pid in TIER2_EXTRA:
        return True
    for lo, hi in TIER2_PIDS_RANGES:
        if lo <= pid < hi:
            return True
    return False


def session_keepalive_entries(start_delay=0):
    """Two entries every config needs: open extended session + keep it alive."""
    return [
        make_transmit_entry(
            "DiagSessionExt_BMS", "17FC007B", "021003555555555555"[:16],
            period_ms=2000, delay_ms=start_delay, extended=True,
        ),
        make_transmit_entry(
            "TesterPresent_BMS", "17FC007B", "023e00555555555555"[:16],
            period_ms=2000, delay_ms=start_delay + 50, extended=True,
        ),
    ]


def make_pid_entry(pid: int, pids_db: dict, period_ms: int, delay_ms: int, prefix: str):
    meta = pids_db[pid]
    return make_transmit_entry(
        f"{prefix}_{pid:04X}_{safe_short_name(meta['name'])}",
        "17FC007B", rdbi_request_bytes_clean(pid),
        period_ms=period_ms, delay_ms=delay_ms, extended=True,
    )


def build_sweep_pack(pids_db: dict, sweep_pids: list, label: str):
    """Build one config with: 2 keepalive + tier1 fast + given sweep_pids slow."""
    entries = list(session_keepalive_entries(0))
    delay = 100
    # Always include Tier 1 fast loop in every sweep so SOC/V/I/temp are
    # captured continuously regardless of which sweep is flashed.
    tier1_pids = sorted(p for p in pids_db if p in TIER1)
    for pid in tier1_pids:
        entries.append(make_pid_entry(pid, pids_db, 1000, delay, "T1"))
        delay += 100
    # Then the assigned slow-cycle PIDs
    for pid in sweep_pids:
        entries.append(make_pid_entry(pid, pids_db, 10000, delay % 10000, label))
        delay += 100
        if len(entries) >= MAX_TRANSMIT_ENTRIES:
            break
    return entries


def build_full_sweep(pids_db: dict):
    """Single 64-entry config with session keepalive + tier1 + tier2 + sampled tier3.

    For complete 1-by-1 coverage of every PID, see build_split_sweeps which
    produces multiple configs to flash on consecutive sessions.
    """
    entries = list(session_keepalive_entries(0))
    delay = 100

    # Tier 1 - fast (always)
    for pid in sorted(p for p in pids_db if p in TIER1):
        entries.append(make_pid_entry(pid, pids_db, 1000, delay, "T1"))
        delay += 100

    # Tier 2 - medium (fit as many as possible)
    for pid in sorted(p for p in pids_db if is_tier2(p) and p not in TIER1):
        if len(entries) >= MAX_TRANSMIT_ENTRIES:
            break
        entries.append(make_pid_entry(pid, pids_db, 5000, delay % 5000, "T2"))
        delay += 100

    # Tier 3 - sampled to fill remaining slots
    remaining = MAX_TRANSMIT_ENTRIES - len(entries)
    tier3_pids = sorted(p for p in pids_db if p not in TIER1 and not is_tier2(p))
    if remaining > 0 and tier3_pids:
        step = max(1, len(tier3_pids) // remaining)
        for pid in tier3_pids[::step][:remaining]:
            entries.append(make_pid_entry(pid, pids_db, 20000, delay % 20000, "T3"))
            delay += 100

    return entries[:MAX_TRANSMIT_ENTRIES]


def build_split_sweeps(pids_db: dict):
    """Return [(out_path, entries), ...] covering every Tier-3 PID across N
    configs, each within the 64-entry cap. Tier 1 + session keepalive are
    repeated in every config so the user still gets SOC/V/I/temp every time.
    """
    fixed_count = 2 + len(TIER1)  # keepalive + tier1
    slots_per_config = MAX_TRANSMIT_ENTRIES - fixed_count

    tier3_pids = sorted(
        p for p in pids_db if p not in TIER1 and not is_tier2(p)
    )
    tier2_pids = sorted(
        p for p in pids_db if is_tier2(p) and p not in TIER1
    )
    rotation = tier2_pids + tier3_pids  # tier2 first (more useful), then tier3

    sweeps = []
    for i in range(0, len(rotation), slots_per_config):
        chunk = rotation[i : i + slots_per_config]
        label = f"S{(i // slots_per_config) + 1}"
        entries = build_sweep_pack(pids_db, chunk, label)
        out = CANEDGE_DIR / f"config-01.08-sweep-{label}.json"
        sweeps.append((out, entries, len(chunk)))
    return sweeps


def write_config(entries, out_path: Path):
    config = json.loads(BASE_CONFIG.read_text(encoding="utf-8"))
    config["can_1"]["transmit"] = entries
    config["can_1"]["general"]["tx_state"] = 1
    config["can_1"]["general"]["rx_state"] = 1
    config["can_1"]["phy"]["mode"] = 0  # Normal (not Restricted)
    out_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode", choices=("curated", "full", "both"), default="both",
        help="curated: ~32 priority PIDs; full: every PID; both (default)",
    )
    args = p.parse_args()

    print(f"Reading PID DB from {PID_CSV.name} ...")
    pids = parse_pid_csv(PID_CSV)
    print(f"  {len(pids)} PIDs")

    if not BASE_CONFIG.exists():
        raise SystemExit(f"Missing base config: {BASE_CONFIG}")

    if args.mode in ("curated", "both"):
        tx = build_transmit_list(pids)
        write_config(tx, OUT_CONFIG_CURATED)
        print(f"  CURATED: {len(tx)} entries -> {OUT_CONFIG_CURATED.name}")

    if args.mode in ("full", "both"):
        # Single 64-entry "best of" sweep
        tx = build_full_sweep(pids)
        write_config(tx, OUT_CONFIG_FULL)
        t1 = sum(1 for e in tx if e["name"].startswith("T1_"))
        t2 = sum(1 for e in tx if e["name"].startswith("T2_"))
        t3 = sum(1 for e in tx if e["name"].startswith("T3_"))
        print(f"  FULL SWEEP: {len(tx)} entries -> {OUT_CONFIG_FULL.name}")
        print(f"    Keepalive: 2  Tier1 fast: {t1}  Tier2 medium: {t2}  Tier3 sampled: {t3}")

        # Multi-config sweep that together covers EVERY PID (cap is 64/config)
        print()
        print("  Generating split sweeps to cover every PID across multiple configs:")
        sweeps = build_split_sweeps(pids)
        total_covered = 0
        for out_path, entries, slow_count in sweeps:
            write_config(entries, out_path)
            print(f"    {out_path.name}: {len(entries)} entries  (slow: {slow_count})")
            total_covered += slow_count
        print(f"    -> Together cover {total_covered} non-Tier1 PIDs across {len(sweeps)} configs")


if __name__ == "__main__":
    main()
