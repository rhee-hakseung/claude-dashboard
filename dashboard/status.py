"""D1 판정 규칙 표를 그대로 구현한다(위에서부터 첫 일치). 임계는 전부 config.py.

행 1 (레지스트리 없음/stale 탈락 → 끝남)은 호출자 몫이다 — 여기 오는 dict는 이미
stale 필터를 통과한 라이브 레코드다.

**꼬리가 없어도 행 4/5는 흔들리지 않는다.** 행 4·5는 레지스트리만 보므로 tail=None이어도
그대로 판정한다. 꼬리가 필요한 것은 행 2·3뿐이고, 꼬리 부재는 그 두 행을 '미성립'으로
만들 뿐 평범한 busy/not-busy 판정을 HOLD로 바꾸지 않는다(그렇게 하면 기록이 아직 없는
새 세션이 영원히 HOLD에 갇힌다).
"""
from __future__ import annotations

import time

import config
from model import WAITING, WORKING


class VetoTracker:
    """거부권 A/B의 세션별 연속 틱 카운터. 조건이 끊기면 0으로 되돌아간다."""

    def __init__(self) -> None:
        self._n: dict[tuple[str, str], int] = {}

    def bump(self, session_id: str, kind: str, cond: bool) -> bool:
        key = (session_id, kind)
        n = self._n.get(key, 0) + 1 if cond else 0
        self._n[key] = n
        return n >= config.VETO_CONFIRM_TICKS

    def forget(self, session_id: str) -> None:
        for kind in ("A", "B"):
            self._n.pop((session_id, kind), None)


def tracker_key(session: dict) -> str:
    """거부권 추적기와 워커의 '직전 상태' 맵은 **같은 키**를 써야 한다.
    갈리면 HOLD(행 6)가 엉뚱한 줄의 상태를 물려받는다."""
    return session.get("sessionId") or "pid:%s" % session.get("pid")


def _status(session: dict) -> str:
    """레지스트리 타입 드리프트(status에 숫자)에도 죽지 않게 항상 str로 낮춘다."""
    return str(session.get("status") or "").lower()


def _su_seconds(raw, now: float) -> float | None:
    """`statusUpdatedAt` 단위 드리프트 방어. 1e11 초과면 ms, 아니면 초로 읽는다.
    하루 전보다 과거거나 60초 넘게 미래면 신뢰하지 않는다(→ None = 거부권 B 무력화).
    이 가드가 없으면 단위가 어긋난 순간 거부권 B가 영원히 발동한다."""
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    su = raw / 1000.0 if raw > 1e11 else float(raw)
    return None if su < now - 86400.0 or su > now + 60.0 else su


def shell_tag(session: dict) -> bool:
    """`shell` = 턴은 끝났는데 백그라운드 셸 명령이 아직 도는 중(행 5 + 표식)."""
    return _status(session) == "shell"


def decide(session: dict, tail: dict | None, tracker: VetoTracker,
           now: float | None = None) -> tuple[str | None, bool]:
    """→ `(state, sources_disagree)`. state가 None이면 행 6 HOLD(직전 상태 유지)."""
    if "status" not in session:
        return None, False                       # 행 6: 어느 행도 매치 안 됨 → HOLD
    now = time.time() if now is None else now
    sid = tracker_key(session)
    busy = _status(session) == "busy"
    su = _su_seconds(session.get("statusUpdatedAt"), now)
    ts = tail.get("timestamp") if tail else None

    # 행 2 — 경고 A(기본 꺼짐). `tool_use`에서는 절대 발동하지 않는다(도구 실행 중).
    cond_a = (config.TAIL_VETO_A_ENABLED and busy and tail is not None
              and tail.get("role") == "assistant" and tail.get("stop_reason") == "end_turn"
              and ts is not None and (now - ts) >= config.TAIL_VETO_ASSISTANT_SEC)
    # 행 3 — 거부권 B. busy가 아닌데 마지막 메시지가 statusUpdatedAt보다 한참 나중이다.
    cond_b = (not busy and tail is not None and ts is not None and su is not None
              and ts > su + config.TAIL_VETO_B_MARGIN_SEC)
    # 두 카운터를 매 틱 함께 갱신한다 — 한쪽만 올리면 반대쪽에 낡은 값이 남는다.
    hit_a = tracker.bump(sid, "A", cond_a)
    hit_b = tracker.bump(sid, "B", cond_b)

    if hit_a:
        return WORKING, True        # 상태는 바꾸지 않는다('작업 중' 유지) — "?" 표식만
    if hit_b:
        return WORKING, True        # 뒤집는다 + "?" 표식
    return (WORKING if busy else WAITING), False   # 행 4 / 행 5
