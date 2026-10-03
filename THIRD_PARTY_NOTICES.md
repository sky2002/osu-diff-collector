# Third-party notices

The collector's own source is Copyright (C) 2026 sky2002 and is licensed under
GNU Affero General Public License version 3 only (`AGPL-3.0-only`); see LICENSE.
Third-party components keep their own licenses. Collected replay and beatmap
files are user inputs and are not licensed by this software's license.

## Source dependencies

The application uses the Python standard library, including Tkinter. It does
not vendor osu! game code, game binaries, judgement engines, research models,
replays, songs, or account databases. Its metadata reader implements the public
osu! file formats. Format references are listed in docs/collection.md.

The four-column SVG in the Linux build script is project source under AGPLv3;
it is not the osu! logo. This project is not affiliated with or endorsed by ppy.

## Bundled runtimes

Source/zipapp users supply their own Python and Tcl/Tk installations. Frozen
Windows and Linux builds contain runtime components with separate terms:

| Component | License / original source |
| --- | --- |
| CPython and included components | PSF License and included third-party notices; https://docs.python.org/3/license.html |
| Tcl | Tcl license (BSD-style); `licenses/Tcl.txt`; https://github.com/tcltk/tcl |
| Tk | Tk license (BSD-style); `licenses/Tk.txt`; https://github.com/tcltk/tk |
| PyInstaller bootloader | GPLv2 with the bootloader exception; https://pyinstaller.org/en/stable/license.html |
| Linux shared libraries | The build collects each actual Debian package's copyright file and version/source-package metadata, plus referenced common license texts. |
| AppImage runtime | Separate from appimagetool; use the runtime's own license and corresponding source at https://github.com/AppImage/type2-runtime. Record the exact runtime used when distributing AppImages. |

The vendored Tcl/Tk notice texts are from the official `core-8-6-16` tags:
https://github.com/tcltk/tcl/blob/core-8-6-16/license.terms and
https://github.com/tcltk/tk/blob/core-8-6-16/license.terms. Runtime-specific notice
files present in the Windows Python installation are additionally copied.

`tools/runtime_licenses.py` copies notices for the **actual build environment**
and emits `runtime-inventory.json`. On Linux it fails if a bundled binary has
no identifiable Debian package/copyright file. On Windows it copies the
official Python distribution's complete LICENSE.txt and Tcl/Tk notices.
Builds may also contain the Microsoft Visual C++ runtime supplied with Python;
that runtime remains subject to Microsoft's redistribution terms, not AGPL.

Notices alone do not satisfy every source-distribution or relinking obligation.
Before publishing a frozen build, review the generated inventory and provide
the corresponding source for components whose licenses require it, including
any modifications. See docs/building.md. The Python/AGPL labels do not relicense
third-party libraries or give permission to redistribute user data.

## Historical downloads

Releases v0.1.0 and v0.1.1 predate this standalone source tree. Their existing
assets are retained; this document does not claim that they contain the new
notice bundle or were built from this source revision.
