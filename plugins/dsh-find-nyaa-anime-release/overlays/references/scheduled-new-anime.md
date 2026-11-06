# 创建 DSH 定时追番

先读 [dsh-host-runtime.md](dsh-host-runtime.md)。仅在用户明确要求未来计划时创建，
创建本身不代表立即下载。确认作品、季/part、任务类型和用户的画质/字幕条件。

1. 已完结作品未指定未来时间：进入一次性检索，不创建周期任务或追番记录。
   明确未来只运行一次：使用一次性任务，整季走 package-review，不伪造 track。
   连载/待播且明确周期：才建立周期追番，通过 watch create 创建或复用确切 track。
2. 用 DSH `schedule_list` 查重，`schedule_view` 查看完整范围。不能覆盖不同季或条件的任务。
   用户时间优先，未指定时区默认 Asia/Shanghai。未指定时间时先核实播出方排期，
   可以建议首次可用时刻后两小时；不能可靠确认时才询问。
3. 使用 DSH `schedule_create(title,prompt,rrule,target)`；时区明确的 DTSTART 加一行 RRULE。
   周期示例形式：`DTSTART;TZID=Asia/Shanghai:YYYYMMDDTHHMMSS` 加换行
   `RRULE:FREQ=WEEKLY;BYDAY=FR;BYHOUR=22;BYMINUTE=0`，日期按真实当前时间生成。
   单次任务使用未来 DTSTART 和 `RRULE:FREQ=DAILY;COUNT=1`，不伪装成每周任务。
4. 默认 `target=this_session`，除非用户选择 `new_once` 或 `new`；不复制其他用户的会话 ID。
   保留已有任务归属、模型/preset、工作目录，更新时只提交必要字段。
5. 创建后 `schedule_view` 读回最终 prompt、计划、ID；通过 dsh_host.py task-snapshot
   生成绑定证据。周期任务按 completion.md 核验所有目标并 bind-automation。
   绑定失败时不交付。仅在真实工具读回成功后声称创建成功。
6. 保存常规计划和补查记忆到 task-snapshot 返回的 memory_directory，不存进插件目录。
   客户端准备按 client-readiness.md。没有客户端或后台运行条件时如实说明，不自动安装。

周期正文保持简短，使用 DSH 的 skill 名称而非依赖 Codex 的 `$` 语法：

```text
加载 find-nyaa-anime-release 技能，按 references/scheduled-run.md 执行。
范围：已核实的作品、年份、季/part、track_id 和必要编号映射；不扩展范围。
常规时间：实际约定的周期和时刻，Asia/Shanghai。
条件：browse，优先 1–2 GiB、允许向上兼容、中文字幕软偏好。
模式：最新未处理正片，授权加入 qBittorrent；其余执行技能默认规则。
```

显式只查/磁力/不下载时覆盖最后一行，不交付、不推进、不自动删除。原有任务的完整
prompt 变更要重新审阅所有目标再绑定。一次性整季任务引用 retrieval-workflow.md
与 package-review.md，没有单集 track；失败保留任务，成功交付或用户取消才删除。
DSH 的 ended 状态只是单次计划触发完毕，不能当成交付成功。宿主关闭时不会继续运行。
