"""빠른 워커의 꼬리 캐시·꼬리 읽기 상한·추적기 키·[점프] 가능 판정.
실제 레지스트리도 창도 건드리지 않는다 — live.py의 의존성을 전부 갈아 끼운다."""
import os

import config
import live
import status

NOW = 1_700_000_000.0
FILETIME_EPOCH_DIFF = 11644473600.0


def ticks(sec):
    return str(int((sec + FILETIME_EPOCH_DIFF) * 1e7))


def reg(sid="s1", pid=1, cwd=os.path.join(config.DEV_ROOT, "myproj")):
    return {"pid": pid, "sessionId": sid, "cwd": cwd, "status": "busy",
            "statusUpdatedAt": NOW * 1000.0, "procStart": ticks(NOW)}


def patch(monkeypatch, regs, paths_by_sid, calls):
    monkeypatch.setattr(live.collect_fs, "read_registry", lambda: (regs, 0, 0))
    monkeypatch.setattr(live.collect_fs, "find_transcript",
                        lambda r, *a: paths_by_sid.get(r["sessionId"]))
    monkeypatch.setattr(live.collect_fs, "procstart_to_unix", lambda s: NOW)
    monkeypatch.setattr(live.term, "can_jump", lambda pid: False)
    monkeypatch.setattr(live.term, "launcher_gone", lambda pid: False)

    def counted(path):
        calls.append(path)
        return {"role": "user", "stop_reason": None, "timestamp": NOW, "cwd": None}

    monkeypatch.setattr(live.tail, "read_last_message", counted)


def test_tail_is_read_once_while_the_file_is_unchanged(tmp_path, monkeypatch):
    f = tmp_path / "s1.jsonl"
    f.write_bytes(b'{"a":1}\n')
    calls = []
    patch(monkeypatch, [reg()], {"s1": str(f)}, calls)
    tracker, prev, tcache = status.VetoTracker(), {}, {}
    live._live(tracker, prev, tcache)
    live._live(tracker, prev, tcache)
    assert calls == [str(f)]                       # 2틱인데 파싱은 1회
    with open(f, "ab") as fh:
        fh.write(b'{"a":2}\n')
    live._live(tracker, prev, tcache)
    assert len(calls) == 2                         # 크기가 바뀌면 다시 읽는다


def test_tail_cache_evicts_departed_sessions(tmp_path, monkeypatch):
    f = tmp_path / "s1.jsonl"
    f.write_bytes(b'{"a":1}\n')
    calls = []
    patch(monkeypatch, [reg()], {"s1": str(f)}, calls)
    tracker, prev, tcache = status.VetoTracker(), {}, {}
    live._live(tracker, prev, tcache)
    assert list(tcache) == [str(f)]
    monkeypatch.setattr(live.collect_fs, "read_registry", lambda: ([], 0, 0))
    live._live(tracker, prev, tcache)
    assert tcache == {} and prev == {}


def test_live_tail_max_files_caps_tail_reads(tmp_path, monkeypatch):
    files = {}
    for sid in ("s1", "s2"):
        p = tmp_path / (sid + ".jsonl")
        p.write_bytes(b'{"a":1}\n')
        files[sid] = str(p)
    calls = []
    patch(monkeypatch, [reg("s1"), reg("s2", pid=2)], files, calls)
    monkeypatch.setattr(config, "LIVE_TAIL_MAX_FILES", 1)
    out, _, _ = live._live(status.VetoTracker(), {}, {})
    assert len(out) == 2 and calls == [files["s1"]]


def test_prev_state_key_matches_status_tracker_key(tmp_path, monkeypatch):
    # sessionId가 없는 레코드도 워커와 판정기가 같은 키('pid:<n>')를 써야 한다.
    r = reg()
    del r["sessionId"]
    patch(monkeypatch, [r], {}, [])
    monkeypatch.setattr(live.collect_fs, "find_transcript", lambda *a: None)
    prev = {}
    out, _, _ = live._live(status.VetoTracker(), prev, {})
    assert list(prev) == [status.tracker_key(r)] == ["pid:1"]
    assert out[0].session_id == ""


def test_jumpable_is_a_bool_from_the_worker_not_an_hwnd(monkeypatch):
    """[점프] 가능 여부는 수집 스레드가 판정한다(렌더 경로에 Win32 호출 없음)."""
    patch(monkeypatch, [reg("s1"), reg("s2", pid=2)], {}, [])
    monkeypatch.setattr(live.term, "can_jump", lambda pid: pid == 1)
    out, _, _ = live._live(status.VetoTracker(), {}, {})
    got = {s.session_id: s.jumpable for s in out}
    assert got == {"s1": True, "s2": False}
    assert all(isinstance(s.jumpable, bool) for s in out)


def test_status_updated_at_uses_the_unit_guard(monkeypatch):
    """단위 드리프트 방어를 통과하지 못한 값은 0.0이다 — 무조건 /1000 하지 않는다."""
    r = reg()
    r["statusUpdatedAt"] = "어제"
    patch(monkeypatch, [r], {}, [])
    out, _, _ = live._live(status.VetoTracker(), {}, {})
    assert out[0].status_updated_at == 0.0


def test_background_flag_comes_from_registry_kind(monkeypatch):
    bg = dict(reg("s-bg", 2), kind="bg")
    patch(monkeypatch, [reg(), bg], {}, [])
    out = live._live(status.VetoTracker(), {}, {})
    got = {s.session_id: s.background for s in (out[0] if isinstance(out, tuple) else out)}
    assert got == {"s1": False, "s-bg": True}


def _sessions(out):
    return out[0] if isinstance(out, tuple) else out


def test_parked_window_and_its_background_continuation_become_one_row(monkeypatch):
    front = dict(reg("front", 10), kind="interactive", parkedJobId="J1")
    bg = dict(reg("bg", 20), kind="bg", jobId="J1")
    other = dict(reg("other", 30), kind="interactive")
    patch(monkeypatch, [front, bg, other], {}, [])
    monkeypatch.setattr(live.term, "can_jump", lambda pid: pid == 10)
    out = _sessions(live._live(status.VetoTracker(), {}, {}))
    by = {s.session_id: s for s in out}
    assert set(by) == {"bg", "other"}
    m = by["bg"]
    assert (m.pid, m.jumpable, m.background, m.also_ids) == (10, True, False, ("front",))


def test_background_alone_keeps_attach_when_the_window_is_gone(monkeypatch):
    bg = dict(reg("bg", 20), kind="bg", jobId="J1")
    patch(monkeypatch, [bg], {}, [])
    (s,) = _sessions(live._live(status.VetoTracker(), {}, {}))
    assert s.background and s.also_ids == ()


def test_unrelated_parked_job_id_does_not_merge(monkeypatch):
    front = dict(reg("front", 10), kind="interactive", parkedJobId="J9")
    bg = dict(reg("bg", 20), kind="bg", jobId="J1")
    patch(monkeypatch, [front, bg], {}, [])
    out = _sessions(live._live(status.VetoTracker(), {}, {}))
    assert {s.session_id for s in out} == {"front", "bg"}


def test_desktop_app_session_is_jumpable_without_a_window(monkeypatch):
    d = dict(reg("d", 5), entrypoint=config.DESKTOP_ENTRYPOINT)
    patch(monkeypatch, [d, reg("cli", 6)], {}, [])
    got = {s.session_id: (s.desktop, s.jumpable) for s in _sessions(live._live(status.VetoTracker(), {}, {}))}
    assert got == {"d": (True, True), "cli": (False, False)}


def test_same_conversation_in_two_processes_is_one_row_preferring_the_terminal(monkeypatch):
    old = dict(reg("same", 10), statusUpdatedAt=(NOW - 60) * 1000.0)
    new = dict(reg("same", 20), entrypoint=config.DESKTOP_ENTRYPOINT)
    patch(monkeypatch, [new, old], {}, [])
    (s,) = _sessions(live._live(status.VetoTracker(), {}, {}))
    assert (s.pid, s.desktop) == (10, False)


def test_same_conversation_in_two_terminals_targets_the_recent_one(monkeypatch):
    t = __import__("time").time()   # _su_seconds는 하루보다 오래된 시각을 버린다 — 지금 시각을 쓴다
    old = dict(reg("same", 10), statusUpdatedAt=(t - 60) * 1000.0)
    patch(monkeypatch, [old, dict(reg("same", 20), statusUpdatedAt=t * 1000.0)], {}, [])
    (s,) = _sessions(live._live(status.VetoTracker(), {}, {}))
    assert s.pid == 20


def test_closed_window_session_is_offered_as_resume_in_a_new_tab(monkeypatch):
    """창도 없고 띄운 셸도 없으면 orphan — 버튼이 켜진다. 셸이 살아 있으면(창을 못 찾을 뿐) 꺼진 채다."""
    bg = dict(reg("bg", 3), kind="bg")
    patch(monkeypatch, [reg("closed", 1), reg("hidden", 2), bg], {}, [])
    monkeypatch.setattr(live.term, "launcher_gone", lambda pid: pid in (1, 3))
    got = {s.session_id: (s.orphan, s.jumpable) for s in _sessions(live._live(status.VetoTracker(), {}, {}))}
    assert got == {"closed": (True, True), "hidden": (False, False), "bg": (False, False)}


def test_reopened_conversation_prefers_the_process_that_still_has_a_window(monkeypatch):
    t = __import__("time").time()
    old = dict(reg("same", 10), statusUpdatedAt=t * 1000.0)            # 창이 닫힌 예전 프로세스(더 최근에 갱신)
    new = dict(reg("same", 20), statusUpdatedAt=(t - 60) * 1000.0)
    patch(monkeypatch, [old, new], {}, [])
    monkeypatch.setattr(live.term, "can_jump", lambda pid: pid == 20)
    monkeypatch.setattr(live.term, "launcher_gone", lambda pid: pid == 10)
    (s,) = _sessions(live._live(status.VetoTracker(), {}, {}))
    assert (s.pid, s.orphan, s.jumpable) == (20, False, True)


def test_launcher_gone_is_false_for_a_process_with_a_live_parent():
    assert live.term.launcher_gone(os.getpid()) is False
    assert live.term.launcher_gone(2 ** 30) is False                   # 없는 pid — 판단하지 않는다
