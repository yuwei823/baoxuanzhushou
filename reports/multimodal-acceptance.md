# P2 工程验收进展（2026-10-12）

状态：**G2 已通过**。上传、多图提取、页面验证与 Unicode/HTML 压力案例复验均完成；压力案例由 partial 转为 completed/non_compliant。这是合成开发案例工程验收，不是效果评估。

## 已实现和验证

- 上传成功、非法格式失败和客户端断连均关闭 multipart 临时文件；新增断连回归确证模型任务取消。断连时服务返回 499/null，避免中间件 No response returned；正常技术故障仍使用既定错误码。
- 图片来源绑定提交时独立 Blob URL。编辑、删除或重排输入不改变已展示结果；结果替换时释放旧 URL，取消或异常时释放未使用的提交快照。
- 原图在提取记录内可见；删除违规证据图片的内联样式，遵守 CSP；演示素材异步加载用 generation 防止旧请求覆盖新选择。
- 真实双图案例 completed/compliant：见 vision-smoke.md 和 p2-real-multi-browser.json。
- 真实 Unicode/HTML 输入案例（首轮，历史证据）：页面高亮“由监管部门担保收益”正确，HTML 字符串按文本展示，没有生成 img[onerror]。结果 partial/non_compliant，3 项有效违规，78.1 秒、8 次尝试。修复后复验为 completed/non_compliant、4 违规、0 错误，见 p2-stress-reverify.json 与 p2-stress-reverify-browser.png。
- 模拟故障页面通过 partial、failed、needs_review、取消、失败输入保留验证；模拟与真实模式显著区分。复现入口 scripts/serve_p2_fixture.py（127.0.0.1:8001，仅 MockProvider，不调用外部模型）。
- 窄屏检查 document scrollWidth 与 clientWidth 均为 375，无横向溢出。截图 p2-mobile-browser.png；多图与 Unicode 截图另存。控制台检查未发现脚本/CSP 错误（模拟 504 HTTP 提示属于预期）。
- pyproject.toml 显式包含 static/*，本地 wheel 构建通过并检查 HTML/JS/CSS/PNG 都已打包：package-check/verification.json。
- pytest 全量 91 passed in 13.91s；取消/矛盾两项在格式修正后再次通过；Ruff 全库通过。

## 未通过与范围（已解决部分见下）

Unicode 压力案例此前在 disclose_material_policy_terms_and_restrictions 规则上两次返回非本规则直接条文，触发 Citation is not a direct rule article。没有放宽引用校验，也没有改成合规。已修复：judge payload 增加逐规则 allowed_citations 与条文 direct_for_rule_ids 标注，修复提示携带各规则可引用条文（条号+开头原文）。复验证据：reports/p2-stress-reverify.json（API，completed/non_compliant、4 违规、0 错误、8 次尝试，首轮 attempt=1 引用校验错误被修复提示纠正）与 reports/p2-stress-reverify-browser.png（浏览器同一输入重放，“发现违规”、HTML 字符串按文本显示）。G1 科普改写过度复核也已修复并通过（reports/g1-acceptance-2026-10-12.md）。

当前案例是合成开发验收，未开展 P3 正式效果评估。保险法抽取、独立案例/FAQ 知识库仍未完成。完整日志仅保留脱敏运行元数据；此处案例文本和截图是主动保存的合成测试证据。

补充：真实教育反例浏览器验收 completed/compliant，84.2 秒；下载报告 p2-real-education-browser.json。桌面 1280px 双栏（494/659px）无横向溢出，截图 p2-education-browser.png；viewport 已恢复默认。
