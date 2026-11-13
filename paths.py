"""경로 → 슬러그 인코딩과 프로젝트 귀속.

**슬러그는 절대 디코딩하지 않는다** — `C--dev-process-game`은 `C:\\dev\\process-game`과
`C:\\dev\\process\\game` 양쪽에서 나온다. 실제 경로를 인코딩해서 대조만 한다.

**화면 귀속과 transcript 경로는 별개다.** 화면 귀속은 `C:\\dev\\<X>` 규칙(또는 끝난 기록이면
파일이 놓인 슬러그 폴더)이고, 라이브 세션의 꼬리 파일 경로는 `slug(session.cwd)`다.
`cwd = C:\\dev\\process-game\\game`인 세션은 프로젝트 `process-game`에 보이지만 기록은
`C--dev-process-game-game\\`에 있다.
"""
from __future__ import annotations

import os
import re

import config

ROOT_KEY = "."  # `C:\dev` 자신을 가리키는 센티널 (화면 표시는 config.ROOT_LABEL)


def slug(path: str) -> str:
    """Claude Code의 인코딩 규칙: 영숫자가 아닌 모든 문자를 `-`로."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def _norm(p: str) -> str:
    """`/`를 `\\`로, 끝 슬래시 제거. 대소문자는 보존한다(비교할 때만 낮춘다)."""
    return os.path.normpath(p.replace("/", os.sep))


def attribute_cwd(cwd: str, dev_root: str = config.DEV_ROOT) -> str | None:
    """① `cwd == C:\\dev` → ROOT_KEY ② `C:\\dev\\<X>` 이하 → `X` ③ 그 외 → None."""
    if not cwd:
        return None
    c, r = _norm(cwd), _norm(dev_root)
    if c.lower() == r.lower():
        return ROOT_KEY
    pre = r + os.sep
    if c[: len(pre)].lower() != pre.lower():
        return None
    rest = c[len(pre):].split(os.sep)[0]
    return rest or None


def attribute_slug(folder_slug: str, projects: list[str],
                   dev_root: str = config.DEV_ROOT) -> str | None:
    """끝난 기록의 귀속: 실제 프로젝트 목록을 인코딩해 폴더 슬러그와 대조한다.

    완전 일치 우선, 없으면 `slug(project) + "-"` 접두 일치 중 가장 긴 것.
    `slug(dev_root)` 완전 일치는 루트 줄.
    """
    fs = folder_slug.lower()
    root = _norm(dev_root)
    if fs == slug(root).lower():
        return ROOT_KEY
    best, best_len = None, -1
    for p in projects:
        if p == ROOT_KEY:
            continue
        s = slug(os.path.join(root, p))
        if s.lower() == fs:
            return p
        if fs.startswith(s.lower() + "-") and len(s) > best_len:
            best, best_len = p, len(s)
    return best


def resume_dir(folder_slug: str, cwd_candidates: list[str],
               project_dir: str | None) -> str | None:
    """[재개] 실행 폴더: cwd 후보(꼬리의 마지막 → 머리의 첫) 중 슬러그가 폴더와 같은 첫 값,
    없으면 프로젝트 경로의 슬러그가 폴더와 같을 때 그 경로, 그래도 없으면 None(비활성)."""
    fs = folder_slug.lower()
    for c in cwd_candidates or ():
        if c and slug(_norm(c)).lower() == fs:
            return _norm(c)
    if project_dir and slug(_norm(project_dir)).lower() == fs:
        return _norm(project_dir)
    return _find_nested(fs, _norm(project_dir)) if project_dir else None


def _find_nested(fs, base):
    """프로젝트 안 하위 폴더로 옮겨진 기록(2026-11-12: process-game → SPI\\project\\process-game).
    기록 속 cwd는 옛 경로라 맞지 않으므로 슬러그가 같은 실제 폴더를 찾는다. 슬러그가 `fs`의
    접두인 폴더로만 내려가므로 몇 번의 scandir로 끝난다."""
    try:
        entries = [e for e in os.scandir(base) if e.is_dir()]
    except OSError:
        return None
    for e in entries:
        s = slug(e.path).lower()
        if s == fs:
            return e.path
        if fs.startswith(s + "-"):
            hit = _find_nested(fs, e.path)
            if hit:
                return hit
    return None
