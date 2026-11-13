import config
import status
from model import WAITING, WORKING

NOW = 1_700_000_000.0      # 현실적인 unix 초 — statusUpdatedAt 위생 검사가 실측값을 본다


def reg(st="busy", su_ms=NOW * 1000.0, sid="s1"):
    return {"pid": 1, "sessionId": sid, "status": st, "statusUpdatedAt": su_ms}


def tick(session, tail, tracker, now, n=1):
    out = (None, False)
    for _ in range(n):
        out = status.decide(session, tail, tracker, now=now)
    return out


# ── 행 4 / 5 ────────────────────────────────────────────────────────────────
def test_row4_busy_is_working():
    assert status.decide(reg("busy"), None, status.VetoTracker(), now=NOW) == (WORKING, False)


def test_row5_not_busy_is_waiting():
    t = status.VetoTracker()
    for v in ("idle", "waiting", "shell", "something-new"):
        assert status.decide(reg(v), None, t, now=NOW) == (WAITING, False)


def test_row5_shell_tag():
    assert status.shell_tag(reg("shell")) is True
    assert status.shell_tag(reg("idle")) is False


def test_missing_tail_does_not_hold_rows_4_5():
    # 꼬리가 없어도 평범한 busy/not-busy 판정은 흔들리지 않는다.
    t = status.VetoTracker()
    assert status.decide(reg("busy"), None, t, now=NOW)[0] == WORKING
    assert status.decide(reg("idle"), None, t, now=NOW)[0] == WAITING


def test_non_string_status_does_not_raise():
    assert status.decide({"pid": 1, "sessionId": "s", "status": 5},
                         None, status.VetoTracker(), now=NOW) == (WAITING, False)
    assert status.shell_tag({"status": 5}) is False


def test_tracker_key_falls_back_to_pid():
    assert status.tracker_key({"sessionId": "s", "pid": 7}) == "s"
    assert status.tracker_key({"pid": 7}) == "pid:7"


# ── 행 2 (경고 A) ───────────────────────────────────────────────────────────
def test_row2_warning_a_disabled_by_default():
    t = status.VetoTracker()
    old = {"role": "assistant", "stop_reason": "end_turn", "timestamp": NOW - 9999, "cwd": None}
    assert config.TAIL_VETO_A_ENABLED is False
    assert tick(reg("busy"), old, t, NOW, n=5) == (WORKING, False)


def test_row2_warning_a_when_enabled_keeps_working_and_flags(monkeypatch):
    monkeypatch.setattr(config, "TAIL_VETO_A_ENABLED", True)
    t = status.VetoTracker()
    old = {"role": "assistant", "stop_reason": "end_turn",
           "timestamp": NOW - config.TAIL_VETO_ASSISTANT_SEC - 1, "cwd": None}
    for _ in range(config.VETO_CONFIRM_TICKS - 1):
        assert status.decide(reg("busy"), old, t, now=NOW) == (WORKING, False)
    assert status.decide(reg("busy"), old, t, now=NOW) == (WORKING, True)


def test_row2_never_fires_on_tool_use(monkeypatch):
    monkeypatch.setattr(config, "TAIL_VETO_A_ENABLED", True)
    t = status.VetoTracker()
    busy_tool = {"role": "assistant", "stop_reason": "tool_use", "timestamp": NOW - 9999,
                 "cwd": None}
    assert tick(reg("busy"), busy_tool, t, NOW, n=10) == (WORKING, False)


# ── 행 3 (거부권 B) ─────────────────────────────────────────────────────────
def late_tail(su_sec):
    return {"role": "user", "stop_reason": None,
            "timestamp": su_sec + config.TAIL_VETO_B_MARGIN_SEC + 1, "cwd": None}


def test_row3_veto_b_needs_three_ticks_then_flips():
    t = status.VetoTracker()
    s, late = reg("idle", NOW * 1000.0), late_tail(NOW)
    for _ in range(config.VETO_CONFIRM_TICKS - 1):
        assert status.decide(s, late, t, now=NOW) == (WAITING, False)
    assert status.decide(s, late, t, now=NOW) == (WORKING, True)


def test_row3_seconds_and_milliseconds_behave_the_same():
    # 단위가 초로 바뀌어도 같은 판정이어야 한다(1e11 기준으로 ms/초를 가른다).
    for su in (NOW * 1000.0, NOW):
        t = status.VetoTracker()
        assert tick(reg("idle", su), late_tail(NOW), t, NOW,
                    n=config.VETO_CONFIRM_TICKS) == (WORKING, True)


def test_row3_absurd_status_updated_at_disables_veto_b():
    t = status.VetoTracker()
    # 하루 넘게 과거(= 단위 드리프트) → su를 믿지 않는다 → 거부권 B가 영영 안 걸린다
    assert tick(reg("idle", 1.0), late_tail(NOW), t, NOW, n=10) == (WAITING, False)
    t2 = status.VetoTracker()
    assert tick(reg("idle", NOW * 1e6), late_tail(NOW), t2, NOW, n=10) == (WAITING, False)


def test_row3_margin_absorbs_small_inversion():
    t = status.VetoTracker()
    near = {"role": "user", "stop_reason": None, "timestamp": NOW + 1, "cwd": None}
    assert tick(reg("idle", NOW * 1000.0), near, t, NOW, n=10) == (WAITING, False)


def test_row3_counter_resets_when_condition_breaks():
    t = status.VetoTracker()
    s, late = reg("idle", NOW * 1000.0), late_tail(NOW)
    status.decide(s, late, t, now=NOW)
    status.decide(s, late, t, now=NOW)
    status.decide(s, None, t, now=NOW)                              # 조건 끊김 → 0
    assert status.decide(s, late, t, now=NOW) == (WAITING, False)


# ── 행 6 (HOLD) ─────────────────────────────────────────────────────────────
def test_row6_hold_when_no_row_matches():
    assert status.decide({"pid": 1, "sessionId": "x"}, None, status.VetoTracker()) == (None, False)


# ── 드라이런 3세션 재현(계획 3.1 재측정 표) ─────────────────────────────────
def test_dryrun_three_live_sessions():
    t = status.VetoTracker()
    su = (NOW - 2414) * 1000
    p28880 = {"role": "assistant", "stop_reason": "tool_use", "timestamp": NOW - 396, "cwd": None}
    assert status.decide(reg("busy", su, "28880"), p28880, t, now=NOW) == (WORKING, False)
    su2 = (NOW - 3034) * 1000
    p32260 = {"role": "assistant", "stop_reason": "end_turn", "timestamp": NOW - 3034, "cwd": None}
    assert status.decide(reg("idle", su2, "32260"), p32260, t, now=NOW) == (WAITING, False)
    su3 = (NOW - 269) * 1000
    p46576 = {"role": "user", "stop_reason": None, "timestamp": NOW - 1, "cwd": None}
    assert status.decide(reg("busy", su3, "46576"), p46576, t, now=NOW) == (WORKING, False)
