"""FastAPI 入口。启动：uv run uvicorn app.main:app --port 8000（在 backend/ 目录下）。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import REPO_ROOT, get_auth_token
from .db import init_db
from .routers import dashboard, explore, funds, portfolio, refresh, snapshot, strategy

# 生产态构建产物（npm run build 产出；dist 不入 git，未构建时仅提供 API）
DIST_DIR = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="基金研究工作台", version="0.1.0", lifespan=lifespan)

# 前端开发期由 Vite 代理 /api，CORS 兜底放开本地访问；生产态同源托管无需放宽
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 手机走 tailnet 访问，链路质量随直连/DERP 中继波动——响应体 >1KB 一律 gzip
# （JS bundle 1.7MB → ~0.4MB，详情 JSON 同样受益），是首屏"有时加载很久"的主修
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(funds.router)
app.include_router(refresh.router)
app.include_router(portfolio.router)
app.include_router(strategy.router)
app.include_router(explore.router)
app.include_router(snapshot.router)
app.include_router(dashboard.router)


@app.middleware("http")
async def require_token_for_writes(request: Request, call_next):
    """M3 token 鉴权：/api 的非 GET/HEAD 请求必须带 X-FQT-Token（手机存一次）。

    GET 放行——读接口在 tailnet 防火墙后面，写接口才需要第二道闸。
    """
    if (request.method not in ("GET", "HEAD", "OPTIONS")
            and request.url.path.startswith("/api")):
        supplied = request.headers.get("X-FQT-Token", "")
        if supplied != get_auth_token():
            return JSONResponse(
                {"detail": "写接口需要鉴权：缺少或错误的 X-FQT-Token（在页面设置里粘贴一次即可）"},
                status_code=401)
    return await call_next(request)


@app.get("/api/auth/status")
def auth_status():
    token = get_auth_token()
    return {"enabled": True, "hint": f"{token[:4]}…（完整 token 见 data/auth_token.txt）"}


@app.get("/api/health")
def health():
    from .config import DB_PATH
    from .db import conn

    with conn() as c:
        count = c.execute("SELECT COUNT(*) FROM fund").fetchone()[0]
        nav_latest = c.execute("SELECT MAX(date) FROM fund_nav").fetchone()[0]
    return {"status": "ok", "db_path": str(DB_PATH), "fund_count": count,
            "nav_latest": nav_latest}


# ---- 生产态静态托管（实现方案 §7：FastAPI 直接托管 frontend/dist，同源免 CORS 放宽）----
# 兜底路由注册在全部 /api 路由之后：未知 /api 路径按 404 处理，不回退页面；
# 其余未命中路径先按静态文件找（resolve 校验防穿越），再回退 index.html（SPA 前端路由）。
if DIST_DIR.exists():

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (DIST_DIR / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(DIST_DIR.resolve()):
            # vite 产物带内容 hash：可 immutable 缓存一年，二次访问零下载；
            # 其余静态文件（favicon 等）保守协商缓存（FileResponse 自带 ETag）
            headers = (
                {"Cache-Control": "public, max-age=31536000, immutable"}
                if full_path.startswith("assets/")
                else None
            )
            return FileResponse(candidate, headers=headers)
        # index.html 永远协商取新（否则发版后手机还在跑旧 chunk 的 hash）
        return FileResponse(DIST_DIR / "index.html", headers={"Cache-Control": "no-cache"})
