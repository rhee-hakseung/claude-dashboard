"""Store: 워커별 마지막 발행 시각으로 만든 collected_at과 예외 시의 실패 카운트.
스레드를 띄우지 않고 루프 본문이 하는 호출만 직접 재현한다."""
import time

import workers


def test_collected_at_is_the_older_of_the_two_workers(monkeypatch):
    """느린 워커만 계속 발행해도 빠른 워커가 멈추면 스냅샷은 낡은 것으로 보여야 한다."""
    clock = [1000.0]
    monkeypatch.setattr(workers.time, "time", lambda: clock[0])
    store = workers.Store()
    store.update("fast", 0, live=[])
    clock[0] += 60.0
    store.update("slow", 0, jobs=[])              # slow만 발행
    assert store.read().collected_at == 1000.0    # 15초 판정은 멈춘 fast를 본다
    store.update("fast", 0, live=[])
    assert store.read().collected_at == 1060.0    # 둘 다 발행하면 다시 최신


def test_worker_exception_counts_a_failure_and_keeps_the_last_good_data():
    store = workers.Store()
    store.update("fast", 0, live=["row"])
    store.update("fast", 1)                       # 루프의 except 블록이 하는 호출
    snap = store.read()
    assert snap.failures == 1 and snap.live == ["row"]
    store.update("slow", 1)
    assert store.read().failures == 2             # 두 워커의 실패가 함께 누적된다


def test_failures_accumulate_per_worker_without_double_counting():
    store = workers.Store()
    store.update("fast", 2, live=[])
    store.update("slow", 0, ended=[])
    assert store.read().failures == 2


def test_update_sets_the_event_for_the_ui_tick():
    store = workers.Store()
    store.event.clear()
    store.update("slow", 0, ended=[])
    assert store.event.is_set()


def test_initial_snapshot_is_not_stale_at_startup():
    store = workers.Store()
    assert abs(store.read().collected_at - time.time()) < 5.0
