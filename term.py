"""운영체제별 창 다루기의 단일 창구: [점프] 가능 여부, [점프], 사후 확인, 저장된 창 자리 검사.

Windows는 win_find·win_focus·win_tabs(Win32·UI Automation), macOS는 mac_term(AppleScript)을 쓴다.
그 밖의 OS(리눅스)는 [점프]를 지원하지 않는다 — 버튼만 꺼지고 나머지 기능은 그대로 돈다.
win_* 모듈은 Windows에서만 불러온다(Win32 DLL을 임포트 시점에 연다).
"""
from __future__ import annotations

import psutil

import config

if config.IS_WIN:
    import win_find
    import win_focus

    def can_jump(pid) -> bool:
        return win_find.hwnd_for_pid(pid) is not None

    def jump(pid, tab_title=None):
        """→ `(창을 올렸는가, 탭 결과 문자열)`. 탭 결과는 config.JUMP_TAB_MESSAGES의 키."""
        hwnd, tab = win_focus.jump(pid, tab_title)
        return bool(hwnd), tab

    def confirm(pid) -> bool:
        return win_focus.confirm_foreground(pid)

    def visible_enough(x, y, w, h) -> bool:
        return win_find._visible_enough(x, y, w, h)

elif config.IS_MAC:
    import mac_term

    can_jump = mac_term.can_jump

    def jump(pid, tab_title=None):
        return mac_term.jump(pid), ""

    def confirm(pid) -> bool:
        return True      # 맥은 AppleScript가 탭을 직접 골라 앞으로 가져온다 — 따로 확인하지 않는다

    def visible_enough(x, y, w, h) -> bool:
        return mac_term.visible_enough(x, y, w, h)

else:
    def can_jump(pid) -> bool:
        return False

    def jump(pid, tab_title=None):
        return False, ""

    def confirm(pid) -> bool:
        return True

    def visible_enough(x, y, w, h) -> bool:
        return True


def launcher_gone(pid) -> bool:
    """세션을 띄운 셸(부모 프로세스)이 이미 없는가. 터미널 창을 닫았는데 claude만 남은 경우를 알아본다.
    부모가 살아 있으면(VS Code 터미널처럼 창을 못 찾을 뿐인 경우) False다."""
    try:
        parent = psutil.Process(pid).parent()
    except psutil.Error:
        return False
    return parent is None or parent.pid <= 1     # 맥·리눅스는 고아가 pid 1 아래로 간다
