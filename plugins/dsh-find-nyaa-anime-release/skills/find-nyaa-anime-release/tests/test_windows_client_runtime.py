import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import qbittorrent_submit as qbt
import windows_client_runtime as runtime


def test_running_installation_wins_over_old_known_install(tmp_path):
    current = tmp_path / "current.exe"
    old = tmp_path / "old.exe"
    current.touch()
    old.touch()
    with (patch.dict(os.environ, {}, clear=True),
          patch.object(qbt, "_desktop_processes", return_value=[{"path": str(current), "pid": 12}]),
          patch.object(qbt, "KNOWN_EXECUTABLES", (old,)),
          patch.object(qbt, "_registry_executables", return_value=[old]),
          patch.object(qbt.shutil, "which", return_value=None),
          patch.object(runtime, "executable_versions", return_value={
              str(current.resolve()).casefold(): (5, 2, 4, 0),
              str(old.resolve()).casefold(): (5, 2, 3, 0)}),
          patch.object(qbt.os, "name", "nt")):
        assert qbt.find_executable() == current.resolve()


def test_configured_missing_installation_does_not_silently_fallback(tmp_path):
    with pytest.raises(qbt.SubmissionError, match="refusing to switch"):
        qbt.find_executable(tmp_path / "missing.exe")


def test_multiple_active_installations_are_a_conflict(tmp_path):
    with (patch.dict(os.environ, {}, clear=True),
          patch.object(qbt.os, "name", "nt"),
          patch.object(qbt, "_desktop_processes", return_value=[
              {"path": str(tmp_path / "a.exe")}, {"path": str(tmp_path / "b.exe")}])):
        with pytest.raises(qbt.SubmissionError) as error:
            qbt.find_executable()
    assert error.value.code == "client_installation_conflict"


def test_registry_installation_precedes_legacy_portable_path(tmp_path):
    registered = tmp_path / "registered.exe"
    portable = tmp_path / "portable.exe"
    registered.touch()
    portable.touch()
    with (patch.dict(os.environ, {}, clear=True),
          patch.object(qbt, "_desktop_processes", return_value=[]),
          patch.object(qbt, "_registry_executables", return_value=[registered]),
          patch.object(qbt, "KNOWN_EXECUTABLES", (portable,)),
          patch.object(runtime, "executable_versions", return_value={
              str(registered.resolve()).casefold(): (5, 2, 4, 0),
              str(portable.resolve()).casefold(): (5, 2, 3, 0)}),
          patch.object(qbt.shutil, "which", return_value=None)):
        assert qbt.find_executable() == registered.resolve()


def test_newer_portable_beats_running_registered_version_and_detects_updates(tmp_path):
    registered, portable = tmp_path / "registered.exe", tmp_path / "portable.exe"
    registered.touch()
    portable.touch()
    versions = {str(registered.resolve()).casefold(): (5, 9, 0, 0),
                str(portable.resolve()).casefold(): (5, 10, 0, 0)}
    with (patch.dict(os.environ, {}, clear=True),
          patch.object(qbt, "_desktop_processes", return_value=[{"path": str(registered)}]),
          patch.object(qbt, "_registry_executables", return_value=[registered]),
          patch.object(qbt, "KNOWN_EXECUTABLES", (portable,)),
          patch.object(qbt.shutil, "which", return_value=None),
          patch.object(runtime, "executable_versions", return_value=versions) as read):
        assert qbt.find_executable() == portable.resolve()
        with pytest.raises(qbt.SubmissionError) as error:
            qbt.qbittorrent_process_running(portable)
        assert error.value.code == "client_installation_conflict"
        versions[str(registered.resolve()).casefold()] = (6, 0, 0, 0)
        assert qbt.find_executable() == registered.resolve()
        assert read.call_count == 2


def test_equal_versions_prefer_running_copy(tmp_path):
    first, active = tmp_path / "first.exe", tmp_path / "active.exe"
    first.touch()
    active.touch()
    with (patch.dict(os.environ, {}, clear=True),
          patch.object(qbt, "_desktop_processes", return_value=[{"path": str(active)}]),
          patch.object(qbt, "_registry_executables", return_value=[first]),
          patch.object(qbt, "KNOWN_EXECUTABLES", ()),
          patch.object(qbt.shutil, "which", return_value=None),
          patch.object(runtime, "executable_versions", return_value={
              str(first.resolve()).casefold(): (5, 3, 0, 0),
              str(active.resolve()).casefold(): (5, 3, 0, 0)})):
        assert qbt.find_executable() == active.resolve()


def test_unknown_version_does_not_silently_select_old_copy(tmp_path):
    exe = tmp_path / "qbittorrent.exe"
    exe.touch()
    with (patch.dict(os.environ, {}, clear=True),
          patch.object(qbt, "_desktop_processes", return_value=[]),
          patch.object(qbt, "_registry_executables", return_value=[exe]),
          patch.object(qbt, "KNOWN_EXECUTABLES", ()),
          patch.object(qbt.shutil, "which", return_value=None),
          patch.object(runtime, "executable_versions",
                       side_effect=runtime.RuntimeErrorWithCode("unreadable"))):
        with pytest.raises(qbt.SubmissionError) as error:
            qbt.find_executable()
    assert error.value.code == "executable_version_unverified"


def test_broker_failure_never_falls_back_to_direct_client_launch():
    with (patch.object(qbt.os, "name", "nt"),
          patch.object(runtime, "_powershell_json", return_value={"return_value": 2, "pid": 0}),
          patch.object(qbt.subprocess, "Popen") as direct):
        with pytest.raises(qbt.SubmissionError) as error:
            qbt._launch(["qbittorrent.exe"])
    assert error.value.code == "client_independent_launch_failed"
    assert error.value.retryable is False
    direct.assert_not_called()


def test_broker_preserves_argv_without_executing_shell_syntax():
    command = [r"C:\Apps with spaces\qbittorrent.exe",
               r"--save-path=C:\文件夹 with spaces",
               "magnet:?xt=test&dn=`$(write-host bad);'\"end"]
    with (patch.object(runtime, "_powershell_json", return_value={"return_value": 0, "pid": 123}) as call,
          patch.object(runtime, "BrokerProcess", return_value=Mock(pid=123))):
        runtime.launch(command)
    script = call.call_args.args[0]
    encoded = script.split("FromBase64String('", 1)[1].split("')", 1)[0]
    assert base64.b64decode(encoded).decode("utf-8") == subprocess.list2cmdline(command)
    assert command[-1] not in script


def test_invalid_process_inventory_is_not_assumed_empty():
    with patch.object(runtime, "_powershell_json", return_value=[{"pid": 10, "path": None}]):
        with pytest.raises(runtime.RuntimeErrorWithCode):
            runtime.processes()


def test_restricted_context_cannot_use_broker_as_fallback():
    import client_context
    report = {"status": "client_context_required", "reason": "restricted context"}
    with (patch.object(client_context, "require_context",
                       side_effect=client_context.ClientContextError(report)),
          patch.object(runtime, "_powershell_json") as call):
        with pytest.raises(runtime.RuntimeErrorWithCode) as error:
            runtime.launch(["qbittorrent.exe"])
    assert error.value.code == "client_context_required"
    call.assert_not_called()


def test_client_status_never_launches_or_inspects_downloads(tmp_path, capsys):
    with (patch.object(qbt, "find_executable", return_value=tmp_path / "qbittorrent.exe"),
          patch.object(qbt, "qbittorrent_process_running", return_value=False),
          patch.object(qbt, "_launch") as launch,
          patch.object(qbt, "submit_magnet") as submit):
        assert qbt.main(["--client-status", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["client_attempted"] is False
    assert report["transfer_state"] == "not_observed"
    launch.assert_not_called()
    submit.assert_not_called()


@pytest.mark.skipif(os.name != "nt" or os.environ.get("ANIME_TEST_DESKTOP_RUNTIME") != "1",
                    reason="Explicit opt-in: benign Windows process lifecycle test")
def test_broker_child_survives_launcher_job_termination(tmp_path):
    """Kill only our own disposable launcher job; the fake client must finish."""
    import ctypes
    from ctypes import wintypes
    import time

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    ready, start, done = (tmp_path / name for name in ("ready.json", "start", "done"))
    fake = tmp_path / "fake.py"
    fake.write_text("import time,pathlib,sys\n"
                    "time.sleep(2)\npathlib.Path(sys.argv[1]).write_text('survived')\n",
                    encoding="utf-8")
    worker = tmp_path / "worker.py"
    worker.write_text(
        "import sys,time,json,pathlib\n"
        f"sys.path.insert(0,{str(Path(runtime.__file__).parent)!r})\n"
        "from windows_client_runtime import launch\n"
        f"start=pathlib.Path({str(start)!r})\n"
        "deadline=time.monotonic()+15\n"
        "while not start.exists() and time.monotonic()<deadline: time.sleep(.05)\n"
        "if not start.exists(): sys.exit(2)\n"
        f"p=launch([sys.executable,{str(fake)!r},{str(done)!r}])\n"
        f"pathlib.Path({str(ready)!r}).write_text(json.dumps({{'pid':p.pid}}))\n"
        "time.sleep(15)\n", encoding="utf-8")
    job = kernel.CreateJobObjectW(None, None)
    assert job
    launcher = subprocess.Popen([sys.executable, str(worker)],
                                creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(launcher._handle)))
        start.touch()
        deadline = time.monotonic() + 12
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists(), "Broker did not start the fake client"
        assert not done.exists(), "Fake client must still be alive when the launcher is killed"
        assert kernel.TerminateJobObject(job, 123)
        assert launcher.wait(timeout=3) == 123
        deadline = time.monotonic() + 5
        while not done.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert done.read_text() == "survived"
    finally:
        if launcher.poll() is None:
            launcher.terminate()
            launcher.wait(timeout=3)
        kernel.CloseHandle(job)
