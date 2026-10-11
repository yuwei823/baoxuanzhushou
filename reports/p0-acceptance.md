# P0 验收记录

日期：2026-10-11。结论：P0-01～05 与 G0 已完成，范围为用户提供的三份核心正式法规。保险法抽取按用户要求暂缓，作为扩展任务保留；不宣称本快照覆盖保险法。

| 任务 | 结果与证据 |
|---|---|
| P0-01 | 环境及五份本地来源清点，哈希匹配；docs/environment.md、集中 extraction-registry.json |
| P0-02 | Python 3.11 哈希锁定依赖；独立 .venv-verify 可导入新模块且 pip check 无损坏依赖 |
| P0-03 | 3 份本地核心来源只读抽取；销售办法 50 条、网络营销办法 39 条、互联网保险办法 83 条 |
| P0-04 | 172 条全文、适用范围和例外核对；34 张规则卡；172 条范围台账；review.json 将来源、原文、规则语义和审阅身份绑定哈希 |
| P0-05 | ingest、validate-corpus、publish-corpus 已实现；18 项异常/不可变性测试通过；严格校验零错误；快照显式发布 |

## 实际命令与结果

```powershell
.venv\Scripts\python.exe -m insurance_audit.cli ingest --ruleset official-v1-2026-10-11
.venv\Scripts\python.exe scripts\build_rule_card_candidates.py
.venv\Scripts\python.exe scripts\record_core_review.py
.venv\Scripts\python.exe -m insurance_audit.cli validate-corpus --ruleset official-v1-2026-10-11 --report reports\corpus-validation.json
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m insurance_audit.cli publish-corpus --ruleset official-v1-2026-10-11
.venv-verify\Scripts\python.exe -m insurance_audit.cli validate-corpus --ruleset official-v1-2026-10-11
.venv-verify\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m ruff check src scripts tests
```

结果：18 passed；ruff 全通过；两个虚拟环境的严格校验均为 structural_valid=true、release_ready=true，完整性错误/审阅门禁均为 0。独立环境 pip check 为 No broken requirements found。发布后集中登记为 published，核心原文均 agent_reviewed，所有 5 份登记来源哈希匹配。

上述 ingest 和核心规则生成是本次候选构建历史命令。快照发布后禁止重跑覆盖；复核使用 validate-corpus。新增法规需要新 ruleset_id、独立显式来源 manifest、原文与规则审阅及回归，不自动启用目录新文件。

快照不仅记录 metadata，还保存 source-files 原文档字节副本与 extracted-files 原始抽取 JSON。整条检索块保留父条各款和例外。修复了旧候选中的章节标题混入上一条、网络营销办法末条混入网页导航问题；原始抽取文件未改动。

## 核对边界与后续

全文及规则映射由实施 agent 核对，reviewer_type=implementation_agent、is_legal_expert=false，不是法律专家认证；官方资料仅辅助版本与抽样检查，裁决原文来自用户本地文件。引用完整性不能证明所有未来案例的法律适用正确，P1/P3 仍需条件、证据及效果评估。

保险法仍为 extraction_deferred_by_user、未抽取；金融消费者保护指导意见为 reference_only。当前核心范围不是全部保险法规覆盖。P1 下一任务为 Schema/状态矩阵；真实百炼调用、审核 API、页面和效果评估尚未实现，未作为本轮验收成果。
