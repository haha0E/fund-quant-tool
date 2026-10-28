"""路径与开关集中管理。SQLite 库与 md 快照都落在仓库 data/ 下（库文件不入 git）。"""
import secrets
from pathlib import Path

# backend/app/config.py -> repo 根目录
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "workbench.db"
NOTES_DIR = DATA_DIR / "notes"  # 结论层 md 快照导出目录
SNAPSHOT_DIR = DATA_DIR / "snapshot"  # a 档：同步盘快照的本地落点（M5 接入）
STRATEGY_DIR = DATA_DIR / "strategy"  # 固化策略 + 双周 brief（M3 策略页数据源）
AUTH_TOKEN_PATH = DATA_DIR / "auth_token.txt"  # 写接口 token（手机存一次）

DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR.mkdir(exist_ok=True)
STRATEGY_DIR.mkdir(exist_ok=True)


def get_auth_token() -> str:
    """写接口鉴权 token：文件存在则读，否则生成并落盘。

    分发方式：桌面端打开 data/auth_token.txt 复制，手机网页「设置」里粘贴一次
    （存 localStorage）。文件不入 git。
    """
    if AUTH_TOKEN_PATH.exists():
        token = AUTH_TOKEN_PATH.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(16)
    AUTH_TOKEN_PATH.write_text(token, encoding="utf-8")
    return token
