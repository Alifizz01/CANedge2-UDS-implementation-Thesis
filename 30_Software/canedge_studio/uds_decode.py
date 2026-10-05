"""Decode a CANedge MF4 log into battery signals.

The logger records both its own UDS requests (Tx) and the vehicle's answers (Rx), so one log
says what was asked, what came back, and what each answer means:

    request  0x17FC007B  03 22 1E 3B ..        ReadDataByIdentifier 0x1E3B (HV pack voltage)
    answer   0x17FE007B  05 62 1E 3B XX YY ..  positive response -> formula from the PID list

On top of the PID list's formulas, three findings from the thesis are applied:
  * 0x1E33 / 0x1E34: the leading 16 bits are the cell voltage x 1/4096 V, ZZ is the cell number
  * cell-voltage identifiers returning raw 0x0FFE mean "not available" (unpopulated slot)
  * answers longer than one frame come back truncated (the logger can't send ISO-TP flow
    control), so they are marked partial
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np

PLACEHOLDERS = ("WW", "XX", "YY", "ZZ", "VV", "UU", "TT", "SS")
NRC = {0x10: "general reject", 0x11: "service not supported", 0x12: "sub-function not supported",
       0x13: "incorrect message length", 0x14: "response too long", 0x21: "busy, repeat request",
       0x22: "conditions not correct", 0x24: "request sequence error", 0x31: "request out of range",
       0x33: "security access denied", 0x78: "response pending", 0x7E: "not supported in active session",
       0x7F: "service not supported in active session"}
SERVICES = {0x01: "OBD-II current data", 0x09: "OBD-II vehicle info", 0x10: "DiagnosticSessionControl",
            0x22: "ReadDataByIdentifier", 0x3E: "TesterPresent", 0x19: "ReadDTCInformation", 0x11: "ECUReset"}
CELL_EXTREMES = {0x1E33: "highest", 0x1E34: "lowest"}
NOT_AVAILABLE = 0x0FFE


def request_id_for(resp_id: int) -> int | None:
    """VW MEB physical addressing: 0x17FExxyy answers 0x17FCxxyy; 11-bit 0x7xx answers 0x7xx-8."""
    if resp_id >> 16 == 0x17FE:
        return (resp_id & 0xFFFF) | 0x17FC0000
    if 0x700 <= resp_id <= 0x7FF:
        return resp_id - 8
    return None


# ---------------------------------------------------------------------------- PID list with formulas
def load_pids(path: Path) -> dict:
    """{(request_id, did): definition} including where each formula letter sits in the answer."""
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    head = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Status")
    col = {n.strip(): i for i, n in enumerate(rows[head])}
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
        recv = r[col["datareceived"]].split()
        labels = {pos: tok.upper() for pos, tok in enumerate(recv[4:]) if tok.upper() in PLACEHOLDERS}
        pids[(req, did)] = {"name": " ".join(r[col["Popular name"]].split()), "unit": r[col["Unit"]].strip(),
                            "group": r[col["group"]].strip() or "Other", "calc": r[col["Calculation"]].strip(),
                            "labels": labels}
    return pids


def _expr(formula: str) -> str:
    """'(XX*2^8+YY)/4 = Voltage in decimal' -> '(XX*2**8+YY)/4'."""
    parts = re.split(r"\s*=\s*(?![=>])", formula.strip())
    expr = next((p for p in parts if any(ph in p.upper() for ph in PLACEHOLDERS)), parts[0])
    expr = re.sub(r"(\d),(\d)", r"\1.\2", expr).replace("^", "**")
    return re.split(r"\s+(?=[A-Za-z]{2,})(?!\*\*)", expr)[0].strip()


def apply_formula(pid: dict, value: bytes):
    """-> (value, kind) with kind numeric | enum | partial | unknown."""
    env = {lab: value[pos] for pos, lab in pid["labels"].items() if pos < len(value)}
    calc = pid["calc"]
    if not calc:
        return None, "unknown"
    if "=>" in calc:                                     # "XX = 0 => standby, XX = 1 => driving"
        m = re.findall(r"([A-Z]{2})\s*=\s*(\d+)\s*=>\s*([^,;]+)", calc)
        if m and m[0][0] in env:
            table = {int(raw): text.strip() for lab, raw, text in m if lab == m[0][0]}
            return table.get(env[m[0][0]], f"code {env[m[0][0]]}"), "enum"
    expr = _expr(calc)
    used = [ph for ph in PLACEHOLDERS if ph in expr]
    if not used:
        return None, "unknown"
    try:
        v = eval(expr, {"__builtins__": {}}, {ph: env.get(ph, 0) for ph in used})   # formulas are the list's own, letters only
    except Exception:
        return None, "unknown"
    if not isinstance(v, (int, float)):
        return None, "unknown"
    return float(v), "partial" if any(ph not in env for ph in used) else "numeric"


# ---------------------------------------------------------------------------- reading the MF4
def read_frames(paths) -> dict:
    """All CAN data frames of one or more MF4 files (one session may be split into parts)."""
    from asammdf import MDF

    t_all, ids_all, data_all, tx_all, starts = [], [], [], [], []
    internal = 0
    for p in paths:
        mdf = MDF(str(p))
        t0 = mdf.start_time.timestamp()
        starts.append(t0)
        for i, g in enumerate(mdf.groups):
            name = g.channel_group.acq_name or ""
            if name.startswith("CAN9"):                      # the logger's internal bus: its own GNSS / IMU messages
                internal += g.channel_group.cycles_nr
                continue
            if not g.channel_group.cycles_nr or not name.startswith(("CAN1", "CAN2")):
                continue
            if "CAN_DataFrame.ID" not in {c.name for c in g.channels}:
                continue
            ids = np.asarray(mdf.get("CAN_DataFrame.ID", group=i).samples, dtype=np.int64)
            sig = mdf.get("CAN_DataFrame.DataBytes", group=i)
            data = np.asarray(sig.samples)
            if data.dtype == object:
                data = np.array([np.frombuffer(bytes(b), np.uint8)[:8].tolist() + [0] * (8 - min(8, len(b))) for b in data])
            t_all.append(np.asarray(sig.timestamps) + t0)
            ids_all.append(ids)
            data_all.append(data[:, :8])
            tx_all.append(np.full(len(ids), "_Tx" in name))
        mdf.close()
    if not t_all:
        return {"t": np.array([]), "id": np.array([], np.int64), "data": np.zeros((0, 8), np.uint8), "tx": np.array([], bool),
                "start": min(starts, default=0), "internal": internal}
    order = np.argsort(np.concatenate(t_all), kind="stable")
    return {"t": np.concatenate(t_all)[order], "id": np.concatenate(ids_all)[order], "data": np.concatenate(data_all)[order],
            "tx": np.concatenate(tx_all)[order], "start": min(starts), "internal": internal}


# ---------------------------------------------------------------------------- decoding
def decode_log(paths, pids: dict, ecu_names: dict, max_points=4000) -> dict:
    return decode_frames(read_frames(paths), pids, ecu_names, max_points)


def decode_frames(fr: dict, pids: dict, ecu_names: dict, max_points=4000) -> dict:
    start = fr["start"]
    signals, last_request, services = {}, {}, {}

    def tally(req, sid, field):
        k = (req, sid)
        services.setdefault(k, {"ecu": ecu_names.get(req, f"0x{req:X}"), "service": SERVICES.get(sid, f"0x{sid:02X}"),
                                "requests": 0, "positive": 0, "negative": 0})[field] += 1
    n_req = n_pos = n_neg = n_partial = 0

    def sig(req, did, suffix="", name=None, unit=None):
        key = f"{req:X}:{did:04X}{suffix}"
        if key not in signals:
            p = pids.get((req, did)) or next((v for (r, d), v in pids.items() if d == did), None)
            signals[key] = {"key": key, "ecu": ecu_names.get(req, f"0x{req:X}"), "did": f"0x{did:04X}",
                            "name": name or (p["name"] if p else "not in the PID list"), "unit": unit if unit is not None else (p["unit"] if p else ""),
                            "group": p["group"] if p else "Unknown", "formula": p["calc"] if p else "",
                            "requested": 0, "answered": 0, "t": [], "v": [], "kinds": set(), "nrc": None, "raw_last": None}
        return signals[key]

    for t, cid, data, tx in zip(fr["t"], fr["id"], fr["data"], fr["tx"]):
        b = bytes(int(x) for x in data)
        pci = b[0] >> 4
        if tx:                                            # the logger's own request
            if pci == 0 and len(b) > 1:
                tally(int(cid), b[1], "requests")
            if pci == 0 and len(b) > 3 and b[1] == 0x22:
                did = b[2] << 8 | b[3]
                n_req += 1
                sig(int(cid), did)["requested"] += 1
                last_request[int(cid)] = did
            continue
        req = request_id_for(int(cid))
        if req is None:
            continue
        if pci == 0 and b[1] == 0x7F:                      # negative response: belongs to the last DID we asked that ECU
            tally(req, b[2], "negative")
            if b[2] == 0x22 and req in last_request:
                n_neg += 1
                s = sig(req, last_request[req])
                s["nrc"] = NRC.get(b[3], f"0x{b[3]:02X}")
            continue
        if pci == 0 and b[1] >= 0x40 and b[1] != 0x7F:
            tally(req, b[1] - 0x40, "positive")
        elif pci == 1 and b[2] >= 0x40:
            tally(req, b[2] - 0x40, "positive")
        if pci == 0 and b[1] == 0x62:
            did, value, partial = b[2] << 8 | b[3], b[4:1 + (b[0] & 0x0F)], False
        elif pci == 1 and b[2] == 0x62:                    # first frame of a longer answer: only 3 value bytes arrive
            did, value, partial = b[3] << 8 | b[4], b[5:8], True
        else:
            continue
        n_pos += 1
        n_partial += partial
        s = sig(req, did)
        s["answered"] += 1
        s["raw_last"] = value.hex(" ").upper()
        tt = float(t - start)
        if did in CELL_EXTREMES and len(value) >= 4:      # thesis: leading 16 bits / 4096 = cell voltage, ZZ = cell number
            which = CELL_EXTREMES[did]
            s["t"].append(tt); s["v"].append(float(value[3])); s["kinds"].add("numeric")
            s["name"], s["unit"] = f"Cell number with the {which} voltage", "#"
            sv = sig(req, did, ".v", f"{which.capitalize()} cell voltage", "V")
            sv["answered"] = s["answered"]
            sv["t"].append(tt); sv["v"].append((value[0] << 8 | value[1]) / 4096); sv["kinds"].add("numeric")
            sv["formula"] = "(WW*2^8+XX)/4096  (thesis, not in the list)"
            continue
        p = pids.get((req, did)) or next((v for (r, d), v in pids.items() if d == did), None)
        if p is None:
            s["kinds"].add("unknown")
            continue
        if "cell voltage" in p["name"].lower() and len(value) >= 2 and (value[0] << 8 | value[1]) == NOT_AVAILABLE:
            s["kinds"].add("not available")
            continue
        v, kind = apply_formula(p, value)
        s["kinds"].add("partial" if partial else kind)
        if v is not None:
            s["t"].append(tt); s["v"].append(v)

    out = []
    for s in signals.values():
        nums = [v for v in s["v"] if isinstance(v, float)]
        status = ("negative: " + s["nrc"]) if s["nrc"] and not s["answered"] else \
                 "never answered" if s["requested"] and not s["answered"] else \
                 "not available (0x0FFE)" if "not available" in s["kinds"] else \
                 "truncated (multi-frame)" if "partial" in s["kinds"] else \
                 "no formula" if not s["v"] else "ok"
        stride = max(1, len(s["t"]) // max_points)
        out.append({k: s[k] for k in ("key", "ecu", "did", "name", "unit", "group", "formula", "requested", "answered", "raw_last")} | {
            "status": status, "samples": len(s["v"]),
            "last": s["v"][-1] if s["v"] else None,
            "min": min(nums) if nums else None, "max": max(nums) if nums else None,
            "mean": sum(nums) / len(nums) if nums else None,
            "t": s["t"][::stride], "v": s["v"][::stride],
        })
    out.sort(key=lambda s: (s["ecu"], s["did"], s["key"]))
    cells = []
    for s in out:
        m = re.search(r"cell voltage - cell (\d+)", s["name"], re.I)
        if m:
            cells.append({"cell": int(m.group(1)), "did": s["did"], "volt": s["last"] if isinstance(s["last"], float) else None, "status": s["status"]})
    cells.sort(key=lambda c: c["cell"])
    duration = float(fr["t"][-1] - fr["t"][0]) if len(fr["t"]) else 0.0
    return {"start": start, "duration_s": duration, "frames": int(len(fr["t"])), "internal_frames": int(fr.get("internal", 0)), "requests": n_req, "positive": n_pos,
            "negative": n_neg, "truncated": n_partial, "signals": out, "cells": cells,
            "services": sorted(services.values(), key=lambda x: (x["ecu"], x["service"])),
            "answered_ids": sum(1 for s in out if s["answered"]), "requested_ids": sum(1 for s in out if s["requested"])}


def export_csv(result: dict, path: Path):
    """Long format: one row per decoded sample."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "ecu", "did", "signal", "value", "unit", "status"])
        for s in result["signals"]:
            for t, v in zip(s["t"], s["v"]):
                w.writerow([f"{t:.3f}", s["ecu"], s["did"], s["name"], v, s["unit"], s["status"]])
