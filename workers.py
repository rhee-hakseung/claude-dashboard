"""수집 스레드 2개와 그들이 공유하는 스냅샷 저장소. 라이브 조립은 `live.py`에 있다.

파일시스템·psutil 접근은 **전부 여기와 live.py에서만** 한다 — UI 스레드에서는 절대 부르지
않는다(`jobs.scan` 첫 호출이 ≈630 ms다). 각 루프 본문을 `try/except Exception`으로 감싼다
(R11): 워커가 죽으면 화면이 조용히 얼어붙기 때문이다. 로그는 stderr로만(SI-2 — 파일 없음).
"""
from __future__ import annotations

import logging
import threading
import time

import collect_fs
import config
import inventory
import jobs
import live
import status
from model import Snapshot

log = logging.getLogger("dev-dashboard")


class Store:
    """Lock 1개 + Event 1개로 보호되는 Snapshot 1개. 큐가 없어 무한 증가가 구조적으로 불가능."""

    def __init__(self):
        self.lock = threading.Lock()
        self.event = threading.Event()
        t0 = time.time()
        self.snap = Snapshot(collected_at=t0)
        self._fails = {"fast": 0, "slow": 0}   # 누적 — 상태줄 "수집 실패 n회"
        self._seen = {"fast": t0, "slow": t0}  # 워커별 마지막 발행 시각

    def update(self, who, fails, **fields):
        with self.lock:
            self._fails[who] += fails
            self._seen[who] = time.time()
            for k, v in fields.items():
                setattr(self.snap, k, v)
            self.snap.failures = sum(self._fails.values())
            # 둘 중 **하나만** 멈춰도 15초 뒤 "수집 중단"이 뜨도록 더 오래된 쪽을 쓴다.
            self.snap.collected_at = min(self._seen.values())
        self.event.set()

    def read(self):
        """락 안에서 얕은 복사만 한다 — 렌더도 재분류도 밖에서(원소는 절대 변경 금지)."""
        with self.lock:
            return self.snap.copy()


def fast_loop(store, stop):
    """0.5 s 틱: 레지스트리 + 라이브 세션 꼬리(파일당 0.46 ms)."""
    tracker, prev, tcache = status.VetoTracker(), {}, {}
    while not stop.is_set():
        t0 = time.time()
        try:
            rows, rejected, failures = live._live(tracker, prev, tcache)
            store.update("fast", failures, live=rows, rejected_registry=rejected,
                         disagreements=sum(1 for s in rows if s.sources_disagree))
        except Exception:
            log.exception("fast worker")
            store.update("fast", 1)      # 예외 = 수집 실패 1건. 직전 데이터는 그대로 둔다.
        stop.wait(max(0.05, config.SESSIONS_PERIOD_SEC - (time.time() - t0)))


def _activity(projects, snap):
    """AC-P2: max(귀속된 기록들의 최신 mtime, 라이브 statusUpdatedAt). 둘 다 없으면 폴더 mtime."""
    newest = {}
    for e in snap.ended:
        if e.project and e.mtime > newest.get(e.project, 0.0):
            newest[e.project] = e.mtime
    for p in projects:
        p.last_activity = collect_fs.last_activity(p, newest, snap.live)
    return projects


def slow_loop(store, stop):
    """데드라인 하나로 projects 3 s / transcripts 5 s / jobs 4 s를 돌린다."""
    ended_cache, job_cache, due = {}, {}, {}
    while not stop.is_set():
        now = time.time()
        try:
            snap = store.read()
            names = [p.name for p in snap.projects]
            if now >= due.get("projects", 0.0):
                due["projects"] = now + config.PROJECTS_PERIOD_SEC
                found = collect_fs.scan_projects()
                names = [p.name for p in found]
                store.update("slow", 0, projects=_activity(found, snap))
            if now >= due.get("ended", 0.0):
                due["ended"] = now + config.TRANSCRIPTS_PERIOD_SEC
                rows, fails = inventory.list_ended(
                    names, {s.session_id for s in snap.live}, cache=ended_cache)
                store.update("slow", fails, ended=rows)
            if now >= due.get("jobs", 0.0):
                due["jobs"] = now + config.JOBS_PERIOD_SEC
                store.update("slow", 0, jobs=jobs.scan(job_cache, names))
        except Exception:
            log.exception("slow worker")
            store.update("slow", 1)      # 예외 = 수집 실패 1건. 직전 데이터는 그대로 둔다.
        stop.wait(0.25)
