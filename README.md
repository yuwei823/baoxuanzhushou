# 保险营销内容智能审核

当前处于工程骨架阶段，审核服务、模型接入和页面尚未实现。实施规格见 [SPEC.md](SPEC.md)，进度见 [PLAN.md](PLAN.md)，验收证据见 [HANDOFF.md](HANDOFF.md)。

## 安装（Windows / Python 3.11）

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --no-deps -r requirements-build.lock
.\.venv\Scripts\python.exe -m pip install --require-hashes --no-build-isolation -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m insurance_audit.cli --help
```

锁文件包含开发及运行依赖，目标环境为 Windows Python 3.11；其他平台需重新验证。更新锁前，先在虚拟环境按当前锁安装依赖（其中含 pip-tools），再运行：

```powershell
.\.venv\Scripts\python.exe scripts/lock_dependencies.py
```

配置模板为 `.env.example`，实际 `.env` 不入库；不要向对话或日志粘贴密钥。当前 CLI 仅支持帮助及版本，不会假装执行审核、语料发布或评估。

## 当前阻塞

当前目标规则集为用户确认的 `official-v1-2026-10-11`，来源是目录中的三份核心正式文件。DOC/PDF 已提取用于诊断，尚未完成人工原文核对，语料仍不可发布。真实百炼调用还需要本地密钥及有效地域配置。
