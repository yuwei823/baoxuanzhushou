# P0 pipeline 验收

日期：2026-10-11。

- 已实现：目录轮询、稳定窗口、哈希去重、原件副本、格式抽取、条号切分、候选包与审阅模板、异常隔离、失败重试、审阅封存后自动校验发布、集中登记、单实例后台进程和 Windows 登录启动任务。
- 校验：33 项 pytest 通过，包含子进程目录监视实测、真实本地 PDF 39 条抽取、DOCX/TXT、幂等、修改新版本、源删除保留快照、失败重试、保险法暂缓、审阅续跑、批准后改动及未来生效阻止发布。ruff check/format 通过。
- 当前目录扫描：5 份本地文件；3 份已登记核心来源跳过；保险法保持 extraction_deferred_by_user；指导意见保持 reference_only；无虚构待审新法规、无真实模型调用。
- 集中记录升级到 schema_version 2.0：documents、snapshots 与 pipeline 在同一 extraction-registry.json 关联，原有失败尝试和工具记录保留。已发布 official-v1-2026-10-11 严格校验仍通过。
- 持续运行：InsuranceAudit-P0-FolderWatch 注册为当前用户登录触发，隐藏执行项目 pythonw；每 5 秒扫描，实例锁避免重复执行。运行证据以 data/runtime/pipeline-health.json 和任务实际状态为准。

法律审阅不能由条号/哈希替代。新文件自动到 needs_review；完成全文、效力、规则及冲突审阅并 seal 后，后台自动续跑发布。原文版本依据仍是用户的本地文件。

## 清理

已删除 6 个被包内流水线替代的旧脚本和 2 份过期候选报告。保留原始法规、需求/规格、当前 .venv、依赖锁、原始抽取证据、已发布快照与 P0 验收报告；历史文档中的旧命令仅作实施记录。

清单见 cleanup-manifest.json。递归删除临时文件/缓存/第二套虚拟环境的两次命令均被自动安全策略拦截（返回 blocked by policy，无更具体原因），未执行删除；因此这些目录仍存在。已提供固定白名单的 scripts/cleanup_p0.ps1 供用户执行，支持 -WhatIf 预览。未通过其他工具绕过该拦截。
