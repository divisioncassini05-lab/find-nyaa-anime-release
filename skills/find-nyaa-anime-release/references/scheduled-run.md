# 定时运行

每次只推进下面一个步骤，依据工具结果进入下一步；沿用任务既有模型设置。
不一次读完所有参考文档，不读取创建模板，不复述已读规则。
任务中的显式范围、质量限制、只查/不下载要求优先。

## 1. 定位和分流

读取本任务实际配置、确切 Automation ID、memory.md 的 scheduled_watch 段，
运行 `python scripts/watch.py inspect "TITLE"` 查看任务固定 track_id 的 v3 状态。
核对身份和全部目标，不按标题猜归属。固定记录已不存在则结束，不重建、不下载。
未知身份或冲突先报告并停止检索，不通过猜测消除歧义。

按顺序选择首个适用分支：

| 状态 | 下一步 |
| --- | --- |
| 只查/磁力/不下载 | 只读检查；跳过恢复、绑定写入、交付及删除，进入步骤 3 |
| 有未完成 operation | `watch.py recover --operation OPERATION_ID`，保持原 hash；未解决就结束检索，已恢复交付则进入步骤 4 |
| completed、cleanup_pending 或待执行 outbox | 读取 [completion.md](completion.md)，只处理本任务相关清理 |
| finale_pending_evidence 且没有目标集 | 读取 [completion.md](completion.md)，只核验官方完结证据，不虚构下一集 |
| 其他可检索状态 | 进入步骤 2 |

涉及调度时先进入步骤 2 的计划校对；恢复和清理不能被旧窗口成功记录跳过。

## 2. 校对计划和归属

正常每周触发且没有补查/未完成调度意图时，直接进入归属核验。
存在临时计划、补查、未完成 intent，或本次不是常规时点时，读取
[scheduled-retry.md](scheduled-retry.md) 校对记忆与实际配置。
提前/重复触发尚未到期则结束。人工暂停或改时不覆盖。新窗口重置次数，
不能沿用上周成功；同一补查重入不再增加次数。

交付前按 [completion.md](completion.md) 的“Bind real ownership”核验
确切 ID、当前完整 prompt 的 UTF-8 SHA-256 和所有目标。未绑定或 hash 变化时，
审阅完整范围再绑定；失败则停止交付。不把自身 ID/hash 回填 prompt。

## 3. 检索与交付

读取 [retrieval-workflow.md](retrieval-workflow.md)，执行 workspace、discover、
detail、Agent review、验证和交付。创建 review 时才读 agent-review.md；
其他专题仅在该分支出现时加载。

每轮最多交付一个未处理的最新常规正片。默认 browse 1–2 GiB、允许向上兼容、
中文软偏好，review 和 deliver 使用相同条件；有显式上限/硬字幕要求则保留。
客户端接受且进度提交才算成功，不等下载完成。失败恢复原操作，不换候选重投。
只读模式只返回审阅结果，不更新 handled progress，也不执行完结删除。

## 4. 收尾

需要补查、恢复常规计划或已有调度 intent 时，读取
[scheduled-retry.md](scheduled-retry.md)；只读 planner 计算，app 工具修改原任务。
未更新、无合格资源、临时网络或详情不完整可 4 小时后补查，最多 3 次，
不跨下次常规检查；成功或耗尽恢复常规。已确认未开播/停播、歧义、权限拒绝、
永久失败不盲目补查；客户端失败只恢复原 operation。
上周已处理的集数不能证明本窗口成功。只读任务用 read_only_done 结束窗口。

出现最终集证据或清理请求才读 completion.md。只有整个固定范围的官方完结证据
和最终集 accepted receipt 都齐全，才能按 outbox 删除所属任务和本地记录。
只清本次范围及必要关联目标，不删除视频、字幕或客户端任务。

无新资源/只读等正常结束执行 `watch.py cleanup --run RUN_DIR`；
交付成功由脚本清理，未完成操作/未持久化回执保留。临时文件只放托管 run_dir。
无变化且无需行动时安静；交付、补查安排/耗尽、失败、完结简短通知。
只报告工具确认的状态，区分已加入客户端、下载完成和已观看。
