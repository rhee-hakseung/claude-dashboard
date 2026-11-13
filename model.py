"""dataclass + 순수 함수: 프로젝트 순서. 파일시스템·프로세스를 절대 건드리지 않는다."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

WORKING = "WORKING"
WAITING = "WAITING"
ENDED = "ENDED"


class SessionState:
    """상태 라벨 3종. UNKNOWN은 없다 — 출처 모순은 `sources_disagree` 플래그로만 드러낸다."""
    WORKING = WORKING
    WAITING = WAITING
    ENDED = ENDED
    ALL = (WORKING, WAITING, ENDED)


@dataclass(slots=True)
class LiveSession:
    pid: int
    session_id: str
    cwd: str
    status: str                 # 레지스트리 원문(busy/idle/shell/waiting/미지)
    status_updated_at: float    # 초 단위(레지스트리는 ms)
    proc_start: float           # 초 단위 unix
    name: str = ""
    project: str | None = None
    transcript_path: str | None = None
    state: str = WORKING
    sources_disagree: bool = False
    shell_tag: bool = False
    jumpable: bool = False      # [점프] 가능 여부. 수집 워커가 판정한다 — hwnd는 남기지 않는다
    background: bool = False    # 레지스트리 kind == "bg"(`claude --bg` 세션) — 창이 없다, [열기]=attach
    also_ids: tuple = ()        # 이 줄에 합쳐진 창 쪽 세션 id(live._merge_parked) — 그 기록은 '끝남'이 아니다
    desktop: bool = False       # Claude 데스크톱 앱 안의 세션(entrypoint) — [점프] = 앱을 앞으로
    orphan: bool = False        # 창이 닫혔는데 프로세스만 남은 세션 — [이어 열기] = 새 탭에서 --resume
    tab_title: str = "Claude Code"   # WT 탭 제목(custom-title → ai-title → 기본값). win_tabs가 쓴다


@dataclass(slots=True)
class EndedSession:
    slug: str                   # 파일이 놓인 폴더 슬러그 — 동일성·귀속의 기준
    session_id: str
    path: str
    project: str | None
    mtime: float
    size: int
    title: str
    is_stub: bool = False
    resume_dir: str | None = None
    duplicate_of_newer: bool = False


@dataclass(slots=True)
class Job:
    pid: int
    create_time: float
    name: str
    cwd: str
    project: str | None
    elapsed: float


@dataclass(slots=True)
class Project:
    name: str                   # 프로젝트 폴더 이름, 루트는 paths.ROOT_KEY
    path: str
    last_activity: float
    is_root: bool = False


@dataclass(slots=True)
class Snapshot:
    projects: list[Project] = field(default_factory=list)
    live: list[LiveSession] = field(default_factory=list)
    ended: list[EndedSession] = field(default_factory=list)
    jobs: list[dict] = field(default_factory=list)   # jobs.scan이 dict를 돌려주고
    # jobs.display가 그 dict를 그대로 먹는다 — Job 데이터클래스는 여기 들어오지 않는다.
    collected_at: float = 0.0
    failures: int = 0
    disagreements: int = 0
    rejected_registry: int = 0

    def copy(self) -> "Snapshot":
        """UI 틱이 락 안에서 부르는 얕은 복사 — 리스트만 새로 만든다."""
        return replace(self, projects=list(self.projects), live=list(self.live),
                       ended=list(self.ended), jobs=list(self.jobs))


def order_projects(projects: list[Project], saved_order) -> list[Project]:
    """사용자가 끌어서 정한 고정 순서(2026-09-22 사용자 결정 — 상태 우선순위 정렬을 대체한다).
    `saved_order`에 있는 폴더가 그 순서대로 먼저 오고(디스크에 없는 이름은 무시할 뿐 지우지
    않는다), 나머지(새 폴더)는 `-last_activity` → 이름 순으로 뒤에 붙되 루트는 그중 맨 뒤다.
    세션 상태는 순서에 전혀 관여하지 않는다 — 줄이 저절로 움직이지 않게 하기 위해서다."""
    by = {p.name: p for p in projects}
    head = [by[n] for n in dict.fromkeys(saved_order) if n in by]
    fixed = {p.name for p in head}
    rest = sorted((p for p in projects if p.name not in fixed),
                  key=lambda p: (p.is_root, -p.last_activity, p.name))
    return head + rest
