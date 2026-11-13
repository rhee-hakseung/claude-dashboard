"""망가진 레코드·읽기 실패 1건이 '끝남' 목록 전체를 얼리지 않는지 — 실패 격리와 캐시 위생."""
import os

import pytest

import inventory
from test_inventory import DEV, PROJECTS, SID_A, SID_B, make, user

SID_C = "cccccccc-1111-2222-3333-444444444444"


def bad_user():
    """cwd가 dict인 레코드 — paths.resume_dir가 AttributeError를 내던 실제 모양."""
    r = user()
    r["cwd"] = {"a": 1}
    return r


@pytest.fixture
def inspect_fails_for_b(monkeypatch):
    """SID_B 파일만 내부 파서가 터지는 상황(파일 단위 실패)을 재현한다."""
    real = inventory._inspect

    def flaky(path, size):
        if SID_B in path:
            raise TypeError("simulated parser failure")
        return real(path, size)
    monkeypatch.setattr(inventory, "_inspect", flaky)


def test_malformed_cwd_record_keeps_the_row(tmp_path):
    """오염된 cwd는 [재개] 후보에서만 빠진다 — 기록 자체는 목록에 남는다(R11 '목록에서 빼지 않음')."""
    make(tmp_path, "C--dev-paper-search", SID_A, [user()])
    make(tmp_path, "C--dev-paper-search", SID_B, [bad_user()])
    make(tmp_path, "C--dev-process-game", SID_C, [user(cwd=r"C:\dev\process-game")])
    rows, failures = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert sorted(r.session_id for r in rows) == sorted([SID_A, SID_B, SID_C])
    assert failures == 0


def test_one_failing_file_is_skipped_not_fatal(tmp_path, inspect_fails_for_b):
    make(tmp_path, "C--dev-paper-search", SID_A, [user()])
    make(tmp_path, "C--dev-paper-search", SID_B, [user()])
    make(tmp_path, "C--dev-process-game", SID_C, [user(cwd=r"C:\dev\process-game")])
    rows, failures = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert sorted(r.session_id for r in rows) == sorted([SID_A, SID_C])
    assert failures == 1


def test_failed_file_is_not_cached_and_is_retried(tmp_path, inspect_fails_for_b):
    good = make(tmp_path, "C--dev-paper-search", SID_A, [user()])
    bad = make(tmp_path, "C--dev-paper-search", SID_B, [user()])
    cache = {}
    rows, failures = inventory.list_ended(PROJECTS, set(), str(tmp_path), cache=cache,
                                          dev_root=DEV)
    assert (len(rows), failures) == (1, 1)
    assert list(cache) == [good]                 # 실패한 파일은 캐시에 없다
    cache[good] = (cache[good][0], {"title": "CACHED", "cwds": [], "is_stub": False})
    rows, failures = inventory.list_ended(PROJECTS, set(), str(tmp_path), cache=cache,
                                          dev_root=DEV)
    assert failures == 1                         # 나쁜 파일은 매 스캔 다시 시도된다
    assert rows[0].title == "CACHED"             # 좋은 파일은 캐시를 탄다
    assert bad not in cache


def test_cache_evicts_paths_not_seen_this_scan(tmp_path):
    make(tmp_path, "C--dev-paper-search", SID_A, [user()])
    gone = make(tmp_path, "C--dev-paper-search", SID_B, [user()])
    cache = {}
    inventory.list_ended(PROJECTS, set(), str(tmp_path), cache=cache, dev_root=DEV)
    assert len(cache) == 2
    os.remove(gone)                              # tmp_path 안의 가짜 기록만 지운다
    inventory.list_ended(PROJECTS, set(), str(tmp_path), cache=cache, dev_root=DEV)
    assert gone not in cache and len(cache) == 1
