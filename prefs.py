"""state.json 읽기/쓰기와 사용자 설정(별칭·순서·접힘·즐겨찾기·테마). 화면 도구(tk·webview)를 모른다.

쓰기는 언제나 읽고-합쳐서 원자적으로(.tmp → os.replace) 한다 — 다른 키를 지우지 않는다.
`ui_shell`(예전 tk 화면)과 `webapp`(새 화면)이 같은 함수를 쓴다.
"""
from __future__ import annotations

import json
import os

import config


def read_state():
    """state.json 전체. 없거나 깨졌거나 dict가 아니면 {}."""
    try:
        with open(config.STATE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_geometry():
    """state.json의 `[x, y, w, h]`. 없거나 깨졌으면 None → 주 모니터 중앙."""
    try:
        g = read_state()["geometry"]
        return [int(v) for v in g] if len(g) == 4 else None
    except (ValueError, TypeError, KeyError):
        return None


def load_aliases():
    """`{폴더 이름: 별칭}`. 모양이 틀린 값(dict 아님, 문자열 아님, 빈 문자열)은 버린다."""
    a = read_state().get("aliases")
    if not isinstance(a, dict):
        return {}
    return {k: v for k, v in a.items() if isinstance(k, str) and isinstance(v, str) and v}


def load_list(key):
    """문자열 리스트 설정(order·folded·favorites). 리스트가 아니면 [], 문자열이 아닌 항목과
    중복(첫 번째를 남긴다)은 버린다."""
    o = read_state().get(key)
    return list(dict.fromkeys(x for x in o if isinstance(x, str))) if isinstance(o, list) else []


def load_order():
    """`[폴더 이름, ...]`(루트는 paths.ROOT_KEY)."""
    return load_list("order")


def save_state(**changes):
    """읽고 → 합치고 → 같은 폴더의 .tmp에 쓴 뒤 os.replace. 다른 키를 지우지 않는다
    (닫기 경로의 geometry 저장이 별칭을 날리면 안 된다)."""
    data = read_state()
    data.update(changes)
    os.makedirs(config.STATE_DIR, exist_ok=True)
    tmp = config.STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, config.STATE_FILE)


def set_alias(aliases, key, text, plain):
    """새 별칭 dict(순수). 빈 문자열·폴더 이름·기본 표시와 같은 값은 별칭을 지운다."""
    out = dict(aliases)
    text = text.strip()
    if not text or text in (key, plain):
        out.pop(key, None)
    else:
        out[key] = text
    return out


class Prefs:
    """새 화면이 쓰는 설정 묶음. 바꾼 즉시 `save(키)`로 그 키만 저장한다."""

    def __init__(self):
        self.aliases = load_aliases()
        self.order = load_order()
        self.folded = set(load_list("folded"))
        self.favorites = load_list("favorites")
        theme = read_state().get("theme")
        self.theme = theme if theme in ("light", "dark") else ""

    def save(self, *keys):
        vals = {"aliases": self.aliases, "order": self.order, "folded": sorted(self.folded),
                "favorites": self.favorites, "theme": self.theme}
        save_state(**{k: vals[k] for k in keys})
