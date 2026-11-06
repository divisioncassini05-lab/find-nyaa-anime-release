# 客户端生命周期、交付与传输诊断

首次配置自动下载、观察到系统弹窗，或可执行文件路径／Windows 用户／网络类型
变化时读取。正常运行沿用已核实环境和用户下载授权，不每集重复确认或要求截图。
仅查资源／磁力模式不要求客户端准备。维护验证不启动客户端或真实下载。

## 固定客户端与独立运行

客户端管理由提交器负责，不在每个任务里另写启动命令。先用只读入口检查：

```powershell
python scripts/qbittorrent_submit.py --client-status --json
```

默认优先已安装的最新版：每次合并当前会话进程、注册安装、PATH、标准安装位置
与已知便携位置，读取文件版本号并按数字比较，不能按路径顺序、修改时间或字符串
排序。版本相同时优先运行中的副本。版本号不缓存；原地升级或发现新的安装路径后，
下一次调用自动重新比较。无法读取版本时报告 `executable_version_unverified`，
不猜测最新版。未注册且不在上述来源中的便携安装需要用户提供路径。

仅显式 `--exe` 或用户配置的 `QBITTORRENT_EXE` 才固定路径；日常任务不要自动
把这次选中的路径写成固定覆盖。显式路径失效不静默换另一套。旧版本仍在运行时，
不能为复用它而放弃最新版，也不强制结束下载；报告版本／路径冲突，待正常退出后
再用最新版恢复原 operation。出现多个安装进程或无法核实路径时同样先解决冲突。
不要为统一路径卸载另一套软件。路径变化后重新核对对应防火墙规则。

已运行时复用。Windows 冷启动与磁力／种子交接都通过本地 WMI 创建进程，
避免继承执行命令的 Job Object；先经过现有正常用户上下文检查。
这不创建开机任务、服务或提升权限。WMI 创建失败／响应不明时，不退回
普通子进程启动，不用另一个账户、计划任务或关闭安全策略补救。
通过执行工具允许的权限流程处理；同一失败环境不盲目重试。
`CREATE_NO_WINDOW`、`Start-Process` 或只改进程组不能作为生命周期隔离证据。

启动成功需观察准确安装的进程；WMI 返回成功只表示创建成功，不能当作资源回执。
交付仍按原 hash 验证 metadata/fastresume 或已配置 API，再提交追番进度。
检查结束只关闭自身观察句柄，不结束、重启 qB 或等待整集下载完。
旧方式启动的现有进程不会因更新 skill 自动迁移；需要切换时等用户正常退出，
后续冷启动才使用新方式，不中断正在进行的下载。

## 速度慢或跟随退出

按证据分层检查，结论区分已确认与推测：

| 层次 | 证据与处理 |
| --- | --- |
| 客户端生命周期 | 对照实际路径、版本、启动时间、父进程和退出日志。没有正常退出记录只支持异常终止，不能单独认定 Codex 杀进程。 |
| 任务状态 | 优先读取已配置且已认证的 API 或 GUI：暂停、排队、校验、元数据、下载、完成，以及普通／备用限速。fastresume 是有时间戳的持久快照，不当实时速度。 |
| 连接与资源 | 看同一 hash 的 Tracker、可用种子／用户、DHT 和接收字节变化。必要时隔 15–30 秒做一次有限对比；两次不足仍保留不确定性，不无限轮询。 |
| 本机网络 | 核对 qB 自身代理和绑定网卡、当前路径的防火墙及 Clash 的 TUN、系统代理和匹配规则；不输出订阅地址、密码或密钥。 |

进程 I/O 包含磁盘读写，不能换算成下载速度；TCP 数量不包含所有 uTP 连接，
也不能证明某个资源正在传输。Clash 在运行或系统代理开启不证明 qB 经过它；
TUN 关闭也不能排除 qB 自身代理。重启后重新校验／建立连接是待验证原因，
不保证稍等就会恢复。UPnP 的成功和失败要对应网卡／时间，不能凭单行概括全局。

只在证据支持且用户授权范围内修复具体项，并读回结果。不要以速度慢为由
直接改 Clash、代理、全局限速或防火墙，也不自动换资源、重复添加、回退进度。
需要换源时沿用已有替换／审核流程。无法读取实时状态就明确说明诊断边界，
不要为了诊断自动开放 Web UI。正常交付无需每次附带完整测速检查。

## 区分三类确认

- Windows 安全中心询问允许网络访问：这是防火墙入站授权，不是资源验证、
  qBittorrent 添加任务确认，也不是执行工具的权限审批。
- qBittorrent 添加任务对话框：现有提交器已使用 `--skip-dialog=true`。
  该参数不能消除 Windows 授权、首次使用声明或执行工具审批。
- 执行工具拒绝：走工具允许的审批路径；已授权下载不等于绕过权限限制。

## 只读核对

先核实提交器实际选中的程序路径（包括显式路径、环境变量及自动发现结果），
再与进程路径、当前网络类型和有效规则比较。不要仅凭规则显示名认定已放行；
旧安装路径的规则不适用于新路径。下面的 PowerShell 查询不改变系统配置：

```powershell
Get-CimInstance Win32_Process -Filter "name='qbittorrent.exe'" |
    Select-Object ProcessId, ExecutablePath
Get-NetConnectionProfile | Select-Object Name, NetworkCategory
Get-NetFirewallApplicationFilter -PolicyStore ActiveStore -ErrorAction Stop |
    Where-Object { $_.Program -match 'qbittorrent' } |
    ForEach-Object {
        $clientProgram = $_.Program
        $_ | Get-NetFirewallRule |
            Select-Object Name, DisplayName, Enabled, Direction, Action, Profile,
                @{Name='Program'; Expression={$clientProgram}}
    }
```

检查准确路径、启用状态、入站方向、Allow/Block、适用网络类型；需要核实 TCP/UDP、
端口及地址限制时，再用目标规则的 Get-NetFirewallPortFilter /
Get-NetFirewallAddressFilter 查询。存在适用的阻止规则或策略限制时，不能只凭
Allow 条目保证通行。查询拒绝或结果缺失表示未核实，不表示没有规则；可按工具
权限流程执行同一只读查询。防火墙状态不证明资源有种、外网可达或已经开始传输。

当前路径与网络类型已有有效放行且没有已知待处理弹窗时，沿用现有配置继续。
不要重新索要逐次下载许可。只有旧路径规则、适用类型不匹配或实际弹窗仍在时，
说明具体差异。已有用户授权的环境修复在其范围内执行；没有授权时，将修改
哪一个程序及哪些网络类型说明清楚后再取得授权。不要把允许自动下载扩展为
关闭整个防火墙、放行所有程序／网络类型或自动开启 Web UI。

环境修复后读回规则。不能声称改了 skill 就等于系统已配置完成，也不能承诺
软件更新、路径／网络类型或策略改变后永不提示。无真实传输验证时明确验证边界。

## 回执与恢复

保持三个状态独立：客户端接受任务、实际传输、下载完成。metadata/fastresume
回执及进度提交只能证明交付；防火墙弹窗不自动撤销已接受回执，也不证明下载
必然失败。没有传输证据只报告“已加入 qBittorrent”，不要报告“已开始下载”。
阻塞无人值守时简短报告具体待处理环境事项，不归类为资源未更新。

存在未完成 operation 时，环境问题解决后按 failure-recovery.md 恢复同一
operation_id/info_hash；已有已提交回执则检查原任务，不重新下载或回退进度。
单纯防火墙问题不创建四小时资源补查，不用反复启动客户端代替环境修复。

Windows 规则行为参考：
[Microsoft Learn — Windows Firewall rules](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules)。
独立启动依据：
[Microsoft Learn — Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
说明通过 `Win32_Process.Create` 创建的进程不继承调用方 Job。
