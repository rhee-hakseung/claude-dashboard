"""launch: wt 이스케이프(-d 폴더 포함)와 Popen 실패 감싸기. 실제로 아무것도 띄우지 않는다."""
import subprocess
import sys

import pytest

import launch

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용 (Win32·wt·PowerShell)")


@pytest.fixture
def wt_mode(monkeypatch):
    monkeypatch.setattr(launch, "_host", "wt")
    monkeypatch.setattr(launch, "_wt_path", r"C:\fake\wt.exe")


@pytest.fixture
def conhost_mode(monkeypatch):
    monkeypatch.setattr(launch, "_host", "conhost")
    monkeypatch.setattr(launch, "_wt_path", None)


def test_argv_wt_escapes_the_directory(wt_mode):
    argv = launch._argv(r"C:\dev\odd;name", "claude")
    assert argv[:5] == [r"C:\fake\wt.exe", "-w", "0", "-d", "C:\\dev\\odd\\;name"]


def test_argv_wt_escapes_quotes_in_directory(wt_mode):
    argv = launch._argv('C:\\dev\\q"uote', None)
    assert argv[4] == 'C:\\dev\\q\\"uote'


def test_argv_conhost_does_not_escape_the_directory(conhost_mode):
    argv = launch._argv(r"C:\dev\odd;name", None)
    assert not any(";" in a and "\\;" in a for a in argv)


def test_spawn_wraps_oserror_as_launch_failed(conhost_mode, monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError(2, "no such file")

    monkeypatch.setattr(subprocess, "Popen", boom)
    with pytest.raises(launch.LaunchFailed) as err:
        launch._spawn(["nope.exe"])
    assert isinstance(err.value, OSError) and "실행 실패" in str(err.value)


def test_child_env_strips_claude_session_markers():
    # 물려받으면 새 claude가 자신을 자식 세션으로 오인해 transcript를 저장하지 않는다(실측).
    env = {"CLAUDECODE": "1", "CLAUDE_CODE_CHILD_SESSION": "1", "CLAUDE_PID": "5",
           "CLAUDE_CONFIG_DIR": "x", "PATH": "p"}
    assert launch._child_env(env) == {"CLAUDE_CONFIG_DIR": "x", "PATH": "p"}


def test_open_explorer_argv_is_list_form_without_shell(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: calls.append((argv, kw)))
    monkeypatch.setenv("CLAUDECODE", "1")
    launch.open_explorer(str(tmp_path) + "/")
    (argv, kw), = calls
    assert argv == [launch.config.EXPLORER_EXE, str(tmp_path)]
    assert argv[0].lower().endswith("\\explorer.exe")
    assert kw["shell"] is False and kw["close_fds"] is True and "CLAUDECODE" not in kw["env"]


def test_open_explorer_missing_folder_does_not_spawn(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: calls.append(a))
    gone = str(tmp_path / "gone")
    with pytest.raises(launch.LaunchFailed) as err:
        launch.open_explorer(gone)
    assert str(err.value) == "폴더가 없습니다: %s" % gone and calls == []


def test_open_explorer_wraps_oserror(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise PermissionError(5, "denied")

    monkeypatch.setattr(subprocess, "Popen", boom)
    with pytest.raises(launch.LaunchFailed):
        launch.open_explorer(str(tmp_path))


def test_spawn_wraps_valueerror_as_launch_failed(conhost_mode, monkeypatch):
    def boom(*a, **kw):
        raise ValueError("bad argv")

    monkeypatch.setattr(subprocess, "Popen", boom)
    with pytest.raises(launch.LaunchFailed):
        launch._spawn([""])


def test_open_attach_runs_claude_attach_with_short_id(wt_mode, monkeypatch):
    calls = []
    monkeypatch.setattr(launch, "_spawn", lambda argv, cwd=None: calls.append((argv, cwd)))
    launch.open_attach(r"C:\dev\potts-annealer", "0a1b2c3d-1111-2222-3333-444444444444")
    argv, cwd = calls[0]
    assert cwd == r"C:\dev\potts-annealer"
    assert argv[-1].endswith("claude attach 0a1b2c3d") and "--resume" not in " ".join(argv)
