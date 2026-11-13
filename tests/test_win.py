"""win_find.hwnd_for_pid의 부모 상승·pid 재사용 가드·SI-7(hwnd 무저장) 검증.
실제 창도 프로세스도 건드리지 않는다 — psutil.Process와 _host_hwnd를 갈아 끼운다."""
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용 (Win32·wt·PowerShell)")

if sys.platform == "win32":
    import win_find
    import win_focus

HWND = 0xBEEF1234          # 모듈 상수와 절대 겹치지 않는 값
CHILD, MID, TOP = 100, 200, 300


@pytest.fixture
def chain(monkeypatch):
    """pid → (ppid, create_time). 부모일수록 먼저 생겼다(정상 계보)."""
    table = {CHILD: (MID, 100.0), MID: (TOP, 50.0), TOP: (0, 10.0)}

    class FakeProc:
        def __init__(self, pid):
            if pid not in table:
                raise LookupError(pid)
            self.pid = pid

        def ppid(self):
            return table[self.pid][0]

        def create_time(self):
            return table[self.pid][1]

    monkeypatch.setattr(win_find.psutil, "Process", FakeProc)
    return table


def test_walk_resolves_at_second_level(chain, monkeypatch):
    monkeypatch.setattr(win_find, "_host_hwnd", lambda pid: HWND if pid == TOP else 0)
    assert win_find.hwnd_for_pid(CHILD) == HWND


def test_walk_resolves_at_first_level(chain, monkeypatch):
    monkeypatch.setattr(win_find, "_host_hwnd", lambda pid: HWND if pid == MID else 0)
    assert win_find.hwnd_for_pid(CHILD) == HWND


@pytest.mark.parametrize("miss", [0, None])
def test_none_when_no_host_window_at_either_level(chain, monkeypatch, miss):
    monkeypatch.setattr(win_find, "_host_hwnd", lambda pid: miss)
    assert win_find.hwnd_for_pid(CHILD) is None


def test_recycled_parent_pid_returns_none(monkeypatch):
    # 부모가 자식보다 늦게 생겼다 = 기록된 ppid가 재활용된 번호다.
    table = {CHILD: (MID, 100.0), MID: (TOP, 200.0), TOP: (0, 10.0)}

    class FakeProc:
        def __init__(self, pid):
            self.pid = pid

        def ppid(self):
            return table[self.pid][0]

        def create_time(self):
            return table[self.pid][1]

    monkeypatch.setattr(win_find.psutil, "Process", FakeProc)
    monkeypatch.setattr(win_find, "_host_hwnd", lambda pid: HWND)
    assert win_find.hwnd_for_pid(CHILD) is None


def test_unknown_pid_is_none(chain, monkeypatch):
    monkeypatch.setattr(win_find, "_host_hwnd", lambda pid: HWND)
    assert win_find.hwnd_for_pid(4242) is None


def test_si7_no_module_attribute_holds_the_hwnd(chain, monkeypatch):
    monkeypatch.setattr(win_find, "_host_hwnd", lambda pid: HWND if pid == TOP else 0)
    assert win_find.hwnd_for_pid(CHILD) == HWND
    for mod in (win_find, win_focus):
        ints = [v for v in vars(mod).values() if isinstance(v, int) and not isinstance(v, bool)]
        assert HWND not in ints
