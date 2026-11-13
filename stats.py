"""프로젝트 현황(git 상태·폴더 용량·최근 활동 막대) — 느린 것들이라 전용 스레드 하나에서만 돈다.

화면(web_view)은 `Stats.get(name)`으로 마지막 값만 읽는다. 아무것도 쓰지 않는다: git은
`--no-optional-locks status`(인덱스를 고치지 않는다)만 부르고, 용량은 scandir로 합산할 뿐이다.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import date

import activity
import paths

log = logging.getLogger("dev-dashboard")

GIT_PERIOD_SEC = 60.0
SIZE_PERIOD_SEC = 1800.0
ACTIVITY_PERIOD_SEC = 60.0
ACTIVITY_DAYS = 14
GIT_TIMEOUT_SEC = 15
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # Windows 밖에서는 0이어야 한다


def parse_git_status(text: str) -> dict:
    """`git status --porcelain --branch` 출력 → `{"branch", "dirty"}`. 첫 줄 `## main...origin/main [ahead 1]`."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    head = lines[0][3:] if lines and lines[0].startswith("## ") else ""
    if head.startswith("No commits yet on "):
        head = head[len("No commits yet on "):]
    branch = head.split("...")[0].split(" ")[0]
    return {"branch": branch, "dirty": sum(1 for ln in lines if not ln.startswith("## "))}


def git_info(path: str, run=subprocess.run, exe=None):
    """git 저장소가 아니면 None. 실패(시간 초과 등)도 None — 화면은 'git 없음'과 구분하지 않는다."""
    exe = exe or shutil.which("git")
    if not exe or not os.path.exists(os.path.join(path, ".git")):
        return None
    try:
        r = run([exe, "--no-optional-locks", "-C", path, "status", "--porcelain", "--branch"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=GIT_TIMEOUT_SEC, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_git_status(r.stdout) if r.returncode == 0 else None


def dir_size(path: str, stop=None):
    """폴더 전체 바이트 수(심볼릭 링크는 따라가지 않는다). 멈춤 신호가 오면 None."""
    total, stack = 0, [path]
    while stack:
        if stop is not None and stop.is_set():
            return None
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif not e.is_symlink():
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


class Stats:
    """`{프로젝트 이름: {"git", "size", "spark"}}` — Lock 하나로 보호한다."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}

    def put(self, name, **fields):
        with self._lock:
            self._data.setdefault(name, {}).update(fields)

    def get(self, name) -> dict:
        with self._lock:
            return dict(self._data.get(name, {}))


def transcripts_by_project(snap) -> dict:
    """활동 막대의 입력: 프로젝트별 transcript 경로(같은 대화의 복사본은 한 번만 센다)."""
    out: dict[str, list] = {}
    for s in snap.live:
        if s.transcript_path and s.project:
            out.setdefault(s.project, []).append(s.transcript_path)
    for e in snap.ended:
        if e.project and not e.duplicate_of_newer:
            out.setdefault(e.project, []).append(e.path)
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def loop(store, stop, stats):
    """한 바퀴에 일 하나씩만 한다(git 1개 또는 용량 1개) — 한꺼번에 몰리지 않게."""
    due, acache = {}, {}
    while not stop.is_set():
        try:
            now, snap = time.time(), store.read()
            if now >= due.get("activity", 0.0) and snap.projects:
                due["activity"] = now + ACTIVITY_PERIOD_SEC
                hist = activity.histogram(transcripts_by_project(snap), acache, date.today(),
                                          ACTIVITY_DAYS)
                for p in snap.projects:
                    stats.put(p.name, spark=hist.get(p.name, [0] * ACTIVITY_DAYS))
            for p in snap.projects:
                if now >= due.get(("git", p.name), 0.0):
                    due[("git", p.name)] = now + GIT_PERIOD_SEC
                    stats.put(p.name, git=git_info(p.path))
                    break
                if p.name != paths.ROOT_KEY and now >= due.get(("size", p.name), 0.0):
                    due[("size", p.name)] = now + SIZE_PERIOD_SEC
                    stats.put(p.name, size=dir_size(p.path, stop))
                    break
        except Exception:
            log.exception("stats worker")
        stop.wait(0.5)
