# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Exercise an EXE/zipapp using only synthetic stable/lazer inputs."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from osu_diff import __version__
from osu_diff.bundle import verify_bundle
from tests.samples import BEATMAP, replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", type=Path)
    args = parser.parse_args()
    program = args.program.resolve(strict=True)
    command = [sys.executable, str(program)] if program.suffix == ".pyz" else [str(program)]

    def run(*arguments):
        return subprocess.run([*command, *map(str, arguments)], check=True, capture_output=True,
                              text=True, encoding="utf-8", timeout=60).stdout

    assert "collect-game" in run("--help")
    assert __version__ in run("--version")
    identities = []
    with tempfile.TemporaryDirectory(prefix="collector-smoke-") as temporary:
        root = Path(temporary).resolve()
        games = [root / client for client in ("stable", "lazer")]
        expected = {hashlib.sha256(data).hexdigest() for data in (BEATMAP, replay())}
        for game in games:
            for name, data in (("Songs/map.osu", BEATMAP), ("Data/r/play.osr", replay())):
                path = game / ("files/" + Path(name).name if game.name == "lazer" else name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        for index, mode in enumerate(("combined", "separate", "combined", "separate")):
            output = root / str(index)
            result = json.loads(run("collect-game", *games, "--output", output, "--package-mode", mode))
            assert len(result["parts"]) == (1 if mode == "combined" else 2)
            assert set(output.iterdir()) == {Path(path) for path in result["parts"]}
            for path in result["parts"]:
                manifest = verify_bundle(path)
                assert {item["sha256"] for item in manifest["objects"]} == expected
                assert json.loads(run("verify", path)) == manifest
                identities.append(manifest["collection_machine"])
        assert all(item == identities[0] for item in identities)
    print(program.name + ": CLI, combined/separate export, integrity, cleanup and stable machine ID passed")


if __name__ == "__main__":
    main()
