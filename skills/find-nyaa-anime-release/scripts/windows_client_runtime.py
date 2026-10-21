"""Current-session discovery and local WMI launch for a persistent desktop client.

WMI owns creation, so the client does not inherit the command runner's job.
This does not elevate, impersonate, change sessions or install a service/task.
Call only after the existing normal-user execution-context check.
"""
from __future__ import annotations

import base64
import ctypes
import json
import subprocess
from ctypes import wintypes


class RuntimeErrorWithCode(RuntimeError):
    def __init__(self, message, code="client_runtime_unverified", **diagnostics):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def _powershell_json(script, *, timeout=15):
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeErrorWithCode("Cannot query the Windows desktop runtime.") from exc
    if result.returncode != 0:
        # Do not expose a full command line (it may include a magnet).
        raise RuntimeErrorWithCode("Windows desktop runtime query failed.",
                                   runtime_exit_code=result.returncode)
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeErrorWithCode("Windows desktop runtime returned invalid data.") from exc


def processes():
    """Return qB processes in this session; inaccessible paths fail closed."""
    result = _powershell_json(r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$session = (Get-Process -Id $PID).SessionId
$items = @(Get-Process -Name qbittorrent -ErrorAction SilentlyContinue |
    Where-Object { $_.SessionId -eq $session } |
    ForEach-Object {
        if (-not $_.Path) { throw 'Process path unavailable' }
        @{pid=$_.Id; path=$_.Path; session_id=$_.SessionId}
    })
ConvertTo-Json -InputObject $items -Compress
""")
    if not isinstance(result, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("pid"), int)
        or not isinstance(row.get("path"), str) or not row["path"]
        for row in result
    ):
        raise RuntimeErrorWithCode("Cannot verify current-session qBittorrent paths.")
    return result


def executable_versions(paths):
    """Read numeric file versions afresh; never rank by path or modification date."""
    payload = base64.b64encode(json.dumps([str(p) for p in paths]).encode("utf-8")).decode("ascii")
    result = _powershell_json(r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$paths = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('""" + payload + r"""')) | ConvertFrom-Json
$items = @($paths | ForEach-Object {
    $info = [Diagnostics.FileVersionInfo]::GetVersionInfo($_)
    if (-not $info.FileVersion) { throw 'Missing file version' }
    @{path=$_; version=@($info.FileMajorPart,$info.FileMinorPart,$info.FileBuildPart,$info.FilePrivatePart)}
})
ConvertTo-Json -InputObject $items -Depth 4 -Compress
""")
    if not isinstance(result, list) or len(result) != len(paths):
        raise RuntimeErrorWithCode("Cannot verify all installed client versions.")
    versions = {}
    for row in result:
        version = row.get("version") if isinstance(row, dict) else None
        if (not isinstance(row.get("path") if isinstance(row, dict) else None, str)
                or not isinstance(version, list) or len(version) != 4
                or any(type(n) is not int or n < 0 for n in version)):
            raise RuntimeErrorWithCode("Invalid executable version data.")
        versions[row["path"].casefold()] = tuple(version)
    if set(versions) != {str(p).casefold() for p in paths}:
        raise RuntimeErrorWithCode("Executable version paths do not match discovery.")
    return versions


class BrokerProcess:
    """Small Popen-like observation handle; closing it never stops the client."""
    def __init__(self, pid):
        self.pid = pid
        self._handle = None
        self._exit_code = None
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        self._kernel = kernel
        self._handle = kernel.OpenProcess(0x00100000 | 0x1000, False, pid)
        # A fast IPC handoff may already have exited. Its exit is unknown, not 0.

    def poll(self):
        if self._exit_code is not None or not self._handle:
            return self._exit_code
        code = wintypes.DWORD()
        if self._kernel.GetExitCodeProcess(self._handle, ctypes.byref(code)):
            if code.value != 259:  # STILL_ACTIVE
                self._exit_code = code.value
        return self._exit_code

    def close(self):
        if self._handle:
            self._kernel.CloseHandle(self._handle)
            self._handle = None

    def __del__(self):
        self.close()


def launch(command):
    """Ask local WMI to create exactly this argv in the caller's user session."""
    from client_context import require_context, ClientContextError
    try:
        require_context()
    except ClientContextError as exc:
        raise RuntimeErrorWithCode(
            "Independent client launch requires the approved normal-user context.",
            exc.report["status"],
        ) from exc
    payload = base64.b64encode(
        subprocess.list2cmdline(command).encode("utf-8")
    ).decode("ascii")
    result = _powershell_json(r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$command = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('""" + payload + r"""'))
$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
$created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine=$command; ProcessStartupInformation=$startup
}
@{return_value=$created.ReturnValue; pid=$created.ProcessId} | ConvertTo-Json -Compress
""", timeout=20)
    if (not isinstance(result, dict) or result.get("return_value") != 0
            or not isinstance(result.get("pid"), int) or result["pid"] <= 0):
        code = result.get("return_value") if isinstance(result, dict) else None
        raise RuntimeErrorWithCode(
            "Independent desktop client launch failed; no direct-child fallback was attempted.",
            "client_independent_launch_failed", wmi_return_value=code,
        )
    return BrokerProcess(int(result["pid"]))
