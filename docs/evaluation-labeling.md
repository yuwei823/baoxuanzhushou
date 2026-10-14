# P3 数据和指标约定

当前仅有 5 条已用于 G1 开发的种子样本，全部 provisional。它们不能成为独立测试集；两条教育改写共享 education_family。目标仍为 20 开发 + 40 测试，测试建议 15 违规/15 非违规/10 复核、至少 12 图文。data/eval/manifest.json 记录目前规模与文件哈希，test_frozen=false，不伪造已冻结测试集。

## 标注

每行遵循 evaluation.runner.Sample：sample_id、group_id、split、text、image_paths、context、expected_decision、expected_categories、expected_article_ids、expected_evidence、annotation_reason、label_status、reviewer、provenance。图片路径相对 JSONL 所在目录，禁止越界。未知分类/条文/证据用 null；已核对确实为空才使用 []。human_reviewed 必须附真实审阅者，不得由 agent 冒充人工。

同一来源、模板和海报变体放在同一 group，few-shot 排除在固定测试之外。加载器检测跨集合同 group 与完全相同文本；语义近似及模板泄漏仍需要人工审查。已有开发失败样本不得转入未见测试。核对条文时只使用当前发布快照原文，并核实适用条件，不照抄模型输出当 gold。

## 指标

混淆矩阵有三类真值和额外 technical_failure 预测列。partial/failed 不从分母删除。完整违规召回只算 completed/non_compliant；另报告包含 partial 的有效违规发现召回。自动覆盖只算 completed 的 yes/no，自动准确率的分母只为这些自动判断。非违规误报包含 partial 中已输出的违规。

Macro-F1 为有定义类别 F1 的均值，无定义类别为 null；类型 Micro-F1 和条文 Precision/Recall 仅统计相应 gold 非 null 的样本，并展示样本数。引用原文一致率只表示与版本原文一致，不表示适用正确。分母为 0 一律 null。延迟使用线性插值 P50/P95，token 沿用响应实测，不估算费用。error_buckets 保留失败代码，runner 异常只保存类名避免泄露。

## 执行

无新 API 调用的历史重放：

```powershell
.\.venv\Scripts\python.exe -m insurance_audit.cli evaluate --split dev --variant hybrid --replay reports/g1-next-live-v2.json --out reports/my-replay
```

真实开发运行（产生用量，报告包含原始样本，须脱敏）：

```powershell
.\.venv\Scripts\python.exe -m insurance_audit.cli evaluate --split dev --variant hybrid --out reports/my-live-dev
```

离线流程验证使用 `--mock --variant bm25`。不读取或输出密钥。已存在的非空报告目录拒绝覆盖；每个样本后保存 results.jsonl、metrics.json 和 report.md，运行结束才标 run_complete=true。响应中保留实际模型、prompt、规则哈希和检索上下文，历史重放不是重新验证当前模型。其中 results.jsonl 是逐样本完整响应，体积大，已列入 `.gitignore` 仅本地留存；report.md、metrics.json、manifest.json、summary.json 仍纳入版本控制。

目前 `--split test` 明确拒绝执行：G2 和人工标签仍未就绪；正式放行时需完成数据冻结及基线比较。当前仅支持 bm25/hybrid，全文基线与共享图像提取的 A/B 尚未实现。
