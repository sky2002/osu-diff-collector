# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Local collector/downloader preferences; no network client dependency."""

import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from .desktop import xdg_path
from .bundle import save_json


@contextmanager
def exclusive_lock(path, *, error_type=RuntimeError):
    """OS-managed lock: released on a crash, independent of stale state files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise error_type("此目录已有另一个任务，请等它完成") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def settings_path(program):
    base = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            if os.name == "nt" else xdg_path("XDG_CONFIG_HOME", ".config"))
    return base / "osu-diff" / (program + ".json")


def load_settings(program):
    path = settings_path(program)
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("设置文件损坏")
        return value
    return {}


def collector_submission_id():
    path = settings_path("collector")
    with exclusive_lock(path.with_suffix(".lock")):
        settings = load_settings("collector")
        if not settings.get("submission_id"):
            settings["submission_id"] = "donor-" + uuid.uuid4().hex[:12]
            save_json(path, settings)
        return settings["submission_id"]


def save_settings(program, values):
    path = settings_path(program)
    with exclusive_lock(path.with_suffix(".lock")):
        settings = load_settings(program)
        settings.update(values)
        save_json(path, settings)
