# 保险营销内容智能审核

P0 知识库及目录自动化流水线已完成；审核服务、模型接入和页面尚未实现。实施规格见 [SPEC.md](SPEC.md)，进度见 [PLAN.md](PLAN.md)，验收证据见 [HANDOFF.md](HANDOFF.md)。

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

配置模板为 `.env.example`，实际 `.env` 不入库；不要向对话或日志粘贴密钥。当前 CLI 已提供 ingest、validate-corpus、publish-corpus；审核 API 与评估将在后续阶段实现。

## 当前阻塞

当前目标规则集为用户确认的 `official-v1-2026-10-11`，来源是目录中的三份核心正式文件。DOC/PDF 已可靠提取；实施 agent 已全文核对 172 条文与 34 张规则卡并完成 P0 校验，核对不代表法律专家认证。保险法按用户要求暂缓，不属于本快照。真实百炼调用还需要本地密钥及有效地域配置。

## P0 语料命令与快照

```powershell
.\.venv\Scripts\python.exe -m insurance_audit.cli validate-corpus --ruleset official-v1-2026-10-11
.\.venv\Scripts\python.exe -m pytest -q
```

已发布快照保存在 `data/corpus/official-v1-2026-10-11/`，包含原 DOC/PDF 的字节副本、原始抽取 JSON、条文、规则、逐条范围台账、哈希绑定的审阅记录和 manifest。集中来源与工具登记在 `data/extracted/extraction-registry.json`。

新法规放入 `法律法规/` 后，后台每 5 秒扫描，自动登记、保存原件、抽取、切分、校验并构建待审候选；完成审阅并 seal 后自动续跑发布。已发布 ID 禁止覆盖，目录新文件不会直接参与审核裁决。完整步骤、状态和审阅协议见 [P0 流水线说明](docs/p0-pipeline.md)。

```powershell
.\.venv\Scripts\python.exe -m insurance_audit.cli pipeline start
.\.venv\Scripts\python.exe -m insurance_audit.cli pipeline status
.\.venv\Scripts\python.exe -m insurance_audit.cli pipeline stop
```

当前用户登录启动任务：`InsuranceAudit-P0-FolderWatch`。由 `scripts/install_pipeline_task.ps1` 安装，移除时加 `-Remove`。单实例锁防止后台重复执行。当前 `.venv` 保留使用；旧脚本与过期报告已清理。临时缓存及第二套验收环境的递归清理由自动安全策略阻止，可手动运行 `scripts/cleanup_p0.ps1` 完成（支持 `-WhatIf`）。重新安装按上方哈希锁命令从包仓库下载。
