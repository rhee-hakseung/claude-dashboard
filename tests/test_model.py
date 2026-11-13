import model
from highlight import Highlight
from model import ENDED, Project, WAITING, WORKING


def P(name, act, root=False):
    return Project(name, "d", act, root)


# 프로젝트 순서(order_projects)는 tests/test_order.py. 상태 우선순위 정렬(sort_projects)은
# 2026-09-22 사용자 결정으로 없앴다 — 기다리는 프로젝트는 위로 뜨지 않고 빨간 점으로만 알린다.

# ── 강조 FSM 10케이스 ────────────────────────────────────────────────────────
def test_fsm_none_to_waiting_turns_on():
    h = Highlight()
    assert h.observe("s", WAITING) is True


def test_fsm_working_to_waiting_turns_on():
    h = Highlight()
    h.observe("s", WORKING)
    assert h.observe("s", WAITING) is True


def test_fsm_waiting_to_waiting_stays():
    h = Highlight()
    h.observe("s", WAITING)
    h.jump_clicked("s")
    assert h.observe("s", WAITING) is False   # 같은 상태 반복은 전이가 아니다


def test_fsm_seen_blocks_first_on():
    h = Highlight()
    h.mark_seen("s")
    assert h.observe("s", WAITING) is False


def test_fsm_seen_cleared_on_first_working():
    h = Highlight()
    h.mark_seen("s")
    h.observe("s", WAITING)
    h.observe("s", WORKING)                   # 여기서 seen 해제
    assert h.observe("s", WAITING) is True


def test_fsm_hold_is_not_a_transition():
    h = Highlight()
    h.observe("s", WORKING)
    assert h.observe("s", None) is False      # HOLD
    assert h.observe("s", WAITING) is True    # prev는 여전히 WORKING


def test_fsm_off_on_jump_click():
    h = Highlight()
    h.observe("s", WAITING)
    h.jump_clicked("s")
    assert h.is_on("s") is False


def test_fsm_off_on_waiting_to_working():
    h = Highlight()
    h.observe("s", WAITING)
    assert h.observe("s", WORKING) is False


def test_fsm_off_on_ended():
    h = Highlight()
    h.observe("s", WAITING)
    assert h.observe("s", ENDED) is False


def test_fsm_sources_disagree_is_neutral():
    h = Highlight()
    h.observe("s", WAITING)
    h.set_disagree("s", True)
    assert h.is_on("s") is True
    h.observe("s", WORKING)
    h.set_disagree("s", True)
    assert h.is_on("s") is False


# ── resuming 상한 ────────────────────────────────────────────────────────────
def test_resuming_cap():
    import config
    h = Highlight()
    h.mark_resuming("s", 1000.0)
    assert h.is_resuming("s", 1000.0 + config.RESUMING_CAP_SEC - 1) is True
    assert h.is_resuming("s", 1000.0 + config.RESUMING_CAP_SEC + 1) is False
    h.mark_resuming("s", 1000.0)
    h.clear_resuming("s")
    assert h.is_resuming("s", 1001.0) is False


def test_snapshot_copy_is_shallow_but_independent():
    s = model.Snapshot(projects=[P("a", 1)], collected_at=5.0)
    c = s.copy()
    c.projects.append(P("b", 2))
    assert len(s.projects) == 1 and c.collected_at == 5.0
