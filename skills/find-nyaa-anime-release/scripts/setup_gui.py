"""Open optional local onboarding, without sending secrets through the agent."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser

from runtime_paths import DEFAULT_STATE
from local_setup import connect_token, load_settings, save_settings, setup_status
from watch_v3.bangumi_client import TOKEN_URL


def window(state, ready=None, section='bangumi'):
    import tkinter as tk
    from tkinter import filedialog, ttk

    root = tk.Tk()
    root.title('动漫追番 - ' + ('Bangumi 连接' if section == 'bangumi' else 'qBittorrent 设置'))
    root.geometry('690x380')
    root.minsize(650, 360)
    style = ttk.Style(root)
    if 'vista' in style.theme_names():
        style.theme_use('vista')
    style.configure('.', font=('Microsoft YaHei UI' if os.name == 'nt' else 'Sans', 10))
    style.configure('Heading.TLabel', font=('Microsoft YaHei UI' if os.name == 'nt' else 'Sans', 17, 'bold'))
    body = ttk.Frame(root, padding=24)
    body.pack(fill='both', expand=True)
    body.columnconfigure(0, weight=1)
    ttk.Label(body, text='Bangumi 连接' if section == 'bangumi' else 'qBittorrent 设置', style='Heading.TLabel').grid(row=0, column=0, sticky='w')
    ttk.Label(body, text='可选配置，不影响查找资源和获取磁力链接。', wraplength=620).grid(row=1, column=0, sticky='w', pady=(8, 12))
    current = load_settings(state)
    status = setup_status(state)
    token = tk.StringVar()
    exe = tk.StringVar(value=current.get('qbittorrent_exe', ''))
    folder = tk.StringVar(value=current.get('download_directory', ''))
    message = tk.StringVar(value='已连接 Bangumi：' + status['bangumi_username'] if status['bangumi_connected'] else 'Bangumi 未连接（可选）')
    bgm = ttk.LabelFrame(body, text='Bangumi · 个人追番同步（可选）', padding=12)
    if section == 'bangumi':
        bgm.grid(row=2, column=0, sticky='ew')
    bgm.columnconfigure(0, weight=1)
    ttk.Label(bgm, text='Access Token', anchor='w').grid(row=0, column=0, sticky='w')
    token_entry = ttk.Entry(bgm, textvariable=token, show='*')
    token_entry.grid(row=1, column=0, sticky='ew', pady=5)
    actions = ttk.Frame(bgm)
    actions.grid(row=2, column=0, sticky='w', pady=(2, 6))
    ttk.Button(actions, text='创建 Token（官网）', command=lambda: webbrowser.open(TOKEN_URL)).pack(side='left')
    results = queue.Queue()
    busy = False

    def verify():
        nonlocal busy
        if busy:
            return
        value = token.get()
        if not value.strip():
            message.set('请在上方填写 Access Token。')
            return
        busy = True
        connect_button.configure(state='disabled')
        token_entry.configure(state='disabled')
        message.set('正在验证 Bangumi 账号…')

        def work():
            try:
                connect_token(state, value)
                results.put(True)
            except Exception:
                results.put(False)
        threading.Thread(target=work, daemon=True).start()

    connect_button = ttk.Button(actions, text='验证并连接', command=verify)
    connect_button.pack(side='left', padx=8)
    ttk.Label(bgm, text='Token 仅保存在本机；仅发送到 Bangumi 官方 API 验证，不进入聊天。\n连接后可读收藏；成功交付的正篇按已看同步，明确说看完也会写回。', wraplength=600).grid(row=3, column=0, sticky='w')
    qb = ttk.LabelFrame(body, text='qBittorrent · 提交下载（可选，本机客户端）', padding=12)
    if section == 'qbittorrent':
        qb.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        message.set('程序位置留空时自动检测；下载目录留空时使用宿主默认目录。')
    qb.columnconfigure(0, weight=1)
    for row, label, variable, picker in [(0, '程序位置', exe, lambda: filedialog.askopenfilename(parent=root, title='选择 qBittorrent 程序')),
                                          (2, '下载目录', folder, lambda: filedialog.askdirectory(parent=root, title='选择下载目录'))]:
        ttk.Label(qb, text=label).grid(row=row, column=0, sticky='w')
        ttk.Entry(qb, textvariable=variable).grid(row=row+1, column=0, sticky='ew', pady=(4, 8))
        def browse(v=variable, choose=picker):
            selected = choose()
            if selected:
                v.set(selected)
        ttk.Button(qb, text='浏览…', command=browse).grid(row=row+1, column=1, padx=(8, 0), pady=(4, 8))
    ttk.Label(body, textvariable=message, wraplength=620).grid(row=3, column=0, sticky='w', pady=(8, 8))
    footer = ttk.Frame(body)
    footer.grid(row=4, column=0, sticky='e', pady=6)

    def finish():
        if busy:
            message.set('请等待账号验证结束。')
            return
        if token.get().strip():
            message.set('Token 尚未验证保存。请点击“验证并连接”，或清空 Token 后继续。')
            return
        try:
            save_settings(state, executable=exe.get(), download_directory=folder.get())
            root.destroy()
        except Exception:
            message.set('保存失败：请确认程序文件和下载目录存在，且本机配置目录可写。')

    if section == 'qbittorrent':
        ttk.Button(footer, text='保存', command=finish).pack(side='left')

    def close():
        if not busy:
            root.destroy()
        else:
            message.set('正在验证账号，请稍候再关闭。')
    root.protocol('WM_DELETE_WINDOW', close)
    ttk.Button(footer, text='关闭', command=close).pack(side='left', padx=(8, 0))

    def poll():
        nonlocal busy
        try:
            ok = results.get_nowait()
            busy = False
            connect_button.configure(state='normal')
            token_entry.configure(state='normal')
            if ok:
                token.set('')
                message.set('Bangumi 已连接并保存，可以关闭窗口继续使用。')
            else:
                message.set('连接失败：请检查 Token、网络或账号是否与现有记录一致。原配置未更改。')
        except queue.Empty:
            pass
        root.after(100, poll)
    root.after(100, poll)
    root.update()
    root.lift()
    root.attributes('-topmost', True)
    root.after(600, lambda: root.attributes('-topmost', False))
    if ready:
        Path(ready).write_text('ready', encoding='ascii')
    root.mainloop()


def launch(state, section):
    executable = Path(sys.executable)
    if os.name == 'nt' and executable.with_name('pythonw.exe').exists():
        executable = executable.with_name('pythonw.exe')
    with tempfile.TemporaryDirectory(prefix='anime-setup-') as tmp:
        ready = Path(tmp) / 'ready'
        child = subprocess.Popen([str(executable), str(Path(__file__).resolve()), '--state', str(Path(state).resolve()),
                                  '--window', '--section', section, '--ready-file', str(ready)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                 start_new_session=os.name != 'nt')
        for _ in range(100):
            if ready.exists():
                return {'status': 'setup_opened', 'section': section, 'message': '请在本机小窗口填写并保存，完成后继续。'}
            if child.poll() is not None:
                break
            time.sleep(.1)
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
    return {'status': 'gui_unavailable', 'message': '无法打开本机窗口。需要带桌面的 Python/Tk 环境；远程主机请使用令牌文件配置。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--status', action='store_true')
    group.add_argument('--window', action='store_true')
    parser.add_argument('--section', choices=['bangumi', 'qbittorrent'], default='bangumi')
    parser.add_argument('--ready-file', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.window:
        window(args.state, args.ready_file, args.section)
        return 0
    try:
        status = setup_status(args.state)
        result = status if args.status else launch(args.state, args.section)
    except Exception:
        result = {'status': 'setup_failed', 'message': '本机配置无法读取，请检查权限或配置格式；原文件未修改。'}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] in {'setup_complete', 'setup_required', 'setup_opened'} else 1


if __name__ == '__main__':
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
