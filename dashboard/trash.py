"""사용자가 고른 기록 1개를 휴지통으로 보낸다 — `~/.claude` 아래의 유일한 쓰기다(SI-3).

3중 가드를 **함수 자신이** 강제한다. UI를 믿지 않는다. `assert`는 쓰지 않는다 —
`python -O`에서 통째로 사라지기 때문이다. 거절 사유는 사용자에게 그대로 보여줄
한국어 문장이며, 모달 없이 상태줄에만 표시한다.
부속 데이터(첨부 폴더 등)는 건드리지 않는다 — 대상은 `.jsonl` 파일 정확히 하나다.
"""
from __future__ import annotations

import os
import time

import send2trash

import collect_fs
import config


class TrashRefused(Exception):
    """가드에 걸렸다. `str(e)`가 곧 상태줄에 나갈 한국어 사유다."""


def _norm(p: str) -> str:
    """대소문자·구분자·`..`를 모두 흡수한 비교용 절대 경로."""
    return os.path.normcase(os.path.abspath(p))


def send(path: str, projects_dir: str = config.PROJECTS_DIR,
         sessions_dir: str = config.SESSIONS_DIR, now: float | None = None) -> None:
    now = time.time() if now is None else now
    full, root = _norm(path), _norm(projects_dir)

    # ① 경로 허용목록: `projects\<슬러그>\<이름>.jsonl` — 깊이가 정확히 그 수준이어야 한다.
    if not full.endswith(".jsonl"):
        raise TrashRefused("기록 파일(.jsonl)이 아니라서 지우지 않습니다")
    parent = os.path.dirname(full)
    if parent == root or os.path.dirname(parent) != root:
        raise TrashRefused("기록 폴더 바로 아래의 파일이 아니라서 지우지 않습니다")

    # ② 라이브 아님: 호출 시점에 레지스트리를 **다시** 읽는다(호출자 스냅샷은 최대 1초 낡았다).
    sid = os.path.splitext(os.path.basename(path))[0].lower()
    accepted, _rejected, failures = collect_fs.read_registry(sessions_dir)
    # 읽기 실패가 하나라도 있으면 fail-closed다 — 그 파일이 이 세션이었을 수 있다.
    # (거절(stale) 수는 보지 않는다 — 죽은 세션의 파일이 남아 있는 건 정상이다.)
    if failures:
        raise TrashRefused("세션 목록을 확인할 수 없어 안전을 위해 지우지 않습니다")
    if any((r.get("sessionId") or "").lower() == sid for r in accepted):
        raise TrashRefused("아직 살아있는 세션의 기록입니다")

    # ③ 방금 쓰인 파일: 아직 append 중일 수 있다.
    try:
        age = now - os.path.getmtime(path)
    except OSError:
        raise TrashRefused("기록을 찾을 수 없습니다") from None
    if age < config.TRASH_MIN_AGE_SEC:
        raise TrashRefused("방금 쓰인 기록이라 5초 뒤 다시 시도하세요")

    send2trash.send2trash(path)
