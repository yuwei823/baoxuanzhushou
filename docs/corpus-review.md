# 法规来源与语料核对记录

日期：2026-10-11；任务：P0-03 已验收，P0-04 进行中；来源、版本及结构抽取完成，语料规则映射尚未完成。

## 范围差异

用户确认所有引用以本地“法律法规”目录中提供的版本为基础。网络营销办法 PDF 已在核心来源中；本地《中华人民共和国保险法.doc》现在登记为补充法律依据，纳入候选规则集，但尚待抽取与核验。其他指导意见暂列 `reference_only`。网上公开的《保险法（修订草案征求意见稿）》是另一种材料状态，不替换现行 DOC，也不混入裁决规则集。

## PDF 初步核对

命令：`.\.venv\Scripts\python.exe scripts/inspect_pdf_source.py`。

- PyMuPDF 1.28.2 按视觉阅读顺序提取 4 页，保留逐页 JSON、干净文本和 PDF 元数据至 data/extracted/。之前 pypdf 提取出现重复标题，当前语料准备应使用 PyMuPDF 产物。
- 四页均渲染并实际查看。页面正文含首尾、章节和第 1 至 39 条，视觉文字完整可读。
- 文件首页显示公告〔2026〕第 9 号，发文日期 2026-04-21，正文标注自 2026-09-30 起实施；这是对附件内容的观察，不代表本轮已联网核验其现行效力。
- 官方市场监管总局公告页确认文件正式发布及施行日期：https://www.samr.gov.cn/ggjgs/tzgg/art/2026/art_45df2e4c27674b2c82b9a5b4489b64ad.html 。官方下载端由 curl 返回 403，未作文件字节哈希比较。本地 PDF 生成器为 Qt 5.5.1、四页，作为用户提供的快照逐页计算哈希；原始文字已与官方发布信息和条文样本交叉核对。
- PyMuPDF 提取按视觉阅读次序保留换行，无重复的条文行首；正文仍包含分页断行，需要文章解析阶段保留原始文本并处理规范化，不覆盖原文。
- 原始 SHA-256 与环境清点一致。

## 官方来源交叉核对

- [保险销售行为管理办法（金融监管总局）](https://www.nfra.gov.cn/cn/view/pages/rulesDetail.html?docId=1129945)：页面载明2023-09-20公布、2024-03-01施行。
- [金融产品网络营销管理办法（市场监管总局公告页）](https://www.samr.gov.cn/ggjgs/tzgg/art/2026/art_45df2e4c27674b2c82b9a5b4489b64ad.html)：公告〔2026〕第9号，载明自2026-09-30起施行。
- [互联网保险业务监管办法（金融监管总局）](https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=949137)：页面载明2020-12-07发文、2021-02-01施行。

## DOC 提取尝试

- 四份 DOC 文件头均为 OLE 复合文档格式，不是扩展名伪装的普通文本。
- 本机未找到 LibreOffice 或 Word 可执行文件；存在 WPS Office 12.0 及系统 Python 的 pywin32。
- 系统 Python 的 Microsoft Word COM 初始化未完成，未产出文本；已结束该提取尝试。
- WPS 官方接口文档给出 `kwps.application` 外部自动化入口：https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/wps/Application/obj 。已用隔离实例、禁宏、只读打开两份核心 DOC，文本和逐段 JSON 提取成功；来源哈希复读一致。
- 结构诊断：保险销售行为管理办法识别到 50 个有序唯一条文标记（第 1 至 50 条）；互联网保险业务监管办法识别到 83 个有序唯一条文标记（第 1 至 83 条）。这只检查提取标记的顺序和缺号，未证明正文逐字准确、无段落遗漏或法规版本适用正确。
- DOC 抬头与收尾元数据显示《保险销售行为管理办法》公布日期 2023-09-20、生效日期 2024-03-01；《互联网保险业务监管办法》公布日期 2020-12-07、生效日期 2021-02-01。与对应官方监管网页信息一致。
- 提取调用：`py -3.11 scripts/extract_doc_sources.py`；pywin32 312、WPS COM 版本 12.0。结构检查由项目 Python `scripts/audit_extractions.py` 执行。
- `data/extracted/source-audit.json`：保险销售办法 50 条、互联网保险办法 83 条、网络营销办法 39 条，均按全文行首标记连续且无重复/缺号。各源文件 SHA-256 已写入 `data/extracted/official-source-manifest.json`，manifest 标明语料未发布。

## P0-04 初始解析结果

`python scripts/parse_official_articles.py` 从已提取的来源生成独立正式版目录 `data/corpus/official-v1-2026-10-11/`，共 172 条（50/39/83）。每条含原文、空白规范化文本、SHA-256 与来源定位。当前是解析候选，不是经过逐字法律校验的知识库；`verified:false`，也尚未生成经核对的规则卡。不得供审核工作流发布使用。

`scripts/build_rule_card_candidates.py` 已建立 9 张优先审核候选卡，关联当前三份已抽取核心法规。所有卡均为 `candidate_pending_legal_mapping_review` / `verified:false`；保险法抽取后还需补充和审查相关映射。候选卡不应作为已核验法律规则用于最终审核。

## 集中抽取登记

统一入口为 `data/extracted/extraction-registry.json`。其中每个来源关联本地路径与源 SHA-256、抽取工具及版本、抽取输出路径及 SHA-256、抽取状态与尝试、结构检查、法律文本/规则映射核验状态、候选语料条数及语料文件哈希。它也登记整体规则卡文件哈希、卡片数和已验证卡片数。`data/sources/catalog.json` 是来源元数据登记；集中 registry 是抽取与核验状态的汇总视图。运行 DOC/PDF 抽取、结构审计、候选语料解析或候选卡生成脚本时会重建该 registry；也可单独运行 `python scripts/build_extraction_registry.py`。

当前状态：保险销售办法 WPS COM 12.0 已抽取（50 条）；互联网保险办法 WPS COM 12.0 已抽取（83 条）；网络营销办法 PDF PyMuPDF 1.28.2 已抽取（39 条）；本地保险法登记在案但 WPS COM 返回拒绝访问，抽取失败、0 条进入候选语料；金融消费者权益保护指导意见标为 `not_selected`。所有法律文本核验和规则映射仍未完成，候选规则集未发布。

## 验收剩余

- 原始来源的逐字内容仍需要在 P0-04 建规则卡时结合条文样本和官方网页复核；不能把结构检查描述成法律审核已完成。
- 现有 PDF 不能从官方站通过命令行下载作 SHA 对比（403）；保留其本地原始 SHA 与官方网页 URL。
- 可开始 P0-04 的条文拆分和候选卡片，但规则卡在对应条文复核前保持 `verified:false`，知识库发布仍受 P0-05 门禁约束。
- 《中华人民共和国保险法.doc》本地哈希已登记，但 WPS COM 重试返回拒绝访问，尚无可靠提取文本；P0-03A 未验收，不能声称其条文已进入条文库。
- 后续法规扩展按 `data/sources/catalog.json` 登记来源，再由规则集 manifest 显式固定来源版本与哈希。已发布规则集不可覆盖；新规或修订生成候选新 ID，校验、规则映射及回归评估通过后才切换当前版本。目录有新文件不会自动激活。
