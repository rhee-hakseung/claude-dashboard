"""행 버튼 6종의 동작만 담는다 — 위젯은 하나도 만들지 않는다(배치는 ui_rows.py).

`ui_rows.py`가 150줄에 닿아 분리했다. **버튼의 동작을 바꾸려면 이 파일만 고친다.**
SI-7: hwnd는 지역 변수로만 흐르고 어디에도 저장하지 않는다 — 사후 확인은 pid 재해소로 한다.
모달은 없다 — 거절·실패 사유는 전부 `set_status`(상태줄)로만 나간다.
"""
from __future__ import annotations

import time

import config
import launch
import term
import trash


class Actions:
    """`(shell, highlight, set_status, invalidate)`만 안다. 뷰모델도 위젯도 모른다."""

    def __init__(self, shell, highlight, set_status, invalidate):
        self.shell, self.hl = shell, highlight
        self.set_status, self.invalidate = set_status, invalidate

    def run(self, fn, *a):
        try:                     # 런처 실패는 모달이 아니라 상태줄로 알린다
            return fn(*a)
        except OSError as err:
            self.set_status(str(err))
            return None

    def new_claude(self, project_dir):
        sid = self.run(launch.open_new_claude, project_dir)
        if sid:
            self.hl.mark_seen(sid)   # 우리가 띄운 세션은 첫 '기다림'에 강조하지 않는다

    def powershell(self, project_dir):
        self.run(launch.open_powershell, project_dir)

    def attach(self, project_dir, session_id):
        self.run(launch.open_attach, project_dir, session_id)

    def explorer(self, project_dir):
        self.run(launch.open_explorer, project_dir)

    def jump(self, s, title=""):
        """탭 전환 실패는 [점프] 자체의 실패가 아니다 — 창은 올라갔으므로 알리기만 한다.
        데스크톱 앱 세션은 창을 찾을 수 없으므로 PowerShell 새 탭에서 같은 대화를 이어 연다
        (2026-11-12 사용자 요청). 그 뒤로는 같은 sid의 터미널 쪽 줄이 [점프] 대상이 된다(live._merge_same_sid)."""
        session_id, pid, tab_title = s.session_id, s.pid, s.tab_title
        self.hl.jump_clicked(session_id)
        if s.desktop or s.orphan:
            self.run(launch.open_resume, s.cwd, session_id)
            self.set_status(config.LABELS["orphan_jump" if s.orphan else "desktop_jump"] % title)
            return
        ok, tab = term.jump(pid, tab_title)
        if not ok:
            self.set_status("창을 찾을 수 없음")
            return
        self.set_status(config.JUMP_TAB_MESSAGES.get(tab, ""))
        self.shell.root.after(config.JUMP_POSTCHECK_MS, lambda: self.postcheck(pid))

    def postcheck(self, pid):
        """사후 확인. 점프 당시의 hwnd는 이미 버렸고 지금 다시 해소한 창으로만 판정한다."""
        if not term.confirm(pid):
            self.set_status("창을 확신할 수 없음")

    def resume(self, e):
        """[재개] 직후 강제 갱신을 하지 않는다(AC-L3). 마크 해제는 레지스트리 등장이 한다."""
        self.hl.mark_resuming(e.session_id, time.time())
        try:
            launch.open_resume(e.resume_dir, e.session_id)
        except OSError as err:
            self.hl.clear_resuming(e.session_id)
            self.set_status(str(err))
        self.invalidate()

    def trash(self, e):
        try:
            trash.send(e.path)
        except (trash.TrashRefused, OSError) as err:
            self.set_status(str(err))
            return
        self.set_status("휴지통으로 이동: %s" % e.title)
        self.invalidate(e)   # 지운 줄은 즉시 뺀다 — 수집을 재촉하지 않는다(다음 스캔이 확정한다)
