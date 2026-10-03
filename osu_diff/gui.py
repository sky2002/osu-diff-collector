# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 sky2002

"""Participant UI: select stable/lazer, collect locally, then share ZIPs."""

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .game_collection import collect_and_pack, discover_games, inspect_game
from .desktop import open_directory
from .local_settings import collector_submission_id, load_settings, save_settings


class CollectorWindow:
    def __init__(self, root):
        self.root = root
        self.messages = queue.Queue()
        self.busy = False
        self.controls = []
        self.share_directory = None
        self.detected = {client: [] for client in ("stable", "lazer")}
        self.game_paths = {client: tk.StringVar() for client in self.detected}
        self.enabled = {client: tk.BooleanVar(value=False) for client in self.detected}
        self.games = {}
        settings = load_settings("collector")
        self.output = tk.StringVar(value=settings.get("output", ""))
        mode = settings.get("package_mode", "combined")
        self.package_mode = tk.StringVar(value=mode if mode in ("combined", "separate") else "combined")
        self.status = tk.StringVar(value="正在查找本机的 osu! 安装和数据目录…")
        root.title("osu-diff · mania 4K 谱面与 replay 导出")
        root.geometry("960x760")
        root.minsize(900, 710)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="选择游戏，导出 replay 与谱面", font=("Microsoft YaHei UI" if os.name == "nt" else "sans-serif", 17)).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="可同时勾选 stable 和 lazer，收集本地能确认属于原生 mania 4K 的 replay 和对应谱面。\n"
                             "导出到本机后，请自行将 ZIP 发给组织者。游戏原文件只读访问。").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(0, 14))
        for row, client in enumerate(self.detected, 2):
            checkbox = ttk.Checkbutton(frame, text="osu! " + client, variable=self.enabled[client])
            checkbox.grid(row=row, column=0, sticky="w", padx=(0, 12))
            self.controls.append(checkbox)
            entry = ttk.Combobox(frame, textvariable=self.game_paths[client])
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=7)
            self.games[client] = entry
            self.controls.append(entry)
            self.button(frame, "选择文件夹…", lambda client=client: self.choose_game(client), row, 3)
        self.button(frame, "重新查找", self.detect_games, 4, 3)
        ttk.Label(frame, text="勾选要导出的客户端；只选一个时，两种打包方式都生成一个 ZIP。").grid(
            row=4, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="打包方式").grid(row=5, column=0, sticky="w", padx=(0, 12))
        modes = ttk.Frame(frame)
        modes.grid(row=5, column=1, columnspan=3, sticky="w", pady=7)
        for title, value in (("合并为一个 ZIP（默认）", "combined"), ("按客户端分开（两个 ZIP）", "separate")):
            option = ttk.Radiobutton(modes, text=title, variable=self.package_mode, value=value)
            option.pack(side="left", padx=(0, 20))
            self.controls.append(option)
        ttk.Label(frame, text="保存位置").grid(row=6, column=0, sticky="w", padx=(0, 12))
        destination = ttk.Entry(frame, textvariable=self.output)
        destination.grid(row=6, column=1, columnspan=2, sticky="ew", pady=7)
        self.controls.append(destination)
        self.button(frame, "选择文件夹…", self.choose_output, 6, 3)
        ttk.Label(frame, text="首次扫描大型文件库可能需要几分钟。非 4K、缺谱及无法确认的 replay 会跳过并提示。\n"
                             "每个 ZIP 均包含对应原始文件、清单和日志；同一电脑导出的包带有相同的采集电脑 ID。").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=12)
        actions = ttk.Frame(frame)
        actions.grid(row=8, column=0, columnspan=4, sticky="w", pady=(0, 12))
        for title, callback in (("开始导出", self.collect), ("打开保存位置", self.open_output)):
            button = ttk.Button(actions, text=title, command=callback)
            button.pack(side="left", padx=(0, 12), ipady=4)
            self.controls.append(button)
        ttk.Label(frame, textvariable=self.status, wraplength=850).grid(
            row=9, column=0, columnspan=4, sticky="w", pady=(0, 6))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=10, column=0, columnspan=4, sticky="ew")
        self.log = tk.Text(frame, height=10, wrap="word", state="disabled")
        self.log.grid(row=11, column=0, columnspan=4, sticky="nsew", pady=(10, 0))
        frame.rowconfigure(11, weight=1)
        ttk.Label(frame, text="包内含原始玩家名、采集电脑 ID，以及可能含本地路径的采集日志。\n"
                             "采集电脑 ID 用于关联导出来源，不代表玩家身份或原始游玩电脑。").grid(
            row=12, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.poll_id = root.after(100, self.poll)
        self.detect_id = root.after(10, self.detect_games)

    def button(self, frame, title, callback, row, column):
        button = ttk.Button(frame, text=title, command=callback)
        button.grid(row=row, column=column, padx=(8, 0), pady=7)
        self.controls.append(button)

    def detect_games(self):
        if self.busy:
            return
        games = discover_games()
        for client in self.detected:
            paths = [game["path"] for game in games if game["client"] == client]
            self.detected[client] = paths
            self.games[client].configure(values=paths)
            if not self.game_paths[client].get() and paths:
                self.game_paths[client].set(paths[0])
                self.enabled[client].set(True)
        self.status.set(f"找到 {len(games)} 个游戏位置，请确认勾选的客户端和目录。" if games else
                        "没有自动找到游戏。请为要导出的客户端选择安装目录或数据目录。")

    def choose_game(self, client):
        path = filedialog.askdirectory(parent=self.root, title=f"选择 osu! {client} 安装目录或数据目录")
        if path:
            self.game_paths[client].set(path)
            self.enabled[client].set(True)

    def choose_output(self):
        path = filedialog.askdirectory(parent=self.root, title="选择导出结果的保存位置")
        if path:
            self.output.set(path)

    def write(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def collect(self):
        if self.busy:
            return
        output = self.output.get().strip()
        clients = [client for client in self.enabled if self.enabled[client].get()]
        mode = self.package_mode.get()
        if not clients or not output:
            messagebox.showerror("还需要选择位置", "请至少勾选一个客户端，并选择保存位置。", parent=self.root)
            return
        try:
            paths = []
            for client in clients:
                path = self.game_paths[client].get().strip()
                if not path:
                    raise ValueError(f"请选择 osu! {client} 的游戏位置。")
                game = inspect_game(path)
                if game["client"] != client:
                    raise ValueError(f"为 {client} 选择的目录实际属于 {game['client']}，请检查游戏位置。")
                paths.append(game["path"])
            submitter = collector_submission_id()
            save_settings("collector", {"output": output, "package_mode": mode})
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror("设置有误", str(error), parent=self.root)
            return
        self.share_directory = None
        self.busy = True
        for control in self.controls:
            control.configure(state="disabled")
        self.progress.start()
        self.status.set("正在查找本地 replay 与谱面…")

        def worker():
            try:
                result = collect_and_pack(paths, output, submitter_id=submitter, package_mode=mode,
                                          progress=lambda text: self.messages.put(("progress", text)))
                lines = []
                for source in result["sources"]:
                    skipped = source["skipped_replays"]
                    lines.append(f"{source['client']}：找到 {source['replays_found']} 份 replay，"
                                 f"收集 {source['collected_replays']} 份 mania 4K replay、"
                                 f"{source['matched_beatmaps']} 张对应谱面。")
                    lines.append(f"跳过：非 4K / 转谱 {skipped['out_of_scope']}，缺谱 {skipped['missing_beatmap']}，"
                                 f"无法确认 {skipped['unverifiable']}，复制失败 {skipped['copy_failed']}。")
                    if not source["collected_replays"]:
                        lines.append(f"{source['client']} 未收集到符合条件的 replay，原因已记录在 ZIP 日志中。")
                lines.extend([f"文件访问错误 {result['counts']['failed']}；详细日志已放进 ZIP。",
                              f"提交代号：{result['submitter_id']}",
                              f"采集电脑 ID：{result['collection_machine']['id']}",
                              f"已生成 {len(result['parts'])} 个 ZIP，请发送以下文件：", *result["parts"]])
                self.messages.put(("done", ("\n".join(lines), result["share_directory"])))
            except Exception as error:
                self.messages.put(("error", str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        while True:
            try:
                kind, message = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self.status.set(message)
                continue
            self.busy = False
            self.progress.stop()
            for control in self.controls:
                control.configure(state="normal")
            self.status.set("本次导出已结束，请查看下方结果。" if kind == "done" else "导出未完成，请查看下方原因。")
            if kind == "done":
                message, self.share_directory = message
            self.write(message if kind == "done" else "操作失败：" + message)
        self.poll_id = self.root.after(100, self.poll)

    def open_output(self):
        directory = self.share_directory or self.output.get().strip()
        if directory and Path(directory).is_dir():
            try:
                open_directory(directory)
            except OSError as error:
                messagebox.showerror("无法打开保存位置", str(error), parent=self.root)
        else:
            messagebox.showinfo("请选择保存位置", "请先选择存在的保存目录。", parent=self.root)

    def close(self):
        if self.busy and not messagebox.askyesno("正在处理", "关闭会中断本次导出，可能留下未完成的临时文件。确认关闭？", parent=self.root):
            return
        self.root.after_cancel(self.poll_id)
        self.root.after_cancel(self.detect_id)
        self.root.destroy()


def main():
    root = tk.Tk()
    CollectorWindow(root)
    root.mainloop()
    return 0
