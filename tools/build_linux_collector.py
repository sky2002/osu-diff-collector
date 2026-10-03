# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Build native x86_64 Linux packages in Debian 12 (see docs/building.md)."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from pathlib import Path


NAME = "osu-diff-collector"
DESKTOP = f"""[Desktop Entry]
Type=Application
Name=osu-diff Collector
Name[zh_CN]=osu-diff 采集器
Comment=Collect local osu!mania 4K replays and beatmaps
Exec={NAME}
Icon={NAME}
Terminal=false
Categories=Utility;Game;
"""
ICON = """<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
<rect width="128" height="128" rx="28" fill="#242638"/>
<g fill="#ef78ac"><rect x="22" y="27" width="15" height="64" rx="6"/>
<rect x="45" y="43" width="15" height="48" rx="6"/>
<rect x="68" y="35" width="15" height="56" rx="6"/>
<rect x="91" y="52" width="15" height="39" rx="6"/></g>
<path d="M22 102h84" stroke="white" stroke-width="5" stroke-linecap="round"/></svg>
"""


def run(*command, **kwargs):
    subprocess.run([str(part) for part in command], check=True, **kwargs)


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def tree_archive(tree, output, *, prefix="", compression="gz"):
    with tarfile.open(output, "w:" + compression) as archive:
        for path in sorted(tree.rglob("*")):
            info = archive.gettarinfo(str(path), str(Path(prefix) / path.relative_to(tree)))
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            if info.isfile():
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
            else:
                archive.addfile(info)


def install_tree(destination, payload, root):
    shutil.copytree(payload, destination / "opt" / NAME)
    write(destination / "usr/bin" / NAME, f'#!/bin/sh\nexec /opt/{NAME}/{NAME} "$@"\n', 0o755)
    write(destination / f"usr/share/applications/{NAME}.desktop", DESKTOP)
    write(destination / f"usr/share/icons/hicolor/scalable/apps/{NAME}.svg", ICON)
    docs = destination / "usr/share/doc" / NAME
    docs.mkdir(parents=True)
    shutil.copyfile(root / "README.md", docs / "README.md")
    shutil.copytree(payload / "_internal/licenses", destination / "usr/share/licenses" / NAME)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appimagetool", type=Path, required=True,
                        help="Official x86_64 appimagetool AppImage")
    parser.add_argument("--appimagetool-sha256", required=True,
                        help="Expected SHA-256 of the reviewed appimagetool download")
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64":
        parser.error("Run under x86_64 Linux; PyInstaller cannot cross-compile from Windows")
    if platform.libc_ver()[1] != "2.36":
        parser.error("Release builds require glibc 2.36 (Debian 12) to keep the documented ABI baseline")
    for program in ("dpkg-deb", "rpmbuild", "mksquashfs", "zstd", "file", "desktop-file-validate"):
        if not shutil.which(program):
            parser.error("Missing build tool: " + program)
    appimagetool = args.appimagetool.resolve(strict=True)
    if hashlib.sha256(appimagetool.read_bytes()).hexdigest() != args.appimagetool_sha256.lower():
        parser.error("appimagetool SHA-256 does not match")
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    output = root / "dist/linux-x86_64"
    output.mkdir(parents=True, exist_ok=True)
    products = []
    # Staging on Linux preserves symlinks and executable modes, including under WSL.
    with tempfile.TemporaryDirectory(prefix="osu-diff-linux-") as temporary:
        work = Path(temporary)
        env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / "cache"))
        run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", work / "dist", "--workpath", work / "build",
            root / "tools/collector.spec", cwd=root, env=env)
        payload = work / "dist" / NAME
        run(payload / NAME, "--help", stdout=subprocess.DEVNULL)

        portable = work / "portable"
        shutil.copytree(payload, portable)
        shutil.copyfile(root / "README.md", portable / "README.md")
        target = output / f"{NAME}-{version}-linux-x86_64.tar.gz"
        tree_archive(portable, target, prefix=f"{NAME}-{version}")
        products.append(target)

        tree = work / "package"
        install_tree(tree, payload, root)
        run("desktop-file-validate", tree / f"usr/share/applications/{NAME}.desktop")
        deb = work / "deb"
        shutil.copytree(tree, deb)
        size = sum(path.stat().st_size for path in tree.rglob("*") if path.is_file()) // 1024
        write(deb / "DEBIAN/control", f"""Package: {NAME}
Version: {version}-1
Section: utils
Priority: optional
Architecture: amd64
Maintainer: osu-diff maintainers <noreply@localhost>
Installed-Size: {size}
Depends: libc6 (>= 2.36), libx11-6, libxext6, libxrender1, libxft2, libfontconfig1, ca-certificates, xdg-utils
Recommends: fonts-noto-cjk
Description: Local osu!mania 4K replay and beatmap collector
 Includes the Python and Tcl/Tk runtimes. Game files are accessed read-only.
""")
        target = output / f"{NAME}_{version}-1_amd64.deb"
        run("dpkg-deb", "--root-owner-group", "--build", deb, target)
        products.append(target)

        rpm = work / "rpm"
        spec = rpm / "SPECS/collector.spec"
        write(spec, f"""%global __os_install_post %{{nil}}
%global _build_id_links none
Name: {NAME}
Version: {version}
Release: 1
Summary: Local osu!mania 4K replay and beatmap collector
License: AGPL-3.0-only
BuildArch: x86_64
AutoReqProv: no
Requires: glibc >= 2.36, libX11, libXext, libXrender, libXft, fontconfig, ca-certificates, xdg-utils
%description
Collect local osu!mania 4K replays and beatmaps with bundled Python and Tcl/Tk.
%prep
%build
%install
mkdir -p %{{buildroot}}
cp -a {tree}/. %{{buildroot}}/
%files
/opt/{NAME}
/usr/bin/{NAME}
/usr/share/applications/{NAME}.desktop
/usr/share/icons/hicolor/scalable/apps/{NAME}.svg
/usr/share/doc/{NAME}
/usr/share/licenses/{NAME}
""")
        run("rpmbuild", "-bb", "--define", f"_topdir {rpm}", spec)
        target = output / f"{NAME}-{version}-1.x86_64.rpm"
        shutil.copyfile(next((rpm / "RPMS/x86_64").glob("*.rpm")), target)
        products.append(target)

        arch = work / "arch"
        shutil.copytree(tree, arch)
        write(arch / ".PKGINFO", f"""pkgname = {NAME}
pkgbase = {NAME}
pkgver = {version}-1
pkgdesc = Local osu!mania 4K replay and beatmap collector
builddate = {int(time.time())}
packager = osu-diff maintainers
size = {size * 1024}
arch = x86_64
license = AGPL-3.0-only
depend = glibc>=2.36
depend = libx11
depend = libxext
depend = libxrender
depend = libxft
depend = fontconfig
depend = ca-certificates
depend = xdg-utils
optdepend = noto-fonts-cjk: Chinese UI fonts
""")
        archive = work / "arch.tar"
        tree_archive(arch, archive, compression="")
        target = output / f"{NAME}-{version}-1-x86_64.pkg.tar.zst"
        run("zstd", "-q", "-f", "-19", archive, "-o", target)
        products.append(target)

        appdir = work / "Collector.AppDir"
        shutil.copytree(payload, appdir / "usr/lib" / NAME)
        write(appdir / "AppRun", f'#!/bin/sh\nAPPDIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\nexec "$APPDIR/usr/lib/{NAME}/{NAME}" "$@"\n', 0o755)
        write(appdir / f"{NAME}.desktop", DESKTOP)
        write(appdir / f"{NAME}.svg", ICON)
        target = output / f"{NAME}-{version}-x86_64.AppImage"
        run(appimagetool, "--appimage-extract-and-run", "--no-appstream", appdir, target,
            env=dict(os.environ, ARCH="x86_64"))
        products.append(target)
        run(target, "--appimage-extract-and-run", "--help", stdout=subprocess.DEVNULL)

    import PyInstaller
    metadata = {"version": version, "architecture": platform.machine(), "glibc_minimum": "2.36",
                "python": sys.version, "pyinstaller": PyInstaller.__version__,
                "appimagetool_sha256": hashlib.sha256(appimagetool.read_bytes()).hexdigest(),
                "packages": [path.name for path in products]}
    write(output / "build-info.json", json.dumps(metadata, indent=2) + "\n")
    write(output / "SHA256SUMS", "".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
                                         for path in products))
    for path in products:
        print(path)


if __name__ == "__main__":
    main()
