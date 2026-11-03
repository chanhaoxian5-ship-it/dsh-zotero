# DSH 插件开源与发布流程

依据 DSH 官方文档，核对日期：2026-11-03。

## 1. 将插件作为独立 bundle 开源

仓库根目录放置 `package.json`、入口模块和 `cordis.patch.yml`。`package.json` 以 `dsh.bundle.patch` 声明配置层，以 `engines.dsh` 声明支持版本。patch 里的插件行按包名引用入口。

本项目直接分发 `.mjs` 和 `.py`，不需要 TypeScript 构建，也没有 `prepare` 或 `postinstall` 脚本。GitHub 安装能直接取得运行文件；不能假设包管理器会自动运行一个普通的 `build` 脚本。

官方依据：[打包与安装插件](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/develop/basic/publish.zh.md)。

## 2. 校验并标记版本

1. 在 Windows/Linux CI 中运行 `npm test`、启动器 `--help`、`npm pack --dry-run`。
2. 更新 `package.json` 和 `CHANGELOG.md`，保留上游来源、许可证和未验收范围。
3. 提交后建立与包版本一致的 `vX.Y.Z` tag。
4. 执行 `npm pack`，将 tarball 和 SHA-256 校验文件附到 GitHub Release。

普通 CI 不访问个人 Zotero 文库、不写入条目、不调用模型。真实 DSH 技能注册与本机连接检查单独执行并记录环境；跨平台 CI 通过不能代替真实平台验收。

## 3. 安装发布版本

```powershell
dsh plugin --profile desktop add 'github:chanhaoxian5-ship-it/dsh-zotero#v0.1.0'
dsh --profile desktop --dump-config
```

`dsh plugin add` 在 profile 内调用 pnpm；识别到 bundle 后维护依赖和有序的 bundles 列表。`remove dsh-zotero` 移除依赖和对应层。通常无需手工编辑 profile manifest。为了锁定不可变来源，可以用完整提交 SHA 替换 tag。

tarball 也受支持：`dsh plugin --profile desktop add './dsh-zotero-0.1.0.tgz'`。发布到 npm 后才可使用 `dsh plugin add dsh-zotero@版本`；本项目尚未发布 npm，不应把这个命令当作已可用的安装方式。

Git 依赖若需要 `prepare` 构建，pnpm 可能要求对该包配置 `allowBuilds`。本项目不需要安装构建；不应为了安装它而添加无关的全局构建豁免。

## 4. 可选：出现在“发现”页面

DSH 的实验性“自定义插件索引”读取静态 HTTPS JSON 文件。官方文档说明 DSH 不内置索引源；公开 GitHub 仓库和被某个索引收录是两件事。不存在本文已核实的统一强制上架审批步骤。

索引采用 `format: 1`，为每个版本列出精确版本、Unix 秒时间戳和来源。Git 来源必须固定 40 位提交 SHA；`engines.dsh` 与包声明一致。发布到可直接返回 JSON 的 HTTPS 地址后，用户可在“发现”中添加该索引源，再在界面核对来源并确认安装。

本项目的独立索引位于 `market/index.json`，发布后可添加：

```text
https://raw.githubusercontent.com/chanhaoxian5-ship-it/dsh-zotero/main/market/index.json
```

更新插件时，先完成代码提交和版本 tag，再将索引中的 SHA 指向该发布提交。索引可在后续单独的提交更新，避免让索引包含自身提交哈希的循环依赖。

也可由索引维护者把本仓库 URL 加入官方参考生成器的来源列表，生成器会发现匹配版本的 `vX.Y.Z` tag。给仓库加 `dsh-plugin` topic 有助于社区检索，但它不代表官方审核或自动收录。

官方依据：[插件索引](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/plugin-market.zh.md)、[参考生成器](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/plugin-market-generator/README.zh.md)。
