"""Cheap, read-only setup guidance shared by both hosts. Never opens a window."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from local_setup import load_settings
from runtime_paths import DEFAULT_STATE
from watch_v3.bangumi_client import BangumiError, credentials, load_config


QUICK_START = '''**动漫搜索与自动追番**
用自然语言查找 Nyaa 动漫资源，核对作品、季集、体积和字幕；可选提交到 qBittorrent、定时追番及同步 Bangumi。需要能够运行本机脚本的 Agent，普通聊天窗口不能直接执行这些操作。

**可以这样说**
- “找《作品名》第 3 集，只要磁力，不下载。”
- “找《作品名》第一季全集，普通观看。”
- “找《电影名》蓝光资源。”
- “找《作品名》下一集，必须有中文字幕。”
- “找到合格版本后提交到 qBittorrent。”
- “每周六晚上检查《作品名》的下一集。”（需宿主支持定时任务）

不指定画质时默认轻量观看，正篇最低 1 GiB/集；中文字幕默认是偏好，必须有中文请明确说。已追踪的新番只说片名默认找下一目标集；仅返回链接不推进下载进度。
想了解画质、追番和 Bangumi 的具体规则，直接说“使用教程”。'''


def guidance(state, *, include_guide=False):
    lines = []
    try:
        account = load_config(state)
        if account:
            credentials(account)
        bangumi = 'configured_unverified' if account else 'not_configured'
    except (BangumiError, OSError, ValueError):
        bangumi = 'needs_repair'
    if bangumi != 'configured_unverified':
        lines.append('Bangumi（可选）：尚未完成可用的本机授权配置。绑定后可读取你的番单、评分和短评，并按约定同步观看记录；不影响找番决策。到 https://next.bgm.tv/demo/access-token 创建 Access Token，然后告诉我“连接 Bangumi”，我会打开填写 Token 的小窗口。不要把 Token 发到聊天里。')
    try:
        settings = load_settings(state)
        configured = settings.get('qbittorrent_exe') or os.environ.get('QBITTORRENT_EXE')
        exe = configured or shutil.which('qbittorrent') or shutil.which('qbittorrent.exe')
        qb = bool(exe and Path(exe).is_file())
        web_mode = settings.get('client') == 'webapi' or (
            not settings.get('client') and bool(settings.get('web_url')))
        username = os.environ.get('QBITTORRENT_USERNAME', settings.get('web_username'))
        password = os.environ.get('QBITTORRENT_PASSWORD', settings.get('web_password'))
        web = web_mode and bool(username and password)
        directory = settings.get('download_directory')
        # Remote download directories need not exist on the agent's machine.
        path_invalid = bool(directory and not web_mode and not Path(directory).is_dir())
        if web_mode:
            qb = False
    except (OSError, ValueError):
        qb, web, path_invalid = False, False, True
    if path_invalid or not (qb or web):
        lines.append('qBittorrent（可选）：快速检查尚未确认下载配置可用，不代表没有安装。仅搜索和返回磁力链接无需配置；需要直接提交下载时，告诉我“配置 qBittorrent”，我会先检测现有客户端，必要时打开小窗口填写程序位置和下载目录。远程 Web API 另行配置，不在聊天中发送密码。')
    sections = [QUICK_START] if lines or include_guide else []
    if lines:
        sections.append('首次使用提示：以下配置均可跳过，未配置不影响查找资源。\n\n' + '\n\n'.join(lines))
    if sections:
        sections.append('可以现在配置，也可以直接告诉我动漫名称。')
    return {'status': 'setup_guidance' if lines else 'usage_guide' if include_guide else 'configured_unverified', 'read_only': True,
            'bangumi': bangumi, 'reply_text': '\n\n'.join(sections),
            'note': '仅检查本机配置是否存在，未验证远程授权或下载器连接。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--guide', action='store_true', help='Show quick start even when locally configured')
    args = parser.parse_args(argv)
    print(json.dumps(guidance(args.state, include_guide=args.guide), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
