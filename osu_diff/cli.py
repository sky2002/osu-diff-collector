# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Offline collector commands; no research or network-service dependencies."""
import argparse
import json
import sys
import zipfile

from . import __version__
from .bundle import verify_bundle
from .game_collection import collect_and_pack, discover_games


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        from .gui import main as gui_main
        return gui_main()
    parser = argparse.ArgumentParser(description="Export local osu!mania 4K replays and beatmaps")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover", help="find local stable/lazer game directories")
    collect = sub.add_parser("collect-game", help="export one or more game directories as ZIPs")
    collect.add_argument("folder", nargs="+")
    collect.add_argument("--output", required=True)
    collect.add_argument("--submitter", help="optional submission label, not player identity")
    collect.add_argument("--package-mode", choices=("combined", "separate"), default="combined")
    verify = sub.add_parser("verify", help="check a collection ZIP's structure, sizes and SHA-256 hashes")
    verify.add_argument("archive")
    args = parser.parse_args(argv)
    try:
        if args.command == "discover":
            result = discover_games()
        elif args.command == "collect-game":
            result = collect_and_pack(args.folder, args.output, args.submitter, package_mode=args.package_mode)
        else:
            result = verify_bundle(args.archive)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"osu-diff-collector: {error}", file=sys.stderr)
        return 2
