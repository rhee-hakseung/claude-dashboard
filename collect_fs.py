"""프로젝트 scandir + 라이브 레지스트리 읽기 + stale 필터.

`~/.claude` 아래는 읽기 전용이다. 글롭은 `*.json`만 — 형제 `*.key` 파일은 원천 배제한다.
거절된(stale) 레지스트리 파일은 무시할 뿐 절대 삭제·수정하지 않는다.
"""
from __future__ import annotations

import glob
import json
import os
import time

import psutil

import config
import paths
from model import Project

FILETIME_EPOCH_DIFF = 11644473600.0   # 1601-01-01 → 1970-01-01 (초)


def procstart_to_unix(s, now=None):
    """레지스트리 `procStart` → unix 초. Windows는 100 ns 틱 FILETIME 문자열이다. 다른 OS의 형식은
    확인하지 못했으므로 FILETIME·밀리초·초를 차례로 시도해 그럴듯한 시각(2000년 ~ 지금+1일)만 받고,
    아니면 None을 돌려준다(그때는 pid 생존만으로 판정한다)."""
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    now = time.time() if now is None else now
    for t in ((v / 1e7 - FILETIME_EPOCH_DIFF) if v > 1e16 else None, v / 1000.0, v):
        if t is not None and 946684800 <= t <= now + 86400:
            return t
    return None


def scan_projects(dev_root: str = config.DEV_ROOT) -> list[Project]:
    """`C:\\dev` 직계 폴더 1개 = 프로젝트 1개. 점 폴더와 HIDDEN_NAMES는 제외, 루트 줄 추가."""
    hidden = {n.lower() for n in config.HIDDEN_NAMES}
    out: list[Project] = []
    try:
        with os.scandir(dev_root) as it:
            for e in it:
                try:
                    if not e.is_dir(follow_symlinks=False):
                        continue
                    if e.name.startswith(config.HIDDEN_NAME_PREFIXES) or e.name.lower() in hidden:
                        continue
                    out.append(Project(e.name, e.path, e.stat().st_mtime, False))
                except OSError:
                    continue
    except OSError:
        pass
    try:
        root_mtime = os.path.getmtime(dev_root)
    except OSError:
        root_mtime = 0.0
    out.append(Project(paths.ROOT_KEY, dev_root, root_mtime, True))
    return out


def _well_typed(reg) -> bool:
    """레지스트리 타입 드리프트 방어. `status`에 숫자가 오면 `.lower()`가 터지고,
    `cwd`에 dict가 오면 슬러그 인코딩이 터진다 — 빠른 틱이 통째로 죽는다."""
    if not isinstance(reg, dict):
        return False
    for k in ("status", "cwd", "sessionId"):
        if k in reg and not isinstance(reg[k], str):
            return False
    return isinstance(reg.get("pid"), int) and not isinstance(reg.get("pid"), bool)


def read_registry(sessions_dir: str = config.SESSIONS_DIR,
                  now: float | None = None) -> tuple[list[dict], int, int]:
    """→ `(살아있는 레코드, 거절 수, 실패 수)`.

    stale 필터: `psutil.pid_exists(pid)` ∧ `|create_time - procStart| <= 허용 오차`.
    `now`는 테스트 주입용으로 열어 둔다(판정은 psutil 실측 시각만 쓴다).
    """
    accepted: list[dict] = []
    rejected = failures = 0
    for f in sorted(glob.glob(os.path.join(sessions_dir, "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                reg = json.load(fh)
            if not _well_typed(reg):
                failures += 1
                continue
            pid = int(reg["pid"])
            started = procstart_to_unix(reg.get("procStart"))
            if not psutil.pid_exists(pid):
                rejected += 1
                continue
            if started is not None and \
                    abs(psutil.Process(pid).create_time() - started) > config.PROCSTART_TOLERANCE_SEC:
                rejected += 1
                continue
            accepted.append(reg)
        except (json.JSONDecodeError, OSError, UnicodeError, KeyError, TypeError,
                ValueError, psutil.Error):
            failures += 1
    return accepted, rejected, failures


def find_transcript(session: dict, projects_dir: str = config.PROJECTS_DIR) -> str | None:
    """빠른 경로는 `slug(session.cwd)` — 그 세션이 화면에서 귀속된 프로젝트의 슬러그가 아니다.
    파일이 없으면 `*/<sessionId>.jsonl` 글롭에서 최신 mtime을 쓴다(세션 중 cwd가 바뀐다)."""
    sid = session.get("sessionId")
    if not sid:
        return None
    cwd = session.get("cwd") or ""
    if cwd:
        fast = os.path.join(projects_dir, paths.slug(cwd), sid + ".jsonl")
        if os.path.exists(fast):
            return fast
    best, best_mtime = None, -1.0
    for p in glob.glob(os.path.join(projects_dir, "*", sid + ".jsonl")):
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if m > best_mtime:
            best, best_mtime = p, m
    return best


def last_activity(project: Project, slug_mtimes: dict[str, float], live: list) -> float:
    """AC-P2: `max(그 프로젝트 기록들의 최신 mtime, 라이브 statusUpdatedAt)`.
    폴더 mtime은 **둘 다 없을 때만** 쓰는 fallback이다(계획서: "없으면 폴더 mtime") —
    max에 섞으면 빌드 산출물이 바꾼 폴더 mtime이 실제 활동 시각을 덮어쓴다."""
    best = slug_mtimes.get(project.name, 0.0)
    for s in live:
        if s.project == project.name and s.status_updated_at > best:
            best = s.status_updated_at
    return best or project.last_activity
