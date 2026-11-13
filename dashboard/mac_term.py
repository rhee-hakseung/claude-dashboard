"""macOS의 창 다루기: 새 터미널 창 열기, [점프](claude가 도는 탭 찾아 앞으로), 창 자리 검사.

[점프]는 claude 프로세스의 tty(`/dev/ttys003` 꼴)를 Terminal·iTerm2의 탭 tty와 대조한다 — 탭 제목은
보지 않는다. 처음 한 번 macOS가 "Terminal을 제어하도록 허용" 여부를 묻는다(시스템 설정 → 개인정보
보호 및 보안 → 자동화). 다른 터미널(VS Code, Ghostty, Warp, tmux 안 …)의 세션은 [점프]가 꺼진다.
AppleScript에는 값을 문자열로 끼우지 않고 `on run argv` 인자로 넘긴다(따옴표 이스케이프 문제가 없다).
"""
from __future__ import annotations

import logging
import re
import shlex
import subprocess

import psutil

import config

log = logging.getLogger("dev-dashboard")
HOSTS = {"terminal": "Terminal", "iterm2": "iTerm2"}    # 조상 프로세스 이름(소문자) → 앱 이름
_TTY = re.compile(r"^/dev/[A-Za-z0-9]+$")
JUMP_TIMEOUT_SEC = 15      # 첫 실행의 '자동화 허용' 대화상자에 답할 시간

_JUMP = {
    "Terminal": """on run argv
  tell application "Terminal"
    repeat with w in windows
      repeat with t in tabs of w
        if tty of t is (item 1 of argv) then
          set selected of t to true
          try
            set miniaturized of w to false
          end try
          set index of w to 1
          activate
          return "ok"
        end if
      end repeat
    end repeat
  end tell
  return "none"
end run""",
    "iTerm2": """on run argv
  tell application "iTerm2"
    repeat with w in windows
      repeat with t in tabs of w
        repeat with s in sessions of t
          if tty of s is (item 1 of argv) then
            tell w to select
            tell t to select
            tell s to select
            activate
            return "ok"
          end if
        end repeat
      end repeat
    end repeat
  end tell
  return "none"
end run""",
}

_OPEN = {
    "Terminal": """on run argv
  tell application "Terminal"
    activate
    do script (item 1 of argv)
  end tell
end run""",
    "iTerm2": """on run argv
  tell application "iTerm2"
    activate
    set w to (create window with default profile)
    tell current session of w to write text (item 1 of argv)
  end tell
end run""",
}


def host_of(pid):
    """claude pid → `(앱 이름, tty)`. 조상 중 Terminal·iTerm2가 없거나 tty가 없으면 None."""
    try:
        proc = psutil.Process(int(pid))
        tty = proc.terminal()
        if not tty or not _TTY.match(tty):
            return None
        for parent in proc.parents()[:8]:
            app = HOSTS.get(parent.name().lower())
            if app:
                return app, tty
    except (psutil.Error, ValueError, TypeError):
        return None
    return None


def can_jump(pid) -> bool:
    return host_of(pid) is not None


def jump(pid) -> bool:
    """그 세션의 탭을 골라 창과 앱을 앞으로. 어떤 오류든 False(예외를 올리지 않는다)."""
    hit = host_of(pid)
    if not hit:
        return False
    app, tty = hit
    try:
        r = subprocess.run(["osascript", "-e", _JUMP[app], tty], capture_output=True, text=True,
                           timeout=JUMP_TIMEOUT_SEC)
    except (OSError, subprocess.SubprocessError):
        log.exception("jump osascript")
        return False
    return r.stdout.strip() == "ok"


def shell_line(project_dir, body=None):
    """새 창에서 칠 한 줄(순수 함수): 폴더로 옮기고, 본문이 있으면 이어서 실행한다."""
    line = "cd " + shlex.quote(project_dir)
    return line + " && " + body if body else line


def open_terminal(project_dir, body, env):
    """config.MAC_TERMINAL 앱의 새 창에서 `cd <폴더> && <본문>`. 기다리지 않는다."""
    app = config.MAC_TERMINAL if config.MAC_TERMINAL in _OPEN else "Terminal"
    subprocess.Popen(["osascript", "-e", _OPEN[app], shell_line(project_dir, body)], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)


def screens():
    """모니터 사각형 `[(x, y, w, h), …]`(왼쪽 위 원점). AppKit이 없으면 빈 목록."""
    try:
        from AppKit import NSScreen
        all_ = NSScreen.screens()
        top = all_[0].frame().size.height           # 주 화면 높이로 아래-원점 좌표를 뒤집는다
        return [(f.origin.x, top - f.origin.y - f.size.height, f.size.width, f.size.height)
                for f in (s.frame() for s in all_)]
    except Exception:
        return []


def visible_enough(x, y, w, h) -> bool:
    """저장된 창 자리가 어느 모니터와든 config.WINDOW_MIN_VISIBLE_PX 이상 겹치는가.
    모니터 정보를 못 얻으면 True(pywebview가 알아서 화면 안에 둔다)."""
    rects, m = screens(), config.WINDOW_MIN_VISIBLE_PX
    if not rects:
        return True
    return any(min(x + w, sx + sw) - max(x, sx) >= m and min(y + h, sy + sh) - max(y, sy) >= m
               for sx, sy, sw, sh in rects)
