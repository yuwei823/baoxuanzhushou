# 审核性能与覆盖率实测报告

2026-10-12。本文件汇总审核耗时与规则覆盖率的实测数据，供决策参考。所有数字来自本地真实模型调用（`qwen3.7-plus` + `text-embedding-v4`），非模拟。

## 1. 测试条件

| 项目 | 值 |
|---|---|
| 规则集 | `official-v2-2026-10-12` |
| 规则数 | 46（v1 的 34 + 保险法 12） |
| 法条数 | 359（v1 的 172 + 保险法 187） |
| 检索模式 | hybrid |
| 文本模型 | `qwen3.7-plus` |
| 测试文本 | 「某保险产品宣传：本产品保本保收益，年化收益率8%，稳赚不赔。投保即享高额回报，无任何风险。限时抢购，错过不再有。联系代理人张经理，电话13800008888。该产品由某保险公司承保，收益写进合同，绝对安全。」 |
| 上下文 | channel=internet, publisher=insurance_institution, product=life_insurance, completeness=complete |
| 审核模式 | concise |

关键配置（来自 `.env`）：

```
MODEL_CONCURRENCY=8
BATCH_RULE_COUNT=2
AUDIT_MAX_MODEL_ATTEMPTS=40
AUDIT_TIMEOUT_SECONDS=150
MODEL_TIMEOUT_SECONDS=45
```

## 2. 初步观察：输出长度是重要因素，尚未隔离输入影响

裸模型测试（绕过业务代码）显示耗时与 `completion_tokens` 有相关性；只有三组样本，未固定输出长度或服务端负载，不能据此证明输入长度无影响：

| 测试 | prompt tokens | completion tokens | 耗时 | 速率 |
|---|---|---|---|---|
| 极简（"回复：ok"） | 13 | 210 | 4.3 s | 49 tok/s |
| 短 | 30 | 1,121 | 19.5 s | 57 tok/s |
| 中 | 410 | 1,798 | 31.6 s | 57 tok/s |

**输入只有 13 token 也要 4.3 秒**，而输出 1,798 token 要 31.6 秒。生成速率稳定在 **约 60 tokens/s**。

工作假设：优先减少冗余输出，同时测量输入、排队、请求、重试等因素；保留完整条件和证据，不将省略条件解释为通过。

## 3. 模型对比（同一 prompt，约 18K 字符）

| 模型 | 耗时 | completion tokens | 说明 |
|---|---|---|---|
| `qwen-turbo` | 2.0 s | 243 | 最快，但输出偏短 |
| `qwen-plus` | 5.9 s | 245 | 快 |
| `qwen3.7-plus` | 53.5 s | 2,167 | 输出较长；推理 token 构成未单独验证 |

三者都能通过 JSON Schema 校验。`qwen3.7-plus` 的 completion 是另两者的 **9 倍**，这与耗时增加相关，尚未排除其他因素。当前配置 enable_thinking=false；须根据实际 usage 中 reasoning_tokens 判断，缺失字段为未知，不记为 0。

> 注：单规则测试时 `qwen-plus` 只用 245 token；但真实审核（6 规则/批）平均约 960 token，因为要覆盖全部规则与条件。

## 4. 并发与批次调优

### 4.1 并发（`MODEL_CONCURRENCY`）

规则批次可并发；查询 embedding 和检索先于规则判断，不是所有调用都彼此独立。

| 并发 | 总耗时 | judge_ms | 调用数 | 覆盖率 | 状态 |
|---|---|---|---|---|---|
| 2 | 88.3 s | 88.1 s | 7 | 20% | partial |
| **8** | **52.6 s** | 52.2 s | 9 | **38%** | completed |

旧 latency_ms 从等待并发名额前计时，包含排队；191.7 / 52.2 不能作为真实并行度。新诊断分别记录 queue_ms、request_ms，且 request_ms 仍包含网络与服务端处理，不等同纯生成时间。

### 4.2 批次大小（`BATCH_RULE_COUNT`）

| 配置 | 总耗时 | 覆盖率 |
|---|---|---|
| batch=6 | 88 s | 20% |
| batch=3 | 33.9 s | 23% |
| **batch=2** | **19.4 s** | 25% |
| batch=2 + attempts=40 | 27–29 s | **46%** |

批次越小 → 单次输出越少 → 单次延迟越低。

## 5. 规则聚类打包实验

### 5.1 动机

规则卡中大量规则**共享同一条法条**，实测重叠情况：

| 重叠度 | 规则对数量 |
|---|---|
| 1.00（完全相同） | 15+ 对 |

例：5 条中介规则共享保险法第 131 条：

```
intermediary_prohibited_deception_and_concealment
intermediary_prohibited_off_contract_benefit
intermediary_prohibited_coercion_and_misrepresentation
intermediary_prohibited_premium_misappropriation
intermediary_prohibited_illegal_commission_seeking
```

被多条规则共享的法条：18 条（如 art_015 被 7 条规则共用）。

原实现只是**按顺序切分**规则列表，导致同源规则被切到不同批次，各自重复携带同一条法条原文。

### 5.2 实现

`Corpus.batches()` 改为：

1. 用并查集按「直接引用法条」聚类（共享法条即合并）
2. 多规则簇优先处理，簇内按 `max_batch_rules` 上限切分
3. 单规则簇（与其他规则无共享）打包合并，避免一规则一次调用
4. 批次在「携带法条字符数超 `article_budget`」或「规则数超上限」时关闭

`article_budget = batch_max_characters // 3 = 30,000` 字符。

### 5.3 聚类对 prompt 大小的影响（静态测量）

| 每批上限 | 批次数 | prompt 总量 | 每批规则数 |
|---|---|---|---|
| 2 | 25 | 358,000 | 多为 2 |
| 3 | 17 | 289,159 | 多为 3 |
| 4 | 13 | 253,579 | 多为 4 |
| 6 | 10 | 229,026 | 多为 6 |
| 8 | 8 | 212,065 | 多为 8 |
| **聚类前（顺序切分）** | **23** | **405,911** | 2 |

聚类确实减少了法条重复携带：相同 cap=2 时 prompt 从 405,911 减至 358,000（约 11.8%）；cap=3 的 29% 同时包含批次大小改变，不能全部归因于聚类。

### 5.4 聚类对真实耗时的影响（实测）

| 每批上限 | 批次数 | 总耗时 | 覆盖率 | completion tokens |
|---|---|---|---|---|
| cap=8 | 8 | **116.4 s** | 26% | 11,122 |
| cap=4 | 13 | 51.2 s | 22% | 13,375 |
| **cap=3** | **17** | **34.2 s** | **44%** | 10,597 |
| cap=2 | 25 | 35.9 s | **53%** | 11,584 |
| 聚类前（顺序切分） | 23 | **27–29 s** | 46% | ~8,000 |

### 5.5 关键观察

**cap=8 最慢（116 秒）**：虽然调用最少（11 次），但单次输出 1,400 token，单次最长 45 秒。11 次 ÷ 8 并发 = 2 轮，每轮等最慢的，总耗时反而最高。

**cap=2 比 cap=3 略慢**（35.9 s vs 34.2 s）：cap=2 有 25 批，并发 8 下需 4 轮；cap=3 有 17 批，3 轮。**并发轮次比单次延迟更影响总耗时。**

**cap=3 是待复验候选**：34.2 秒、44% 覆盖率、prompt 省 29%。

**聚类前最快（27–29 秒）**：但 prompt 用量最大（405,911 字符），仅凭输入字符数不能确定费用最高，还需输出 token、重试用量和实际单价。

## 6. 覆盖率问题

即使调优后，覆盖率仍未达 100%。需按状态分别统计，不能把所有未 checked 项归因于技术失败：

needs_context 和 external_verification_required 表示材料不足或需要外部核验，不能通过提高重试次数消除。completed 仅表示无技术错误，不代表所有规则已得出明确结论。

**结构或语义校验失败**：部分批次模型输出不符合 JSON Schema，触发一次修复重试后仍失败，该批全部规则作废。

实测错误样例：

```json
{
  "stage": "judge",
  "code": "invalid_model_output",
  "message": "模型输出经一次修复后仍不符合结构验证约束。",
  "rule_ids": [6 条规则]
}
```

覆盖率计算口径（`coverage`）：

- `total` = 规则全集（46）
- `eligible` = 排除 `not_applicable` / `out_of_scope`
- `checked` = 已检查条数
- `coverage_ratio` = `checked` / `eligible`
- `resolved_ratio` = 已检查且无 `uncertain` 的条数 / `eligible`

**覆盖率不是准确率。** 46 条都有处理记录，不等于 46 条都已确认适用或通过。

## 7. 模型调用次数构成

以 batch=2 为例：

| 来源 | 次数 |
|---|---|
| 检索 embedding | 1 |
| 规则判断（46 ÷ 2 = 23 批） | 23 |
| 结构修复重试（每批最多 1 次） | 0–23 |
| 视觉提取（每图） | N |
| **合计（无图、无重试）** | **24** |
| **合计（无图、全部重试）** | **47** |

以上 23 批仅适用于旧顺序切分。聚类后 cap=2 的静态结果为 25 批，则无图基础调用 26 次，全部一次结构修复为 51 次；网络重试另计。实际分批还受完整上下文拆分影响，必须按真实批次计数。`AUDIT_MAX_MODEL_ATTEMPTS=40` 在极端重试下会撞上限；保留预算保护，不以无限重试掩盖结构失败。

## 8. 权衡总结

| 目标 | 手段 | 代价 |
|---|---|---|
| 降耗时 | 提高并发 | 可能触发服务端限流 |
| 降耗时 | 减小批次 | 调用次数增加，撞 attempts 上限风险 |
| 降耗时 | 换非推理模型 | 判定质量可能下降，需评估 |
| 降成本 | 规则聚类 | 单批输出增大，耗时可能上升 |
| 提覆盖 | 提高 attempts / timeout | 等待更久 |
| 提覆盖 | 减小批次 | 调用次数增加 |

**当前实验尚未证明存在同时最优化「耗时」与「成本」的配置**：聚类省 prompt 但增耗时，小批次快但调用多。

## 9. 未验证方向

以下方向未实测，供后续评估：

1. **换 `qwen-plus` 或 `qwen-turbo`**：单规则测试快 9–25 倍，但真实审核质量未评估
2. **简化输出 schema**：如减少冗余解释；仍完整输出 true/false/unknown 条件，禁止省略条件默认通过
3. **按规则单独重试失败批次**：而非整批作废，可提升覆盖率
4. **提高 `AUDIT_TIMEOUT_SECONDS`**（150 → 240）：让更多批次完成
5. **索引二进制化**：当前 JSON 存 359×1024 浮点数占 8.2 MB，可压至约 1.5 MB

## 10. 复现方式

```bash
# 启动本地服务
.\.venv\Scripts\python.exe -m uvicorn insurance_audit.api:app --host 127.0.0.1 --port 8100

# 关键环境变量
MODEL_CONCURRENCY=8
BATCH_RULE_COUNT=2
AUDIT_MAX_MODEL_ATTEMPTS=40
```

响应中 `meta` 字段包含全部诊断数据：

```json
{
  "latency_ms": 34154,
  "stage_latency": {"extract_ms": 0, "retrieval_ms": 437, "judge_ms": 33641},
  "attempts": 19,
  "token_usage": {"prompt_tokens": 133421, "completion_tokens": 10597},
  "calls": [{"kind": "text", "latency_ms": 12345, "actual_model": "qwen3.7-plus"}],
  "hidden_review_items": 8
}
```

`coverage` 字段给出逐规则的 `status`、`finding` 与 `reason`。

## 11. 免责

- 测试文本仅 1 条，样本量小，结论可能有波动
- 真实审核结果受模型服务端负载影响，同一配置多次运行耗时会有差异
- 覆盖率反映「已检查比例」，不代表判定准确性
- 模型置信度未经校准，不作为正确率


## 12. 2026-10-12 诊断修正与受控复验

旧表格作为历史观察保留，不代表新规则集的稳定性能结论。新代码 workflow=1.2-diagnostics，逐调用记录 queue_ms、request_ms、transport_retry、structure_attempt、token_usage、reasoning_tokens（供应商未返回则 null）、outcome；latency_ms 保持旧口径以兼容。未获得调用名额就超时不会计为已发出模型调用；整体耗时与失败台账仍保留。

meta.rule_status_counts 区分 checked、not_applicable、out_of_scope、needs_context、external_verification_required、failed。网络重试次数和结构修复次数分别统计，模型输出不合约仍执行原校验，未放宽证据/引用约束。

`scripts/benchmark_audit.py` 固定 v2 快照、Prompt、五个已暴露 G1 开发案例、关闭思考、同一时间/次数预算；按固定随机种子交错模型配置顺序，每次仅一个审核请求，避免多个实验竞争配额。每条响应落盘，记录源码哈希与数据哈希；输出目录拒绝覆盖。真实 API 产生用量，仅作工程诊断，不能当成专家 gold 或正式测试集。

第一阶段比较三个模型、batch=2/concurrency=8；第二阶段在选定候选上比较 batch=2/3、concurrency=4/8，各重复两轮。配置比较不自动写入 .env；没有稳定性证据不切换线上模型。最新结果目录和结论见后续执行记录。
