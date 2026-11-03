# DSH Zotero

[![CI](https://github.com/chanhaoxian5-ship-it/dsh-zotero/actions/workflows/ci.yml/badge.svg)](https://github.com/chanhaoxian5-ship-it/dsh-zotero/actions/workflows/ci.yml)

在 DeepSeek Harness 中使用本机 Zotero：搜索文库、读取附件索引全文、导入 RIS/BibTeX、导出参考文献和插入引用。基于 OpenAI Zotero plugin 0.1.2 适配，完整保留原插件及原始 Python 脚本。

## 环境要求

- DSH `>=0.2.1-rc.5 <0.3.0`，profile 中提供 `skills` 服务。
- Node.js >=22、Python >=3.10。
- Zotero Desktop 正在运行，本地 API 已启用；默认地址 `http://127.0.0.1:23119`。

实际验证环境为 Windows、DSH 0.2.1-rc.5、Zotero 10.0.6。适配层通过 Windows/Linux CI；macOS 与实际模型对话调用尚未验收。

## 安装发布版本

在终端执行（只在你准备好安装时运行）：

```powershell
dsh plugin --profile desktop add 'github:chanhaoxian5-ship-it/dsh-zotero#v0.1.0'
```

DSH 根据本包的 `dsh.bundle` 声明自动维护 profile 的依赖和 bundles 列表。无需手工编辑 profile，也无需把 skill 复制到全局目录。插件直接分发可运行的 `.mjs` 和 `.py` 文件，没有安装构建脚本。

先查看组合配置：

```powershell
dsh --profile desktop --dump-config
```

确认其中出现 `dsh-zotero` 后，重新启动 DSH，并在新对话中输入：

> 用 zotero 技能搜索我的文库中关于 retron 的论文。

若 `dsh` 不在 PATH，可使用桌面安装目录的 `resources/runtime/cli/bin/dsh.cmd`。如果当前 profile 有其他插件的版本兼容性错误，须先处理对应插件；这类错误与 Zotero 本地 API 是否可连接是两项检查。

也可以从 [Releases](https://github.com/chanhaoxian5-ship-it/dsh-zotero/releases) 下载 `.tgz`，然后执行 `dsh plugin --profile desktop add 'D:/下载目录/dsh-zotero-0.1.0.tgz'`。如需不可变来源，用发布提交的完整 SHA 替代 `#v0.1.0`。本项目目前未发布到 npm。

卸载：

```powershell
dsh plugin --profile desktop remove dsh-zotero
```

## 使用示例

- “用 zotero 搜索 cross-species retron，列出标题、年份和条目 key。”
- “读取这篇论文的 PDF 正文，先检查附件和索引覆盖情况。”
- “把这条已核对的 RIS 文献加入 Zotero 当前分类，先检查是否重复。”
- “把选中的文献导出成 references.bib。”

原脚本默认搜索不能保证命中 DOI；去重应先按标题搜索再核对 DOI。全文接口提供 Zotero 的文本索引，图表、扫描件和页面布局仍需 PDF 阅读工具。插件不内置 DOI 解析、全文或补充材料下载器。正式版与预印本需分别核对。

## 组成

| 文件 | 作用 |
| --- | --- |
| `index.mjs` | DSH 原生技能提供器，注册 `zotero` 并填入实际绝对路径 |
| `cordis.patch.yml` | DSH bundle 配置层 |
| `skills/zotero/SKILL.md` | DSH 使用流程 |
| `skills/zotero/scripts/run-zotero.mjs` | 选择 Python、设置 UTF-8、透传参数 |
| `skills/zotero/scripts/zotero.py` | 原始 Zotero API / Connector 脚本 |
| `upstream/codex-zotero-0.1.2/` | 原 Codex 插件完整副本，排除生成缓存 |

没有额外 MCP 服务或云端 Zotero Key。启动器优先使用 `ZOTERO_PYTHON` 指定的解释器，否则选择 DSH 自带 Python，再尝试 PATH 上的 Python；指定路径不要附加参数。`ZOTERO_LOCAL_BASE_URL` 可修改本地 API 地址。

读取和导入通过本机 HTTP 完成；送入 DSH 模型的文本仍由所选模型服务处理。导入会写入 Zotero 当前选中的文库/分类，操作前应检查目标。

## 开发与验证

```powershell
npm test
node skills/zotero/scripts/run-zotero.mjs --help
npm pack --dry-run
```

这些检查不需要运行 Zotero，也不会安装插件或调用模型。连接检查需要启动 Zotero：

```powershell
node skills/zotero/scripts/run-zotero.mjs status --json
node skills/zotero/scripts/run-zotero.mjs search 'cross-species retron' --json
```

可选的真实 DSH 技能注册检查：在已安装 DSH 的 Electron Node 环境下运行 `tests/runtime-check.cjs`，用 `DSH_RUNTIME_ROOT` 指向含 DSH `node_modules` 的目录，例如 `resources/app.asar/dsh`。它只加载隔离的技能注册表，不修改 profile，也不调用模型。

## 开源与发布

本仓库按 DSH 官方 bundle 格式分发，可从 GitHub、发布 tarball 或 npm 安装；上架“发现”是另外一项可选操作，使用独立 JSON 索引源。详细依据和发布步骤见 [发布流程](docs/publishing.md)。

许可证及上游出处见 [LICENSE](LICENSE) 和 [NOTICE.md](NOTICE.md)。这是社区适配版本。
