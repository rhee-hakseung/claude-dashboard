"""[점프]의 포그라운드 전환과 사후 확인. 창 해소는 win_find.py가 한다.

실측: 잠금 화면이 아니면 그냥 SetForegroundWindow가 10/10 성공(최대 44 ms)했고,
최소화 상태와 보조 모니터도 포함된다. 잠금 화면에서는 0을 돌려주며 이때는 방법이 없다.
SI-7: 여기서도 hwnd를 저장하지 않는다 — 사후 확인은 pid에서 다시 해소해 판정한다.
"""
import ctypes
import ctypes.wintypes as wt

import win_find
import win_tabs

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

SW_RESTORE = 9
ASFW_ANY = -1

_u32.GetForegroundWindow.restype = wt.HWND     # 기본 restype은 64비트 핸들을 잘라먹는다
_u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_u32.GetWindowThreadProcessId.restype = wt.DWORD
for _f in (_u32.IsIconic, _u32.SetForegroundWindow):
    _f.argtypes = [wt.HWND]
_u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
_u32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]


def bring_to_front(hwnd):
    """AllowSetForegroundWindow → 최소화면 복원 → SetForegroundWindow, 실패 시 1회만 재시도."""
    try:
        _u32.AllowSetForegroundWindow(ASFW_ANY)
        if _u32.IsIconic(hwnd):
            _u32.ShowWindow(hwnd, SW_RESTORE)
        if _u32.SetForegroundWindow(hwnd):
            return True
        tid = _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wt.DWORD()))
        cur = _k32.GetCurrentThreadId()
        if not tid or tid == cur:
            return False
        _u32.AttachThreadInput(cur, tid, True)   # 입력 큐를 붙여 포그라운드 권한을 빌린다
        try:
            return bool(_u32.SetForegroundWindow(hwnd))
        finally:
            _u32.AttachThreadInput(cur, tid, False)
    except Exception:
        return False


def jump(claude_pid, tab_title=None):
    """해소 → (제목이 있으면) 탭 고르기 → 앞으로. `(쓴 hwnd | None, 탭 결과 문자열)`.

    탭을 **먼저** 고르고 창을 올린다 — 순서를 뒤집으면 엉뚱한 탭이 한 번 보였다가 바뀐다.
    탭 결과는 창 올리기의 성패와 무관하다(win_tabs.select_tab은 예외를 올리지 않는다).
    """
    hwnd = win_find.hwnd_for_pid(claude_pid)
    if not hwnd:
        return None, ""
    result = win_tabs.select_tab(hwnd, tab_title) if tab_title else ""
    return (hwnd if bring_to_front(hwnd) else None), result


def confirm_foreground(claude_pid):
    """사후 확인. sleep 하지 않는다 — UI가 root.after(config.JUMP_POSTCHECK_MS, …)로 부른다.
    점프 당시의 hwnd는 인자로도 받지 않는다 — 판정은 언제나 지금 다시 해소한 창으로 한다.
    그 사이 탭을 떼어 호스트 창이 바뀌었어도 pid 기준으로 맞으면 성공이다(SI-7)."""
    hwnd = win_find.hwnd_for_pid(claude_pid)
    if not hwnd:
        return False
    return hwnd == int(_u32.GetForegroundWindow() or 0)
