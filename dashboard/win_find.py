"""[점프] 대상 창 해소와 모니터 사각형. ctypes만 쓴다(pywin32 불필요).

SI-7: hwnd를 어디에도 저장하지 않는다. 탭을 떼거나 합치면 100 ms 안에 호스트 창이 바뀌는데,
캐시된 hwnd는 실패하지 않고 '엉뚱한 창을 성공적으로' 앞에 가져온다 — 조용히 틀리는 최악의
실패 모드다. 그래서 매 호출마다 pid에서 다시 해소한다. 저장해도 되는 것은 pid뿐이다.
포그라운드 전환은 win_focus.py에 있다.
"""
import ctypes
import ctypes.wintypes as wt

import psutil

import config

_u32 = ctypes.WinDLL("user32", use_last_error=True)

GW_OWNER = 4
GA_ROOTOWNER = 3
_PSEUDO = "PseudoConsoleWindow"    # WT: 이 창의 pid == 셸 pid, 소유자가 보이는 호스트 창
_CONHOST = "ConsoleWindowClass"    # 고전 콘솔: 이 창 자체가 호스트이고 pid == 셸 pid

_ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_MONPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC,
                              ctypes.POINTER(wt.RECT), wt.LPARAM)


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


for _f in (_u32.GetWindow, _u32.GetAncestor):
    _f.restype = wt.HWND           # 기본 restype(c_int)은 64비트 핸들을 잘라먹는다
    _f.argtypes = [wt.HWND, wt.UINT]
_u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_u32.GetWindowThreadProcessId.restype = wt.DWORD
_u32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_u32.IsWindowVisible.argtypes = [wt.HWND]


def _class_of(h):
    b = ctypes.create_unicode_buffer(256)
    _u32.GetClassNameW(h, b, 256)
    return b.value


def _pid_of(h):
    p = wt.DWORD()
    _u32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value


def _host_hwnd(shell_pid):
    """셸 pid → 보이는 호스트 창. EnumWindows 1회(실측 ≈1 ms)이고 프로세스 스냅샷은 쓰지 않는다
    (CreateToolhelp32Snapshot은 14 ms — 점프 경로에서 금지)."""
    hit = []

    def cb(h, _l):
        cls = _class_of(h)
        if cls in (_PSEUDO, _CONHOST) and _pid_of(h) == shell_pid:
            hit.append((cls, h))
            return False
        return True

    _u32.EnumWindows(_ENUMPROC(cb), 0)
    if not hit:
        return None
    cls, h = hit[0]
    if cls == _CONHOST:
        return int(h)
    owner = int(_u32.GetWindow(h, GW_OWNER) or 0)
    if not owner:                                  # Paseo 등 외부 호스트는 소유자가 0이다
        owner = int(_u32.GetAncestor(h, GA_ROOTOWNER) or 0)
        if owner == int(h):
            owner = 0                              # 자기 자신 = 못 찾은 것
    if not owner or not _u32.IsWindowVisible(owner):
        return None
    return owner


def hwnd_for_pid(claude_pid):
    """claude pid → 부모 셸 pid → 호스트 창. 못 찾으면 한 단계만 더 거슬러 오른다
    (claude가 런처에 감싸인 경우). 상승은 2단계에서 멈춘다. 어떤 오류든 None."""
    try:
        child = psutil.Process(int(claude_pid))
        for _ in range(2):
            ppid = child.ppid()
            if not ppid:
                return None
            parent = psutil.Process(ppid)
            # pid 재사용 가드: 부모가 자식보다 늦게 생겼다면 기록된 ppid는 이미 재활용된
            # 번호다. 그 pid의 창을 앞에 가져오면 '엉뚱한 창을 성공적으로' 띄운다.
            if parent.create_time() > child.create_time():
                return None
            h = _host_hwnd(ppid)
            if h:
                return h
            child = parent
    except Exception:
        return None
    return None


def monitor_rects():
    """모든 모니터의 rcMonitor [(left, top, right, bottom), …].
    실측: {0,0,2560,1440} 주 모니터, {-2560,0,0,1440} 보조."""
    out = []

    def cb(hmon, _hdc, _rc, _l):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if _u32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcMonitor
            out.append((r.left, r.top, r.right, r.bottom))
        return True

    _u32.EnumDisplayMonitors(None, None, _MONPROC(cb), 0)
    return out


def primary_rect():
    """주 모니터는 정의상 가상 화면 원점 (0, 0)에서 시작한다."""
    rects = monitor_rects()
    for r in rects:
        if r[0] == 0 and r[1] == 0:
            return r
    return rects[0] if rects else (0, 0, 1920, 1080)


def _visible_enough(x, y, w, h):
    m = config.WINDOW_MIN_VISIBLE_PX
    for left, top, right, bottom in monitor_rects():
        if min(x + w, right) - max(x, left) >= m and min(y + h, bottom) - max(y, top) >= m:
            return True
    return False
