"""Read the Windows execution token before touching a desktop client.

This is a routing guard, not an authorization mechanism. It never impersonates,
elevates, changes permissions, or launches the client in another session.
"""
import os


class ClientContextError(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report['reason'])


def windows_identity():
    """Use native token APIs, not inherited USERNAME/USERPROFILE environment values."""
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi.GetUserNameW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    advapi.GetUserNameW.restype = wintypes.BOOL
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.IsTokenRestricted.argtypes = [wintypes.HANDLE]
    advapi.IsTokenRestricted.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    length = wintypes.DWORD(32768)
    name = ctypes.create_unicode_buffer(length.value)
    if not advapi.GetUserNameW(name, ctypes.byref(length)):
        raise ctypes.WinError(ctypes.get_last_error())
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        restricted = bool(advapi.IsTokenRestricted(token))
    finally:
        kernel.CloseHandle(token)
    return {'account': name.value, 'restricted_token': restricted}


def inspect_context(*, executable=None):
    if os.name != 'nt':
        return {'status': 'not_applicable', 'ok': True, 'platform': os.name}
    try:
        identity = windows_identity()
    except OSError as exc:
        return {'status': 'client_context_unverified', 'ok': False,
                'reason': 'Cannot inspect the Windows execution token.',
                'probe_error': str(exc), 'action': 'inspect_execution_context'}
    account = identity['account'].casefold()
    sandbox_account = any(part.startswith('codexsandbox')
                          for part in account.replace('/', '\\').split('\\'))
    if (sandbox_account or identity['restricted_token']) and executable is not None:
        try:
            from pathlib import Path
            known = {str(Path(p).resolve()).casefold()
                     for p in (r'C:\Apps\Tools\qBittorrent\qbittorrent.exe',
                               r'C:\Program Files\qBittorrent\qbittorrent.exe',
                               r'C:\Program Files (x86)\qBittorrent\qbittorrent.exe')}
            if str(Path(executable).resolve()).casefold() not in known:
                return {'status': 'client_context_ready', 'ok': True, **identity,
                        'scope': 'custom-executable-test-or-operator-path'}
        except OSError:
            pass
    if sandbox_account or identity['restricted_token']:
        return {'status': 'client_context_required', 'ok': False, **identity,
                'reason': 'Desktop qBittorrent delivery requires the owning normal-user execution context.',
                'action': 'run_full_resolver_in_approved_user_context',
                'requires_execution_tool_approval': True,
                'client_attempted': False, 'submission_attempts': 0}
    return {'status': 'client_context_ready', 'ok': True, **identity,
            'scope': 'execution_token_only_not_client_acceptance'}


def require_context():
    report = inspect_context()
    if not report['ok']:
        raise ClientContextError(report)
    return report
