# 保险营销内容智能审核

P0 知识库及目录自动化流水线已完成；G1/G2 已通过（2026-10-12 真实验收，合成开发案例工程验收），P3 数据集与正式效果评估尚未完成。详见 [G1 验收报告](reports/g1-acceptance-2026-10-12.md)、[图文报告](reports/multimodal-acceptance.md)。实施规格见 [SPEC.md](SPEC.md)，进度见 [PLAN.md](PLAN.md)，验收证据见 [HANDOFF.md](HANDOFF.md)。

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

当前规则集为用户确认的 `official-v1-2026-10-11`，只使用本地三份核心正式文件，含 172 条文、34 张规则卡；实施 agent 的核对不代表法律专家认证，保险法仍暂缓。本地 hybrid RAG 已接通；G1/G2 已通过，正式效果评估未完成。详见 [RAG 实测报告](reports/rag-acceptance.md)、[G1 验收报告](reports/g1-acceptance-2026-10-12.md)、[运行说明](docs/rag-operations.md)。

## 纯文本运行

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m insurance_audit.cli build-index
.\.venv\Scripts\python.exe -m insurance_audit.cli audit-text '保险知识科普：分红属于非保证利益。'
.\.venv\Scripts\python.exe -m uvicorn insurance_audit.api:app --host 127.0.0.1 --port 8000
# 以下使用真实 API，产生调用用量；五例合成开发案例验收（不调用视觉模型）。
.\.venv\Scripts\python.exe scripts/verify_g1.py --out reports/g1-next-live.json
```

页面地址为 http://127.0.0.1:8000，支持文本和有序多图。P2 本轮验证见 [图文报告](reports/multimodal-acceptance.md)，操作见 [演示说明](docs/demo-script.md)。完整审核结果包含 completed/partial/failed 执行状态及三态业务结论；failed/null 是技术失败，不表示合规。合成案例报告不是正式评估成绩。

本地文本模型为 qwen3.7-plus，使用 `BAILIAN_TEXT_ENABLE_THINKING=false` 控制思考模式；更换模型时按其能力确认该参数，移除参数则使用模型默认行为。依据：[百炼思考模式文档](https://help.aliyun.com/zh/model-studio/deep-thinking)。本地已启用 RETRIEVAL_MODE=hybrid，使用 text-embedding-v4/1024 维和 BM25，经 RRF 融合召回后将原文送入模型，同时保留全部规则覆盖。查询向量失败不会静默降级。

`build-index` 首次调用真实 Embedding，现有 172 条文每批最多 10 条；重复运行校验并复用同一版本。索引单独保存在 data/indexes/，绑定法规快照哈希、模型、维度和检索文本哈希。新快照发布后需显式重新执行 build-index；不匹配的旧索引不会被使用。当前整条索引限每条检索文本 2000 字符，未来超长条文需实现分款/父条方案，构建器会拒绝而非截断。图片验收已恢复，保险法抽取仍暂缓。

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

## P3 评估准备

已提供 `evaluate --split dev --variant hybrid --out <新目录>`，可真实运行或用 `--replay reports/g1-next-live-v2.json` 重放历史响应。数据规范见 [标注与指标说明](docs/evaluation-labeling.md)，本轮 [开发诊断报告](reports/p3-dev-replay-v1.0/report.md) 基于 5 条已暴露、待人工核对的案例；不是正式效果验收。G1/G2 已通过（工程验收），20/40 数据及全文基线尚未完成，固定测试入口尚未放行。
