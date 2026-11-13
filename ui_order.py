"""프로젝트 순서: 사용자가 머리 줄 왼쪽의 손잡이(≡)를 잡아끌어 정하는 고정 순서
(2026-09-22 사용자 결정 — ▲▼ 버튼에서 끌기로 교체).

기다리는 세션이 있어도 줄은 움직이지 않는다 — 알림은 빨간 점뿐이다(누르려던 버튼이
막 움직여 엉뚱한 것을 누르는 일을 막는다). 끄는 동안에는 파란 가로줄이 놓일 자리를 보이고
화면 재생성이 멈춘다(`rows.dragging`). 놓으면 **지금 보이는 전체 순서**(아직 저장되지 않은
새 폴더 포함)를 곧바로 `state.json`의 `"order"`에 저장한다(`ui_shell.save_state`). Esc = 취소.
"""
from __future__ import annotations

import tkinter as tk

import config
import model
import ui_shell

LINE_BG = "#3a7bd5"    # 놓일 자리 표시줄
EDGE_PX = 28           # 창 위·아래 끝에서 이 안쪽으로 끌면 자동 스크롤


def arrange(groups, order):
    """뷰모델 묶음(p, lives, ends, jobs)을 `model.order_projects` 순서로 늘어놓는다."""
    by = {g[0].name: g for g in groups}
    return [by[p.name] for p in model.order_projects([g[0] for g in groups], order)]


def moved(names, i, slot):
    """→ i번째를 틈 `slot`(0 = 맨 앞, len = 맨 뒤; 원래 목록 기준)으로 옮긴 새 리스트(순수)."""
    out = list(names)
    if not 0 <= i < len(out):
        return out
    slot = max(0, min(slot, len(out)))
    item = out.pop(i)
    out.insert(slot - 1 if slot > i else slot, item)
    return out


def reorder(shown, saved, i, slot):
    """→ 새로 저장할 순서. 지금 디스크에 없어 안 보이는 예전 이름은 지우지 않고 뒤에 남긴다
    (폴더가 돌아오면 그 뒤쪽 자리로 복귀)."""
    out = moved(shown, i, slot)
    seen = set(out)
    return out + [n for n in saved if n not in seen]


def slot_for(mids, y):
    """머리 줄 가운데 y 좌표들(위→아래)과 포인터 y → 틈 번호 = 포인터보다 위에 있는 가운데의 수."""
    return sum(1 for m in mids if m < y)


def commit(rows, i, slot):
    """메모리에 먼저 반영하고 즉시 저장, 실패는 상태줄로만 알린다. 제자리면 저장하지 않는다."""
    shown = [g[0].name for g in rows._groups]
    if moved(shown, i, slot) != shown:
        rows.order = reorder(shown, rows.order, i, slot)
        try:
            ui_shell.save_state(order=rows.order)
        except OSError as err:
            rows.message = config.LABELS["order_save_failed"] % err
    rows.invalidate()


class Drag:
    """손잡이 1개에 붙는 끌기. 누름 → 끌기(표시줄) → 놓음(commit) / Esc(취소)."""

    def __init__(self, rows, grip, i):
        self.rows, self.i, self.slot, self.line = rows, i, i, None
        grip.bind("<ButtonPress-1>", self.start)
        grip.bind("<B1-Motion>", self.motion)
        grip.bind("<ButtonRelease-1>", self.drop)

    def start(self, event):
        if self.rows.editing:
            return
        self.rows.dragging, self.slot = True, self.i
        self.line = tk.Frame(self.rows.shell.body, height=3, bg=LINE_BG)
        event.widget.winfo_toplevel().bind("<Escape>", self.cancel)

    def motion(self, event):
        if self.line is None:
            return
        canvas = self.rows.shell.canvas
        top = canvas.winfo_rooty()
        if event.y_root < top + EDGE_PX:
            canvas.yview_scroll(-1, "units")
        elif event.y_root > top + canvas.winfo_height() - EDGE_PX:
            canvas.yview_scroll(1, "units")
        hs = self.rows._headers
        self.slot = slot_for([h.winfo_rooty() + h.winfo_height() / 2 for h in hs], event.y_root)
        body = self.rows.shell.body
        y = hs[self.slot].winfo_y() - 5 if self.slot < len(hs) else body.winfo_height() - 3
        self.line.place(x=0, y=max(0, y), relwidth=1)
        self.line.lift()

    def drop(self, event):
        if self.line is not None:
            self._end(event.widget)
            commit(self.rows, self.i, self.slot)

    def cancel(self, event=None):
        if self.line is not None:
            self._end(event.widget if event else self.rows.shell.body)
            self.rows.invalidate()

    def _end(self, widget):
        widget.winfo_toplevel().unbind("<Escape>")
        self.line.destroy()
        self.line, self.rows.dragging = None, False
