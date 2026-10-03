# 从源码运行、构建和验证

源码版本为 **0.1.2.dev0**，是从 v0.1.1 所用项目提取出的独立导出器。
保留采集与电脑 ID 算法，去除 Dataset、判定后端、训练、收件服务和下载器；
增加独立 ZIP 校验命令、许可证和构建依赖清单。旧 Release 不是该源码的构建结果。

## 源码运行

需要 Python 3.11+。Windows 推荐 python.org 安装包并安装 Tcl/Tk；
Debian/Ubuntu 安装 `python3-tk`。应用没有第三方 Python 运行依赖。

```bash
python -m osu_diff                 # GUI
python -m osu_diff --help
python -m osu_diff discover
python -m osu_diff collect-game /path/to/osu --output /path/to/export
python -m osu_diff verify /path/to/export.zip
python -m unittest discover -v
```

GUI 测试需要显示服务，Linux 无桌面时使用 `xvfb-run -a python -m unittest discover -v`。
安装为命令可运行 `python -m pip install .`，之后使用 `osu-diff-collector`。
测试只创建合成谱面/replay 和临时目录，不需要参与者数据。

## 可选 zipapp

```bash
python tools/build_collector.py
python dist/osu-diff-collector.pyz --help
```

不带参数启动 GUI。它包含源码和项目许可文件，不捆绑 Python/Tk，需本机提供。

## Windows EXE

在 Windows x64 的独立 Python 环境中：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python tools/build_exe.py
dist\osu-diff-collector.exe --help
python tools/test_portable.py dist/osu-diff-collector.exe
```

输出 `dist/osu-diff-collector.exe`，只构建导出器。`tools/collector.spec` 根据实际
PyInstaller 依赖收集许可文件，并把它们嵌入 `licenses/`。构建中间目录同时保留
可检查的许可文件和运行库清单。Python 与系统补丁版本可能影响字节结果；不承诺逐字节可重现。

## Linux 五种格式

在 **Debian 12 x86_64 / glibc 2.36** 中构建，可用容器或独立 chroot：

```bash
sudo apt-get install python3-venv python3-tk libpython3.11 binutils rpm squashfs-tools zstd file curl ca-certificates desktop-file-utils xvfb xauth cpio
python3 -m venv .venv
.venv/bin/pip install -r requirements-build.txt
```

从 [官方 appimagetool Release](https://github.com/AppImage/appimagetool/releases)
选择 x86_64 文件并记录审核过的 SHA-256。持续发布下载地址可变化，不把它当作版本锁。
构建参数要求提供预期哈希：

```bash
chmod +x /path/to/appimagetool
.venv/bin/python tools/build_linux_collector.py \
  --appimagetool /path/to/appimagetool \
  --appimagetool-sha256 YOUR_REVIEWED_SHA256
.venv/bin/python tools/test_linux_release.py
```

输出在 `dist/linux-x86_64/`：AppImage、DEB、RPM、Arch `.pkg.tar.zst`、tar.gz，
以及 `SHA256SUMS`、`build-info.json`。测试逐包解开检查 CLI、合成双客户端导出、
电脑 ID、ZIP 哈希、临时文件清理、Xvfb GUI 启动和 GLIBC 符号版本。
构建需要临时目录允许执行程序；chroot 还需要正常的 `/proc` 和 `/dev`。
AppImage 工具可能下载运行时，需要网络；分发前
固定并记录运行时版本和哈希，保留其对应源码。该步骤不等于各发行版原生安装验收。

Linux 包的许可元数据为 `AGPL-3.0-only`。二进制目录的 `_internal/licenses/`
包含本项目许可、实际捆绑 Debian 库的版权文件、版本/源码包名称和共用许可文本；
DEB/RPM/Arch 还将副本安装到 `/usr/share/licenses/osu-diff-collector/`。
不带入本机构建目录或玩家数据。

## 发布二进制时

1. 钉住源码 commit/tag，运行两平台测试，检查成品仅包含导出器模块。
2. 在同一下载处提供对应源码及这些构建脚本，不用本仓库最新 main 冒充旧成品对应源码。
3. 审核 `runtime-inventory.json` 和各组件版权文件。对要求提供源码的捆绑库，保存并提供
   精确版本的源码及补丁；Debian 库可按记录的 source package/version 获取相应 Debian
   source package。保持动态库可替换，满足适用的 LGPL 等条款。通知文件不能替代这些义务。
4. 单独核对 AppImage runtime 的版本、许可及对应源码。Windows 构建遵守官方 Python
   所含 Microsoft 运行库的再分发条件。不要把第三方组件改标为自己的 AGPL 代码。
5. 发布校验和与实际测试范围。保留历史 Release，禁止用新成品覆盖旧版本文件。

这里仅公开源码与构建方式；不会自动发布、上传或覆盖 Releases 的二进制资产。
