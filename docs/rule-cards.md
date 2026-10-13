# 规则卡：形态、实例与设计理由

> 本文回答三个问题：规则卡长什么样、举一条真实实例、以及**为什么不能直接用法律条文切分后的向量**。
> 所有内容取自当前仓库代码与已发布快照 `official-v3-2026-10-12`（46 张规则卡、359 条条文）。

---

## 一、规则卡的具体形态

规则卡是 `data/corpus/<ruleset_id>/rule_cards.jsonl` 里的一行 JSON —— **JSONL 格式，一张卡一行**。当前快照 `data/corpus/official-v3-2026-10-12/rule_cards.jsonl` 共 46 行。

它不是给模型看的自由文本，而是**带 schema 的结构化记录**：代码按固定字段名消费（见 `src/insurance_audit/workflow.py` 的 `JUDGE_RULE_FIELDS`），并对其中若干字段做强制校验。

### 1.1 真实实例

以下为快照中的真卡 `no_regulatory_guarantee_or_filing_endorsement`（「不得利用监管审核/备案为产品背书」），原文照抄：

```json
{
  "rule_id": "no_regulatory_guarantee_or_filing_endorsement",
  "article_ids": [
    "insurance_sales_behavior_order_2023_02::art_017",
    "financial_network_marketing_order_2026_09::art_010",
    "internet_insurance_supervision_order_2020_13::art_015"
  ],
  "category": "regulatory_or_public_figure_endorsement",
  "subject_scope": ["marketing_entity", "marketing_personnel"],
  "channel_scope": ["all_marketing"],
  "product_scope": ["insurance", "financial_product"],
  "trigger_conditions": [
    "material invokes regulatory review or filing to suggest a product guarantee, or online insurance commercial promotion uses a regulator or its staff's name or image"
  ],
  "prohibited_or_required_behavior": "Do not use regulatory review or filing to imply a product guarantee. Internet insurance article 15 item 5 also prohibits misleading interpretations of regulatory policy and commercial promotion using, or indirectly using, regulators or their staff's names or images.",
  "exceptions": [
    "Neutral factual reporting of an approval or filing is not automatically a guarantee or endorsement; the exact wording and context matter."
  ],
  "required_facts": [
    "exact wording and imagery",
    "context and attribution",
    "approval or filing facts",
    "financial product and marketing subject"
  ],
  "checkability": "context_required",
  "coverage_group": "endorsement_and_regulatory_claims",
  "interpretation_note": "This card covers regulatory guarantee/filing claims only. It does not determine whether a public-figure endorsement complies with advertising law.",
  "verified": true,
  "verification_status": "reviewed_source_mapping",
  "ruleset_id": "official-v3-2026-10-12",
  "document_status": "effective",
  "valid_from": "2026-10-11",
  "valid_to": null,
  "supporting_article_ids": [
    "insurance_sales_behavior_order_2023_02::art_002",
    "insurance_sales_behavior_order_2023_02::art_005",
    "insurance_sales_behavior_order_2023_02::art_048",
    "financial_network_marketing_order_2026_09::art_002",
    "financial_network_marketing_order_2026_09::art_003",
    "financial_network_marketing_order_2026_09::art_036",
    "financial_network_marketing_order_2026_09::art_037",
    "internet_insurance_supervision_order_2020_13::art_002",
    "internet_insurance_supervision_order_2020_13::art_005",
    "internet_insurance_supervision_order_2020_13::art_044",
    "internet_insurance_supervision_order_2020_13::art_050",
    "internet_insurance_supervision_order_2020_13::art_078"
  ],
  "source_types": ["local_provided_effective_regulation"],
  "reviewer_type": "implementation_agent"
}
```

### 1.2 它绑定的直接条文原文

> **保险销售行为管理办法 第十七条**：保险公司、保险中介机构应当建立保险销售宣传管理制度，确保保险销售宣传符合下列要求：…（五）**不得利用监管机构对保险产品的审核或者备案程序，不得使用监管机构为该保险产品提供保证等引人误解的不当表述**；…

> **金融网络营销办法 第十条**：（五）利用金融管理部门、行业自律组织对金融产品的审核或备案程序，误导金融消费者和投资者认为金融管理部门、行业自律组织对该金融产品提供保证；

> **互联网保险监管办法 第十五条**：（五）…不得误导性解读监管政策，不得使用或变相使用监管机构及其工作人员的名义或形象进行商业宣传。

对比可见：**卡不是原文的摘要，而是原文的"可判定化"改写**——它补上了原文没有的触发条件、例外和所需事实。

### 1.3 字段分组与作用

| 字段组 | 字段 | 作用 |
|---|---|---|
| 身份 | `rule_id`、`category`、`coverage_group` | 规则叫什么、归到哪个违规大类 |
| 法源 | `article_ids`（直接依据）、`supporting_article_ids`（辅助）、`document_status`、`valid_from/to` | 绑到哪几条原文、何时有效 |
| 判定 | `trigger_conditions`、`prohibited_or_required_behavior`、`exceptions`、`required_facts`、`checkability` | 什么情况触发、什么算违规、什么算例外、还缺哪些事实 |
| 范围 | `subject_scope`、`channel_scope`、`product_scope` | 对谁、在哪个渠道、什么产品适用 |
| 溯源 | `verified`、`verification_status`、`reviewer_type` | 谁核对的、核到什么程度 |

### 1.4 哪些字段被机器强校验

这些字段不是"写着好看"，而是有程序门禁：

- `trigger_conditions` 被编号为 `c1/c2/...` 注入 prompt（`condition_bindings`），模型返回的 `condition_results` **必须逐条覆盖、不能多也不能少**，否则 `workflow.py` 直接抛 `Condition coverage mismatch`。
- `article_ids` 构成引用白名单：模型引用了非直接条文，报 `Citation is not a direct rule article`。
- `evidence` 必须**真实出现在材料中**，否则报 `Evidence does not occur in the specified source`（防编造证据）。
- `exceptions` 与 `interpretation_note` 是给模型的"别误判"约束。例如 `public_figure_endorsement_external_review` 的 `checkability` 为 `external_verification`，卡内明写「本条只要求符合广告代言规定，而本语料不含那些细则，故只识别问题并转外部法律复核，**不得单凭本条判违规**」——防止模型拿半截法条硬下违法结论。

### 1.5 实测分布

| 每条规则引用的直接条文数 | 规则数 |
|---|---|
| 1 条 | 18 |
| 2 条 | 10 |
| 3 条 | 8 |
| 4–8 条 | 10 |
| **合计** | **46** |

溯源字段实测：`reviewer_type: implementation_agent`（46/46）、`verification_status: reviewed_source_mapping`（46/46）。即**全部由实施 agent 核对，不是法律专家认证**；`manifest.json` 中 `production_legal_certification: false`。

---

## 二、为什么不直接用"法律条文切分后的向量"

六层理由，前两层是决定性的。

### 2.1 向量只能「找得到」，不能「判得动」

检索的产物是一段法条文本。要判违规，模型必须知道：这条法对**谁**适用、在**哪个渠道**适用、**什么事实**才触发、**什么情况**是例外、**缺哪些事实**时必须判"未决"而非"合规"。

这些信息**在法条原文里根本不存在**。原文只说"不得利用审核或备案程序"，它不会告诉你"中性的审批事实陈述不算违规"。向量检索出来的原文是**证据材料**，不是**判定规则**；`trigger_conditions` / `exceptions` / `required_facts` 才是把法律语言翻译成可判定条件的那一层，只能人工/agent 逐条建立。

### 2.2 靠相似度挑规则 = 漏检，而漏检是不可接受的失败模式

项目明确设计为：**46 条规则全部参与判定，不因检索结果减少**（见 `docs/project-introduction.md`）。RAG 只决定"哪些法条原文进 prompt"，不决定"哪些规则被检查"。

若直接用向量筛法条当作规则集，则材料里没有字面/语义线索的规则会被静默跳过——审核工具报"合规"而实际没查，这比报错严重得多。

### 2.3 条文与规则是 N:M，不是 1:1

实测：引用 1 条原文的规则 18 张、2 条 10 张、3 条 8 张、4–8 条 10 张。同一条《互联网保险监管办法》第十五条同时支撑 `marketing_truthful_and_not_misleading`、`no_regulatory_guarantee_or_filing_endorsement` 等多张卡，但**每张卡只取该条的不同款项**。

向量按"条"切分，切不出"第十五条第五项 vs 第四项"这种款项级归属，也没有"这一项属于哪条规则"的映射。

### 2.4 重复条文会被反复传输和反复计分

一张卡挂多条原文、一条原文又被多张卡共享，直接按向量块拼 prompt 会让同一段法条在多个批次里重复出现。

因此 `src/insurance_audit/retrieval.py` 的 `batches()` 按"共享直接条文"做并查集聚类：共享法条在**同一次调用里只传一次**，再按 8,000 字符/条文预算打包。这正是 46 条规则 → 25 次调用（而非 46 次）的原因。该结构只有靠 `article_ids` 映射才能构建。

### 2.5 引用可校验、可回溯

`docs/SPEC.md` 定死："规则卡是解释，正式引用只能来自条文原文"。程序强制检查模型给出的每条引用都在 `article_ids` 白名单内，且 `evidence` 必须真实出现在材料中。

如果上下文只是一堆向量块，就没有"这条引用属于哪条规则、是否被允许"的判定基准。

### 2.6 版本与效力可绑定

卡内含 `ruleset_id`、`document_status`、`valid_from/to`。检索先按"本次固定规则集 + 审核日期"过滤，再判适用性；跨文件冲突需记录优先级或人工复核，**不能靠检索分数决定适用哪部法**。向量相似度是语义相近度，不是法律效力位阶。

### 2.7 一句话总结

> **向量负责「召回」（哪段法条可能相关），规则卡负责「判定」（什么情况违规、什么情况例外、缺什么事实）。**
>
> 两者不是替代关系：向量解决"359 条塞不进上下文"，规则卡解决"判得动、判得全、判得住、可追溯"。用向量替代规则卡，等于把"全覆盖的合规检查"降级成"碰运气的相似度搜索"。

---

## 三、补充：RAG 并未缺席

RAG 在本项目中是 hybrid 链路：BM25 + `text-embedding-v4`（1024 维）+ RRF 融合，索引绑定 manifest 哈希，规则集一变旧索引自动失效。

它服务的对象是**"进 prompt 的原文"**，而不是**"被检查的规则集"**——这是理解整套设计的关键区分。详见 `docs/rag-operations.md` 与 `docs/decisions.md`。
