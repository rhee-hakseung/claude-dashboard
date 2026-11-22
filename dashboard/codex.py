"""Codex(OpenAI의 코딩 도구) 세션 수집. `~/.codex` 아래는 **읽기만** 한다.

Claude Code와 달리 Codex에는 `<pid>.json` 같은 레지스트리가 없다(2026-11-22 실측, codex-cli 0.171):
- 세션(thread) 목록은 `~/.codex/state_<n>.sqlite`의 `threads` 표에 있다(id·cwd·이름·갱신 시각·보관 여부).
- 살아 있는 세션은 프로세스로 알아본다: 터미널에서 띄운 `codex`(하위 명령이 없거나 resume/fork).
- 프로세스 ↔ thread: `codex resume <id>`는 명령줄에 id가 있다. 새 세션은 thread id(UUIDv7)에 든
  시각이 프로세스가 뜬 시각과 같다(`thread-writer-locks/<id>.lock`도 그 순간 생긴다 — 이름만 본다).
- 작업 중/기다림: 기록(rollout .jsonl)의 마지막 `task_started` / `task_complete` / `turn_aborted`.
  기록을 못 읽으면 `thread_history_<n>.sqlite`의 마지막 turn으로 대신한다.

대화 내용은 읽지 않는다 — 제목(이름, 없으면 첫 메시지 앞부분)과 이벤트 종류만 쓴다.
프로세스 탐색·sqlite 읽기는 수집 스레드에서만 부른다.
"""
from __future__ import annotations

import glob
import os
import pathlib
import re
import sqlite3
import time

import psutil

import config
import paths
import term
from model import WAITING, WORKING, EndedSession, LiveSession

AGENT = "codex"
KEY = "codex:"                  # EndedSession.path 자리에 넣는 식별자 — 파일 경로가 아니다
NAMES = {"codex.exe", "codex"}
PROC_PERIOD_SEC = 2.0           # 프로세스 전체 훑기 주기(그 사이 틱은 직전 목록을 쓴다)
NEW_THREAD_WINDOW = (-2.0, 20.0)   # thread id 시각 − 프로세스 시작 시각의 허용 범위(초)
TAIL_BYTES = (256 * 1024, 4 * 1024 * 1024)   # 기록 꼬리 창: 못 찾으면 한 번 넓힌다(사진이 든 줄은 수 MB)
# 창이 없는 실행(서버·일괄 실행·관리 명령). 이 중 하나가 인자에 있으면 화면에 띄우는 세션이 아니다.
_BATCH = {"exec", "e", "review", "login", "logout", "mcp", "plugin", "app-server", "remote-control", "app",
          "completion", "update", "doctor", "sandbox", "debug", "apply", "a", "queue", "archive", "delete",
          "migrate-rollouts", "migrate-nfs-db", "unarchive", "cloud", "exec-server", "features", "help",
          "--help", "-h", "--version", "-V"}
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_EVENT = re.compile(rb'"type":"event_msg","payload":\{"type":"(task_started|turn_started|task_complete'
                    rb'|turn_complete|turn_aborted)"')
_STARTED = {"task_started", "turn_started"}


# ── 순수 함수 ─────────────────────────────────────────────────────────────────
def clean_cwd(cwd) -> str:
    """`\\\\?\\C:\\…`(Windows 긴 경로 표기)를 벗기고 정규화한다. 문자열이 아니면 빈 문자열."""
    if not isinstance(cwd, str) or not cwd:
        return ""
    if cwd.startswith("\\\\?\\"):
        cwd = cwd[4:]
    return os.path.normpath(cwd)


def interactive(cmdline):
    """명령줄 → `(화면에 띄운 세션인가, resume로 지정한 thread id 또는 None)`."""
    args = list(cmdline or ())[1:]
    for i, a in enumerate(args):
        if a in _BATCH:
            return False, None
        if a in ("resume", "fork"):
            ids = [x for x in args[i + 1:] if UUID.match(x)]
            return True, (ids[0].lower() if a == "resume" and ids else None)
    return True, None


def uuid7_time(tid):
    """UUIDv7 앞 48비트 = 만든 시각(ms). v7이 아니면 None."""
    h = tid.replace("-", "") if isinstance(tid, str) else ""
    if len(h) != 32 or h[12] != "7":
        return None
    try:
        return int(h[:12], 16) / 1000.0
    except ValueError:
        return None


def _same(a, b):
    return os.path.normcase(a) == os.path.normcase(b)


def match_threads(procs, threads, locks):
    """프로세스 → thread id. `procs`: `[{pid, cwd, start, resume}]`, `threads`: `{id: {cwd, updated}}`,
    `locks`: 잠금 파일에서 본 id들. 한 thread는 한 프로세스에만 붙는다. 못 찾으면 None.
    ① 명령줄의 `resume <id>` ② 새 세션: id에 든 시각이 프로세스 시작 시각과 같은 것(가장 가까운 것)
    ③ 고르기 화면·`--last`로 이은 세션: 같은 폴더에서 프로세스가 뜬 뒤 갱신된 thread 중 최신."""
    out, used = {}, set()
    lo, hi = NEW_THREAD_WINDOW
    for p in sorted(procs, key=lambda p: p["start"]):
        tid = p.get("resume")
        if tid is None:
            near = []
            for t in set(threads) | set(locks):
                at = uuid7_time(t)
                if t in used or at is None or not lo <= at - p["start"] <= hi:
                    continue
                if t in threads and not _same(threads[t]["cwd"], p["cwd"]):
                    continue
                near.append((abs(at - p["start"]), t))
            tid = min(near)[1] if near else None
        if tid is None:
            later = [(th["updated"], t) for t, th in threads.items()
                     if t not in used and _same(th["cwd"], p["cwd"]) and th["updated"] >= p["start"]]
            tid = max(later)[1] if later else None
        out[p["pid"]] = tid
        if tid:
            used.add(tid)
    return out


def last_event(data: bytes):
    """기록 꼬리(바이트)에서 마지막 turn 이벤트 이름. 없으면 None. 따옴표가 이스케이프되지 않은
    구조만 맞추므로 메시지 본문 속 같은 글자는 걸리지 않는다."""
    hits = _EVENT.findall(data)
    return hits[-1].decode("ascii") if hits else None


def _title(row) -> str:
    """이름(Codex가 붙였거나 사용자가 바꾼 것) → 없으면 첫 메시지 앞부분(Claude 쪽과 같은 규칙)."""
    name = row.get("name")
    if isinstance(name, str) and name.strip():
        return " ".join(name.split())
    for k in ("title", "first_user_message", "preview"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return " ".join(v.split())[:config.NAME_FALLBACK_CHARS]
    return ""


def thread_from_row(row):
    """`threads` 표의 한 줄(dict) → 우리가 쓰는 dict. 쓸 수 없는 줄(하위 에이전트 등)은 None.
    열은 버전마다 늘어나므로 있는 것만 읽는다."""
    tid, cwd = row.get("id"), clean_cwd(row.get("cwd"))
    if not isinstance(tid, str) or not UUID.match(tid) or not cwd:
        return None
    if row.get("agent_role") or row.get("attached_thread_parent_id"):
        return None
    ms, sec = row.get("updated_at_ms"), row.get("updated_at")
    updated = ms / 1000.0 if isinstance(ms, (int, float)) and ms else float(sec) if isinstance(sec, (int, float)) else 0.0
    rollout = row.get("rollout_path")
    return {"id": tid.lower(), "cwd": cwd, "title": _title(row), "updated": updated,
            "archived": bool(row.get("archived")),
            "rollout": clean_cwd(rollout) if isinstance(rollout, str) else ""}


# ── 읽기(sqlite·파일·프로세스) ────────────────────────────────────────────────
def available() -> bool:
    return os.path.isdir(config.CODEX_HOME)


def _db(prefix):
    """`~/.codex/<prefix>_<n>.sqlite` 중 n이 가장 큰 것 — Codex가 올라가면 숫자가 바뀐다."""
    best = None
    for p in glob.glob(os.path.join(config.CODEX_HOME, prefix + "_*.sqlite")):
        m = re.search(r"_(\d+)\.sqlite$", p)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), p)
    return best[1] if best else None


def _rows(prefix, sql, args=()):
    """읽기 전용(`mode=ro`)으로 열어 바로 닫는다. 파일이 없으면 빈 목록, 그 밖의 오류는 올린다."""
    path = _db(prefix)
    if not path:
        return []
    con = sqlite3.connect(pathlib.Path(path).as_uri() + "?mode=ro", uri=True, timeout=0.3)
    try:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def threads() -> dict:
    out = {}
    for row in _rows("state", "select * from threads"):
        th = thread_from_row(row)
        if th:
            out[th["id"]] = th
    return out


def _locks():
    """잠금 파일 **이름**에서 thread id만 얻는다(내용은 열지 않는다)."""
    try:
        names = os.listdir(os.path.join(config.CODEX_HOME, "thread-writer-locks"))
    except OSError:
        return set()
    return {n[:-5].lower() for n in names if n.endswith(".lock") and UUID.match(n[:-5])}


def _scan():
    """화면에 띄운 codex 프로세스들. 감싼 프로세스와 그 자식이 둘 다 codex면 바깥쪽(셸에 가까운 쪽)만 남긴다."""
    found = {}
    for p in psutil.process_iter(["pid", "name"]):
        if (p.info["name"] or "").lower() not in NAMES:
            continue
        try:
            ok, rid = interactive(p.cmdline())
            if ok:
                found[p.pid] = {"pid": p.pid, "ppid": p.ppid(), "cwd": clean_cwd(p.cwd()),
                                "start": p.create_time(), "resume": rid}
        except (psutil.Error, OSError):
            continue
    return [p for p in found.values() if p["ppid"] not in found and p["cwd"]]


def _tail_event(path, cache):
    """기록 파일의 마지막 turn 이벤트. `(크기, mtime)`이 같으면 직전 결과를 쓴다. → `(이벤트, mtime)`."""
    try:
        st = os.stat(path)
    except OSError:
        return None, 0.0
    key = (st.st_size, st.st_mtime_ns)
    hit = cache.get(path)
    if hit and hit[0] == key:
        return hit[1], st.st_mtime
    ev = None
    try:
        with open(path, "rb") as fh:
            for window in TAIL_BYTES:
                fh.seek(max(0, st.st_size - window))
                ev = last_event(fh.read())
                if ev or window >= st.st_size:
                    break
    except OSError:
        return None, st.st_mtime
    cache[path] = (key, ev)
    return ev, st.st_mtime


def _turn_open(tid) -> bool:
    """기록에서 못 읽었을 때의 대안: 마지막 turn이 아직 안 끝났는가."""
    try:
        rows = _rows("thread_history", "select completed_at from thread_turns where thread_id = ? "
                     "order by rollout_ordinal desc limit 1", (tid,))
    except (sqlite3.Error, OSError):
        return False
    return bool(rows) and rows[0].get("completed_at") is None


def live_sessions(memo: dict, now=None) -> list[LiveSession]:
    """지금 떠 있는 Codex 세션(프로젝트 폴더 안의 것만). `memo`는 호출자가 들고 있는 캐시다."""
    now = time.time() if now is None else now
    if now >= memo.get("due", 0.0):
        memo["due"], memo["procs"] = now + PROC_PERIOD_SEC, _scan()
    procs = [p for p in memo.get("procs", ()) if paths.attribute_cwd(p["cwd"]) is not None
             and psutil.pid_exists(p["pid"])]
    if not procs:
        memo.pop("tails", None)
        return []
    ths = threads()
    ids = match_threads(procs, ths, _locks())
    tails, out = memo.setdefault("tails", {}), []
    for p in procs:
        pid, tid = p["pid"], ids.get(p["pid"])
        th = ths.get(tid) or {}
        ev, mtime = _tail_event(th["rollout"], tails) if th.get("rollout") else (None, 0.0)
        working = ev in _STARTED if ev else bool(th) and _turn_open(tid)
        jump = term.can_jump(pid)
        orphan = not jump and term.launcher_gone(pid)
        out.append(LiveSession(
            pid=pid, session_id=tid or "codex-pid-%d" % pid, cwd=p["cwd"], status="",
            status_updated_at=max(mtime, th.get("updated", 0.0)) or p["start"], proc_start=p["start"],
            name=th.get("title", ""), project=paths.attribute_cwd(p["cwd"]),
            transcript_path=th["rollout"] if mtime else None,
            state=WORKING if working else WAITING,
            jumpable=jump or (orphan and bool(th)),     # 기록이 없는 세션은 이어 열 수 없다
            orphan=orphan, agent=AGENT,
            tab_title=os.path.basename(p["cwd"]) or AGENT))   # Codex의 탭 제목 = 폴더 이름(실측)
    return out


def ended_sessions(live_ids) -> list[EndedSession]:
    """끝난 Codex 세션: 보관(archive)하지 않았고 지금 떠 있지 않은 thread 중 프로젝트 폴더 안의 것."""
    rows = []
    for tid, th in threads().items():
        project = paths.attribute_cwd(th["cwd"])
        if th["archived"] or tid in live_ids or project is None:
            continue
        rows.append(EndedSession(
            slug="", session_id=tid, path=KEY + tid, project=project, mtime=th["updated"], size=0,
            title=th["title"] or tid[:8], is_stub=not th["title"],
            resume_dir=th["cwd"] if os.path.isdir(th["cwd"]) else None, agent=AGENT,
            activity_path=th["rollout"] if th["rollout"] and os.path.isfile(th["rollout"]) else None))
    return rows
