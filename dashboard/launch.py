"""[재개]·[새 claude]·[PowerShell]·[탐색기] 런처. 리스트 형태 Popen만 쓰고 셸을 경유하지 않는다.
맥은 mac_term.open_terminal(Terminal·iTerm2 새 창)과 `open`(Finder)을 쓴다. 아래 실측은 Windows 이야기다.

실측(S0-2): wt를 거치는 본문은 ';'와 '"'를 모두 백슬래시로 이스케이프해야 한다.
맨 '"'를 넘기면 오류 없이 문장이 조용히 사라진다. 직접 powershell을 띄울 때는 반대로
그대로 넘겨야 하고(이스케이프하면 리터럴 '\\"'가 된다), DETACHED_PROCESS만으로는
본문이 아예 실행되지 않으므로 CREATE_NEW_CONSOLE을 쓴다.
PowerShell 5.1에는 '&&'·'??'·삼항이 없으므로 본문에 쓰지 않는다.
"""
import os
import subprocess
import uuid

import config
import mac_term     # 맥·리눅스 분기용. 임포트만으로는 아무것도 하지 않는다(psutil·subprocess뿐)

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NEW_CONSOLE = 0x00000010

_host = None      # "wt" | "conhost". 모드 문자열일 뿐 hwnd가 아니므로 캐시해도 된다(SI-7 무관).
_wt_path = None
# wt -w 0 = 가장 최근에 쓴 Windows Terminal 창에 탭으로 연다. 열린 창이 없으면 wt가 새 창을 만든다.
WT_WINDOW = "0"


class LaunchFailed(OSError):
    """런처 실패. OSError를 상속해 web_api의 `except OSError` 하나로 상태줄에 나간다."""


def resolve_host():
    """wt.exe(앱 실행 별칭)를 1회만 해소한다. 없으면 conhost 모드로 강등."""
    global _host, _wt_path
    if _host is None:
        _host = "conhost"
        if config.HOST_MODE == "wt":
            for p in config.WT_CANDIDATES:
                if p and os.path.isfile(p):
                    _wt_path, _host = p, "wt"
                    break
    return _host


def _esc(s):
    """wt는 ';'를 명령 구분자로, '"'를 인용부호로 먹는다 — 본문이든 -d 폴더든 똑같이 막는다."""
    return s.replace('"', '\\"').replace(";", "\\;")


def _argv(project_dir, body=None):
    """순수 함수. body가 None이면 -Command 없이 셸만 연다."""
    ps = [config.POWERSHELL_EXE, "-NoLogo", "-NoExit"]
    if resolve_host() == "wt":
        if body is not None:
            ps += ["-Command", _esc(body)]
        return [_wt_path, "-w", WT_WINDOW, "-d", _esc(project_dir)] + ps
    if body is not None:
        ps += ["-Command", body]
    return ps


def _child_env(env=None):
    """Claude Code 세션 표식을 벗긴 환경. 대시보드가 Claude 세션 안에서 실행됐다면
    `CLAUDECODE`/`CLAUDE_CODE_*`/`CLAUDE_PID`가 물려지는데, 그러면 새로 띄운 claude가
    자신을 자식 세션으로 오인해 transcript 저장을 끄고 레지스트리에도 안 나타난다(실측)."""
    src = os.environ if env is None else env
    return {k: v for k, v in src.items()
            if not (k.upper().startswith("CLAUDE_CODE_") or k.upper() in ("CLAUDECODE", "CLAUDE_PID"))}


def _spawn(argv, cwd=None):
    """wt 모드는 즉시 끝나는 런처라 DETACHED로 띄우고, 직접 모드는 새 콘솔이 필요하다."""
    flags = CREATE_NEW_CONSOLE
    if resolve_host() == "wt":
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(argv, cwd=cwd, env=_child_env(), shell=False, close_fds=True,
                         creationflags=flags)
    except (OSError, ValueError) as exc:
        raise LaunchFailed("실행 실패: %s" % exc) from exc


def _open(project_dir, body):
    """새 터미널 창(탭)에서 project_dir로 옮겨 body를 실행한다(None이면 셸만). 운영체제별 분기는 여기뿐."""
    if config.IS_WIN:
        return _spawn(_argv(project_dir, body), project_dir)
    try:
        if config.IS_MAC:
            mac_term.open_terminal(project_dir, body, _child_env())
        else:              # 리눅스: 데비안 계열의 기본 터미널 별칭. 없으면 실패를 알린다
            subprocess.Popen(["x-terminal-emulator", "-e", "sh", "-c", mac_term.shell_line(project_dir, body)
                              + "; exec \"${SHELL:-sh}\""], cwd=project_dir, env=_child_env(), close_fds=True)
    except (OSError, ValueError) as exc:
        raise LaunchFailed("실행 실패: %s" % exc) from exc


def open_resume(project_dir, session_id):
    """[재개]. 부팅 동안 그 sessionId는 아직 라이브가 아니다 — 호출자는 강제 갱신하지 말 것."""
    _open(project_dir, "%s --resume %s" % (config.CLAUDE_CMD, session_id))


def open_attach(project_dir, session_id):
    """[열기] — 창이 없는 백그라운드 세션(`claude --bg`)을 새 탭에 붙인다. 세션은 계속 돈다
    (붙은 화면에서 ←는 목록, Ctrl+Z는 셸로 빠질 뿐 세션을 멈추지 않는다). id = sessionId 앞 8자."""
    _open(project_dir, "%s attach %s" % (config.CLAUDE_CMD, session_id[:8]))


def open_new_claude(project_dir):
    """[새 claude]. id를 우리가 정해 넘기므로 대시보드가 방금 띄운 세션을 알아본다."""
    session_id = str(uuid.uuid4())
    _open(project_dir, "%s --session-id %s" % (config.CLAUDE_CMD, session_id))
    return session_id


def open_powershell(project_dir):
    """[PowerShell](맥은 [터미널]). Windows는 -Command 없이 -NoLogo -NoExit만."""
    _open(project_dir, None)


def open_explorer(project_dir):
    """[탐색기](맥은 [Finder]). 폴더가 사라졌으면 띄우지 않고 상태줄로만 알린다(LaunchFailed)."""
    if not os.path.isdir(project_dir):
        raise LaunchFailed(config.LABELS["no_folder"] % project_dir)
    opener = [config.EXPLORER_EXE] if config.IS_WIN else ["open"] if config.IS_MAC else ["xdg-open"]
    try:
        subprocess.Popen(opener + [os.path.normpath(project_dir)],
                         env=_child_env(), shell=False, close_fds=True)
    except (OSError, ValueError) as exc:
        raise LaunchFailed("실행 실패: %s" % exc) from exc
