"""Windows 전용: 대시보드 창 자리 복원·저장, 제목줄·작업 표시줄 아이콘, 작업 표시줄 묶음 id.

webapp.py가 Windows에서만 불러온다. pywebview의 창 핸들(hwnd)은 호출할 때마다 창 객체에서 다시
얻고 저장하지 않는다(SI-7과 같은 원칙).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os

import config
import prefs

log = logging.getLogger("dev-dashboard")
_u32 = ctypes.WinDLL("user32")   # 전용 인스턴스 — 공유 windll.user32의 argtypes를 건드리지 않는다
_u32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [ctypes.c_int] * 4 + [ctypes.c_uint]
_u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.RECT)]
_u32.IsIconic.argtypes = _u32.IsZoomed.argtypes = [ctypes.c_void_p]


def _hwnd(win):
    try:
        return int(win.native.Handle.ToInt64())
    except Exception:
        return 0


def scale():
    """시스템 배율(1.0 = 100%). pywebview는 만들 때 위치·크기에 배율을 곱한다(2026-11-12 실측:
    150%에서 x=80 → 실제 120) — 그래서 실제 픽셀 값을 넘길 땐 이 값으로 나눈다."""
    try:
        return max(1.0, _u32.GetDpiForSystem() / 96.0)
    except (AttributeError, OSError):
        return 1.0


def set_app_id():
    """없으면 pythonw.exe로 묶여 작업 표시줄에 Python 아이콘이 뜬다. 창을 만들기 전에 불러야 한다."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(config.APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


def restore_placement(win, g):
    """창이 뜬 직후 저장된 자리로 정확히 옮긴다 — pywebview의 배율 계산에 기대지 않는다."""
    hwnd = _hwnd(win)
    if hwnd and g:
        _u32.SetWindowPos(hwnd, None, g[0], g[1], g[2], g[3], 0x0004 | 0x0010)   # NOZORDER | NOACTIVATE


def set_icon(win):
    """제목줄·작업 표시줄 아이콘. 파일이 없거나 실패해도 창은 그대로 쓴다."""
    hwnd = _hwnd(win)
    if not hwnd or not os.path.isfile(config.APP_ICON):
        return
    _u32.LoadImageW.restype = ctypes.c_void_p
    _u32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    for which, px in ((0, 16), (1, 32)):          # ICON_SMALL, ICON_BIG
        icon = _u32.LoadImageW(None, config.APP_ICON, 1, px, px, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
        if icon:
            _u32.SendMessageW(hwnd, 0x0080, which, icon)                 # WM_SETICON


def save_placement(win):
    """닫을 때 위치·크기(실제 픽셀)를 저장한다. 최소화·최대화 상태의 좌표는 저장하지 않는다
    (다음에 엉뚱한 곳에 뜬다). 예전 화면의 `geometry` 키와 섞이지 않게 `window` 키를 쓴다."""
    hwnd = _hwnd(win)
    try:
        if not hwnd or _u32.IsIconic(hwnd) or _u32.IsZoomed(hwnd):
            return
        r = wt.RECT()
        if _u32.GetWindowRect(hwnd, ctypes.byref(r)):
            prefs.save_state(window=[r.left, r.top, r.right - r.left, r.bottom - r.top])
    except Exception:
        log.exception("save placement")
