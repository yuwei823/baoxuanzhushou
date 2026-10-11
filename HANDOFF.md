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
