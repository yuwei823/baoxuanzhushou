# 审核接口契约（当前实现）

2026-10-11。对应 schemas.py、api.py、service.py。图片代码保留，当前开发与真实验收以纯文本为主。

POST /api/v1/audits 使用 multipart/form-data；text 为最多 10,000 Unicode 码点的文本，context 为可选 JSON 字符串，depth 为可选审核模式。图片参数 images 支持文件，禁止 URL/任意服务器路径。文本与图片至少提供一项。

context 四个字段默认 unknown：channel（internet/offline），publisher_type（insurance_institution/insurance_intermediary/marketing_personnel/other），product_type（insurance/life_insurance/property_insurance/other），material_completeness（complete/partial）。用户声明不等于外部认证。

depth 默认 concise，对应“初审”：先用 BM25 与向量检索召回相关法条，再只审核与命中法条直接或支持关联的规则卡。strict 对应“完全 · 查验所有规则”：审核规则全集，并按批次用 RAG 补充相关法条。非法取值返回 422。

初审模式未被选中的规则以 coverage.rules.status=not_reviewed 明示，并记录在 meta.omitted_rule_ids；它们不会被当作不适用或已通过。若初审模式未发现明确违规，有限覆盖本身会使结论保持 needs_review；完整规则结论必须使用 strict。

`rule_id` 继续作为稳定的机器接口字段；`meta.rule_display_names` 返回当前规则集全部规则 ID 对应的中文名称。前端展示中文名称，JSON 中保留原始 ID 以便追踪、评估和回放。

开发评估 CLI 默认使用 strict，避免把初审模式的有限覆盖当作正式评估口径；如需比较成本与召回范围，可显式传 `--depth concise`。`audit-text` CLI 同样默认 strict。

接口默认开放，不校验访问口令。如需限制访问请在反向代理层实现。

## 进度流：POST /api/v1/audits/stream

与 /api/v1/audits 接受完全相同的 multipart 请求体与校验，但以 Server-Sent Events 返回，便于前端在审核过程中显示真实进度。事件类型：

| 事件 | 时机 | data 字段 |
|---|---|---|
| progress | 各阶段开始与每个裁决批次完成 | stage（start/extract/observation/retrieve/judge/done）、total_rules、planned_rules、total_batches、completed_rules、completed_batches |
| progress（stage=observation） | 每张图片识别完成后 | image_id、total_images、observations、visible_text、unreadable_regions |
| result | 审核结束 | 与阻塞接口完全相同的响应体 |
| error | 流内异常 | message（异常类型名） |

进度是**尽力而为的遥测**：投递失败不会使审核失败；`completed_rules` 在 done 事件时等于 `total_rules`。规则按共享条文聚类打包，因此 `total_batches` 小于规则数（当前 46 条规则 → 25 个批次）。空行注释帧 `: keep-alive` 每 15 秒发送一次，防止代理超时断开。

`observation` 事件让前端在裁决进行期间展示模型读图所见。图片并发识别，因此多个 observation 事件会在 extract 阶段集中到达，而不是逐张实时到达。

## 确定性状态矩阵

| 情况 | status | decision | is_compliant |
|---|---|---|---|
| 有通过校验的违规，无技术错误 | completed | non_compliant | no |
| 有通过校验的违规，同时有技术错误 | partial | non_compliant | no |
| 无明确违规，有阻断性业务疑点 | completed | needs_review | null |
| 无违规、无阻断项、无技术错误 | completed | compliant | yes |
| 无通过校验的违规，有技术错误 | failed | null | null |

partial 返回 HTTP 200；审核失败按错误原因返回 502/503/504。输入错误主要为 413/415/422；multipart 解析错误可为 400。输入错误 envelope 不包含未执行的 coverage。

响应包括 violations、review_items、coverage.rules、errors、sources、images、ruleset_id、trace_id 和 meta。顶层 confidence=null、confidence_kind=not_computed；单项模型自评标为 model_self_report，不是正确率。

证据分 present 与 absence。present 的 start/end 为 Unicode 码点左闭右开；文本来源起点保留原输入位置。absence 仅在适用条件明确且完整材料可读时成立，标注完整性来自用户声明。条文原文由本地 article_id 回填。

coverage.total 为规则全集数量；eligible 排除 not_applicable/out_of_scope/not_reviewed；checked 为已检查条数；coverage_ratio=checked/eligible；resolved_ratio 为已检查且无 uncertain 的条数/eligible。分母为 0 时比率为 null。当前 v2 共 46 条规则；都有处理记录不等于均已确认适用或通过。

GET /healthz 检查进程，/readyz 检查本地配置与语料，不调用付费模型。GET /api/v1/rulesets/current 提供当前快照，GET /api/v1/articles/{article_id} 只允许读取快照内 ID。

契约和故障注入测试已实现；完整 G1/G2 验收状态以 PLAN 与实际报告为准。


## 性能诊断（workflow 1.4-batch-targeted-rag）

meta.rule_status_counts 按 coverage.rules.status 汇总，包含材料待核验及技术失败的区别。meta.calls 的 queue_ms 是等待本进程模型信号量的时间；request_ms 从取得名额后发请求到返回/异常，含网络与服务端处理。旧 latency_ms 包含排队，不能用于推算模型纯并行度。

transport_retry 为网络层重试序号（0=首次）；structure_attempt 为结构/证据校验后的修复序号（0=首次，1=唯一一次修复）。结构修复内仍可能遇到网络重试，meta 分别计数。每条调用有返回用量时保留 token_usage 与 reasoning_tokens；供应商未返回细分则 null，失败请求未知用量不能据此宣称没有计费。backoff_ms 是计划退避等待时间，outcome 只记录安全错误类别/HTTP 状态，不记录服务端异常正文。

未取得并发名额的超时不算已发送调用，整体耗时和规则 failed 台账仍记录。简要模式的 hidden_review_items 是被隐藏的补充提示数量，不改变最终聚合。

meta.context_trace 逐批记录实际送入模型的 article_ids、retrieved_article_ids、因定向筛选或预算未加入的 dropped_retrieved_article_ids、retrieval_context_mode、可选条文条数/字符上限以及 prompt_characters。直接与支持条文始终保留；只有额外 RAG 召回可省略。顶层 meta.retrieved_article_ids 仍保留本次文本的完整有序命中，便于区分“检索到了”与“本批实际使用”。meta.retrieval_executed 明示本次是否真正执行查询向量、BM25 与 RRF；`RAG_BATCH_CONTEXT_MODE=none` 时为 false，检索 trace 和命中列表为空。

默认 `targeted` 模式把文本的全局 RRF 顺序与当前批次直接法条的 BM25/向量相似顺序再次融合，候选需同时处于两侧前列，每批最多加入 8 条、8,000 字符。`global` 仅用于 A/B 复现旧行为，`none` 用于无额外召回条文的工程基线；三种模式都检查全部规则，不能用相似度删除规则。
