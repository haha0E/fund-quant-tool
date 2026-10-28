"""后端启动入口（供 VSCode ▶「运行文件」直接跑，等价于 F5 启动配置）。

放在 backend/ 根（不在 app/ 包内），脚本方式运行时 cwd 即 backend/，
`app` 包可被找到，uvicorn 以模块方式加载应用，相对导入不受影响。
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
