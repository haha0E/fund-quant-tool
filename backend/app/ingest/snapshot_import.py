"""a 档快照导入（实现方案 §2.2）：同步盘 data/snapshot/YYYY-MM-DD/ → SQLite，幂等。

链路：Mac/外部 ZCode 批次产出快照目录（domain_map.csv 等）落同步盘 →
本模块检测未记账目录 → 校验结构 → UPSERT 导入 → snapshot_log 记账。
幂等保证两层：snapshot_log (日期,文件名) 记账跳过 + 表唯一键 UPSERT——
同一目录导入两次行数不变（M5 验收线）。

CSV 约定（首行表头，UTF-8，可带 BOM）：
  domain_map.csv: domain,fund_code,fund_name
"""
from __future__ import annotations

import csv
from datetime import date

from ..config import SNAPSHOT_DIR
from ..db import conn

_SUPPORTED = {"domain_map.csv": ("domain", "fund_code", "fund_name")}


def _is_date_dir(name: str) -> bool:
    try:
        date.fromisoformat(name)
        return True
    except ValueError:
        return False


def _import_domain_map(csv_path) -> int:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    valid = [r for r in rows
             if (r.get("domain") or "").strip() and (r.get("fund_code") or "").strip()]
    with conn() as c:
        c.executemany(
            """INSERT INTO domain_map (domain, fund_code, fund_name, updated_at)
               VALUES (:domain, :fund_code, :fund_name, datetime('now', 'localtime'))
               ON CONFLICT(domain, fund_code) DO UPDATE SET
                   fund_name = excluded.fund_name,
                   updated_at = excluded.updated_at""",
            [{"domain": r["domain"].strip(), "fund_code": r["fund_code"].strip(),
              "fund_name": (r.get("fund_name") or "").strip()} for r in valid])
    return len(valid)


def import_snapshots() -> dict:
    """扫 data/snapshot/ 下所有日期目录，导入未记账的文件。幂等可重复调用。"""
    if not SNAPSHOT_DIR.exists():
        return {"imported": [], "skipped": [], "errors": [],
                "note": "data/snapshot/ 不存在（尚无快照产出）"}
    with conn() as c:
        done = {(r["snapshot_date"], r["filename"]) for r in
                c.execute("SELECT snapshot_date, filename FROM snapshot_log")}
    imported, skipped, errors = [], [], []
    for day_dir in sorted(p for p in SNAPSHOT_DIR.iterdir()
                          if p.is_dir() and _is_date_dir(p.name)):
        for filename in _SUPPORTED:
            path = day_dir / filename
            if not path.is_file():
                continue
            if (day_dir.name, filename) in done:
                skipped.append(f"{day_dir.name}/{filename}")
                continue
            try:
                n = _import_domain_map(path)
                with conn() as c:
                    c.execute("INSERT INTO snapshot_log (snapshot_date, filename, rows)"
                              " VALUES (?, ?, ?)", (day_dir.name, filename, n))
                imported.append({"file": f"{day_dir.name}/{filename}", "rows": n})
            except Exception as e:  # noqa: BLE001 单文件失败不阻塞，错误显式返回
                errors.append(f"{day_dir.name}/{filename}: {e}")
    return {"imported": imported, "skipped": skipped, "errors": errors}
