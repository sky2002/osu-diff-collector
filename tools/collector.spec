# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002
# PyInstaller executes this file; SPECPATH points at tools/.
import os
import sys
from pathlib import Path

root = Path(SPECPATH).parent
sys.path.insert(0, str(root / "tools"))
from runtime_licenses import collect_notices

analysis = Analysis([str(root / "tools/collector_entry.py")], pathex=[str(root)],
                    binaries=[], datas=[], hiddenimports=[], hookspath=[],
                    runtime_hooks=[], excludes=[], noarchive=False)
legal = collect_notices(root, analysis.binaries, Path(workpath) / "licenses")
for path in sorted(legal.rglob("*")):
    if path.is_file():
        analysis.datas.append(("licenses/" + path.relative_to(legal).as_posix(), str(path), "DATA"))
pyz = PYZ(analysis.pure)
if sys.platform == "win32":
    exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas, [],
              name="osu-diff-collector", console=True, hide_console="hide-early", upx=False)
else:
    exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
              name="osu-diff-collector", console=True, upx=False)
    coll = COLLECT(exe, analysis.binaries, analysis.datas, name="osu-diff-collector", upx=False)
