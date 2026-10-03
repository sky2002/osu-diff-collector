# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Smoke-test every Linux package using synthetic games and a virtual display.

Run in Linux with xvfb, xauth, cpio, rpm, zstd and dpkg-deb installed.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from osu_diff.bundle import verify_bundle
from tests.samples import BEATMAP, replay


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, capture_output=True,
                          text=True, **kwargs).stdout


def main():
    release = ROOT / "dist/linux-x86_64"
    run("sha256sum", "-c", "SHA256SUMS", cwd=release)
    metadata = json.loads((release / "build-info.json").read_text())
    results = []
    binaries = set()
    with tempfile.TemporaryDirectory(prefix="osu-diff-release-test-") as temporary:
        work = Path(temporary)
        home = work / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / "data"),
                   XDG_CONFIG_HOME=str(home / "config"), WINEPREFIX=str(home / "wine"))
        for filename in metadata["packages"]:
            package = release / filename
            stage = work / filename
            stage.mkdir()
            if filename.endswith(".deb"):
                run("dpkg-deb", "-x", package, stage)
                binary = stage / "opt/osu-diff-collector/osu-diff-collector"
            elif filename.endswith(".rpm"):
                run("rpm", "-K", "--nosignature", package)
                archive = stage / "payload.cpio"
                with archive.open("wb") as stream:
                    subprocess.run(["rpm2cpio", str(package)], stdout=stream, check=True)
                with archive.open("rb") as stream:
                    subprocess.run(["cpio", "-id", "--quiet"], stdin=stream, cwd=stage, check=True)
                binary = stage / "opt/osu-diff-collector/osu-diff-collector"
            elif filename.endswith(".pkg.tar.zst"):
                run("tar", "--zstd", "-xf", package, "-C", stage)
                assert "arch = x86_64" in (stage / ".PKGINFO").read_text()
                binary = stage / "opt/osu-diff-collector/osu-diff-collector"
            elif filename.endswith(".AppImage"):
                run(package, "--appimage-extract", cwd=stage)
                binary = stage / "squashfs-root/usr/lib/osu-diff-collector/osu-diff-collector"
            else:
                run("tar", "-xzf", package, "-C", stage)
                binary = next(stage.glob("*/osu-diff-collector"))
            binaries.add(hashlib.sha256(binary.read_bytes()).hexdigest())
            legal = binary.parent / "_internal/licenses"
            assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (legal / "LICENSE").read_text()
            assert (legal / "runtime-inventory.json").is_file()
            assert list(legal.glob("*python*copyright.txt")), "Python runtime notice missing"
            from PyInstaller.archive.readers import CArchiveReader
            reader = CArchiveReader(binary)
            modules = reader.open_embedded_archive("PYZ.pyz").toc
            assert not any("osu_diff." + name in modules for name in
                           ("dataset", "judgement", "stable_judgement", "lazer_judgement",
                            "lazer_replay", "inbox_client", "inbox_server", "downloader"))
            assert "collect-game" in run(binary, "--help", env=env)
            assert json.loads(run(binary, "discover", env=env)) == []
            games, identities = [], []
            for client in ("stable", "lazer"):
                game = stage / client
                games.append(game)
                for index, data in enumerate((BEATMAP, replay())):
                    path = game / (f"files/{index}" if client == "lazer" else
                                   "Songs/map.osu" if index == 0 else "Data/r/play.osr")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                output = stage / (client + "-output")
                result = json.loads(run(binary, "collect-game", game, "--output", output, env=env))
                assert result["collected_replays"] == 1 and result["matched_beatmaps"] == 1
                manifest = verify_bundle(result["archive_path"])
                assert manifest["collection_machine"]["scheme"] == "linux-machine-id-hmac-sha256-v1"
                identities.append(manifest["collection_machine"])
                assert len(manifest["objects"]) == 2
                assert len(list(output.iterdir())) == 1
            batches = []
            for index, mode in enumerate(("combined", "separate", "combined", "separate")):
                output = stage / f"{mode}-output-{index}"
                result = json.loads(run(binary, "collect-game", *games, "--output", output,
                                        "--package-mode", mode, env=env))
                assert len(result["parts"]) == (1 if mode == "combined" else 2)
                assert set(output.iterdir()) == {Path(path) for path in result["parts"]}
                batch_ids = []
                for archive in result["parts"]:
                    manifest = verify_bundle(archive)
                    assert len(manifest["objects"]) == 2  # identical fixtures deduplicate
                    identities.append(manifest["collection_machine"])
                    batch_ids.append(manifest["collection_batch_id"])
                assert len(set(batch_ids)) == 1
                batches.append(batch_ids[0])
            assert all(identity == identities[0] for identity in identities)
            assert len(set(batches)) == 4
            gui = subprocess.run(["xvfb-run", "-a", "timeout", "4", str(binary)],
                                 capture_output=True, text=True, env=env)
            assert gui.returncode == 124, (filename, gui.returncode, gui.stderr)
            assert not gui.stderr.strip(), (filename, gui.stderr)
            if filename.endswith(".AppImage"):
                assert "collect-game" in run(package, "--appimage-extract-and-run", "--help", env=env)
            versions = set()
            for path in binary.parent.rglob("*"):
                if path.is_file():
                    with path.open("rb") as stream:
                        if stream.read(4) != b"\x7fELF":
                            continue
                    text = run("objdump", "-T", path)
                    versions.update(tuple(map(int, version.split(".")))
                                    for version in re.findall(r"GLIBC_(\d+\.\d+)", text))
            assert max(versions) <= (2, 36), versions
            results.append({"package": filename, "cli": "passed", "stable_lazer_collection": "passed",
                            "standalone_modules_and_license_notices": "passed",
                            "combined_and_separate_export": "passed", "stable_machine_id_across_runs": "passed",
                            "gui_xvfb": "passed", "max_glibc_symbol": ".".join(map(str, max(versions)))})
            print(filename + ": passed", flush=True)
        assert len(binaries) == 1, "Packages must contain the same tested executable"
    (release / "smoke-test-results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
