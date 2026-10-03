# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

import hashlib
import json
import lzma
import os
import struct
import tempfile
import unittest
from pathlib import Path

from tests.samples import BEATMAP, replay


class GameFolderImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    @unittest.skipUnless(os.name == "nt", "Windows registry identity")
    def test_stable_and_lazer_packages_share_machine_id_across_output_locations(self):
        import winreg
        import zipfile
        from unittest.mock import patch
        from osu_diff.game_collection import collect_and_pack

        machine_guid = "11111111-2222-4333-8444-555555555555"
        identities = []
        for client in ("stable", "lazer"):
            game = self.root / client
            for index, content in enumerate([BEATMAP, replay()]):
                path = game / (f"files/{index}" if client == "lazer" else
                               ("Songs/map.osu" if index == 0 else "Data/r/play.osr"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            with patch("winreg.QueryValueEx", return_value=(machine_guid, winreg.REG_SZ)):
                result = collect_and_pack(game, self.root / (client + "-output"))
            with zipfile.ZipFile(result["archive_path"]) as package:
                manifest = json.loads(package.read("manifest.json"))
                identity = manifest["collection_machine"]
                self.assertRegex(identity["id"], r"^pc-[0-9a-f]{64}$")
                self.assertEqual(identity["scheme"], "windows-machineguid-sha256-v1")
                self.assertEqual(identity["assurance"], "self_reported")
                for name in ("manifest.json", "inventory.json", "collection-log.json"):
                    text = package.read(name).decode("utf-8")
                    self.assertEqual(json.loads(text)["collection_machine"], identity)
                    self.assertNotIn(machine_guid, text)
                identities.append(identity)
        self.assertEqual(identities[0], identities[1])

    def test_one_click_leaves_one_zip_including_data_inventory_and_log_even_over_64_mib(self):
        import zipfile
        from osu_diff.game_collection import collect_and_pack

        game = self.root / "stable"
        (game / "Songs").mkdir(parents=True)
        (game / "Data/r").mkdir(parents=True)
        (game / "Songs/map.osu").write_bytes(BEATMAP)
        with (game / "Data/r/play.osr").open("wb") as stream:
            stream.write(replay())
            stream.seek(65 * 1024 * 1024)
            stream.write(b"\0")
        output = self.root / "output"
        result = collect_and_pack(game, output)
        self.assertEqual(len(result["parts"]), 1)
        archive = Path(result["parts"][0])
        self.assertEqual(list(output.iterdir()), [archive])
        with zipfile.ZipFile(archive) as package:
            manifest = json.loads(package.read("manifest.json"))
            inventory = json.loads(package.read("inventory.json"))
            log = json.loads(package.read("collection-log.json"))
            self.assertEqual(manifest, inventory)
            self.assertEqual(log["collected_replays"], 1)
            self.assertEqual(len(manifest["objects"]), 2)
            for entry in manifest["objects"]:
                with package.open("objects/" + entry["sha256"]) as source:
                    self.assertEqual(hashlib.file_digest(source, "sha256").hexdigest(), entry["sha256"])

    def test_failed_pack_removes_only_its_scratch_files(self):
        from unittest.mock import patch
        from osu_diff.game_collection import collect_and_pack

        game = self.root / "stable"
        (game / "Songs").mkdir(parents=True)
        (game / "Data/r").mkdir(parents=True)
        (game / "Songs/map.osu").write_bytes(BEATMAP)
        recording = replay()
        (game / "Data/r/play.osr").write_bytes(recording)
        output = self.root / "output"
        output.mkdir()
        existing = output / "previous.zip"
        existing.write_bytes(b"existing archive")
        original_replace = Path.replace

        def fail_publish(path, target):
            if Path(target).suffix == ".zip":
                raise OSError("publish failed")
            return original_replace(path, target)

        for failure in (patch("zipfile.ZipFile.write", side_effect=OSError("write failed")),
                        patch.object(Path, "replace", fail_publish)):
            with self.subTest(failure=failure), failure:
                with self.assertRaises(OSError):
                    collect_and_pack(game, output, "donor-failure-test")
            self.assertEqual(list(output.iterdir()), [existing])
            self.assertEqual(existing.read_bytes(), b"existing archive")
            self.assertEqual((game / "Songs/map.osu").read_bytes(), BEATMAP)
            self.assertEqual((game / "Data/r/play.osr").read_bytes(), recording)

    def test_default_collection_only_copies_confirmed_native_mania_4k_pairs(self):
        from osu_diff.game_collection import collect_game

        seven = BEATMAP.replace(b"CircleSize:4", b"CircleSize:7")
        standard = BEATMAP.replace(b"Mode:3", b"Mode:0")
        valid = replay()
        excluded = [replay(map_hash=hashlib.md5(seven).hexdigest()),
                    b"\x00" + replay(map_hash=hashlib.md5(standard).hexdigest())[1:],
                    replay(map_hash=hashlib.md5(standard).hexdigest())]
        for client in ("stable", "lazer"):
            with self.subTest(client=client):
                game = self.root / client
                for index, content in enumerate([BEATMAP, seven, standard, valid, *excluded]):
                    path = (game / "files" / str(index) if client == "lazer" else
                            game / (f"Songs/{index}.osu" if index < 3 else f"Data/r/{index}.osr"))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                output = self.root / (client + "-output")
                result = collect_game(game, output, "donor")
                inventory = json.loads((output / "inventory.json").read_text())
                self.assertEqual({item["sha256"] for item in inventory["objects"]},
                                 {hashlib.sha256(BEATMAP).hexdigest(), hashlib.sha256(valid).hexdigest()})
                self.assertEqual(result["collected_replays"], 1)
                self.assertEqual(result["skipped_replays"]["out_of_scope"], 3)

    def test_key_count_and_coop_mods_are_filtered_without_filtering_identity_time_or_speed(self):
        from osu_diff.game_collection import collect_game

        game = self.root / "stable"
        (game / "Songs").mkdir(parents=True)
        (game / "Data/r").mkdir(parents=True)
        (game / "Songs/map.osu").write_bytes(BEATMAP)
        accepted = [replay(), replay(mods=32768), replay(mods=64), replay(mods=256),
                    replay(player="", ticks=0)]
        excluded = [replay(mods=mod) for mod in
                    (65536, 131072, 262144, 524288, 16777216, 33554432, 67108864,
                     134217728, 268435456, 32768 | 262144)]
        for index, content in enumerate(accepted + excluded):
            (game / f"Data/r/{index}.osr").write_bytes(content)
        output = self.root / "output"
        result = collect_game(game, output, "different-submitter")
        inventory = json.loads((output / "inventory.json").read_text())
        self.assertEqual({item["sha256"] for item in inventory["objects"] if item["kind"] == "replay"},
                         {hashlib.sha256(content).hexdigest() for content in accepted})
        self.assertEqual(result["skipped_replays"]["out_of_scope"], 10)

    def test_lazer_extension_mods_must_confirm_4k_even_when_legacy_flags_are_empty(self):
        from osu_diff.game_collection import collect_game

        def modern(mods):
            payload = lzma.compress(json.dumps({"mods": mods}).encode(), format=lzma.FORMAT_ALONE)
            return replay(version=30000019) + struct.pack("<i", len(payload)) + payload

        accepted = [modern([]), modern([{"acronym": "4K"}]),
                    modern([{"acronym": "DT", "settings": {"speed_change": 1.2}}])]
        excluded = [modern([{"acronym": "10K"}]), modern([{"acronym": "DS"}]),
                    modern([{"acronym": "7K"}])]
        unknown = [replay(version=30000019), modern([{"acronym": "FUTURE"}]),
                   modern(None), modern([])[:-6]]
        game = self.root / "lazer"
        for content in [BEATMAP, *accepted, *excluded, *unknown]:
            sha = hashlib.sha256(content).hexdigest()
            path = game / "files" / sha[0] / sha[:2] / sha
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        output = self.root / "output"
        result = collect_game(game, output, "donor")
        inventory = json.loads((output / "inventory.json").read_text())
        self.assertEqual({item["sha256"] for item in inventory["objects"] if item["kind"] == "replay"},
                         {hashlib.sha256(content).hexdigest() for content in accepted})
        self.assertEqual(result["skipped_replays"]["out_of_scope"], 3)
        self.assertEqual(result["skipped_replays"]["unverifiable"], 4)

    def test_stable_root_collects_local_and_exported_replays_with_only_corresponding_maps(self):
        from osu_diff.game_collection import collect_game

        game = self.root / "stable"
        for directory in ("Songs/map", "Data/r", "Replays"):
            (game / directory).mkdir(parents=True)
        (game / "Songs/map/exact.osu").write_bytes(BEATMAP)
        (game / "Songs/map/unplayed.osu").write_bytes(BEATMAP + b"\n// other map")
        (game / "Songs/map/audio.mp3").write_bytes(b"music")
        local = replay()
        exported = replay(ticks=638396640100000000)
        (game / "Data/r/local.osr").write_bytes(local)
        (game / "Replays/exported.osr").write_bytes(exported)
        output = self.root / "output"
        result = collect_game(game, output, "donor")
        inventory = json.loads((output / "inventory.json").read_text())
        self.assertEqual(result["client"], "stable")
        self.assertEqual(result["replays_found"], 2)
        self.assertEqual(result["matched_beatmaps"], 1)
        self.assertEqual({entry["sha256"] for entry in inventory["objects"]}, {
            hashlib.sha256(BEATMAP).hexdigest(), hashlib.sha256(local).hexdigest(),
            hashlib.sha256(exported).hexdigest()})
        self.assertFalse((output / "quality-report.json").exists())

    def test_lazer_collects_extensionless_file_store_without_copying_media_or_accounts(self):
        from osu_diff.game_collection import collect_game

        game = self.root / "lazer-data"
        game.mkdir()
        (game / "client.realm").write_bytes(b"private database not needed for raw capture")
        extension = lzma.compress(b'{"mods":[],"future_field":"kept"}', format=lzma.FORMAT_ALONE)
        raw_replay = replay(version=30000019) + struct.pack("<i", len(extension)) + extension
        for content in (BEATMAP, raw_replay, b"audio", BEATMAP + b"\n// unplayed"):
            sha = hashlib.sha256(content).hexdigest()
            path = game / "files" / sha[0] / sha[:2] / sha
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        output = self.root / "output"
        result = collect_game(game, output, "donor")
        inventory = json.loads((output / "inventory.json").read_text())
        self.assertEqual(result["client"], "lazer")
        self.assertEqual(result["replays_found"], 1)
        self.assertEqual(len(inventory["objects"]), 2)
        entry = next(item for item in inventory["objects"] if item["kind"] == "replay")
        self.assertEqual((output / "data" / "objects" / entry["sha256"]).read_bytes(), raw_replay)
        self.assertEqual(result["missing_beatmap_hashes"], [])

    def test_stable_follows_custom_song_location_from_config(self):
        from osu_diff.game_collection import collect_game

        game = self.root / "stable"
        (game / "Data/r").mkdir(parents=True)
        songs = self.root / "custom-songs"
        songs.mkdir()
        (game / "osu!.cfg").write_text(f"BeatmapDirectory = {songs}\n", encoding="utf-8")
        (game / "Data/r/play.osr").write_bytes(replay())
        (songs / "map.osu").write_bytes(BEATMAP)
        result = collect_game(game, self.root / "output", "donor")
        self.assertEqual(result["matched_beatmaps"], 1)
        self.assertEqual(result["missing_beatmap_hashes"], [])

    def test_lazer_program_folder_resolves_moved_data_and_automatic_discovery(self):
        from osu_diff.game_collection import discover_games, inspect_game

        appdata = self.root / "roaming"
        (appdata / "osu").mkdir(parents=True)
        moved = self.root / "moved-lazer"
        (moved / "files").mkdir(parents=True)
        (moved / "client.realm").write_bytes(b"not read")
        (appdata / "osu/storage.ini").write_text(f"FullPath = {moved}\n", encoding="utf-8")
        program = self.root / "program"
        (program / "current").mkdir(parents=True)
        (program / "current/osu.Game.dll").write_bytes(b"marker only")
        found = inspect_game(program, appdata=appdata)
        self.assertEqual(found["client"], "lazer")
        self.assertEqual(found["path"], str(moved.resolve()))
        self.assertEqual(discover_games(appdata=appdata, localappdata=self.root / "local", registry_paths=[], installed_apps=[]), [found])

    def test_windows_installed_apps_locations_discover_nondefault_stable_install(self):
        from osu_diff.game_collection import discover_games

        install = self.root / "Games/osu stable"
        (install / "Songs").mkdir(parents=True)
        records = [{"DisplayName": "osu!", "InstallLocation": str(install)},
                   {"DisplayName": "osu!", "DisplayIcon": f'"{install / "osu!.exe"}",0'},
                   {"DisplayName": "Different game", "InstallLocation": str(self.root)}]
        found = discover_games(appdata=self.root / "roaming", localappdata=self.root / "local",
                               registry_paths=[], installed_apps=records)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["client"], "stable")
        self.assertEqual(found[0]["path"], str(install.resolve()))

    def test_one_step_collection_builds_share_packages_and_reports_missing_maps(self):
        from osu_diff.game_collection import collect_and_pack

        game = self.root / "stable"
        (game / "Data/r").mkdir(parents=True)
        (game / "Songs").mkdir()
        (game / "Data/r/play.osr").write_bytes(replay())
        output = self.root / "output"
        result = collect_and_pack(game, output)
        self.assertEqual(result["replays_found"], 1)
        self.assertEqual(result["missing_beatmap_hashes"], [hashlib.md5(BEATMAP).hexdigest()])
        self.assertEqual(len(result["parts"]), 1)
        self.assertEqual(result["skipped_replays"]["missing_beatmap"], 1)
        self.assertTrue(result["submitter_id"].startswith("donor-"))
        (game / "Songs/map.osu").write_bytes(BEATMAP)
        self.assertEqual(len(collect_and_pack(game, output)["parts"]), 1)
        repeated = collect_and_pack(game, output)
        self.assertEqual(repeated["submitter_id"], result["submitter_id"])
        self.assertEqual(repeated["counts"]["duplicate"], 0)

    def test_share_package_carries_generated_submitter_code_without_machine_paths(self):
        import zipfile
        from osu_diff.game_collection import collect_and_pack

        game = self.root / "stable"
        (game / "Data/r").mkdir(parents=True)
        (game / "Songs").mkdir()
        (game / "Songs/map.osu").write_bytes(BEATMAP)
        (game / "Data/r/play.osr").write_bytes(replay())
        result = collect_and_pack(game, self.root / "output")
        with zipfile.ZipFile(result["parts"][0]) as package:
            manifest = json.loads(package.read("manifest.json"))
        self.assertEqual(manifest["submission_id"], result["submitter_id"])
        self.assertNotIn(str(self.root), json.dumps(manifest))

    def test_command_line_collects_a_game_root_and_finishes_the_share_package(self):
        import subprocess
        import sys

        game = self.root / "stable"
        (game / "Data/r").mkdir(parents=True)
        (game / "Songs").mkdir()
        (game / "Songs/map.osu").write_bytes(BEATMAP)
        (game / "Data/r/play.osr").write_bytes(replay())
        completed = subprocess.run([sys.executable, "-m", "osu_diff", "collect-game", str(game),
                                    "--output", str(self.root / "output")],
                                   capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["client"], "stable")
        self.assertEqual(len(result["parts"]), 1)

    def test_unverifiable_replays_and_maps_produce_a_log_only_zip(self):
        import zipfile
        from osu_diff.game_collection import collect_and_pack

        game = self.root / "stable"
        (game / "Data/r").mkdir(parents=True)
        (game / "Songs").mkdir()
        (game / "Data/r/broken.osr").write_bytes(b"unknown format")
        for index, content in enumerate([BEATMAP.replace(b"CircleSize:4", b"// no keys"),
                                         BEATMAP.replace(b"CircleSize:4", b"CircleSize:bad")]):
            (game / f"Songs/{index}.osu").write_bytes(content)
            (game / f"Data/r/{index}.osr").write_bytes(replay(map_hash=hashlib.md5(content).hexdigest()))
        # Seed an older raw collection to ensure a no-match run cannot share stale files.
        from osu_diff.collector import collect_submission
        output = self.root / "output"
        collect_submission([game], output, "donor")
        result = collect_and_pack(game, output)
        self.assertEqual(len(result["parts"]), 1)
        self.assertEqual(result["collected_replays"], 0)
        self.assertEqual(result["skipped_replays"]["unverifiable"], 3)
        with zipfile.ZipFile(result["parts"][0]) as package:
            self.assertEqual(json.loads(package.read("manifest.json"))["objects"], [])
            self.assertEqual(json.loads(package.read("collection-log.json"))["skipped_replays"]["unverifiable"], 3)
            self.assertEqual(set(package.namelist()), {"manifest.json", "inventory.json", "collection-log.json"})

    def test_reusing_old_collection_only_shares_current_4k_pairs_in_a_separate_zip(self):
        import zipfile
        from osu_diff.collector import collect_submission, pack_submission
        from osu_diff.game_collection import collect_and_pack

        game = self.root / "stable"
        (game / "Songs").mkdir(parents=True)
        (game / "Data/r").mkdir(parents=True)
        seven = BEATMAP.replace(b"CircleSize:4", b"CircleSize:7")
        (game / "Songs/seven.osu").write_bytes(seven)
        (game / "Data/r/seven.osr").write_bytes(replay(map_hash=hashlib.md5(seven).hexdigest()))
        output = self.root / "output"
        collect_submission([game], output, "donor")
        old_parts = pack_submission(output)
        (game / "Songs/four.osu").write_bytes(BEATMAP)
        (game / "Data/r/four.osr").write_bytes(replay())
        (game / "Data/r/four-copy.osr").write_bytes(replay())
        result = collect_and_pack(game, output)
        with zipfile.ZipFile(result["parts"][0]) as package:
            manifest = json.loads(package.read("manifest.json"))
            self.assertEqual({item["sha256"] for item in manifest["objects"]},
                             {hashlib.sha256(BEATMAP).hexdigest(), hashlib.sha256(replay()).hexdigest()})
        self.assertEqual(result["collected_replays"], 2)
        self.assertEqual(result["counts"]["duplicate"], 1)
        self.assertEqual(set(Path(result["share_directory"]).glob("*.zip")),
                         {Path(part) for part in result["parts"]})
        self.assertNotEqual(Path(old_parts[0]).parent, Path(result["share_directory"]))
        self.assertTrue(Path(old_parts[0]).exists())
