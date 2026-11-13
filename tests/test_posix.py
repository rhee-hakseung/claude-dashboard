"""맥(·리눅스) 쪽: procStart 해석, mac_term(터미널 열기·[점프]), launch의 OS 분기, 유닉스 경로 귀속.
osascript도 실제 프로세스도 부르지 않는다 — subprocess·psutil을 갈아 끼운다. 순수 함수는 어느 OS에서나 돈다."""
import json
import os
import subprocess
import sys

import psutil
import pytest

import collect_fs
import config
import launch
import mac_term

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="유닉스 경로 전제")
NOW = 1_700_000_000.0


# ── procStart ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw, want", [
    (str(int((NOW + collect_fs.FILETIME_EPOCH_DIFF) * 1e7)), NOW),   # Windows FILETIME 문자열
    (str(int(NOW * 1000)), NOW),                                      # 밀리초
    (NOW, NOW),                                                       # 초
])
def test_procstart_formats(raw, want):
    assert collect_fs.procstart_to_unix(raw, now=NOW + 10) == pytest.approx(want, abs=1e-3)


@pytest.mark.parametrize("raw", [None, "", "abc", "12345", "2026-11-12T00:00:00Z"])
def test_procstart_unknown_is_none(raw):
    """부팅 후 클록 틱처럼 그럴듯하지 않은 값은 None — 그때는 pid 생존만으로 판정한다."""
    assert collect_fs.procstart_to_unix(raw, now=NOW) is None


def test_registry_without_procstart_is_accepted_when_pid_alive(tmp_path):
    (tmp_path / "1.json").write_text(json.dumps({"pid": os.getpid(), "sessionId": "s", "status": "busy",
                                                 "cwd": "x"}), encoding="utf-8")
    accepted, rejected, failures = collect_fs.read_registry(str(tmp_path))
    assert (len(accepted), rejected, failures) == (1, 0, 0)


# ── mac_term ────────────────────────────────────────────────────────────────
def test_shell_line_quotes_folder():
    assert mac_term.shell_line("/a b/it's", "claude --resume x") == "cd '/a b/it'\"'\"'s' && claude --resume x"
    assert mac_term.shell_line("/plain", None) == "cd /plain"


class FakeProc:
    def __init__(self, name, tty=None, parents=()):
        self._name, self._tty, self._parents = name, tty, list(parents)

    def name(self):
        return self._name

    def terminal(self):
        return self._tty

    def parents(self):
        return self._parents


@pytest.fixture
def fake_tree(monkeypatch):
    def use(proc):
        monkeypatch.setattr(mac_term.psutil, "Process", lambda pid: proc)
    return use


def test_host_of_finds_terminal_ancestor(fake_tree):
    fake_tree(FakeProc("claude", "/dev/ttys003", [FakeProc("zsh"), FakeProc("login"), FakeProc("Terminal")]))
    assert mac_term.host_of(1) == ("Terminal", "/dev/ttys003")


def test_host_of_iterm(fake_tree):
    fake_tree(FakeProc("claude", "/dev/ttys009", [FakeProc("zsh"), FakeProc("iTerm2")]))
    assert mac_term.host_of(1) == ("iTerm2", "/dev/ttys009")


@pytest.mark.parametrize("proc", [
    FakeProc("claude", None, [FakeProc("Terminal")]),                     # tty 없음(백그라운드)
    FakeProc("claude", "/dev/ttys1; rm", [FakeProc("Terminal")]),         # 이상한 tty
    FakeProc("claude", "/dev/ttys004", [FakeProc("zsh"), FakeProc("Code Helper")]),   # 지원하지 않는 터미널
])
def test_host_of_none(fake_tree, proc):
    fake_tree(proc)
    assert mac_term.host_of(1) is None


def test_host_of_swallows_psutil_errors(monkeypatch):
    def gone(pid):
        raise psutil.NoSuchProcess(pid)
    monkeypatch.setattr(mac_term.psutil, "Process", gone)
    assert mac_term.host_of(1) is None and mac_term.can_jump(1) is False


def test_jump_passes_tty_as_argument(fake_tree, monkeypatch):
    fake_tree(FakeProc("claude", "/dev/ttys003", [FakeProc("Terminal")]))
    seen = []
    monkeypatch.setattr(mac_term.subprocess, "run",
                        lambda argv, **kw: seen.append(argv) or subprocess.CompletedProcess(argv, 0, "ok\n", ""))
    assert mac_term.jump(1) is True
    argv = seen[0]
    assert argv[0] == "osascript" and argv[-1] == "/dev/ttys003" and "/dev/ttys003" not in argv[2]


def test_jump_not_found_is_false(fake_tree, monkeypatch):
    fake_tree(FakeProc("claude", "/dev/ttys003", [FakeProc("Terminal")]))
    monkeypatch.setattr(mac_term.subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "none\n", ""))
    assert mac_term.jump(1) is False


@pytest.mark.parametrize("app", ["Terminal", "iTerm2", "Unknown"])
def test_open_terminal_argv(monkeypatch, app):
    seen = []
    monkeypatch.setattr(mac_term.config, "MAC_TERMINAL", app)
    monkeypatch.setattr(mac_term.subprocess, "Popen", lambda argv, **kw: seen.append(argv))
    mac_term.open_terminal("/p q", "claude", env={})
    argv = seen[0]
    assert argv[0] == "osascript" and argv[-1] == "cd '/p q' && claude"
    assert ('"iTerm2"' if app == "iTerm2" else '"Terminal"') in argv[2]


# ── launch의 맥 분기 ────────────────────────────────────────────────────────
@pytest.fixture
def as_mac(monkeypatch):
    monkeypatch.setattr(config, "IS_WIN", False)
    monkeypatch.setattr(config, "IS_MAC", True)
    calls = []
    monkeypatch.setattr(mac_term, "open_terminal", lambda d, body, env: calls.append((d, body, env)))
    return calls


def test_mac_new_claude_and_resume(as_mac):
    sid = launch.open_new_claude("/proj")
    launch.open_resume("/proj", "abc")
    launch.open_powershell("/proj")
    assert [(d, b) for d, b, _ in as_mac] == [("/proj", "claude --session-id " + sid),
                                               ("/proj", "claude --resume abc"), ("/proj", None)]
    assert not any(k.upper().startswith("CLAUDE_CODE_") for k in as_mac[0][2])


def test_mac_open_folder_uses_open(as_mac, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(launch.subprocess, "Popen", lambda argv, **kw: seen.append(argv))
    launch.open_explorer(str(tmp_path))
    assert seen == [["open", os.path.normpath(str(tmp_path))]]


def test_mac_launch_failure_is_launch_failed(as_mac, monkeypatch):
    def boom(*a):
        raise OSError("no osascript")
    monkeypatch.setattr(mac_term, "open_terminal", boom)
    with pytest.raises(launch.LaunchFailed):
        launch.open_powershell("/proj")


# ── 유닉스 경로 귀속·작업 분류 ──────────────────────────────────────────────
@posix_only
def test_attribute_cwd_posix():
    import paths
    assert paths.attribute_cwd("/dev-root") == paths.ROOT_KEY
    assert paths.attribute_cwd("/dev-root/proj/sub/") == "proj"
    assert paths.attribute_cwd("/elsewhere/proj") is None
    assert paths.slug("/Users/me/dev/my_proj") == "-Users-me-dev-my-proj"


@posix_only
@pytest.mark.parametrize("info, parent, want", [
    ({"name": "zsh"}, None, "shell"),
    ({"name": "node", "cmdline": ["node", "x.js", "--stdio"]}, None, "helper"),
    ({"name": "python3"}, {"name": "claude", "cmdline": ["claude"]}, "helper"),
    ({"name": "python3"}, {"name": "zsh", "cmdline": ["-zsh"]}, "job"),
])
def test_classify_posix(info, parent, want):
    import jobs
    base = {"pid": 5, "name": "python3", "exe": "/usr/bin/python3", "cmdline": ["python3", "run.py"],
            "cwd": "/dev-root/proj", "create_time": NOW - 3600}
    kind, _ = jobs.classify(dict(base, **info), 1, ["proj"], NOW, parent)
    assert kind == want
