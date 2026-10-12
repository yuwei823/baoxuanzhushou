# G1 真实工程验收（2026-10-12）

状态：**通过**。五个合成开发案例全部符合预期，verify_g1.py 退出码 0。这是工程验收，不是效果评估；label_status=provisional，案例不构成专家 gold 或正式测试集。

## 修复内容

- 科普改写过度复核：`approved_marketing_content_use`、`internet_platform_operating_conditions` 把内部审批/平台条件误用于教育材料。修复方式为 Prompt 层 `trigger_guidance`（明确触发条件以“材料是否呈现营销宣传/平台运营活动”为核心，中性教育材料判 false），规则卡未改、预期标签未改。Prompt 版本 `audit-v1.6-citation-guidance`。
- 逐规则引用：judge payload 增加逐规则 `allowed_citations` 与条文 `direct_for_rule_ids` 标注，禁止跨规则借条文；修复提示携带可引用条文（条号+开头原文）。中间轮 `illegal_financial_activity_marketing` 跨规则借条文失败后加标注复验通过。

## 验收结果（reports/g1-next-live-v2.json）

| 案例 | 接口 | 预期 | 实际 | 结果 |
|---|---|---|---|---|
| violation | http | non_compliant | non_compliant | 通过 |
| education | http | compliant | compliant | 通过 |
| partial_material | http | needs_review | needs_review | 通过 |
| disguised_sale_injection | http | non_compliant | non_compliant | 通过 |
| education_paraphrase | cli | compliant | compliant | 通过 |

全部案例 status=completed、errors=[]；hybrid 真实检索、无视觉调用、34 规则台账完整、引用原文一致、证据偏移正确。中间失败轮（violation 案例跨规则借条文）的经过记录于 HANDOFF.md 历史，其报告文件已随 2026-10-12 清理删除。

## 版本

文本 qwen3.7-plus（思考关闭）、text-embedding-v4 1024 维、official-v1-2026-10-11（34 规则/172 条文）、audit-v1.6-citation-guidance、workflow 1.1-rag、segment512-rrf60-top8-v1。

## 边界

- 合成开发案例、provisional 标签；不宣称准确率或效果达标。
- 模型输出存在随机性：单次全过为本次验收证据；正式稳定性评估依赖 P3 已核对数据集。
- meta.validation_errors 中 attempt=1 的记录是“修复成功”轨迹，attempt=2 无失败即通过。
