# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Portable manifests and file transport; no network service required."""

import re
import hashlib
import json
import uuid
import zipfile
from pathlib import Path



def validate_inventory(inventory):
    if not isinstance(inventory, dict) or inventory.get("schema_version") != 1:
        raise ValueError("unsupported inventory schema")
    entries = inventory.get("objects")
    if not isinstance(entries, list):
        raise ValueError("inventory objects must be a list")
    if "collection_machine" in inventory:
        machine = inventory["collection_machine"]
        if (not isinstance(machine, dict)
                or not isinstance(machine.get("id"), str)
                or not re.fullmatch(r"pc-[0-9a-f]{64}", machine["id"])
                or machine.get("scheme") not in ("windows-machineguid-sha256-v1",
                                                  "linux-machine-id-hmac-sha256-v1")
                or machine.get("assurance") != "self_reported"):
            raise ValueError("invalid collection machine claim")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid inventory object")
        sha = entry.get("sha256")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha) or sha in seen:
            raise ValueError("invalid or repeated SHA-256")
        seen.add(sha)
        if entry.get("kind") not in ("beatmap", "replay"):
            raise ValueError("unsupported object kind")
        if type(entry.get("size")) is not int or entry["size"] < 0:
            raise ValueError("invalid object size")
    return entries


def export_bundle(dataset, output, *, requested=None, max_part_bytes=64 * 1024 * 1024):
    if max_part_bytes <= 0:
        raise ValueError("max_part_bytes must be positive")
    inventory = dataset.export_inventory()
    entries = inventory["objects"]
    if requested is not None:
        wanted = set(requested)
        if wanted - {entry["sha256"] for entry in entries}:
            raise ValueError("requested objects are not in this collection")
        entries = [entry for entry in entries if entry["sha256"] in wanted]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    groups = []
    group, size = [], 0
    for entry in entries:
        if group and size + entry["size"] > max_part_bytes:
            groups.append(group)
            group, size = [], 0
        group.append(entry)
        size += entry["size"]
    if group:
        groups.append(group)
    parts = []
    batch = uuid.uuid4().hex
    for index, group in enumerate(groups, 1):
        path = output / f"{batch}-{index:04d}.zip"
        staging = path.with_suffix(".partial")
        try:
            with zipfile.ZipFile(staging, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as package:
                manifest = {"schema_version": 1, "objects": group}
                if "submission_id" in inventory:
                    manifest["submission_id"] = inventory["submission_id"]
                if "collection_machine" in inventory:
                    manifest["collection_machine"] = inventory["collection_machine"]
                package.writestr("manifest.json", json.dumps(manifest))
                for entry in group:
                    package.write(dataset.root / "objects" / entry["sha256"], "objects/" + entry["sha256"])
            staging.replace(path)
        finally:
            staging.unlink(missing_ok=True)
        parts.append(str(path))
    return parts
