# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Atomic settings writes and offline collection ZIP verification."""

import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from .transfer import validate_inventory

CHUNK_SIZE = 8 * 1024**2
MAX_PACKAGE = 4 * 1024**3


def file_digest(path):
    digest, size = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024**2):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def sync_directory(path):
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".state-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def valid_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def verify_bundle(path):
    """Verify bytes and bounded ZIP structure without importing/decoding gameplay."""
    with zipfile.ZipFile(path) as package:
        infos = package.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("ZIP 必须包含唯一的 manifest.json，且不能有重名成员")
        if sum(info.file_size for info in infos) > MAX_PACKAGE:
            raise ValueError("ZIP 解压后总量超过 4 GiB 接收上限")
        for name in {"manifest.json", "inventory.json", "collection-log.json"} & set(names):
            if package.getinfo(name).file_size > 16 * 1024**2:
                raise ValueError("ZIP 清单或日志超过 16 MiB")
        manifest = json.loads(package.read("manifest.json"))
        entries = validate_inventory(manifest)
        expected = {"manifest.json"} | {"objects/" + item["sha256"] for item in entries}
        if set(names) - {"inventory.json", "collection-log.json"} != expected:
            raise ValueError("ZIP 包含缺失或额外文件")
        for item in entries:
            name = "objects/" + item["sha256"]
            if package.getinfo(name).file_size != item["size"]:
                raise ValueError("ZIP 内文件大小不一致")
            digest = hashlib.sha256()
            with package.open(name) as source:
                while chunk := source.read(1024**2):
                    digest.update(chunk)
            if digest.hexdigest() != item["sha256"]:
                raise ValueError("ZIP 内文件 SHA-256 不一致")
        # Read bounded diagnostics too, checking their CRC instead of ignoring corruption.
        for name in {"inventory.json", "collection-log.json"} & set(names):
            package.read(name)
        return manifest
