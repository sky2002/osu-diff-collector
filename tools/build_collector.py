# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Build the portable source zipapp (Python 3.11+ and Tk must be installed)."""
import shutil
import tempfile
import zipapp
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "dist/osu-diff-collector.pyz"
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        (stage / "osu_diff").mkdir()
        for source in sorted((root / "osu_diff").glob("*.py")):
            shutil.copyfile(source, stage / "osu_diff" / source.name)
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            shutil.copyfile(root / name, stage / name)
        (stage / "__main__.py").write_text("from osu_diff.cli import main\nraise SystemExit(main())\n", encoding="utf-8")
        zipapp.create_archive(stage, target=output, interpreter="/usr/bin/env python3", compressed=True)
    print(output)


if __name__ == "__main__":
    main()
