# 文本 RAG 运行与边界

2026-10-11。图片识别与新案例收集不阻塞当前文本检索。新增外部资料尚未导入，本次索引完全来自已发布的本地法规快照。

## 已实现流程

用户文本按原始位置分段 → text-embedding-v4 查询向量 + 中文 BM25 → 各路 Top 8 → RRF(k=60) 融合取每段 Top 8 → 命中规则优先排列 → 召回整条原文与规则直接/支持原文去重 → 模型逐规则判断 → 引用/条件/证据校验 → 确定性聚合。

额外召回原文实际加入每批模型消息，meta.context_trace 记录提供的 article_ids；meta.retrieval_trace 记录各段位置及两路排名。原文携带 retrieved/mandatory/supporting 角色。检索命中不允许模型新增未核对规则；最终引用仍限于该规则合法 article_ids，并由知识库回填。

当前仍检查全部 34 张规则卡，不凭相似度排除规则。这样保留覆盖，但上下文会重复，暂未证明比旧流程更快。以后可以优化分批分配，但不得牺牲覆盖或切掉例外。

## 配置与索引

```dotenv
RETRIEVAL_MODE=hybrid
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
BAILIAN_TEXT_ENABLE_THINKING=false
```

```powershell
.\.venv\Scripts\python.exe -m insurance_audit.cli build-index
.\.venv\Scripts\python.exe -m insurance_audit.cli audit-text '保险知识科普：不要把分红演示当成保证收益。'
```

首次 build-index 有 API 用量；同一版本再次执行校验后复用。首批实测 172 条、1024 维、18 次调用、18,067 token，见 reports/vector-index-build.json。不估算费用。

索引为 data/indexes/ 下单个 JSON 文件，包含 manifest、归一化向量及向量哈希，文件名是 manifest 哈希。manifest 绑定 ruleset_hash、模型、维度、切片版本、article_ids、检索文本哈希。临时文件完整写入后原子改名；不会修改已发布法规快照。

目前使用完整条文（最长正文 787 字）加标题/章节构建索引，无额外数据库依赖。构建器拒绝超过 2000 字符的检索条目；这是本项目保守限制，未来长法规应增加分款与父条映射，不能截断。查询段长 512 字符，每段都参与，不忽略长文尾部。

新法规完成 P0 审阅发布后，显式选择新 RULESET_ID 并 build-index，再重启服务。P0 watcher 尚未自动触发付费向量构建。索引不匹配、缺失或损坏时 hybrid 启动就绪检查失败；不会借用旧版本。Embedding 模型升级也需重新构建并评估。

## 预算与失败

在线向量和判定共享并发 2、150 秒总预算、最多 16 次尝试。向量每批最多 10 条，鉴权不重试，可恢复错误按 Retry-After 与退避重试。离线构建单独采用 900 秒/60 次预算。

查询向量失败时未执行的规则进入 failed，整体返回技术失败；不自动退为 BM25。显式 RETRIEVAL_MODE=bm25 可运行文字检索基线，结果会标明模式；不能计入 hybrid 验收。

不会持久化用户查询向量或原始输入作为缓存。合成开发案例报告会保留完整结果用于排错；不是生产日志策略或正式效果评估。

## 当前质量限制

现有校验诊断记录错误类别与已验证 rule_id，不记录失败模型原文、输入或密钥。Prompt audit-v1.4-rag 采用局部条件 ID 映射原文，明确证据 ID 范围、原文标点与合法引用；修复仍最多一次。最新实测见 reports/rag-acceptance.md。

教育反例已完成一次真实审核，无技术错误、无违规，但因外部资质/平台适用性过度保守而转为 needs_review。这不是预期 compliant 的三态验收通过。应继续完善适用性判断，并在独立开发集/测试集衡量误报、漏报及复核率。新案例库与官方解读将单独标注来源和用途，不能替换法规裁决依据。
