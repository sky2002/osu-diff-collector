# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Pseudonymous collection origin, independent of game, user and output path."""

import hashlib
import hmac
import os
import re
import sys
import uuid
from pathlib import Path


def collection_machine():
    """Identify this OS installation; this is a claim, not attestation."""
    if sys.platform == "linux":
        return _linux_machine()
    if os.name != "nt":
        raise ValueError("采集电脑标识目前仅支持 Windows / Linux；未生成采集包")
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            value, kind = winreg.QueryValueEx(key, "MachineGuid")
        if kind != winreg.REG_SZ or not isinstance(value, str):
            raise ValueError("invalid machine GUID type")
        guid = uuid.UUID(value.strip())
        if not guid.int:
            raise ValueError("empty machine GUID")
    except (OSError, ValueError, AttributeError):
        # Never silently substitute a new random ID or inherit another ZIP's ID.
        raise ValueError("无法读取有效的 Windows 采集电脑标识；未生成采集包，请检查系统注册表读取权限") from None
    digest = hashlib.sha256(b"osu-diff/collection-machine/v1\0" + str(guid).encode("ascii")).hexdigest()
    return {"id": "pc-" + digest, "scheme": "windows-machineguid-sha256-v1",
            "assurance": "self_reported"}


def _linux_machine():
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            value = path.read_text(encoding="ascii").strip().lower()
        except (OSError, UnicodeError):
            continue
        if re.fullmatch(r"[0-9a-f]{32}", value) and int(value, 16):
            digest = hmac.new(b"osu-diff/collection-machine/linux/v1", bytes.fromhex(value),
                              hashlib.sha256).hexdigest()
            return {"id": "pc-" + digest, "scheme": "linux-machine-id-hmac-sha256-v1",
                    "assurance": "self_reported"}
    raise ValueError("无法读取有效的 Linux 采集电脑标识；未生成采集包，请检查 /etc/machine-id")
