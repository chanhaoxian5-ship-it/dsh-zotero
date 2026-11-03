# 导入去重与异常恢复

## 去重边界

分类（collection）是同一文库中已有条目的组织方式，不是独立文献库。安全导入检查整个个人文库，不能以“当前分类没有”作为重新创建条目的理由。个人文库与各群组文库仍是不同 library。

- DOI 做大小写、doi: 前缀和 DOI URL 规范化后精确比对；不随意剥掉 DOI 尾部标点，避免改写合法标识符。
- 同 DOI 已有条目返回 existing 和原 key；已有多个副本时全部列出，不自动选主条目。
- 仅同标题、DOI 缺失或冲突时为 ambiguous，暂停整个导入批次。预印本和正式版不凭同标题自动合并。
- 输入批次中的同 DOI 重复项只保留第一次。同标题而不同 DOI 的输入仍暂停核查。
- 扫描显式分页，并核对 Total-Results、唯一 key 和 Last-Modified-Version；读失败、漏页或文库变化时不写入。

目前仅对个人文库提供安全导入。只读搜索、inventory 和 duplicates 支持 `--library groups/数字ID`；group ID 不是 Connector 的内部 libraryID。

## 结果与状态

| 状态 | 含义与下一步 |
| --- | --- |
| existing | 本次未创建；复用返回的 key。分类归属未自动改变。 |
| imported | 已发送一次，并回读确认全部待导入记录和新 key。 |
| recovered | 响应丢失/异常，但已回读确认全部新条目；不再发送。 |
| blocked / ambiguous-identity | 元数据存在身份歧义；调整证据或选择已有条目。 |
| blocked / outcome unknown | 不能判断是否全部写入；运行 import-status，不重发。 |
| verified-target-changed | 已确认写入，但检测到 UI 目标变化；核对分类，不重导。 |

导入不是服务器事务：批次可能部分成功。pending 记录在 POST 前原子写入，保留会话 ID、目标、身份字段和导入前 keys。后续调用在同一地址的进程间文件锁下读取记录；进程退出会释放锁，但不会清除 pending。只有全部身份都能匹配唯一的新 key，才自动恢复为 verified。

记录默认位于 `~/.dsh/state/dsh-zotero`，随 `DSH_HOME` 移动；`ZOTERO_DSH_STATE_DIR` 可指定稳定目录。升级插件时保留该目录，不要为重试换目录。内容只保存在本机，不随插件发布；其中有标题、DOI 和条目 key，应按个人文献数据保存。

## 无法自动恢复时

运行 `import-status`，按返回的身份字段在 Zotero 检查实际条目。如果只有部分导入完成，不要重发整批。保留记录，核清 Zotero 已经结束处理、哪些条目已创建以及哪些尚未创建，再决定后续操作。必要时由操作人员备份并归档旧日志后建立新的待导入清单；模型不能把清除日志当作自动重试手段。

锁与记录只协调使用同一状态目录和同一服务地址的本插件进程。不能阻止原生 UI、其他插件或其他机器同时导入，也不能把 Connector 当前 UI 目标变成服务器端固定目标。因此仍需避免在导入中切换分类，并在需要清理历史副本时使用 Zotero 的原生合并。

## 元数据解析限制

RIS 要求完整的 TY/ER 边界，支持 TI/T1、DO 和续行；冲突标题/重复身份字段会阻止导入。BibTeX 支持字面量值、嵌套花括号和引号；宏、拼接、指令和标题内 TeX 命令均明确拒绝，以免预检与 Zotero 实际导入解析出不同身份。遇到这些情况可导出为 RIS，而不是绕过去重层。

官方依据：[重复条目与原生合并](https://www.zotero.org/support/duplicate_detection)、[Connector 导入实现](https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/server/server_connector.js)。
