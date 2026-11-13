"""새 화면의 상태 한 덩어리: 수집 스레드들 + 강조 + 설정 + 마지막 뷰(JSON).

화면(JS)은 `changed_view(rev)`로 물어 가고, 버튼은 `web_api.Api`가 이 객체를 통해 처리한다.
강조(Highlight)는 원래 UI 스레드 전용이었다 — 여기서는 틱 스레드와 버튼 스레드가 같이 만지므로
**모든 접근을 `self.lock` 안에서** 한다.
"""
from __future__ import annotations

import json
import logging
import threading
import time

import highlight
import prefs
import stats
import web_view
import workers
from viewmodel import apply_highlight

log = logging.getLogger("dev-dashboard")
TICK_SEC = 0.25


class Hub:
    def __init__(self):
        self.store = workers.Store()
        self.stop = threading.Event()
        self.stats = stats.Stats()
        self.hl = highlight.Highlight()
        self.prefs = prefs.Prefs()
        self.lock = threading.RLock()
        self.snap = self.store.read()
        self.live_ids: set[str] = set()
        self.trashed: set[str] = set()     # 방금 휴지통으로 보낸 경로 — 다음 스캔 전까지 화면에서 뺀다
        self.view, self.rev, self._json = {}, 0, ""
        self.message, self.msg_seq = "", 0

    def start(self):
        jobs = ((workers.fast_loop, (self.store, self.stop)),
                (workers.slow_loop, (self.store, self.stop)),
                (stats.loop, (self.store, self.stop, self.stats)),
                (self._loop, ()))
        for fn, args in jobs:
            threading.Thread(target=fn, args=args, daemon=True).start()

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("view tick")     # 한 틱이 터져도 다음 틱은 돈다
            self.stop.wait(TICK_SEC)

    def tick(self):
        """스냅샷이 바뀌었으면 강조를 갱신하고, 뷰를 다시 만들어 달라졌을 때만 rev를 올린다."""
        with self.lock:
            now = time.time()
            if self.store.event.is_set():
                self.store.event.clear()   # 먼저 내린다 — 복사 도중의 발행을 다음 틱에 잡는다
                self.snap = self.store.read()
                self.live_ids = apply_highlight(self.hl, self.snap, self.live_ids)
                self.trashed &= {e.path for e in self.snap.ended}
                favs = web_view.normalize_favorites(self.prefs.favorites, self.snap.live)
                if favs != self.prefs.favorites:
                    self.prefs.favorites = favs
                    self.save("favorites")
            if self.trashed:
                self.snap.ended = [e for e in self.snap.ended if e.path not in self.trashed]
            view = web_view.build(self.snap, self.prefs, self.hl, self.stats, now,
                                  self.message, self.msg_seq)
            text = json.dumps(view, sort_keys=True, ensure_ascii=False)
            if text != self._json:
                self._json, self.view, self.rev = text, view, self.rev + 1

    def changed_view(self, rev):
        with self.lock:
            return dict(self.view, rev=self.rev) if rev != self.rev else None

    def say(self, text):
        """상태 메시지(화면 아래 토스트). 빈 문자열은 무시한다."""
        if text:
            with self.lock:
                self.message, self.msg_seq = text, self.msg_seq + 1

    def save(self, *keys):
        try:
            self.prefs.save(*keys)
        except OSError as err:
            self.say("설정 저장 실패: %s" % err)

    def live(self, sid):
        return next((s for s in self.snap.live if s.session_id == sid), None)

    def ended(self, path):
        return next((e for e in self.snap.ended if e.path == path), None)

    def project(self, name):
        return next((p for p in self.snap.projects if p.name == name), None)
