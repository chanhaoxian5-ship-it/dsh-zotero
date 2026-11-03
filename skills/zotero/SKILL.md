---
name: zotero
description: 使用 Zotero Desktop 搜索本地文库、读取论文附件索引全文、导入 RIS/BibTeX、导出参考文献和插入引用。用户提及 Zotero、文库、添加论文、引用或读取 Zotero 论文时使用。
---

# Zotero for DSH

通过本地 HTTP API 和 Connector 操作 Zotero。运行环境为 Windows PowerShell；以下启动器路径由 DSH 技能提供器自动填入。如果直接从磁盘读取本文件，应根据本文件位置找到 scripts/run-zotero.mjs，不要执行未替换的占位符。

## 连接与搜索

```powershell
node '{{ZOTERO_RUNNER_PS}}' status --json
node '{{ZOTERO_RUNNER_PS}}' search '标题关键词' --json
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

用户明确要求添加即已授权导入，无须重复确认。先按标题搜索去重并核对 DOI（原脚本默认搜索不保证命中 DOI，DOI 搜索为空不能判定条目不存在），获取并核对可信来源的 RIS 或 BibTeX，确认条目版本。脚本不会自动解析 DOI 或下载正文。

```powershell
node '{{ZOTERO_RUNNER_PS}}' selected-target --json
node '{{ZOTERO_RUNNER_PS}}' import-ris --file 'D:/论文工作区/paper.ris' --yes
node '{{ZOTERO_RUNNER_PS}}' import-bibtex --file 'D:/论文工作区/paper.bib' --yes
```

导入目标由 Zotero 当前选中的文库/分类决定。selected-target 可能包含大量标签，只保留目标相关字段供判断。导入后搜索核对条目；请求超时先查是否已添加，避免盲目重复导入。不要直接写 Zotero SQLite 数据库。

## 导出与引用

```powershell
node '{{ZOTERO_RUNNER_PS}}' export-bibtex --item-key ITEMKEY --out 'D:/论文工作区/references.bib'
node '{{ZOTERO_RUNNER_PS}}' cite --item-key ITEMKEY --markdown 'D:/论文工作区/draft.md' --bib 'D:/论文工作区/references.bib' --marker '<cite>'
node '{{ZOTERO_RUNNER_PS}}' --help
```

修改用户文稿须在请求范围内；Zotero item key 不等于 BibTeX citation key。完整命令与选项以 --help 为准，API 路由见 references/local-api-routes.md。不同 Zotero 版本能力有差异，以实际响应为准。

Python 脚本原样来自 OpenAI Zotero 0.1.2，原插件保存在 upstream。连接在本机发生，但送入 DSH 模型的正文仍会进入所选模型服务。
