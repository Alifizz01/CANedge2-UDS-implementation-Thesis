#!/usr/bin/env python3
"""
CAN Analyzer v1.0 - SavvyCAN-like CAN Bus Analysis Tool for MF4 Files

Features:
  - Sniffer:          Browse/filter CAN frames with color-coded table
  - ID Analysis:      Per-CAN-ID statistics, distribution charts
  - Signal Plotter:   Interactive byte-level signal plotting (pyqtgraph)
  - Payload Analysis: Bit-change heatmap, byte distributions
  - Flow Analysis:    Message timeline, rate charts, timing stats

Usage:
  cd src && python -X utf8 can_analyzer.py

Dependencies:
  pip install PyQt5 pyqtgraph asammdf pandas numpy matplotlib
"""

import sys
import os
from pathlib import Path

# Ensure utf-8 output on Windows
if hasattr(sys.stdout, "buffer"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout,
        QHBoxLayout, QTableView, QHeaderView, QComboBox, QLineEdit,
        QPushButton, QLabel, QGroupBox, QCheckBox, QSplitter, QFileDialog,
        QStatusBar, QAction, QAbstractItemView, QDoubleSpinBox, QFormLayout,
        QGridLayout, QSizePolicy, QMessageBox, QTableWidget, QTableWidgetItem,
        QFrame, QScrollArea, QToolBar
    )
    from PyQt5.QtCore import (
        Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QSize
    )
    from PyQt5.QtGui import QColor, QFont, QBrush, QPalette
except ImportError:
    print("ERROR: PyQt5 not found. Install: pip install PyQt5")
    sys.exit(1)

try:
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True)
    pg.setConfigOption("background", "#1e1e2e")
    pg.setConfigOption("foreground", "#cdd6f4")
except ImportError:
    print("ERROR: pyqtgraph not found. Install: pip install pyqtgraph")
    sys.exit(1)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib
matplotlib.use("Qt5Agg")

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mf4_reader


# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

APP_NAME = "CAN Analyzer"
APP_VERSION = "1.0.0"

CAN_ID_COLORS = {
    0x065: "#e6194b", 0x066: "#3cb44b", 0x067: "#4363d8", 0x068: "#f58231",
    0x06A: "#911eb4", 0x06B: "#42d4f4", 0x06F: "#f032e6",
}

SIGNAL_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#469990", "#dcbeff",
    "#9A6324", "#800000", "#aaffc3", "#fffac8", "#ffd8b1",
]

MPL_RC = {
    "figure.facecolor": "#1e1e2e", "axes.facecolor": "#2a2a3a",
    "axes.edgecolor": "#45475a", "axes.labelcolor": "#cdd6f4",
    "text.color": "#cdd6f4", "xtick.color": "#a6adc8",
    "ytick.color": "#a6adc8", "grid.color": "#45475a", "grid.alpha": 0.3,
    "legend.facecolor": "#2a2a3a", "legend.edgecolor": "#45475a",
    "figure.titlesize": 13, "axes.titlesize": 11, "font.size": 9,
}
matplotlib.rcParams.update(MPL_RC)

DARK_QSS = """
QMainWindow, QWidget { background-color: #1e1e2e; color: #cdd6f4; }
QTabWidget::pane { border: 1px solid #45475a; background: #1e1e2e; }
QTabBar::tab { background: #2a2a3a; color: #bac2de; padding: 8px 18px;
               border: 1px solid #45475a; border-bottom: none; margin-right: 2px; }
QTabBar::tab:selected { background: #45475a; color: #89b4fa; }
QTabBar::tab:hover { background: #383850; }
QTableView, QTableWidget { background-color: #1e1e2e;
    alternate-background-color: #232336; gridline-color: #45475a;
    selection-background-color: #45475a; selection-color: #cdd6f4; }
QHeaderView::section { background: #313244; color: #cdd6f4;
    padding: 5px; border: 1px solid #45475a; font-weight: bold; }
QComboBox { background: #2a2a3a; border: 1px solid #45475a;
    padding: 4px 8px; border-radius: 4px; min-width: 80px; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background: #2a2a3a; border: 1px solid #45475a;
    selection-background-color: #45475a; }
QLineEdit { background: #2a2a3a; border: 1px solid #45475a;
    padding: 4px 8px; border-radius: 4px; }
QLineEdit:focus { border: 1px solid #89b4fa; }
QPushButton { background: #45475a; color: #cdd6f4; border: none;
    padding: 6px 14px; border-radius: 4px; font-weight: bold; }
QPushButton:hover { background: #585b70; }
QPushButton:pressed { background: #6c7086; }
QGroupBox { border: 1px solid #45475a; border-radius: 6px;
    margin-top: 12px; padding-top: 18px; font-weight: bold; }
QGroupBox::title { color: #89b4fa; subcontrol-position: top left;
    padding: 0 6px; }
QSplitter::handle { background: #45475a; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }
QStatusBar { background: #181825; color: #a6adc8; font-size: 12px; }
QMenuBar { background: #181825; color: #cdd6f4; }
QMenuBar::item:selected { background: #45475a; }
QMenu { background: #2a2a3a; border: 1px solid #45475a; }
QMenu::item:selected { background: #45475a; }
QScrollBar:vertical { background: #1e1e2e; width: 10px; }
QScrollBar::handle:vertical { background: #45475a; border-radius: 5px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #1e1e2e; height: 10px; }
QScrollBar::handle:horizontal { background: #45475a; border-radius: 5px; min-width: 20px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #585b70;
    border-radius: 3px; background: #2a2a3a; }
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QDoubleSpinBox, QSpinBox { background: #2a2a3a; border: 1px solid #45475a;
    padding: 3px; border-radius: 4px; }
QLabel { background: transparent; }
QToolBar { background: #181825; border: none; spacing: 6px; padding: 2px; }
QToolBar QLabel { padding: 0 4px; }
"""

MONO = QFont("Consolas", 10)


def get_color(can_id):
    if can_id in CAN_ID_COLORS:
        return CAN_ID_COLORS[can_id]
    return SIGNAL_COLORS[can_id % len(SIGNAL_COLORS)]


def normalize_bytes(b):
    """Convert any data_bytes value to list of ints."""
    if isinstance(b, (bytes, bytearray)):
        return list(b)
    if isinstance(b, np.ndarray):
        return b.astype(int).tolist()
    if hasattr(b, "__iter__") and not isinstance(b, str):
        return [int(x) for x in b]
    return []


# ═══════════════════════════════════════════════════════════════════════
# DATA MANAGER
# ═══════════════════════════════════════════════════════════════════════

class DataManager:
    """Centralized CAN data storage and access."""

    def __init__(self):
        self.df = pd.DataFrame()
        self.sources = []
        self.can_ids = []
        self.time_range = (0.0, 0.0)
        self.is_loaded = False

    def load_default(self):
        self.df = mf4_reader.load_all()
        self._post_load()

    def load_directory(self, dir_path):
        self.df = mf4_reader.load_all(log_dir=dir_path)
        self._post_load()

    def load_file(self, file_path):
        self.df = mf4_reader.load_file(file_path)
        self.df["source"] = Path(file_path).parent.name
        self._post_load()

    def load_csv(self, csv_path):
        self.df = pd.read_csv(csv_path, index_col=0)
        if "data_bytes" in self.df.columns:
            import ast
            self.df["data_bytes"] = self.df["data_bytes"].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
        self._post_load()

    def _post_load(self):
        if self.df.empty:
            self.is_loaded = False
            return
        self.df["data_bytes"] = self.df["data_bytes"].apply(normalize_bytes)
        self.df.sort_index(inplace=True)
        self._expand_bytes()
        self.df["data_hex_fmt"] = self.df["data_bytes"].apply(
            lambda b: " ".join(f"{x:02X}" for x in b)
        )
        self.sources = sorted(self.df["source"].unique().tolist())
        self.can_ids = sorted(self.df["can_id"].unique().astype(int).tolist())
        t = self.df.index.values
        self.time_range = (float(t.min()), float(t.max()))
        self.is_loaded = True

    def _expand_bytes(self):
        max_dlc = int(self.df["dlc"].max())
        data_lists = self.df["data_bytes"].tolist()
        for i in range(max_dlc):
            self.df[f"b{i}"] = [
                float(row[i]) if i < len(row) else np.nan for row in data_lists
            ]

    def get_dlc(self, can_id):
        sub = self.df[self.df["can_id"] == can_id]
        return int(sub["dlc"].max()) if len(sub) > 0 else 0


# ═══════════════════════════════════════════════════════════════════════
# TABLE MODELS
# ═══════════════════════════════════════════════════════════════════════

class CANFrameModel(QAbstractTableModel):
    COLUMNS = ["#", "Time (s)", "CAN ID", "DLC", "Data (hex)", "Source"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = pd.DataFrame()
        self._timestamps = np.array([])
        self._row_nums = np.array([])
        self._time_strs = []
        self._id_strs = []
        self._id_vals = np.array([])
        self._dlc_vals = np.array([])
        self._hex_strs = []
        self._src_strs = []
        self._color_cache = {}

    def set_data(self, df):
        self.beginResetModel()
        self._df = df
        n = len(df)
        if n > 0:
            self._timestamps = df.index.values.astype(float)
            self._row_nums = np.arange(1, n + 1)
            self._time_strs = [f"{t:.4f}" for t in self._timestamps]
            self._id_vals = df["can_id"].values.astype(int)
            self._id_strs = [f"0x{x:03X}" for x in self._id_vals]
            self._dlc_vals = df["dlc"].values.astype(int)
            self._hex_strs = df["data_hex_fmt"].tolist()
            self._src_strs = df["source"].astype(str).tolist()
        else:
            self._timestamps = np.array([])
            self._row_nums = np.array([])
            self._time_strs = []
            self._id_strs = []
            self._id_vals = np.array([])
            self._dlc_vals = np.array([])
            self._hex_strs = []
            self._src_strs = []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._time_strs)

    def columnCount(self, parent=QModelIndex()):
        return 6

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if role == Qt.DisplayRole:
            if c == 0: return int(self._row_nums[r])
            if c == 1: return self._time_strs[r]
            if c == 2: return self._id_strs[r]
            if c == 3: return int(self._dlc_vals[r])
            if c == 4: return self._hex_strs[r]
            if c == 5: return self._src_strs[r]
        elif role == Qt.BackgroundRole:
            cid = int(self._id_vals[r])
            if cid not in self._color_cache:
                c_hex = get_color(cid)
                qc = QColor(c_hex)
                qc.setAlpha(35)
                self._color_cache[cid] = QBrush(qc)
            return self._color_cache[cid]
        elif role == Qt.FontRole:
            if c in (2, 4):
                return MONO
        elif role == Qt.TextAlignmentRole:
            if c in (0, 3):
                return Qt.AlignCenter
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMNS[section]
        return None

    def get_can_id(self, row):
        return int(self._id_vals[row])

    def get_hex(self, row):
        return self._hex_strs[row]

    def get_source(self, row):
        return self._src_strs[row]


class CANFilterProxy(QSortFilterProxyModel):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._can_id = None
        self._search = ""
        self._source = None

    def set_can_id(self, can_id):
        self._can_id = can_id
        self.invalidateFilter()

    def set_search(self, text):
        self._search = text.upper().strip()
        self.invalidateFilter()

    def set_source(self, source):
        self._source = source
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        m = self.sourceModel()
        if self._can_id is not None and m.get_can_id(row) != self._can_id:
            return False
        if self._search and self._search not in m.get_hex(row):
            return False
        if self._source is not None and m.get_source(row) != self._source:
            return False
        return True

    def lessThan(self, left, right):
        ld = self.sourceModel().data(left, Qt.DisplayRole)
        rd = self.sourceModel().data(right, Qt.DisplayRole)
        c = left.column()
        if c in (0, 3):
            return int(ld) < int(rd)
        if c == 1:
            return float(ld) < float(rd)
        return str(ld) < str(rd)


# ═══════════════════════════════════════════════════════════════════════
# TAB 1: SNIFFER (Frame View)
# ═══════════════════════════════════════════════════════════════════════

class FrameViewWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dm = None
        self.model = CANFrameModel(self)
        self.proxy = CANFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ── Toolbar ──
        tb = QHBoxLayout()
        tb.addWidget(QLabel("CAN ID:"))
        self.id_combo = QComboBox()
        self.id_combo.addItem("All", None)
        self.id_combo.currentIndexChanged.connect(self._on_id_changed)
        tb.addWidget(self.id_combo)

        tb.addWidget(QLabel("Source:"))
        self.src_combo = QComboBox()
        self.src_combo.addItem("All", None)
        self.src_combo.currentIndexChanged.connect(self._on_src_changed)
        tb.addWidget(self.src_combo)

        tb.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Hex pattern (e.g. A5 B3)")
        self.search_box.textChanged.connect(self.proxy.set_search)
        tb.addWidget(self.search_box)

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self._export)
        tb.addWidget(self.export_btn)
        tb.addStretch()

        self.count_label = QLabel("0 frames")
        self.count_label.setStyleSheet("color: #a6adc8;")
        tb.addWidget(self.count_label)
        layout.addLayout(tb)

        # ── Table ──
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 50)
        self.table.setColumnWidth(4, 260)
        layout.addWidget(self.table)

    def set_data(self, dm):
        self.dm = dm
        self.model.set_data(dm.df)
        self.id_combo.blockSignals(True)
        self.id_combo.clear()
        self.id_combo.addItem("All", None)
        for cid in dm.can_ids:
            self.id_combo.addItem(f"0x{cid:03X}", cid)
        self.id_combo.blockSignals(False)

        self.src_combo.blockSignals(True)
        self.src_combo.clear()
        self.src_combo.addItem("All", None)
        for s in dm.sources:
            self.src_combo.addItem(s, s)
        self.src_combo.blockSignals(False)

        self._update_count()

    def _on_id_changed(self, idx):
        cid = self.id_combo.currentData()
        self.proxy.set_can_id(cid)
        self._update_count()

    def _on_src_changed(self, idx):
        src = self.src_combo.currentData()
        self.proxy.set_source(src)
        self._update_count()

    def _update_count(self):
        total = self.model.rowCount()
        shown = self.proxy.rowCount()
        self.count_label.setText(
            f"{shown} / {total} frames" if shown != total else f"{total} frames"
        )

    def _export(self):
        if self.dm is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "can_export.csv",
                                               "CSV (*.csv)")
        if path:
            self.dm.df.to_csv(path)
            QMessageBox.information(self, "Export", f"Exported {len(self.dm.df)} frames to:\n{path}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 2: ID ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

class IDOverviewWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)

        # ── Stats table ──
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(8)
        self.stats_table.setHorizontalHeaderLabels([
            "CAN ID", "Count", "%", "Freq (Hz)", "DLC",
            "First (s)", "Last (s)", "Duration (s)"
        ])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.verticalHeader().setVisible(False)
        splitter.addWidget(self.stats_table)

        # ── Chart ──
        self.fig = Figure(figsize=(5, 6), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        chart_widget = QWidget()
        chart_layout = QVBoxLayout(chart_widget)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar = NavigationToolbar(self.canvas, chart_widget)
        chart_layout.addWidget(self.toolbar)
        chart_layout.addWidget(self.canvas)
        splitter.addWidget(chart_widget)

        splitter.setSizes([500, 500])
        layout.addWidget(splitter)

    def set_data(self, dm):
        self._fill_table(dm)
        self._draw_chart(dm)

    def _fill_table(self, dm):
        df = dm.df
        ids = dm.can_ids
        self.stats_table.setRowCount(len(ids))
        total = len(df)
        for i, cid in enumerate(ids):
            sub = df[df["can_id"] == cid]
            n = len(sub)
            t = sub.index.values
            t0, t1 = float(t.min()), float(t.max())
            dur = t1 - t0
            freq = n / dur if dur > 0 else 0
            dlc = int(sub["dlc"].iloc[0])
            pct = 100.0 * n / total if total > 0 else 0

            vals = [f"0x{cid:03X}", str(n), f"{pct:.1f}", f"{freq:.1f}",
                    str(dlc), f"{t0:.3f}", f"{t1:.3f}", f"{dur:.1f}"]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setForeground(QColor(get_color(cid)))
                if j in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.stats_table.setItem(i, j, item)

        self.stats_table.resizeColumnsToContents()

    def _draw_chart(self, dm):
        self.fig.clear()
        df = dm.df
        ids = dm.can_ids
        if not ids:
            self.canvas.draw()
            return

        counts = [len(df[df["can_id"] == cid]) for cid in ids]
        labels = [f"0x{cid:03X}" for cid in ids]
        colors = [get_color(cid) for cid in ids]

        ax1 = self.fig.add_subplot(211)
        bars = ax1.barh(labels, counts, color=colors, edgecolor="#45475a")
        ax1.set_xlabel("Message Count")
        ax1.set_title("CAN ID Distribution", fontweight="bold")
        ax1.invert_yaxis()
        for bar, count in zip(bars, counts):
            ax1.text(bar.get_width() + max(counts) * 0.02, bar.get_y() + bar.get_height() / 2,
                     str(count), va="center", fontsize=9, color="#a6adc8")

        ax2 = self.fig.add_subplot(212)
        wedges, texts, autotexts = ax2.pie(
            counts, labels=labels, colors=colors, autopct="%1.1f%%",
            textprops={"color": "#cdd6f4", "fontsize": 9},
            wedgeprops={"edgecolor": "#45475a"},
        )
        for t in autotexts:
            t.set_fontsize(8)
        ax2.set_title("Share of Bus Traffic", fontweight="bold")

        self.fig.tight_layout(pad=2)
        self.canvas.draw()


# ═══════════════════════════════════════════════════════════════════════
# TAB 3: SIGNAL PLOTTER
# ═══════════════════════════════════════════════════════════════════════

class SignalPlotterWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dm = None
        self.curves = []
        self._color_idx = 0
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ── Left panel: Controls ──
        ctrl = QWidget()
        ctrl.setFixedWidth(260)
        cl = QVBoxLayout(ctrl)
        cl.setContentsMargins(4, 4, 4, 4)

        # CAN ID selector
        grp1 = QGroupBox("Signal Selection")
        g1 = QFormLayout(grp1)
        self.id_combo = QComboBox()
        self.id_combo.currentIndexChanged.connect(self._on_id_changed)
        g1.addRow("CAN ID:", self.id_combo)

        self.src_combo = QComboBox()
        self.src_combo.addItem("All Sources", None)
        g1.addRow("Source:", self.src_combo)
        cl.addWidget(grp1)

        # Byte checkboxes
        grp2 = QGroupBox("Bytes to Plot")
        g2 = QGridLayout(grp2)
        self.byte_checks = []
        for i in range(8):
            cb = QCheckBox(f"B{i}")
            cb.setFont(MONO)
            self.byte_checks.append(cb)
            g2.addWidget(cb, i // 4, i % 4)
        cl.addWidget(grp2)

        # 16-bit mode
        grp_16 = QGroupBox("16-bit Combine")
        g16 = QFormLayout(grp_16)
        self.combine_combo = QComboBox()
        self.combine_combo.addItem("Off")
        for i in range(7):
            self.combine_combo.addItem(f"B[{i}:{i+1}] BE")
        for i in range(7):
            self.combine_combo.addItem(f"B[{i}:{i+1}] LE")
        g16.addRow("Combine:", self.combine_combo)
        cl.addWidget(grp_16)

        # Scaling
        grp3 = QGroupBox("Scaling")
        g3 = QFormLayout(grp3)
        self.factor_spin = QDoubleSpinBox()
        self.factor_spin.setRange(-10000, 10000)
        self.factor_spin.setValue(1.0)
        self.factor_spin.setDecimals(4)
        g3.addRow("Factor:", self.factor_spin)
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-10000, 10000)
        self.offset_spin.setValue(0.0)
        self.offset_spin.setDecimals(2)
        g3.addRow("Offset:", self.offset_spin)
        cl.addWidget(grp3)

        # Buttons
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add Signal")
        self.add_btn.clicked.connect(self._add_signal)
        self.add_btn.setStyleSheet("background: #89b4fa; color: #1e1e2e;")
        btn_row.addWidget(self.add_btn)
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._clear_plot)
        btn_row.addWidget(self.clear_btn)
        cl.addLayout(btn_row)

        # Active signals list
        grp4 = QGroupBox("Active Signals")
        g4 = QVBoxLayout(grp4)
        self.signal_list = QTableWidget()
        self.signal_list.setColumnCount(2)
        self.signal_list.setHorizontalHeaderLabels(["Signal", ""])
        self.signal_list.horizontalHeader().setStretchLastSection(True)
        self.signal_list.setColumnWidth(1, 50)
        self.signal_list.verticalHeader().setVisible(False)
        g4.addWidget(self.signal_list)
        cl.addWidget(grp4)

        cl.addStretch()
        layout.addWidget(ctrl)

        # ── Right panel: Plot ──
        plot_container = QWidget()
        pl = QVBoxLayout(plot_container)
        pl.setContentsMargins(0, 0, 0, 0)

        self.coord_label = QLabel("t = 0.000 s | val = 0.00")
        self.coord_label.setFont(MONO)
        self.coord_label.setStyleSheet("color: #89b4fa; padding: 2px 8px;")
        pl.addWidget(self.coord_label)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "Value")
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend(offset=(10, 10))
        pl.addWidget(self.plot_widget)

        # Crosshair
        self.vLine = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen("#89b4fa", width=1, style=Qt.DashLine))
        self.hLine = pg.InfiniteLine(angle=0, movable=False,
                                      pen=pg.mkPen("#89b4fa", width=1, style=Qt.DashLine))
        self.plot_widget.addItem(self.vLine, ignoreBounds=True)
        self.plot_widget.addItem(self.hLine, ignoreBounds=True)
        self.proxy = pg.SignalProxy(self.plot_widget.scene().sigMouseMoved,
                                    rateLimit=60, slot=self._mouse_moved)

        layout.addWidget(plot_container, stretch=1)

    def set_data(self, dm):
        self.dm = dm
        self.id_combo.blockSignals(True)
        self.id_combo.clear()
        for cid in dm.can_ids:
            self.id_combo.addItem(f"0x{cid:03X}", cid)
        self.id_combo.blockSignals(False)
        if dm.can_ids:
            self.id_combo.setCurrentIndex(0)
            self._on_id_changed(0)

        self.src_combo.blockSignals(True)
        self.src_combo.clear()
        self.src_combo.addItem("All Sources", None)
        for s in dm.sources:
            self.src_combo.addItem(s, s)
        self.src_combo.blockSignals(False)

    def _on_id_changed(self, idx):
        if self.dm is None:
            return
        cid = self.id_combo.currentData()
        if cid is None:
            return
        dlc = self.dm.get_dlc(cid)
        for i, cb in enumerate(self.byte_checks):
            cb.setEnabled(i < dlc)
            if i >= dlc:
                cb.setChecked(False)

    def _next_color(self):
        c = SIGNAL_COLORS[self._color_idx % len(SIGNAL_COLORS)]
        self._color_idx += 1
        return c

    def _add_signal(self):
        if self.dm is None:
            return
        cid = self.id_combo.currentData()
        src = self.src_combo.currentData()
        factor = self.factor_spin.value()
        offset = self.offset_spin.value()
        if cid is None:
            return

        # Check 16-bit combine
        combine_idx = self.combine_combo.currentIndex()
        if combine_idx > 0:
            self._add_16bit_signal(cid, src, combine_idx, factor, offset)
            return

        # Add individual byte signals
        checked = [i for i, cb in enumerate(self.byte_checks) if cb.isChecked()]
        if not checked:
            QMessageBox.information(self, "Info", "Select at least one byte or a 16-bit combine mode.")
            return
        for bi in checked:
            self._add_byte_signal(cid, bi, src, factor, offset)

    def _add_byte_signal(self, cid, byte_idx, source, factor, offset):
        mask = self.dm.df["can_id"] == cid
        if source:
            mask &= self.dm.df["source"] == source
        data = self.dm.df[mask]
        if len(data) == 0:
            return
        col = f"b{byte_idx}"
        if col not in data.columns:
            return
        t = data.index.values.astype(np.float64)
        y = data[col].values * factor + offset
        color = self._next_color()
        src_tag = f" [{source}]" if source else ""
        name = f"0x{cid:03X} B{byte_idx}{src_tag}"
        if factor != 1.0 or offset != 0.0:
            name += f" *{factor}+{offset}"
        curve = self.plot_widget.plot(t, y, pen=pg.mkPen(color, width=2), name=name)
        self.curves.append({"name": name, "curve": curve, "color": color})
        self._update_signal_list()

    def _add_16bit_signal(self, cid, source, combo_idx, factor, offset):
        # combo_idx 1-7: BE, 8-14: LE
        if combo_idx <= 7:
            hi_idx = combo_idx - 1
            lo_idx = hi_idx + 1
            endian = "BE"
        else:
            hi_idx = combo_idx - 8
            lo_idx = hi_idx + 1
            endian = "LE"

        mask = self.dm.df["can_id"] == cid
        if source:
            mask &= self.dm.df["source"] == source
        data = self.dm.df[mask]
        if len(data) == 0:
            return
        t = data.index.values.astype(np.float64)
        bh = data[f"b{hi_idx}"].values
        bl = data[f"b{lo_idx}"].values
        if endian == "BE":
            y = bh * 256 + bl
        else:
            y = bl * 256 + bh
        y = y * factor + offset
        color = self._next_color()
        src_tag = f" [{source}]" if source else ""
        name = f"0x{cid:03X} B[{hi_idx}:{lo_idx}] {endian}{src_tag}"
        curve = self.plot_widget.plot(t, y, pen=pg.mkPen(color, width=2), name=name)
        self.curves.append({"name": name, "curve": curve, "color": color})
        self._update_signal_list()

    def _clear_plot(self):
        for c in self.curves:
            self.plot_widget.removeItem(c["curve"])
        self.curves.clear()
        self._color_idx = 0
        self._update_signal_list()
        # Re-add legend
        if self.plot_widget.plotItem.legend is not None:
            self.plot_widget.plotItem.legend.clear()

    def _update_signal_list(self):
        self.signal_list.setRowCount(len(self.curves))
        for i, c in enumerate(self.curves):
            name_item = QTableWidgetItem(c["name"])
            name_item.setForeground(QColor(c["color"]))
            self.signal_list.setItem(i, 0, name_item)
            rm_btn = QPushButton("X")
            rm_btn.setFixedSize(30, 22)
            rm_btn.setStyleSheet(f"background: #f38ba8; color: #1e1e2e; font-weight: bold;")
            rm_btn.clicked.connect(lambda checked, idx=i: self._remove_signal(idx))
            self.signal_list.setCellWidget(i, 1, rm_btn)

    def _remove_signal(self, idx):
        if 0 <= idx < len(self.curves):
            c = self.curves.pop(idx)
            self.plot_widget.removeItem(c["curve"])
            self._update_signal_list()

    def _mouse_moved(self, evt):
        pos = evt[0]
        if self.plot_widget.plotItem.sceneBoundingRect().contains(pos):
            pt = self.plot_widget.plotItem.vb.mapSceneToView(pos)
            self.vLine.setPos(pt.x())
            self.hLine.setPos(pt.y())
            self.coord_label.setText(f"t = {pt.x():.3f} s | val = {pt.y():.2f}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 4: PAYLOAD ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

class PayloadAnalysisWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dm = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ── Toolbar ──
        tb = QHBoxLayout()
        tb.addWidget(QLabel("CAN ID:"))
        self.id_combo = QComboBox()
        self.id_combo.currentIndexChanged.connect(self._analyze)
        tb.addWidget(self.id_combo)
        tb.addWidget(QLabel("Source:"))
        self.src_combo = QComboBox()
        self.src_combo.addItem("All", None)
        self.src_combo.currentIndexChanged.connect(self._analyze)
        tb.addWidget(self.src_combo)
        tb.addStretch()
        layout.addLayout(tb)

        # ── Content area (scroll) ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self.content)
        layout.addWidget(scroll)

        # Heatmap + Stats side by side
        self.top_splitter = QSplitter(Qt.Horizontal)
        self.content_layout.addWidget(self.top_splitter)

        # Bit heatmap
        self.heat_fig = Figure(figsize=(6, 3.5), dpi=100)
        self.heat_canvas = FigureCanvas(self.heat_fig)
        self.top_splitter.addWidget(self.heat_canvas)

        # Byte stats table
        self.byte_table = QTableWidget()
        self.byte_table.setColumnCount(7)
        self.byte_table.setHorizontalHeaderLabels([
            "Byte", "Min", "Max", "Mean", "Std", "Unique", "Pattern"
        ])
        self.byte_table.verticalHeader().setVisible(False)
        self.byte_table.horizontalHeader().setStretchLastSection(True)
        self.top_splitter.addWidget(self.byte_table)
        self.top_splitter.setSizes([500, 400])

        # Byte distributions
        self.dist_fig = Figure(figsize=(10, 4), dpi=100)
        self.dist_canvas = FigureCanvas(self.dist_fig)
        self.dist_toolbar = NavigationToolbar(self.dist_canvas, self.content)
        self.content_layout.addWidget(self.dist_toolbar)
        self.content_layout.addWidget(self.dist_canvas)

    def set_data(self, dm):
        self.dm = dm
        self.id_combo.blockSignals(True)
        self.id_combo.clear()
        for cid in dm.can_ids:
            self.id_combo.addItem(f"0x{cid:03X}", cid)
        self.id_combo.blockSignals(False)

        self.src_combo.blockSignals(True)
        self.src_combo.clear()
        self.src_combo.addItem("All", None)
        for s in dm.sources:
            self.src_combo.addItem(s, s)
        self.src_combo.blockSignals(False)

        if dm.can_ids:
            self._analyze()

    def _analyze(self):
        if self.dm is None:
            return
        cid = self.id_combo.currentData()
        src = self.src_combo.currentData()
        if cid is None:
            return

        mask = self.dm.df["can_id"] == cid
        if src:
            mask &= self.dm.df["source"] == src
        msgs = self.dm.df[mask]
        if len(msgs) == 0:
            return
        dlc = int(msgs["dlc"].iloc[0])
        self._draw_heatmap(msgs, dlc)
        self._fill_stats(msgs, dlc)
        self._draw_distributions(msgs, dlc)

    def _draw_heatmap(self, msgs, dlc):
        """Bit transition rate heatmap."""
        self.heat_fig.clear()
        ax = self.heat_fig.add_subplot(111)

        transitions = np.zeros((dlc, 8))
        for bi in range(dlc):
            col = f"b{bi}"
            vals = msgs[col].dropna().values.astype(int)
            if len(vals) < 2:
                continue
            for bit in range(8):
                bits = (vals >> bit) & 1
                changes = np.sum(bits[1:] != bits[:-1])
                transitions[bi, 7 - bit] = changes / (len(vals) - 1)

        im = ax.imshow(transitions, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1,
                       interpolation="nearest")
        ax.set_xlabel("Bit Position (MSB \u2192 LSB)")
        ax.set_ylabel("Byte")
        ax.set_xticks(range(8))
        ax.set_xticklabels(["7", "6", "5", "4", "3", "2", "1", "0"])
        ax.set_yticks(range(dlc))
        ax.set_yticklabels([f"B{i}" for i in range(dlc)])

        for i in range(dlc):
            for j in range(8):
                v = transitions[i, j]
                tc = "#1e1e2e" if v > 0.5 else "#cdd6f4"
                ax.text(j, i, f"{v:.0%}", ha="center", va="center", color=tc, fontsize=8)

        self.heat_fig.colorbar(im, ax=ax, label="Transition Rate", shrink=0.85)
        ax.set_title("Bit Change Frequency", fontweight="bold")
        self.heat_fig.tight_layout()
        self.heat_canvas.draw()

    def _fill_stats(self, msgs, dlc):
        self.byte_table.setRowCount(dlc)
        for i in range(dlc):
            col = f"b{i}"
            vals = msgs[col].dropna().values
            mn, mx = int(vals.min()), int(vals.max())
            mean = float(vals.mean())
            std = float(vals.std())
            uniq = len(np.unique(vals))

            # Detect pattern
            pattern = ""
            if std == 0:
                pattern = f"Constant (0x{mn:02X})"
            elif uniq == 2 and mn == 0 and mx == 1:
                pattern = "Binary flag"
            elif uniq <= 3:
                pattern = f"Enum ({uniq} vals)"
            elif 32 <= mn <= 126 and 32 <= mx <= 126:
                pattern = "ASCII range"
            else:
                # Check counter
                diffs = np.diff(vals)
                if len(diffs) > 0 and np.all(diffs == 1):
                    pattern = "Counter (inc)"
                elif len(diffs) > 0 and np.all(diffs == -1):
                    pattern = "Counter (dec)"
                elif std < 3:
                    pattern = "Near-constant"
                elif mn >= 0 and mx <= 255:
                    pattern = "Dynamic"

            for j, v in enumerate([f"B{i}", str(mn), str(mx), f"{mean:.1f}",
                                    f"{std:.2f}", str(uniq), pattern]):
                item = QTableWidgetItem(v)
                if j == 0:
                    item.setForeground(QColor("#89b4fa"))
                    item.setFont(MONO)
                self.byte_table.setItem(i, j, item)
        self.byte_table.resizeColumnsToContents()

    def _draw_distributions(self, msgs, dlc):
        self.dist_fig.clear()
        cols = 4
        rows = max(1, (dlc + cols - 1) // cols)

        for i in range(dlc):
            ax = self.dist_fig.add_subplot(rows, cols, i + 1)
            vals = msgs[f"b{i}"].dropna().values
            ax.hist(vals, bins=min(50, len(np.unique(vals))),
                    color="#89b4fa", alpha=0.85, edgecolor="#45475a")
            ax.set_title(f"Byte {i}", fontsize=10, fontweight="bold")
            ax.tick_params(labelsize=7)
            if len(vals) > 0:
                ax.text(0.97, 0.95,
                        f"n={len(np.unique(vals))}\n\u03bc={np.mean(vals):.0f}",
                        transform=ax.transAxes, fontsize=7, color="#a6adc8",
                        ha="right", va="top")

        self.dist_fig.tight_layout(pad=1.5)
        self.dist_canvas.draw()


# ═══════════════════════════════════════════════════════════════════════
# TAB 5: FLOW ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

class DataFlowWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Vertical)

        # ── Timeline scatter ──
        self.timeline_plot = pg.PlotWidget(title="Message Timeline")
        self.timeline_plot.setLabel("bottom", "Time", units="s")
        self.timeline_plot.setLabel("left", "CAN ID")
        self.timeline_plot.showGrid(x=True, y=True, alpha=0.2)
        splitter.addWidget(self.timeline_plot)

        # ── Message rate ──
        self.rate_plot = pg.PlotWidget(title="Message Rate")
        self.rate_plot.setLabel("bottom", "Time", units="s")
        self.rate_plot.setLabel("left", "Messages / sec")
        self.rate_plot.showGrid(x=True, y=True, alpha=0.3)
        self.rate_plot.addLegend(offset=(10, 10))
        splitter.addWidget(self.rate_plot)

        # ── Timing stats ──
        self.timing_table = QTableWidget()
        self.timing_table.setColumnCount(8)
        self.timing_table.setHorizontalHeaderLabels([
            "CAN ID", "Count", "Freq (Hz)", "Min dt (ms)", "Max dt (ms)",
            "Mean dt (ms)", "Std dt (ms)", "Jitter (ms)"
        ])
        self.timing_table.setAlternatingRowColors(True)
        self.timing_table.verticalHeader().setVisible(False)
        self.timing_table.horizontalHeader().setStretchLastSection(True)
        self.timing_table.setMaximumHeight(220)
        splitter.addWidget(self.timing_table)

        splitter.setSizes([300, 250, 200])
        layout.addWidget(splitter)

    def set_data(self, dm):
        self._draw_timeline(dm)
        self._draw_rate(dm)
        self._fill_timing(dm)

    def _draw_timeline(self, dm):
        self.timeline_plot.clear()
        df = dm.df
        ids = dm.can_ids
        id_to_y = {cid: i for i, cid in enumerate(ids)}

        # Set Y axis ticks
        y_axis = self.timeline_plot.getAxis("left")
        ticks = [(i, f"0x{cid:03X}") for i, cid in enumerate(ids)]
        y_axis.setTicks([ticks])

        for cid in ids:
            sub = df[df["can_id"] == cid]
            t = sub.index.values.astype(np.float64)
            y = np.full(len(t), id_to_y[cid], dtype=np.float64)
            color = get_color(cid)
            self.timeline_plot.plot(t, y, pen=None,
                                    symbol="o", symbolSize=4,
                                    symbolBrush=pg.mkBrush(color),
                                    symbolPen=None)

    def _draw_rate(self, dm):
        self.rate_plot.clear()
        df = dm.df
        t_min, t_max = dm.time_range
        bin_width = 1.0
        bins = np.arange(t_min, t_max + bin_width, bin_width)
        if len(bins) < 2:
            return
        centers = (bins[:-1] + bins[1:]) / 2

        for cid in dm.can_ids:
            sub = df[df["can_id"] == cid]
            counts, _ = np.histogram(sub.index.values, bins=bins)
            color = get_color(cid)
            self.rate_plot.plot(centers, counts,
                                pen=pg.mkPen(color, width=2),
                                name=f"0x{cid:03X}")

    def _fill_timing(self, dm):
        df = dm.df
        ids = dm.can_ids
        self.timing_table.setRowCount(len(ids))

        for i, cid in enumerate(ids):
            sub = df[df["can_id"] == cid]
            t = sub.index.values.astype(np.float64)
            n = len(t)
            dt = np.diff(t) * 1000  # milliseconds
            dur = t[-1] - t[0] if n > 1 else 0
            freq = n / dur if dur > 0 else 0
            dt_min = float(dt.min()) if len(dt) > 0 else 0
            dt_max = float(dt.max()) if len(dt) > 0 else 0
            dt_mean = float(dt.mean()) if len(dt) > 0 else 0
            dt_std = float(dt.std()) if len(dt) > 0 else 0
            jitter = dt_max - dt_min

            vals = [f"0x{cid:03X}", str(n), f"{freq:.1f}",
                    f"{dt_min:.2f}", f"{dt_max:.2f}", f"{dt_mean:.2f}",
                    f"{dt_std:.2f}", f"{jitter:.2f}"]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if j == 0:
                    item.setForeground(QColor(get_color(cid)))
                    item.setFont(MONO)
                elif j >= 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.timing_table.setItem(i, j, item)

        self.timing_table.resizeColumnsToContents()


# ═══════════════════════════════════════════════════════════════════════
# TAB 6: LIVE HEX MATRIX (SavvyCAN-style current values)
# ═══════════════════════════════════════════════════════════════════════

class HexMatrixWidget(QWidget):
    """Shows current byte values for each CAN ID at a given time position,
    with highlighting for recently changed bytes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dm = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Time slider
        tb = QHBoxLayout()
        tb.addWidget(QLabel("Time Position:"))
        self.time_slider = pg.PlotWidget()
        self.time_slider.setFixedHeight(60)
        self.time_slider.setLabel("bottom", "Time", units="s")
        self.time_slider.showGrid(x=True, alpha=0.2)
        self.region = pg.LinearRegionItem(values=[0, 1], movable=True)
        self.region.setZValue(10)
        self.time_slider.addItem(self.region)
        self.region.sigRegionChanged.connect(self._on_region_changed)
        tb.addWidget(self.time_slider, stretch=1)

        self.time_label = QLabel("0.000 s")
        self.time_label.setFont(MONO)
        self.time_label.setStyleSheet("color: #89b4fa; min-width: 100px;")
        tb.addWidget(self.time_label)
        layout.addLayout(tb)

        # Hex matrix table
        self.hex_table = QTableWidget()
        self.hex_table.verticalHeader().setVisible(False)
        self.hex_table.setFont(MONO)
        self.hex_table.setStyleSheet("""
            QTableWidget { font-size: 13px; }
            QTableWidget::item { padding: 4px 8px; }
        """)
        layout.addWidget(self.hex_table)

        # Auto-play
        play_row = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self._toggle_play)
        play_row.addWidget(self.play_btn)
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["1x", "2x", "5x", "10x"])
        play_row.addWidget(QLabel("Speed:"))
        play_row.addWidget(self.speed_combo)
        play_row.addStretch()
        layout.addLayout(play_row)

        from PyQt5.QtCore import QTimer
        self._timer = QTimer()
        self._timer.timeout.connect(self._advance_time)
        self._playing = False
        self._current_time = 0.0

    def set_data(self, dm):
        self.dm = dm
        if not dm.is_loaded:
            return
        t0, t1 = dm.time_range
        self.time_slider.setXRange(t0, t1)
        self.region.setRegion([t0, t0 + min(1.0, (t1 - t0) * 0.01)])
        self._current_time = t0

        # Plot message density on slider background
        self.time_slider.clear()
        self.time_slider.addItem(self.region)
        bins = np.arange(t0, t1 + 0.5, 0.5)
        if len(bins) > 1:
            counts, _ = np.histogram(dm.df.index.values, bins=bins)
            centers = (bins[:-1] + bins[1:]) / 2
            self.time_slider.plot(centers, counts, pen=pg.mkPen("#45475a", width=1),
                                   fillLevel=0, brush=pg.mkBrush("#45475a80"))

        self._setup_table(dm)
        self._update_matrix()

    def _setup_table(self, dm):
        max_dlc = int(dm.df["dlc"].max())
        cols = ["CAN ID", "Count"] + [f"B{i}" for i in range(max_dlc)] + ["ASCII"]
        self.hex_table.setColumnCount(len(cols))
        self.hex_table.setHorizontalHeaderLabels(cols)
        self.hex_table.setRowCount(len(dm.can_ids))
        self._prev_values = {}

    def _on_region_changed(self):
        r = self.region.getRegion()
        self._current_time = r[1]
        self.time_label.setText(f"{self._current_time:.3f} s")
        self._update_matrix()

    def _update_matrix(self):
        if self.dm is None:
            return
        dm = self.dm
        max_dlc = int(dm.df["dlc"].max())

        for row, cid in enumerate(dm.can_ids):
            sub = dm.df[(dm.df["can_id"] == cid) & (dm.df.index <= self._current_time)]
            if len(sub) == 0:
                continue

            last = sub.iloc[-1]
            count = len(sub)
            data_bytes = last["data_bytes"]
            color = get_color(cid)

            # CAN ID cell
            id_item = QTableWidgetItem(f"0x{cid:03X}")
            id_item.setForeground(QColor(color))
            id_item.setFont(MONO)
            self.hex_table.setItem(row, 0, id_item)

            # Count
            self.hex_table.setItem(row, 1, QTableWidgetItem(str(count)))

            # Byte values with change highlighting
            prev_key = cid
            prev = self._prev_values.get(prev_key, [])
            ascii_str = ""
            for i in range(max_dlc):
                if i < len(data_bytes):
                    val = data_bytes[i]
                    item = QTableWidgetItem(f"{val:02X}")
                    item.setFont(MONO)
                    item.setTextAlignment(Qt.AlignCenter)
                    # Highlight changed bytes
                    if i < len(prev) and prev[i] != val:
                        item.setBackground(QColor("#f38ba8"))
                        item.setForeground(QColor("#1e1e2e"))
                    else:
                        item.setForeground(QColor("#cdd6f4"))
                    self.hex_table.setItem(row, 2 + i, item)
                    # ASCII
                    ascii_str += chr(val) if 32 <= val <= 126 else "."
                else:
                    self.hex_table.setItem(row, 2 + i, QTableWidgetItem(""))

            self._prev_values[prev_key] = list(data_bytes)

            # ASCII column
            ascii_item = QTableWidgetItem(ascii_str)
            ascii_item.setFont(MONO)
            ascii_item.setForeground(QColor("#a6e3a1"))
            self.hex_table.setItem(row, 2 + max_dlc, ascii_item)

        self.hex_table.resizeColumnsToContents()

    def _toggle_play(self):
        if self._playing:
            self._timer.stop()
            self._playing = False
            self.play_btn.setText("Play")
        else:
            speed_map = {"1x": 50, "2x": 25, "5x": 10, "10x": 5}
            interval = speed_map.get(self.speed_combo.currentText(), 50)
            self._timer.start(interval)
            self._playing = True
            self.play_btn.setText("Pause")

    def _advance_time(self):
        if self.dm is None:
            return
        t0, t1 = self.dm.time_range
        step = (t1 - t0) / 500
        self._current_time += step
        if self._current_time > t1:
            self._current_time = t0
        rmin, rmax = self.region.getRegion()
        width = rmax - rmin
        self.region.setRegion([self._current_time - width, self._current_time])


# ═══════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════

class CANAnalyzer(QMainWindow):

    def __init__(self):
        super().__init__()
        self.dm = DataManager()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1400, 900)
        self.setMinimumSize(900, 600)
        self._build_ui()
        self._center()

    def _center(self):
        try:
            screen = self.screen().availableGeometry()
        except AttributeError:
            screen = QApplication.desktop().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(max(0, x), max(0, y))

    def _build_ui(self):
        # ── Menu bar ──
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        act_open_dir = QAction("Open MF4 &Directory...", self)
        act_open_dir.setShortcut("Ctrl+O")
        act_open_dir.triggered.connect(self._open_directory)
        file_menu.addAction(act_open_dir)

        act_open_file = QAction("Open MF4 &File...", self)
        act_open_file.triggered.connect(self._open_file)
        file_menu.addAction(act_open_file)

        act_open_csv = QAction("Open &CSV...", self)
        act_open_csv.triggered.connect(self._open_csv)
        file_menu.addAction(act_open_csv)

        file_menu.addSeparator()

        act_reload = QAction("&Reload Default Data", self)
        act_reload.setShortcut("F5")
        act_reload.triggered.connect(self._load_default)
        file_menu.addAction(act_reload)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        help_menu = menu.addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)

        # ── Tabs ──
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.frame_view = FrameViewWidget()
        self.tabs.addTab(self.frame_view, "Sniffer")

        self.id_overview = IDOverviewWidget()
        self.tabs.addTab(self.id_overview, "ID Analysis")

        self.signal_plotter = SignalPlotterWidget()
        self.tabs.addTab(self.signal_plotter, "Signal Plotter")

        self.payload_analysis = PayloadAnalysisWidget()
        self.tabs.addTab(self.payload_analysis, "Payload Analysis")

        self.data_flow = DataFlowWidget()
        self.tabs.addTab(self.data_flow, "Flow Analysis")

        self.hex_matrix = HexMatrixWidget()
        self.tabs.addTab(self.hex_matrix, "Hex Matrix")

        self.setCentralWidget(self.tabs)

        # ── Status bar ──
        self.status_label = QLabel("No data loaded")
        self.statusBar().addPermanentWidget(self.status_label)

        # ── Auto-load on startup ──
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self._load_default)

    def _distribute_data(self):
        """Push data to all tabs."""
        self.frame_view.set_data(self.dm)
        self.id_overview.set_data(self.dm)
        self.signal_plotter.set_data(self.dm)
        self.payload_analysis.set_data(self.dm)
        self.data_flow.set_data(self.dm)
        self.hex_matrix.set_data(self.dm)

        n = len(self.dm.df)
        nids = len(self.dm.can_ids)
        t0, t1 = self.dm.time_range
        self.status_label.setText(
            f"{n:,} frames | {nids} CAN IDs | {t0:.1f} - {t1:.1f} s | "
            f"Sources: {', '.join(self.dm.sources)}"
        )
        self.setWindowTitle(
            f"{APP_NAME} v{APP_VERSION}  [{n:,} frames, {nids} IDs]"
        )

    def _load_default(self):
        self.statusBar().showMessage("Loading MF4 files from default directory...")
        QApplication.processEvents()
        try:
            self.dm.load_default()
            if self.dm.is_loaded:
                self._distribute_data()
                self.statusBar().showMessage("Data loaded successfully.", 3000)
            else:
                self.statusBar().showMessage(
                    "No data found. Use File > Open to load MF4 files.", 5000
                )
        except Exception as e:
            self.statusBar().showMessage(f"Load error: {e}", 5000)

    def _open_directory(self):
        d = QFileDialog.getExistingDirectory(self, "Select MF4 Directory")
        if d:
            self.statusBar().showMessage(f"Loading from {d}...")
            QApplication.processEvents()
            try:
                self.dm.load_directory(d)
                if self.dm.is_loaded:
                    self._distribute_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load:\n{e}")

    def _open_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open MF4 File", "",
                                            "MF4 Files (*.mf4 *.MF4);;All (*)")
        if f:
            self.statusBar().showMessage(f"Loading {f}...")
            QApplication.processEvents()
            try:
                self.dm.load_file(f)
                if self.dm.is_loaded:
                    self._distribute_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load:\n{e}")

    def _open_csv(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open CSV", "",
                                            "CSV Files (*.csv);;All (*)")
        if f:
            try:
                self.dm.load_csv(f)
                if self.dm.is_loaded:
                    self._distribute_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load CSV:\n{e}")

    def _about(self):
        QMessageBox.about(self, "About CAN Analyzer",
            f"<h2>{APP_NAME} v{APP_VERSION}</h2>"
            "<p>SavvyCAN-like CAN Bus Analysis Tool for MF4 Files</p>"
            "<p>Bachelor Thesis - VW ID Buzz</p>"
            "<hr>"
            "<p>Built with PyQt5, pyqtgraph, matplotlib, asammdf</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Sniffer - Browse & filter CAN frames</li>"
            "<li>ID Analysis - Per-ID statistics & charts</li>"
            "<li>Signal Plotter - Interactive byte plotting</li>"
            "<li>Payload Analysis - Bit heatmap & distributions</li>"
            "<li>Flow Analysis - Timing & message rates</li>"
            "<li>Hex Matrix - Live byte value view</li>"
            "</ul>"
        )


# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

def main():
    # Enable High DPI scaling
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_QSS)

    window = CANAnalyzer()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
