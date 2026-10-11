# 实施交接记录

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
