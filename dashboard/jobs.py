"""작업 모니터. 프로세스를 분류(classify)하고 '작업'만 모은다(scan).

어떤 프로세스도 건드리지 않는다 — 읽기만 한다(SI-1).
psutil 첫 호출의 워밍업(≈1.7 s)은 여기가 아니라 **빠른 워커의 `collect_fs.read_registry`**
(`pid_exists`/`Process`)에서 일어난다 — 그래서 첫 fast 틱이 한 번 0.5 s를 넘길 수 있다.
여기 `scan`의 첫 호출(≈600 ms)은 느린 워커 몫이고, 두 번째부터는 캐시 덕에 100 ms 미만이다.
어느 쪽도 UI 스레드에서는 절대 부르지 않는다.
"""
import os
import time

import psutil

import config

ROOT_KEY = "."   # paths.ROOT_KEY와 같은 값을 미러링한다(그 모듈을 아직 import하지 않는다)

_SKIP = (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess)
_DEV = os.path.normpath(config.DEV_ROOT).rstrip(os.sep).lower()
_OWN = os.path.normpath(config.OWN_DIR).rstrip(os.sep).lower()
_HIDDEN = {n.lower() for n in config.HIDDEN_NAMES}
_SELF_MARK = os.path.join(os.path.basename(config.OWN_DIR), "app.py").lower()
_MARKERS = tuple(m.lower() for m in config.NODE_HELPER_MARKERS)
# 환경 변수가 비어 만들어진 상대 경로 조각(예: 'npm\\')은 아무 exe에나 걸리므로 버린다.
_HELPER_DIRS = tuple(d.lower() for d in config.HELPER_EXE_DIRS
                     if d and (os.path.splitdrive(d)[0] or d.startswith(os.sep)))


def _project_of(cwd, projects):
    """cwd → 프로젝트 이름(대소문자 무시). C:\\dev 자신은 루트 프로젝트(ROOT_KEY).
    자기 폴더·숨김 폴더·C:\\dev 바깥·목록에 없는 폴더는 None."""
    if not cwd:
        return None
    c = os.path.normpath(cwd).rstrip(os.sep).lower()
    if c == _DEV:
        return ROOT_KEY
    if not c.startswith(_DEV + os.sep):
        return None
    if c == _OWN or c.startswith(_OWN + os.sep):
        return None
    parts = c[len(_DEV) + 1:].split(os.sep)
    for part in parts:
        if part.startswith(config.HIDDEN_NAME_PREFIXES) or part in _HIDDEN:
            return None
    for p in projects:
        if p.lower() == parts[0]:
            return p
    return None


def classify(info, own_pid, projects, now, parent=None):
    """계획서 Step 5의 7개 규칙을 위에서부터 그대로 적용한다(+ 규칙 4b·4c).
    info 키: pid, name, exe, cmdline(list|None), cwd, create_time. parent도 같은 모양(없으면 None)."""
    name = (info.get("name") or "").lower()
    exe = (info.get("exe") or "").lower()
    cmd = " ".join(info.get("cmdline") or ()).lower()
    if info.get("pid") == own_pid or _SELF_MARK in cmd:
        return "self", None
    if name in config.SHELL_NAMES:
        return "shell", None
    for d in _HELPER_DIRS:
        if d in exe:
            return "helper", None
    if name in config.NODE_NAMES and any(m in cmd for m in _MARKERS):
        return "helper", None
    # 4b. venv python.exe는 실제 인터프리터를 자식으로 한 번 더 띄우는 중계기다 — 같은
    #     명령줄의 자식은 부모와 같은 프로세스로 보고 한 줄만 남긴다(부모 쪽을 판정한다).
    if parent and info.get("cmdline") and parent.get("cmdline") == info.get("cmdline"):
        return "dup", None
    # 4c. claude.exe가 **직접** 띄운 프로세스는 MCP 서버다(2026-09-22 사용자 결정으로 숨김).
    #     명령 실행 도구로 띄운 실험은 셸(bash/powershell)을 거치므로 여기 걸리지 않고 계속 보인다.
    if parent and (parent.get("name") or "").lower() in config.CLAUDE_NAMES:
        return "helper", None
    project = _project_of(info.get("cwd"), projects)
    if project is None:
        return "excluded", None
    if now - (info.get("create_time") or 0) < config.JOB_MIN_ELAPSED_SEC:
        return "young", project
    return "job", project


def _safe(fn):
    """AccessDenied/NoSuchProcess/ZombieProcess는 정상 상황이다 — 조용히 None."""
    try:
        return fn()
    except _SKIP:
        return None


def scan(cache, projects, now=None):
    """'작업'만 추려 반환한다. cache 키 (pid, create_time) → name/exe/cmdline/cwd.
    이미 본 프로세스는 cmdline()/cwd()를 다시 부르지 않고, 사라진 pid의 키는 지운다."""
    now = time.time() if now is None else now
    own_pid = os.getpid()
    seen, out, by_pid = set(), [], {}
    for proc in psutil.process_iter(attrs=["pid", "name", "create_time", "ppid"]):
        raw = proc.info
        if raw.get("create_time") is None:
            continue
        key = (raw["pid"], raw["create_time"])
        seen.add(key)
        info = cache.get(key)
        if info is None:
            try:
                with proc.oneshot():
                    info = {"pid": raw["pid"], "name": raw.get("name") or "",
                            "create_time": raw["create_time"], "ppid": raw.get("ppid"),
                            "exe": _safe(proc.exe), "cmdline": _safe(proc.cmdline),
                            "cwd": _safe(proc.cwd)}
            except _SKIP:
                continue
            cache[key] = info
        by_pid[info["pid"]] = info

    def parent_of(i):
        """pid 재사용 가드: 부모는 반드시 자식보다 먼저 태어났다."""
        p = by_pid.get(i.get("ppid")) if i else None
        return p if p and p["create_time"] <= i["create_time"] else None

    for info in by_pid.values():
        kind, project = classify(info, own_pid, projects, now, parent_of(info))
        if kind == "job":
            out.append({"pid": info["pid"], "create_time": info["create_time"],
                        "name": info["name"], "cwd": info["cwd"], "project": project,
                        "elapsed": now - info["create_time"]})
    for key in [k for k in cache if k not in seen]:
        del cache[key]
    return out


def format_elapsed(seconds):
    """1분 / 12분 / 1시간 5분 / 2일 3시간."""
    minutes = int(max(0.0, seconds) // 60)
    if minutes < 60:
        return "%d분" % minutes
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return "%d시간 %d분" % (hours, minutes)
    days, hours = divmod(hours, 24)
    return "%d일 %d시간" % (days, hours)


def display(job):
    return "▶ %s %s" % (job["name"], format_elapsed(job["elapsed"]))
