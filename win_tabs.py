"""[점프]의 탭 고르기: UI Automation으로 호스트 창의 TabItem을 제목으로 찾아 Select한다.

한 Windows Terminal 창에 세션이 탭으로 여러 개 있으면 창만 앞에 가져와 봐야 엉뚱한 탭이
보인다 — 사용자 눈에는 "아무 일도 안 일어난" 것이다. 숨은 `PseudoConsoleWindow`의 제목은
비어 있으므로 **세션 ↔ 탭을 잇는 유일한 끈은 탭 제목**이다(실측). 제목 T는
`custom-title` → `ai-title` → `"Claude Code"` 순으로 정해지고, 탭 이름은 `"<글리프> " + T`다.

실측(comtypes 1.4.17): `FindAll(TreeScope_Descendants, ControlType == TabItem)` 30 ms,
`SelectionItemPattern.Select()` 25 ms이며 창 제목이 따라 바뀐다.
SI-7: 여기서도 hwnd를 저장하지 않는다 — 인자로 받아 쓰고 버린다.
comtypes는 함수 안에서 늦게 임포트한다 — 없어도 나머지 앱은 그대로 돈다(결과는 "error").
"""
from __future__ import annotations

import os

import config

DEFAULT_TITLE = "Claude Code"   # 기록이 아직 제목을 못 정한 새 세션의 탭 제목

_uia = None   # (IUIAutomation, UIAutomationClient 모듈). COM 객체이지 hwnd가 아니다(SI-7 무관).


def expected_title(records_newest_first) -> str:
    """최신 `custom-title` → 최신 `ai-title` → `"Claude Code"`. 순수 함수.

    두 종류 모두 한 기록 안에 여러 번 나오므로 **최신 것이 이긴다**(= 최신순 입력의 첫 번째).
    메시지 본문은 보지 않는다 — 제목 필드만 읽는다(inventory._inspect와 같은 원칙).
    """
    ai = None
    for rec in records_newest_first:
        kind = rec.get("type")
        if kind == "custom-title" and rec.get("customTitle"):
            return rec["customTitle"]
        if ai is None and kind == "ai-title" and rec.get("aiTitle"):
            ai = rec["aiTitle"]
    return ai or DEFAULT_TITLE


def _strip_glyph(name: str) -> str:
    """앞머리의 '영숫자가 하나도 없는 토큰 + 공백' 하나만 떼어낸다(상태 글리프 `◑`·`✳` 등)."""
    head, sep, rest = name.partition(" ")
    if sep and head and not any(ch.isalnum() for ch in head):
        return rest
    return name


def _matches(name: str, title: str) -> bool:
    """글리프를 뗀 뒤 **정확히** 같아야 한다 — 부분 일치는 엉뚱한 탭을 고를 수 있다."""
    return name == title or _strip_glyph(name) == title


def _gen_dir():
    """comtypes 래퍼(.py) 생성 폴더. 기본값은 `.venv\\…\\comtypes\\gen`이라 **프로젝트 폴더
    안**이다 — `PYTHONDONTWRITEBYTECODE`와 같은 취지로 런타임 쓰기를 상태 폴더로 돌린다.
    이미 생성돼 있는 래퍼는 원래 자리에서 그대로 임포트된다(새 쓰기만 이리로 온다)."""
    try:
        path = os.path.join(config.STATE_DIR, "comtypes_gen")
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        return None


def _automation():
    """`(IUIAutomation, UIAutomationClient)`를 1회만 만들어 재사용한다.
    `CoInitialize`는 comtypes가 임포트 시점에 대신 해 준다. **UI 스레드에서만** 부른다."""
    global _uia
    if _uia is None:
        import comtypes.client
        gen = _gen_dir()
        if gen:
            comtypes.client.gen_dir = gen
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as mod
        _uia = (comtypes.client.CreateObject(mod.CUIAutomation, interface=mod.IUIAutomation), mod)
    return _uia


def _tabs(host_hwnd):
    """`[(이름, 선택됨, SelectionItemPattern), …]`. 실패는 그대로 올린다(호출자가 감싼다)."""
    uia, mod = _automation()
    cond = uia.CreatePropertyCondition(mod.UIA_ControlTypePropertyId, mod.UIA_TabItemControlTypeId)
    found = uia.ElementFromHandle(host_hwnd).FindAll(mod.TreeScope_Descendants, cond)
    out = []
    for i in range(found.Length):
        el = found.GetElement(i)
        pat = el.GetCurrentPattern(mod.UIA_SelectionItemPatternId)
        if not pat:
            continue
        pat = pat.QueryInterface(mod.IUIAutomationSelectionItemPattern)
        out.append((el.CurrentName or "", bool(pat.CurrentIsSelected), pat))
    return out


def tab_names(host_hwnd) -> list[tuple[str, bool]]:
    """`[(탭 이름, 선택됨), …]`. 어떤 오류든 빈 목록 — 절대 예외를 올리지 않는다."""
    try:
        return [(name, sel) for name, sel, _pat in _tabs(host_hwnd)]
    except Exception:
        return []


def select_tab(host_hwnd, title) -> str:
    """제목이 맞는 탭 하나를 고른다. 절대 예외를 올리지 않고 결과 문자열만 돌려준다.

    `"selected"` 골랐다 / `"already"` 이미 그 탭이었다 / `"single"` 탭이 하나뿐이라 할 일 없음 /
    `"ambiguous"` 같은 제목이 둘 이상이라 **아무것도 고르지 않았다** / `"not_found"` /
    `"error"` 예외(comtypes 없음 포함).
    """
    try:
        names = tab_names(host_hwnd)
        if not names:            # 창은 해소됐는데 탭을 하나도 못 셌다 = UIA 실패
            return "error"
        if len(names) == 1:
            return "single"
        hits = [i for i, (name, _sel) in enumerate(names) if _matches(name, title)]
        if not hits:
            return "not_found"
        if len(hits) > 1:
            return "ambiguous"   # 조용히 틀리느니 창만 올리고 사용자에게 알린다
        if names[hits[0]][1]:
            return "already"
        return "selected" if _select(host_hwnd, title) else "not_found"
    except Exception:
        return "error"


def _select(host_hwnd, title) -> bool:
    """고르기 직전에 **다시 열거해서** 고른다 — 첫 순회의 인덱스를 믿지 않는다.
    그 사이 탭이 열리거나 닫히면 번호가 밀리고, 그러면 엉뚱한 탭을 '성공적으로' 고른다."""
    hits = [pat for name, _sel, pat in _tabs(host_hwnd) if _matches(name, title)]
    if len(hits) != 1:
        return False
    hits[0].Select()
    return True
