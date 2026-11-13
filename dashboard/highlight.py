"""강조 상태기계 하나만 담는다(model.py의 150줄 상한 때문에 분리했다).

**소유 스레드는 UI 스레드뿐이다.** 화면 쪽(`web_hub`·`web_api`)의 호출만
이 객체를 만진다 — 수집 워커는 절대 건드리지 않으므로 락이 필요 없다.
메모리에만 존재하며 디스크에 남기지 않는다.
"""
from __future__ import annotations

import config
from model import ENDED, WAITING, WORKING


class Highlight:
    """강조 상태기계. 세션별 상태는 `forget`으로만 사라진다."""

    def __init__(self) -> None:
        self._s: dict[str, dict] = {}

    def _st(self, sid: str) -> dict:
        return self._s.setdefault(sid, {"seen": False, "sources_disagree": False,
                                        "resuming": 0.0, "on": False, "prev_state": None})

    def observe(self, session_id: str, cur_state: str | None) -> bool:
        """`cur_state is None` = D1 행 6 HOLD → 전이 없음. `sources_disagree`는 중립이라
        여기서 보지 않는다."""
        st = self._st(session_id)
        if cur_state is None:
            return st["on"]
        prev = st["prev_state"]
        if cur_state == WORKING:
            st["seen"] = False           # WORKING이 처음 관측되는 순간 seen 해제
            if prev == WAITING:
                st["on"] = False         # OFF ②
        elif cur_state == WAITING:
            if prev != WAITING and not st["seen"]:
                st["on"] = True          # ON (prev is None도 전이로 센다)
        elif cur_state == ENDED:
            st["on"] = False             # OFF ③
        st["prev_state"] = cur_state
        return st["on"]

    def mark_seen(self, session_id: str) -> None:
        """대시보드가 방금 띄운 세션 — 첫 WAITING에 강조를 걸지 않는다."""
        st = self._st(session_id)
        st["seen"] = True
        st["on"] = False

    def jump_clicked(self, session_id: str) -> None:
        self._st(session_id)["on"] = False   # OFF ①

    def is_on(self, session_id: str) -> bool:
        st = self._s.get(session_id)         # 없는 세션의 상태를 만들지 않는다 — 렌더는 읽기만
        return bool(st and st["on"])

    def set_disagree(self, session_id: str, value: bool) -> None:
        self._st(session_id)["sources_disagree"] = bool(value)

    def mark_resuming(self, session_id: str, now: float) -> None:
        self._st(session_id)["resuming"] = now

    def clear_resuming(self, session_id: str) -> None:
        self._st(session_id)["resuming"] = 0.0

    def is_resuming(self, session_id: str, now: float) -> bool:
        st = self._s.get(session_id)         # 끝난 줄을 그릴 때마다 상태를 만들면 안 된다
        t = st["resuming"] if st else 0.0
        return bool(t) and (now - t) <= config.RESUMING_CAP_SEC

    def forget(self, session_id: str) -> None:
        """떠난 세션의 상태를 버린다. **ENDED를 관측한 뒤에만** 부른다 — 먼저 지우면
        OFF ③ 전이가 사라진다. 다시 나타나면 처음 보는 세션으로 취급된다."""
        self._s.pop(session_id, None)
