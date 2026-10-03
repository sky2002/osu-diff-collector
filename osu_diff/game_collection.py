# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Locate game files and copy replay/beatmap pairs without interpreting scores."""

import hashlib
import json
import lzma
import os
import re
import getpass
import struct
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from .collector import RawCollection
from .formats import read_beatmap, read_replay
from .machine import collection_machine
from .desktop import xdg_path


# Legacy Key1/2/3/5/6/7/8/9 and KeyCoop. Key4 does not change the scope.
_NON_4K_MODS = (65536 | 131072 | 262144 | 524288 | 16777216 | 33554432
                | 67108864 | 134217728 | 268435456)


def _mod_scope(path, metadata):
    """Conservative key-count gate; never decompress the replay frame payload."""
    if metadata["mods"] & _NON_4K_MODS:
        return "out_of_scope"
    if metadata["game_version"] < 30000000:
        return None
    if not 30000001 <= metadata["game_version"] <= 30000019:
        return "unverifiable"
    # Modern lazer serialises an LZMA JSON score-info block after the online ID.
    # Its mods can contain information not representable in the legacy bitmask.
    limit = 4 * 1024 * 1024
    try:
        with path.open("rb") as stream:
            stream.seek(metadata["payload_offset"] + metadata["payload_size"] + 8)
            raw_length = stream.read(4)
            if len(raw_length) != 4:
                return "unverifiable"
            length, = struct.unpack("<i", raw_length)
            if not 0 < length <= limit:
                return "unverifiable"
            compressed = stream.read(length)
        if len(compressed) != length:
            return "unverifiable"
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=64 * 1024 * 1024)
        raw = decoder.decompress(compressed, max_length=limit + 1)
        if len(raw) > limit or not decoder.eof:
            return "unverifiable"
        info = json.loads(raw)
        mods = info.get("mods") if isinstance(info, dict) else None
        if not isinstance(mods, list):
            return "unverifiable"
        # Unknown future mods are held back until their effect on columns is known.
        same_keys = {"4K", "NF", "EZ", "HR", "SD", "PF", "DT", "NC", "HT", "DC",
                     "HD", "FI", "FL", "MR", "RD", "CL", "SV2", "AT", "CN",
                     "NR", "CV", "AC", "DA", "IN", "CS", "HO", "WU", "WD", "MU", "AS"}
        for mod in mods:
            if not isinstance(mod, dict) or not isinstance(mod.get("acronym"), str):
                return "unverifiable"
            acronym = mod["acronym"]
            if acronym == "DS" or re.fullmatch(r"(?:[1-35-9]|10)K", acronym):
                return "out_of_scope"
            if acronym not in same_keys:
                return "unverifiable"
            settings = mod.get("settings", {})
            if not isinstance(settings, dict) or any(key in settings for key in ("circle_size", "key_count", "columns")):
                return "unverifiable"
        return None
    except (ValueError, lzma.LZMAError, RecursionError):
        return "unverifiable"


def _setting(path, name):
    if not path.is_file():
        return None
    # Read only the requested path setting; never copy login/configuration data.
    with path.open(encoding="utf-8-sig", errors="replace") as stream:
        for line in stream:
            key, separator, value = line.partition("=")
            if separator and key.strip().casefold() == name.casefold():
                return value.strip().strip('"') or None
    return None


def _data_home():
    if sys.platform == "linux":
        return xdg_path("XDG_DATA_HOME", ".local/share")
    return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))


def _configured_path(value, root):
    value = os.path.expandvars(value)
    if sys.platform == "linux" and "\\" in value:
        value = value.replace("\\", "/")
    if sys.platform == "linux" and re.match(r"^[A-Za-z]:/", value):
        # Resolve Wine drive mappings, including custom drives in dosdevices.
        prefix = next((path.parent for path in (root, *root.parents)
                       if path.name == "drive_c"), None)
        if prefix is None:
            raise ValueError("Windows 配置路径无法映射到 Linux，请手动选择真实数据目录")
        drive = value[0].lower()
        mapped = prefix / "dosdevices" / (drive + ":")
        if not mapped.exists():
            mapped = prefix / "drive_c" if drive == "c" else Path("/") if drive == "z" else mapped
        if not mapped.exists():
            raise ValueError("Wine 驱动器映射不存在，请手动选择真实数据目录")
        return (mapped / value[3:]).resolve()
    target = Path(value).expanduser()
    return (target if target.is_absolute() else root / target).resolve()


def inspect_game(path, *, appdata=None):
    root = Path(path).expanduser().resolve()
    default_lazer = Path(appdata or _data_home()) / "osu"
    if (root / "osu.Game.dll").is_file() or (root / "current/osu.Game.dll").is_file():
        root = default_lazer.resolve()
    visited = set()
    while True:
        if root in visited:
            raise ValueError("lazer 数据目录配置形成循环，请手动选择数据目录")
        visited.add(root)
        custom = _setting(root / "storage.ini", "FullPath")
        if not custom:
            break
        target = _configured_path(custom, root)
        if target == root:
            break
        root = target
    if (root / "files").is_dir():
        return {"client": "lazer", "path": str(root)}
    if (root / "Songs").is_dir() or (root / "Data" / "r").is_dir() or any(root.glob("osu!*.cfg")):
        maps = root / "Songs"
        configs = [root / f"osu!.{getpass.getuser()}.cfg", root / "osu!.cfg", *sorted(root.glob("osu!.*.cfg"))]
        for config in configs:
            custom = _setting(config, "BeatmapDirectory")
            if custom:
                maps = _configured_path(custom, root)
                break
        return {"client": "stable", "path": str(root), "maps": str(maps.resolve())}
    raise ValueError("没有识别到 osu! 数据，请选择游戏目录")


def _registry_roots():
    paths = []
    if os.name == "nt":
        import winreg
        for name in ("osustable.File.osz", "osu!"):
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, name + r"\shell\open\command") as key:
                    command = winreg.QueryValueEx(key, "")[0]
                match = re.match(r'\s*"([^\"]+\.exe)"', command, re.IGNORECASE)
                if match:
                    paths.append(Path(match[1]).parent)
            except OSError:
                pass
    return paths


def _installed_apps():
    records = []
    if os.name != "nt":
        return records
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as parent:
                    for index in range(winreg.QueryInfoKey(parent)[0]):
                        try:
                            with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as key:
                                name = winreg.QueryValueEx(key, "DisplayName")[0]
                                if not re.match(r"^osu!?(?:$|[ (]|lazer|stable)", str(name), re.IGNORECASE):
                                    continue
                                record = {"DisplayName": name}
                                for field in ("InstallLocation", "DisplayIcon", "UninstallString"):
                                    try:
                                        record[field] = winreg.QueryValueEx(key, field)[0]
                                    except OSError:
                                        pass
                                records.append(record)
                        except OSError:
                            continue
            except OSError:
                continue
    return records


def _program_paths(records):
    for record in records:
        if not re.match(r"^osu!?(?:$|[ (]|lazer|stable)", record.get("DisplayName", ""), re.IGNORECASE):
            continue
        location = record.get("InstallLocation", "").strip().strip('"')
        if location:
            yield Path(os.path.expandvars(location))
        for field in ("DisplayIcon", "UninstallString"):
            value = os.path.expandvars(record.get(field, ""))
            match = re.match(r'\s*(?:"([^\"]+\.exe)"|(.+?\.exe))(?:[,\s]|$)', value, re.IGNORECASE)
            if match:
                yield Path(match[1] or match[2]).parent


def _linux_roots():
    home = Path.home()
    data = _data_home()
    yield home / ".local/share/osu"
    yield home / ".var/app/sh.ppy.osu/data/osu"
    yield home / "Games/osu"
    prefixes = [Path(os.environ.get("WINEPREFIX") or home / ".wine").expanduser(),
                home / "Games/osu", home / ".osu"]
    for directory in (data / "bottles/bottles",
                      home / ".var/app/com.usebottles.bottles/data/bottles/bottles"):
        if directory.is_dir():
            prefixes.extend(path for path in directory.iterdir() if path.is_dir())
    for prefix in dict.fromkeys(prefixes):
        yield prefix / "drive_c/osu!"
        yield prefix / "drive_c/Program Files/osu!"
        yield prefix / "drive_c/Program Files (x86)/osu!"
        users = prefix / "drive_c/users"
        if users.is_dir():
            for user in users.iterdir():
                yield user / "AppData/Local/osu!"
                yield user / "Local Settings/Application Data/osu!"
                yield user / "AppData/Roaming/osu"


def discover_games(*, appdata=None, localappdata=None, registry_paths=None, installed_apps=None):
    appdata = Path(appdata or _data_home())
    localappdata = Path(localappdata or os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    candidates = [*_program_paths(_installed_apps() if installed_apps is None else installed_apps),
                  *(_registry_roots() if registry_paths is None else registry_paths),
                  appdata / "osu", localappdata / "osu!"]
    if sys.platform == "linux":
        try:
            candidates.extend(_linux_roots())
        except OSError:
            pass  # A restricted prefix must not prevent manual selection.
    found = {}
    for candidate in candidates:
        try:
            game = inspect_game(candidate, appdata=appdata)
            found[game["path"]] = game
        except (ValueError, OSError):
            continue
    return sorted(found.values(), key=lambda game: (game["client"], game["path"]))


def _files(root, excluded, errors):
    if not root.exists():
        return
    def failed(error):
        errors.append({"path": str(error.filename), "error": str(error)})

    for parent, directories, names in os.walk(root, onerror=failed):
        directories[:] = [name for name in directories if not (Path(parent) / name).is_symlink()
                          and (Path(parent) / name).resolve() != excluded]
        for name in names:
            path = Path(parent) / name
            if not path.is_symlink():
                yield path


def _replay_map_hash(prefix):
    if (len(prefix) >= 39 and prefix[0] in range(4) and prefix[5:7] == b"\x0b\x20"
            and re.fullmatch(b"[0-9a-fA-F]{32}", prefix[7:39])):
        return prefix[7:39].decode("ascii").lower()
    return None


def collect_game(game_path, output, submitter_id, *, progress=None):
    if not str(output).strip():
        raise ValueError("请选择保存位置")
    if not submitter_id.strip():
        raise ValueError("提交代号不能为空")
    game = inspect_game(game_path)
    root, output = Path(game["path"]), Path(output).resolve()
    if root == output or root.is_relative_to(output):
        raise ValueError("保存位置不能是游戏目录或其上层目录")
    machine = collection_machine()
    output.mkdir(parents=True, exist_ok=True)
    collection = RawCollection(output)
    errors = []
    counts = {"imported": 0, "duplicate": 0, "failed": 0, "ignored": 0}
    hashes, matched = set(), set()
    replays_found, unknown_references = 0, 0
    collected_replays = 0
    skipped = {"out_of_scope": 0, "missing_beatmap": 0, "unverifiable": 0, "copy_failed": 0}

    def copy(path, kind=None):
        try:
            counts[collection.copy_file(path, kind=kind)] += 1
            return True
        except OSError as error:
            errors.append({"path": str(path), "error": str(error)})
            return False

    map_paths = []
    replay_paths = []
    if game["client"] == "lazer":
        for index, path in enumerate(_files(root / "files", output, errors), 1):
            if progress and index % 250 == 0:
                progress(f"正在查找 lazer 文件：已检查 {index} 个，找到 {len(replay_paths)} 份 replay")
            try:
                with path.open("rb") as stream:
                    prefix = stream.read(64)
                if prefix.removeprefix(b"\xef\xbb\xbf").lstrip().startswith(b"osu file format v"):
                    map_paths.append(path)
                elif _replay_map_hash(prefix):
                    replay_paths.append(path)
                else:
                    counts["ignored"] += 1
            except OSError as error:
                errors.append({"path": str(path), "error": str(error)})
    else:
        map_paths = [path for path in _files(Path(game["maps"]), output, errors) if path.suffix.lower() == ".osu"]
    directories = (root / "exports",) if game["client"] == "lazer" else (root / "Data" / "r", root / "Replays")
    for directory in directories:
        for path in _files(directory, output, errors):
            if path.suffix.lower() == ".osr":
                replay_paths.append(path)
    candidates = []
    for path in replay_paths:
        replays_found += 1
        try:
            metadata = read_replay(path)
            if metadata["mode"] != 3:
                skipped["out_of_scope"] += 1
                continue
            hashes.add(metadata["beatmap_md5"])
            candidates.append((path, metadata))
        except ValueError:
            unknown_references += 1
            skipped["unverifiable"] += 1
        except OSError as error:
            errors.append({"path": str(path), "error": str(error)})
            skipped["unverifiable"] += 1
    maps, found = {}, set()
    for index, path in enumerate(map_paths, 1):
        if progress and index % 250 == 0:
            progress(f"正在查找对应谱面：{index} / {len(map_paths)}")
        try:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, lambda: hashlib.md5(usedforsecurity=False)).hexdigest()
            if digest in hashes:
                found.add(digest)
                maps[digest] = (path, read_beatmap(path))
        except ValueError:
            # The referenced file exists, but cannot establish the key count.
            continue
        except OSError as error:
            errors.append({"path": str(path), "error": str(error)})
    for index, (path, metadata) in enumerate(candidates, 1):
        if progress and index % 100 == 0:
            progress(f"正在筛选并复制 mania 4K replay：{index} / {len(candidates)}")
        reference = metadata["beatmap_md5"]
        if reference not in found:
            skipped["missing_beatmap"] += 1
            continue
        if reference not in maps or maps[reference][1]["keys"] is None:
            skipped["unverifiable"] += 1
            continue
        map_path, beatmap = maps[reference]
        if beatmap["mode"] != 3 or beatmap["keys"] != 4:
            skipped["out_of_scope"] += 1
            continue
        try:
            reason = _mod_scope(path, metadata)
        except OSError as error:
            errors.append({"path": str(path), "error": str(error)})
            reason = "unverifiable"
        if reason:
            skipped[reason] += 1
            continue
        if reference not in matched:
            if not copy(map_path, "beatmap"):
                skipped["copy_failed"] += 1
                continue
            matched.add(reference)
        if copy(path, "replay"):
            collected_replays += 1
        else:
            skipped["copy_failed"] += 1
    counts["failed"] = len(errors)
    result = {"client": game["client"], "data_path": str(root), "submitter_id": submitter_id,
              "collection_machine": machine,
              "counts": counts, "replays_found": replays_found, "matched_beatmaps": len(matched),
              "collection_scope": "native_mania_4k", "collected_replays": collected_replays,
              "selected_objects": sorted(collection.copied_objects),
              "skipped_replays": skipped, "missing_beatmap_hashes": sorted(hashes - found),
              "unknown_replay_references": unknown_references,
              "copy_errors": errors, "inventory_path": str(collection.inventory_path),
              "log_path": str(output / "collection-log.json")}
    (output / "collection-log.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    collection.save()
    return result


def _collection_summary(sources, entries):
    """Summarise scanned files, retaining source membership even after deduplication."""
    clients = list(dict.fromkeys(source["client"] for source in sources))
    result = dict(sources[0])
    result.update(client="+".join(clients), collection_clients=clients, sources=sources,
                  selected_objects=sorted(entry["sha256"] for entry in entries),
                  matched_beatmaps=sum(entry["kind"] == "beatmap" for entry in entries))
    if len(sources) > 1:
        result.pop("data_path", None)
    for field in ("counts", "skipped_replays"):
        result[field] = {key: sum(source[field][key] for source in sources) for key in sources[0][field]}
    for field in ("replays_found", "collected_replays", "unknown_replay_references"):
        result[field] = sum(source[field] for source in sources)
    result["missing_beatmap_hashes"] = sorted({value for source in sources for value in source["missing_beatmap_hashes"]})
    result["copy_errors"] = [error for source in sources for error in source["copy_errors"]]
    return result


def collect_and_pack(game_path, output, submitter_id=None, *, progress=None, package_mode="combined"):
    """Collect one or more game folders into one ZIP, or one ZIP per client."""
    if not str(output).strip():
        raise ValueError("请选择保存位置")
    if package_mode not in ("combined", "separate"):
        raise ValueError("打包方式须为 combined 或 separate")
    output = Path(output).resolve()
    paths = [game_path] if isinstance(game_path, (str, os.PathLike)) else list(game_path)
    games = {}
    for path in paths:
        game = inspect_game(path)
        game_root = Path(game["path"])
        if game_root == output or game_root.is_relative_to(output):
            raise ValueError("保存位置不能是游戏目录或其上层目录")
        games[game_root] = game
    if not games:
        raise ValueError("请至少选择一个游戏位置")
    output.mkdir(parents=True, exist_ok=True)
    if not submitter_id:
        log = output / "collection-log.json"
        if log.is_file():
            submitter_id = json.loads(log.read_text(encoding="utf-8")).get("submitter_id")
        if not submitter_id:
            for previous in sorted(output.glob("osu-diff-4k-*.zip"), reverse=True):
                try:
                    with zipfile.ZipFile(previous) as package:
                        if package.getinfo("manifest.json").file_size > 16 * 1024 * 1024:
                            continue
                        prior_id = json.loads(package.read("manifest.json")).get("submission_id")
                    if isinstance(prior_id, str) and prior_id.strip():
                        submitter_id = prior_id
                        break
                except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                    continue
        submitter_id = submitter_id or "donor-" + uuid.uuid4().hex[:12]
    batch_id = uuid.uuid4().hex
    filename = f"osu-diff-4k-{datetime.now():%Y%m%d-%H%M%S}-{batch_id[:8]}"
    # Work on the selected volume, then publish complete archives.
    # Only this generated scratch directory is cleaned; existing outputs stay intact.
    with tempfile.TemporaryDirectory(prefix=".osu-diff-", dir=output) as temporary:
        workspace = Path(temporary).resolve()
        if workspace.parent != output:
            raise ValueError("临时采集目录不在保存位置内")
        sources = []
        for game in games.values():
            if progress:
                progress(f"正在收集 {game['client']}：{game['path']}")
            source = collect_game(game["path"], workspace, submitter_id, progress=progress)
            source["inventory_path"] = "inventory.json"
            source["log_path"] = "collection-log.json"
            sources.append(source)
        if any(source["collection_machine"] != sources[0]["collection_machine"] for source in sources):
            raise ValueError("采集电脑 ID 在本次操作中发生变化，请重新采集")
        collection = RawCollection(workspace)
        inventory = collection.export_inventory()
        result = _collection_summary(sources, inventory["objects"])
        result.update(collection_batch_id=batch_id, package_mode=package_mode, share_directory=str(output))
        groups = ([sources] if package_mode == "combined" else
                  [[source for source in sources if source["client"] == client]
                   for client in result["collection_clients"]])
        archives = [output / (filename + ("-" + group[0]["client"] if package_mode == "separate" else "") + ".zip")
                    for group in groups]
        result["parts"] = [str(archive) for archive in archives]
        if len(archives) == 1:
            result["archive_path"] = str(archives[0])
        staged, published = [], []
        try:
            for group, archive in zip(groups, archives):
                selected = {sha for source in group for sha in source["selected_objects"]}
                entries = [entry for entry in inventory["objects"] if entry["sha256"] in selected]
                log = _collection_summary(group, entries)
                log.update(collection_batch_id=batch_id, package_mode=package_mode,
                           archive_path=str(archive), share_directory=str(output), parts=[str(archive)])
                manifest = {**inventory, "objects": entries, "collection_batch_id": batch_id,
                            "collection_clients": log["collection_clients"]}
                if progress:
                    progress(f"正在生成 ZIP：{archive.name}")
                # Keep the destination ACL fix: never move a private-temp ZIP here.
                staging = archive.with_suffix(".zip.partial")
                stream = staging.open("xb")
                staged.append(staging)
                with stream, zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as package:
                    serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
                    package.writestr("manifest.json", serialized)
                    package.writestr("inventory.json", serialized)
                    package.writestr("collection-log.json", json.dumps(log, ensure_ascii=False, indent=2) + "\n")
                    for entry in entries:
                        package.write(collection.root / "objects" / entry["sha256"], "objects/" + entry["sha256"])
            for staging, archive in zip(staged, archives):
                staging.replace(archive)
                published.append(archive)
        except Exception:
            for archive in published:
                archive.unlink(missing_ok=True)
            raise
        finally:
            for staging in staged:
                staging.unlink(missing_ok=True)
    return result
