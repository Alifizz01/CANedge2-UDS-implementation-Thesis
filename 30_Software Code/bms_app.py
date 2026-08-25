"""
BMS UDS Log Explorer — Streamlit app.

Run with:
    streamlit run bms_app.py

Loads VW MEB BMS UDS traffic from MF4 logs (CANedge SD card or single file),
decodes every 0x17FE007B response into named signals using the same PID
database as uds_battery_decoder.py, and exposes:

  1. Load          - point to a file or folder, see what was captured
  2. Decoded       - filterable table of decoded signal samples + CSV export
  3. Plots         - interactive time-series, multi-signal overlay, PNG export
  4. Raw sniffer   - every UDS frame with PCI/SID/PID/decoded value inline
  5. Summary       - per-PID statistics + .txt export, PID coverage report
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from asammdf import MDF

import uds_battery_decoder as udsd

BMS_REQUEST_ID = 0x17FC007B
BMS_RESPONSE_ID = 0x17FE007B

# Mapping from request CAN-ID to (ECU label, response CAN-ID).
# VW MEB convention:
#   29-bit extended: request 0x17FCxxYY -> response 0x17FExxYY
#   11-bit standard: request 0xRRR      -> response 0xRRR + 8
# Pre-populated for the probe-ECUs config; auto-extended from any config JSON.
DEFAULT_ECU_PAIRS: dict[int, tuple[str, int]] = {
    0x17FC007B: ("BMS",      0x17FE007B),
    0x17FC00B9: ("DCDC",     0x17FE00B9),
    0x17FC0076: ("EDU",      0x17FE0076),
    0x746:      ("Climate",  0x74E),
    0x710:      ("Gateway",  0x718),
    0x767:      ("Nav",      0x76F),
}


def derive_response_id(req_id: int) -> int:
    """Derive the response CAN-ID for a UDS physical-addressed request.

    29-bit VW MEB pattern: 0x17FCxxYY -> 0x17FExxYY.
    11-bit standard:       0xRRR     -> 0xRRR + 8.
    """
    if (req_id >> 16) == 0x17FC:
        return (req_id & 0xFFFF) | 0x17FE0000
    if req_id <= 0x7FF:
        return req_id + 8
    return req_id


def load_ecu_pairs_from_config(config_path: str | Path | None) -> dict[int, tuple[str, int]]:
    """Parse a CANedge config JSON's can_1.transmit list into request->ECU map.

    Falls back to DEFAULT_ECU_PAIRS when no config is supplied or parsing fails.
    """
    pairs = dict(DEFAULT_ECU_PAIRS)
    if not config_path:
        return pairs
    try:
        import json
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return pairs
    for ch_key in ("can_1", "can_2"):
        ch = cfg.get(ch_key, {})
        for tx in ch.get("transmit", []):
            try:
                req = int(tx["id"], 16)
            except (KeyError, ValueError):
                continue
            name = tx.get("name", "").split("_")[0] or f"ECU_{req:X}"
            resp = derive_response_id(req)
            pairs.setdefault(req, (name, resp))
    return pairs

# Standard ISO 14229 negative response codes (subset that BMS actually emits)
NRC_NAMES = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x14: "responseTooLong",
    0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect",
    0x24: "requestSequenceError",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceededNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x70: "uploadDownloadNotAccepted",
    0x72: "generalProgrammingFailure",
    0x78: "requestCorrectlyReceivedResponsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}

def _has_kaleido() -> bool:
    try:
        import kaleido  # noqa: F401
        return True
    except Exception:
        return False


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PID_CSV = PROJECT_ROOT / "40_Experiments" / "Exprimental Data" / "csv" / "VW MEB UDS PIDs list.csv"
DEFAULT_LOG_PATH = r"D:\LOG\2A73E1CC"
DEFAULT_CONFIG_JSON = PROJECT_ROOT / "20_Hardware" / "CANedge" / "config-01.08-probe-ECUs.json"


# ── Loaders (cached) ──────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_pid_db(pid_csv: str) -> dict:
    return udsd.parse_pid_csv(Path(pid_csv))


def _discover_mf4(path_str: str) -> list[tuple[str, Path]]:
    p = Path(path_str)
    if p.is_file() and p.suffix.lower() == ".mf4":
        return [(p.parent.name or p.stem, p)]
    if not p.is_dir():
        return []
    files = []
    # Direct MF4s in this folder
    for f in sorted(p.glob("*.MF4")) + sorted(p.glob("*.mf4")):
        files.append((p.name + "/" + f.stem, f))
    # One level of session subfolders (CANedge layout)
    if not files:
        for sub in sorted(p.iterdir()):
            if not sub.is_dir():
                continue
            mf4s = sorted(sub.glob("*.MF4")) + sorted(sub.glob("*.mf4"))
            if mf4s:
                files.append((sub.name, mf4s[0]))
    return files


@st.cache_data(show_spinner="Reading MF4...", max_entries=8)
def load_mf4_frames(mf4_path: str, mtime: float,
                    req_ids: tuple[int, ...], resp_ids: tuple[int, ...],
                    id_to_ecu: tuple[tuple[int, str], ...]) -> pd.DataFrame:
    """Return every UDS frame on any of the configured ECU IDs.

    Columns: timestamp, can_id, ecu, direction, raw_bytes, raw_hex.
    Cached on (path, mtime, id sets) so repeated tab switches are free.
    """
    req_set = set(req_ids)
    resp_set = set(resp_ids)
    all_set = req_set | resp_set
    ecu_map = dict(id_to_ecu)

    mdf = MDF(mf4_path)
    rows = []
    for i, g in enumerate(mdf.groups):
        if g.channel_group.cycles_nr == 0:
            continue
        ch_names = {c.name for c in g.channels}
        if "CAN_DataFrame.ID" not in ch_names:
            continue
        try:
            ids = np.asarray(mdf.get("CAN_DataFrame.ID", group=i).samples, dtype=np.int64)
        except Exception:
            continue
        id_arr = ids.astype(np.int64)
        mask = np.isin(id_arr, list(all_set))
        if not mask.any():
            continue
        ts = np.asarray(mdf.get("CAN_DataFrame.ID", group=i).timestamps)
        data = np.asarray(mdf.get("CAN_DataFrame.DataBytes", group=i).samples)
        sel_ids = id_arr[mask]
        sel_ts = ts[mask]
        sel_data = data[mask]
        for t, cid, payload in zip(sel_ts, sel_ids, sel_data):
            if hasattr(payload, "tobytes"):
                payload = payload.tobytes()
            payload = bytes(payload)
            cid_int = int(cid)
            rows.append({
                "timestamp": float(t),
                "can_id": cid_int,
                "can_id_hex": f"0x{cid_int:X}",
                "ecu": ecu_map.get(cid_int, ""),
                "direction": "TX" if cid_int in req_set else "RX",
                "raw_bytes": payload,
                "raw_hex": " ".join(f"{b:02X}" for b in payload),
            })
    if not rows:
        return pd.DataFrame(columns=["timestamp", "can_id", "can_id_hex", "ecu",
                                     "direction", "raw_bytes", "raw_hex"])
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


# ── Frame decode → richer DataFrame ───────────────────────────────

def annotate_frames(frames: pd.DataFrame, pids: dict) -> pd.DataFrame:
    """Add parsed columns: pci_kind, sid, pid, pid_hex, pid_name, value_bytes,
    value, value_kind, nrc, nrc_name."""
    if frames.empty:
        return frames.assign(
            pci_kind="", sid=pd.NA, pid=pd.NA, pid_hex="", pid_name="",
            value=pd.NA, value_kind="", unit="", group="",
            nrc=pd.NA, nrc_name="", ecu=frames.get("ecu", ""),
        )
    out = []
    for _, row in frames.iterrows():
        payload = row["raw_bytes"]
        kind = "REQ" if row["direction"] == "TX" else "—"
        sid = pid = value = value_kind = unit = grp = name = nrc = nrc_name = None
        pid_hex = ""
        if row["direction"] == "TX" and len(payload) >= 4 and payload[1] == 0x22:
            sid = 0x22
            pid = (payload[2] << 8) | payload[3]
            pid_hex = f"0x{pid:04X}"
            if pid in pids:
                name = pids[pid]["name"]
                unit = pids[pid]["unit"]
                grp = pids[pid]["group"]
            kind = "REQ"
        elif row["direction"] == "RX":
            decoded = udsd.decode_response_frame(payload)
            kind = decoded["kind"]
            pid = decoded.get("pid")
            if kind == "NEG":
                sid = 0x7F
                nrc = decoded.get("nrc")
                nrc_name = NRC_NAMES.get(nrc, "")
            elif kind in ("SF", "FF") and pid is not None:
                sid = 0x62
                pid_hex = f"0x{pid:04X}"
                if pid in pids:
                    pid_def = pids[pid]
                    name = pid_def["name"]
                    unit = pid_def["unit"]
                    grp = pid_def["group"]
                    v, vk = udsd.decode_value(pid_def, decoded.get("value_bytes", b""))
                    value = v
                    value_kind = vk
        out.append({
            **row,
            "pci_kind": kind,
            "sid": sid,
            "pid": pid,
            "pid_hex": pid_hex,
            "pid_name": name or "",
            "unit": unit or "",
            "group": grp or "",
            "value": value,
            "value_kind": value_kind or "",
            "nrc": nrc,
            "nrc_name": nrc_name or "",
        })
    return pd.DataFrame(out)


# ── UI ────────────────────────────────────────────────────────────

st.set_page_config(page_title="BMS UDS Log Explorer", layout="wide")
st.title("BMS UDS Log Explorer")
st.caption("VW MEB / ID. Buzz — decode CANedge MF4 logs from the SD card.")

with st.sidebar:
    st.header("Configuration")
    pid_csv = st.text_input("PID CSV", value=str(DEFAULT_PID_CSV))
    log_path = st.text_input("MF4 file or folder", value=DEFAULT_LOG_PATH)
    config_json = st.text_input("CANedge config (for ECU list)",
                                value=str(DEFAULT_CONFIG_JSON))
    load_btn = st.button("Load", type="primary", width='stretch')

    if "frames_per_session" not in st.session_state:
        st.session_state.frames_per_session = {}

    if load_btn:
        try:
            pids = load_pid_db(pid_csv)
        except Exception as e:
            st.error(f"Failed to read PID CSV: {e}")
            st.stop()
        files = _discover_mf4(log_path)
        if not files:
            st.error(f"No MF4 files found at {log_path}")
            st.stop()
        ecu_pairs = load_ecu_pairs_from_config(config_json)
        req_ids = tuple(sorted(ecu_pairs.keys()))
        resp_ids = tuple(sorted({resp for _, resp in ecu_pairs.values()}))
        id_to_ecu_list = []
        for req, (name, resp) in ecu_pairs.items():
            id_to_ecu_list.append((req, name))
            id_to_ecu_list.append((resp, name))
        id_to_ecu = tuple(id_to_ecu_list)

        ann_per_session = {}
        for label, path in files:
            mtime = path.stat().st_mtime
            frames = load_mf4_frames(str(path), mtime, req_ids, resp_ids, id_to_ecu)
            ann_per_session[label] = annotate_frames(frames, pids)
        st.session_state.pids = pids
        st.session_state.frames_per_session = ann_per_session
        st.session_state.ecu_pairs = ecu_pairs
        ecu_summary = ", ".join(f"{n} (0x{r:X}→ 0x{p:X})"
                                for r, (n, p) in ecu_pairs.items())
        st.success(f"Loaded {len(files)} session(s). ECUs: {ecu_summary}")

if not st.session_state.get("frames_per_session"):
    st.info("Enter a path in the sidebar and click **Load**. "
            f"Default: `{DEFAULT_LOG_PATH}` (CANedge SD card layout).")
    st.stop()

pids = st.session_state.pids
sessions = st.session_state.frames_per_session

with st.sidebar:
    st.divider()
    session_pick = st.multiselect(
        "Sessions to include",
        options=list(sessions.keys()),
        default=list(sessions.keys()),
    )

# Combined DataFrame across selected sessions (with session column).
parts = []
for s in session_pick:
    df = sessions[s].copy()
    df["session"] = s
    parts.append(df)
df_all = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
df_decoded = df_all[df_all["value"].notna()].copy()

tab_load, tab_decoded, tab_plots, tab_raw, tab_summary = st.tabs(
    ["Load", "Decoded signals", "Plots", "Raw sniffer", "Summary"]
)

# ── Tab: Load overview ────────────────────────────────────────────
with tab_load:
    st.subheader("Sessions loaded")
    rows = []
    for s, df in sessions.items():
        rx = (df["direction"] == "RX").sum()
        tx = (df["direction"] == "TX").sum()
        sf = (df["pci_kind"] == "SF").sum()
        ff = (df["pci_kind"] == "FF").sum()
        cf = (df["pci_kind"] == "CF").sum()
        neg = (df["pci_kind"] == "NEG").sum()
        dec = df["value"].notna().sum()
        uniq = df.loc[df["value"].notna(), "pid"].nunique()
        rows.append({
            "session": s, "TX": tx, "RX": rx,
            "SF": sf, "FF": ff, "CF": cf, "NEG": neg,
            "decoded values": dec, "unique PIDs": uniq,
        })
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

    st.caption(f"PID database: {len(pids)} PIDs known.")
    if df_decoded.empty:
        st.warning("No decoded values in the selected sessions yet.")

# ── Tab: Decoded signals table ────────────────────────────────────
with tab_decoded:
    st.subheader("Decoded signal samples")
    if df_decoded.empty:
        st.info("Nothing decoded.")
    else:
        c1, c2, c3 = st.columns(3)
        groups = sorted(g for g in df_decoded["group"].unique() if g)
        sel_groups = c1.multiselect("Group", groups, default=groups)
        pid_options = sorted(df_decoded["pid_hex"].unique())
        sel_pids = c2.multiselect("PID", pid_options, default=[])
        kinds = sorted(df_decoded["value_kind"].unique())
        sel_kinds = c3.multiselect("Value kind", kinds, default=kinds)

        mask = df_decoded["group"].isin(sel_groups) & df_decoded["value_kind"].isin(sel_kinds)
        if sel_pids:
            mask &= df_decoded["pid_hex"].isin(sel_pids)

        view = df_decoded.loc[mask, [
            "session", "timestamp", "ecu", "can_id_hex", "pid_hex", "pid_name",
            "unit", "value", "value_kind", "group", "raw_hex",
        ]].sort_values(["session", "timestamp"])

        st.caption(f"{len(view):,} rows")
        st.dataframe(view, width='stretch', hide_index=True, height=520)

        csv_buf = view.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv_buf,
            file_name="decoded_signals.csv",
            mime="text/csv",
        )

# ── Tab: Plots ────────────────────────────────────────────────────
with tab_plots:
    st.subheader("Time-series plots")
    if df_decoded.empty:
        st.info("Nothing to plot.")
    else:
        # Build pretty labels
        labels = (
            df_decoded.groupby("pid_hex")
            .agg(name=("pid_name", "first"), unit=("unit", "first"))
            .reset_index()
        )
        labels["label"] = labels.apply(
            lambda r: f"{r['pid_hex']}  {r['name']}  [{r['unit']}]", axis=1
        )
        label_map = dict(zip(labels["label"], labels["pid_hex"]))

        sel_labels = st.multiselect(
            "Signals (multi-select to overlay)",
            options=labels["label"].tolist(),
            default=labels["label"].tolist()[:1],
        )
        overlay_mode = st.radio(
            "Overlay mode",
            ["Single axis (same unit)", "Subplots (one per signal)"],
            horizontal=True,
        )

        if sel_labels:
            sel_pids = [label_map[l] for l in sel_labels]
            sub = df_decoded[df_decoded["pid_hex"].isin(sel_pids)].copy()
            sub = sub[sub["value_kind"].isin(["numeric", "partial"])]

            if sub.empty:
                st.warning("Selected signals have no numeric samples.")
            elif overlay_mode.startswith("Single"):
                fig = px.line(
                    sub, x="timestamp", y="value",
                    color="pid_hex", line_dash="session",
                    hover_data=["pid_name", "unit", "raw_hex"],
                    markers=True,
                )
                fig.update_layout(height=520, xaxis_title="time (s)",
                                  yaxis_title="value")
                st.plotly_chart(fig, width='stretch')
                png = fig.to_image(format="png", width=1200, height=520) \
                    if _has_kaleido() else None
                if png:
                    st.download_button("Download PNG", png,
                                       file_name="plot.png", mime="image/png")
                else:
                    st.caption("Install `kaleido` for PNG export: `pip install kaleido`")
            else:
                from plotly.subplots import make_subplots
                fig = make_subplots(rows=len(sel_pids), cols=1, shared_xaxes=True,
                                    subplot_titles=sel_labels)
                for i, pid_hex in enumerate(sel_pids, start=1):
                    s = sub[sub["pid_hex"] == pid_hex]
                    for sess, grp in s.groupby("session"):
                        fig.add_trace(
                            go.Scatter(x=grp["timestamp"], y=grp["value"],
                                       mode="lines+markers", name=f"{pid_hex} {sess}"),
                            row=i, col=1,
                        )
                fig.update_layout(height=260 * len(sel_pids), showlegend=False)
                st.plotly_chart(fig, width='stretch')
                png = fig.to_image(format="png", width=1200, height=260 * len(sel_pids)) \
                    if _has_kaleido() else None
                if png:
                    st.download_button("Download PNG", png,
                                       file_name="plot.png", mime="image/png")

# ── Tab: Raw sniffer ──────────────────────────────────────────────
with tab_raw:
    st.subheader("Raw UDS frames")
    if df_all.empty:
        st.info("No frames.")
    else:
        c1, c2, c3 = st.columns(3)
        dirs = c1.multiselect("Direction", ["TX", "RX"], default=["TX", "RX"])
        kinds_all = sorted(k for k in df_all["pci_kind"].unique() if k)
        sel_k = c2.multiselect("PCI kind", kinds_all, default=kinds_all)
        search = c3.text_input("Search (PID hex, name, raw)", value="")

        view = df_all[df_all["direction"].isin(dirs) & df_all["pci_kind"].isin(sel_k)]
        if search:
            s = search.upper()
            view = view[
                view["pid_hex"].str.upper().str.contains(s, na=False)
                | view["pid_name"].str.upper().str.contains(s, na=False)
                | view["raw_hex"].str.upper().str.contains(s, na=False)
            ]

        # Highlight negative responses
        def _style_neg(row):
            color = "background-color: #5a1a1a" if row["pci_kind"] == "NEG" else ""
            return [color] * len(row)

        cols = ["session", "timestamp", "ecu", "can_id_hex", "direction",
                "pci_kind", "pid_hex", "pid_name", "value", "unit",
                "nrc", "nrc_name", "raw_hex"]
        view_disp = view[cols].sort_values(["session", "timestamp"])
        st.caption(f"{len(view_disp):,} frames")
        st.dataframe(
            view_disp.style.apply(_style_neg, axis=1),
            width='stretch', hide_index=True, height=560,
        )

# ── Tab: Summary ──────────────────────────────────────────────────
with tab_summary:
    st.subheader("Per-PID statistics")
    if df_decoded.empty:
        st.info("Nothing decoded.")
    else:
        num = df_decoded[df_decoded["value_kind"].isin(["numeric", "partial"])].copy()
        num["value"] = pd.to_numeric(num["value"], errors="coerce")
        agg = (
            num.groupby(["pid_hex", "pid_name", "unit", "group"])
            .agg(count=("value", "size"),
                 first=("value", "first"),
                 last=("value", "last"),
                 min=("value", "min"),
                 max=("value", "max"),
                 mean=("value", "mean"))
            .reset_index()
            .sort_values("pid_hex")
        )
        st.dataframe(agg, width='stretch', hide_index=True)

        # Coverage report
        seen = set(df_decoded["pid"].dropna().astype(int).unique())
        unseen = sorted(set(pids.keys()) - seen)
        st.caption(
            f"Coverage: {len(seen)}/{len(pids)} PIDs observed. "
            f"{len(unseen)} known PIDs not seen in selected sessions."
        )

        # .txt export matching the existing decoder's summary style
        buf = io.StringIO()
        buf.write("VW MEB UDS Battery Decoder Summary — Streamlit app export\n")
        buf.write(f"Sessions: {', '.join(session_pick)}\n")
        buf.write(f"Total decoded values: {int(agg['count'].sum())}\n")
        buf.write(f"Unique PIDs decoded: {len(agg)}\n\n")
        buf.write(f"{'PID':<8} {'Name':<55} {'Unit':<8} "
                  f"{'count':>6} {'min':>10} {'max':>10} {'last':>10}\n")
        buf.write("-" * 110 + "\n")
        for _, r in agg.iterrows():
            mn = f"{r['min']:>10.3f}" if pd.notna(r['min']) else f"{'':>10}"
            mx = f"{r['max']:>10.3f}" if pd.notna(r['max']) else f"{'':>10}"
            lv = f"{r['last']:>10.3f}" if pd.notna(r['last']) else f"{'':>10}"
            buf.write(f"{r['pid_hex']:<8} {r['pid_name'][:54]:<55} "
                      f"{(r['unit'] or '')[:7]:<8} "
                      f"{int(r['count']):>6} {mn} {mx} {lv}\n")
        st.download_button("Download summary.txt",
                           data=buf.getvalue().encode("utf-8"),
                           file_name="summary.txt", mime="text/plain")
