# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Collect notices for the actual PyInstaller binary dependencies.

Debian builds record each binary's owning package and copy its copyright file.
This is an inventory and notices step, not an automatic legal-compliance claim.
See docs/building.md before redistributing binaries or modified runtimes.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def collect_notices(root, binaries, output):
    output.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(root / name, output / name)
    for path in (root / "licenses").glob("*.txt"):
        shutil.copyfile(path, output / path.name)
    inventory = []
    if sys.platform == "win32":
        license_path = Path(sys.base_prefix) / "LICENSE.txt"
        if not license_path.is_file():
            raise RuntimeError("Build with the official python.org Windows distribution (LICENSE.txt missing)")
        shutil.copyfile(license_path, output / "Python-LICENSE.txt")
        for path in (Path(sys.base_prefix) / "tcl").glob("*/license.terms"):
            shutil.copyfile(path, output / (path.parent.name + "-license.terms"))
        inventory = [{"name": dest, "size": Path(source).stat().st_size} for dest, source, kind in binaries]
    else:
        packages = set()
        for dest, source, kind in binaries:
            path = Path(source)
            candidates = [str(path), str(path.resolve())]
            # Debian's merged-/usr layout may retain /lib paths in dpkg's index.
            candidates += [p[4:] for p in candidates if p.startswith("/usr/lib/")]
            owners = set()
            for candidate in dict.fromkeys(candidates):
                result = subprocess.run(["dpkg-query", "-S", candidate], capture_output=True, text=True)
                if result.returncode == 0:
                    owners.update(line.split(": ", 1)[0] for line in result.stdout.splitlines() if ": " in line)
            if not owners:
                raise RuntimeError("Cannot determine Debian package licensing for bundled binary: " + str(path))
            record = {"name": dest, "packages": sorted(owners)}
            inventory.append(record)
            packages.update(owners)
        for package in sorted(packages):
            name = package.split(":", 1)[0]
            copyright_path = Path("/usr/share/doc") / name / "copyright"
            if not copyright_path.is_file():
                raise RuntimeError("Missing package copyright file: " + package)
            shutil.copyfile(copyright_path, output / (name + "-copyright.txt"))
            metadata = subprocess.check_output(
                ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n", package],
                text=True)
            (output / (name + "-version.txt")).write_text(metadata, encoding="utf-8")
        common = Path("/usr/share/common-licenses")
        for path in common.iterdir():
            if path.is_file():
                shutil.copyfile(path, output / ("Debian-" + path.name + ".txt"))
    (output / "runtime-inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    return output
