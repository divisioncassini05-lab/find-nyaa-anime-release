# 无人值守下载与 Windows 授权

首次配置自动下载、观察到系统弹窗，或可执行文件路径／Windows 用户／网络类型
变化时读取。正常运行沿用已核实环境和用户下载授权，不每集重复确认或要求截图。
仅查资源／磁力模式不要求客户端准备。维护验证不启动客户端或真实下载。

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
