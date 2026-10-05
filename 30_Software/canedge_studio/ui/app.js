// CANedge Studio UI. Talks to Python through window.pywebview.api (see app.py).
"use strict";

const $ = (s) => document.querySelector(s);
const COLORS = ["#3DBFA7", "#F2C14E", "#6EA0FF", "#FF6B66", "#C792EA", "#8BC34A"];
let api, state = { cards: [], configs: [] }, selectedCfg = null, result = null, plotted = [], uplot = null, cardKey = "";

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") el.style.cssText = v;
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
  return el;
}
const fmt = (v, d = 3) => (v == null ? "–" : typeof v === "number" ? (Math.abs(v) >= 1000 ? v.toFixed(0) : +v.toFixed(d) + "") : String(v));
const dur = (s) => (s < 60 ? `${s.toFixed(0)} s` : s < 3600 ? `${(s / 60).toFixed(1)} min` : `${(s / 3600).toFixed(1)} h`);
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 2600); }
const card = () => state.cards[0] || null;

// ------------------------------------------------------------------ tabs
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("on", p.id === b.dataset.tab));
  if (b.dataset.tab === "logs") renderSessions();
  if (uplot) setTimeout(resizePlot, 0);
}));

// ------------------------------------------------------------------ SD card
function renderCard() {
  const c = card(), box = $("#sdcard"), mini = $("#cardMini");
  mini.className = "card-mini" + (c ? " in" : "");
  mini.textContent = c ? `SD card ${c.device_id}` : "No SD card";
  mini.title = c ? c.root : "";
  if (!c) {
    box.className = "sdcard none";
    box.replaceChildren(h("div", { class: "sd-ico" }), h("div", { class: "sd-main" },
      h("h2", {}, "Insert the CANedge SD card"),
      h("div", { class: "sub" }, "It is detected automatically: any drive with the logger's device.json. Configs below can still be browsed without it.")),
      h("div", { class: "sd-actions" }, h("button", { onclick: addCardFolder }, "Use a folder as card…")));
    return;
  }
  const used = c.space ? 1 - c.space.free_gb / c.space.total_gb : 0;
  const onCard = c.config_match ? h("b", {}, c.config_match) : h("b", { class: "mono" }, `unknown config (CRC ${c.config_crc})`);
  const bootBadge = c.pending ? h("span", { class: "badge warn", title: "The file on the card changed after the logger last started" }, "⏳ applies after power-cycle")
    : c.booted_crc ? h("span", { class: "badge ok", title: `device.json cfg_crc32 = ${c.booted_crc}` }, "✓ running") : null;
  box.className = "sdcard in";
  box.replaceChildren(h("div", { class: "sd-ico" }),
    h("div", { class: "sd-main" },
      h("h2", {}, `CANedge2 · ${c.device_id}`, h("span", { class: "badge ok" }, "SD card detected")),
      h("div", { class: "sd-facts" },
        h("div", { class: "fact" }, h("span", {}, "Config on card"), h("div", {}, onCard, " ", bootBadge,
          !c.config_match && c.config_crc ? h("button", { class: "link", style: "margin-left:8px;color:var(--accent)", onclick: importCardConfig }, "Save it to the project →") : null)),
        c.pending ? h("div", { class: "fact" }, h("span", {}, "Logger last ran"), h("b", {}, c.booted_match || `CRC ${c.booted_crc}`)) : null,
        h("div", { class: "fact" }, h("span", {}, "Firmware"), h("b", { class: "mono" }, c.firmware || "–")),
        h("div", { class: "fact" }, h("span", {}, "Log sessions"), h("b", {}, `${c.sessions}`, h("span", { class: "sub" }, ` · ${c.mf4_files} files`))),
        c.space ? h("div", { class: "fact" }, h("span", {}, "Space"), h("b", {}, `${c.space.free_gb} GB free`), h("div", { class: "space" }, h("i", { style: `width:${(used * 100).toFixed(0)}%` }))) : null)),
    h("div", { class: "sd-actions" },
      h("button", { onclick: () => api.open_path(c.root) }, "Open card"),
      h("button", { onclick: () => { document.querySelector('[data-tab="logs"]').click(); } }, "Analyse its logs →")));
}

async function importCardConfig() {
  const r = await api.import_card_config(card().root);
  if (r.ok) { toast(`Saved as ${r.file}`); selectedCfg = r.path; await refresh(); selectConfig(r.path); } else toast(r.error);
}

async function addCardFolder() {
  const r = await api.add_card_folder();
  if (r) { toast(`Using ${r} as a card`); refresh(); } else toast("That folder has no device.json.");
}

// ------------------------------------------------------------------ configs
function renderConfigs() {
  const showArchived = $("#showArchive").checked;
  const c = card();
  const list = state.configs.filter((x) => showArchived || !x.archived);
  $("#configList").replaceChildren(...list.map((x) => {
    const onCard = c && c.config_crc === x.crc32;
    return h("button", { class: `cfg${selectedCfg === x.path ? " on" : ""}${x.archived ? " archived" : ""}`, onclick: () => selectConfig(x.path) },
      h("div", { class: "t" }, x.title || x.file.replace(/^config-01\.08-|\.json$/g, ""),
        onCard ? h("span", { class: "badge ok" }, "on card") : null, x.archived ? h("span", { class: "badge" }, "archived") : null,
        x.warnings ? h("span", { class: "badge warn", title: "has warnings" }, `⚠ ${x.warnings}`) : null),
      h("div", { class: "f" }, `profiles/${x.file}/`),
      h("div", { class: "chips" }, h("span", { class: "chip" }, `${x.identifiers} signals`), h("span", { class: "chip" }, `${x.frames} frames`),
        ...Object.entries(x.ecus).map(([e, n]) => h("span", { class: "chip" }, `${e} ${n}`))));
  }));
  if (!list.length) $("#configList").replaceChildren(h("div", { class: "empty" }, state.config_dir_ok ? "No configs found." : "Set the project folder (bottom left)."));
}

async function selectConfig(path) {
  selectedCfg = path;
  renderConfigs();
  const c = card();
  const d = await api.config_detail(path, c ? c.root : null);
  renderDetail(d);
}

function statusOf(row) {
  if (!row.did) return h("span", { class: "st mut" }, "keep-alive / session");
  if (!row.signal) return h("span", { class: "st bad" }, "unknown DID");
  return h("span", { class: `st ${row.signal.status.toLowerCase().startsWith("ready") ? "ok" : "warn"}` }, row.signal.status || "–");
}

function renderDetail(d) {
  const c = card();
  const groups = {};
  for (const r of d.rows) (groups[r.did ? (r.signal ? r.signal.group : "Not in the PID list") : "Session control"] ??= []).push(r);
  const order = Object.keys(groups).sort((a, b) => (a === "Session control") - (b === "Session control") || groups[b].length - groups[a].length);
  const can = c && !(d.vs_card && d.vs_card.same);
  $("#configDetail").replaceChildren(
    h("div", { class: "detail-head" },
      h("div", { class: "grow" }, h("h2", {}, d.title || d.file), h("div", { class: "sub mono" }, `profiles/${d.file}/config-01.08.json · CRC32 ${d.crc32}`),
        d.about ? h("p", { class: "about" }, d.about) : null),
      h("button", { class: "primary", disabled: !can, onclick: () => confirmDeploy(d),
        title: !c ? "Insert the SD card first" : d.vs_card && d.vs_card.same ? "This config is already on the card" : "" },
        d.vs_card && d.vs_card.same ? "✓ On the SD card" : "Write to SD card")),
    h("div", { class: "stats" },
      stat(d.identifiers, "signals requested"), stat(Object.keys(d.ecus).length, "ECUs addressed"),
      stat(d.period_ms ? `${d.period_ms / 1000} s` : "–", "repeat period"), stat(`${(d.cycle_ms / 1000).toFixed(2)} s`, "to send one round"),
      stat(d.bitrate ? `${d.bitrate / 1000} k` : "–", "CAN 1 bit rate"), stat(d.phy_mode.split(" ")[0], "CAN 1 mode")),
    d.vs_card && !d.vs_card.same ? h("div", { class: "warnings" }, h("div", { class: "ok-line" },
      `Compared with the config on the card: ${d.vs_card.added} signal(s) added, ${d.vs_card.removed} removed.`)) : null,
    d.warnings.length ? h("div", { class: "warnings" }, ...d.warnings.map((w) => h("div", { class: "warn-line" }, "⚠ " + w))) : null,
    h("div", { class: "groups" }, ...order.map((g) => h("div", { class: "group" },
      h("h3", {}, g, h("span", { class: "badge blue" }, String(groups[g].filter((r) => r.did).length || groups[g].length))),
      h("table", { class: "table" },
        h("thead", {}, h("tr", {}, ...["#", "Delay", "ECU", "Request", "DID", "Signal", "Unit", "Formula (PID list)", "List status"].map((x) => h("th", {}, x)))),
        h("tbody", {}, ...groups[g].map((r) => h("tr", {},
          h("td", { class: "num" }, String(r.index)), h("td", { class: "num" }, r.delay_ms != null ? `${r.delay_ms} ms` : ""),
          h("td", {}, r.ecu), h("td", { class: "mono" }, r.did ? "0x22 RDBI" : r.service),
          h("td", { class: "mono" }, r.did || ""), h("td", {}, r.signal ? r.signal.name : r.did ? "—" : r.name),
          h("td", {}, r.signal ? r.signal.unit : ""), h("td", { class: "formula" }, r.signal ? r.signal.formula : ""),
          h("td", {}, statusOf(r))))))))),
    h("h3", { style: "margin:22px 0 8px" }, "Coverage of the PID list"),
    ...Object.entries(d.coverage).sort((a, b) => b[1].total - a[1].total).map(([g, v]) => h("div", { class: "cov" },
      h("span", {}, g), h("div", { class: "bar" }, h("i", { style: `width:${(100 * v.targeted / v.total).toFixed(0)}%` })),
      h("span", { class: "sub" }, `${v.targeted} / ${v.total}`))));
}
const stat = (v, label) => h("div", { class: "stat" }, h("b", {}, String(v)), h("span", {}, label));

function confirmDeploy(d) {
  const c = card();
  $("#confirmTitle").textContent = `Write ${d.title || d.file} to the SD card?`;
  $("#confirmBody").replaceChildren(
    h("p", {}, "The profile's files (", h("code", {}, "config-01.08.json"), " + schema) replace the card's. What the card holds now ",
      `(${c.config_match || "CRC " + c.config_crc}) is saved to `, h("code", {}, "20_Hardware/canedge/_card_backups"), " first."),
    h("p", {}, `It becomes active the next time the logger powers up. ${d.identifiers} signals from ${Object.keys(d.ecus).length} ECU(s) will be requested every ${d.period_ms / 1000} s.`),
    d.warnings.length ? h("div", { class: "warn-line" }, `⚠ This config has ${d.warnings.length} warning(s); see the list above.`) : null);
  const dlg = $("#confirm");
  dlg.onclose = async () => {
    if (dlg.returnValue !== "ok") return;
    const r = await api.deploy(c.root, d.path);
    if (r.ok) { toast(`Written and verified (CRC ${r.crc32}). Power-cycle the logger to apply it.`); await refresh(); selectConfig(d.path); }
    else toast("Failed: " + r.error);
  };
  dlg.showModal();
}

// ------------------------------------------------------------------ logs
async function renderSessions() {
  const c = card(), box = $("#cardSessions");
  if (!c) { box.replaceChildren(h("span", { class: "sub" }, "Insert the SD card to pick a session from it.")); return; }
  const s = await api.card_sessions(c.root);
  box.replaceChildren(h("span", { class: "lbl" }, `On card ${c.device_id}:`),
    ...s.slice(0, 14).map((x) => h("button", { class: "sess", title: `${x.files} file(s), ${x.mb} MB, ${new Date(x.modified * 1000).toLocaleString()}`,
      onclick: async () => decode(await api.session_files(x.path), `Session ${x.session}`) }, x.session)),
    ...(s.length > 14 ? [h("span", { class: "sub" }, `+${s.length - 14} more`)] : []));
}

async function decode(paths, title) {
  if (!paths || !paths.length) return;
  $("#logEmpty").hidden = true; $("#logResult").hidden = true; $("#logBusy").hidden = false;
  $("#busyText").textContent = `${paths.length} file(s)`;
  const r = await api.decode(paths);
  $("#logBusy").hidden = true;
  if (r.error) { $("#logEmpty").hidden = false; toast(r.error); return; }
  result = r; plotted = [];
  renderResult(title || (r.files.length === 1 ? r.files[0] : `${r.files.length} files`));
}

function stCls(s) { return s === "ok" ? "ok" : s.startsWith("truncated") || s.startsWith("not available") ? "warn" : s === "no formula" ? "mut" : "bad"; }

function renderResult(title) {
  const r = result;
  $("#logResult").hidden = false;
  $("#logTitle").textContent = title;
  $("#logSub").textContent = `${r.source} · started ${new Date(r.start * 1000).toLocaleString()} · ${dur(r.duration_s)}`;
  $("#logStats").replaceChildren(stat(r.answered_ids, "signals answered"), stat(r.requested_ids, "signals requested"),
    stat(r.requests, "UDS read requests"), stat(r.positive, "positive answers"), stat(r.truncated, "truncated (multi-frame)"),
    stat(r.negative, "negative answers"), stat(r.frames.toLocaleString(), "vehicle CAN frames"));
  const n = $("#logNotice");
  n.hidden = !(r.frames === 0 || !r.requests);
  n.textContent = r.frames === 0
    ? `This log has no vehicle CAN traffic at all${r.internal_frames ? ` — only ${r.internal_frames.toLocaleString()} frames from the logger's own internal bus (GNSS/IMU, IDs 0x65–0x6F)` : ""}. The logger was probably not connected, or the car was off.`
    : "The logger sent no ReadDataByIdentifier requests in this log, so there are no battery signals to decode. See the services table below for what was exchanged.";
  renderSignals();
  renderCells();
  $("#svcTable").replaceChildren(h("thead", {}, h("tr", {}, ...["ECU", "Service", "Requests", "Positive", "Negative"].map((x) => h("th", {}, x)))),
    h("tbody", {}, ...r.services.map((s) => h("tr", {}, h("td", {}, s.ecu), h("td", {}, s.service), h("td", { class: "num" }, String(s.requests)),
      h("td", { class: "num" }, String(s.positive)), h("td", { class: "num" }, String(s.negative))))));
  // plot the first two numeric signals so there's something to look at straight away
  const numeric = r.signals.filter((s) => s.samples > 1 && typeof s.last === "number");
  const moving = numeric.filter((s) => s.max > s.min);               // signals that change are the interesting ones
  plotted = [...moving, ...numeric.filter((s) => !moving.includes(s))].slice(0, 2).map((s) => s.key);
  renderSignals(); drawPlot();
}

function renderSignals() {
  if (!result) return;
  const q = $("#sigFilter").value.toLowerCase();
  const rows = result.signals.filter((s) => !q || `${s.name} ${s.did} ${s.ecu} ${s.group}`.toLowerCase().includes(q));
  $("#sigTable").replaceChildren(
    h("thead", {}, h("tr", {}, ...["", "ECU", "DID", "Signal", "Last", "Min", "Max", "n", "Status"].map((x) => h("th", {}, x)))),
    h("tbody", {}, ...rows.map((s) => {
      const i = plotted.indexOf(s.key);
      const plottable = s.samples > 0 && typeof s.last === "number";
      return h("tr", { class: `${plottable ? "click" : ""}${i >= 0 ? " sel" : ""}`, title: s.formula ? `Formula: ${s.formula}\nLast raw bytes: ${s.raw_last || "–"}` : "",
        onclick: () => plottable && togglePlot(s.key) },
        h("td", {}, i >= 0 ? h("span", { class: "swatch", style: `background:${COLORS[i % COLORS.length]}` }) : ""),
        h("td", {}, s.ecu), h("td", { class: "mono" }, s.did), h("td", {}, s.name),
        h("td", { class: "num" }, `${fmt(s.last)} ${s.last != null ? s.unit : ""}`), h("td", { class: "num" }, fmt(s.min)), h("td", { class: "num" }, fmt(s.max)),
        h("td", { class: "num" }, String(s.samples)), h("td", {}, h("span", { class: `st ${stCls(s.status)}` }, s.status)));
    })));
}

function togglePlot(key) {
  const i = plotted.indexOf(key);
  if (i >= 0) plotted.splice(i, 1); else plotted.push(key);
  if (plotted.length > COLORS.length) plotted.shift();
  renderSignals(); drawPlot();
}

function drawPlot() {
  const box = $("#plot");
  if (uplot) { uplot.destroy(); uplot = null; }
  const sigs = plotted.map((k) => result.signals.find((s) => s.key === k)).filter(Boolean);
  $("#plotTitle").textContent = sigs.length ? "Plot" : "Plot";
  if (!sigs.length) { box.replaceChildren(h("div", { class: "empty" }, "Select a signal on the left.")); return; }
  box.replaceChildren();
  // one shared time axis: union of all sample times, gaps where a signal has no sample
  const times = [...new Set(sigs.flatMap((s) => s.t))].sort((a, b) => a - b);
  const idx = new Map(times.map((t, i) => [t, i]));
  const series = sigs.map((s) => { const y = new Array(times.length).fill(null); s.t.forEach((t, j) => (y[idx.get(t)] = s.v[j])); return y; });
  const units = [...new Set(sigs.map((s) => s.unit))];
  const opts = {
    width: box.clientWidth, height: 320, cursor: { drag: { x: true, y: false } },
    scales: { x: { time: false }, ...Object.fromEntries(units.map((u) => [u || "_", { range: around }])) },
    axes: [{ stroke: "#8B96A5", grid: { stroke: "#26303B" }, label: "time [s]" },
      ...units.slice(0, 2).map((u, i) => ({ scale: u || "_", side: i ? 1 : 3, stroke: "#8B96A5", grid: { show: i === 0, stroke: "#26303B" }, label: u || "" }))],
    series: [{ label: "t" }, ...sigs.map((s, i) => ({ label: `${s.name} [${s.unit}]`, scale: s.unit || "_", stroke: COLORS[plotted.indexOf(s.key) % COLORS.length], width: 1.8, spanGaps: true, points: { show: s.samples < 60 } }))],
    legend: { live: true },
  };
  uplot = new uPlot(opts, [times, ...series], box);
}
// zoom each axis onto its own data; a flat signal gets a small band instead of 0..2x
function around(u, min, max) {
  if (min == null) return [0, 1];
  const pad = max > min ? (max - min) * 0.15 : Math.max(Math.abs(max) * 0.02, 0.5);
  return [min - pad, max + pad];
}
function resizePlot() { if (uplot) uplot.setSize({ width: $("#plot").clientWidth, height: 320 }); }
window.addEventListener("resize", resizePlot);

function renderCells() {
  const cells = result.cells, panel = $("#cellsPanel"), box = $("#cells");
  if (!cells.length) { $("#cellsSub").textContent = "this log has no per-cell voltage reads"; box.style.height = "auto"; box.replaceChildren(h("div", { class: "empty", style: "width:100%" }, "Use a cells-front / cells-rear config to read them.")); return; }
  box.style.height = "";
  const v = cells.filter((c) => c.volt != null).map((c) => c.volt);
  const lo = Math.min(...v), hi = Math.max(...v), pad = Math.max((hi - lo) * 0.25, 0.002);
  $("#cellsSub").textContent = v.length ? `${v.length} cells · ${lo.toFixed(3)}–${hi.toFixed(3)} V · spread ${((hi - lo) * 1000).toFixed(1)} mV` : "";
  box.replaceChildren(...cells.map((c) => h("div", {
    class: `cellbar${c.volt == null ? " na" : ""}`,
    style: c.volt == null ? "" : `height:${(8 + 92 * (c.volt - lo + pad) / (hi - lo + 2 * pad)).toFixed(1)}%`,
    title: `Cell ${c.cell} (${c.did}): ${c.volt == null ? c.status : c.volt.toFixed(4) + " V"}` })));
}

// ------------------------------------------------------------------ wiring
$("#showArchive").addEventListener("change", renderConfigs);
$("#sigFilter").addEventListener("input", renderSignals);
$("#openLogs").onclick = async () => decode(await api.pick_logs());
$("#openFolder").onclick = async () => decode(await api.pick_session_folder());
$("#exportCsv").onclick = async () => { const p = await api.export_csv(); if (p) toast(`Saved ${p}`); };
$("#projectBtn").onclick = async () => { if (await api.choose_project()) { toast("Project folder set"); refresh(); } };

async function refresh() {
  state = await api.state();
  renderCard(); renderConfigs();
  if (!selectedCfg && state.configs.length) {
    const c = card();
    const onCard = c && state.configs.find((x) => x.crc32 === c.config_crc);
    selectConfig((onCard || state.configs.find((x) => !x.archived) || state.configs[0]).path);
  }
}

async function watchCard() {           // the card can come and go at any time
  try {
    const cards = await api.cards();
    const key = JSON.stringify(cards.map((c) => [c.root, c.config_crc, c.booted_crc, c.sessions]));
    if (key !== cardKey) {
      const was = cardKey; cardKey = key; state.cards = cards; renderCard(); renderConfigs();
      if (was) { toast(cards.length ? `SD card ${cards[0].device_id} detected` : "SD card removed"); if (selectedCfg) selectConfig(selectedCfg); renderSessions(); }
    }
  } catch (e) { /* api busy decoding */ }
}

window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  await refresh();
  cardKey = JSON.stringify(state.cards.map((c) => [c.root, c.config_crc, c.booted_crc, c.sessions]));
  setInterval(watchCard, 2000);
});
