"""路径与开关集中管理。SQLite 库与 md 快照都落在仓库 data/ 下（库文件不入 git）。"""
from pathlib import Path

# backend/app/config.py -> repo 根目录
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "workbench.db"
NOTES_DIR = DATA_DIR / "notes"  # 结论层 md 快照导出目录
SNAPSHOT_DIR = DATA_DIR / "snapshot"  # a 档：同步盘快照的本地落点（M5 接入）

DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR.mkdir(exist_ok=True)
