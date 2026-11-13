"""끝난 기록 열거: 동일성, 귀속, stub 판정, 이름 3단 fallback.

- 최상위 `projects/*/*.jsonl` 글롭만(재귀 금지 — 하위 폴더는 첨부물이다).
- 동일성은 `(슬러그, sessionId, 경로)`. 같은 sessionId가 두 슬러그에 있으면 **두 줄 다** 표시한다.
- live↔ended dedup만 sessionId 기준 — 라이브가 되면 두 사본 모두 목록에서 빠진다.
- 첫 user 메시지는 **표시 제목으로만** 쓴다. 본문을 로그·파일 어디에도 남기지 않는다.
"""
from __future__ import annotations

import glob
import json
import os

import config
import paths
import tail
from model import EndedSession


def format_age(seconds: float) -> str:
    if seconds < 60:
        return "방금"
    if seconds < 3600:
        return f"{int(seconds // 60)}분 전"
    if seconds < 86400:
        return f"{int(seconds // 3600)}시간 전"
    return f"{int(seconds // 86400)}일 전"


def _first(values):
    for v in values:
        if v:
            return v
    return None


def _text(content) -> str:
    """content(문자열 또는 블록 리스트)에서 표시용 텍스트만 뽑는다."""
    if isinstance(content, str):
        return " ".join(content.split())
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return " ".join(" ".join(parts).split())
    return ""


def _count_users(path: str) -> int | None:
    """user 메시지 수. 줄 수가 상한을 넘으면 None(= 판정하지 않음 → non-stub)."""
    users = lines = 0
    with open(path, "rb") as fh:
        for raw in fh:
            lines += 1
            if lines > config.STUB_MAX_LINES:
                return None
            try:
                rec = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            msg = rec.get("message") if isinstance(rec, dict) else None
            if isinstance(msg, dict) and msg.get("role") == "user":
                users += 1
    return users


def _inspect(path: str, size: int) -> dict:
    """제목·cwd 후보·stub 여부. 큰 파일은 머리 창과 꼬리 창만 읽는다(전수 읽기 없음)."""
    trecs = list(tail.iter_tail_records(path))                       # 최신 → 과거
    hrecs = list(tail.iter_head_records(path, config.CWD_SCAN_LINES))
    title = None      # ① 최신 custom-title(/rename) → 최신 ai-title. 각각 꼬리 먼저, 머리는 fallback
    for kind, field in (("custom-title", "customTitle"), ("ai-title", "aiTitle")):
        title = title or _first(r.get(field) for recs in (trecs, hrecs)
                                for r in recs if r.get("type") == kind)
    if not title:                                                    # ② 첫 user 메시지 절단
        for r in hrecs:
            msg = r.get("message")
            if isinstance(msg, dict) and msg.get("role") == "user":
                title = _text(msg.get("content"))[:config.NAME_FALLBACK_CHARS] or None
                break
    # [재개] 폴더 후보: 꼬리의 마지막 cwd → 머리의 첫 cwd
    cwds = [c for c in (_first(r.get("cwd") for r in trecs),
                        _first(r.get("cwd") for r in hrecs)) if c]
    is_stub = False
    if size < config.STUB_MAX_BYTES:                                 # 크기 가드 — 85MB는 미진입
        users = _count_users(path)
        is_stub = users == 0
    cont = _first(r.get("continuedInSessionId") for r in trecs if r.get("type") == "continued-in")
    return {"title": title, "cwds": cwds, "is_stub": is_stub, "continued_in": cont}   # cont: 이어받은 sessionId


def _project_dir(project: str | None, dev_root: str) -> str | None:
    if project is None:
        return None
    return dev_root if project == paths.ROOT_KEY else os.path.join(dev_root, project)


def list_ended(projects: list[str], live_ids: set[str],
               projects_dir: str = config.PROJECTS_DIR, cache: dict | None = None,
               dev_root: str = config.DEV_ROOT) -> tuple[list[EndedSession], int]:
    """→ `(끝난 세션 목록, 실패 수)`. `cache[path] = ((path, mtime, size), info)`로
    5초 폴링이 바뀐 파일만 다시 읽게 한다. 나이 문자열은 화면(ui_rows)이 mtime으로 만든다."""
    rows: list[EndedSession] = []
    failures, seen, cont_of = 0, set(), {}
    for path in glob.glob(os.path.join(projects_dir, "*", "*.jsonl")):
        folder_slug = os.path.basename(os.path.dirname(path))
        sid = os.path.splitext(os.path.basename(path))[0]
        if sid in live_ids:
            continue
        seen.add(path)
        # 행 조립까지 전부 이 try 안에 둔다 — 레코드 하나가 망가져도 그 파일만 건너뛴다.
        try:
            st = os.stat(path)
            key = (path, st.st_mtime, st.st_size)
            hit = cache.get(path) if cache is not None else None
            info = hit[1] if hit and hit[0] == key else _inspect(path, st.st_size)
            cwds = [c for c in info["cwds"] if isinstance(c, str) and c]   # 오염된 cwd는 후보에서만 제외
            project = paths.attribute_slug(folder_slug, projects, dev_root)
            row = EndedSession(
                slug=folder_slug, session_id=sid, path=path, project=project,
                mtime=st.st_mtime, size=st.st_size,
                title=info["title"] or sid[:8],   # 나이는 붙이지 않는다 — 뷰키가 매분 바뀐다
                is_stub=info["is_stub"],
                resume_dir=paths.resume_dir(folder_slug, cwds,
                                            _project_dir(project, dev_root)),
                duplicate_of_newer=False)
        except (OSError, UnicodeError, ValueError, AttributeError, TypeError, KeyError):
            failures += 1
            continue
        if cache is not None:
            cache[path] = (key, info)   # 실패한 파일은 캐시에 남기지 않는다(매 스캔 재시도)
        rows.append(row)
        cont_of[path] = info.get("continued_in")
    if cache is not None:               # 이번 스캔에서 못 본 경로는 버린다(jobs.scan과 동일)
        for gone in [k for k in cache if k not in seen]:
            del cache[gone]

    by_sid: dict[str, list[EndedSession]] = {}
    for r in rows:
        by_sid.setdefault(r.session_id, []).append(r)
    for group in by_sid.values():   # [재개]는 한 줄에만: 폴더가 살아 있는 쪽 → mtime 최신(복사본은 동률)
        if len(group) > 1:
            newest = max(group, key=lambda r: (r.project is not None, bool(r.resume_dir), r.mtime))
            for r in group:
                r.duplicate_of_newer = r is not newest
                if r.duplicate_of_newer:
                    r.resume_dir = None           # 데이터 층에서 [재개]를 원천 차단한다
    # 다른 기록으로 이어진 원본은 숨긴다([재개]하면 옛 시점으로 돌아감). 이어받은 쪽이 사라지면 다시 보인다.
    known = live_ids | {r.session_id for r in rows}
    rows = [r for r in rows if cont_of.get(r.path) not in known]
    rows.sort(key=lambda r: -r.mtime)
    return rows, failures
