---
name: zotero
description: 使用 Zotero Desktop 搜索本地文库、读取论文附件索引全文、导入 RIS/BibTeX、导出参考文献和插入引用。用户提及 Zotero、文库、添加论文、引用或读取 Zotero 论文时使用。
---

# Zotero for DSH

通过本地 HTTP API 和 Connector 操作 Zotero。运行环境为 Windows PowerShell；以下启动器路径由 DSH 技能提供器自动填入。如果直接从磁盘读取本文件，应根据本文件位置找到 scripts/run-zotero.mjs，不要执行未替换的占位符。

## 连接与搜索

```powershell
node '{{ZOTERO_RUNNER_PS}}' status --json
node '{{ZOTERO_RUNNER_PS}}' search '标题关键词或 DOI/DOI URL' --json
node '{{ZOTERO_RUNNER_PS}}' collections --json
node '{{ZOTERO_RUNNER_PS}}' tags --json
```

Zotero 必须运行。本地 API 默认 http://127.0.0.1:23119，可用 ZOTERO_LOCAL_BASE_URL 修改。单次请求失败先报告具体错误并重试检查，不要直接关闭 Zotero。启用 API 可使用 enable；需要重启时说明会中断当前 Zotero 操作，按用户已有授权处理。

## 阅读正文、附件与图表

```powershell
node '{{ZOTERO_RUNNER_PS}}' children ITEMKEY --json
node '{{ZOTERO_RUNNER_PS}}' fulltext ATTACHMENTKEY --out 'D:/论文工作区/正文.txt'
node '{{ZOTERO_RUNNER_PS}}' file-url ATTACHMENTKEY
```

先确认标题、DOI 和版本，再查看附件。用户要求阅读论文已授权读取相关正文及附件。fulltext 读取 Zotero 索引，注意 indexedPages/totalPages 等覆盖信息；长文写入文件后分段阅读。只有元数据不等于读过正文。索引缺失或不完整时，根据 file-url 返回的本地 PDF 地址使用可用的 PDF 技能；图表、扫描件和页面布局也需要 PDF 工具。补充材料分别检查，不把预印本视为正式版。此插件不内置全文下载器，缺失附件须通过可用的合法获取工具另行获取并说明来源。

## 添加文献

用户明确要求添加即已授权导入，无须重复确认。获取并核对可信来源的 RIS 或 BibTeX，确认版本，再通过以下启动器预览并导入。启动器已接入 DSH 去重层：完整分页读取个人文库，规范化 DOI（支持 DOI URL 与大小写），跨分类检查。不要绕过启动器直接调用上游 zotero.py 来导入。

```powershell
node '{{ZOTERO_RUNNER_PS}}' selected-target --json
node '{{ZOTERO_RUNNER_PS}}' plan-import --format ris --file 'D:/论文工作区/paper.ris'
node '{{ZOTERO_RUNNER_PS}}' import-ris --file 'D:/论文工作区/paper.ris' --yes
node '{{ZOTERO_RUNNER_PS}}' import-bibtex --file 'D:/论文工作区/paper.bib' --yes
```

`plan-import` 只读：`existing` 表示同 DOI 已在文库，导入命令会跳过；`ambiguous` 表示同标题但身份/版本不确定，整个批次暂停；`duplicate-in-input` 表示输入内重复；只有 `new` 会发送。已有条目在其他分类中仍然算已有；返回 key 供复用，本命令不会自动变更已有条目的分类。

安全导入目前仅支持“我的文库”，不猜测群组库内部 ID 与 Web API group ID 的映射。导入目标为 Zotero 当前分类，两次检查目标是否改变；知道分类内部 ID 时可用 `--expect-collection-id 52`（根目录用 root）。导入过程中不要切换目标；若结果为 verified-target-changed，只核对归属，不重导。

导入前落盘 pending 记录，并对同一服务地址加并发锁；返回 HTTP 201 后也要回读 DOI/title 与新 key 才报成功。超时、进程中断或部分成功时，后续导入会被挡住。用下列命令核对，**不要改 session、删除记录或重新发包来绕过 pending**：

```powershell
node '{{ZOTERO_RUNNER_PS}}' import-status
node '{{ZOTERO_RUNNER_PS}}' duplicates
```

`import-status` 不发送导入请求；能回读全部条目时恢复为 verified，否则保留待核查状态。duplicates 是只读的精确 DOI/标题候选报告，不等于 Zotero 原生完整去重算法。不自动合并或删除已有条目，尤其是已被 Word 引用的条目；复用 key 或在 Zotero 内原生合并。批量 BibTeX 的宏、字符串拼接和标题内 TeX 命令不猜测解析，改用字面值 BibTeX 或 RIS。详见 [导入可靠性](references/import-reliability.md)。

## 导出与引用

```powershell
node '{{ZOTERO_RUNNER_PS}}' export-bibtex --item-key ITEMKEY --out 'D:/论文工作区/references.bib'
node '{{ZOTERO_RUNNER_PS}}' cite --item-key ITEMKEY --markdown 'D:/论文工作区/draft.md' --bib 'D:/论文工作区/references.bib' --marker '<cite>'
node '{{ZOTERO_RUNNER_PS}}' --help
```

修改用户文稿须在请求范围内；Zotero item key 不等于 BibTeX citation key。完整命令与选项以 --help 为准，API 路由见 references/local-api-routes.md。不同 Zotero 版本能力有差异，以实际响应为准。

上游 zotero.py 原样来自 OpenAI Zotero 0.1.2，原插件保存在 upstream。新增 zotero_dsh.py 承接搜索和导入检查。连接在本机发生，但送入 DSH 模型的正文仍会进入所选模型服务。
