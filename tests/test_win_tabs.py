"""win_tabs: 탭 제목 결정(custom-title → ai-title → 기본값), 글리프 제거, select_tab 분기.
UI Automation도 comtypes도 부르지 않는다 — `tab_names`/`_tabs`를 갈아 끼운다."""
import pytest

import win_tabs

CUSTOM = {"type": "custom-title", "customTitle": "FPGA work"}
AI = {"type": "ai-title", "aiTitle": "IEEE Xplore API 키 확인"}
NOISE = {"type": "user", "message": {"role": "user", "content": "비밀"}}


def test_expected_title_prefers_custom_over_ai():
    # 최신순 입력에서 ai가 더 최신이어도 custom이 이긴다(종류 우선, 그 다음 최신).
    assert win_tabs.expected_title([AI, CUSTOM]) == "FPGA work"


def test_expected_title_falls_back_to_newest_ai_title():
    older = {"type": "ai-title", "aiTitle": "옛 제목"}
    assert win_tabs.expected_title([NOISE, AI, older]) == "IEEE Xplore API 키 확인"


def test_expected_title_defaults_for_brand_new_session():
    assert win_tabs.expected_title([NOISE]) == "Claude Code"
    assert win_tabs.expected_title([]) == win_tabs.DEFAULT_TITLE


@pytest.mark.parametrize("name, title", [
    ("◑ PowerShell 세션 관리 도구", "PowerShell 세션 관리 도구"),
    ("✳ FPGA work", "FPGA work"),
    ("FPGA work", "FPGA work"),                 # 글리프 없는 이름은 자기 자신과 맞는다
    ("✳ Claude Code", "Claude Code"),
])
def test_strip_glyph_matching(name, title):
    assert win_tabs._matches(name, title)


@pytest.mark.parametrize("name", ["✳ FPGA work extra", "FPGA", "◑ 다른 제목"])
def test_partial_names_do_not_match(name):
    assert not win_tabs._matches(name, "FPGA work")


def test_strip_glyph_keeps_alphanumeric_first_token():
    assert win_tabs._strip_glyph("2단계 계획") == "2단계 계획"
    assert win_tabs._strip_glyph("✳ FPGA work") == "FPGA work"
    assert win_tabs._strip_glyph("✳") == "✳"     # 뒤에 공백이 없으면 떼지 않는다


def fake_tabs(monkeypatch, names):
    monkeypatch.setattr(win_tabs, "tab_names", lambda hwnd: list(names))


def test_single_tab_is_nothing_to_do(monkeypatch):
    fake_tabs(monkeypatch, [("✳ FPGA work", True)])
    assert win_tabs.select_tab(1234, "다른 제목") == "single"


def test_duplicate_titles_select_nothing(monkeypatch):
    fake_tabs(monkeypatch, [("✳ Claude Code", True), ("✳ Claude Code", False)])
    assert win_tabs.select_tab(1234, "Claude Code") == "ambiguous"


def test_not_found(monkeypatch):
    fake_tabs(monkeypatch, [("✳ FPGA work", True), ("◑ 다른 것", False)])
    assert win_tabs.select_tab(1234, "없는 제목") == "not_found"


def test_already_selected_does_not_touch_com(monkeypatch):
    fake_tabs(monkeypatch, [("✳ FPGA work", True), ("◑ 다른 것", False)])
    monkeypatch.setattr(win_tabs, "_tabs", lambda hwnd: pytest.fail("두 번째 순회를 하면 안 된다"))
    assert win_tabs.select_tab(1234, "FPGA work") == "already"


def test_selected_calls_select_once(monkeypatch):
    calls = []

    class Pat:
        def Select(self):
            calls.append(1)

    fake_tabs(monkeypatch, [("✳ FPGA work", True), ("◑ 대상", False)])
    monkeypatch.setattr(win_tabs, "_tabs",
                        lambda hwnd: [("✳ FPGA work", True, None), ("◑ 대상", False, Pat())])
    assert win_tabs.select_tab(1234, "대상") == "selected"
    assert calls == [1]


def test_empty_enumeration_is_error(monkeypatch):
    fake_tabs(monkeypatch, [])          # comtypes 없음·UIA 실패는 전부 여기로 떨어진다
    assert win_tabs.select_tab(1234, "FPGA work") == "error"


def test_select_tab_never_raises(monkeypatch):
    def boom(hwnd):
        raise RuntimeError("COM 폭발")

    monkeypatch.setattr(win_tabs, "tab_names", boom)
    assert win_tabs.select_tab(1234, "FPGA work") == "error"


def test_tab_names_swallows_errors(monkeypatch):
    def boom(hwnd):
        raise OSError("UIA 없음")

    monkeypatch.setattr(win_tabs, "_tabs", boom)
    assert win_tabs.tab_names(1234) == []


def test_si7_no_hwnd_is_stored(monkeypatch):
    hwnd = 0xBEEF4321
    fake_tabs(monkeypatch, [("✳ FPGA work", True), ("◑ 다른 것", False)])
    win_tabs.select_tab(hwnd, "FPGA work")
    ints = [v for v in vars(win_tabs).values() if isinstance(v, int) and not isinstance(v, bool)]
    assert hwnd not in ints
