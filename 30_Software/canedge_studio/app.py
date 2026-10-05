"""CANedge Studio - a desktop app for the thesis logger.

  Logger tab : is the CANedge SD card in? Which config is on it, which one did the logger run?
               Pick a config, see exactly which UDS signals it asks the car for, write it to the card.
  Logs tab   : open an MF4 log (or a session straight from the card) and see every decoded signal.

Built into a normal Windows program with build_exe.ps1; no Python commands needed to use it.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import webview

import canedge_config as C
import uds_decode as U

APP = "CANedge Studio"
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
SETTINGS = Path(os.environ.get("APPDATA", Path.home())) / APP / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(s: dict):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=2), encoding="utf-8")


class Api:
    """Every method is callable from the page as window.pywebview.api.<name>(...)."""

    def __init__(self):
        self.window = None
        self.settings = load_settings()
        project = self.settings.get("project")
        if not (project and C.set_project(project)) and not C.CONFIG_DIR.is_dir():
            bundled = HERE / "vw_meb_uds_pid_list.csv"        # the installed exe still knows the PID list
            if bundled.is_file():
                C.PID_CSV = bundled
        self.pids_cfg = self.pids_dec = None
        self.last_result = None
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ helpers
    def _pids(self):
        if self.pids_cfg is None:
            self.pids_cfg, self.pids_dec = C.load_pid_list(C.PID_CSV), U.load_pids(C.PID_CSV)
        return self.pids_cfg, self.pids_dec

    def _local_crcs(self):
        return {C.crc32_of(p): p.parent.name for p in C.local_configs()} if C.CONFIG_DIR.is_dir() else {}

    def _extra_roots(self):
        return [r for r in self.settings.get("extra_cards", []) if Path(r).is_dir()]

    # ------------------------------------------------------------------ logger tab
    def state(self):
        pids, _ = self._pids()
        configs = []
        if C.CONFIG_DIR.is_dir():
            configs = [C.summary(p, pids) for p in C.local_configs()]
        return {"project": str(C.PROJECT), "config_dir_ok": C.CONFIG_DIR.is_dir(), "pid_count": len(pids),
                "cards": C.find_cards(self._extra_roots(), self._local_crcs()), "configs": configs}

    def cards(self):
        return C.find_cards(self._extra_roots(), self._local_crcs())

    def config_detail(self, path, card_root=None):
        pids, _ = self._pids()
        a = C.analyse(json.loads(Path(path).read_text(encoding="utf-8")), pids)
        a["file"], a["path"], a["crc32"] = Path(path).parent.name, path, C.crc32_of(path)
        a["title"], a["about"] = C.describe(Path(path).parent)
        if card_root and (Path(card_root) / C.CARD_CONFIG).is_file():         # what changes if we write this one
            card = C.analyse(json.loads((Path(card_root) / C.CARD_CONFIG).read_text(encoding="utf-8")), pids)
            mine = {(r["ecu"], r["did"]) for r in a["rows"] if r["did"]}
            theirs = {(r["ecu"], r["did"]) for r in card["rows"] if r["did"]}
            a["vs_card"] = {"added": len(mine - theirs), "removed": len(theirs - mine), "same": a["crc32"] == C.crc32_of(Path(card_root) / C.CARD_CONFIG)}
        return a

    def import_card_config(self, card_root):
        """The card holds a config no local profile matches: keep it as a new profile folder."""
        root = Path(card_root)
        src = root / C.CARD_CONFIG
        dev = json.loads((root / "device.json").read_text(encoding="utf-8"))
        dst = C.PROFILES_DIR / f"from_card_{dev.get('id', 'card').lower()}_{C.crc32_of(src).lower()}"
        try:
            json.loads(src.read_text(encoding="utf-8"))
            dst.mkdir(parents=True, exist_ok=True)
            for f in C.CARD_FILES:
                if (root / f).is_file() and not (dst / f).exists():
                    (dst / f).write_bytes((root / f).read_bytes())
            if not (dst / "README.md").exists():
                (dst / "README.md").write_text(
                    f"# From card {dev.get('id', '')}\n\nCopied from the SD card of logger {dev.get('id', '')}; "
                    "it matched no other profile. Describe here what it is for.\n", encoding="utf-8")
            return {"ok": True, "file": dst.name, "path": str(dst / C.CARD_CONFIG)}
        except (OSError, ValueError) as e:
            return {"ok": False, "error": str(e)}

    def card_config_detail(self, card_root):
        return self.config_detail(str(Path(card_root) / C.CARD_CONFIG))

    def deploy(self, card_root, path):
        try:
            return {"ok": True, **C.deploy(card_root, Path(path))}
        except (OSError, ValueError) as e:
            return {"ok": False, "error": str(e)}

    def card_sessions(self, card_root):
        dev = json.loads((Path(card_root) / "device.json").read_text(encoding="utf-8"))
        log = Path(card_root) / "LOG" / dev.get("id", "")
        out = []
        if log.is_dir():
            for d in sorted((p for p in log.iterdir() if p.is_dir()), reverse=True):
                files = sorted(d.glob("*.MF4")) + sorted(d.glob("*.mf4"))
                if files:
                    out.append({"session": d.name, "path": str(d), "files": len(files),
                                "mb": round(sum(f.stat().st_size for f in files) / 1e6, 2),
                                "modified": max(f.stat().st_mtime for f in files)})
        return out

    def choose_project(self):
        r = self.window.create_file_dialog(webview.FileDialog.FOLDER, directory=str(C.PROJECT))
        if r and C.set_project(r[0]):
            self.settings["project"] = r[0]
            save_settings(self.settings)
            self.pids_cfg = None
            return True
        return False

    def add_card_folder(self):
        """For a card copied to the PC (or a reader Windows reports oddly): treat a folder as a card."""
        r = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        if r and (Path(r[0]) / "device.json").is_file():
            self.settings.setdefault("extra_cards", [])
            if r[0] not in self.settings["extra_cards"]:
                self.settings["extra_cards"].append(r[0])
                save_settings(self.settings)
            return r[0]
        return None

    def open_path(self, path):
        os.startfile(path) if sys.platform == "win32" else None

    # ------------------------------------------------------------------ logs tab
    def pick_logs(self):
        r = self.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                           file_types=("CANedge logs (*.MF4;*.mf4)", "All files (*.*)"))
        return list(r) if r else []

    def pick_session_folder(self):
        r = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        if not r:
            return []
        return [str(p) for p in sorted(Path(r[0]).rglob("*")) if p.suffix.lower() == ".mf4"]

    def session_files(self, folder):
        return [str(p) for p in sorted(Path(folder).glob("*")) if p.suffix.lower() == ".mf4"]

    def decode(self, paths):
        _, pids = self._pids()
        with self.lock:
            try:
                r = U.decode_log([Path(p) for p in paths], pids, C.ECUS)
            except Exception as e:            # a broken or foreign file shouldn't kill the app
                return {"error": f"Couldn't read the log: {e}"}
            r["files"] = [Path(p).name for p in paths]
            r["source"] = str(Path(paths[0]).parent) if paths else ""
            self.last_result = r
            return r

    def export_csv(self):
        if not self.last_result:
            return None
        r = self.window.create_file_dialog(webview.FileDialog.SAVE, save_filename="decoded_signals.csv",
                                           file_types=("CSV (*.csv)",))
        if not r:
            return None
        path = r if isinstance(r, str) else r[0]
        U.export_csv(self.last_result, Path(path))
        return path


def main():
    api = Api()
    window = webview.create_window(APP, str(HERE / "ui" / "index.html"), js_api=api, width=1360, height=880,
                                   min_size=(1000, 640), background_color="#0F1419")
    api.window = window
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()
