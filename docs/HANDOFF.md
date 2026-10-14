# 实施交接记录

## 当前交接摘要（2026-10-15 双审核模式）

接手时以本节及最新 reports/performance-* 为准，下面 dated 记录保留历史事实。

### 2026-10-15 模式拆分

- 保留 API 参数 `depth=concise|strict` 兼容既有客户端，但含义已经改变：`concise` 对应“初审”，只审核 RAG 命中法条关联的规则；`strict` 对应“完全 · 查验所有规则”，继续使用 46 条规则基线 + 按批次定向 RAG。
- 初审模式未选规则写入逐规则台账，状态为 `not_reviewed`，并列入 `meta.omitted_rule_ids`；未发现明确违规时因覆盖不完整返回 `needs_review`，不会输出完整合规。RAG 失败则整体技术失败，不静默降级。
- 页面、API 契约、项目介绍、RAG/规则卡说明、测试材料、workflow、intro 和 batch-flow 已同步新语义。全量测试为 **122 passed**；新增测试分别验证 RAG 选规则、完整规则基线、未查验台账和检索失败行为。

### 当前规则与实现

- 当前快照 `official-v3-2026-10-12` 已发布：4 份用户本地法规，含保险法，359 条文、46 规则。严格 validate-corpus 为 release_ready=true，0 完整性错误、0 审阅门禁。不要沿用旧“保险法暂缓”的状态。v3 与 v2 内容完全一致，仅文档顺序不同（保险法置于首位）；已发布快照不可原位覆盖，故顺序调整必须新建 ruleset。
- 文本 `qwen3.7-plus`，视觉 `qwen3-vl-plus`；hybrid=BM25 + text-embedding-v4/1024；Prompt `audit-v1.6-citation-guidance`，workflow `1.5-depth-rule-selection`。默认 targeted：全局召回与当前批次直接法条的 BM25/向量相似度二次 RRF，每批最多补充 8 条/8,000 字符。完全模式覆盖全部 46 条规则；初审模式只覆盖 RAG 选中规则。
- 2026-10-13 修复长、多段材料的 `context_budget_exceeded`：旧检索将每段 Top 8 的无序并集全部复制到每个判定批次；现按跨段累计 RRF 排序，强制保留规则直接/支持条文，并只在剩余预算中加入额外召回。context_trace 新增实际 Prompt 字符数和 dropped 召回 ID。用户提供的“慈铭体检+保险”原文在旧逻辑下召回 153 条、13 批超过 90,000 字符；修复后离线 46/46 台账、0 超限。真实 hybrid 复验召回 210 条，最大 Prompt 54,529 字符，completed/non_compliant、0 错误，trace_id=`a910cd8c-387d-42a6-9340-2060f294f082`。全量 114 tests passed，Ruff 通过。
- 保留其他 agent 的法规聚类分批改动。当前本地 `.env` 为 batch=4、model_concurrency=8、attempts=40、单次45秒/总计150秒；代码及 `.env.example` 默认 batch=2。性能比较通过独立 Settings 覆盖，不修改密钥或模型配置。
- 新增逐调用 queue_ms、request_ms、token_usage、reasoning_tokens（缺失为 null）、transport_retry、structure_attempt、outcome；旧 latency_ms 包含排队，保留兼容。meta.rule_status_counts 区分已检查、不适用、范围外、待上下文、待外部核验及技术失败。页面展示各状态数量和简要模式隐藏提示数量。

### 验收与效果边界

- targeted/global 真实 A/B 已完成：同一 qwen3.7-plus、batch=4、concurrency=8、5 条 provisional 开发案例各 1 次，两组均 4/5；targeted Prompt token 625,312→533,436（-14.7%），P50 32.609→26.609 秒（-18.4%），结构修复 3→1。共同失败是教育案例 `disclose_material_policy_terms_and_restrictions` 的证据原句校验；不宣称准确率提升。详见 `reports/rag-batch-context-ab-2026-10-13/report.md`。
- 2026-10-14 完成 targeted/严格 none 真实开关对照。`none` 现跳过查询向量、BM25、RRF及检索排序，并以 `meta.retrieval_executed=false` 明示；46 条规则和直接/支持法条仍完整保留。5 条 provisional 单次结果 targeted 5/5、none 4/5；none Prompt token -19.5%、总 token -18.1%、P50 -3.0%，中性科普发生一次最终证据校验失败。继续默认 targeted，但不把小样本单次差异宣传为正式准确率提升。详见 `reports/rag-on-off-ab-v2-2026-10-14/report.md`。
- 2026-10-14 完成仅基线/仅 RAG/两者都开三策略交错实测，各 5 次。三组均 4/5，共同失败是中性科普证据输出校验。仅 RAG 平均检查 19.2/46 条规则，较仅基线 Prompt token -33.4%、P50 -39.4%，但两个违规案例的规则级违规发现从 14 项降至 7 项。2026-10-15 起仅 RAG 用于初审模式，组合策略用于完全模式；初审模式不形成完整合规结论。详见 `reports/rag-three-strategies-2026-10-14/report.md`。
- 2026-10-15 将产品文案统一为“初审模式/完全模式”；新增 46 条规则的中文展示名，响应通过 `meta.rule_display_names` 提供完整映射，前端违规卡片与规则台账使用中文名。Batch Flow 第 6 页按 5 条开发案例实测 token 与华北 2 实时调用原价展示估算单条成本：初审约 ¥0.154，完全约 ¥0.292。
- `batch-flow` 已新增“方案取舍”和“测试案例”两步，页面直接展示三方案机制、实测指标、5 条开发案例及混合方案的选择依据，并通过 `/batch-flow/report` 提供完整三策略报告。当前共 11 个可播放步骤。
- “慈铭体检+保险”长材料 targeted 真实复验 completed/non_compliant、0 错误、全局召回 210、13 批、最大 Prompt 44,442 字符、38.391 秒，trace_id=`68b51f73-b8d0-4f3f-a332-a69980f6b99c`。相较旧记录最大 Prompt 54,529 更小，但单次时延更高，不能把时延波动归因于 RAG。

- v1 的 G1/G2 已通过合成开发案例工程验收，证据 reports/g1-acceptance-2026-10-12.md、reports/p2-stress-reverify.json；该结论不能自动覆盖 v2。
- 本轮 v2 模型初筛已完成：qwen3.7-plus 5/5、qwen-plus 4/5、qwen-turbo 3/5，失败均为教育反例误复核；均不是正式 gold 评估。完整调用、代码/语料/案例哈希见 reports/performance-model-pilot-v2/。保留当前模型。
- v2 的 batch=2/3、concurrency=4/8 两轮比较已完成 40 次：b2c8=10/10，P50 27.83秒、P95 29.06秒，无修复；b3c8=9/10，教育反例证据校验失败。保留模型和 batch=2/concurrency=8。见 reports/performance-batch-matrix-v2/report.md；不能直接当作 v3 的验收。
- 最新全量测试 **117 passed in 19.67s**，Ruff 全库通过；新增 targeted/global 上下文分配、必需条文保留、召回台账分区和动画路由回归。独立模拟页面此前已验证状态总数 46（checked=1、needs_context=39、failed=6），没有把待核验算作技术失败；截图 reports/performance-status-ui.png。
- P3 正式评估继续暂缓：5 条 provisional 开发种子已暴露，20/40 数据、图文人工标注、全文基线及正式 A/B 未完成。P4 部署产物由此前 agent 建立，本轮没有执行远程部署或更改访问控制。

### 下一步与复现

1. 分批/并发矩阵已完成；每组仅10次，不能称生产稳定指标。后续如变更规则或 Prompt，单独复验。
2. 本轮结论保留 batch=2/concurrency=8；模型初筛不支持换为 qwen-plus/turbo。不要通过省略条件、扩大无限重试或隐藏错误提高覆盖率。
3. 继续收集独立标注资料；未有人工 gold，不将工程回归通过率当作准确率。
4. 已在 `docs/decisions.md` 记录长文本改进建议：API 的 10,000 码点硬上限暂不改变；页面已限制为 5,000 码点，并按 Unicode 码点计数和截取。60 个非空段落提醒尚未实现；模型 Prompt 采用 60k 目标、75k 强制收缩/分批、90k 硬预算。预算数值仍需纳入 P3 长度梯度评测后校准。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m insurance_audit.cli validate-corpus --ruleset official-v3-2026-10-12
# 真实调用产生 API 用量；out 必须尚不存在，不覆盖历史报告
.\.venv\Scripts\python.exe scripts/benchmark_audit.py --models qwen3.7-plus --batches 2 3 --concurrencies 4 8 --repeats 2 --out reports/performance-next
```

本轮修改：models/bailian.py、service.py、static/app.js/styles.css、scripts/benchmark_audit.py、tests/unit/test_performance_diagnostics.py、docs/audit-performance.md、docs/api-contract.md、HANDOFF/PLAN。已有 retrieval.py 改动不是本轮原创，未覆盖；语料和评估预期不变。

---

## 2026-10-12 — P4 内部上线交付（用户指示：P3 暂缓、先上线）

- 用户决定：快速上线到阿里云（Docker + 域名 baoxuanzhushou.app + GitHub Actions 自动部署），P3 正式评估暂缓（保留未勾选，不取消）。本机不装 Docker，构建在服务器上执行。
- 代码：config.py 新增 `auth_token`（可选共享口令，未设时行为不变）与 `audit_max_concurrency`（默认 2，超限 429）；api.py 增加口令中间件（仅保护 /api/*，页面与健康检查开放）与审核并发信号量；前端新增口令输入框（localStorage 保存）、Authorization 头与 401/429 提示；.env.example 增补两项。
- 部署件：Dockerfile（两阶段：容器内 pip-compile 生成 Linux 哈希锁 → 运行时镜像烘焙已发布语料与向量索引，PROJECT_ROOT=/app）、.dockerignore、requirements-runtime.in（与 Windows dev 锁同版本）、docker-compose.yml（audit + caddy、健康检查、日志轮转）、Caddyfile（自动 HTTPS、其它主机名 404）、.github/workflows/deploy.yml（push main → 测试 → SSH 部署 → /readyz 检查）、docs/deployment.md（ECS 初始化、DNS/安全组、secrets、运维与免责）。另交付本地一键部署：deploy-local.bat / stop-local.bat + scripts/deploy_local.ps1 / stop_local.ps1（自动建 venv 装锁、检查 .env 与索引、停旧启新、开浏览器；已实测 hybrid 就绪）。
- 验证：pytest 全量通过（新增口令 401/200、并发 429 用例）；ruff 通过。Docker 镜像未本地构建（本机无 Docker），首次构建与 G4 线上验证待用户在阿里云执行。
- 边界：上线状态为“内部使用”；P3 未验收，不得宣称效果达标；规则卡非法律专家认证，needs_review 通道与免责声明保留。密钥仅存服务器 .env，不入库不入镜像。
- 下一步：用户在 GitHub 建私有仓库并推送（推送前按 docs/deployment.md 清点敏感文件）、ECS 初始化与首次构建、配置 Actions secrets 与 Deploy Key、验证域名与一次真实审核（P4-06）。

---

## 2026-10-12 — 项目清理（用户指示）

- 用户指示：删除不必要的中间件、脚本与过时报告。经确认，“中间件”指构建与缓存中间产物；FastAPI 两个请求中间件（BodyLimit、security_headers 响应头）均有测试覆盖且为验收必需，未改动；P0 目录监控后台服务按用户选择保留。
- 删除中间产物：build/、src/insurance_audit.egg-info/、reports/package-check/ 内 wheel（verification.json 保留）、.pytest_cache、.ruff_cache、各 __pycache__。以上均可重新生成，且均在 .gitignore 中。
- 删除脚本（被流水线或新入口取代的一次性工具）：record_core_review.py、core_rule_review_data.py、build_rule_card_candidates.py（P0 候选卡一次性构建，现由 corpus/pipeline.py 的候选与审阅模板流程取代）；live_audit_smoke.py（由 verify_g1.py 取代，README 已更新）。保留：cleanup_p0.ps1（本项目指定的缓存清理工具）、create_demo_assets.py（static 演示素材生成器）、install_pipeline_task.ps1、lock_dependencies.py、serve_p2_fixture.py、verify_g1.py、verify_stress.py。
- 删除过时报告：早期文本冒烟系列（text-audit-smoke*.json、text-smoke.md、live-audit-smoke.json）、RAG 中间运行（text-rag-smoke.json、text-rag-smoke-v1.3.json；v1.4 为 rag-acceptance 现行证据保留）、G1 旧轮（g1-development-v1.5、g1-live-acceptance-v1.5、g1-next-live、g1-progress-2026-10-12.md）、P2 首轮 partial 证据（p2-real-unicode-browser.json、p2-unicode-browser.png）、p3-g1-replay、p3-dev-replay-console.json、p3-mock-console.json、旧清理记录 cleanup-manifest/cleanup-result。当前证据保留：G0 各验收、model-doctor、rag-acceptance（含 v1.4）、g1-next-live-v2、g1-acceptance-2026-10-12、P2 教育/多图/压力复验、p3-dev-replay-v1.0、p3-mock-runner-v1.0、package-check/verification.json。
- 同步文档：README（运行入口改 verify_g1.py、replay 改 g1-next-live-v2.json、移除 text-smoke 链接）、docs/evaluation-labeling.md、reports/rag-acceptance.md、multimodal-acceptance.md、g1-acceptance-2026-10-12.md、PLAN.md P1-07 产物、HANDOFF 摘要。
- 验证：pytest 全量通过、ruff check src tests scripts 通过；服务重启后 /readyz 正常（删除 egg-info 不影响已安装可编辑环境与运行中服务；重装时自动重建）。
- 未删除：data/ 全部（含 pipeline 运行态与用户提供的案例库 data/pipeline/sources/*/source.md，100 条待人工复核案例）、法律法规原始文件、已发布语料快照、docs 与 Spec 历史文档。

---

## 2026-10-15 — 停止跟踪逐次原始响应（用户指示）

- 用户指示：处理各 run 目录下的 results.jsonl / summary.json / metrics.json 等生成产物。经确认，选择“保留全部，仅把大文件改为 .gitignore 不再跟踪（本地留存）”。
- 结论：这些文件均为 git 已提交内容，且每个 report.md 明确将其列为“原始证据”，是一次性真实 API 运行的原始响应，重跑无法复现同一结果。因此不删除任何文件，仅调整跟踪范围。
- 具体改动：7 个 `reports/**/results.jsonl`（p3-dev-replay-v1.0、p3-mock-runner-v1.0、performance-batch-matrix-v2、performance-model-pilot-v2、rag-batch-context-ab-2026-10-13、rag-on-off-ab-v2-2026-10-14、rag-three-strategies-2026-10-14，合计约 7.4 MB）执行 `git rm --cached`，并在 `.gitignore` 增加 `reports/**/results.jsonl`。文件仍保留在本地磁盘。
- 保持跟踪：report.md、manifest.json、summary.json、metrics.json、package-check/verification.json、全部 PNG 截图，以及 g1-next-live-v2.json（多处验收引用）与 g1-next-live-v5.json（tests/unit/test_evaluation.py 直接读取）。
- 同步文档：上述 7 个 run 的 report.md 证据小节、docs/evaluation-labeling.md 报告产物说明，均标注 results.jsonl 仅本地留存。
- 验证：无任何代码或测试读取 results.jsonl（已全库确认）；`git check-ignore` 命中新增规则；其余报告文件未被忽略。

---

## 2026-10-12 — G1/G2 修复与真实验收（本轮）

- 任务：修复 G1 科普改写过度复核与 G2 逐规则引用失败，按 PLAN 顺序复验。
- G1 修复：`workflow.py` 新增 `TRIGGER_GUIDANCE`，为 `approved_marketing_content_use`、`internet_platform_operating_conditions` 提供触发要点（只关注材料是否呈现营销宣传/平台运营活动，中性教育材料判 false）；judge payload 注入 `trigger_guidance`，JUDGE_PROMPT 增加使用说明。Prompt 版本升级为 `audit-v1.6-citation-guidance`。
- G2 修复：judge payload 新增逐规则 `allowed_citations`（rule_id→{条文 ID: 条号}）与每条文 `direct_for_rule_ids` 标注，禁止跨规则借条文；`structured()` 新增 `repair_context`，修复提示携带各规则可引用条文（条号+开头原文，`citation_repair_context`），单次修复即可纠正引用。
- 真实 G1 复验（本轮第二次，第一次暴露出 `illegal_financial_activity_marketing` 跨规则借条文，修复 direct_for_rule_ids 标注后通过）：`scripts/verify_g1.py --out reports/g1-next-live-v2.json` 退出码 0，五例全过——violation non_compliant、education compliant、partial_material needs_review、disguised_sale_injection non_compliant、education_paraphrase compliant。标签未修改。中间失败轮报告已随 2026-10-12 清理删除，经过见本条记录。
- 真实 G2 压力复验：`scripts/verify_stress.py`（新增，API 入口）→ completed/non_compliant、4 违规、0 错误、8 次尝试；首轮 attempt=1 引用校验错误被修复提示纠正，attempt=2 无最终失败。浏览器对同一输入重放：页面显示“发现违规”、HTML 字符串按文本显示、4 违规项，截图 reports/p2-stress-reverify-browser.png；下载 JSON 受浏览器工具限制未落盘，API 报告 p2-stress-reverify.json 为完整响应证据。
- 离线验证：pytest 98 passed（新增 allowed_citations/direct_for_rule_ids/trigger_guidance 断言与修复提示测试）；ruff check src tests scripts 通过。
- 版本：qwen3.7-plus / qwen3-vl-plus / text-embedding-v4 1024 维；official-v1-2026-10-11；audit-v1.6-citation-guidance；服务已用 `.venv` 重启于 127.0.0.1:8000。
- 边界：G1/G2 为合成开发案例工程验收，不是效果评估；P3 数据与正式测试仍待用户资料与标签核对。meta.validation_errors 中 attempt=1 的记录是成功修复轨迹，不算失败。
- 下一步：P3 数据准备与冻结、全文基线 A/B、正式测试与交付复现；保险法抽取保持暂缓。


## 2026-10-11 — P0-03 来源与抽取验收；P0-04 已启动

- 规则范围：按用户指示采用本地现有三份正式版来源，单独建立 `official-v1-2026-10-11`；不得与题目征求意见稿 `assignment-v1` 合并。
- P0-03 完成：保险销售行为管理办法 DOC、互联网保险业务监管办法 DOC 经 WPS COM 12.0 只读提取；金融产品网络营销管理办法 PDF 经 PyMuPDF 1.28.2 提取并逐页渲染目检。三份标题/版本日期与对应官方发布信息吻合；条文标记分别为 50、83、39 条，序号连续、无重复或缺号。源文件 SHA-256 已写入 `data/extracted/official-source-manifest.json`。
- 官方核对：金融产品网络营销管理办法官方公告确认公告〔2026〕第9号、2026-09-30施行；保险销售办法官方页确认2023-09-20公布、2024-03-01施行；互联网保险办法官方页确认2020-12-07发文、2021-02-01施行。来源链接见 `docs/corpus-review.md`。
- 边界：P0-03 仅验收来源、版本和结构可读性，不代表逐字法律审校或规则适用性核验。PDF 本地快照不是官方原文件字节副本，官方附件下载返回403；保留本地原始哈希并记录限制。语料发布仍需 P0-04 规则卡核验和 P0-05 门禁。
- P0-04 进展：新增 `scripts/parse_official_articles.py`，生成 `data/corpus/official-v1-2026-10-11/{documents,articles,chunks}.jsonl` 和 `parse-summary.json`。172 条可解析，按来源计 50/39/83；包含稳定 ID、原文/规范化文本、SHA-256 和 DOC 段落/行或 PDF 页/行定位。
- 验证：解析汇总所有条文非空；`ruff check scripts` 与 `compileall -q scripts` 通过。条文及规则映射仍为 `verified:false`，尚未生成经核对的规则卡，规则集未发布。
- 模型/Key：未调用百炼；当前未配置 Key。
- 下一步：P0-04 逐条核验营销相关条文与规则卡映射，记录不适用范围和例外；不得把候选解析用于正式审核。

## 2026-10-11 — 来源范围扩充与版本扩展设计

- 用户澄清：以本地 `法律法规/中华人民共和国保险法.doc` 已生效版本为依据；《金融产品网络营销管理办法.pdf》已在核心来源中，无需重复导入。不要以网上修订草案替代本地法。
- 文件核对：`法律法规/` 共五份文件。本地保险法 SHA-256 `083a55d495a75a6335c02af3c90c139f3fd8f3db14548967179a397dad86527c`。官方市场监管总局页面记载保险法最近一次修正信息为2015-04-24；金融监管总局在2026-09-04另发布修订草案征求意见，明确是征求意见材料。来源链接见 SPEC 与下方官方来源。
- 当前阻塞：把保险法加入 DOC 抽取脚本后重试 WPS `DispatchEx("kwps.application")`，返回 `0x80070005 access denied`；改用 `Dispatch` 仍被拒绝。未改写本地 DOC；摘录、全文条数及适用条文尚未进入语料。P0-03A 未验收，P0-04 的正式映射需等待其完成。
- 扩展方案：新增 `data/sources/catalog.json`，列出来源类别、状态、成员资格、版本元数据、来源哈希与官方核对 URL。文件夹新增文件不自动启用；每个候选规则集显式固定文档版本/哈希。发布后规则集不可覆盖，更新或新规另建 ID，保留历史快照；每次审核 pin 规则集及 manifest/hash。草案、有效、废止和未知状态隔离；候选新集经语料门禁、规则映射复核和回归评估后才切换。
- 修改：`SPEC.md`、`PLAN.md`、`docs/environment.md`、`docs/corpus-review.md`、`scripts/extract_doc_sources.py`、`data/sources/catalog.json`。
- 下一步：恢复本地 DOC 可靠读取，完成保险法版本确认与条文提取，再按其与监管办法适用范围建立跨法规 rule_cards；不使用网络草案或替换下载文本作为最终依据。

## 2026-10-11 — 集中抽取登记已建立

- 完成：建立 `data/extracted/extraction-registry.json` 作为统一汇总入口，按 document_id 将本地来源、源文件哈希、抽取工具/版本、产物路径/大小/哈希、失败尝试、结构核验状态、法律核验状态、语料条数与 corpus 工件哈希关联。
- 状态：5 个本地来源都登记；3 个核心来源已抽取（50/39/83 条）；保险法为 `failed`（WPS COM 拒绝访问，0 条入库）；消费者权益指导意见为 `not_selected`。结构检查通过不代表法律文本或规则映射核验通过；候选规则集仍未发布。
- 维护：`scripts/build_extraction_registry.py` 可单独重建；DOC/PDF 抽取、结构审计及语料解析脚本成功运行后会自动刷新集中登记。
- 验证：JSON 解析、Ruff、compileall 通过；断言检查 5 个源哈希均与 catalog 一致、网络营销 PDF 状态为 extracted、保险法为 failed、候选语料 172 条且每个 corpus 工件哈希存在。
- 修改：`data/extracted/extraction-registry.json`、`data/extracted/extraction-attempts.json`、`scripts/build_extraction_registry.py`、`scripts/{extract_doc_sources,inspect_pdf_source,audit_extractions,parse_official_articles}.py`、SPEC.md、PLAN.md、docs/corpus-review.md。

## 2026-10-11 — 暂缓保险法抽取，推进核心来源候选规则卡检查

- 用户决定：暂缓《中华人民共和国保险法.doc》抽取，继续执行计划中的下一步。P0-03A 保持未验收；P0-04 可先基于三份已抽取核心法规推进候选阶段，但保险法未纳入前不得声称规则集覆盖完整或发布。
- 检查结果：现有核心法规语料含 3 份来源、172 条文和 172 个检索块；9 张候选规则卡引用 34 个 article_id。所有引用均可解析，枚举及必需字段完整，全部卡片 `verified=false`。结构检查通过，法律映射尚待人工逐条核对。
- 新增：`reports/rule-card-candidate-check.md`，记录范围、计数、检查内容、限制和重现命令。
- 更新：`PLAN.md` 将 P0-03A 标为用户要求暂缓，并明确 P0-04 的核心来源候选工作与总体验收边界。
- 命令及结果：临时 Python JSONL 检查通过；`scripts/build_extraction_registry.py` 成功重建集中登记；`scripts/audit_extractions.py` 结构检查通过但 `legal_text_verified=false`；`ruff check scripts` 和 `compileall -q scripts` 通过。
- 规则/模型：候选规则集 `official-v1-2026-10-11`；未调用百炼；无 Key。
- 下一步：继续 P0-04，对三份核心法规的营销相关条文与规则卡映射逐项核对并记录原文定位；之后实现 P0-05 语料校验和发布门禁。保险法抽取按用户指示继续暂缓。

## 2026-10-11 — P0-04 核心候选规则卡范围与映射初核

- 完成：按本地来源条文主题和适用范围初核 9 张候选卡，记录每卡关联条文、成立条件及范围限制。初核结果见 `reports/rule-card-mapping-review.md`；此记录不是逐字法律审校，不能作为规则发布依据。
- 修改：`scripts/build_rule_card_candidates.py` 与生成的 `data/corpus/official-v1-2026-10-11/rule_cards.jsonl`。为产品/机构信息披露卡补入金融产品网络营销管理办法第 8 条；收窄人员/渠道卡文字，分别描述保险销售信息授权、互联网保险平台和金融产品社交媒体渠道义务。9 张卡仍全部 `verified=false`。
- 检查：当前 172 条文、172 个检索块、9 张卡，35 个条文关联均解析成功；Ruff、compileall、登记文件 JSON 校验通过；规则集登记仍为未发布、已验证卡 0。
- 参考：主要依据仍为三份本地文件及其提取快照；官方发布页仅辅助核对。金融监管总局对互联网保险办法的页面抓取返回 403，因此该来源未以网页文本替代本地 DOC。
- 未决：还需逐款核对销售办法第 25、26 条、网络营销办法第 16、17 条、互联网保险办法第 14 至 16 条及其他被引用款项，并记录适用条件、例外和原文定位。保险法抽取依用户指示暂缓。
- 下一步：继续 P0-04 对重点条款逐款审阅；P0-05 实现前先完成候选规则映射审阅，不发布未核对规则。

## 2026-10-11 — P0-04 外部代言条款范围再收窄

- 核对发现：网络营销办法第17条要求引用学术机构、行业协会、专业人士及社会公众人物名义/形象推荐或证明时遵守广告代言规定；本语料未包含具体广告代言规则。不能把该转引义务与“冒用监管部门保证”合并，也不能仅凭该条判断具体代言违法。
- 修改：将监管审核/备案保证风险卡缩为保险销售办法第17条、网络营销办法第10条的直接规则；新增 `public_figure_endorsement_external_review`，checkability 为 `external_verification`，显式要求外部审查而非自动下违法结论。规则卡总数 10、条文关联 34，仍全部未验证。
- 验证：候选生成脚本成功；172 条文及检索块、10 张候选卡和 34 个有效 article_id 关联检查通过；registry 显示验证卡为 0、规则集未发布；Ruff、compileall、JSON 语法检查通过。
- 参考：金融产品网络营销办法本地 PDF；官方公告及附件仅用于辅助确认正文和实施信息。其他条文仍以本地来源和哈希快照为准。
- 下一步：继续审核剩余候选映射和未覆盖条文，完整检查适用范围与例外。保险法抽取保持暂缓。

## 2026-10-11 — P0-01 已验收

- 完成：读取计划、规格及题目；核对环境、五份实际附件大小和 SHA-256、密钥配置存在性。
- 修改：docs/environment.md、PLAN.md、HANDOFF.md。
- 命令及结果：py -0p / --version / pip --version 成功；Get-FileHash 五份成功；未找到 LibreOffice；Word COM 已注册但尚未验证转换。
- 模型调用：未执行；无配置的百炼 Key。
- 规则版本：assignment-v1 尚未发布。缺少规格指定草案，现有 PDF 待核对，已询问用户规则范围。
- 下一步：P0-02 工程骨架及依赖锁定；P0-03 可先做来源提取诊断，范围确认前不能完成版本验收。

## 2026-10-11 — P0-03 提取诊断（未验收）

- 修改：scripts/extract_doc_sources.py、scripts/inspect_pdf_source.py、docs/corpus-review.md、reports/source-inventory.json；data/extracted/ 保存 PDF 原始提取产物。
- 命令：系统 Python 执行 extract_doc_sources.py，Word COM 未完成初始化，取消退出，无 DOC 产物；项目 Python 执行 inspect_pdf_source.py 成功，提取 4 页并渲染首页/末页。
- 工具：pypdf 6.20.0、PyMuPDF 1.28.2。首尾页已实际查看，标注正式公告及施行日期；未做现行效力联网确认。
- 限制：原始 PDF 提取有重复条号与换行噪声，尚未核对全部条文；DOC 文本已用 WPS 提取，仍未逐字核验；用户尚未确认规则范围。
- 状态：P0-03 不勾选，G0 不通过，规则库不发布。五份附件哈希重新清点与初始值一致。

## 2026-10-11 — P0-02 干净安装验证已通过

- 验证：在 `.venv-verify` 中从本地分发包先安装构建工具，再以 `--require-hashes` 安装全部锁定依赖，之后 editable 安装项目。
- 命令结果：`insurance-audit --help`、`--version`、核心模块导入成功；`pip check` 为 `No broken requirements found`；`compileall -q src scripts` 通过。
- 状态：P0-02 已验收。运行依赖仍不包含实际审核功能；CLI 只显示帮助。

## 2026-10-11 — P0-03 转换诊断更新（仍未验收）

- WPS COM `kwps.application` 只读提取两份 DOC 成功，版本 12.0；源哈希在提取前后相同。
- 结构脚本识别出保险销售行为管理办法 50 个有序唯一条文标记，互联网保险业务监管办法 83 个有序唯一条文标记；只证明结构线索完整，不等于逐字核对。
- 条号诊断检查每段开头的第 X 条，数值序列从 1 连续且无重复。
- PDF 4 页逐页文本及首末页预览已保存；排版提取重复有待清洗。
- 规格草案 DOC 缺失，已有正式版 PDF。规则范围问题已询问用户，未收到回答；不把正式版 PDF 混进 assignment-v1。其余条文仍待人工原文核对。
- 下一步：获取规则范围选择后，完成相应附件转换与逐条检查，再进入 P0-04/05。

## 2026-10-11 — P0-02 已验收

- 完成：Python 3.11 项目骨架、包、CLI、模板、忽略规则、离线提取工具与 Windows/Python 3.11 定向哈希锁。
- 修改：pyproject.toml、requirements-build.in、requirements-build.lock、requirements-dev.lock、README.md、.env.example、.gitignore、src/、scripts/。
- 依赖：46 个精确版本及各目标分发包 SHA-256；建立 requirements-build.lock 供源码包构建准备。
- 验证：新建 .venv-verify；本地 wheels 使用 `--require-hashes --no-deps` 安装；源码 editable 安装通过；`insurance-audit --help`、核心包导入及 `compileall -q src scripts` 通过。
- 范围：当前仅有帮助/版本 CLI，审核、语料、API 和页面尚未实现。锁文件针对 Windows x64/Python 3.11；其他平台须重新生成和验证。
- 后续：P0-03 继续检查法规来源与转换；assignment-v1 受附件版本差异阻塞。


## 2026-10-11 — P0-04、P0-05 与核心 G0 已验收

- 范围：按用户暂缓保险法的指示，当前快照仅包含本地三份核心正式法规；保险法扩展 P0-03A 保持暂缓，不纳入本次 G0。
- 完成：全文读取核对 172 条，34 张规则卡，172 条完整范围台账；source-files 保存原始文件副本，extracted-files 保存原始抽取副本。review.json 将来源/抽取哈希、条文原文、规则语义、范围台账与 implementation_agent 审阅身份关联。
- 修正：章节标题不再附着前一条，金融网络营销末条不含网页 Q&A/URL 尾注；互联网保险第十五条第（五）项确有监管名义宣传限制，已恢复对应引用。补齐披露、销售前义务、平台、网络推广与外部核验规则并保留例外。
- 代码：src/insurance_audit/corpus/{ingest,validate,review}.py、cli.py；scripts/{parse_official_articles,build_rule_card_candidates,core_rule_review_data,record_core_review,build_extraction_registry}.py；tests/unit/test_corpus.py。登记状态与 SPEC/PLAN/README 已同步。
- 验证：pytest 18 passed；ruff check/format 通过；validate-corpus 3 文档/172 条文/172 整条块/34 规则/172 台账，完整性错误与审阅门禁均 0；独立 .venv-verify 校验同样通过，pip check 无损坏依赖。pytest 临时原子替换被沙箱拒绝，获准运行原命令后通过。
- 发布：publish-corpus 显式发布 official-v1-2026-10-11；重复发布幂等，ingest/manifest 原位覆盖拒绝。集中 data/extracted/extraction-registry.json 已反映 published 和 agent_reviewed，全部来源原始哈希匹配。
- 证据：reports/core-p0-review.md、reports/corpus-validation.json、reports/corpus-validation.md、reports/p0-acceptance.md。旧候选报告明确标记已被取代。
- 边界：审阅者为实施 agent、不是法律专家；没有真实百炼调用或效果指标。保险法仍未抽取，其他指导意见 reference_only。公开网页未替换本地原文。
- 下一步：P1-01 Schema、三态与 partial/failed 状态矩阵；P1-02 百炼适配及预算。新增法规须新来源 manifest、新快照 ID 与核对/回归，已发布快照不原位补入。

## 2026-10-11 — P0 目录自动化流水线

新增 corpus/pipeline.py、extract.py、wps_worker.py、registry.py 与 CLI pipeline run/watch/start/stop/status/seal。自动检测稳定文件、按哈希保留独立版本，生成包含已发布基础集的候选和审阅模板；review.json 完成后 seal，后台验证并发布。保险法暂缓与 reference_only 保留，未来生效与未核对来源禁止发布。注册 Windows 当前用户登录任务 InsuranceAudit-P0-FolderWatch，每 5 秒循环，系统锁防重复。集中 registry 升级 2.0，不再依赖旧脚本重建。

pytest 33 passed，包括独立监视进程投递/停止实测与真实 PDF 39 条抽取。原快照严格校验继续通过。删除 6 旧脚本、2 过期报告；旧命令在历史记录中保留但不再是当前入口。递归清理缓存/临时产物/复现环境被自动安全策略阻止，未绕过；清单 reports/cleanup-manifest.json，用户可运行 scripts/cleanup_p0.ps1。详细行为与边界见 docs/p0-pipeline.md 和 reports/p0-pipeline-acceptance.md。

## 2026-10-11 — P1/P2 开发进展补记，转为文本优先

- 用户指示：同步本轮开发进展，随后暂时搁置图片识别，先推进文字审核。保留图片实现，不删除历史产物；后续不再主动执行视觉模型调用或图文验收。
- P1 已实现：config.py、schemas.py、models/bailian.py、models/mock.py、retrieval.py、workflow.py、service.py、api.py、doctor.py、CLI 的 doctor/audit-text；含规则全集分批、证据和引用校验、确定性状态聚合、调用预算及错误处理。
- P2 已实现：uploads.py、static/index.html/app.js/styles.css、演示图片及生成脚本；含实际图片格式校验、大小/像素限制、多图来源与顺序、页面和 JSON 导出。未完成完整浏览器及真实图文验收。
- 测试：tests/unit/test_audit.py、tests/integration/test_api.py 已加入；重新执行 `.venv\Scripts\python.exe -m pytest -q`，63 passed in 9.31s。mock、故障注入与真实模型证据分开记录。
- 真实模型：reports/model-doctor.json 记录 qwen3.7-plus 文本 JSON 和 qwen3-vl-plus 提取成功；原 qwen-vl-plus 返回模型不存在后已调整本地配置。密钥不输出、不入文档。
- 失败证据：scripts/live_audit_smoke.py 的 reports/live-audit-smoke.json 当前记录 violation、education、multi 三例 failed/null，均 budget_exhausted，checked=0；不能宣称真实审核链路已通过。
- 配置：.env/.env.example 与 Settings 增加 EMBEDDING_MODEL=text-embedding-v4、EMBEDDING_DIMENSIONS=1024，读取验证通过；尚未启用向量检索。
- 状态：G0 通过；G1/G2 未通过，P3 未开始。PLAN 保留完整验收 checkbox 未勾选，并补充编码进度，避免混同实现与验收。
- 下一步：只运行文本诊断，定位整体 150 秒预算耗尽原因，保留失败报告，修复后重跑三类文本用例并记录真实结果。

## 2026-10-11 — 文本复验与 RAG 方案

- 同步 PLAN/HANDOFF/README，并新增 docs/api-contract.md、docs/decisions.md；P1-01 状态矩阵任务验收，整体 G1 不通过。
- 修改 config.py、models/bailian.py、workflow.py、.env.example/.env、scripts/live_audit_smoke.py、tests/unit/test_audit.py：增加仅文本思考模式开关，本地关闭；audit-v1.1 去除重复 normalized_text 和存储元数据，保留全部法规原文及规则条件；调用记录绑定当前对象；默认冒烟只执行文本且另存报告。
- 实测命令：scripts/live_audit_smoke.py violation education review --out reports/text-audit-smoke-v1.1.json。真实 qwen3.7-plus，规则集 official-v1-2026-10-11；无视觉/Embedding 调用。违规 completed/non_compliant，97.594 秒、6 次调用；教育反例 failed/null，150.016 秒、9 次尝试；局部材料 failed/null，123.265 秒、7 次尝试。后两者仍有 invalid_model_output，教育反例另有 budget_exhausted。不能宣称三态已验收。
- 验证：pytest 65 passed in 9.26s；本轮修改文件 Ruff 通过。完整结果见 reports/text-smoke.md。原始失败证据保留，未覆盖已发布知识库。
- 用户要求模型使用 RAG 并先给方案：docs/text-rag-plan.md 已写入，尚未实现 hybrid。已明确当前 BM25 只记录额外召回 ID、模型上下文由规则卡条文构成的集成缺口。方案为向量+BM25、实际原文上下文、独立必查覆盖、版本绑定及对照评估，复用现有工程。
- 下一步：按 RAG 方案接通索引与上下文；同时细化脱敏校验错误诊断，解决结构化输出失败。图片识别与保险法抽取继续暂缓。

## 文本 RAG 实施与真实复验（本轮）

- 用户要求继续，不等待外部案例收集；图片识别与保险法继续暂缓，未新增外部法规或案例。
- 完成：vector_index.py、Bailian.embed、CLI build-index；172 条 text-embedding-v4/1024 向量索引真实构建，18 次请求、18,067 token。索引哈希绑定规则快照、模型、维度和检索文本，原子写入，重复运行复用；未来超长条文目前拒绝，未自动实现分款索引。
- 接通：retrieval.py 分段 BM25/向量双路 Top 8、RRF k=60；service.py 将召回全文加入实际模型上下文、命中规则优先、全 34 规则覆盖；查询向量预算与模型共享，失败无静默降级。meta 保留检索/上下文 trace、索引标识、版本、token 和脱敏校验类别。
- 修复：worklow.py（实际文件名 workflow.py）中的条件逐字复制失败改为显式 c1/c2 绑定，未知/重复/漏项继续拒绝；Prompt audit-v1.4-rag，错误修复说明包含规则 ID；原文证据及引用校验未放宽。
- 配置：本地 .env 与 .env.example RETRIEVAL_MODE=hybrid；文本 qwen3.7-plus，关闭思考。SPEC 更新 v1.2，PLAN H-01/H-02 勾选工程实现；docs/rag-operations.md、reports/rag-acceptance.md/json、README 和设计记录已同步。
- 验证：pytest 75 passed in 10.46s；Ruff 通过；validate-corpus 3 文档/172 条/34 规则，错误及审阅门禁为 0。新增测试覆盖索引篡改/错维度/不匹配版本、向量乱序、长文尾部、原文注入、失败不得降级、API 未就绪和条件 ID。
- 真实复验：scripts/live_audit_smoke.py violation education review --out reports/text-rag-smoke-v1.4.json。违规 completed/non_compliant 67.406 秒/7 次；教育 completed/needs_review 114.672 秒/10 次；局部 completed/needs_review 62.703 秒/7 次。每例均含 1 次查询向量，未调用视觉；教育发生 3 次批次结构修复。结果所有召回原文进入批次、34 规则台账完整、输出引用与知识库一致。
- 服务：重启本项目 uvicorn（原 PID 14780），新服务监听 127.0.0.1:8000；真实 HTTP /readyz 返回 200、hybrid、vector_index_ready=true、mock=false。
- 限制：教育反例应无违规但仍复核，未达到预期 compliant，G1 不通过；不能声称正式效果改善。当前所有规则仍执行，提示上下文较多。新快照发布后 build-index 仍需显式执行，P0 watcher 未自动付费建索引；P3 和案例知识库未完成。
- 下一步：完善材料商业属性与规则适用性判断，降低教育反例误复核；补全纯文本 API/CLI 三态验收，并以开发集检验检索与 Prompt，保留独立测试集。资料收集不由系统冒充人工标注。

## 2026-10-12 — G1 进度落盘，恢复 P2

状态：未通过。用户要求保存当前进度并恢复 P2，允许 P2 工程工作与 G1 未决项并行推进。

已完成：audit-v1.5-scope 明确材料范围、必要条件与教育语境；校验器处理必要条件为假和范围外规则；增加脱敏 assessment_trace、单次调用墙钟超时及元数据日志。

真实验收：reports/g1-live-acceptance-v1.5.json，五个合成开发案例中四个符合预期：明确违规、原教育反例、局部材料、伪装科普的销售注入。科普改写仍 needs_review（预期 compliant），涉及 approved_marketing_content_use 和 internet_platform_operating_conditions，把内部审批及平台资质要求误用于教育材料。没有修改预期标签。五例均 completed，采用真实 hybrid RAG；并非正式测试集或专家 gold。

离线验证：89 passed；新增 tests/unit/test_g1_scope.py、tests/integration/test_g1_failures.py。真实验收入口 scripts/verify_g1.py（退出码 1 如实表示仍有失败）。

版本：qwen3.7-plus / text-embedding-v4，1024 维；official-v1-2026-10-11，34 规则、172 条文；audit-v1.5-scope。视觉配置 qwen3-vl-plus，本次 G1 不涉及视觉。

下一步：P2 上传、多图证据、网页与真实视觉验收；保留 G1 科普适用性问题及保险法抽取暂缓状态。

修改文件：workflow.py、service.py、models/bailian.py、api.py、上述测试与验收脚本、PLAN.md、README.md、本交接及进度报告。命令：pytest -q（89 passed）；scripts/verify_g1.py --out reports/g1-live-acceptance-v1.5.json（exit 1，4/5 预期匹配）。

## 2026-10-12 — P2 恢复及页面/多图验证

修改 api.py 断连响应及取消任务收尾、static/app.js 提交图片快照及异步示例竞争、styles.css 原图样式、pyproject.toml 静态资源打包；新增 tests/integration/test_p2_multimodal.py、scripts/serve_p2_fixture.py、docs/demo-script.md 和 P2 报告。

真实多图浏览器提交 completed/compliant，73.1 秒，10 次尝试；下载 JSON 落盘。真实 Unicode/HTML 压力输入 partial/non_compliant，78.1 秒，3 违规，直接引用白名单两次失败，原报告保留。页面原图、图序、导出、高亮、文本安全、取消、partial/failed/needs_review、窄屏均检查；后几类故障使用明显标注的本地模拟服务器。

命令：pytest -q（91 passed）；Ruff 全库通过；pip wheel --no-deps --no-build-isolation . -w reports/package-check（成功，static 文件清单核对通过）。具体证据 reports/vision-smoke.md、multimodal-acceptance.md、p2-real-*-browser.json 和截图。

P2-01～03 完成，P2-04/G2 不通过；下一步修复 disclose_material_policy_terms_and_restrictions 的逐规则直接条文引用与修复提示，并复验压力案例，保留 G1 科普改写过度复核。未开始 P3，不修改已发布规则库及测试预期。

补充：真实教育反例浏览器验收 completed/compliant，84.2 秒；下载报告 p2-real-education-browser.json。桌面 1280px 双栏（494/659px）无横向溢出，截图 p2-education-browser.png；viewport 已恢复默认。

## 2026-10-12 — P3 准备与评估工具

用户询问能否进入 P3 并要求可行则继续。按依赖仅推进 P3-01/02；G1/G2 未放行，未跑正式测试或宣称效果验收。新增 evaluation/metrics.py、runner.py、CLI evaluate、tests/unit/test_evaluation.py；data/eval/dev.jsonl/manifest.json 和 docs/evaluation-labeling.md。五条已暴露 G1 案例作为 provisional 开发种子，未编造专家标签、条文 gold 或测试集。

功能：共享 AuditService，bm25/hybrid、mock、历史 JSON 重放；响应逐样本留存，模型/规则/Prompt 元数据和数据/代码哈希；分母含失败/partial、三分类矩阵/F1、双口径违规召回、误报、自动覆盖/准确率、类型 Micro-F1、条文 P/R、原文一致率、失败桶、P50/P95/token。gold 未知用 null，报告不产生伪分数。检测同组/相同文本跨 split；拒绝覆盖非空报告；固定 test 暂不放行。

验证：pytest -q 96 passed in 14.47s；Ruff 全库通过。CLI 历史真实重放 reports/p3-dev-replay-v1.0（5 例，Macro-F1 0.7778、自动覆盖 3/5、24/24 引用原文一致、0 虚构 ID；无类型/条文 gold，相关指标 null），没有新付费调用。另有 p3-mock-runner-v1.0，仅验证批量流程不计入真实效果；较早 p3-g1-replay 是初次开发报告，最终入口指向 v1.0。

待完成：扩展并人工核对 20/40 数据和图文标注，真实案例资料由用户另行收集；修复 G1 科普过度复核及 G2 引用失败；全文基线/共享图片提取 A/B、数据冻结、正式测试及新环境复现。P3-01/02 仍按完整验收要求保留未勾选。
