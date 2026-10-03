# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Copy raw files for offline transport without interpreting gameplay."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .transfer import validate_inventory, export_bundle
from .machine import collection_machine


class RawCollection:
    def __init__(self, output):
        self.output = Path(output).resolve()
        self.root = self.output / "data"
        self.inventory_path = self.output / "inventory.json"
        self.entries = {}
        self.copied_objects = set()
        if self.inventory_path.is_file():
            inventory = json.loads(self.inventory_path.read_text(encoding="utf-8"))
            self.entries = {entry["sha256"]: entry for entry in validate_inventory(inventory)}

    def export_inventory(self):
        result = {"schema_version": 1, "objects": [self.entries[sha] for sha in sorted(self.entries)]}
        log = self.output / "collection-log.json"
        if log.is_file():
            metadata = json.loads(log.read_text(encoding="utf-8"))
            submission_id = metadata.get("submitter_id")
            if isinstance(submission_id, str) and submission_id:
                result["submission_id"] = submission_id
            if "collection_machine" in metadata:
                result["collection_machine"] = metadata["collection_machine"]
        return result

    def save(self):
        staging = self.inventory_path.with_suffix(".json.partial")
        staging.write_text(json.dumps(self.export_inventory(), indent=2) + "\n", encoding="utf-8")
        staging.replace(self.inventory_path)

    def copy_file(self, path, *, kind=None):
        objects = self.root / "objects"
        objects.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        descriptor, temporary = tempfile.mkstemp(dir=self.root, prefix="collect-")
        temporary = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as target, path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            sha = digest.hexdigest()
            duplicate = sha in self.entries
            destination = objects / sha
            if not destination.exists():
                temporary.replace(destination)
            self.entries[sha] = {"sha256": sha, "size": size,
                                 "kind": kind or ("replay" if path.suffix.lower() == ".osr" else "beatmap")}
            self.copied_objects.add(sha)
            return "duplicate" if duplicate else "imported"
        finally:
            temporary.unlink(missing_ok=True)


def collect_submission(folders, output, submitter_id):
    if not str(output).strip():
        raise ValueError("请选择保存位置")
    folders = list(dict.fromkeys(Path(folder).resolve() for folder in folders))
    if not folders or any(not folder.is_dir() for folder in folders):
        raise ValueError("请选择存在的 replay / 谱面目录")
    if not submitter_id.strip():
        raise ValueError("请填写组织者分配的提交代号")
    output = Path(output).resolve()
    if any(folder == output or folder.is_relative_to(output) for folder in folders):
        raise ValueError("保存位置不能是输入目录或输入目录的上层目录")
    machine = collection_machine()
    output.mkdir(parents=True, exist_ok=True)
    counts = {"imported": 0, "duplicate": 0, "failed": 0, "ignored": 0}
    collection = RawCollection(output)
    errors = []

    def failed(path, error):
        counts["failed"] += 1
        errors.append({"path": str(path), "error": str(error)})

    for folder in folders:
        for parent, directories, names in os.walk(folder, onerror=lambda e: failed(e.filename, e)):
            directories[:] = [name for name in directories if not (Path(parent) / name).is_symlink()
                              and (Path(parent) / name).resolve() != output]
            for name in names:
                path = Path(parent) / name
                if path.is_symlink() or path.suffix.lower() not in (".osu", ".osr"):
                    counts["ignored"] += 1
                    continue
                try:
                    counts[collection.copy_file(path)] += 1
                except OSError as error:
                    failed(path, error)
        collection.save()
    log_path = output / "collection-log.json"
    log_path.write_text(json.dumps({"submitter_id": submitter_id.strip(), "collection_machine": machine, "counts": counts,
                                    "copy_errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    collection.save()
    return {"counts": counts, "collection_machine": machine,
            "inventory_path": str(collection.inventory_path), "log_path": str(log_path)}


def pack_submission(output, *, requested=None, max_part_bytes=64 * 1024 * 1024):
    if not str(output).strip():
        raise ValueError("请选择保存位置")
    output = Path(output).resolve()
    if not (output / "inventory.json").is_file():
        raise ValueError("保存位置中没有采集清单，请先采集")
    return export_bundle(RawCollection(output), output / "outbox",
                         requested=requested, max_part_bytes=max_part_bytes)
