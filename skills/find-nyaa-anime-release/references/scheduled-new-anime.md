# 新番定时追更：固定创建流程与提示词

用于创建新的新番追更任务，以及运行由本模板创建的任务。用户说“给《作品名》
创建追番定时任务，每周四晚上十点检查”即可。维护模板不授权批量修改既有任务。

## 创建与参数填充

1. 读取 SKILL.md，inspect 已有记录；核实作品年份、季／part、provider 绑定和
   集数映射。使用已验证别名搜索，不能通过模糊首项绑定作品。新记录经 watch create
   建档；未知字段保留未知，有真实歧义才询问。计划尚未开播不妨碍建立将来任务，
   但不凭日期推断已发布。身份未解决时停止创建。
2. 检查现有自动化的完整 prompt 和身份：相同目标和用途优先复用。不同季、part、
   下载模式或硬限制不是同一用途，不能覆盖。只有用户明确要求新建重复任务才重复。
   用户明确时间优先，默认 Asia/Shanghai；未指定时间先核实官方/播出方首播或配信
   时刻，以可验证的首发可用时刻后 2 小时作为建议检查时间，并在创建结果中说明。
   多个不能消歧的时刻或无可靠时刻才询问；不把日本深夜日期直接当北京时间。
3. 将下方唯一 canonical prompt 中五个占位符替换为实际文本：作品与别名、身份、
   常规计划、质量条件、字幕条件。默认 browse 1–2 GiB，允许向上兼容，中文软偏好；
   显式 min/max/tier/硬中文字幕优先，review 和 deliver 使用相同参数。
   若用户明确只查/磁力/不下载，改写交付段为仅 discover/detail/review 并返回结果；
   删除 enqueue 授权、交付成功条件和自动完结删除条款，不更新 handled progress，
   使用 read_only_done 结束窗口。不能只在顶部加一句例外却留下相反执行指令。
4. 用 automation_update 创建或更新。普通新请求使用当前聊天 heartbeat；明确要求
   独立任务才采用 standalone cron。保留已有任务 kind/归属，除非用户要求迁移；
   不擅自指定新模型。按工具契约完整保留其他字段。将无变化静默写入 prompt，
   不以仅失败通知策略屏蔽用户需要的成功交付通知。
5. 创建返回后读回实际 ID、最终 prompt 和计划。SHA-256 使用最终保存的 prompt
   UTF-8 内容，不能自己归一化空白；不把自身 ID/hash 回填 prompt，避免循环变更。
   核验全部目标，按 [completion.md](completion.md) 调用 bind-automation。绑定失败
   明确报告，首次交付前修复；scope 变化须重新审阅全部范围，不能盲目重绑后删除。
6. 保存常规计划和创建结果。确认创建不等于已经下载；只有工具返回/读回确认后才
   报告已创建。结果不确定先读回查重，不能再造一个任务。

## 固定提示词

```text
使用 $find-nyaa-anime-release 执行新番定时追更。

【固定范围】
作品：{{已核实的作品名及别名}}
身份：{{年份、季／part、已核实的 provider 绑定及已有 track_id}}
常规计划：{{星期与时间}}，时区 Asia/Shanghai。
仅覆盖上述播出范围；不自动扩展到续作、其他季、特别篇或合集。
目标为最新已发布的常规正片；默认授权将合格资源加入 qBittorrent。

【质量与字幕】
{{默认：browse，每集优先 1–2 GiB，允许向上兼容}}
{{默认：中文字幕软偏好}}
优先选择档位内合格资源；只有档位内无合格候选时才允许向上兼容。
不降低最低体积；用户明确指定的最大体积和字幕硬要求始终有效。
字幕必须有详情、文件或轨道证据，不能仅凭 MultiSub 或中文标题推断。

【运行入口】
每次读取当前 skill、references/scheduled-new-anime.md、v3 追番状态、
本任务配置和运行记忆。取得运行上下文中的确切 Automation ID，
核验完整任务范围并绑定 automation_id、prompt scope hash 和全部目标 track。
不通过标题猜测归属，不使用旧状态 writer 或旧定时包装脚本。

先处理尚未完成的交付恢复、完结核验和 outbox。
已有待恢复 operation 时，恢复原 operation_id 和 info_hash；
未解决前不得搜索替代候选或发起另一笔交付。
恢复本轮已交付一个资源后，不再交付另一集。
已 completed 的对象只处理尚未完成的清理。
最终集已处理但证据未确认时，只核验完结，不虚构下一集。
分割放送的中途停播不等于整个绑定范围已完成。

【发现、审阅与交付】
需要检索时，先创建 skill 管理的运行工作目录。
读取完整时间顺序列表及候选详情，确认作品、季／part、集数映射、
真实视频大小、字幕和 hash，生成并完成 Agent review manifest。
不能把最新上传直接当作最新集，也不能仅凭播出计划判定已经发布。

每轮最多选择并交付一个尚未处理的最新正片资源。
使用 v3 watch deliver，携带 --review、--latest、--include-magnet、
--legal-ok、--enqueue-qbittorrent，以及完整质量条件；
默认启用 --allow-upward-compatibility 和 --want-zh。
交付前证据变化时重新审阅，不暗中替换候选或放宽条件。

只有匹配的 accepted receipt 返回 already_present、submitted 或
submitted_verified 后，才通过 StateRepository 提交进度。
启动器退出、HTTP 成功、已生成磁力都不等于客户端接受。
接受后提交状态失败，保留并恢复原操作。
成功边界为已加入客户端，不等待视频下载完成。

【有限补查】
常规检查为第 0 次；本轮尚未成功且属于以下情况时，
复用本任务安排 4 小时后的补查，最多补查 3 次：
尚未更新、合格资源未出现、临时网络失败或详情证据暂时不完整。

已确认尚未开播或官方停播的时段不反复补查。
身份歧义、证据冲突、永久失败、权限或审批拒绝不安排盲目重试。
客户端问题按 RecoveryAction 恢复原操作；
不得将客户端上下文失败当成普通网络失败循环补查。

保存常规计划、本轮窗口、补查次数、目标时间、失败阶段和调度结果。
补查可跨午夜，但不能跨入下一次常规检查；到达下一常规时点即结束旧窗口。
成功、次数耗尽或无需补查时恢复常规计划。
每次入口核对实际调度与已保存意图，修复中断留下的临时计划。

上一个窗口的成功记录不能阻止新窗口检查。
“最新集此前已处理”必须结合本窗口的发布证据判断；
不能因为上周那集已处理，就认定本周已经更新并成功。

按 scheduled-new-anime.md 使用只读补查计算助手。
修改调度前保存意图，只用 automation_update 修改本任务，保留其他配置。
结果不确定时读回确认，不能重复创建任务。
记录无法保存时不安排临时补查；已有临时计划时恢复常规计划并报告保存失败。
只有工具确认成功后，才报告已安排或已恢复计划。

【完结与删除】
官方或播出方明确确认最终集，且最终集已有 accepted delivery receipt，
才使用独立 reconcile 流程持久化 completed。
计划日期到期、没有下一集信息或集数达到预计总数均不单独证明完结。

完成后核验确切 Automation ID、当前 prompt scope hash、
全部目标均 completed、最终集接受回执及无待恢复操作或待执行重试子任务，
通过 outbox 执行所属自动化删除，并保存真实删除回执。
删除失败保留 cleanup_pending；后续运行只继续清理，不重复检索或提交。
保留完成记录，不把删除失败报告为已停止任务。

【文件与反馈】
listing、detail、review、临时报告均放入本轮托管目录，不写入 Download 根目录。
成功提交后的证据由交付流程清理；没有新资源等正常结束分支显式执行
watch cleanup --run RUN_DIR。
保留未完成操作引用的证据、正式追番状态和持久化回执。

没有变化且无需行动时保持安静。
成功交付、安排补查、补查耗尽、需要处理的失败、完结或清理失败时简短通知。
说明实际集数、资源大小、字幕、客户端接受结果及下一次补查时间。
严格区分“已加入 qBittorrent”“下载完成”和“已观看”。
```

## 补查计算和调度确认

`scripts/scheduled_watch.py` 只计算/核对，不写状态、不创建任务、不调用客户端。
输入输出临时 JSON 放在托管 run_dir 并登记；长期记忆保存本任务 memory.md 的
`scheduled_watch` JSON 段，包含 regular_rrule、timezone、window_start、attempt、
retry_due、intent 和 applied_receipt；不保存另一份追番进度。

每次入口先校对记忆与当前 scheduler 配置。window_start 是常规主检查的实际计划
时点，不是补查时点；窗口终点为其后 7 天。新窗口开始时重置 attempt=0，旧窗口
成功不沿用；待恢复 operation 和 outbox 不随窗口重置。补查以保存的 retry_due
和 next_attempt 识别；相同执行重入不再次加次数。提前/重复触发且尚未到 retry_due
时只校对调度后退出。工具不支持本模板的单个每周时点时，保留常规计划并报告，
不另造子任务或 shell 定时器。

调用 `python scripts/scheduled_watch.py plan --input RUN_DIR/SCHEDULE_INPUT.json`。
输入字段：

- automation_id、scope_hash：当前已验证归属；timezone 固定 Asia/Shanghai。
- regular_rrule：首次保存的常规每周计划；不能从补查的临时 rrule 反推。
- current_rrule：本次从 scheduler 读取的当前计划，用于阻止覆盖随后发生的人工改时。
- window_start、now：带时区 ISO 时间；now 取实际当前时间。
- attempt：本次实际检查编号，主检查 0、补查 1–3。
- outcome：not_updated / release_unqualified / network_transient / detail_incomplete；
  latest_already_handled 只有 current_window_release_verified=true 才结束窗口。
  该布尔值需要本窗口目标已发布并处理的证据，不能只看 handled progress 或
  新上传了旧集；缺乏证据视为仍未更新。
- delivered 另需 accepted_and_committed=true。其他结果可用 pre_airing、hiatus、
  blocked、identity_ambiguous、permission_denied、permanent_failure、tls_failure、
  client_recovery、finale_pending_evidence、completed、cleanup_pending、read_only_done。

助手输出 action、desired_rrule、next_retry_at、next_attempt、plan_id。
时间按当前时刻加 4 小时向上取整到分钟，最多 3 次且不能跨入下一常规检查。
`restore_regular` 恢复常规；`recover_operation`/`await_completion` 在恢复常规后
只走对应恢复/证据流程；`drain_outbox` 优先删除，删除失败则恢复常规供以后清理。
这些 action 都不是新的交付授权。

先把完整计划作为 intent 持久化并读回，再执行只读门禁：
`python scripts/scheduled_watch.py prepare --plan RUN_DIR/PLAN.json --snapshot RUN_DIR/SNAPSHOT.json --saved-intent RUN_DIR/SAVED_INTENT.json --now CURRENT_ISO_TIME`。
没有持久化意图、归属变化、人工暂停/改时或过期补查均拒绝生成更新建议；
already_applied 直接读回确认，不重复修改。然后用 automation_update 更新**相同 ID**
的 rrule，保留 prompt、kind、名称、模型、项目/聊天归属及其他配置。
工具调用前重新检查 next_retry_at 仍在未来；过期则重新计算并重新保存意图。
读回当前配置后运行：
`python scripts/scheduled_watch.py verify --plan RUN_DIR/PLAN.json --snapshot RUN_DIR/SNAPSHOT.json --saved-intent RUN_DIR/SAVED_INTENT.json`。
snapshot 是工具/实际配置中的 id、prompt、rrule、status；saved-intent 必须从已保存
记忆重新读取。调用超时但读回一致时确认已应用；不一致则明确未确认，保留意图
以便后续恢复，不创建第二个任务。人工修改 prompt/暂停任务时停止旧意图重放。

若保存意图失败，不应用临时计划；若先前已有临时计划，则通过 app 工具恢复常规，
分别报告恢复是否成功。调度成功但回执保存失败时保留先前 intent；下次先读回校对。
彻底中断可能使修复延迟到下一次实际运行，不能声称进程退出期间已自动恢复。
删除任务可能删除 memory 目录，删除回执使用 v3 outbox 持久化，不重建被删除目录。

## 模板维护验收

检查单一模板占位、创建去重/歧义分支、只读覆盖、参数一致性和 v3 命令。
用只读 planner 覆盖跨日、次数、旧窗口、官方停播、保存失败与读回不确定场景；
用 fake client/automation adapter 覆盖交付、恢复、完结与删除；使用临时仓库验收
证据清理。不得真实提交 torrent、修改现有自动化或以实盘下载验证模板。
