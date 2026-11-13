"""프로젝트 머리 줄(끌기 손잡이 ≡ · 접기 · 이름 · 버튼 3개)과 이름(별칭) 제자리 편집.
끌기의 동작(순서 저장)은 `ui_order.py`에 있다.

`ui_rows.py`가 150줄에 닿아 분리했다. 이름을 더블클릭하면 그 자리에 Entry가 뜬다 —
Enter = 저장(즉시 state.json), Esc·포커스 이탈 = 취소. 모달은 없다.
편집 중에는 `rows.editing`이 100 ms 재생성을 멈춘다 — 그러지 않으면 틱이 Entry를 부순다.
별칭은 표시만 바꾼다. 정렬·귀속·경로의 키는 언제나 폴더 이름이다.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import config
import ui_order
import ui_shell


def plain_name(p):
    """별칭이 없을 때의 표시 — 루트는 ROOT_LABEL, 나머지는 폴더 이름."""
    return config.ROOT_LABEL if p.is_root else p.name


def display_name(p, aliases):
    """`별칭 (폴더 이름)`. 루트는 `별칭 (C:\\dev)`. 별칭이 없으면 plain_name."""
    alias = aliases.get(p.name)
    if not alias:
        return plain_name(p)
    return "%s (%s)" % (alias, config.DEV_ROOT if p.is_root else p.name)


def set_alias(aliases, key, text, plain):
    """→ 새 dict(순수). 빈 문자열·폴더 이름·기본 표시와 같은 값은 별칭을 지운다."""
    out = dict(aliases)
    text = text.strip()
    if not text or text in (key, plain):
        out.pop(key, None)
    else:
        out[key] = text
    return out


DOT, DOT_FG = "●", "#d93025"   # 강조는 빨간 점뿐(배경색 없음) — 소리·토스트·topmost 호출 0건.


def dot(parent, bg):
    """'나를 기다림' 표시 — 글자 바로 오른쪽의 빨간 점(2026-09-22 사용자 요청: 노란 배경 대체)."""
    tk.Label(parent, text=DOT, bg=bg, fg=DOT_FG, font=("Segoe UI", 13)).pack(side="left", padx=(4, 0))


def header(rows, p, folded, i, lit):
    """i = 보이는 순서의 위치. `lit` = 세션 하나라도 강조 중 → **접혀 있을 때만** 이름 옆에도
    빨간 점(세션 줄이 안 보이므로). 펼쳐 있으면 점은 세션 줄에만 있다. → 머리 줄 Frame."""
    bg = rows._bg
    hdr = tk.Frame(rows.shell.body, bg=bg)
    hdr.pack(fill="x", pady=(8, 1))
    grip = tk.Label(hdr, text=config.LABELS["grip"], bg=bg, fg="#666666", cursor="fleur",
                    font=("Segoe UI", 13, "bold"), padx=4)
    grip.pack(side="left")
    ui_order.Drag(rows, grip, i)
    ttk.Button(hdr, text="▸" if folded else "▾", width=3,
               command=lambda n=p.name: rows.toggle(n)).pack(side="left", padx=(4, 0))
    lb = tk.Label(hdr, text=display_name(p, rows.aliases), bg=bg, cursor="xterm",
                  font=("Segoe UI", 10, "bold"))
    lb.pack(side="left", padx=(6, 0))
    lb.bind("<Double-Button-1>", lambda e: edit(rows, p, lb))
    if lit and folded:     # 펼쳐 두면 세션 줄에만 찍는다(2026-09-22 사용자 요청)
        dot(hdr, bg)
    tk.Frame(hdr, width=6, bg=bg).pack(side="left")
    for key, fn in (("new_claude", rows.act.new_claude), ("powershell", rows.act.powershell),
                    ("explorer", rows.act.explorer)):
        ttk.Button(hdr, text=config.LABELS[key],
                   command=lambda f=fn, d=p.path: f(d)).pack(side="left", padx=2)
    return hdr


def edit(rows, p, lb):
    """이름 라벨을 Entry로 바꾼다. 끝나면(저장/취소) 편집 표시를 풀고 다시 그리게 한다."""
    if rows.editing:
        return
    rows.editing = True
    var = tk.StringVar(master=lb, value=rows.aliases.get(p.name) or plain_name(p))
    ent = ttk.Entry(lb.master, textvariable=var, width=max(20, len(var.get()) + 4))
    ent.pack(side="left", padx=6, after=lb)
    lb.pack_forget()
    ent.focus_set()
    ent.select_range(0, "end")
    done = []

    def finish(save):
        if done:               # Enter 뒤의 재생성이 FocusOut을 한 번 더 부를 수 있다
            return
        done.append(True)
        lb.winfo_toplevel().unbind_all("<Button-1>")
        if save:
            save_alias(rows, p.name, var.get(), plain_name(p))
        rows.editing = False
        rows.invalidate()

    ent.bind("<Return>", lambda e: finish(True))
    ent.bind("<KP_Enter>", lambda e: finish(True))
    ent.bind("<Escape>", lambda e: finish(False))
    ent.bind("<FocusOut>", lambda e: finish(False))
    # 창 안의 빈 곳을 눌러도 Tk 포커스는 안 옮겨 간다 — Entry 밖 클릭도 '포커스 이탈'로 본다.
    lb.winfo_toplevel().bind_all("<Button-1>", lambda e: e.widget is not ent and finish(False))
    return ent


def save_alias(rows, key, text, plain):
    """메모리에 먼저 반영하고 즉시 저장한다. 저장 실패는 상태줄로만 알린다."""
    rows.aliases = set_alias(rows.aliases, key, text, plain)
    try:
        ui_shell.save_state(aliases=rows.aliases)
    except OSError as err:
        rows.message = config.LABELS["alias_save_failed"] % err
