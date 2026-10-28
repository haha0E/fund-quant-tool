"""策略页接口（M3）：data/strategy/ 下 markdown 只读渲染。

内容来源两类：固化策略 strategy.md（定投纪律/二选一框架/暴露上限/核查节奏，
从两份调查报告提炼）+ 双周会话产物 brief-YYYYMMDD.md。版本史靠 git diff，
本接口只做只读列表与取文，不提供写入。
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..config import STRATEGY_DIR
from ..schemas import StrategyFileOut

router = APIRouter(prefix="/api/strategy", tags=["strategy"])

_SAFE_NAME = re.compile(r"^[\w\-. ]+$")


def _title_of(path) -> str:
    """取 md 首行 # 标题（无则回退文件名）。"""
    try:
        first = next((ln for ln in
                      path.read_text(encoding="utf-8").splitlines() if ln.strip()), "")
    except OSError:
        return path.stem
    return first.lstrip("# ").strip() or path.stem


@router.get("", response_model=list[StrategyFileOut])
def list_strategy():
    """strategy.md 永远置顶；brief-* 按文件名降序（新 brief 在前）。"""

    def sort_key(p):
        return (0, "") if p.name == "strategy.md" else (1, p.name)

    out = []
    for p in sorted(STRATEGY_DIR.glob("*.md"), key=sort_key):
        out.append(StrategyFileOut(
            filename=p.name, title=_title_of(p),
            updated_at=datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
        ))
    return out


@router.get("/{filename}")
def get_strategy(filename: str):
    if not _SAFE_NAME.match(filename):
        raise HTTPException(400, "非法文件名")
    path = (STRATEGY_DIR / filename).resolve()
    if not path.is_relative_to(STRATEGY_DIR.resolve()) or not path.is_file():
        raise HTTPException(404, "策略文件不存在")
    return {
        "filename": filename,
        "title": _title_of(path),
        "content": path.read_text(encoding="utf-8"),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }
