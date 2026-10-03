# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Desktop paths and folder opening shared by the collector UI."""

import os
import subprocess
from pathlib import Path


def xdg_path(variable, fallback):
    value = os.environ.get(variable, "")
    path = Path(value)
    return path if value and path.is_absolute() else Path.home() / fallback


def open_directory(path):
    path = str(Path(path).resolve())
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
