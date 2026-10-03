# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Frozen entry point: GUI without arguments, CLI otherwise."""
from osu_diff.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
