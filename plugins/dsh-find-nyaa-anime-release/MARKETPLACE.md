# 发布与市场收录

这个目录已经是可安装的 DSH bundle，安装不需要构建。发布前确认包内没有
追番记录、qBittorrent 密码、个人聊天 ID、缓存或真实任务快照。

## 当前发布地址

- [插件源码与详情](https://github.com/divisioncassini05-lab/find-nyaa-anime-release/tree/main/plugins/dsh-find-nyaa-anime-release)
- [GitHub Release 安装包](https://github.com/divisioncassini05-lab/find-nyaa-anime-release/releases)
- [npm 包](https://www.npmjs.com/package/dsh-find-nyaa-anime-release)
- [DSH 自定义市场索引](https://raw.githubusercontent.com/divisioncassini05-lab/find-nyaa-anime-release/main/marketplace.json)

将索引地址加入 DSH 的 Custom plugin indexes / Discover 后刷新，选择「dsh-find-anime」。从 `0.2.2` 起，索引使用 npm 精确版本，更新时保留同一个索引 URL。本项目尚未宣称被公共市场收录。

## 发布仓库

本插件位于原项目的 `plugins/dsh-find-nyaa-anime-release` 子目录；
原 Codex 的 `skills/find-nyaa-anime-release` 安装路径保持不变。
保留 package.json、cordis.patch.yml、index.js、locale、icon.svg、skills、许可及说明。
添加 GitHub topic `dsh-plugin` 可让社区发现它，但不代表已经通过任何市场的审核。
源码发布后记录包含这些文件的真实 commit SHA；不要用上游 skill 的旧 commit 代替。

## 同步发布流程

每次更新一起发布 Codex 核心、DSH 适配、npm 包、GitHub Release 和自定义市场索引。
包名、仓库地址和 Codex 安装路径保持不变。具体维护约束见仓库根目录 `AGENTS.md`。

1. 同步核心与适配，更新插件版本及 lockfile，运行两套 Python 测试、Node 测试和同步校验。
2. 运行 `npm run build` 与 `npm pack --ignore-scripts`，用 `tools/verify_and_archive.py`
   核验实际包并生成源码 ZIP、SHA256 校验文件；检查无凭据、个人数据和缓存。
3. 提交代码。以维护者账号运行 `npm whoami --registry=https://registry.npmjs.org`；
   未登录时运行 `npm login --auth-type=web --registry=https://registry.npmjs.org`，由本人完成网页授权。
4. 发布刚刚核验的同一个 `.tgz`，不要重新从另一个目录打包：

```sh
npm publish dist/release-<VERSION>/dsh-find-nyaa-anime-release-<VERSION>.tgz --access public --tag latest --ignore-scripts --registry=https://registry.npmjs.org/
npm view dsh-find-nyaa-anime-release@<VERSION> version dist.integrity --json --registry=https://registry.npmjs.org/
npm view dsh-find-nyaa-anime-release dist-tags --json --registry=https://registry.npmjs.org/
```

5. 对比 `dist.integrity` 与本地 `.tgz` 的 SHA-512 SRI，确认 `latest` 等于本次版本后，
   生成并提交下方 npm 索引，推送代码与索引；把同一 `.tgz`、源码 ZIP 和校验文件
   附到 `dsh-v<VERSION>` GitHub Release。
6. 读回 npm、公开索引和 GitHub Release，确认版本一致。任一渠道未完成都要如实说明，
   不能把“已推送 GitHub”说成“DSH 可更新”。已发布版本不可覆盖，修正使用新版本号。

本包不包含发布凭据。不要在仓库、聊天或发行包中写入 npm Token、密码或验证码。
首次 npm 发布仍需本人验证；安装者无需 npm 账号。

## DSH 原生自定义索引

DSH 自定义索引格式是 `format: 1`。npm 版本已公开并核验后，从插件目录运行：

```sh
python tools/make_market_index.py --source npm --repository https://github.com/divisioncassini05-lab/find-nyaa-anime-release --path plugins/dsh-find-nyaa-anime-release --output ../../marketplace.json
```

需要 Git 来源时仍支持 `--source git --commit REAL_40_HEX_COMMIT`，但 Git / 路径 /
压缩包依赖不具备 DSH 的原生 npm 更新检查，不应替代默认 npm 发布渠道。
生成器把图标嵌入索引，不需要另外托管图片。将索引放到无重定向、可直接读取的
HTTPS 静态地址，然后在 DSH 的 Custom plugin indexes / Discover 添加这个地址。
社区市场各有收录流程，提交真实仓库或版本链接即可；不要把索引可用说成社区已收录。

发布后先在一个独立 DSH profile 用插件管理器安装，确认：插件中文标题、技能可加载、
Python doctor 正常、一次只查请求可以取证。再测试自己授权的客户端和定时任务。
安装新版本后按宿主要求重启，并核对数据目录没有变化。
