"""任务计划专用：调本机 API（自动带 token）。cron_call.py <path> [method]

用法（任务计划程序注册，见 setup_m5_tasks.ps1）：
  python scripts/cron_call.py /api/refresh?scope=all          # 每周全量刷（含基准）
  python scripts/cron_call.py /api/snapshot/import            # 每日快照检测导入

Windows 纪律：不用 curl（Git Bash/管道 GBK 坑），一律 python urllib。
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
TOKEN_FILE = Path(__file__).resolve().parents[1] / "data" / "auth_token.txt"


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
    except Exception as e:  # noqa: BLE001 cron 环境异常打日志退非零，任务计划看重试
        print(f"FAIL {path}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
