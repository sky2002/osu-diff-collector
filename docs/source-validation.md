# 独立源码发布验证（2026-10-03）

验证对象：源码开发版 **0.1.2.dev0**。这是 v0.1.1 项目中导出功能的独立提取，
不代表旧 Release 可由此版本源码逐字节重建。本次不覆盖或新增二进制 Release。

| 检查 | 实际结果 |
| --- | --- |
| Windows 11 / Python 3.13.7 回归测试 | 36 项，35 通过，1 项 POSIX 设置测试跳过 |
| Debian 12 / Python 3.11.2 / Xvfb 回归测试 | 36 项，34 通过，2 项 Windows 专属测试跳过 |
| zipapp | 构建成功；CLI、合并/分开导出、哈希、清理、跨次电脑 ID 检查通过 |
| Windows EXE / PyInstaller 6.21.0 | 构建成功；同上实际导出检查通过 |
| Python wheel | 使用 setuptools 82.0.1 构建成功，应用无第三方 Python 运行依赖 |
| Linux tar.gz、DEB、RPM、Arch、AppImage | 五种格式构建成功，逐包验收通过 |
| Linux GUI | 五种成品在 Xvfb 下启动，无启动错误；源码 GUI 测试实际操作导出流程 |
| Linux ABI | 五种成品打包 ELF 的最高 GLIBC 符号要求不超过 2.36 |
| 成品范围 | Windows EXE、五种 Linux 包均不含 Dataset、判定后端、上传/收件服务或下载器模块 |
| 许可文件 | Windows EXE 含 AGPL、Python、Tcl/Tk 等通知；Linux 包含 AGPL、实际捆绑 Debian 库的版权文件及运行库清单 |

所有游戏输入均由 `tests/samples.py` 合成，未重新扫描真实玩家游戏库。
Windows 权限回归使用合成目录，未人工执行 UAC“以管理员身份运行”。
Linux 在 Debian 12 chroot 中验证；未在每个发行版真实桌面人工验收，也未做
RPM/Arch 的原生安装卸载测试。AppImage 验证时 chroot 需要挂载 `/proc`。

公开树按文件清单提取，只包含程序、测试、许可证、构建与使用文档及 CI 配置。
常见凭据、私有本机路径和硬编码服务器 IP 模式检查无命中；不包含研究仓库历史、
参与者数据或部署配置。这是限定范围的发布检查，不是完整安全审计。

分发新的二进制前仍需按 [构建说明](building.md) 核对每个捆绑组件的再分发与
对应源码要求。已经完成的本地构建验证不等于已经发布这些二进制资产。
