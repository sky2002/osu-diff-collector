# 采集范围、隐私与包格式

## 发现与读取

Windows 只读查询 osu! 的安装记录与文件关联，从配置里的 `BeatmapDirectory`
和 `storage.ini` 的 `FullPath` 找到实际数据位置，不执行注册表里的命令。
Linux 支持 XDG 数据位置、Flatpak lazer、Wine 及常见 Bottles 前缀；自定义
Proton/Lutris 安装可设置 `WINEPREFIX` 或在界面中选目录。

stable 扫描 `Data/r`、`Replays`，lazer 扫描 `files` 的文件头及 `exports`。
replay 必须属于 mania，且精确匹配 MD5 的原始 `.osu` 必须为 Mode 3、CircleSize 4。
其他键数、转谱、双舞台、缺谱或无法判断的文件被跳过。lazer 现代扩展版本
30000001–30000019 需成功解析 mods；未知版本/Mod 保守跳过。

谱面读取上限 16 MiB、replay 单字符串上限 1 MiB、现代扩展压缩/解压数据上限
4 MiB、LZMA 内存上限 64 MiB。不会解压 replay 的按键帧，不重建成绩或判定。
客户端来源表示本次从哪里采集，不能证明 replay 最初在哪个客户端录制。

## ZIP 内容

- `objects/<SHA-256>`：去重后的完整原始 replay 和谱面字节。
- `manifest.json` / `inventory.json`：对象哈希、长度、类型、提交代号、电脑 ID、客户端列表和批次号。
- `collection-log.json`：来源目录、收集/跳过统计、错误及来源对象列表，可能包含完整本地路径。

合并导出跨客户端去重；分开导出时每包都带所需谱面。同次分开导出共享批次号；
每次运行新建批次号。提交代号用于来源管理，不能当作玩家身份。
ZIP 使用 ZIP64 / 存储模式，不按大小拆分；临时副本与最终 ZIP 需要相应空闲空间。
正常结束或捕获到错误时清理本次临时文件，已有 ZIP 与游戏原件保留。
强制结束进程可能留下临时文件。建议采集时停止游戏写入；扫描不是事务快照。

`python -m osu_diff verify package.zip` 检查结构、大小和哈希，默认接受不超过
4 GiB 的包、16 MiB 的清单/日志；导出端没有相同的总量限制。校验成功不等于
成绩有效，也不验证玩家身份；超大导出包需要使用方另行处理。

## 隐私

程序没有上传、下载或遥测功能。游戏数据只读，不复制 Realm/成绩数据库、登录配置、
音频、背景或视频。原始 replay 仍含玩家名和游玩记录，日志可能含本地路径。
发送 ZIP 前应确认接收者和用途。公开这个程序的源码不等于公开参与者的数据。

Windows 的 `collection_machine.id` 用固定项目命名空间对 MachineGuid 做 SHA-256；
Linux 用项目专用 HMAC-SHA-256 从 `/etc/machine-id`（备用 `/var/lib/dbus/machine-id`）派生。
原始系统标识不会进入 ZIP。固定命名空间是公开算法常量，不是认证秘密。
保持派生方案与历史导出器一致，避免同一系统的来源 ID 因源码拆分变化。
读取不到有效标识会明确失败，不随机生成或继承其他人的电脑 ID。

这是可关联的系统安装标识，不是匿名化保证、硬件证明或防伪认证。重装可能改变 ID，
克隆可能重复，双系统可能不同；它无法证明原始游玩电脑或玩家身份。

GUI 设置保存在 Windows 的 `%LOCALAPPDATA%/osu-diff/collector.json` 或 Linux 的
`$XDG_CONFIG_HOME/osu-diff/collector.json`（默认 `~/.config/osu-diff/`）。

## 格式依据

- [osu! replay 文件格式](https://osu.ppy.sh/wiki/en/Client/File_formats/osr_(file_format))
- [osu! 谱面文件格式](https://osu.ppy.sh/wiki/en/Client/File_formats/osu_(file_format))
- [lazer 文件存储](https://osu.ppy.sh/wiki/en/Client/Release_stream/Lazer/File_storage)
- [LegacyScoreEncoder](https://github.com/ppy/osu/blob/master/osu.Game/Scoring/Legacy/LegacyScoreEncoder.cs)
- [LegacyReplaySoloScoreInfo](https://github.com/ppy/osu/blob/master/osu.Game/Scoring/Legacy/LegacyReplaySoloScoreInfo.cs)
