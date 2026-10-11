# 审核接口契约（当前实现）

2026-10-11。对应 schemas.py、api.py、service.py。图片代码保留，当前开发与真实验收以纯文本为主。

POST /api/v1/audits 使用 multipart/form-data；text 为最多 10,000 Unicode 码点的文本，context 为可选 JSON 字符串。图片参数 images 支持文件，禁止 URL/任意服务器路径。文本与图片至少提供一项。

context 四个字段默认 unknown：channel（internet/offline），publisher_type（insurance_institution/insurance_intermediary/marketing_personnel/other），product_type（insurance/life_insurance/property_insurance/other），material_completeness（complete/partial）。用户声明不等于外部认证。

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

coverage.total 为规则全集数量；eligible 排除 not_applicable/out_of_scope；checked 为已检查条数；coverage_ratio=checked/eligible；resolved_ratio 为已检查且无 uncertain 的条数/eligible。分母为 0 时比率为 null。34 条都有处理记录不等于 34 条均已确认适用或通过。

GET /healthz 检查进程，/readyz 检查本地配置与语料，不调用付费模型。GET /api/v1/rulesets/current 提供当前快照，GET /api/v1/articles/{article_id} 只允许读取快照内 ID。

契约和故障注入测试已实现；完整 G1/G2 验收状态以 PLAN 与实际报告为准。
