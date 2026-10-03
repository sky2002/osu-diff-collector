# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Conservative metadata readers; raw files remain the source of truth."""

import re
import struct
from datetime import datetime, timedelta, timezone


def read_replay(path):
    with path.open("rb") as stream:
        def unpack(fmt):
            size = struct.calcsize(fmt)
            data = stream.read(size)
            if len(data) != size:
                raise ValueError("truncated replay header")
            return struct.unpack(fmt, data)

        def string():
            marker, = unpack("<B")
            if marker == 0:
                return ""
            if marker != 11:
                raise ValueError("invalid replay string marker")
            length = 0
            for shift in range(0, 35, 7):
                byte, = unpack("<B")
                length |= (byte & 127) << shift
                if not byte & 128:
                    break
            else:
                raise ValueError("invalid ULEB128 string length")
            if length > 1024 * 1024:
                raise ValueError("replay string exceeds 1 MiB")
            data = stream.read(length)
            if len(data) != length:
                raise ValueError("truncated replay string")
            return data.decode("utf-8")

        mode, version = unpack("<Bi")
        map_hash, player, replay_hash = string(), string(), string()
        if mode not in range(4) or not re.fullmatch(r"[0-9a-fA-F]{32}", map_hash):
            raise ValueError("invalid replay mode or beatmap MD5")
        counts = dict(zip(("n300", "n100", "n50", "ngeki", "nkatu", "nmiss"), unpack("<6H")))
        score, combo, perfect, mods = unpack("<iHBi")
        life = string()
        ticks, payload_size = unpack("<qi")
        if payload_size < 0 or stream.tell() + payload_size > path.stat().st_size:
            raise ValueError("missing or truncated replay payload")
        payload_offset = stream.tell()
        stream.seek(payload_size, 1)
        remaining = path.stat().st_size - stream.tell()
        online_id = unpack("<q")[0] if remaining >= 8 else None
        trailing_bytes = path.stat().st_size - stream.tell()
        played_at = None
        if ticks > 0:
            try:
                played_at = (datetime(1, 1, 1, tzinfo=timezone.utc)
                             + timedelta(microseconds=ticks // 10)).isoformat()
            except OverflowError:
                pass
        fast, slow = bool(mods & (64 | 512)), bool(mods & 256)
        return {
            "mode": mode, "game_version": version, "beatmap_md5": map_hash.lower(),
            "player_name": player, "player_id": None, "replay_hash": replay_hash,
            "counts": counts, "score": score, "max_combo": combo, "perfect": perfect,
            "mods": mods, "life_graph": life, "played_at_ticks": ticks,
            "played_at": played_at, "online_score_id": online_id,
            "payload_offset": payload_offset, "payload_size": payload_size,
            "trailing_bytes": trailing_bytes, "client": "unknown",
            "rate_hint": None if fast and slow else 1.5 if fast else 0.75 if slow else 1.0,
            "rule_hint": "score_v2" if mods & 536870912 else "legacy_default",
            "effective_conditions": None, "completeness": "unknown",
            "frame_validation": "not_checked", "judgement_validation": "not_checked",
        }


def read_beatmap(path):
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("beatmap exceeds the 16 MiB metadata reader limit")
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("osu file format v"):
        raise ValueError("missing osu file format header")
    sections = {}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            sections.setdefault(section, {})
        elif section and ":" in line and not line.startswith("//"):
            key, value = line.split(":", 1)
            sections[section][key.strip()] = value.strip()
    difficulty = sections.get("Difficulty", {})
    return {
        "mode": int(sections.get("General", {}).get("Mode", "0")),
        "keys": float(difficulty["CircleSize"]) if "CircleSize" in difficulty else None,
        "od": float(difficulty["OverallDifficulty"]) if "OverallDifficulty" in difficulty else None,
        "title": sections.get("Metadata", {}).get("Title"),
        "difficulty": sections.get("Metadata", {}).get("Version"),
    }
