# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Build the standalone Windows collector, including runtime license notices."""
import os
import subprocess
import sys
from pathlib import Path


def main():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows executable on Windows")
    root = Path(__file__).resolve().parents[1]
    build = root / "build"
    build.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(root / "dist"), "--workpath", str(build / "pyinstaller"),
                    str(root / "tools/collector.spec")], cwd=root, check=True,
                   env=dict(os.environ, PYINSTALLER_CONFIG_DIR=str(build / "pyinstaller-cache")))
    print(root / "dist/osu-diff-collector.exe")


if __name__ == "__main__":
    main()
