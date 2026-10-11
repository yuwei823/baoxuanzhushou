# 纯文本开发冒烟记录

日期：2026-10-11。真实百炼 API，非 mock；合成演示案例，不是专家标注集或正式效果评估。

模型 qwen3.7-plus，BAILIAN_TEXT_ENABLE_THINKING=false；规则集 official-v1-2026-10-11；Prompt audit-v1.1。并发 2、调用超时 45 秒、整体 150 秒、最多 16 次尝试均未放宽。此次未调用视觉或 Embedding 模型。

| 用例 | 执行状态 | 业务结论 | 耗时 | 尝试数 | 问题 |
|---|---|---|---|---|---|
| 明确违规文案 | completed | non_compliant | 97.594 秒 | 6 | 无技术错误；3 违规项、18 复核项 |
| 教育性否定反例 | failed | null | 150.016 秒 | 9 | invalid_model_output、budget_exhausted |
| 局部材料 | failed | null | 123.265 秒 | 7 | invalid_model_output |

详细结果：text-audit-smoke-v1.1.json。原始失败报告 live-audit-smoke.json 保留。关闭思考后的 audit-v1.0 单例记录在 text-audit-smoke.json：违规 completed/non_compliant，128.921 秒、7 次尝试。不同单次运行和修复次数不构成性能对照实验。

修复与验证：增加文本思考开关并只作用于文本调用；提示去掉重复 normalized_text 与存储字段，保留所有条文全文及规则条件；调用记录使用本次调用对象；脚本默认仅文本且另存报告。新增参数作用范围及全文保留测试。pytest 65 passed in 9.26s；本轮修改 Python 文件 Ruff 检查通过。

结论：已打通一个真实违规案例，但三态端到端仍未通过，G1 保持未验收。当前失败仅返回通用结构/证据约束错误，下一步需加入不含原始材料的精确校验错误类别，定位失败条件后改进结构化输出与修复提示；不得放松引用或证据约束使案例通过。

复现（产生 API 用量）：

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe scripts/live_audit_smoke.py violation education review --out reports/text-audit-smoke-v1.1.json
```

RAG 改造方案另见 docs/text-rag-plan.md，尚未实施；当前检索额外召回原文未独立进入模型上下文。
