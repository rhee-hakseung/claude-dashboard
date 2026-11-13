"""빠른 워커의 라이브 세션 조립: 레지스트리 → 꼬리 → D1 판정 → 프로젝트 귀속.

`workers.py`에서 분리했다(라이브 세션 조립만 맡는다).
파일시스템·psutil·Win32 접근은 전부 수집 스레드에서만 한다(UI 스레드 금지).
"""
from __future__ import annotations

import os
import time

import collect_fs
import config
import paths
import status
import tail
import term
import win_tabs
from model import WORKING, LiveSession

_NO_TAIL = (None, win_tabs.DEFAULT_TITLE)


def _tail(path, cache):
    """`(st_size, st_mtime_ns)`가 같으면 직전 파싱을 재사용한다 — 2 Hz 재파싱 방지(stat 1회).

    돌려주는 값은 `(마지막 메시지, 탭 제목)`이다. 제목을 같은 캐시에 얹었으므로 파일이
    안 바뀐 틱에서는 제목이 공짜다 — 탭 제목 때문에 폴링 비용이 늘지 않는다.
    """
    try:
        key = os.stat(path)
        key = (key.st_size, key.st_mtime_ns)
    except OSError:
        return _NO_TAIL
    hit = cache.get(path)
    if hit and hit[0] == key:
        return hit[1]
    value = (tail.read_last_message(path), _tab_title(path))
    cache[path] = (key, value)
    return value


def _tab_title(path):
    """WT 탭 제목. custom-title(/rename)이 ai-title보다 우선이므로 꼬리 → 머리를 한 줄로 이어
    판정한다 — 머리에만 있는 rename이 꼬리의 ai-title에 지지 않게(inventory._inspect와 같은 규칙)."""
    try:
        return win_tabs.expected_title(list(tail.iter_tail_records(path))
                                       + list(tail.iter_head_records(path)))
    except (OSError, UnicodeError, ValueError):
        return win_tabs.DEFAULT_TITLE


def _merge_parked(out, regs):
    """창의 세션(parkedJobId=J)이 대화를 백그라운드 세션(kind=bg, jobId=J)으로 넘기면 대화는 그쪽
    기록으로만 이어지고(창 쪽 기록에 `continued-in`) 창은 그 세션을 보여 주는 화면이 된다(2026-10-14
    실측). → 한 줄로 합친다: 상태·제목·id는 백그라운드 쪽, [점프] 대상(pid)은 창 쪽."""
    job_sid = {r.get("jobId"): r.get("sessionId") for r in regs if r.get("kind") == "bg" and r.get("jobId")}
    front = {job_sid[r["parkedJobId"]]: r.get("sessionId") for r in regs
             if r.get("parkedJobId") in job_sid and r.get("kind") != "bg"}
    by_sid = {s.session_id: s for s in out}
    drop = set()
    for bg_sid, f_sid in front.items():
        b, f = by_sid.get(bg_sid), by_sid.get(f_sid)
        if b is None or f is None:
            continue
        b.pid, b.jumpable, b.background, b.also_ids = f.pid, f.jumpable, f.orphan, (f_sid,)  # 창이 닫혔으면 attach
        drop.add(f_sid)
    return [s for s in out if s.session_id not in drop]


def _merge_same_sid(out):
    """같은 대화를 두 프로세스가 열면(예: 터미널에서 띄운 세션을 데스크톱 앱에서도 재개) 레지스트리에
    같은 sessionId가 둘 나온다 → 한 줄로 합친다. 대상은 터미널 쪽(창이 있다)이 앱 쪽보다 먼저고, 그다음
    가장 최근에 상태가 바뀐 쪽이다 — 앱 쪽을 고르면 [점프]가 또 새 탭을 연다. 하나라도 작업 중이면 작업 중이다."""
    best, rank = {}, lambda s: (not s.orphan, not s.desktop, s.status_updated_at)
    for s in out:
        b = best.get(s.session_id)
        if b is None or rank(s) > rank(b):
            if b is not None and b.state == WORKING:
                s.state = WORKING
            best[s.session_id] = s
        elif s.state == WORKING:
            b.state = WORKING
    return [s for s in out if best[s.session_id] is s]


def _live(tracker, prev, tcache):
    """레지스트리 → 꼬리 → D1 판정 → 프로젝트 귀속. `C:\\dev` 바깥 세션은 버린다."""
    now = time.time()
    regs, rejected, failures = collect_fs.read_registry()
    out, keys, live_paths = [], set(), set()
    for reg in regs:
        project = paths.attribute_cwd(reg.get("cwd") or "")
        if project is None:
            continue
        key = status.tracker_key(reg)           # status.decide와 같은 키여야 HOLD가 맞는다
        keys.add(key)
        # 꼬리 경로는 RAW cwd의 슬러그다 — 화면에서 귀속된 프로젝트의 슬러그가 아니다.
        path = collect_fs.find_transcript(reg)
        # 방어 상한: 이 수를 넘는 세션은 꼬리를 읽지 않고 레지스트리만으로 판정한다(행 4/5).
        read_tail = path and len(out) < config.LIVE_TAIL_MAX_FILES
        last, tab_title = _tail(path, tcache) if read_tail else _NO_TAIL
        if read_tail:
            live_paths.add(path)
        state, disagree = status.decide(reg, last, tracker)
        if state is None:                       # D1 행 6 HOLD — 직전 상태를 그대로 유지
            state = prev.get(key, WORKING)
        prev[key] = state
        pid = int(reg.get("pid") or 0)
        desktop = reg.get("entrypoint") == config.DESKTOP_ENTRYPOINT
        bg = reg.get("kind") == "bg"
        jump = desktop or term.can_jump(pid)
        # 창을 닫았는데 프로세스만 남은 세션: 창도 없고 띄운 셸도 없다 → 새 탭에서 이어 열게 한다
        orphan = not jump and not bg and term.launcher_gone(pid)
        # [점프] 가능 여부는 여기서 미리 판정한다 — 세션당 ≈6 ms(psutil 조상 2단 + EnumWindows
        # 1회)라 렌더 경로에서는 부를 수 없다. 남기는 것은 불리언뿐이고 hwnd는 버린다(SI-7).
        out.append(LiveSession(
            pid=pid, session_id=reg.get("sessionId") or "",
            cwd=reg.get("cwd") or "", status=reg.get("status") or "",
            status_updated_at=status._su_seconds(reg.get("statusUpdatedAt"), now) or 0.0,
            proc_start=collect_fs.procstart_to_unix(reg.get("procStart")) or 0.0,
            name=reg.get("name") or "", project=project, transcript_path=path,
            state=state, sources_disagree=disagree, shell_tag=status.shell_tag(reg),
            jumpable=jump or orphan, tab_title=tab_title, background=bg, desktop=desktop, orphan=orphan))
    out = _merge_same_sid(_merge_parked(out, regs))
    for k in [k for k in prev if k not in keys]:
        prev.pop(k, None)
        tracker.forget(k)
    for p in [p for p in tcache if p not in live_paths]:   # 살아있지 않은 경로는 버린다
        tcache.pop(p, None)
    return out, rejected, failures
