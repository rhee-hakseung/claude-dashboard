"""순수 함수 테스트: jobs.classify / format_elapsed, launch._argv.
psutil도 Popen도 부르지 않는다(sys.path는 conftest.py가 잡는다)."""
import os

import pytest

import config
import jobs
import launch

# Windows 경로(C:\dev …)·wt·Win32를 전제한 표다. 맥·리눅스 쪽은 test_posix.py가 본다.
pytestmark = pytest.mark.skipif(not config.IS_WIN, reason="Windows 전용")

PROJECTS = ["potts-annealer", "myproj", "dev-dashboard", jobs.ROOT_KEY]
NOW = 1_000_000.0
OWN_PID = 999


def info(**kw):
    base = {"pid": 4242, "name": "python.exe", "exe": r"C:\Python313\python.exe",
            "cmdline": ["python.exe", "run.py"], "cwd": r"C:\dev\potts-annealer",
            "create_time": NOW - 3600}
    base.update(kw)
    return base


def cls(**kw):
    return jobs.classify(info(**kw), OWN_PID, PROJECTS, NOW)


def test_self_by_pid():
    assert cls(pid=OWN_PID) == ("self", None)


def test_self_by_cmdline():
    # 설치 폴더 이름은 clone한 이름(claude-dashboard 등)일 수 있다 — 실제 자기 폴더 이름으로 만든다
    own = os.path.basename(config.OWN_DIR)
    assert cls(cmdline=["python.exe", "C:\\dev\\%s\\app.py" % own]) == ("self", None)


@pytest.mark.parametrize("name", ["powershell.exe", "PowerShell.exe", "claude.exe",
                                  "WindowsTerminal.exe", "git.exe", "cmd.exe",
                                  "wsl.exe", "wslhost.exe", "WSLRelay.exe"])
def test_shell_names(name):
    assert cls(name=name) == ("shell", None)


def test_helper_exe_under_claude_home():
    exe = os.path.join(config.CLAUDE_HOME, "local", "node.exe")
    assert cls(name="node.exe", exe=exe) == ("helper", None)


def test_helper_exe_under_node_modules():
    assert cls(exe=r"C:\dev\myproj\NODE_MODULES\.bin\tsserver.exe") == ("helper", None)


def test_helper_node_stdio():
    assert cls(name="node.exe", exe=r"C:\Program Files\nodejs\node.exe",
               cmdline=["node.exe", "server.js", "--stdio"]) == ("helper", None)


def test_plain_node_in_project_is_job():
    assert cls(name="node.exe", exe=r"C:\Program Files\nodejs\node.exe",
               cmdline=["node.exe", "build.js"]) == ("job", "potts-annealer")


def test_cwd_outside_dev_root_excluded():
    assert cls(cwd=r"C:\Users\USER\scratch") == ("excluded", None)


def test_cwd_is_dev_root_is_root_project():
    assert cls(cwd="C:\\dev\\") == ("job", jobs.ROOT_KEY)


def test_cwd_under_own_dir_excluded():
    assert cls(cwd=r"C:\dev\dev-dashboard\tests") == ("excluded", None)


def test_cwd_under_hidden_folder_excluded():
    assert cls(cwd=r"C:\dev\myproj\node_modules\x") == ("excluded", None)


def test_young_bound_is_closed():
    assert cls(create_time=NOW - 59)[0] == "young"
    assert cls(create_time=NOW - 60) == ("job", "potts-annealer")


@pytest.mark.parametrize("seconds,text", [(60, "1분"), (12 * 60, "12분"),
                                          (3900, "1시간 5분"), (2 * 86400 + 3 * 3600, "2일 3시간")])
def test_format_elapsed(seconds, text):
    assert jobs.format_elapsed(seconds) == text


def test_display():
    assert jobs.display({"name": "python.exe", "elapsed": 3900}) == "▶ python.exe 1시간 5분"


# ── launch._argv ────────────────────────────────────────────────────────────
BODY, PROJ = 'claude --resume a;b "q"', r"C:\dev\my proj"


@pytest.fixture
def wt_mode(monkeypatch):
    monkeypatch.setattr(launch, "_host", "wt")
    monkeypatch.setattr(launch, "_wt_path", r"C:\fake\wt.exe")


@pytest.fixture
def conhost_mode(monkeypatch):
    monkeypatch.setattr(launch, "_host", "conhost")
    monkeypatch.setattr(launch, "_wt_path", None)


def test_argv_wt_escapes_and_shape(wt_mode):
    argv = launch._argv(PROJ, BODY)
    assert argv[:5] == [r"C:\fake\wt.exe", "-w", "0", "-d", PROJ]
    assert argv[5] == config.POWERSHELL_EXE
    assert argv[-2] == "-Command"
    assert argv[-1] == 'claude --resume a\\;b \\"q\\"'


def test_argv_conhost_is_bare(conhost_mode):
    argv = launch._argv(PROJ, BODY)
    assert argv[0] == config.POWERSHELL_EXE
    assert argv[-1] == BODY
    assert not any("wt.exe" in a.lower() for a in argv)


@pytest.mark.parametrize("mode", ["wt_mode", "conhost_mode"])
def test_powershell_button_has_no_command(mode, request):
    request.getfixturevalue(mode)
    argv = launch._argv(PROJ, None)
    assert "-Command" not in argv
    assert argv[-2:] == ["-NoLogo", "-NoExit"]
