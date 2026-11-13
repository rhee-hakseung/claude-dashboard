"""행 4종(프로젝트 / 라이브 / 끝남 / '빈 기록')을 셸의 body에 그린다.

**버튼의 동작을 바꾸려면 `ui_actions.py`를, 배치를 바꾸려면 이 파일을 고친다.**
프로젝트 머리 줄과 이름(별칭) 편집은 `ui_project.py`로 옮겼다. 다음 분할은 `ui_rows.py → ui_rows_live.py / ui_rows_ended.py`(행 종류별)다 — 150줄에 닿으면
그리로 옮긴다. 뷰모델 키가 바뀔 때만 전부 다시 만들고 스크롤·접힘을 복원한다.
SI-5: [휴지통]·[재개] 위젯은 `_ended_row`의 `if not resuming:` 블록 안에만 존재한다.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import config
import inventory
import jobs
import ui_actions
import ui_order
import ui_project
import ui_shell
import win_tabs

GRAY = "#888888"


def live_label(s):
    """탭 제목(/rename → ai-title)을 그대로 보인다. 아직 기본값("Claude Code")인 새 세션만
    레지스트리 name(자동 이름)으로 대신하고, 둘 다 없으면 sessionId 앞 8자."""
    if s.tab_title and s.tab_title != win_tabs.DEFAULT_TITLE:
        return s.tab_title
    return s.name or s.tab_title or s.session_id[:8]


class Rows:
    """셸의 body 프레임 하나를 통째로 소유한다. 뷰모델(groups)은 app.py가 만들어 준다."""

    def __init__(self, shell, highlight):
        self.shell, self.hl = shell, highlight
        self.collapsed: set[str] = set()
        self.message = ""      # 상태줄의 '마지막 동작' 칸 — app.py가 읽어 조립한다.
        self._key, self._groups, self._ages = None, [], []
        self.aliases, self.editing = ui_shell.load_aliases(), False   # 별칭 편집은 ui_project
        self.order, self.dragging, self._headers = ui_shell.load_order(), False, []   # 끌기는 ui_order
        self._bg = shell.body.cget("background")
        self.act = ui_actions.Actions(shell, highlight, self._set_message, self.invalidate)

    def _set_message(self, text):
        self.message = text

    def invalidate(self, dropped=None):
        """다음 틱(≤100 ms)에 다시 그린다. `dropped`가 있으면 그 줄을 빼고 그린다."""
        if dropped is not None:
            for _p, _lives, ends, _js in self._groups:
                ends[:] = [x for x in ends if x is not dropped]
        self._key = None

    def render(self, groups, now):
        self._groups = groups = ui_order.arrange(groups, self.order)   # 사용자 고정 순서
        if self.editing or self.dragging:   # 편집·끌기 중엔 재생성을 멈춘다(끝나면 invalidate)
            return
        key = self._viewkey(groups, now)
        if key == self._key:
            return             # 보이는 값이 그대로면 위젯을 하나도 건드리지 않는다
        self._key = None       # 도중에 죽어도 반쯤 그린 화면이 굳지 않게 먼저 무효화한다
        top = self.shell.scroll_top()
        for w in self.shell.body.winfo_children():
            w.destroy()
        self._ages, self._headers = [], []
        for i, row in enumerate(groups):
            self._project_row(now, i, *row)
        self.shell.restore_scroll(top)
        self.refresh_ages(now)
        self._key = key        # 전부 다시 만든 뒤에만 키를 확정한다

    def refresh_ages(self, now):
        """나이 문자열만 제자리로 갱신한다(app.tick이 매 틱 부른다) — 재생성이 없다."""
        for lb, mtime, head, tags in self._ages:
            lb.configure(text=head + inventory.format_age(max(0.0, now - mtime)) + tags)

    def _viewkey(self, groups, now):
        """화면에 실제로 보이는 값만 모은 키. 여기 없는 변화는 재생성을 일으키지 않는다.
        나이 문자열은 일부러 빠져 있다 — `refresh_ages`가 제자리로 갱신한다."""
        return tuple(
            (p.name, ui_project.display_name(p, self.aliases), p.name in self.collapsed,
             self._lit(lives), tuple((s.session_id, live_label(s), s.state, s.shell_tag, s.sources_disagree,
                    s.jumpable, s.background, self.hl.is_on(s.session_id)) for s in lives),
             tuple((e.path, e.title, e.is_stub, e.duplicate_of_newer, bool(e.resume_dir),
                    self.hl.is_resuming(e.session_id, now)) for e in ends),
             tuple(jobs.display(j) for j in js))
            for p, lives, ends, js in groups)

    def _lit(self, lives):
        return any(self.hl.is_on(s.session_id) for s in lives)

    def _project_row(self, now, i, p, lives, ends, js):
        folded = p.name in self.collapsed
        self._headers.append(ui_project.header(self, p, folded, i, self._lit(lives)))
        if folded:
            return
        for s in lives:
            self._live_row(s)
        for e in ends:
            self._ended_row(e, now)
        for j in js:
            tk.Label(self.shell.body, text=jobs.display(j), bg=self._bg,
                     fg=GRAY).pack(anchor="w", padx=34)

    def _live_row(self, s):
        bg = self._bg
        f = tk.Frame(self.shell.body, bg=bg)
        f.pack(fill="x", padx=20)
        text = "%s  ·  %s" % (live_label(s), config.LABELS.get(s.state, s.state))
        if s.shell_tag:        # 백그라운드 세션이라는 꼬리표는 달지 않는다(2026-10-14 사용자 요청)
            text += " + " + config.LABELS["shell_tag"]
        if s.sources_disagree:
            text += "   %s 상태 출처 불일치" % config.LABELS["disagree"]
        tk.Label(f, text=text, bg=bg, anchor="w").pack(side="left")
        if self.hl.is_on(s.session_id):
            ui_project.dot(f, bg)
        if s.background:       # `claude --bg` 세션은 창이 없다 — [점프] 대신 새 탭에서 attach
            ttk.Button(f, text=config.LABELS["attach"], command=lambda x=s: self.act.attach(
                x.cwd, x.session_id)).pack(side="right", padx=2)
            return
        btn = ttk.Button(f, text="점프", command=lambda x=s: self.act.jump(x, live_label(x)))
        btn.pack(side="right", padx=2)
        if not s.jumpable:     # 판정은 수집 워커가 한다 — 렌더 경로에 Win32 호출이 없다
            btn.state(["disabled"])
            tk.Label(f, text=config.LABELS["no_window"], bg=bg, fg=GRAY).pack(side="right", padx=4)

    def _ended_row(self, e, now):
        resuming = self.hl.is_resuming(e.session_id, now)
        f = tk.Frame(self.shell.body, bg=self._bg)
        f.pack(fill="x", padx=20)
        tags = [t for t in (config.LABELS["stub"] if e.is_stub else "",
                            config.LABELS["dup"] if e.duplicate_of_newer else "",
                            config.LABELS["resuming"] if resuming else "") if t]
        lb = tk.Label(f, bg=self._bg, anchor="w", fg=GRAY if e.is_stub else "black")
        lb.pack(side="left")
        self._ages.append((lb, e.mtime, e.title + " · ", "".join("   " + t for t in tags)))
        if not resuming:       # SI-5: 두 위젯은 이 블록 안에서만 만들어진다
            ttk.Button(f, text="휴지통",
                       command=lambda x=e: self.act.trash(x)).pack(side="right", padx=2)
            if not e.is_stub and not e.duplicate_of_newer and e.resume_dir:
                ttk.Button(f, text="재개",
                           command=lambda x=e: self.act.resume(x)).pack(side="right", padx=2)

    def toggle(self, name):
        self.collapsed ^= {name}
        self.invalidate()
