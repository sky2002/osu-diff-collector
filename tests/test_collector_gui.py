# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

import gc
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from osu_diff.gui import CollectorWindow
from tests.samples import BEATMAP, replay


class CollectorGuiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.discovered = []
        for client in ("stable", "lazer"):
            game = self.directory / client
            for relative, content in (("files/map" if client == "lazer" else "Songs/map.osu", BEATMAP),
                                      ("files/play" if client == "lazer" else "Data/r/play.osr", replay())):
                path = game / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            self.discovered.append({"client": client, "path": str(game)})
        for name, value in (("discover_games", self.discovered), ("load_settings", {}),
                            ("collector_submission_id", "donor-gui-test"), ("save_settings", None)):
            mock = patch("osu_diff.gui." + name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.root.withdraw()
        self.window = CollectorWindow(self.root)
        self.addCleanup(self.close_window)
        self.window.detect_games()
        self.window.output.set(str(self.directory / "output"))

    def close_window(self):
        self.window.close()
        self.window = None
        self.root = None
        # Finalise Tk objects here, not during a later test's worker-thread GC.
        gc.collect()

    def export(self):
        with patch("osu_diff.gui.messagebox.showerror") as error:
            self.window.collect()
            self.assertTrue(self.window.busy)
            deadline = time.monotonic() + 10
            while self.window.busy and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.01)
            self.assertFalse(self.window.busy, "export worker did not finish")
            error.assert_not_called()
        text = self.window.log.get("1.0", "end")
        self.assertNotIn("操作失败", text)
        return text

    def test_discovery_selects_both_and_gui_exports_combined_then_separate(self):
        self.assertTrue(all(value.get() for value in self.window.enabled.values()))
        self.assertEqual(self.window.package_mode.get(), "combined")
        self.assertIn("已生成 1 个 ZIP", self.export())
        self.assertEqual(len(list((self.directory / "output").glob("*.zip"))), 1)
        self.window.package_mode.set("separate")
        self.assertIn("已生成 2 个 ZIP", self.export())
        self.assertEqual(len(list((self.directory / "output").glob("*.zip"))), 3)

    def test_unchecked_client_is_not_exported_and_rediscovery_keeps_choice(self):
        self.window.enabled["lazer"].set(False)
        self.window.detect_games()
        self.assertFalse(self.window.enabled["lazer"].get())
        self.window.package_mode.set("separate")
        self.assertIn("已生成 1 个 ZIP", self.export())
        self.assertNotIn("lazer：", self.window.log.get("1.0", "end"))

    def test_wrong_client_directory_is_rejected_before_export(self):
        self.window.game_paths["lazer"].set(str(self.directory / "stable"))
        with patch("osu_diff.gui.messagebox.showerror") as error:
            self.window.collect()
        error.assert_called_once()
        self.assertIn("实际属于 stable", error.call_args.args[1])
        self.assertFalse(self.window.busy)
        self.assertFalse((self.directory / "output").exists())

    def test_ui_has_no_upload_controls_or_network_client_dependency(self):
        def labels(widget):
            if "text" in widget.keys():
                yield str(widget.cget("text"))
            for child in widget.winfo_children():
                yield from labels(child)

        text = "\n".join(labels(self.root))
        self.assertNotIn("上传", text)
        self.assertNotIn("续传", text)
        completed = subprocess.run([sys.executable, "-c",
                                    "import sys; import osu_diff.gui; assert 'osu_diff.inbox_client' not in sys.modules"],
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
