"""화면(JS)이 부르는 버튼 동작. 밑줄로 시작하지 않는 메서드만 화면에 노출된다(pywebview 규칙).

동작 자체는 예전 화면과 같은 모듈(launch·trash·term)을 쓴다. 세션을 멈추거나 끝내는 동작은
없다 — 창을 앞으로 가져오고, 새 탭을 열고, 사용자가 고른 기록을 휴지통으로 보낼 뿐이다.
[점프]는 스레드 하나(`_pool`)에서만 돈다: 탭 고르기(UIA/COM) 객체는 만든 스레드에서만 쓸 수 있다.
"""
from __future__ import annotations

import functools
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import config
import launch
import prefs
import term
import trash
import web_view

log = logging.getLogger("dev-dashboard")


def _action(fn):
    """실패는 예외가 아니라 상태 메시지로 알리고, 끝나면 화면을 바로 갱신한다."""
    @functools.wraps(fn)
    def run(self, *args):
        hub = self._hub
        try:
            with hub.lock:
                fn(self, *args)
        except (OSError, trash.TrashRefused) as err:
            hub.say(str(err))
        except Exception as err:
            log.exception("action %s", fn.__name__)
            hub.say("동작 실패: %s" % err)
        hub.tick()
        return True
    return run


class Api:
    def __init__(self, hub):
        self._hub = hub
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jump")

    def view(self, rev):
        return self._hub.changed_view(rev)

    def jump(self, sid):
        return self._pool.submit(self._jump, sid).result(timeout=20)

    @_action
    def _jump(self, sid):
        hub, s = self._hub, self._hub.live(sid)
        if s is None:
            return
        hub.hl.jump_clicked(sid)
        if s.background:        # 창이 없는 백그라운드 세션 — 새 탭에서 붙는다
            launch.open_attach(s.cwd, sid)
        elif s.desktop or s.orphan:   # Claude 앱 세션·창이 닫힌 세션 — 새 탭에서 이어 연다
            launch.open_resume(s.cwd, sid)
            hub.say(config.LABELS["orphan_jump" if s.orphan else "desktop_jump"] % web_view.live_label(s))
        else:
            ok, tab = term.jump(s.pid, s.tab_title)
            if not ok:
                hub.say("창을 찾을 수 없음")
                return
            hub.say(config.JUMP_TAB_MESSAGES.get(tab, ""))
            threading.Timer(config.JUMP_POSTCHECK_MS / 1000.0, self._postcheck, (s.pid,)).start()

    def _postcheck(self, pid):
        if not term.confirm(pid):
            self._hub.say("창을 확신할 수 없음")

    @_action
    def resume(self, path):
        hub, e = self._hub, self._hub.ended(path)
        if e is None or e.is_stub or e.duplicate_of_newer or not e.resume_dir:
            return
        hub.hl.mark_resuming(e.session_id, time.time())
        try:
            launch.open_resume(e.resume_dir, e.session_id)
        except OSError:
            hub.hl.clear_resuming(e.session_id)
            raise

    @_action
    def trash(self, path):
        hub, e = self._hub, self._hub.ended(path)
        if e is None or hub.hl.is_resuming(e.session_id, time.time()):
            return
        trash.send(e.path)
        hub.trashed.add(e.path)
        hub.say("휴지통으로 이동: %s" % e.title)

    @_action
    def new_claude(self, name):
        p = self._hub.project(name)
        if p is not None:
            self._hub.hl.mark_seen(launch.open_new_claude(p.path))

    @_action
    def powershell(self, name):
        p = self._hub.project(name)
        if p is not None:
            launch.open_powershell(p.path)

    @_action
    def explorer(self, name):
        p = self._hub.project(name)
        if p is not None:
            launch.open_explorer(p.path)

    @_action
    def rename(self, name, text):
        hub, p = self._hub, self._hub.project(name)
        if p is not None:
            plain = web_view.project_title(p, {})[0]
            hub.prefs.aliases = prefs.set_alias(hub.prefs.aliases, name, str(text), plain)
            hub.save("aliases")

    @_action
    def reorder(self, names):
        """화면에 보이는 순서 전체를 받는다. 지금 디스크에 없는 예전 이름은 지우지 않고 뒤에 남긴다."""
        hub = self._hub
        shown = list(dict.fromkeys(n for n in names if isinstance(n, str)))
        hub.prefs.order = shown + [n for n in hub.prefs.order if n not in set(shown)]
        hub.save("order")

    @_action
    def fold(self, name, on):
        hub = self._hub
        hub.prefs.folded = (hub.prefs.folded | {name}) if on else (hub.prefs.folded - {name})
        hub.save("folded")

    @_action
    def set_favorites(self, ids):
        hub = self._hub
        hub.prefs.favorites = list(dict.fromkeys(i for i in ids if isinstance(i, str)))
        hub.save("favorites")

    @_action
    def set_theme(self, theme):
        hub = self._hub
        hub.prefs.theme = theme if theme in ("light", "dark") else ""
        hub.save("theme")
