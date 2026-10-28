"""生产启动入口（任务计划程序 FQT_Web_Server 调用）：无 --reload，监听 0.0.0.0:8000。

与 run.py（开发态 127.0.0.1 + reload）并存但同端口不可同时起——开发调试需先停任务：
  MSYS_NO_PATHCONV=1 schtasks /end /tn FQT_Web_Server
安全边界：本端口仅由防火墙规则 "FQT 8000 tailnet only" 放行 100.64.0.0/10（tailnet）访问。
（实现方案 §7 原文写 127.0.0.1，2026-10-28 tailnet 化部署时按任务要求放宽监听地址，
暴露面由防火墙规则收紧到 tailnet 网段，与 mobile-hq 8100 服务同模式。）
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
