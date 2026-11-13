"""강조 FSM의 재진입·HOLD·forget. 나머지 10케이스는 test_model.py에 있다(150줄 상한)."""
from highlight import Highlight
from model import ENDED, WAITING, WORKING


def test_ended_then_waiting_turns_on_again():
    h = Highlight()
    h.observe("s", WAITING)
    h.observe("s", ENDED)
    assert h.observe("s", WAITING) is True     # 재개된 세션은 다시 강조된다


def test_forget_after_ended_then_waiting_turns_on():
    h = Highlight()
    h.observe("s", WAITING)
    h.observe("s", ENDED)                      # OFF ③을 먼저 태우고
    h.forget("s")                              # 그 다음에만 상태를 버린다
    assert h.observe("s", WAITING) is True


def test_forget_is_safe_for_unknown_session():
    Highlight().forget("nope")


def test_hold_keeps_seen():
    h = Highlight()
    h.mark_seen("s")
    assert h.observe("s", None) is False       # HOLD는 seen도 prev도 건드리지 않는다
    assert h.observe("s", WAITING) is False


def test_hold_keeps_on_state():
    h = Highlight()
    h.observe("s", WORKING)
    h.observe("s", WAITING)
    assert h.observe("s", None) is True
