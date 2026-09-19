# osu-diff Collector

用于收集本机 osu!mania **原生 4K** replay 及对应谱面的桌面工具，支持 Windows x64 和 Linux x86_64。

## 下载

到 [最新发布页](https://github.com/sky2002/osu-diff-collector/releases/latest) 下载适合系统的文件。

| 系统 / 方式 | 文件 |
| --- | --- |
| Windows x64 | `osu-diff-collector.exe`，双击启动 |
| Linux 免安装 | `osu-diff-collector-0.1.0-x86_64.AppImage` |
| Debian 12+ / Ubuntu 24.04+ | `osu-diff-collector_0.1.0-1_amd64.deb` |
| Fedora / openSUSE | `osu-diff-collector-0.1.0-1.x86_64.rpm` |
| Arch / Manjaro | `osu-diff-collector-0.1.0-1-x86_64.pkg.tar.zst` |
| Linux 通用解压版 | `osu-diff-collector-0.1.0-linux-x86_64.tar.gz` |

所有安装包均包含 Python 运行时，使用者无需安装 Python。Linux 版本要求 **glibc 2.36+**、X11 或 XWayland；不适用于 Alpine/musl、Ubuntu 22.04 或 Debian 11。中文界面需要系统中文字体（例如 Noto CJK）。

AppImage：

```bash
chmod +x osu-diff-collector-0.1.0-x86_64.AppImage
./osu-diff-collector-0.1.0-x86_64.AppImage
# 没有 FUSE 时使用：
./osu-diff-collector-0.1.0-x86_64.AppImage --appimage-extract-and-run
```

DEB 使用 `sudo apt install ./文件名.deb`，RPM 使用 `sudo dnf install ./文件名.rpm` 或 `sudo zypper install ./文件名.rpm`，Arch 包使用 `sudo pacman -U ./文件名.pkg.tar.zst`。安装后从应用菜单启动 **osu-diff Collector**，或运行 `osu-diff-collector`。tar.gz 解压后运行目录中的同名程序。不要用 sudo 启动采集器。

## 使用

1. 确认自动找到的游戏位置，或手动选择 stable / lazer 的游戏数据目录。
2. 选择有足够剩余空间的保存目录。
3. 填写组织者私下提供的上传码，点击 **收集并上传**。不需要注册账号，服务器地址已内置。
4. 也可点击 **仅收集打包**，把生成的一个 ZIP 发给组织者。

上传码由组织者直接提供，请勿发布到本仓库或 Issues。服务器校验成功后，仅本次上传的 ZIP 会自动清理；上传失败时保留 ZIP，可通过 **续传已有 ZIP** 重试。目录中原有文件和游戏原文件保留。

工具默认仅收集能确认属于原生 mania 4K 的 replay 和对应谱面，跳过其他模式、其他键数、转谱、缺谱和无法确认的文件。不会下载游戏服务器上尚未保存到本机的 replay。

## Linux 游戏位置

- lazer：`$XDG_DATA_HOME/osu`，默认 `~/.local/share/osu`，支持游戏配置里的数据目录迁移。
- Flatpak lazer：`~/.var/app/sh.ppy.osu/data/osu`。
- stable：支持 Wine，以及常见 Bottles 前缀。自定义 Lutris / Proton / Wine 安装可设置 `WINEPREFIX` 或手动选择数据目录。

## 采集信息

分享包包含原始 replay 和谱面、玩家名、采集电脑的应用专用哈希 ID，以及可能包含本地路径的采集日志。它不包含上传码，也不复制游戏账号配置。电脑 ID 用于区分采集来源，不代表玩家身份。

## 校验和与验证范围

发布页附带 `SHA256SUMS`。Linux 可运行 `sha256sum -c SHA256SUMS --ignore-missing`；Windows 可用 `Get-FileHash .\osu-diff-collector.exe -Algorithm SHA256` 对照。

Windows 和 Linux 均通过采集与传输回归测试。五种 Linux 包都在 Debian 12 环境验证了解包、CLI、图形界面启动及合成 stable/lazer 数据的采集打包；DEB 另完成实际安装测试。未逐一在所有发行版的真实桌面上验收。

本仓库用于发布收集器二进制和使用说明。
