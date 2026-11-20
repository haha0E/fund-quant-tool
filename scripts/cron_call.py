"""任务计划专用：调本机 API（自动带 token）。cron_call.py <path> [method]

用法（任务计划程序注册，见 setup_m5_tasks.ps1）：
  python scripts/cron_call.py /api/refresh?scope=all          # 每周全量刷（含基准）
  python scripts/cron_call.py /api/snapshot/import            # 每日快照检测导入

Windows 纪律：不用 curl（Git Bash/管道 GBK 坑），一律 python urllib。

失败即 Bark（2026-11-20 阶段A修复，brief #001 建议②）：退出非零前推警报，
推送纪律=静默+异常才推。key 读取链：本仓 data/bark_key.txt 优先，
降级借 mobile-hq/push.config；两者皆缺则跳过推送仅打日志（推送故障
不影响退出码，任务计划只看退出码做重试）。
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
REPO = Path(__file__).resolve().parents[1]
TOKEN_FILE = REPO / "data" / "auth_token.txt"
BARK_KEY_FILE = REPO / "data" / "bark_key.txt"
FALLBACK_KEY_FILE = Path(r"D:\For_Coding\MyProjects\mobile-hq\push.config")
BARK_API = "https://api.day.app/push"


def load_bark_key() -> str:
    """本仓 data/bark_key.txt（单行即 key）优先，降级读 mobile-hq 的 push.config。"""
    if BARK_KEY_FILE.exists():
        key = BARK_KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    if FALLBACK_KEY_FILE.exists():
        for line in FALLBACK_KEY_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("bark_key="):
                return line.split("=", 1)[1].strip()
    return ""


def bark_alert(title: str, body: str) -> None:
    """异常才推（alarm 铃 + timeSensitive 穿透专注 + isArchive 留档），失败重试 3 次。"""
    key = load_bark_key()
    if not key:
        print("bark skipped: no key in data/bark_key.txt nor mobile-hq/push.config",
              file=sys.stderr)
        return
    payload = {
        "device_key": key, "title": title, "body": body,
        "group": "FQT", "sound": "alarm", "level": "timeSensitive", "isArchive": 1,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(
                BARK_API, data=data,
                headers={"Content-Type": "application/json; charset=utf-8"})
            with urllib.request.urlopen(req, timeout=15,
                                        context=ssl.create_default_context()) as r:
                r.read()
            print(f"bark ok (attempt {attempt})")
            return
        except Exception as e:  # noqa: BLE001 api.day.app 有 TLS 抖动前科，统一重试
            print(f"bark attempt {attempt} failed: {e}", file=sys.stderr)
            if attempt < 3:
                time.sleep(5)


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "/api/health"
    method = sys.argv[2].upper() if len(sys.argv) > 2 else "GET"
    req = urllib.request.Request(BASE + path, method=method)
    if method != "GET":
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        req.add_header("X-FQT-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            body = r.read().decode("utf-8", errors="replace")
            print(f"{r.status} {path} -> {body[:300]}")
            return 0
    except Exception as e:  # noqa: BLE001 失败先 Bark 再退非零，任务计划看重试
        print(f"FAIL {path}: {e}")
        bark_alert("FQT定时任务失败", f"{path}\n{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
