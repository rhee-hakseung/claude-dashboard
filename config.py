"""모든 상수. 주기·임계·경로·제외 규칙을 바꾸려면 이 파일만 고친다.

계획서: C:\\dev\\.omc\\plans\\dev-dashboard-plan.md (rev 3.3) 3절·4절의 값을 그대로 옮겼다.
"""
import os
import sys

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def _env(name, default):
    """`.get(k, d)`는 **빈 문자열로 설정된** 환경 변수를 막지 못한다 — 그러면
    os.path.join이 상대 경로를 내놓아 엉뚱한 폴더를 가리킨다. 그래서 `or`로 받는다."""
    return os.environ.get(name) or default


_HOME = os.path.expanduser("~")
_LOCALAPPDATA = _env("LOCALAPPDATA", os.path.join(_HOME, "AppData", "Local"))
_APPDATA = _env("APPDATA", os.path.join(_HOME, "AppData", "Roaming"))

# ── 경로 ─────────────────────────────────────────────────────────────────────
OWN_DIR = os.path.dirname(os.path.abspath(__file__))   # 자기 폴더 = 설치 위치(목록에서 숨김)
CLAUDE_HOME = os.path.join(_HOME, ".claude")
SESSIONS_DIR = os.path.join(CLAUDE_HOME, "sessions")   # 라이브 레지스트리 <pid>.json (읽기 전용)
PROJECTS_DIR = os.path.join(CLAUDE_HOME, "projects")   # transcript <slug>\<sessionId>.jsonl
STATE_DIR = os.path.join(_LOCALAPPDATA if IS_WIN else os.path.join(_HOME, "Library", "Application Support")
                         if IS_MAC else _env("XDG_STATE_HOME", os.path.join(_HOME, ".local", "state")),
                         "dev-dashboard")
STATE_FILE = os.path.join(STATE_DIR, "state.json")     # geometry·aliases·order·dev_root


def _saved(key):
    """state.json의 문자열 값 하나(install 스크립트가 쓴다). 없거나 깨졌으면 None."""
    import json
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            v = json.load(fh).get(key)
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, str) and v else None


def _dev_root():
    """관찰 대상 루트: 환경 변수 DEV_DASHBOARD_ROOT → state.json의 "dev_root"(install 스크립트가
    쓴다) → C:\\dev(맥은 ~/dev). 다른 PC에서 프로젝트 폴더가 다를 수 있다(2026-09-22 사용자 결정)."""
    root = _env("DEV_DASHBOARD_ROOT", _saved("dev_root")) or (r"C:\dev" if IS_WIN else os.path.join(_HOME, "dev"))
    return os.path.normpath(os.path.expanduser(root))


DEV_ROOT = _dev_root()                     # 관찰 대상 루트. 직계 폴더 1개 = 프로젝트 1개
ROOT_LABEL = "(루트) " + DEV_ROOT
APP_TITLE = "Claude dashboard"                         # 창 제목(바탕화면 바로가기 이름과 같게)
APP_ICON = os.path.join(OWN_DIR, "dashboard.ico")      # 제목줄·작업 표시줄 아이콘
APP_USER_MODEL_ID = "hakseung.ClaudeCodeDashboard"     # 작업 표시줄 묶음 id(바로가기에도 같은 값)

# ── 제외 규칙 ────────────────────────────────────────────────────────────────
HIDDEN_NAME_PREFIXES = (".",)              # 점 폴더(.omc, .claude, .git …) 제외
HIDDEN_NAMES = {"dev-dashboard", os.path.basename(OWN_DIR), "__pycache__", "node_modules"}

# ── 폴링 주기(초) — 계획서 3절 "폴링 주기" 표 ────────────────────────────────
SESSIONS_PERIOD_SEC = 0.5      # 레지스트리 + 라이브 세션 꼬리 (fast worker)
PROJECTS_PERIOD_SEC = 3.0      # C:\dev scandir (slow worker)
TRANSCRIPTS_PERIOD_SEC = 5.0   # 끝난 기록 열거 (slow worker)
JOBS_PERIOD_SEC = 4.0          # psutil 프로세스 스캔 (slow worker)
UI_TICK_MS = 100               # UI가 스냅샷을 복사하는 주기
STALE_SNAPSHOT_SEC = 15.0      # 이 시간 이상 스냅샷 갱신이 없으면 "수집 중단" 표시

# ── 상태 판정(D1) 임계 ──────────────────────────────────────────────────────
PROCSTART_TOLERANCE_SEC = 2.0          # 레지스트리 procStart ↔ 실제 프로세스 생성 시각 허용 오차
TAIL_VETO_A_ENABLED = False            # 경고 A(busy ∧ end_turn ∧ 오래됨) — 기본 OFF, 표식만
TAIL_VETO_ASSISTANT_SEC = 180          # 경고 A: 마지막 assistant 메시지 나이 임계
TAIL_VETO_B_MARGIN_SEC = 5             # 거부권 B: 마지막 메시지 시각 > statusUpdatedAt + 이 값
VETO_CONFIRM_TICKS = 3                 # A/B 모두 연속 이 횟수만큼 관측돼야 발동
TAIL_WINDOW_BYTES = 256 * 1024         # 역파서 1차 창
TAIL_WINDOW_MAX_BYTES = 1024 * 1024    # 창 안에 메시지가 없으면 1회 확장, 그래도 없으면 HOLD

# ── 인벤토리(끝난 기록) ─────────────────────────────────────────────────────
STUB_MAX_BYTES = 64 * 1024     # 이 크기 미만 ∧ 아래 줄 수 이하일 때만 전수 스캔해 stub 판정
STUB_MAX_LINES = 200
NAME_FALLBACK_CHARS = 40       # 이름 2단계: 첫 user 메시지 절단 길이
CWD_SCAN_LINES = 50            # [재개] 폴더 후보: 앞에서 읽는 줄 수
LIVE_TAIL_MAX_FILES = 64       # 라이브 꼬리 읽기 상한(방어용)

# ── 작업 모니터(jobs) ───────────────────────────────────────────────────────
JOB_MIN_ELAPSED_SEC = 60       # 이보다 짧게 산 프로세스는 아직 '작업'이 아니다 (불변)
SHELL_NAMES = {"powershell.exe", "pwsh.exe", "cmd.exe", "conhost.exe", "wt.exe",
               "windowsterminal.exe", "openconsole.exe", "claude.exe", "git.exe",
               # WSL 다리 프로세스: Claude의 Bash 도구가 `wsl -e bash -lc …`로 띄운다 — 작업이 아니다
               # (2026-10-12 사용자 요청으로 숨김)
               "wsl.exe", "wslhost.exe", "wslrelay.exe",
               # macOS·리눅스: 셸·터미널·claude 자신
               "zsh", "bash", "sh", "fish", "login", "tmux", "screen", "terminal", "iterm2", "claude", "git"}
NODE_NAMES = {"node.exe", "node"}
CLAUDE_NAMES = {"claude.exe", "claude"}
HELPER_EXE_DIRS = (
    CLAUDE_HOME + os.sep,
    os.sep + "node_modules" + os.sep,
    os.path.join(_APPDATA, "npm") + os.sep,
    os.path.join(_LOCALAPPDATA, "AnthropicClaude") + os.sep,
    # Git Bash 유틸(grep/tail/sleep …)은 Claude 도구 프로세스다 — 2026-09-22 사용자 결정으로 helper 처리
    os.path.join(_env("ProgramFiles", r"C:\Program Files"), "Git", "usr", "bin") + os.sep,
)
NODE_HELPER_MARKERS = ("mcp", "--stdio", "@modelcontextprotocol", "language-server", ".claude\\plugins",
                       ".claude/plugins")

# ── 런처 ────────────────────────────────────────────────────────────────────
HOST_MODE = "wt"               # "wt" | "conhost". wt.exe 해소 실패 시 자동으로 conhost로 강등
WT_CANDIDATES = (
    os.path.join(_LOCALAPPDATA, "Microsoft", "WindowsApps", "wt.exe"),
)
POWERSHELL_EXE = os.path.join(_env("SystemRoot", r"C:\Windows"),
                              "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
EXPLORER_EXE = os.path.join(_env("SystemRoot", r"C:\Windows"), "explorer.exe")
CLAUDE_CMD = "claude"          # 새 셸의 PATH로 해소한다(사용자 셸과 같은 claude)
MAC_TERMINAL = _saved("terminal") or "Terminal"   # 맥에서 새 창을 열 앱: "Terminal" | "iTerm2"
RESUMING_CAP_SEC = 120         # [재개] 마크 상한: 레지스트리에 안 나타나면 이 뒤 '끝남'으로 복귀
JUMP_POSTCHECK_MS = 200        # [점프] 사후 확인 지연

# ── 휴지통 ──────────────────────────────────────────────────────────────────
TRASH_MIN_AGE_SEC = 5          # mtime 나이가 이보다 어리면 거절(아직 append 중일 수 있음)

# ── 화면 문구 ───────────────────────────────────────────────────────────────
SHELL_LABEL = "PowerShell" if IS_WIN else "터미널"
FILES_LABEL = "탐색기" if IS_WIN else "Finder" if IS_MAC else "파일"
LABELS = {
    "WORKING": "작업 중", "WAITING": "나를 기다림", "ENDED": "끝남",
    "shell_tag": "백그라운드 실행 중", "stub": "빈 기록", "resuming": "재개 중…",
    "dup": "다른 프로젝트에 같은 기록 있음", "disagree": "?",
    "new_claude": "새 claude", "powershell": SHELL_LABEL, "explorer": FILES_LABEL,
    "no_folder": "폴더가 없습니다: %s", "alias_save_failed": "이름 저장 실패: %s",
    "grip": "≡", "attach": "열기",
    "no_window": "창을 찾을 수 없습니다", "order_save_failed": "순서 저장 실패: %s",
    "orphan_jump": "'%s' — 창이 닫힌 세션을 " + SHELL_LABEL + " 새 탭에서 이어 엽니다",
    "desktop_jump": "'%s' — Claude 앱의 세션을 " + SHELL_LABEL + "에서 이어 엽니다(앱 쪽은 앱에서 닫으세요)",
}
# Claude 데스크톱 앱 안에서 돈 세션: 레지스트리 entrypoint로 알아본다. 앱 창은 트레이로 숨어 pid로 찾을 수
# 없으므로 [점프]는 PowerShell 새 탭에서 `claude --resume`으로 이어 연다(2026-11-12 사용자 요청).
DESKTOP_ENTRYPOINT = "claude-desktop"
JUMP_TAB_MESSAGES = {           # win_tabs.select_tab 결과 → 상태줄. 여기 없는 결과는 무소식
    "ambiguous": "창은 올렸지만 같은 제목의 탭이 여러 개라 탭을 고르지 못함",
    "not_found": "창은 올렸지만 탭을 찾지 못함",
    "error": "탭 전환 불가(UIA) — 창만 올림",
}
DEFAULT_GEOMETRY = (1000, 700)  # (w, h) 저장된 상태가 없을 때
WINDOW_MIN_VISIBLE_PX = 100     # 저장된 창 위치 복원 임계: 어느 모니터와든 이 이상 겹쳐야 유지
