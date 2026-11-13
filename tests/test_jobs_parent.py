"""규칙 4b(venv 중계기 중복)·4c(claude.exe의 직계 자식 = MCP 서버) — 순수 classify만 본다."""
import pytest

import config
import jobs

pytestmark = pytest.mark.skipif(not config.IS_WIN, reason="Windows 경로 전제 — 맥·리눅스는 test_posix.py")


NOW = 1_800_000_000.0
PROJECTS = ["paper-search", "potts-annealer"]
MCP_CMD = [r"C:/dev/paper-search/.venv/Scripts/python.exe", "-m", "paper_search.server"]


def proc(pid, name, cmdline, cwd=r"C:\dev\paper-search", age=3600):
    return {"pid": pid, "name": name, "exe": r"C:\x\%s" % name, "cmdline": cmdline,
            "cwd": cwd, "create_time": NOW - age}


def test_direct_child_of_claude_is_mcp_helper():
    claude = proc(1, "claude.exe", ["claude.exe"])
    server = proc(2, "python.exe", MCP_CMD)
    assert jobs.classify(server, 0, PROJECTS, NOW, claude) == ("helper", None)


def test_venv_redirector_child_with_same_cmdline_is_dup():
    redirector = proc(2, "python.exe", MCP_CMD)
    real = proc(3, "python.exe", MCP_CMD)
    assert jobs.classify(real, 0, PROJECTS, NOW, redirector) == ("dup", None)


def test_experiment_launched_through_a_shell_stays_a_job():
    """Claude의 명령 실행 도구는 셸을 거친다 — 그 아래 python 실험은 계속 보인다."""
    shell = proc(4, "powershell.exe", ["powershell.exe"])
    exp = proc(5, "python.exe", ["python.exe", "anneal.py"], cwd=r"C:\dev\potts-annealer")
    assert jobs.classify(exp, 0, PROJECTS, NOW, shell) == ("job", "potts-annealer")


def test_child_with_different_cmdline_is_not_dup():
    parent = proc(6, "python.exe", ["python.exe", "runner.py"])
    child = proc(7, "python.exe", ["python.exe", "worker.py"])
    assert jobs.classify(child, 0, PROJECTS, NOW, parent) == ("job", "paper-search")


def test_no_parent_keeps_old_behaviour():
    assert jobs.classify(proc(8, "python.exe", MCP_CMD), 0, PROJECTS, NOW) == ("job", "paper-search")
