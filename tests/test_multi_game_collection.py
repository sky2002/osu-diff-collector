# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

import hashlib
import io
import json
import lzma
import struct
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from osu_diff.bundle import verify_bundle
from osu_diff.game_collection import collect_and_pack
from tests.samples import BEATMAP, replay


class MultiGameCollectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stable = self.root / "stable"
        self.lazer = self.root / "lazer"
        extension = lzma.compress(b'{"mods":[]}', format=lzma.FORMAT_ALONE)
        self.stable_replay = replay()
        self.lazer_replay = replay(version=30000019) + struct.pack("<i", len(extension)) + extension
        for relative, content in (("stable/Songs/map.osu", BEATMAP),
                                  ("stable/Data/r/play.osr", self.stable_replay),
                                  ("lazer/files/map", BEATMAP),
                                  ("lazer/files/play", self.lazer_replay),
                                  ("lazer/exports/stable-copy.osr", self.stable_replay)):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.output = self.root / "output"

    def read_package(self, path):
        with zipfile.ZipFile(path) as package:
            manifest = json.loads(package.read("manifest.json"))
            self.assertEqual(manifest, json.loads(package.read("inventory.json")))
            for entry in manifest["objects"]:
                self.assertEqual(hashlib.sha256(package.read("objects/" + entry["sha256"])).hexdigest(),
                                 entry["sha256"])
            self.assertEqual(len(package.namelist()), 3 + len(manifest["objects"]))
            return manifest, json.loads(package.read("collection-log.json"))

    def test_combined_deduplicates_and_preserves_both_sources(self):
        result = collect_and_pack([self.stable, self.lazer], self.output)
        self.assertEqual(len(result["parts"]), 1)
        self.assertEqual(list(self.output.iterdir()), [Path(result["archive_path"])])
        manifest, log = self.read_package(result["archive_path"])
        self.assertEqual(len(manifest["objects"]), 3)
        self.assertEqual(manifest["collection_clients"], ["stable", "lazer"])
        self.assertEqual({source["client"] for source in log["sources"]}, {"stable", "lazer"})
        self.assertEqual(log["collected_replays"], 3)
        self.assertEqual(log["matched_beatmaps"], 1)
        self.assertEqual(log["counts"]["duplicate"], 2)
        for source in log["sources"]:
            self.assertTrue(set(source["selected_objects"]) <= {item["sha256"] for item in manifest["objects"]})
            self.assertEqual(source["collection_machine"], manifest["collection_machine"])
        self.assertEqual(verify_bundle(result["archive_path"]), manifest)

    def test_separate_packages_are_self_contained_and_share_machine_submission_and_batch(self):
        result = collect_and_pack([self.stable, self.lazer], self.output, package_mode="separate")
        self.assertEqual(len(result["parts"]), 2)
        self.assertEqual(set(self.output.iterdir()), {Path(path) for path in result["parts"]})
        manifests = []
        for path, client, expected in zip(result["parts"], ("stable", "lazer"), (2, 3)):
            manifest, log = self.read_package(path)
            manifests.append(manifest)
            self.assertIn(client, Path(path).name)
            self.assertEqual(manifest["collection_clients"], [client])
            self.assertEqual(len(manifest["objects"]), expected)
            self.assertEqual(log["client"], client)
            self.assertEqual([source["client"] for source in log["sources"]], [client])
            self.assertEqual(verify_bundle(path), manifest)
        for field in ("collection_machine", "submission_id", "collection_batch_id"):
            self.assertEqual(manifests[0][field], manifests[1][field])

    def test_single_client_and_duplicate_paths_still_make_one_package(self):
        result = collect_and_pack([self.stable, self.stable / ".." / "stable"], self.output,
                                  package_mode="separate")
        self.assertEqual(len(result["parts"]), 1)
        self.assertEqual(result["collected_replays"], 1)

    def test_empty_client_is_reported_in_both_modes(self):
        (self.lazer / "files/play").unlink()
        (self.lazer / "exports/stable-copy.osr").unlink()
        for mode in ("combined", "separate"):
            with self.subTest(mode=mode):
                result = collect_and_pack([self.stable, self.lazer], self.output / mode, package_mode=mode)
                self.assertEqual(result["sources"][1]["collected_replays"], 0)
                if mode == "separate":
                    manifest, log = self.read_package(result["parts"][1])
                    self.assertEqual(manifest["objects"], [])
                    self.assertEqual(log["collected_replays"], 0)

    def test_invalid_second_source_or_mode_does_not_create_partial_output(self):
        for paths, mode in (([self.stable, self.root / "missing"], "combined"),
                            ([self.stable], "invalid"), ([], "combined")):
            with self.subTest(paths=paths, mode=mode), self.assertRaises(ValueError):
                collect_and_pack(paths, self.output, package_mode=mode)
            self.assertFalse(self.output.exists())

    def test_second_package_failure_cleans_this_batch_and_preserves_existing_zip(self):
        self.output.mkdir()
        previous = self.output / "previous.zip"
        previous.write_bytes(b"keep me")
        original_write = zipfile.ZipFile.write
        original_replace = Path.replace

        def fail_second(package, *args, **kwargs):
            if "lazer" in package.filename:
                raise OSError("second package failed")
            return original_write(package, *args, **kwargs)

        def fail_second_publish(path, target):
            if Path(target).name.endswith("-lazer.zip"):
                raise OSError("second publish failed")
            return original_replace(path, target)

        for failure in (patch.object(zipfile.ZipFile, "write", fail_second),
                        patch.object(Path, "replace", fail_second_publish)):
            with self.subTest(failure=failure), failure, self.assertRaises(OSError):
                collect_and_pack([self.stable, self.lazer], self.output, package_mode="separate")
            self.assertEqual(list(self.output.iterdir()), [previous])
        self.assertEqual(previous.read_bytes(), b"keep me")
        self.assertEqual((self.stable / "Data/r/play.osr").read_bytes(), self.stable_replay)

    def test_cli_accepts_two_folders_and_split_option(self):
        from osu_diff.cli import main
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = main(["collect-game", str(self.stable), str(self.lazer), "--output", str(self.output),
                           "--package-mode", "separate"])
        self.assertEqual(status, 0)
        self.assertEqual(len(json.loads(stdout.getvalue())["parts"]), 2)
