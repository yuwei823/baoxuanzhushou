# 保险营销内容智能审核

P0 知识库及目录自动化流水线已完成；P1/P2 审核服务、模型接入和页面主体代码已实现，完整验收尚未完成。目前按用户指示优先推进纯文本审核，图片识别开发与验收暂缓。实施规格见 [SPEC.md](SPEC.md)，进度见 [PLAN.md](PLAN.md)，验收证据见 [HANDOFF.md](HANDOFF.md)。

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

配置模板为 `.env.example`，实际 `.env` 不入库；不要向对话或日志粘贴密钥。当前 CLI 已提供语料命令及 audit-text、doctor，审核 API 已实现；正式效果评估尚未完成。

## 当前阻塞

当前目标规则集为用户确认的 `official-v1-2026-10-11`，来源是目录中的三份核心正式文件。DOC/PDF 已可靠提取；实施 agent 已全文核对 172 条文与 34 张规则卡并完成 P0 校验，核对不代表法律专家认证。保险法按用户要求暂缓，不属于本快照。本地密钥与地域配置已就绪，文本与视觉基础探测已通过；文本复验一个违规案例成功，教育反例和局部材料仍有校验失败，详见 [文本冒烟报告](reports/text-smoke.md)。G1/G2 尚未通过，RAG 改造见 [待实施方案](docs/text-rag-plan.md)。

## 纯文本运行

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m insurance_audit.cli audit-text --text '保险知识科普：分红属于非保证利益。'
.\.venv\Scripts\python.exe -m uvicorn insurance_audit.api:app --host 127.0.0.1 --port 8000
# 以下使用真实 API，产生调用用量；只运行三个合成文本演示案例，不调用视觉模型。
.\.venv\Scripts\python.exe scripts/live_audit_smoke.py violation education review
```

页面地址为 http://127.0.0.1:8000，当前优先使用文本输入。完整审核结果包含 completed/partial/failed 执行状态及三态业务结论；failed/null 是技术失败，不表示合规。合成案例报告不是正式评估成绩。

本地文本模型为 qwen3.7-plus，使用 `BAILIAN_TEXT_ENABLE_THINKING=false` 控制思考模式；更换模型时按其能力确认该参数，移除参数则使用模型默认行为。依据：[百炼思考模式文档](https://help.aliyun.com/zh/model-studio/deep-thinking)。Embedding 模型和维度已配置，但当前仍使用 BM25，没有向量 API 调用。

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
