"""진입점. 기본은 새 웹 화면(`webapp.py`)이고, `--classic`을 주면 예전 tk 화면(이 파일의 App)을 띄운다.

예전 화면: 셸 1개 + 워커 2개 + UI 틱. 수집 로직은 하나도 없다(전부 workers.py/live.py).

실행은 언제나 `.venv\\Scripts\\pythonw.exe`로 한다 — PATH의 `python`은 Store 스텁이다.
"""
from __future__ import annotations

import logging
import sys
import threading
import time

import config
import highlight
import ui_rows
import ui_shell
import workers
from viewmodel import apply_highlight, status_line, viewmodel  # noqa: F401

log = logging.getLogger("dev-dashboard")


class App:
    def __init__(self):
        self.store = workers.Store()
        self.stop = threading.Event()
        self.hl = highlight.Highlight()   # UI 스레드 전용 — 워커는 만지지 않는다
        self.shell = ui_shell.Shell(on_close=self.stop.set)
        self.rows = ui_rows.Rows(self.shell, self.hl)
        self.snap = self.store.read()
        self.groups = viewmodel(self.snap)
        self.live_ids: set[str] = set()

    def start(self):
        for fn in (workers.fast_loop, workers.slow_loop):
            threading.Thread(target=fn, args=(self.store, self.stop), daemon=True).start()
        self.shell.root.after(config.UI_TICK_MS, self.tick)
        self.shell.root.mainloop()

    def tick(self):
        try:
            now = time.time()
            if self.store.event.is_set():
                # Event를 먼저 내린다 — 복사 도중의 발행을 잃지 않고 다음 틱에 잡는다.
                self.store.event.clear()
                self.snap = self.store.read()
                self.live_ids = apply_highlight(self.hl, self.snap, self.live_ids)
                self.groups = viewmodel(self.snap)
            self.rows.render(self.groups, now)
            self.rows.refresh_ages(now)    # 나이만 바뀐 틱은 재생성 없이 라벨만 고친다
            self.shell.set_status(status_line(
                self.snap, self.rows.message,
                now - self.snap.collected_at > config.STALE_SNAPSHOT_SEC))
        except Exception:
            log.exception("ui tick")       # 한 틱이 터져도 다음 틱은 반드시 예약한다
        finally:
            self.shell.root.after(config.UI_TICK_MS, self.tick)


def main():
    if "--classic" not in sys.argv:
        import webapp                            # 새 화면 — 창 도구(pywebview)는 여기서만 불러온다
        return webapp.main()
    logging.basicConfig(level=logging.WARNING)   # stderr 전용 — 파일을 만들지 않는다
    App().start()


if __name__ == "__main__":
    main()
