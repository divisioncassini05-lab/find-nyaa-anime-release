# 发布与市场收录

这个目录已经是可安装的 DSH bundle，安装不需要构建。发布前确认包内没有
追番记录、qBittorrent 密码、个人聊天 ID、缓存或真实任务快照。

## 当前发布地址

- [插件源码与详情](https://github.com/divisioncassini05-lab/find-nyaa-anime-release/tree/main/plugins/dsh-find-nyaa-anime-release)
- [GitHub Release 安装包](https://github.com/divisioncassini05-lab/find-nyaa-anime-release/releases)
- [DSH 自定义市场索引](https://raw.githubusercontent.com/divisioncassini05-lab/find-nyaa-anime-release/main/marketplace.json)

将索引地址加入 DSH 的 Custom plugin indexes / Discover 后刷新，选择「动漫搜索与自动追番」。索引固定到与版本对应的源码 commit，更新时保留同一个索引 URL。本项目尚未宣称被公共市场收录，也没有发布到 npm。

## 发布仓库

本插件位于原项目的 `plugins/dsh-find-nyaa-anime-release` 子目录；
原 Codex 的 `skills/find-nyaa-anime-release` 安装路径保持不变。
保留 package.json、cordis.patch.yml、index.js、locale、icon.svg、skills、许可及说明。
添加 GitHub topic `dsh-plugin` 可让社区发现它，但不代表已经通过任何市场的审核。
源码发布后记录包含这些文件的真实 commit SHA；不要用上游 skill 的旧 commit 代替。

## npm 或发布附件

`npm pack --ignore-scripts` 生成 `.tgz`；可以作为 GitHub Release 附件供本地安装。
如选择 npm，需要有对应包名的发布权限；确认包名可用后再运行 npm publish。
本包没有发布凭据，也不会自动登录或上传。更改包名时同步 cordis.patch.yml 的 name。

## DSH 原生自定义索引

DSH 自定义索引格式是 `format: 1`，Git 来源必须固定到真实的 40 位 commit。
公开源码后运行（参数换成实际值）：

```sh
python tools/make_market_index.py --repository https://github.com/OWNER/REPO --commit REAL_40_HEX_COMMIT --output marketplace.json
```

若插件在仓库子目录，增加 `--path plugins/dsh-find-nyaa-anime-release`。
生成器把图标嵌入索引，不需要另外托管图片。将索引放到无重定向、可直接读取的
HTTPS 静态地址，然后在 DSH 的 Custom plugin indexes / Discover 添加这个地址。
社区市场各有收录流程，提交真实仓库或版本链接即可；不要把索引可用说成社区已收录。

发布后先在一个独立 DSH profile 用插件管理器安装，确认：插件中文标题、技能可加载、
Python doctor 正常、一次只查请求可以取证。再测试自己授权的客户端和定时任务。
安装新版本后按宿主要求重启，并核对数据目录没有变化。
