"""창 껍데기: Tk 루트, 스크롤 Canvas, 상태줄, geometry 로드/저장.

`-topmost`도 소리도 토스트도 호출하지 않는다(AC-W1). 프로그램 전체의 쓰기는 여기의
`state.json`, `trash.send`, 그리고 `win_tabs`가 돌려놓은 comtypes 래퍼 캐시(같은 상태 폴더의
`comtypes_gen` 폴더)뿐이다(SI-2) — `state.json`은 닫을 때(geometry), 별칭을 Enter로 확정할
때, 프로젝트를 끌어 놓을 때(order)만 쓰며, 언제나 읽고-합쳐서 원자적으로(.tmp → os.replace) 쓴다.
행은 `ui_rows.Rows`가 `self.body` 안에 그린다. 이 파일은 행의 내용을 모른다.
"""
from __future__ import annotations

import ctypes
import json
import os
import tkinter as tk
from tkinter import ttk

import config


# state.json 함수는 prefs.py로 옮겼다(새 웹 화면과 같이 쓴다) — 예전 이름 그대로 다시 내보낸다.
from prefs import load_aliases, load_geometry, load_order, read_state, save_state  # noqa: E402,F401


def save_geometry(root):
    save_state(geometry=[root.winfo_x(), root.winfo_y(), root.winfo_width(), root.winfo_height()])


class Shell:
    """루트 창 1개. 행을 담을 빈 프레임(`body`)과 상태줄만 제공한다."""

    def __init__(self, on_close=None):
        try:   # 없으면 pythonw.exe로 묶여 작업 표시줄에 Python 아이콘이 뜬다. 창을 만들기 전에 불러야 한다
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(config.APP_USER_MODEL_ID)
        except (AttributeError, OSError):
            pass
        self.root = tk.Tk()
        self.root.title(config.APP_TITLE)
        try:   # 제목줄·작업 표시줄 아이콘. 파일이 없어도 창은 뜬다(기본 Tk 아이콘)
            self.root.iconbitmap(default=config.APP_ICON)
        except tk.TclError:
            pass
        # 음수 x는 win_find가 '+-2560' 꼴로 조립해 준다 — 직접 f-string으로 만들지 말 것.
        if config.IS_WIN:
            import win_find
            self.root.geometry(win_find.place_geometry(load_geometry(), config.DEFAULT_GEOMETRY))
        else:   # 맥·리눅스: 저장된 크기만 쓰고 자리는 창 관리자에 맡긴다
            w, h = (load_geometry() or [0, 0, *config.DEFAULT_GEOMETRY])[2:]
            self.root.geometry("%dx%d" % (w, h))
        self._on_close = on_close

        self.status = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.status, anchor="w",
                  padding=(6, 3)).pack(side="bottom", fill="x")
        bar = ttk.Scrollbar(self.root, orient="vertical")
        bar.pack(side="right", fill="y")
        self.canvas = tk.Canvas(self.root, highlightthickness=0, yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.configure(command=self.canvas.yview)

        self.body = tk.Frame(self.canvas, bg=self.root.cget("background"))
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self._resync())
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.root.bind_all("<MouseWheel>", self._wheel)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _resync(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def set_status(self, text):
        if self.status.get() != text:
            self.status.set(text)

    def scroll_top(self):
        return self.canvas.yview()[0]

    def restore_scroll(self, top):
        """행을 다시 만든 직후에만 부른다 — 높이를 확정한 뒤 같은 위치로 되돌린다."""
        self.canvas.update_idletasks()
        self._resync()
        self.canvas.yview_moveto(top)

    def close(self):
        """✕ = 저장 후 destroy. 어떤 세션도 건드리지 않는다(SI-8)."""
        if self._on_close:
            self._on_close()
        try:
            save_geometry(self.root)
        except OSError:
            pass
        self.root.destroy()
