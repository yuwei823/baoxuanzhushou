# 评估报告

开发诊断；provisional 与 mock 结果均不代表专家 gold 或正式效果达标。

运行方式：replay；样本：5；数据 SHA-256：fff9b70f744b4b64a072a93134591a83ff74ca46ad0693061c62790def4cbe7f

| 指标 | 数值或分子/分母 |
|---|---|
| samples | 5 |
| macro_f1 | 0.7777777777777777 |
| violation_recall | 1.0 (2/2) |
| valid_violation_detection_recall_including_partial | 1.0 (2/2) |
| non_compliant_false_positive_rate | 0.0 (0/2) |
| automatic_coverage | 0.6 (3/5) |
| automatic_accuracy | 1.0 (3/3) |
| technical_failure_rate_including_partial | 0.0 (0/5) |
| type_micro_f1 | None (0/0) |
| type_labeled_samples | 0 |
| article_precision | None (0/0) |
| article_recall | None (0/0) |
| article_labeled_samples | 0 |
| citation_original_match | 1.0 (24/24) |
| citation_count | 24 |
| unknown_articles | 0 |
| mock_samples | 0 |

完整混淆矩阵、标签状态、延迟及 token 用量见 metrics.json。逐样本完整响应见 results.jsonl（体积大，已列入 `.gitignore`，仅本地留存）。

## 未匹配或技术失败案例

- education_paraphrase: expected=compliant; actual=needs_review; status=completed; errors=
