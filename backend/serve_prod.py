"""生产启动入口（任务计划程序 FQT_Web_Server 调用）：无 --reload，监听 0.0.0.0:8000。

与 run.py（开发态 127.0.0.1 + reload）并存但同端口不可同时起——开发调试先停任务：
  MSYS_NO_PATHCONV=1 schtasks /end /tn FQT_Web_Server
安全边界：本端口仅由防火墙规则 "FQT 8000 tailnet only" 放行 100.64.0.0/10（tailnet）访问。
访问日志落 data/logs/access.log（滚动 2MB×3）：手机打不开时可立刻判断请求是否到达服务器。
"""
import logging
import logging.handlers
from pathlib import Path

import uvicorn

LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "logs"
LOG_DIR.mkdir(exist_ok=True)
_handler = logging.handlers.RotatingFileHandler(
    LOG_DIR / "access.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
_acc = logging.getLogger("uvicorn.access")
_acc.setLevel(logging.INFO)  # log_config=None 时不再由 dictConfig 设级别，须自设（否则继承 root WARNING，INFO 全被滤掉）
_acc.handlers = [_handler]
_acc.propagate = False

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False,
               access_log=True, log_config=None)  # log_config=None：不覆盖上面的 access 落盘 handler
