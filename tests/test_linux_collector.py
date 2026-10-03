# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from osu_diff.game_collection import collect_and_pack, discover_games, inspect_game
from osu_diff.bundle import verify_bundle
from osu_diff.machine import collection_machine
from tests.samples import BEATMAP, replay


class LinuxCollectorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.addCleanup(patch.stopall)
        patch("sys.platform", "linux").start()
        patch("pathlib.Path.home", return_value=self.root).start()
        patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data"),
                                "WINEPREFIX": str(self.root / "wine")}).start()

    def test_discover_native_flatpak_wine_and_redirected_lazer(self):
        native = self.root / "data/osu"
        native.mkdir(parents=True)
        (native / "storage.ini").write_text('FullPath = "../moved"\n')
        moved = self.root / "data/moved"
        (moved / "files").mkdir(parents=True)
        flatpak = self.root / ".var/app/sh.ppy.osu/data/osu"
        (flatpak / "files").mkdir(parents=True)
        stable = self.root / "wine/drive_c/users/player/AppData/Local/osu!"
        (stable / "Songs").mkdir(parents=True)
        found = discover_games(registry_paths=[], installed_apps=[])
        self.assertEqual({game["path"] for game in found},
                         {str(path.resolve()) for path in (moved, flatpak, stable)})

    def test_wine_absolute_and_relative_beatmap_paths(self):
        stable = self.root / "wine/drive_c/osu!"
        stable.mkdir(parents=True)
        config = stable / "osu!.cfg"
        config.write_text("BeatmapDirectory = C:\\maps\\Songs\n")
        self.assertEqual(inspect_game(stable)["maps"], str((self.root / "wine/drive_c/maps/Songs").resolve()))
        config.write_text("BeatmapDirectory = custom\\Songs\n")
        self.assertEqual(inspect_game(stable)["maps"], str((stable / "custom/Songs").resolve()))

    def test_machine_id_fallback_and_fail_closed(self):
        with patch("pathlib.Path.read_text", side_effect=[FileNotFoundError(), "a" * 32]):
            identity = collection_machine()
        self.assertEqual(identity["scheme"], "linux-machine-id-hmac-sha256-v1")
        with patch("pathlib.Path.read_text", return_value="A" * 32 + "\n"):
            self.assertEqual(collection_machine(), identity)
        for invalid in ("", "uninitialized", "0" * 32, "bad-id"):
            with patch("pathlib.Path.read_text", return_value=invalid):
                with self.assertRaises(ValueError):
                    collection_machine()

    def test_linux_identity_survives_stable_lazer_pack_and_verify(self):
        # Only substitute the machine-id read, leaving game/config reads real.
        read_text = Path.read_text
        raw_id = "1234567890abcdef1234567890abcdef"
        def read(path, *args, **kwargs):
            if str(path).replace("\\", "/") == "/etc/machine-id":
                return raw_id
            return read_text(path, *args, **kwargs)
        identities = []
        with patch.object(Path, "read_text", read):
            for client in ("stable", "lazer"):
                game = self.root / client
                for name, content in (("Songs/map.osu", BEATMAP), ("Data/r/play.osr", replay())):
                    target = game / ("files/" + Path(name).name if client == "lazer" else name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                result = collect_and_pack(game, self.root / (client + "-output"))
                manifest = verify_bundle(result["archive_path"])
                identities.append(manifest["collection_machine"])
                with zipfile.ZipFile(result["archive_path"]) as package:
                    for name in ("manifest.json", "inventory.json", "collection-log.json"):
                        text = package.read(name).decode()
                        self.assertNotIn(raw_id, text)
                        self.assertEqual(json.loads(text)["collection_machine"], identities[-1])
        self.assertEqual(identities[0], identities[1])

    def test_linux_multi_client_identity_is_stable_across_modes_outputs_and_runs(self):
        read_text = Path.read_text
        raw_id = "1234567890abcdef1234567890abcdef"

        def read(path, *args, **kwargs):
            if str(path).replace("\\", "/") == "/etc/machine-id":
                return raw_id
            return read_text(path, *args, **kwargs)

        games = []
        for client in ("stable", "lazer"):
            game = self.root / client
            for name, content in (("Songs/map.osu", BEATMAP), ("Data/r/play.osr", replay())):
                target = game / ("files/" + Path(name).name if client == "lazer" else name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            games.append(game)
        identities, batches = [], []
        with patch.object(Path, "read_text", read):
            for index, mode in enumerate(("combined", "separate", "combined", "separate")):
                result = collect_and_pack(games, self.root / f"output-{index}", package_mode=mode)
                self.assertEqual(len(result["parts"]), 1 if mode == "combined" else 2)
                batch = []
                for archive in result["parts"]:
                    manifest = verify_bundle(archive)
                    identities.append(manifest["collection_machine"])
                    self.assertEqual(identities[-1]["scheme"], "linux-machine-id-hmac-sha256-v1")
                    batch.append(manifest["collection_batch_id"])
                    with zipfile.ZipFile(archive) as package:
                        for name in ("manifest.json", "inventory.json", "collection-log.json"):
                            self.assertNotIn(raw_id, package.read(name).decode())
                self.assertEqual(len(set(batch)), 1)
                batches.append(batch[0])
            self.assertTrue(all(identity == identities[0] for identity in identities))
            self.assertEqual(len(set(batches)), 4)
            raw_id = "abcdef1234567890abcdef1234567890"
            changed = collect_and_pack(games, self.root / "other-system")
            self.assertNotEqual(changed["collection_machine"]["id"], identities[0]["id"])

    @unittest.skipUnless(os.name != "nt", "POSIX XDG configuration")
    def test_settings_use_xdg_config_home_and_reject_relative_override(self):
        from osu_diff.local_settings import settings_path
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")}):
            self.assertEqual(settings_path("collector"), self.root / "config/osu-diff/collector.json")
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "relative"}):
            self.assertEqual(settings_path("collector"), self.root / ".config/osu-diff/collector.json")
