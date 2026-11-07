# 动漫搜索与自动追番 · DSH 插件

[完整功能介绍与使用说明](DETAILS.zh.md) · [GitHub 发布包](https://github.com/divisioncassini05-lab/find-nyaa-anime-release/releases)

将 `find-nyaa-anime-release` 的作品核验、整季/单集筛选、中文字幕检查和 qBittorrent
交付流程打包为 **DeepSeek Harness 原生技能插件**。安装后可直接用自然语言调用。

这是独立的 DSH 适配包，不需要先安装 Codex，也不会读取你的 Codex 追番记录。
模型负责理解与审阅，Python 脚本负责取证、校验和交付；体积大不等于画质一定更好。

## 能做什么

- 原生侧栏“动漫追番”：查看 DSH 追番记录、交付进度、下一目标和待核验操作；筛选与刷新不调用模型。
- 图形化填写作品、季集、画质、字幕与下载授权，在聊天中打开待发送请求；保留原有审核与交付流程。
- 从全名、别名与当前对话确认具体作品、季和集，不把外传当正篇。
- 查下一集、最新集、指定集、完整一季或电影，核对 Nyaa 详情与文件列表。
- 按轻量观看、普通观看、高画质筛选；默认正篇最低 1 GiB/集，电影最低 10 GiB。
- 可硬性要求中文字幕；只有证据支持才标记已确认，不把中文配音或组名当字幕证明。
- 返回可复制磁力，或在获得授权后交给 qBittorrent。只查/只要链接不会提交下载。
- 使用 DSH 自带定时工具追番；按真实客户端接受回执推进，遇到未出/失败不跳集。
- 可选连接 Bangumi，查询个人番单、评分与短评、辅助推荐，并同步明确看完或已交付的追番正篇单集；不改变本地找番决策。

## 环境要求

| 组件 | 要求 |
| --- | --- |
| DSH | 面向 `0.2.2-rc.1` 接口制作；声明支持 `>=0.2.2-rc.1 <0.3.0`，未来版本仍需验证 |
| Node.js | DSH 对应环境，24.9+；桌面端使用自己的宿主运行时 |
| Python | 3.11+，终端可运行 `python` / `python3` / `py -3` |
| Agent 工具 | 技能加载、文件读写、终端；名称/排期疑难时需要联网检索 |
| 网络 | 执行 DSH 的机器能访问 Nyaa 及需要的作品资料来源 |
| qBittorrent | 仅实际下载需要；Windows 桌面模式，或已配置的 Web API |
| 定时追番 | 当前 preset 提供 `schedule_create/list/view/edit`，且宿主在计划时运行 |

插件不自动安装 Python/qBittorrent，不开放 Web API，不修改代理、防火墙或模型选择。
没有下载客户端仍可检索和返回链接。Windows 若缺 IANA 时区数据，定时功能需要安装
`tzdata`；只读检查会提示，不能因此假称已完成无人值守配置。

## 安装

### 从插件包安装

当前版本为 `0.2.1`。从 [GitHub Release](https://github.com/divisioncassini05-lab/find-nyaa-anime-release/releases/tag/dsh-v0.2.1) 下载
`dsh-find-nyaa-anime-release-0.2.1.tgz`，交给 DSH，并说：

> 请通过当前 profile 的插件管理器安装这个本地插件包，完成后确认技能可加载。

也可以在 DSH CLI 中使用实际 profile 和本地绝对路径：

```sh
dsh plugin --profile web add "/absolute/path/dsh-find-nyaa-anime-release-0.2.1.tgz"
```

桌面端优先在应用内用插件管理器安装到当前 profile，不要照抄 `web` 去改另一个 profile。
源码 ZIP 解压后，插件管理器也可安装包含 `package.json` 的目录。不要只把 SKILL.md
复制进某个文件夹，否则会漏掉脚本及 DSH 调度适配。

更新已安装版本后按宿主提示重启。安装成功不等于运行成功：在技能选择器里确认
`find-nyaa-anime-release` 可用，然后运行一次只查请求。若宿主返回版本不兼容，
不要删掉版本声明强行安装，先核实接口变化。

### 更新已有安装

- 通过项目自定义市场安装：刷新原索引，在当前 profile 的插件管理器中更新到 `0.2.1`。
  [索引地址](https://raw.githubusercontent.com/divisioncassini05-lab/find-nyaa-anime-release/main/marketplace.json) 保持不变，版本固定到对应的源码提交。
- 通过本地包安装：下载新版 `.tgz`，让当前 profile 的插件管理器用它更新同名插件。
  不要只替换 `SKILL.md`；脚本、面板和宿主适配必须一起更新。
- 更新不会自动迁移 Codex 的记录或授权。已有 DSH 数据和定时任务保留；Bangumi
  凭据在 DSH 执行宿主中单独配置。同机可显式引用已有的私密令牌文件。

本索引由项目维护，不代表已被官方或社区公共市场收录。

### 调用例子

```text
用 find-nyaa-anime-release 找这部番的下一集，只返回磁力。
找某作品第一季完整合集，普通观看，必须有中文字幕。
每周五 22 点检查这部在播作品，有合格新集就加入 qBittorrent。
```

初次安装可让 Agent 进入技能资源目录执行 `python scripts/dsh_doctor.py`。
它只检查本地前置条件，**不联网、不启动客户端、不下载、不修改记录**。

## 图形面板（0.2.1）

安装并按宿主提示重载后，支持 Client UI 的 profile 会注册侧栏“动漫追番”。
纯终端或无 Client 服务的环境仍提供原来的 Skill，不强制安装 UI 服务。

![图形面板独立预览，使用示例数据，并非已登录的 DSH 实机截图](assets/readme/dsh-panel-preview.png)

- 列表显示 **已交付** 而不是“已观看”；只读取 DSH 的 v3 记录，不导入 Codex 数据。
- 已绑定 Bangumi 时，详情另列云端观看快照；待同步与下载待核验分开标注，下一目标仍来自本地记录。
- 点选记录可查看下一目标、检查待处理操作或准备定时追番请求。
- “在聊天中打开”只填入 **未发送草稿**，不直接执行模型任务；已有草稿使用追加方式，不覆盖。
- 默认不勾选下载；只有勾选“合格后提交 qBittorrent”后，生成的搜索请求才授权审核后的交付。
- 本地记录损坏、需要迁移或读取超时会显示错误，不假装为空列表，也不擅自修改文件。
- 面板不会直接增删计划或修改进度；操作仍由 Agent 按 Skill 进行。

本版已做独立浏览器界面检查与原生 Cordis 生命周期测试，**尚未完成登录后 DSH 桌面端实装验证**。
预览使用与插件相同的面板组件，但示例数据与草稿弹窗仅在预览中存在，不会被打入运行时插件。

## 数据与兼容性

### Bangumi（可选）

首次使用会提醒到 [官方令牌页面](https://next.bgm.tv/demo/access-token) 创建 Access Token。
将令牌保存在 DSH 执行宿主上的私密文本文件，告诉 Agent 文件路径，或设置
`BANGUMI_ACCESS_TOKEN`。不要把令牌贴进聊天；不会读取 Codex 的凭据。

可问“在看列表和进度”“根据我看过的番、评分和短评推荐几部”，或说“这部番第 6 集看完了”。
查询按需筛选、分页，不为每次找番加载全部收藏；当前读取收藏短评，不读取长篇日志。
已核验接受的追番正篇单集按约定记为已看，链接查询和添加失败不写回。
整季/电影不自动推断逐集观看，可明确说看完后写入。
Bangumi 的进度、搁置或弃坑状态不改变本地下一目标、画质或下载策略；断网时同步待重试，下载结果仍有效。

详情及命令见随包 [Bangumi 使用说明](skills/find-nyaa-anime-release/references/bangumi-sync.md)。

### 本地隔离

- 脚本随包安装，所有证据、进度和恢复日志放在包目录外，更新和卸载不会抹掉它们。
- Windows 默认数据目录 `%LOCALAPPDATA%/DSH/AnimeRelease`；macOS、Linux 使用对应的用户数据目录。
- `ANIME_DSH_HOME` 可指定绝对数据目录；默认目录适合单一 profile。多个 profile 做定时追番时必须分别配置，不能用一个 profile 的任务清单证明另一个没有任务。
- 默认桌面下载目录 `~/Downloads/Anime`；`ANIME_DSH_DOWNLOAD_DIR` 可覆盖。
- qBittorrent 凭据只通过执行宿主的环境变量传入，不写任务正文。
- Bangumi 凭据引用和个人番单缓存保存在包外；公共发布不包含令牌、评论或观看历史。
- 远程/容器 DSH 只能直接控制其所在机器；要操作另一台电脑的客户端，应显式配置可达的 Web API。
- 当前自动补查规划器只优化 Asia/Shanghai 的单一每周时点。其他 DSH 计划可保留运行，但不会擅自转换时区、套用补查或创建额外任务。
- DSH 未开放定时工具时，交互查询仍可使用；定时及需要任务读回的自动清理会停止并报告缺少能力。

详细适配边界与验证范围见 [COMPATIBILITY.md](COMPATIBILITY.md)。这不是 DSH 官方插件，
也不是播放软件；只能用于你有权获取的内容。第三方站点、种子活跃度及模型判断会影响结果。

## 维护与上架

源码中 `overlays/` 和 `tools/sync_skill.py` 保存适配逻辑，`skills/` 是已包含全部脚本的
可安装快照；来源文件哈希记录在 `UPSTREAM.json`。更新上游后可重新构建：

```sh
python tools/sync_skill.py --source "/absolute/path/find-nyaa-anime-release"
npm ci --ignore-scripts
npm run build
npm test
python -m pytest tests/test_dsh_adapter.py skills/find-nyaa-anime-release/tests -m "not live" -p no:cacheprovider
npm pack --ignore-scripts
```

安装包无生命周期脚本、无 npm 运行时依赖，不会下载一个未知版本的 skill。
预构建客户端通过 DSH ModuleLoader 加载，共用宿主 React；构建依赖仅在开发时安装。
开发预览：`npm run build` 后运行 `npm run preview`，打开 `http://127.0.0.1:4319`。
预览只含示例数据，不访问真实追番记录或下载客户端。
`.tgz` 不含测试和 Python 字节码；源码 ZIP 另外提供测试、适配覆盖文件和构建工具。
本次实际验证记录见 [BUILD-REPORT.md](BUILD-REPORT.md)。
上架资料与索引生成步骤见 [MARKETPLACE.md](MARKETPLACE.md)。本地生成的包不等于已经
发布到 npm 或被市场收录，需先发布源码/版本，再提交所使用市场的收录渠道。

基础 skill：[divisioncassini05-lab/find-nyaa-anime-release](https://github.com/divisioncassini05-lab/find-nyaa-anime-release)。
本插件沿用 MIT 许可；随附的 Python 依赖和身份目录保留各自许可文件。
