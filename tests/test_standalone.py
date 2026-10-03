# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from osu_diff.cli import main
from osu_diff.game_collection import collect_and_pack
from tests.samples import BEATMAP, replay


class StandaloneTests(unittest.TestCase):
    def test_runtime_has_no_research_or_network_modules(self):
        code = """
import sys
import osu_diff.cli
import osu_diff.gui
for name in ('dataset', 'judgement', 'stable_judgement', 'lazer_judgement',
             'lazer_replay', 'inbox_client', 'inbox_server', 'downloader'):
    assert 'osu_diff.' + name not in sys.modules, name
"""
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_verify_cli_accepts_valid_export_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            game = root / "game"
            (game / "Songs").mkdir(parents=True)
            (game / "Data/r").mkdir(parents=True)
            (game / "Songs/map.osu").write_bytes(BEATMAP)
            (game / "Data/r/play.osr").write_bytes(replay())
            export = collect_and_pack(game, root / "output")
            archive = Path(export["archive_path"])
            result = subprocess.run([sys.executable, "-m", "osu_diff", "verify", str(archive)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)["objects"]), 2)
            archive.write_bytes(b"invalid ZIP")
            result = subprocess.run([sys.executable, "-m", "osu_diff", "verify", str(archive)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
