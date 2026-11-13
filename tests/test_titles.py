"""/rename 제목: 라이브 행 라벨(탭 제목 우선)과 끝난 기록의 custom-title 우선."""
import inventory
import web_view
from model import LiveSession
from test_inventory import DEV, PROJECTS, SID_A, make, user


def live(tab="Claude Code", name="dev-2e", sid="abcdef0123456789"):
    return LiveSession(pid=1, session_id=sid, cwd=DEV, status="busy", status_updated_at=0.0,
                       proc_start=0.0, name=name, tab_title=tab)


def test_live_label_prefers_tab_title_over_registry_name():
    assert web_view.live_label(live(tab="세션 관리 도구")) == "세션 관리 도구"


def test_live_label_default_title_falls_back_to_registry_name():
    assert web_view.live_label(live()) == "dev-2e"


def test_live_label_default_title_without_name_keeps_default():
    assert web_view.live_label(live(name="")) == "Claude Code"


def test_live_label_last_resort_is_session_prefix():
    assert web_view.live_label(live(tab="", name="")) == "abcdef01"


def title_of(tmp_path, records):
    make(tmp_path, "C--dev-paper-search", SID_A, records)
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    return rows[0].title


def test_ended_title_prefers_newest_custom_title(tmp_path):
    assert title_of(tmp_path, [
        user(), {"type": "custom-title", "customTitle": "옛 이름"},
        {"type": "ai-title", "aiTitle": "자동 제목"},
        {"type": "custom-title", "customTitle": "LoRR 튜닝"},
        {"type": "ai-title", "aiTitle": "더 새 자동 제목"}]) == "LoRR 튜닝"


def test_ended_title_custom_title_in_head_beats_ai_title_in_tail(tmp_path):
    filler = [{"type": "attachment", "z": "q" * 900}] * 400    # 머리 창(50줄)·꼬리 창 분리
    assert title_of(tmp_path, [
        user(), {"type": "custom-title", "customTitle": "앞쪽 이름"}] + filler +
        [{"type": "ai-title", "aiTitle": "자동 제목"}]) == "앞쪽 이름"


def test_ended_title_without_custom_title_uses_ai_title(tmp_path):
    assert title_of(tmp_path, [user(), {"type": "ai-title", "aiTitle": "자동 제목"}]) == "자동 제목"
