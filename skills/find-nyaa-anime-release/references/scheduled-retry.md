# 补查计算和调度确认


`scripts/scheduled_watch.py` 只计算/核对，不写状态、不创建任务、不调用客户端。
输入输出临时 JSON 放在托管 run_dir 并登记；长期记忆保存本任务 memory.md 的
`scheduled_watch` JSON 段，包含 regular_rrule、timezone、window_start、attempt、
retry_due、intent 和 applied_receipt；不保存另一份追番进度。

每次入口先校对记忆与当前 scheduler 配置。window_start 是常规主检查的实际计划
时点，不是补查时点；窗口终点为其后 7 天。新窗口开始时重置 attempt=0，旧窗口
成功不沿用；待恢复 operation 和 outbox 不随窗口重置。补查以保存的 retry_due
和 next_attempt 识别；相同执行重入不再次加次数。提前触发先运行
`python scripts/scheduled_watch.py gate --rrule "当前实际规则" --due-at "已核实的 retry_due"`。
提前不超过 5 分钟返回 wait_until_due，按返回的 wait_seconds 分段等待并用真实
当前时间重查（每段最多 60 秒）；不能丢弃本轮，也不能靠假设将来再次触发。
更早的补查返回 not_due，保留原计划和意图，不增加次数，不伪造已检查结果。
常规时点 gate 不传 --due-at，临近下一时点会归入下一窗口，不能用上周成功跳过。
等待结束后重读配置，人工暂停/改时/范围变化先重新校对；再按原 operation 和
本窗口记忆去重。无法继续等待需明确报告本轮未执行，不静默称无需处理。
工具不支持本模板的单个每周时点时，保留常规计划并报告，
不另造子任务或 shell 定时器。

调用 `python scripts/scheduled_watch.py plan --input RUN_DIR/SCHEDULE_INPUT.json`。
输入字段：

- automation_id、scope_hash：当前已验证归属；timezone 固定 Asia/Shanghai。
- regular_rrule：首次保存的常规每周计划；不能从补查的临时 rrule 反推。
- current_rrule：本次从 scheduler 读取的当前计划，用于阻止覆盖随后发生的人工改时。
- window_start、now：带时区 ISO 时间；now 取实际当前时间。
- attempt：本次实际检查编号，主检查 0、补查 1–3。
- outcome：not_updated / release_unqualified / network_transient / detail_incomplete；
  检索连接失败优先采用工具的 transport.scheduled_outcome，不根据 TLS 字样一概停止。
  握手中断/EOF 可归 network_transient；证书、身份上下文和权限失败仍不可盲目补查。
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

