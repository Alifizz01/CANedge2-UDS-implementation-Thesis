"""CANedge2 config logic, no UI: read the UDS PID list, decode a config's transmit list into
"which signals does this config ask the car for", find CANedge SD cards, and write a config
to a card safely.

Key fact used throughout: the logger writes `cfg_crc32` into device.json at boot, and it is the
plain CRC32 of the config-01.08.json bytes. So comparing CRCs tells us exactly which local
config a card holds and which one the logger actually ran.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import string
import sys
import time
import zlib
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT / "20_Hardware" / "canedge"
PROFILES_DIR = CONFIG_DIR / "profiles"            # one folder per profile = exactly what goes on the SD card
PID_CSV = PROJECT / "40_Experiments" / "data" / "csv" / "vw_meb_uds_pid_list.csv"
BACKUP_DIR = CONFIG_DIR / "_card_backups"
CARD_CONFIG = "config-01.08.json"
CARD_FILES = ("config-01.08.json", "schema-01.08.json", "uischema-01.08.json")

# Request CAN-ID -> ECU (VW MEB physical addressing; response = 0x17FE.. / +8 for 11-bit)
ECUS = {0x17FC007B: "BMS", 0x17FC00B9: "DC-DC", 0x17FC0076: "Drive unit (EDU)", 0x746: "Climate",
        0x710: "Gateway", 0x767: "Navigation"}
SERVICES = {0x10: "DiagnosticSessionControl", 0x3E: "TesterPresent", 0x22: "ReadDataByIdentifier",
            0x19: "ReadDTCInformation", 0x14: "ClearDiagnosticInformation", 0x11: "ECUReset"}
SESSIONS = {0x01: "default", 0x02: "programming", 0x03: "extended"}
PHY_MODES = {0: "Normal", 1: "Restricted (listen only, no transmit)", 2: "Monitoring"}


def set_project(root) -> bool:
    """Point at a thesis project folder (the installed app doesn't live inside it)."""
    global PROJECT, CONFIG_DIR, PROFILES_DIR, BACKUP_DIR, PID_CSV
    root = Path(root)
    if not (root / "20_Hardware" / "canedge" / "profiles").is_dir():
        return False
    PROJECT, CONFIG_DIR = root, root / "20_Hardware" / "canedge"
    PROFILES_DIR, BACKUP_DIR = CONFIG_DIR / "profiles", CONFIG_DIR / "_card_backups"
    csv_path = root / "40_Experiments" / "data" / "csv" / "vw_meb_uds_pid_list.csv"
    if csv_path.is_file():
        PID_CSV = csv_path
    return True


def describe(profile_dir) -> tuple:
    """(title, description) from the profile's README.md: '# Title' then its first paragraph."""
    readme = Path(profile_dir) / "README.md"
    if not readme.is_file():
        return "", ""
    lines = readme.read_text(encoding="utf-8").splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "")
    body = [l for l in lines if l.strip() and not l.startswith("#")]
    return title, body[0].strip() if body else ""


def crc32_of(path: Path) -> str:
    return f"{zlib.crc32(Path(path).read_bytes()):08X}"


def ecu_name(req_id: int) -> str:
    return ECUS.get(req_id, f"ECU 0x{req_id:X}")


# ---------------------------------------------------------------------------- PID list
def load_pid_list(path: Path = PID_CSV) -> dict:
    """{(request_id, did): {...}} from the community VW MEB UDS list (semicolon CSV, header on row 5)."""
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    head = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Status")
    col = {name.strip(): i for i, name in enumerate(rows[head])}
    pids = {}
    for r in rows[head + 1:]:
        if len(r) <= col["Calculation"]:
            continue
        send = r[col["data send"]].split()
        try:
            req = int(r[col["ATSH"]].strip(), 16)
            if len(send) < 4 or send[1].lower() != "22":
                continue
            did = int(send[2], 16) << 8 | int(send[3], 16)
        except ValueError:
            continue
        pids[(req, did)] = {
            "name": " ".join(r[col["Popular name"]].split()), "unit": r[col["Unit"]].strip(),
            "group": r[col["group"]].strip() or "Other", "status": r[col["Status"]].strip(),
            "formula": " ".join(r[col["Calculation"]].split()), "response": " ".join(r[col["datareceived"]].split()),
            "info": " ".join(r[col["info"]].split()) if len(r) > col["info"] else "",
        }
    return pids


# ---------------------------------------------------------------------------- frames & configs
def decode_frame(data_hex: str) -> dict:
    """One CAN frame of a transmit list -> the UDS request it carries (ISO-TP single frame)."""
    b = bytes.fromhex(data_hex)
    if not b or b[0] >> 4 != 0 or not 1 <= (b[0] & 0x0F) <= 7:
        return {"service": "not a UDS single frame", "sid": None, "dids": []}
    n, sid = b[0] & 0x0F, b[1]
    payload = b[2:1 + n]
    out = {"sid": sid, "service": SERVICES.get(sid, f"service 0x{sid:02X}"), "dids": []}
    if sid == 0x22:
        out["dids"] = [payload[i] << 8 | payload[i + 1] for i in range(0, len(payload) - 1, 2)]
    elif sid == 0x10 and payload:
        out["service"] += f" ({SESSIONS.get(payload[0], hex(payload[0]))})"
    return out


def analyse(cfg: dict, pids: dict) -> dict:
    """Everything the UI shows about one config."""
    rows, warnings = [], []
    ch = cfg.get("can_1", {})
    phy = ch.get("phy", {})
    for i, tx in enumerate(ch.get("transmit", [])):
        req = int(tx.get("id", "0"), 16)
        fr = decode_frame(tx.get("data", ""))
        base = {"index": i + 1, "name": tx.get("name", ""), "enabled": tx.get("state", 1) == 1,
                "can_id": f"0x{req:X}", "ecu": ecu_name(req), "extended": tx.get("id_format") == 1,
                "period_ms": tx.get("period"), "delay_ms": tx.get("delay"), "data": tx.get("data", "").upper(),
                "service": fr["service"]}
        if not fr["dids"]:
            rows.append({**base, "did": None, "signal": None})
        for did in fr["dids"]:
            p = pids.get((req, did)) or next((v for (r, d), v in pids.items() if d == did), None)
            rows.append({**base, "did": f"0x{did:04X}", "signal": p, "in_list": (req, did) in pids})
    targeted = [r for r in rows if r["did"]]
    if phy.get("mode", 0) != 0:
        warnings.append(f"CAN 1 is in {PHY_MODES.get(phy.get('mode'), phy.get('mode'))} mode: the logger will NOT send any of these requests.")
    if targeted and not any(r["service"].startswith("DiagnosticSessionControl") for r in rows):
        warnings.append("No DiagnosticSessionControl request: some identifiers only answer in the extended session.")
    unknown = [r["did"] for r in targeted if not r["signal"]]
    if unknown:
        warnings.append(f"{len(unknown)} identifier(s) are not in the PID list, so their meaning is unknown: {', '.join(unknown[:8])}")
    disabled = sum(not r["enabled"] for r in rows)
    if disabled:
        warnings.append(f"{disabled} transmit entr{'y is' if disabled == 1 else 'ies are'} disabled (state 0).")
    periods = {r["period_ms"] for r in rows if r["period_ms"]}
    last = max((r["delay_ms"] or 0 for r in rows), default=0)
    if periods and last >= min(periods):
        warnings.append(f"The last request is delayed {last} ms but the period is {min(periods)} ms: the schedule overlaps itself.")
    ecus = {}
    for r in targeted:
        ecus[r["ecu"]] = ecus.get(r["ecu"], 0) + 1
    coverage = {}
    for (req, _), p in pids.items():
        c = coverage.setdefault(p["group"], {"total": 0, "targeted": 0})
        c["total"] += 1
    for r in targeted:
        if r["signal"] and r.get("in_list"):
            coverage[r["signal"]["group"]]["targeted"] += 1
    return {
        "frames": len(ch.get("transmit", [])), "identifiers": len(targeted), "rows": rows, "ecus": ecus,
        "period_ms": min(periods) if periods else None, "cycle_ms": last,
        "phy_mode": PHY_MODES.get(phy.get("mode", 0), str(phy.get("mode"))), "bitrate": phy.get("bit_rate_std"),
        "log_rx": ch.get("filter", {}) != {}, "coverage": coverage, "warnings": warnings,
    }


def summary(path: Path, pids: dict) -> dict:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    a = analyse(cfg, pids)
    title, about = describe(Path(path).parent)
    return {"file": Path(path).parent.name, "path": str(path), "crc32": crc32_of(path), "frames": a["frames"],
            "title": title, "about": about,
            "identifiers": a["identifiers"], "ecus": a["ecus"], "warnings": len(a["warnings"]),
            "modified": Path(path).stat().st_mtime, "archived": "_archive" in Path(path).parts}


def local_configs(include_archive=True) -> list[Path]:
    """The config-01.08.json of every profile folder (profiles/<name>/), archived ones last."""
    files = sorted(p for p in PROFILES_DIR.glob(f"*/{CARD_CONFIG}") if p.parent.name != "_archive")
    if include_archive:
        files += sorted(PROFILES_DIR.glob(f"_archive/*/{CARD_CONFIG}"))
    return files


# ---------------------------------------------------------------------------- SD cards
def _candidate_roots(extra=()):
    roots = [Path(p) for p in extra]
    if sys.platform == "win32":
        import ctypes
        k32 = ctypes.windll.kernel32
        mask, system = k32.GetLogicalDrives(), os.environ.get("SystemDrive", "C:").upper()[0]
        for i, letter in enumerate(string.ascii_uppercase):
            if mask >> i & 1 and letter != system and k32.GetDriveTypeW(f"{letter}:\\") in (2, 3):   # removable / fixed
                roots.append(Path(f"{letter}:\\"))
    else:
        for base in ("/media", "/run/media", "/Volumes"):
            for p in Path(base).glob("*/*") if base != "/Volumes" else Path(base).glob("*"):
                roots.append(p)
    return roots


def find_cards(extra=(), local_crcs: dict | None = None) -> list[dict]:
    """Every mounted folder that looks like a CANedge SD card (device.json + config at its root)."""
    cards = []
    for root in _candidate_roots(extra):
        try:
            dev_file = root / "device.json"
            if not dev_file.is_file():
                continue
            dev = json.loads(dev_file.read_text(encoding="utf-8"))
            if "cfg_crc32" not in dev and "fw_ver" not in dev:
                continue
            cfg = root / dev.get("cfg_name", CARD_CONFIG)
            file_crc = crc32_of(cfg) if cfg.is_file() else None
            booted = (dev.get("cfg_crc32") or "").upper() or None
            log_dir = root / "LOG" / dev.get("id", "")
            sessions = sorted(p.name for p in log_dir.iterdir() if p.is_dir()) if log_dir.is_dir() else []
            mf4 = sum(1 for _ in log_dir.rglob("*.MF4")) if log_dir.is_dir() else 0
            try:
                usage = shutil.disk_usage(root)
                space = {"total_gb": round(usage.total / 1e9, 1), "free_gb": round(usage.free / 1e9, 1)}
            except OSError:
                space = None
            local = local_crcs or {}
            cards.append({
                "root": str(root), "device_id": dev.get("id"), "firmware": dev.get("fw_ver"), "hardware": dev.get("hw_ver"),
                "config_file": cfg.name, "config_crc": file_crc, "booted_crc": booted,
                "config_match": local.get(file_crc), "booted_match": local.get(booted),
                # the file on the card changed after the logger last started: power-cycle it to apply
                "pending": bool(file_crc and booted and file_crc != booted),
                "sessions": len(sessions), "last_session": sessions[-1] if sessions else None, "mf4_files": mf4,
                "space": space,
            })
        except (OSError, ValueError):
            continue
    return cards


def deploy(card_root: str, config_path: Path) -> dict:
    """Copy a profile onto the card: its config-01.08.json plus the schema files next to it.
    Whatever the card held is backed up on the PC first (one dated folder per write), every
    write is atomic, and the config is verified by CRC afterwards."""
    root, profile = Path(card_root), Path(config_path).parent
    if not (root / "device.json").is_file():
        raise ValueError(f"{root} is not a CANedge SD card (no device.json).")
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))     # refuse broken JSON before touching the card
    if "can_1" not in cfg or "general" not in cfg:
        raise ValueError(f"{profile.name} doesn't look like a CANedge config.")
    dev = json.loads((root / "device.json").read_text(encoding="utf-8"))
    on_card = [f for f in CARD_FILES if (root / f).is_file()]
    backup = None
    if on_card:
        backup = BACKUP_DIR / f"{time.strftime('%Y-%m-%d_%H%M%S')}_{dev.get('id', 'card').lower()}"
        backup.mkdir(parents=True, exist_ok=True)
        for f in on_card:
            shutil.copy2(root / f, backup / f)
    for f in CARD_FILES:
        if (profile / f).is_file():
            tmp = root / (f + ".tmp")
            shutil.copyfile(profile / f, tmp)
            os.replace(tmp, root / f)
    written, wanted = crc32_of(root / CARD_CONFIG), crc32_of(config_path)
    if written != wanted:
        raise OSError(f"Verification failed: card has CRC {written}, expected {wanted}.")
    return {"written": str(root / CARD_CONFIG), "crc32": written, "profile": profile.name,
            "backup": str(backup) if backup else None}
