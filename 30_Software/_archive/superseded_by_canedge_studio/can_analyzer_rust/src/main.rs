//! CAN Analyzer v2.0 — Native SavvyCAN-like tool for MF4/CSV CAN data
//!
//! Features:
//!   - Data Flow: Real-time hex matrix with red/green byte-change highlighting
//!   - Sniffer: Virtual-scrolling frame table with filtering
//!   - Signal Plotter: Interactive byte-value plots
//!   - Stats: Per-CAN-ID statistics and timing analysis
//!
//! Run:  cargo run --release -- [path/to/can_data.csv]

use eframe::egui;
use egui::{Color32, RichText, Stroke};
use egui_extras::{Column, TableBuilder};
use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Command;
use std::sync::{Arc, Mutex};

// ══════════════════════════════════════════════════════════════════
// CONSTANTS
// ══════════════════════════════════════════════════════════════════

const CAN_COLORS: &[(u32, [u8; 3])] = &[
    (0x065, [230, 25, 75]),
    (0x066, [60, 180, 75]),
    (0x067, [67, 99, 216]),
    (0x068, [245, 130, 49]),
    (0x06A, [145, 30, 180]),
    (0x06B, [66, 212, 244]),
    (0x06F, [240, 50, 230]),
];

const PALETTE: &[[u8; 3]] = &[
    [230, 25, 75],
    [60, 180, 75],
    [67, 99, 216],
    [245, 130, 49],
    [145, 30, 180],
    [66, 212, 244],
    [240, 50, 230],
    [191, 239, 69],
    [70, 153, 144],
    [220, 190, 255],
];

fn id_color(can_id: u32) -> Color32 {
    for &(id, rgb) in CAN_COLORS {
        if id == can_id {
            return Color32::from_rgb(rgb[0], rgb[1], rgb[2]);
        }
    }
    let idx = can_id as usize % PALETTE.len();
    Color32::from_rgb(PALETTE[idx][0], PALETTE[idx][1], PALETTE[idx][2])
}

fn id_color_dim(can_id: u32, alpha: u8) -> Color32 {
    let c = id_color(can_id);
    Color32::from_rgba_unmultiplied(c.r(), c.g(), c.b(), alpha)
}

// ══════════════════════════════════════════════════════════════════
// DATA STRUCTURES
// ══════════════════════════════════════════════════════════════════

#[derive(Clone)]
struct CanFrame {
    timestamp: f64,
    can_id: u32,
    dlc: u8,
    data: [u8; 8],
    source: String,
    hex_str: String,
}

#[derive(Clone)]
struct ChangeEvent {
    timestamp: f64,
    can_id: u32,
    byte_idx: usize,
    old_val: u8,
    new_val: u8,
}

impl ChangeEvent {
    fn diff_str(&self) -> String {
        let diff = self.new_val as i16 - self.old_val as i16;
        if diff == 1 {
            "++".into()
        } else if diff == -1 {
            "--".into()
        } else if diff > 0 {
            format!("+{}", diff)
        } else {
            format!("{}", diff)
        }
    }
}

struct IdState {
    can_id: u32,
    dlc: u8,
    data: [u8; 8],
    last_change_time: [f64; 8],
    total_changes: [u32; 8],
    frame_count: u32,
}

impl IdState {
    fn new(can_id: u32, dlc: u8, initial_data: [u8; 8]) -> Self {
        Self {
            can_id,
            dlc,
            data: initial_data,
            last_change_time: [f64::NEG_INFINITY; 8],
            total_changes: [0; 8],
            frame_count: 1,
        }
    }
}

// ══════════════════════════════════════════════════════════════════
// DATA STORE — loads CSV, indexes frames
// ══════════════════════════════════════════════════════════════════

struct DataStore {
    frames: Vec<CanFrame>,
    can_ids: Vec<u32>,
    sources: Vec<String>,
    time_range: (f64, f64),
    id_dlc: HashMap<u32, u8>,
}

impl DataStore {
    fn load_csv(path: &str) -> Result<Self, String> {
        let mut rdr = csv::ReaderBuilder::new()
            .has_headers(true)
            .flexible(true)
            .from_path(path)
            .map_err(|e| format!("Cannot open CSV: {}", e))?;

        let headers = rdr.headers().map_err(|e| e.to_string())?.clone();

        // Find columns by name
        let ts_col = headers
            .iter()
            .position(|h| h == "timestamp" || h.is_empty())
            .unwrap_or(0);
        let id_col = headers.iter().position(|h| h == "can_id").unwrap_or(2);
        let dlc_col = headers.iter().position(|h| h == "dlc").unwrap_or(4);
        let hex_col = headers.iter().position(|h| h == "data_hex").unwrap_or(8);
        let src_col = headers.iter().position(|h| h == "source").unwrap_or(10);

        let mut frames = Vec::with_capacity(10_000);

        for result in rdr.records() {
            let rec = result.map_err(|e| format!("CSV parse: {}", e))?;
            let timestamp: f64 = rec.get(ts_col).unwrap_or("0").parse().unwrap_or(0.0);
            let can_id = rec.get(id_col).unwrap_or("0").parse::<f64>().unwrap_or(0.0) as u32;
            let dlc = rec.get(dlc_col).unwrap_or("0").parse::<f64>().unwrap_or(0.0) as u8;
            let hex_raw = rec.get(hex_col).unwrap_or("").to_string();
            let source = rec.get(src_col).unwrap_or("").to_string();

            let mut data = [0u8; 8];
            for (i, tok) in hex_raw.split_whitespace().enumerate() {
                if i >= 8 {
                    break;
                }
                data[i] = u8::from_str_radix(tok, 16).unwrap_or(0);
            }

            let hex_str = (0..dlc as usize)
                .map(|i| format!("{:02X}", data[i]))
                .collect::<Vec<_>>()
                .join(" ");

            frames.push(CanFrame {
                timestamp,
                can_id,
                dlc,
                data,
                source,
                hex_str,
            });
        }

        frames.sort_by(|a, b| a.timestamp.partial_cmp(&b.timestamp).unwrap());

        let mut id_set = std::collections::BTreeSet::new();
        let mut src_set = std::collections::BTreeSet::new();
        let mut id_dlc = HashMap::new();
        for f in &frames {
            id_set.insert(f.can_id);
            src_set.insert(f.source.clone());
            id_dlc.entry(f.can_id).or_insert(f.dlc);
            let d = id_dlc.get_mut(&f.can_id).unwrap();
            if f.dlc > *d {
                *d = f.dlc;
            }
        }

        let t_min = frames.first().map(|f| f.timestamp).unwrap_or(0.0);
        let t_max = frames.last().map(|f| f.timestamp).unwrap_or(0.0);

        Ok(Self {
            frames,
            can_ids: id_set.into_iter().collect(),
            sources: src_set.into_iter().collect(),
            time_range: (t_min, t_max),
            id_dlc,
        })
    }

    fn precompute_changes(&self) -> Vec<ChangeEvent> {
        let mut states: HashMap<u32, [u8; 8]> = HashMap::new();
        let mut first_seen: HashMap<u32, bool> = HashMap::new();
        let mut changes = Vec::new();

        for f in &self.frames {
            let is_first = !first_seen.contains_key(&f.can_id);
            first_seen.insert(f.can_id, true);
            let prev = states.entry(f.can_id).or_insert(f.data);

            if !is_first {
                for i in 0..f.dlc as usize {
                    if f.data[i] != prev[i] {
                        changes.push(ChangeEvent {
                            timestamp: f.timestamp,
                            can_id: f.can_id,
                            byte_idx: i,
                            old_val: prev[i],
                            new_val: f.data[i],
                        });
                    }
                }
            }
            *prev = f.data;
        }
        changes
    }
}

// ══════════════════════════════════════════════════════════════════
// MF4 CONVERTER — calls Python/asammdf to convert MF4 → CSV
// ══════════════════════════════════════════════════════════════════

/// Result of a background MF4 conversion
#[derive(Clone)]
enum MF4Status {
    Idle,
    Converting(String),  // status message
    Done(PathBuf),       // path to generated CSV
    Error(String),
}

fn find_python() -> Option<String> {
    for cmd in ["python", "python3", "py"] {
        if let Ok(out) = Command::new(cmd).arg("--version").output() {
            if out.status.success() {
                return Some(cmd.to_string());
            }
        }
    }
    None
}

/// Canonicalize a path and strip the \\?\ prefix that Windows adds
fn clean_canonicalize(p: &std::path::Path) -> Option<PathBuf> {
    std::fs::canonicalize(p).ok().map(|c| {
        let s = c.to_string_lossy();
        if s.starts_with(r"\\?\") {
            PathBuf::from(&s[4..])
        } else {
            c
        }
    })
}

fn find_src_dir() -> Option<PathBuf> {
    // Try relative to CWD
    for rel in ["../src", "src", "../../src"] {
        let p = PathBuf::from(rel);
        if p.join("mf4_reader.py").exists() {
            return clean_canonicalize(&p).or(Some(p));
        }
    }
    // Try relative to the executable location
    if let Ok(exe) = std::env::current_exe() {
        let exe = clean_canonicalize(&exe).unwrap_or(exe);
        if let Some(parent) = exe.parent() {
            // exe is in can_analyzer/target/release/ or can_analyzer/target/debug/
            for up in ["../../src", "../../../src", "../../../../src"] {
                let p = parent.join(up);
                if p.join("mf4_reader.py").exists() {
                    return clean_canonicalize(&p).or(Some(p));
                }
            }
        }
    }
    None
}

fn convert_mf4_file(mf4_path: &str) -> Result<PathBuf, String> {
    let python = find_python().ok_or("Python not found. Install Python 3 with asammdf.")?;
    let src_dir = find_src_dir().ok_or(
        "Cannot find src/mf4_reader.py. Run from the project directory."
    )?;

    let out_csv = std::env::temp_dir().join("can_analyzer_mf4.csv");
    // Use forward slashes for Python paths — works on Windows and avoids escaping issues
    let src_str = src_dir.to_string_lossy().replace('\\', "/");
    let mf4_str = mf4_path.replace('\\', "/");
    let csv_str = out_csv.to_string_lossy().replace('\\', "/");
    let source_name = PathBuf::from(mf4_path)
        .parent()
        .and_then(|p| p.file_name())
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "unknown".into());

    let script = format!(
        r#"
import sys
sys.path.insert(0, '{src_str}')
import mf4_reader
df = mf4_reader.load_file('{mf4_str}')
df['source'] = '{source_name}'
df.to_csv('{csv_str}')
print('OK ' + str(len(df)) + ' frames')
"#
    );

    let output = Command::new(&python)
        .args(["-X", "utf8", "-c", &script])
        .output()
        .map_err(|e| format!("Failed to run Python: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Python error:\n{}", stderr));
    }

    Ok(out_csv)
}

fn convert_mf4_dir(dir_path: &str) -> Result<PathBuf, String> {
    let python = find_python().ok_or("Python not found. Install Python 3 with asammdf.")?;
    let src_dir = find_src_dir().ok_or(
        "Cannot find src/mf4_reader.py. Run from the project directory."
    )?;

    let out_csv = std::env::temp_dir().join("can_analyzer_mf4.csv");
    // Use forward slashes for Python paths — works on Windows and avoids escaping issues
    let src_str = src_dir.to_string_lossy().replace('\\', "/");
    let dir_str = dir_path.replace('\\', "/");
    let csv_str = out_csv.to_string_lossy().replace('\\', "/");

    let script = format!(
        r#"
import sys
sys.path.insert(0, '{src_str}')
import mf4_reader
df = mf4_reader.load_all('{dir_str}')
df.to_csv('{csv_str}')
print('OK ' + str(len(df)) + ' frames')
"#
    );

    let output = Command::new(&python)
        .args(["-X", "utf8", "-c", &script])
        .output()
        .map_err(|e| format!("Failed to run Python: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Python error:\n{}", stderr));
    }

    Ok(out_csv)
}

// ══════════════════════════════════════════════════════════════════
// PLAYBACK ENGINE — processes frames up to current time
// ══════════════════════════════════════════════════════════════════

struct Playback {
    current_time: f64,
    frame_cursor: usize, // next frame to process
    id_states: HashMap<u32, IdState>,
    recent_changes: Vec<ChangeEvent>, // changes visible in current playback
}

impl Playback {
    fn new() -> Self {
        Self {
            current_time: 0.0,
            frame_cursor: 0,
            id_states: HashMap::new(),
            recent_changes: Vec::new(),
        }
    }

    fn reset(&mut self) {
        self.current_time = 0.0;
        self.frame_cursor = 0;
        self.id_states.clear();
        self.recent_changes.clear();
    }

    fn seek(&mut self, data: &DataStore, target_time: f64) {
        if target_time < self.current_time {
            self.reset();
        }
        self.advance_to(data, target_time);
    }

    fn advance_to(&mut self, data: &DataStore, target_time: f64) {
        while self.frame_cursor < data.frames.len() {
            let f = &data.frames[self.frame_cursor];
            if f.timestamp > target_time {
                break;
            }

            let state = self
                .id_states
                .entry(f.can_id)
                .or_insert_with(|| IdState::new(f.can_id, f.dlc, f.data));

            if state.frame_count > 0 {
                // Not first frame — check for changes
                for i in 0..f.dlc as usize {
                    if f.data[i] != state.data[i] {
                        self.recent_changes.push(ChangeEvent {
                            timestamp: f.timestamp,
                            can_id: f.can_id,
                            byte_idx: i,
                            old_val: state.data[i],
                            new_val: f.data[i],
                        });
                        state.last_change_time[i] = f.timestamp;
                        state.total_changes[i] += 1;
                    }
                }
            }
            state.data = f.data;
            if f.dlc > state.dlc {
                state.dlc = f.dlc;
            }
            state.frame_count += 1;
            self.frame_cursor += 1;
        }
        self.current_time = target_time;
    }
}

// ══════════════════════════════════════════════════════════════════
// BYTE CHANGE COLOR — red→neutral→green fade
// ══════════════════════════════════════════════════════════════════

fn byte_bg(time_since_change: f64) -> Color32 {
    if time_since_change < 0.0 || time_since_change > 1e9 {
        return Color32::TRANSPARENT; // never changed
    }
    if time_since_change < 0.4 {
        // Bright red
        let a = (200.0 * (1.0 - time_since_change / 0.4)) as u8;
        Color32::from_rgba_unmultiplied(243, 139, 168, a.max(80))
    } else if time_since_change < 2.0 {
        // Fading
        let t = (time_since_change - 0.4) / 1.6;
        let a = (80.0 * (1.0 - t)) as u8;
        Color32::from_rgba_unmultiplied(243, 139, 168, a)
    } else if time_since_change > 5.0 {
        // Stable green tint
        Color32::from_rgba_unmultiplied(166, 227, 161, 25)
    } else {
        Color32::TRANSPARENT
    }
}

// ══════════════════════════════════════════════════════════════════
// APPLICATION
// ══════════════════════════════════════════════════════════════════

#[derive(PartialEq)]
enum Tab {
    DataFlow,
    Sniffer,
    Plotter,
    Stats,
}

struct PlotSignal {
    label: String,
    color: Color32,
    points: Vec<[f64; 2]>,
}

struct App {
    // Data
    data: Option<DataStore>,
    all_changes: Vec<ChangeEvent>,
    csv_path: String,
    load_error: String,

    // Tab
    tab: Tab,

    // Data Flow state
    playback: Playback,
    playing: bool,
    speed: f64,
    flow_id_filter: Option<u32>,

    // Sniffer state
    sniff_id_filter: Option<u32>,
    sniff_src_filter: Option<String>,
    sniff_search: String,
    sniff_indices: Vec<usize>,
    sniff_dirty: bool,

    // Plotter state
    plot_id: Option<u32>,
    plot_bytes: [bool; 8],
    plot_signals: Vec<PlotSignal>,
    plot_color_idx: usize,

    // MF4 conversion state
    mf4_status: Arc<Mutex<MF4Status>>,
}

impl App {
    fn new(cc: &eframe::CreationContext<'_>) -> Self {
        // Try to find CSV automatically
        let candidates = [
            "../output/can_data.csv".to_string(),
            "output/can_data.csv".to_string(),
        ];
        let mut csv_path = String::new();
        for c in &candidates {
            if std::path::Path::new(c).exists() {
                csv_path = c.clone();
                break;
            }
        }

        // If no CSV, try to auto-convert MF4 from default data dir
        let mut auto_mf4_dir: Option<String> = None;
        if csv_path.is_empty() {
            for d in ["../data/mf4", "data/mf4"] {
                if std::path::Path::new(d).is_dir() {
                    auto_mf4_dir = Some(d.to_string());
                    break;
                }
            }
        }

        let mut app = Self {
            data: None,
            all_changes: Vec::new(),
            csv_path,
            load_error: String::new(),
            tab: Tab::DataFlow,
            playback: Playback::new(),
            playing: false,
            speed: 1.0,
            flow_id_filter: None,
            sniff_id_filter: None,
            sniff_src_filter: None,
            sniff_search: String::new(),
            sniff_indices: Vec::new(),
            sniff_dirty: true,
            plot_id: None,
            plot_bytes: [false; 8],
            plot_signals: Vec::new(),
            plot_color_idx: 0,
            mf4_status: Arc::new(Mutex::new(MF4Status::Idle)),
        };

        if !app.csv_path.is_empty() {
            app.load_data();
        } else if let Some(mf4_dir) = auto_mf4_dir {
            app.load_mf4_dir(mf4_dir, cc.egui_ctx.clone());
        }
        app
    }

    fn load_mf4_file(&mut self, path: String, ctx: egui::Context) {
        let status = self.mf4_status.clone();
        *status.lock().unwrap() = MF4Status::Converting(format!("Converting {}...", path));

        std::thread::spawn(move || {
            match convert_mf4_file(&path) {
                Ok(csv_path) => {
                    *status.lock().unwrap() = MF4Status::Done(csv_path);
                }
                Err(e) => {
                    *status.lock().unwrap() = MF4Status::Error(e);
                }
            }
            ctx.request_repaint();
        });
    }

    fn load_mf4_dir(&mut self, path: String, ctx: egui::Context) {
        let status = self.mf4_status.clone();
        *status.lock().unwrap() = MF4Status::Converting(format!("Converting MF4 files in {}...", path));

        std::thread::spawn(move || {
            match convert_mf4_dir(&path) {
                Ok(csv_path) => {
                    *status.lock().unwrap() = MF4Status::Done(csv_path);
                }
                Err(e) => {
                    *status.lock().unwrap() = MF4Status::Error(e);
                }
            }
            ctx.request_repaint();
        });
    }

    fn check_mf4_status(&mut self) {
        let status = self.mf4_status.lock().unwrap().clone();
        match status {
            MF4Status::Done(csv_path) => {
                self.csv_path = csv_path.to_string_lossy().to_string();
                self.load_data();
                *self.mf4_status.lock().unwrap() = MF4Status::Idle;
            }
            MF4Status::Error(e) => {
                self.load_error = e;
                *self.mf4_status.lock().unwrap() = MF4Status::Idle;
            }
            _ => {}
        }
    }

    fn load_data(&mut self) {
        match DataStore::load_csv(&self.csv_path) {
            Ok(data) => {
                self.all_changes = data.precompute_changes();
                self.playback.reset();
                self.sniff_dirty = true;
                self.plot_signals.clear();
                self.plot_id = data.can_ids.first().copied();
                self.data = Some(data);
                self.load_error.clear();
            }
            Err(e) => {
                self.load_error = e;
                self.data = None;
            }
        }
    }

    fn rebuild_sniffer_filter(&mut self) {
        if let Some(data) = &self.data {
            let search_upper = self.sniff_search.to_uppercase();
            self.sniff_indices = data
                .frames
                .iter()
                .enumerate()
                .filter(|(_, f)| {
                    if let Some(id) = self.sniff_id_filter {
                        if f.can_id != id {
                            return false;
                        }
                    }
                    if let Some(ref src) = self.sniff_src_filter {
                        if &f.source != src {
                            return false;
                        }
                    }
                    if !search_upper.is_empty() && !f.hex_str.contains(&search_upper) {
                        return false;
                    }
                    true
                })
                .map(|(i, _)| i)
                .collect();
        }
        self.sniff_dirty = false;
    }

    // ── DATA FLOW TAB ───────────────────────────────────────────

    fn show_data_flow(&mut self, ui: &mut egui::Ui) {
        let data = match &self.data {
            Some(d) => d,
            None => {
                ui.heading("No data loaded");
                return;
            }
        };
        let (t_min, t_max) = data.time_range;
        let can_ids = data.can_ids.clone();

        // ── Time controls ──
        ui.horizontal(|ui| {
            if ui.button("|\u{25C0}").on_hover_text("Start").clicked() {
                self.playback.reset();
                self.playing = false;
            }
            if ui
                .button(if self.playing { "\u{23F8}" } else { "\u{25B6}" })
                .clicked()
            {
                self.playing = !self.playing;
            }
            if ui.button("\u{25B6}|").on_hover_text("End").clicked() {
                if let Some(d) = &self.data {
                    self.playback.seek(d, t_max);
                }
                self.playing = false;
            }

            let mut t = self.playback.current_time;
            let resp = ui.add(
                egui::Slider::new(&mut t, t_min..=t_max)
                    .text("s")
                    .trailing_fill(true)
                    .max_decimals(3),
            );
            if resp.changed() {
                if let Some(d) = &self.data {
                    self.playback.seek(d, t);
                }
            }

            ui.label(
                RichText::new(format!(
                    "{:.3} / {:.1} s",
                    self.playback.current_time, t_max
                ))
                .monospace()
                .color(Color32::from_rgb(137, 180, 250)),
            );
        });

        ui.horizontal(|ui| {
            ui.label("Speed:");
            for (label, spd) in [
                ("0.5x", 0.5),
                ("1x", 1.0),
                ("2x", 2.0),
                ("5x", 5.0),
                ("10x", 10.0),
                ("50x", 50.0),
            ] {
                if ui
                    .selectable_label((self.speed - spd).abs() < 0.01, label)
                    .clicked()
                {
                    self.speed = spd;
                }
            }

            ui.separator();
            ui.label("Step:");
            if ui.button("\u{25C0} 1 frame").clicked() {
                // Step backward: seek to previous frame
                if let Some(d) = &self.data {
                    if self.playback.frame_cursor > 1 {
                        let prev_t = d.frames[self.playback.frame_cursor.saturating_sub(2)].timestamp;
                        self.playback.seek(d, prev_t);
                    }
                }
            }
            if ui.button("1 frame \u{25B6}").clicked() {
                if let Some(d) = &self.data {
                    if self.playback.frame_cursor < d.frames.len() {
                        let next_t = d.frames[self.playback.frame_cursor].timestamp;
                        self.playback.advance_to(d, next_t + 0.0001);
                    }
                }
            }
        });

        ui.separator();

        // ── Hex Matrix ──
        ui.heading(
            RichText::new("Hex Matrix")
                .color(Color32::from_rgb(137, 180, 250))
                .size(14.0),
        );

        let current_time = self.playback.current_time;
        let avail_width = ui.available_width();
        let col_w = ((avail_width - 200.0) / 8.0).max(38.0);

        TableBuilder::new(ui)
            .striped(true)
            .cell_layout(egui::Layout::centered_and_justified(egui::Direction::LeftToRight))
            .column(Column::exact(70.0)) // CAN ID
            .column(Column::exact(50.0)) // Count
            .columns(Column::exact(col_w.min(52.0)), 8) // B0-B7
            .column(Column::exact(80.0)) // ASCII
            .header(22.0, |mut header| {
                header.col(|ui| { ui.strong("CAN ID"); });
                header.col(|ui| { ui.strong("Cnt"); });
                for i in 0..8 {
                    header.col(|ui| { ui.strong(format!("B{}", i)); });
                }
                header.col(|ui| { ui.strong("ASCII"); });
            })
            .body(|body| {
                body.rows(26.0, can_ids.len(), |mut row| {
                    let cid = can_ids[row.index()];
                    let state = self.playback.id_states.get(&cid);

                    row.col(|ui| {
                        ui.label(
                            RichText::new(format!("0x{:03X}", cid))
                                .monospace()
                                .color(id_color(cid))
                                .strong(),
                        );
                    });
                    row.col(|ui| {
                        let cnt = state.map(|s| s.frame_count).unwrap_or(0);
                        ui.label(RichText::new(cnt.to_string()).monospace());
                    });

                    let dlc = state.map(|s| s.dlc).unwrap_or(0) as usize;
                    let mut ascii = String::with_capacity(8);

                    for bi in 0..8 {
                        row.col(|ui| {
                            if let Some(st) = state {
                                if bi < dlc {
                                    let val = st.data[bi];
                                    let dt = current_time - st.last_change_time[bi];
                                    let bg = byte_bg(dt);

                                    egui::Frame::new()
                                        .fill(bg)
                                        .inner_margin(egui::Margin::symmetric(2, 2))
                                        .corner_radius(3.0)
                                        .show(ui, |ui| {
                                            ui.label(
                                                RichText::new(format!("{:02X}", val))
                                                    .monospace()
                                                    .strong(),
                                            );
                                        });

                                    let ch = val as char;
                                    ascii.push(if ch.is_ascii_graphic() { ch } else { '.' });
                                }
                            }
                        });
                    }

                    row.col(|ui| {
                        ui.label(
                            RichText::new(ascii)
                                .monospace()
                                .color(Color32::from_rgb(166, 227, 161)),
                        );
                    });
                });
            });

        ui.separator();

        // ── Change Log ──
        ui.horizontal(|ui| {
            ui.heading(
                RichText::new("Change Log")
                    .color(Color32::from_rgb(137, 180, 250))
                    .size(14.0),
            );
            ui.separator();
            ui.label("Filter:");
            egui::ComboBox::from_id_salt("flow_id_filter")
                .selected_text(match self.flow_id_filter {
                    Some(id) => format!("0x{:03X}", id),
                    None => "All".into(),
                })
                .show_ui(ui, |ui| {
                    if ui.selectable_label(self.flow_id_filter.is_none(), "All").clicked() {
                        self.flow_id_filter = None;
                    }
                    for &cid in &can_ids {
                        if ui
                            .selectable_label(
                                self.flow_id_filter == Some(cid),
                                RichText::new(format!("0x{:03X}", cid)).color(id_color(cid)),
                            )
                            .clicked()
                        {
                            self.flow_id_filter = Some(cid);
                        }
                    }
                });

            ui.label(format!(
                "{} changes up to {:.3}s",
                self.playback.recent_changes.len(),
                self.playback.current_time
            ));
        });

        // Show changes in reverse chronological order
        let filtered_changes: Vec<&ChangeEvent> = self
            .playback
            .recent_changes
            .iter()
            .rev()
            .filter(|c| self.flow_id_filter.map_or(true, |id| c.can_id == id))
            .take(500)
            .collect();

        let avail = ui.available_height().max(100.0);
        egui::ScrollArea::vertical()
            .max_height(avail)
            .auto_shrink(false)
            .show(ui, |ui| {
                TableBuilder::new(ui)
                    .striped(true)
                    .cell_layout(egui::Layout::left_to_right(egui::Align::Center))
                    .column(Column::exact(80.0))  // Time
                    .column(Column::exact(70.0))  // CAN ID
                    .column(Column::exact(40.0))  // Byte
                    .column(Column::exact(80.0))  // Old → New
                    .column(Column::exact(50.0))  // Diff
                    .column(Column::remainder())   // empty
                    .header(20.0, |mut header| {
                        header.col(|ui| { ui.strong("Time (s)"); });
                        header.col(|ui| { ui.strong("CAN ID"); });
                        header.col(|ui| { ui.strong("Byte"); });
                        header.col(|ui| { ui.strong("Change"); });
                        header.col(|ui| { ui.strong("Diff"); });
                        header.col(|_| {});
                    })
                    .body(|body| {
                        body.rows(20.0, filtered_changes.len(), |mut row| {
                            let ch = filtered_changes[row.index()];
                            row.col(|ui| {
                                ui.label(RichText::new(format!("{:.3}", ch.timestamp)).monospace());
                            });
                            row.col(|ui| {
                                ui.label(
                                    RichText::new(format!("0x{:03X}", ch.can_id))
                                        .monospace()
                                        .color(id_color(ch.can_id)),
                                );
                            });
                            row.col(|ui| {
                                ui.label(
                                    RichText::new(format!("B{}", ch.byte_idx))
                                        .monospace()
                                        .color(Color32::from_rgb(137, 180, 250)),
                                );
                            });
                            row.col(|ui| {
                                ui.label(
                                    RichText::new(format!(
                                        "{:02X} \u{2192} {:02X}",
                                        ch.old_val, ch.new_val
                                    ))
                                    .monospace(),
                                );
                            });
                            row.col(|ui| {
                                let diff = ch.diff_str();
                                let color = if diff.starts_with('+') {
                                    Color32::from_rgb(166, 227, 161)
                                } else {
                                    Color32::from_rgb(243, 139, 168)
                                };
                                ui.label(RichText::new(diff).monospace().color(color));
                            });
                            row.col(|_| {});
                        });
                    });
            });
    }

    // ── SNIFFER TAB ─────────────────────────────────────────────

    fn show_sniffer(&mut self, ui: &mut egui::Ui) {
        let data = match &self.data {
            Some(d) => d,
            None => {
                ui.heading("No data loaded");
                return;
            }
        };
        let can_ids = data.can_ids.clone();
        let sources = data.sources.clone();

        // Filters
        ui.horizontal(|ui| {
            ui.label("CAN ID:");
            let old_id = self.sniff_id_filter;
            egui::ComboBox::from_id_salt("sniff_id")
                .selected_text(match self.sniff_id_filter {
                    Some(id) => format!("0x{:03X}", id),
                    None => "All".into(),
                })
                .show_ui(ui, |ui| {
                    if ui.selectable_label(self.sniff_id_filter.is_none(), "All").clicked() {
                        self.sniff_id_filter = None;
                    }
                    for &cid in &can_ids {
                        if ui
                            .selectable_label(
                                self.sniff_id_filter == Some(cid),
                                RichText::new(format!("0x{:03X}", cid)).color(id_color(cid)),
                            )
                            .clicked()
                        {
                            self.sniff_id_filter = Some(cid);
                        }
                    }
                });
            if self.sniff_id_filter != old_id {
                self.sniff_dirty = true;
            }

            ui.label("Source:");
            let old_src = self.sniff_src_filter.clone();
            egui::ComboBox::from_id_salt("sniff_src")
                .selected_text(
                    self.sniff_src_filter
                        .as_deref()
                        .unwrap_or("All"),
                )
                .show_ui(ui, |ui| {
                    if ui
                        .selectable_label(self.sniff_src_filter.is_none(), "All")
                        .clicked()
                    {
                        self.sniff_src_filter = None;
                    }
                    for s in &sources {
                        if ui
                            .selectable_label(
                                self.sniff_src_filter.as_ref() == Some(s),
                                s.as_str(),
                            )
                            .clicked()
                        {
                            self.sniff_src_filter = Some(s.clone());
                        }
                    }
                });
            if self.sniff_src_filter != old_src {
                self.sniff_dirty = true;
            }

            ui.label("Search:");
            let old_search = self.sniff_search.clone();
            ui.add(egui::TextEdit::singleline(&mut self.sniff_search).desired_width(120.0));
            if self.sniff_search != old_search {
                self.sniff_dirty = true;
            }

            ui.label(
                RichText::new(format!("{} frames", self.sniff_indices.len()))
                    .color(Color32::from_rgb(166, 173, 200)),
            );
        });

        if self.sniff_dirty {
            self.rebuild_sniffer_filter();
        }

        ui.separator();

        // Frame table
        let indices = &self.sniff_indices;
        TableBuilder::new(ui)
            .striped(true)
            .cell_layout(egui::Layout::left_to_right(egui::Align::Center))
            .column(Column::exact(60.0))  // #
            .column(Column::exact(90.0))  // Time
            .column(Column::exact(70.0))  // CAN ID
            .column(Column::exact(40.0))  // DLC
            .column(Column::remainder().at_least(200.0)) // Data
            .column(Column::exact(80.0))  // Source
            .header(22.0, |mut header| {
                header.col(|ui| { ui.strong("#"); });
                header.col(|ui| { ui.strong("Time (s)"); });
                header.col(|ui| { ui.strong("CAN ID"); });
                header.col(|ui| { ui.strong("DLC"); });
                header.col(|ui| { ui.strong("Data (hex)"); });
                header.col(|ui| { ui.strong("Source"); });
            })
            .body(|body| {
                let data_ref = self.data.as_ref().unwrap();
                body.rows(20.0, indices.len(), |mut row| {
                    let idx = indices[row.index()];
                    let f = &data_ref.frames[idx];

                    row.col(|ui| {
                        ui.label(RichText::new((idx + 1).to_string()).monospace());
                    });
                    row.col(|ui| {
                        ui.label(RichText::new(format!("{:.4}", f.timestamp)).monospace());
                    });
                    row.col(|ui| {
                        ui.label(
                            RichText::new(format!("0x{:03X}", f.can_id))
                                .monospace()
                                .color(id_color(f.can_id)),
                        );
                    });
                    row.col(|ui| {
                        ui.label(RichText::new(f.dlc.to_string()).monospace());
                    });
                    row.col(|ui| {
                        ui.label(RichText::new(&f.hex_str).monospace());
                    });
                    row.col(|ui| {
                        ui.label(RichText::new(&f.source).monospace());
                    });
                });
            });
    }

    // ── SIGNAL PLOTTER TAB ──────────────────────────────────────

    fn show_plotter(&mut self, ui: &mut egui::Ui) {
        if self.data.is_none() {
            ui.heading("No data loaded");
            return;
        }
        let can_ids = self.data.as_ref().unwrap().can_ids.clone();
        let id_dlc = self.data.as_ref().unwrap().id_dlc.clone();

        ui.horizontal(|ui| {
            // CAN ID selector
            ui.label("CAN ID:");
            egui::ComboBox::from_id_salt("plot_id")
                .selected_text(match self.plot_id {
                    Some(id) => format!("0x{:03X}", id),
                    None => "Select".into(),
                })
                .show_ui(ui, |ui| {
                    for &cid in &can_ids {
                        if ui
                            .selectable_label(
                                self.plot_id == Some(cid),
                                RichText::new(format!("0x{:03X}", cid)).color(id_color(cid)),
                            )
                            .clicked()
                        {
                            self.plot_id = Some(cid);
                            self.plot_bytes = [false; 8];
                        }
                    }
                });

            // Byte checkboxes
            let dlc = self
                .plot_id
                .and_then(|id| id_dlc.get(&id).copied())
                .unwrap_or(8) as usize;
            for i in 0..8 {
                let enabled = i < dlc;
                ui.add_enabled(enabled, egui::Checkbox::new(&mut self.plot_bytes[i], format!("B{}", i)));
            }

            if ui
                .button(RichText::new("Add Signal").strong())
                .clicked()
            {
                self.add_plot_signals();
            }
            if ui.button("Clear").clicked() {
                self.plot_signals.clear();
                self.plot_color_idx = 0;
            }
        });

        ui.separator();

        // Plot
        let plot = egui_plot::Plot::new("signal_plot")
            .legend(egui_plot::Legend::default())
            .x_axis_label("Time (s)")
            .y_axis_label("Value")
            .show_axes(true)
            .show_grid(true);

        plot.show(ui, |plot_ui| {
            for sig in &self.plot_signals {
                let points = egui_plot::PlotPoints::new(sig.points.clone());
                let line = egui_plot::Line::new(points)
                    .name(&sig.label)
                    .color(sig.color)
                    .width(1.5);
                plot_ui.line(line);
            }
        });
    }

    fn add_plot_signals(&mut self) {
        let data = match &self.data {
            Some(d) => d,
            None => return,
        };
        let can_id = match self.plot_id {
            Some(id) => id,
            None => return,
        };

        let checked: Vec<usize> = self
            .plot_bytes
            .iter()
            .enumerate()
            .filter(|(_, &c)| c)
            .map(|(i, _)| i)
            .collect();

        for bi in checked {
            let points: Vec<[f64; 2]> = data
                .frames
                .iter()
                .filter(|f| f.can_id == can_id && (bi < f.dlc as usize))
                .map(|f| [f.timestamp, f.data[bi] as f64])
                .collect();

            if points.is_empty() {
                continue;
            }

            let ci = self.plot_color_idx % PALETTE.len();
            let color = Color32::from_rgb(PALETTE[ci][0], PALETTE[ci][1], PALETTE[ci][2]);
            self.plot_color_idx += 1;

            self.plot_signals.push(PlotSignal {
                label: format!("0x{:03X} B{}", can_id, bi),
                color,
                points,
            });
        }
    }

    // ── STATS TAB ───────────────────────────────────────────────

    fn show_stats(&mut self, ui: &mut egui::Ui) {
        let data = match &self.data {
            Some(d) => d,
            None => {
                ui.heading("No data loaded");
                return;
            }
        };

        ui.heading(
            RichText::new("CAN ID Statistics")
                .color(Color32::from_rgb(137, 180, 250)),
        );

        TableBuilder::new(ui)
            .striped(true)
            .cell_layout(egui::Layout::left_to_right(egui::Align::Center))
            .column(Column::exact(70.0))  // CAN ID
            .column(Column::exact(60.0))  // Count
            .column(Column::exact(50.0))  // %
            .column(Column::exact(70.0))  // Freq
            .column(Column::exact(40.0))  // DLC
            .column(Column::exact(80.0))  // First
            .column(Column::exact(80.0))  // Last
            .column(Column::exact(80.0))  // Min dt
            .column(Column::exact(80.0))  // Mean dt
            .column(Column::exact(80.0))  // Max dt
            .column(Column::exact(80.0))  // Changes
            .column(Column::remainder())
            .header(22.0, |mut header| {
                header.col(|ui| { ui.strong("CAN ID"); });
                header.col(|ui| { ui.strong("Count"); });
                header.col(|ui| { ui.strong("%"); });
                header.col(|ui| { ui.strong("Freq Hz"); });
                header.col(|ui| { ui.strong("DLC"); });
                header.col(|ui| { ui.strong("First (s)"); });
                header.col(|ui| { ui.strong("Last (s)"); });
                header.col(|ui| { ui.strong("Min dt"); });
                header.col(|ui| { ui.strong("Mean dt"); });
                header.col(|ui| { ui.strong("Max dt"); });
                header.col(|ui| { ui.strong("Changes"); });
                header.col(|_| {});
            })
            .body(|body| {
                let total = data.frames.len();
                body.rows(22.0, data.can_ids.len(), |mut row| {
                    let cid = data.can_ids[row.index()];
                    let frames_for_id: Vec<&CanFrame> =
                        data.frames.iter().filter(|f| f.can_id == cid).collect();
                    let n = frames_for_id.len();
                    let t_first = frames_for_id.first().map(|f| f.timestamp).unwrap_or(0.0);
                    let t_last = frames_for_id.last().map(|f| f.timestamp).unwrap_or(0.0);
                    let dur = t_last - t_first;
                    let freq = if dur > 0.0 { n as f64 / dur } else { 0.0 };
                    let dlc = data.id_dlc.get(&cid).copied().unwrap_or(0);

                    // Timing stats
                    let mut dts: Vec<f64> = Vec::new();
                    for i in 1..frames_for_id.len() {
                        dts.push(
                            (frames_for_id[i].timestamp - frames_for_id[i - 1].timestamp) * 1000.0,
                        );
                    }
                    let dt_min = dts.iter().cloned().fold(f64::MAX, f64::min);
                    let dt_max = dts.iter().cloned().fold(0.0f64, f64::max);
                    let dt_mean = if !dts.is_empty() {
                        dts.iter().sum::<f64>() / dts.len() as f64
                    } else {
                        0.0
                    };

                    let changes = self
                        .all_changes
                        .iter()
                        .filter(|c| c.can_id == cid)
                        .count();

                    row.col(|ui| {
                        ui.label(
                            RichText::new(format!("0x{:03X}", cid))
                                .monospace()
                                .color(id_color(cid))
                                .strong(),
                        );
                    });
                    row.col(|ui| { ui.label(RichText::new(n.to_string()).monospace()); });
                    row.col(|ui| {
                        ui.label(
                            RichText::new(format!("{:.1}", 100.0 * n as f64 / total as f64))
                                .monospace(),
                        );
                    });
                    row.col(|ui| { ui.label(RichText::new(format!("{:.1}", freq)).monospace()); });
                    row.col(|ui| { ui.label(RichText::new(dlc.to_string()).monospace()); });
                    row.col(|ui| { ui.label(RichText::new(format!("{:.3}", t_first)).monospace()); });
                    row.col(|ui| { ui.label(RichText::new(format!("{:.3}", t_last)).monospace()); });
                    row.col(|ui| {
                        ui.label(RichText::new(format!("{:.2}ms", dt_min)).monospace());
                    });
                    row.col(|ui| {
                        ui.label(RichText::new(format!("{:.2}ms", dt_mean)).monospace());
                    });
                    row.col(|ui| {
                        ui.label(RichText::new(format!("{:.2}ms", dt_max)).monospace());
                    });
                    row.col(|ui| { ui.label(RichText::new(changes.to_string()).monospace()); });
                    row.col(|_| {});
                });
            });

        ui.separator();

        // Change summary per byte
        ui.heading(
            RichText::new("Byte Change Summary (all time)")
                .color(Color32::from_rgb(137, 180, 250))
                .size(14.0),
        );

        for &cid in &data.can_ids {
            let dlc = data.id_dlc.get(&cid).copied().unwrap_or(0) as usize;
            ui.horizontal(|ui| {
                ui.label(
                    RichText::new(format!("0x{:03X}:", cid))
                        .monospace()
                        .color(id_color(cid))
                        .strong(),
                );
                for bi in 0..dlc {
                    let cnt = self
                        .all_changes
                        .iter()
                        .filter(|c| c.can_id == cid && c.byte_idx == bi)
                        .count();
                    let intensity = (cnt as f32 / 100.0).min(1.0);
                    let r = (243.0 * intensity) as u8;
                    let g = (227.0 * (1.0 - intensity * 0.6)) as u8;
                    ui.label(
                        RichText::new(format!("B{}:{}", bi, cnt))
                            .monospace()
                            .color(Color32::from_rgb(r, g, 161)),
                    );
                }
            });
        }
    }
}

// ══════════════════════════════════════════════════════════════════
// EFRAME APP IMPLEMENTATION
// ══════════════════════════════════════════════════════════════════

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Check MF4 conversion status
        self.check_mf4_status();

        // Advance playback
        if self.playing {
            if let Some(data) = &self.data {
                let dt = ctx.input(|i| i.stable_dt as f64) * self.speed;
                let new_time = self.playback.current_time + dt;
                let (_, t_max) = data.time_range;
                if new_time >= t_max {
                    self.playback.seek(data, t_max);
                    self.playing = false;
                } else {
                    self.playback.advance_to(data, new_time);
                }
            }
            ctx.request_repaint();
        }

        // ── Top panel: Menu + Tabs ──
        egui::TopBottomPanel::top("top_bar").show(ctx, |ui| {
            egui::menu::bar(ui, |ui| {
                ui.menu_button("File", |ui| {
                    if ui.button("Open MF4 File...").clicked() {
                        if let Some(path) = rfd::FileDialog::new()
                            .add_filter("MF4", &["MF4", "mf4", "mdf", "MDF"])
                            .pick_file()
                        {
                            let p = path.to_string_lossy().to_string();
                            self.load_mf4_file(p, ctx.clone());
                        }
                        ui.close_menu();
                    }
                    if ui.button("Open MF4 Directory...").clicked() {
                        if let Some(path) = rfd::FileDialog::new().pick_folder() {
                            let p = path.to_string_lossy().to_string();
                            self.load_mf4_dir(p, ctx.clone());
                        }
                        ui.close_menu();
                    }
                    ui.separator();
                    if ui.button("Open CSV...").clicked() {
                        if let Some(path) = rfd::FileDialog::new()
                            .add_filter("CSV", &["csv"])
                            .pick_file()
                        {
                            self.csv_path = path.to_string_lossy().to_string();
                            self.load_data();
                        }
                        ui.close_menu();
                    }
                    if ui.button("Reload").clicked() {
                        self.load_data();
                        ui.close_menu();
                    }
                    ui.separator();
                    if ui.button("Export Change Log...").clicked() {
                        if let Some(path) = rfd::FileDialog::new()
                            .add_filter("CSV", &["csv"])
                            .set_file_name("change_log.csv")
                            .save_file()
                        {
                            self.export_change_log(&path);
                        }
                        ui.close_menu();
                    }
                    ui.separator();
                    if ui.button("Quit").clicked() {
                        ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                    }
                });
            });

            ui.horizontal(|ui| {
                ui.selectable_value(&mut self.tab, Tab::DataFlow, "Data Flow");
                ui.selectable_value(&mut self.tab, Tab::Sniffer, "Sniffer");
                ui.selectable_value(&mut self.tab, Tab::Plotter, "Signal Plotter");
                ui.selectable_value(&mut self.tab, Tab::Stats, "Stats");

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if let Some(data) = &self.data {
                        let (t0, t1) = data.time_range;
                        ui.label(
                            RichText::new(format!(
                                "{} frames | {} IDs | {:.1}-{:.1}s",
                                data.frames.len(),
                                data.can_ids.len(),
                                t0,
                                t1
                            ))
                            .color(Color32::from_rgb(166, 173, 200))
                            .small(),
                        );
                    } else {
                        let mf4_msg = self.mf4_status.lock().unwrap().clone();
                        match mf4_msg {
                            MF4Status::Converting(ref msg) => {
                                ui.spinner();
                                ui.label(
                                    RichText::new(msg)
                                        .color(Color32::from_rgb(249, 226, 175)),
                                );
                            }
                            _ => {
                                ui.label(
                                    RichText::new("No data — File > Open MF4 File / Directory")
                                        .color(Color32::from_rgb(243, 139, 168)),
                                );
                            }
                        }
                    }
                });
            });
        });

        // ── Central panel ──
        egui::CentralPanel::default().show(ctx, |ui| {
            if !self.load_error.is_empty() {
                ui.colored_label(Color32::from_rgb(243, 139, 168), &self.load_error);
            }

            // Show converting overlay
            let is_converting = matches!(
                *self.mf4_status.lock().unwrap(),
                MF4Status::Converting(_)
            );
            if is_converting {
                ui.vertical_centered(|ui| {
                    ui.add_space(100.0);
                    ui.spinner();
                    ui.add_space(10.0);
                    let msg = match &*self.mf4_status.lock().unwrap() {
                        MF4Status::Converting(m) => m.clone(),
                        _ => String::new(),
                    };
                    ui.heading(
                        RichText::new(msg)
                            .color(Color32::from_rgb(249, 226, 175)),
                    );
                    ui.label("Using Python + asammdf to parse MF4 binary format...");
                });
                ctx.request_repaint();
                return;
            }

            match self.tab {
                Tab::DataFlow => self.show_data_flow(ui),
                Tab::Sniffer => self.show_sniffer(ui),
                Tab::Plotter => self.show_plotter(ui),
                Tab::Stats => self.show_stats(ui),
            }
        });
    }
}

impl App {
    fn export_change_log(&self, path: &PathBuf) {
        let mut wtr = match csv::Writer::from_path(path) {
            Ok(w) => w,
            Err(_) => return,
        };
        let _ = wtr.write_record(["timestamp", "can_id", "byte", "old", "new", "diff"]);
        for ch in &self.all_changes {
            let _ = wtr.write_record([
                format!("{:.4}", ch.timestamp),
                format!("0x{:03X}", ch.can_id),
                format!("B{}", ch.byte_idx),
                format!("{:02X}", ch.old_val),
                format!("{:02X}", ch.new_val),
                ch.diff_str(),
            ]);
        }
    }
}

// ══════════════════════════════════════════════════════════════════
// ENTRY POINT
// ══════════════════════════════════════════════════════════════════

fn main() -> eframe::Result {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1400.0, 900.0])
            .with_min_inner_size([800.0, 600.0])
            .with_title("CAN Analyzer v2.0"),
        ..Default::default()
    };

    eframe::run_native(
        "CAN Analyzer v2.0",
        options,
        Box::new(|cc| {
            // Dark theme
            let mut visuals = egui::Visuals::dark();
            visuals.panel_fill = Color32::from_rgb(30, 30, 46);
            visuals.window_fill = Color32::from_rgb(30, 30, 46);
            visuals.extreme_bg_color = Color32::from_rgb(24, 24, 37);
            visuals.widgets.inactive.bg_fill = Color32::from_rgb(49, 50, 68);
            visuals.widgets.hovered.bg_fill = Color32::from_rgb(69, 71, 90);
            visuals.widgets.active.bg_fill = Color32::from_rgb(88, 91, 112);
            visuals.widgets.noninteractive.bg_fill = Color32::from_rgb(42, 42, 58);
            visuals.widgets.inactive.fg_stroke =
                Stroke::new(1.0, Color32::from_rgb(186, 194, 222));
            visuals.widgets.noninteractive.fg_stroke =
                Stroke::new(1.0, Color32::from_rgb(205, 214, 244));
            visuals.selection.bg_fill = Color32::from_rgb(137, 180, 250);
            visuals.override_text_color = Some(Color32::from_rgb(205, 214, 244));
            visuals.striped = true;
            cc.egui_ctx.set_visuals(visuals);

            // Larger default font
            let mut style = (*cc.egui_ctx.style()).clone();
            style.text_styles.insert(
                egui::TextStyle::Body,
                egui::FontId::new(13.0, egui::FontFamily::Proportional),
            );
            style.text_styles.insert(
                egui::TextStyle::Monospace,
                egui::FontId::new(13.0, egui::FontFamily::Monospace),
            );
            cc.egui_ctx.set_style(style);

            Ok(Box::new(App::new(cc)))
        }),
    )
}
