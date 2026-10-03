# osu-diff Collector

导出本机 osu!mania **原生 4K** replay 与对应谱面，支持 Windows x64 和 Linux x86_64。

v0.1.1 可同时导出 stable 和 lazer，自选合成一个 ZIP 或按客户端分为两个 ZIP。已移除上传、上传码与续传功能，导出后自行发送文件。

## 下载

前往 [最新发布页](https://github.com/sky2002/osu-diff-collector/releases/latest)。

| 系统 / 方式 | 文件 |
| --- | --- |
| Windows x64 | `osu-diff-collector.exe`，双击启动 |
| Linux 免安装 | `osu-diff-collector-0.1.1-x86_64.AppImage` |
| Debian 12+ / Ubuntu 24.04+ | `osu-diff-collector_0.1.1-1_amd64.deb` |
| Fedora / openSUSE | `osu-diff-collector-0.1.1-1.x86_64.rpm` |
| Arch / Manjaro | `osu-diff-collector-0.1.1-1-x86_64.pkg.tar.zst` |
| Linux 通用解压版 | `osu-diff-collector-0.1.1-linux-x86_64.tar.gz` |

安装包自带 Python / Tk，无需安装 Python。Linux 要求 **x86_64、glibc 2.36+、X11 或 XWayland**，不适用于 Ubuntu 22.04、Debian 11 或 Alpine/musl。中文界面需要系统中文字体（例如 Noto CJK）。

```bash
chmod +x osu-diff-collector-0.1.1-x86_64.AppImage
./osu-diff-collector-0.1.1-x86_64.AppImage
# 没有 FUSE 时：
./osu-diff-collector-0.1.1-x86_64.AppImage --appimage-extract-and-run
```

DEB 使用 `sudo apt install ./文件名.deb`，RPM 使用 `sudo dnf install ./文件名.rpm` 或 `sudo zypper install ./文件名.rpm`，Arch 包使用 `sudo pacman -U ./文件名.pkg.tar.zst`。安装后从应用菜单启动 osu-diff Collector；tar.gz 解压后运行目录内同名程序。不要用 sudo 启动导出器。

## 使用

1. 分别确认 stable / lazer 目录，勾选要导出的客户端，可同时勾选，也可只选一个。
2. 选择 **合并为一个 ZIP** 或 **按客户端分开（两个 ZIP）**；只选一端时始终生成一个 ZIP。
3. 选择保存位置，点击 **开始导出**。
4. 将完成提示中列出的全部 ZIP 手动发给组织者。

合并包按内容哈希去重；分开时每包均包含所需谱面、清单和日志，可独立接收。已完成的 ZIP 保留；原有文件和游戏原件不变，正常完成后临时文件自动清理。

只收集能确认属于原生 mania 4K 的 replay 和对应谱面，跳过其他模式、其他键数、转谱、缺谱和无法确认的文件。不会下载游戏服务器上未保存到本机的 replay。无符合条件的 replay 时仍生成清单及原因日志，并显示提示。

## Linux 游戏位置

- lazer：`$XDG_DATA_HOME/osu`，默认 `~/.local/share/osu`，跟随数据目录迁移配置。
- Flatpak lazer：`~/.var/app/sh.ppy.osu/data/osu`。
- stable：支持 Wine 和常见 Bottles 前缀。自定义 Lutris / Proton / Wine 安装可设置 `WINEPREFIX` 或手动选目录。

## 如何关联同一台电脑的导出包

`manifest.json` 的 **`collection_machine.id`** 是采集系统的应用专用哈希 ID。Windows 根据系统安装标识派生，Linux 根据 `/etc/machine-id`（备用 `/var/lib/dbus/machine-id`）派生，不写入原始系统标识。

同一系统安装下，stable / lazer、保存位置及重复导出不影响 ID；同次分开的两个包还共享 **`collection_batch_id`**，每次导出会产生新批次。

这是采集时的系统来源，不能证明玩家身份、硬件或 replay 原始游玩电脑。重装 / 更换系统标识可能改变 ID，克隆可能重复；同一硬件上的 Windows / Linux 双系统和不同 Linux 系统安装可能得到不同 ID。

包内还包含原始 replay 内的玩家名及可能含本地路径的日志。不复制游戏登录配置。没有网络上传功能。

## 校验与验证范围

发布页附带 `SHA256SUMS`。Linux：`sha256sum -c SHA256SUMS --ignore-missing`；Windows：`Get-FileHash .\osu-diff-collector.exe -Algorithm SHA256`。

Windows 与 Debian 12 各运行 72 项回归测试，无失败，分别跳过 1 / 3 项平台专属检查。五种 Linux 包逐一验证解包、CLI、Xvfb 界面启动、合成 stable / lazer 合并与分开导出、ZIP 哈希及重复导出的电脑 ID 一致性。五种包内二进制一致，ELF 的最高 GLIBC 符号要求为 2.36。

未逐一在所有发行版真实桌面上人工验收，也未重新扫描参与者真实游戏库。本仓库用于发布二进制与使用说明，旧版本保留在 Releases。
