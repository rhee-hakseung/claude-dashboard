"""새 화면의 진입점: 전용 창(pywebview — Windows는 WebView2, macOS는 WKWebView) 하나에 `web/index.html`을 띄운다.

수집은 `web_hub.Hub`가, 버튼은 `web_api.Api`가 한다. 이 파일은 창만 다룬다: 위치·크기 복원/저장,
작업 표시줄 아이콘, 닫기. ✕는 저장 후 닫을 뿐 어떤 세션도 건드리지 않는다(SI-8).
쓰기는 state.json과 WebView2 자료 폴더(`<상태 폴더>/webview`)뿐이다.
Windows는 Win32로 창 자리를 정확히 다루고(win_window), 다른 OS는 pywebview가 주는 값만 쓴다.
"""
from __future__ import annotations

import logging
import os

import webview

import config
import prefs
import term
import web_api
import web_hub

if config.IS_WIN:
    import win_window

log = logging.getLogger("dev-dashboard")
INDEX = os.path.join(config.OWN_DIR, "web", "index.html")
DEFAULT_SIZE = (1240, 860)
MIN_SIZE = (560, 420)


def placement():
    """저장된 창 자리 `[x, y, w, h]`. 없거나 어느 모니터에도 충분히 안 보이면 None(가운데)."""
    g = prefs.read_state().get("window")
    try:
        g = [int(v) for v in g] if len(g) == 4 else None
    except (TypeError, ValueError):
        return None
    ok = g and g[2] >= MIN_SIZE[0] and g[3] >= MIN_SIZE[1] and term.visible_enough(*g)
    return g if ok else None


def _save_portable(win):
    """Windows 밖: pywebview가 아는 위치·크기를 그대로 저장한다(맥은 논리 좌표 = 배율 없음)."""
    try:
        g = [int(win.x), int(win.y), int(win.width), int(win.height)]
        if g[2] >= MIN_SIZE[0] and g[3] >= MIN_SIZE[1]:
            prefs.save_state(window=g)
    except Exception:
        log.exception("save placement")


def open_window(hub):
    """창 하나를 만든다(아직 띄우진 않는다 — `webview.start`가 띄운다). 저장된 자리가 있으면 그리로."""
    g = placement()
    s = win_window.scale() if config.IS_WIN else 1.0
    where = dict(x=int(g[0] / s), y=int(g[1] / s), width=int(g[2] / s), height=int(g[3] / s)) if g \
        else dict(width=DEFAULT_SIZE[0], height=DEFAULT_SIZE[1])       # 자리가 없으면 pywebview가 가운데에 둔다
    dark = hub.prefs.theme == "dark"
    win = webview.create_window(config.APP_TITLE, url=INDEX, js_api=web_api.Api(hub), min_size=MIN_SIZE,
                                background_color="#0e1014" if dark else "#f4f5f8", **where)
    if config.IS_WIN:
        win.events.shown += lambda: (win_window.set_icon(win), win_window.restore_placement(win, g))
        win.events.closing += lambda: win_window.save_placement(win)
    else:
        win.events.closing += lambda: _save_portable(win)
    return win


def main():
    logging.basicConfig(level=logging.WARNING)   # stderr 전용 — 파일을 만들지 않는다
    if config.IS_WIN:
        win_window.set_app_id()
    hub = web_hub.Hub()
    hub.start()
    open_window(hub)
    try:
        webview.start(private_mode=False, storage_path=os.path.join(config.STATE_DIR, "webview"))
    finally:
        hub.stop.set()


if __name__ == "__main__":
    main()
