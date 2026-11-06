# 动漫搜索与自动追番 · DSH 插件

[完整功能介绍与使用说明](DETAILS.zh.md) · [GitHub 发布包](https://github.com/divisioncassini05-lab/find-nyaa-anime-release/releases)

将 `find-nyaa-anime-release` 的作品核验、整季/单集筛选、中文字幕检查和 qBittorrent
交付流程打包为 **DeepSeek Harness 原生技能插件**。安装后可直接用自然语言调用。

这是独立的 DSH 适配包，不需要先安装 Codex，也不会读取你的 Codex 追番记录。
模型负责理解与审阅，Python 脚本负责取证、校验和交付；体积大不等于画质一定更好。

## 能做什么

- 从全名、别名与当前对话确认具体作品、季和集，不把外传当正篇。
- 查下一集、最新集、指定集、完整一季或电影，核对 Nyaa 详情与文件列表。
- 按轻量观看、普通观看、高画质筛选；默认正篇最低 1 GiB/集，电影最低 10 GiB。
- 可硬性要求中文字幕；只有证据支持才标记已确认，不把中文配音或组名当字幕证明。
- 返回可复制磁力，或在获得授权后交给 qBittorrent。只查/只要链接不会提交下载。
- 使用 DSH 自带定时工具追番；按真实客户端接受回执推进，遇到未出/失败不跳集。

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

把发布包 `dsh-find-nyaa-anime-release-0.1.0.tgz` 交给 DSH，并说：

> 请通过当前 profile 的插件管理器安装这个本地插件包，完成后确认技能可加载。

也可以在 DSH CLI 中使用实际 profile 和本地绝对路径：

```sh
dsh plugin --profile web add "/absolute/path/dsh-find-nyaa-anime-release-0.1.0.tgz"
```

桌面端优先在应用内用插件管理器安装到当前 profile，不要照抄 `web` 去改另一个 profile。
源码 ZIP 解压后，插件管理器也可安装包含 `package.json` 的目录。不要只把 SKILL.md
复制进某个文件夹，否则会漏掉脚本及 DSH 调度适配。

更新已安装版本后按宿主提示重启。安装成功不等于运行成功：在技能选择器里确认
`find-nyaa-anime-release` 可用，然后运行一次只查请求。若宿主返回版本不兼容，
不要删掉版本声明强行安装，先核实接口变化。

### 调用例子

```text
用 find-nyaa-anime-release 找这部番的下一集，只返回磁力。
找某作品第一季完整合集，普通观看，必须有中文字幕。
每周五 22 点检查这部在播作品，有合格新集就加入 qBittorrent。
```

初次安装可让 Agent 进入技能资源目录执行 `python scripts/dsh_doctor.py`。
它只检查本地前置条件，**不联网、不启动客户端、不下载、不修改记录**。

## 数据与兼容性

- 脚本随包安装，所有证据、进度和恢复日志放在包目录外，更新和卸载不会抹掉它们。
- Windows 默认数据目录 `%LOCALAPPDATA%/DSH/AnimeRelease`；macOS、Linux 使用对应的用户数据目录。
- `ANIME_DSH_HOME` 可指定绝对数据目录；默认目录适合单一 profile。多个 profile 做定时追番时必须分别配置，不能用一个 profile 的任务清单证明另一个没有任务。
- 默认桌面下载目录 `~/Downloads/Anime`；`ANIME_DSH_DOWNLOAD_DIR` 可覆盖。
- qBittorrent 凭据只通过执行宿主的环境变量传入，不写任务正文。
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
npm test
python -m pytest tests/test_dsh_adapter.py skills/find-nyaa-anime-release/tests -m "not live" -p no:cacheprovider
npm pack --ignore-scripts
```

安装包无生命周期脚本、无 npm 运行时依赖，不会下载一个未知版本的 skill。
`.tgz` 不含测试和 Python 字节码；源码 ZIP 另外提供测试、适配覆盖文件和构建工具。
本次实际验证记录见 [BUILD-REPORT.md](BUILD-REPORT.md)。
上架资料与索引生成步骤见 [MARKETPLACE.md](MARKETPLACE.md)。本地生成的包不等于已经
发布到 npm 或被市场收录，需先发布源码/版本，再提交所使用市场的收录渠道。

基础 skill：[divisioncassini05-lab/find-nyaa-anime-release](https://github.com/divisioncassini05-lab/find-nyaa-anime-release)。
本插件沿用 MIT 许可；随附的 Python 依赖和身份目录保留各自许可文件。
