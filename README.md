# fund-quant-tool · 基金量化助手

为 investment-weekly 的 5 只场外持仓做**信号驱动的调仓辅助**。决策辅助，不自动交易。路线图见 [ROADMAP.md](ROADMAP.md)。

## 环境（uv 管理）

```bash
uv sync                # 按 uv.lock 精确复原环境（Python 3.12 + pandas/matplotlib/jupyter/typesafe-sdk）
uv run jupyter lab     # 启动 Jupyter
```

- Python 版本钉在 `.python-version`（3.12），依赖锁在 `uv.lock`
- 依赖增删用 `uv add <pkg>` / `uv remove <pkg>`，不要手动改 .venv
- 机器级 uv 配置在 `~/.config/uv/uv.toml`（阿里云 PyPI 镜像；清华 403、直连 pypi 偶发超时，2026-09-24 实测）

## 目录

- `notebooks/` — 教学 notebook（阶段 0 起）
- `data/` — 原始数据快照（来源与口径见 data/README.md）
- `figures/` — notebook 输出的图

## 安全

`.env`（TYPESAFE_API_KEY）已被 .gitignore 排除，**任何时候不要提交**；怀疑泄露去 console.typesafe.ai 轮换。
