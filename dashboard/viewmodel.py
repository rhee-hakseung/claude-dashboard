"""스냅샷 → 화면용 묶음. 화면 도구(tk·webview)를 모르는 순수 함수들 — 두 화면이 같이 쓴다."""
from __future__ import annotations

from model import ENDED


def viewmodel(snap):
    """프로젝트별로 라이브·끝남·작업을 묶는다. 세션 상태는 순서에 관여하지 않는다 —
    화면 순서는 사용자 고정 순서(`model.order_projects`)로 정한다."""
    live, ended, js = {}, {}, {}
    live_ids = {i for s in snap.live for i in (s.session_id, *s.also_ids)}
    for s in snap.live:
        live.setdefault(s.project, []).append(s)
    for e in snap.ended:
        # SI-5: 끝남 목록의 dedup은 5초마다뿐이고 레지스트리는 0.5초마다다 —
        # 다시 살아난 세션의 낡은 '끝남' 줄([재개]·[휴지통]이 달린다)을 여기서 떨군다.
        if e.session_id in live_ids:
            continue
        ended.setdefault(e.project, []).append(e)
    for j in snap.jobs:
        js.setdefault(j["project"], []).append(j)
    return [(p, live.get(p.name, []), ended.get(p.name, []), js.get(p.name, []))
            for p in snap.projects]


def status_line(snap, message, stale):
    parts = []
    if snap.failures:
        parts.append("수집 실패 %d회" % snap.failures)       # 워커는 살아 있는데 읽기가
    if snap.disagreements:                                   # 전부 실패하는 상황의 유일한 신호
        parts.append("상태 출처 불일치 %d건" % snap.disagreements)
    if message:
        parts.append(message)
    if stale:
        parts.append("수집 중단 — 재시작 필요")
    return "   ·   ".join(parts)


def apply_highlight(hl, snap, live_ids):
    """강조 FSM 갱신 → 이번 틱의 라이브 sid 집합. 사라진 세션엔 ENDED를 넣어 OFF ③을 태운다."""
    ids = set()
    for s in snap.live:
        ids.add(s.session_id)
        hl.observe(s.session_id, s.state)
        hl.set_disagree(s.session_id, s.sources_disagree)
        hl.clear_resuming(s.session_id)    # 레지스트리에 나타났다 = 재개 완료(증거 기반)
    for sid in live_ids - ids:
        hl.observe(sid, ENDED)             # OFF ③을 먼저 태우고
        hl.forget(sid)                     # 그 다음에만 세션별 상태를 버린다
    return ids
