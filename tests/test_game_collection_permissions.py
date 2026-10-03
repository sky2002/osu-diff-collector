# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from osu_diff.game_collection import collect_and_pack
from osu_diff.bundle import verify_bundle
from tests.samples import BEATMAP, replay


@unittest.skipUnless(os.name == "nt", "Windows file permissions")
class CollectionPermissionsTests(unittest.TestCase):
    def test_export_inherits_destination_read_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            game = root / "game"
            (game / "Songs").mkdir(parents=True)
            (game / "Data/r").mkdir(parents=True)
            (game / "Songs/map.osu").write_bytes(BEATMAP)
            (game / "Data/r/play.osr").write_bytes(replay())
            output = root / "output"
            output.mkdir()
            # Give ordinary users read access only to this synthetic output.
            subprocess.run(["icacls.exe", str(output), "/grant",
                            "*S-1-5-32-545:(OI)(CI)(RX)"],
                           capture_output=True, check=True)
            reference = output / "ordinary-file.txt"
            reference.write_bytes(b"destination permissions")
            machine = {"id": "pc-" + "a" * 64,
                       "scheme": "windows-machineguid-sha256-v1",
                       "assurance": "self_reported"}
            with patch("osu_diff.game_collection.collection_machine", return_value=machine):
                result = collect_and_pack(game, output, "donor-permissions-test")
            archive = Path(result["archive_path"])
            verify_bundle(archive)
            script = """
$ErrorActionPreference = 'Stop'
$result = foreach ($path in @($env:OSU_TEST_REFERENCE, $env:OSU_TEST_ARCHIVE)) {
    $rules = [System.IO.File]::GetAccessControl($path).GetAccessRules(
        $true, $true, [System.Security.Principal.SecurityIdentifier])
    $mask = 0
    foreach ($rule in $rules) {
        if ($rule.IdentityReference.Value -eq 'S-1-5-32-545' -and
            $rule.AccessControlType -eq 'Allow') {
            $mask = $mask -bor [int]$rule.FileSystemRights
        }
    }
    $mask
}
ConvertTo-Json -Compress -InputObject @($result)
"""
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                env={**os.environ, "OSU_TEST_REFERENCE": str(reference),
                     "OSU_TEST_ARCHIVE": str(archive)},
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            reference_rights, archive_rights = json.loads(completed.stdout)
            # ReadData (1) opens the ZIP; ReadPermissions (0x20000) opens Security.
            required = 0x20001
            self.assertEqual(reference_rights & required, required)
            self.assertEqual(archive_rights & required, required,
                             "Exported ZIP lost ordinary users' file/security read access")
            self.assertEqual(set(output.iterdir()), {reference, archive})


if __name__ == "__main__":
    unittest.main()
