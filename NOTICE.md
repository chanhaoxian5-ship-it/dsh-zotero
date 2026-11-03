# 来源与改动

上游：OpenAI Zotero plugin 0.1.2，公开源码位于：
https://github.com/openai/plugins/tree/cd0fccd4ed62dded584c16246685b232d7bfe7f6/plugins/zotero

原插件 `.codex-plugin/plugin.json` 声明作者 OpenAI、许可证 MIT。仓库根目录的 LICENSE 保留上游归属，并覆盖本项目的适配代码。

`upstream/codex-zotero-0.1.2/` 保存已安装原插件的完整文件（排除 Python 生成缓存）。该副本在移植时与本机来源逐文件核对一致。原始 `zotero.py` 也与上述公开提交核对 Git blob SHA-1：

`0b12836d8133209d8f20d25bd1eba8904fd2833d`

活动目录 `skills/zotero/scripts/zotero.py` 原样保留，归属原作者 OpenAI。原始图片资源和其他原始文档的归属保持不变；引用这些资源不表示获得商标授权或官方背书。

适配新增 DSH bundle 清单、Cordis 技能注册入口和 Node/Python 启动器；0.2.0 新增 zotero_dsh.py，在上游脚本之外实现搜索、导入去重、pending 记录与回读检查。重写活动技能说明以适配 Windows、DSH 和完整阅读工作流，调整活动目录的技能调用名。活动 API 路由说明按本适配层能力更新。原始说明与清单仍在 upstream 中。

此包为社区适配版本，并非 OpenAI、DeepSeek 或 Zotero 的官方发布。
