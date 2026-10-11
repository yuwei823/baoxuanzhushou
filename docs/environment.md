# 环境与输入核对

检查日期：2026-10-11；任务：P0-01。

- Windows / PowerShell；Python 3.11.9 可用，另安装 3.12；选择 3.11。
- Python 3.11 pip 26.1.2；Git 2.55.0.windows.2。
- P0-02 建立项目 venv 后，pip-tools 7.6.2 已创建 Windows x64 / Python 3.11 的 46 包版本及分发文件 SHA-256 锁。无网络本地 wheel 缓存可完成全新 venv 安装。
- 未找到 PATH 中的 uv、soffice、pdftotext；默认 LibreOffice 安装路径不存在。
- WPS Office 12.0 安装于本机；使用系统 Python 的 pywin32 和官方文档 `kwps.application` 自动化 ProgID，已成功只读抽取两份 DOC。转换版本、哈希及计数见 data/extracted/doc-extraction.json。
- PDF 提取／预览工具：pypdf 6.20.0、PyMuPDF 1.28.2。
- 当前进程和用户级 DASHSCOPE_API_KEY 均未配置；项目无 .env。未读取或输出密钥值。
- 已读取 Requirement.md 和 SPEC.md。未发现 D:\AGENTS.md 或项目 AGENTS.md。

## 附件清单

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| 中华人民共和国保险法.doc | 80896 | 083A55D495A75A6335C02AF3C90C139F3FD8F3DB14548967179A397DAD86527C |
| 互联网保险业务监管办法.doc | 112128 | 70222AC5D0AB7819BFDC7EABBAF6C8EEB8414B2D038E16B99CA8DE09A90EFD9A |
| 保险销售行为管理办法.doc | 56832 | E929839E427ED300853ED7417BDC7C1688C955E62DF47CFE3F27F9231681B52A |
| 国务院办公厅关于加强金融消费者权益保护工作的指导意见.doc | 29184 | CEE82068A6578315212B0391F7E96F8A3FA7ECD6E86DC938831CBB46E80D0B7F |
| 金融产品网络营销管理办法.pdf | 206424 | 7BC3F991244609AF7A171C302282AB03BDC8D6540A86BD20CC5CBEB5B9E8F001 |

用户已确定以“法律法规”目录本地文件为依据，建立候选快照 `official-v1-2026-10-11`。网络营销办法 PDF 已是核心来源；《中华人民共和国保险法.doc》列为本地现行法补充来源，但因本轮 WPS COM 返回拒绝访问，尚未可靠抽取和核验，规则集发布前必须完成。线上《保险法（修订草案征求意见稿）》不替代本地现行版本，也不进入本次裁决规则集。

## 检查命令

`py -0p`、`py -3.11 --version`、`py -3.11 -m pip --version`、`Get-Command`、`Get-FileHash -Algorithm SHA256`、Word COM 注册项及 Python 模块存在性检查。

P0-01 的清点任务完成；清点完成不等于原文解析、规则版本或模型调用已验收。
