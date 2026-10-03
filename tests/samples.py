# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Synthetic format examples; not captured or verified game output."""

import hashlib
import lzma
import struct

BEATMAP = b"""osu file format v14

[General]
Mode:3
[Metadata]
Title:Synthetic
Artist:Fixture
Creator:Tests
Version:4K
[Difficulty]
CircleSize:4
OverallDifficulty:8
[HitObjects]
64,192,1000,1,0,0:0:0:0:
192,192,2000,128,0,2500:0:0:0:0:
"""


def replay(*, player="Guest", ticks=638396640000000000, map_hash=None,
           replay_hash="0123456789abcdef0123456789abcdef", mods=0,
           score=123456, frames="1000|1|0|0,1000|2|0|0,", version=20240101,
           counts=(10, 2, 1, 20, 3, 4)):
    def string(value):
        encoded = value.encode("utf-8")
        length = len(encoded)
        prefix = bytearray([11])
        while length >= 128:
            prefix.append((length & 127) | 128)
            length >>= 7
        prefix.append(length)
        return bytes(prefix) + encoded

    payload = lzma.compress(frames.encode(), format=lzma.FORMAT_ALONE)
    return (struct.pack("<Bi", 3, version)
            + string(map_hash or hashlib.md5(BEATMAP).hexdigest())
            + string(player) + string(replay_hash)
            + struct.pack("<6HiHBi", *counts, score, 15, 0, mods)
            + string("") + struct.pack("<qi", ticks, len(payload)) + payload
            + struct.pack("<q", 42))
