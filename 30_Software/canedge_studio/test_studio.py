"""python -m unittest test_studio   (from 30_Software/canedge_studio)"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

import canedge_config as C
import uds_decode as U

PIDS = U.load_pids(C.PID_CSV)
REQ, RESP = 0x17FC007B, 0x17FE007B
LOG13 = C.PROJECT / "40_Experiments/data/2026-04-09_sd_card_dump_2a73e1cc/LOG/2A73E1CC/00000013/00000001.MF4"


def frames(*rows):
    """rows: (t, can_id, tx, 'hex bytes')"""
    t, ids, data, tx = zip(*[(r[0], r[1], bytes.fromhex(r[3]).ljust(8, b"\xaa"), r[2]) for r in rows])
    return {"t": np.array(t, float), "id": np.array(ids, np.int64), "data": np.array([list(d) for d in data], np.uint8),
            "tx": np.array(tx, bool), "start": 0.0, "internal": 0}


class Decode(unittest.TestCase):
    def setUp(self):
        fr = frames(
            (0.0, REQ, True, "03 22 1E 33 55 55 55 55"), (0.01, RESP, False, "07 62 1E 33 3E 4A 00 52"),
            (0.1, REQ, True, "03 22 1E A0 55 55 55 55"), (0.11, RESP, False, "05 62 1E A0 0F FE"),
            (0.2, REQ, True, "03 22 1E 40 55 55 55 55"), (0.21, RESP, False, "05 62 1E 40 0B 5F"),
            (0.3, REQ, True, "03 22 1E 3D 55 55 55 55"), (0.31, RESP, False, "10 08 62 1E 3D 00 02 49"),
            (0.4, REQ, True, "03 22 12 34 55 55 55 55"), (0.41, RESP, False, "03 7F 22 31"),
            (0.5, REQ, True, "03 22 02 8C 55 55 55 55"),                                  # never answered
        )
        self.r = U.decode_frames(fr, PIDS, C.ECUS)
        self.by = {s["key"]: s for s in self.r["signals"]}

    def test_cell_extreme_uses_the_thesis_encoding(self):
        v = self.by["17FC007B:1E33.v"]
        self.assertAlmostEqual(v["last"], 0x3E4A / 4096, places=6)          # 3.8931 V, as in the thesis
        self.assertEqual(self.by["17FC007B:1E33"]["last"], 82.0)           # cell number from ZZ

    def test_0ffe_is_not_available_not_5_volts(self):
        s = self.by["17FC007B:1EA0"]
        self.assertEqual(s["status"], "not available (0x0FFE)")
        self.assertIsNone(s["last"])

    def test_cell_voltage_formula_and_cell_chart(self):
        self.assertAlmostEqual(self.by["17FC007B:1E40"]["last"], 0x0B5F / 1000 + 1)
        self.assertEqual([c["cell"] for c in self.r["cells"]], [1, 97])

    def test_truncated_negative_and_unanswered(self):
        self.assertEqual(self.by["17FC007B:1E3D"]["status"], "truncated (multi-frame)")
        self.assertEqual(self.by["17FC007B:1234"]["status"], "negative: request out of range")
        self.assertEqual(self.by["17FC007B:028C"]["status"], "never answered")
        self.assertEqual((self.r["requests"], self.r["negative"], self.r["truncated"]), (6, 1, 1))


class RealLog(unittest.TestCase):
    @unittest.skipUnless(LOG13.exists(), "thesis log not on this machine")
    def test_session_13_matches_the_recorded_results(self):
        r = U.decode_log([LOG13], PIDS, C.ECUS)
        by = {s["did"]: s for s in r["signals"]}
        self.assertEqual(by["0x028C"]["last"], 67.6)                      # SOC %
        self.assertEqual((by["0x1E3B"]["min"], by["0x1E3B"]["max"]), (368.0, 368.25))
        self.assertEqual(by["0x7448"]["last"], "driving")
        self.assertEqual(by["0x1E3D"]["status"], "truncated (multi-frame)")


class Configs(unittest.TestCase):
    def test_every_config_decodes_and_known_dids_have_names(self):
        for path in C.local_configs():
            a = C.analyse(json.loads(path.read_text(encoding="utf-8")), C.load_pid_list())
            self.assertGreater(a["frames"], 0, path.name)
            for row in a["rows"]:
                if row["did"] == "0x1E3B":
                    self.assertEqual(row["signal"]["name"], "HV Battery voltage")

    def test_frame_decoding(self):
        self.assertEqual(C.decode_frame("03221E3B55555555")["dids"], [0x1E3B])
        self.assertTrue(C.decode_frame("0210035555555555")["service"].startswith("DiagnosticSessionControl (extended)"))
        self.assertEqual(C.decode_frame("023E005555555555")["service"], "TesterPresent")

    def test_card_detection_crc_and_safe_deploy(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            local = C.PROFILES_DIR / "01_smoke_test" / "config-01.08.json"
            other = C.PROFILES_DIR / "06_thesis_selected_signals" / "config-01.08.json"
            shutil.copy(local, tmp / "config-01.08.json")
            (tmp / "device.json").write_text(json.dumps({"id": "TEST", "fw_ver": "01.08.01", "cfg_crc32": C.crc32_of(local)}))
            crcs = {C.crc32_of(p): p.parent.name for p in C.local_configs()}
            card = C.find_cards([tmp], crcs)[0]
            self.assertEqual((card["config_match"], card["booted_match"], card["pending"]),
                             ("01_smoke_test", "01_smoke_test", False))
            res = C.deploy(str(tmp), other)
            self.assertEqual(C.crc32_of(tmp / "config-01.08.json"), C.crc32_of(other))
            self.assertTrue((Path(res["backup"]) / "config-01.08.json").exists())       # the card's old config, kept
            self.assertEqual(C.crc32_of(tmp / "schema-01.08.json"), C.crc32_of(other.parent / "schema-01.08.json"))
            shutil.rmtree(res["backup"])
            card = C.find_cards([tmp], crcs)[0]
            self.assertTrue(card["pending"])                                 # new file, logger hasn't restarted yet
            with self.assertRaises(ValueError):
                C.deploy(str(tmp / "nope"), other)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
