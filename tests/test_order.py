"""프로젝트 고정 순서: state.json 로드 관용성, order_projects, 저장 병합.
읽고 쓰는 파일은 전부 tmp_path다(진짜 state.json은 건드리지 않는다)."""
import json

import pytest

import config
import model
import prefs
from model import Project


def P(name, act=0.0, root=False):
    return Project(name, "d", act, root)


def names(ps):
    return [p.name for p in ps]


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path / "st"))
    f = tmp_path / "st" / "state.json"
    monkeypatch.setattr(config, "STATE_FILE", str(f))
    return f


# ── 로드 관용성 ──────────────────────────────────────────────────────────────
def test_absent_file_gives_empty_order(state):
    assert prefs.load_order() == []


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", json.dumps({"order": "abc"}),
                                  json.dumps({"order": {"a": 1}}), json.dumps({"order": None})])
def test_corrupt_or_wrong_shape_gives_empty_order(state, text):
    state.parent.mkdir()
    state.write_text(text, encoding="utf-8")
    assert prefs.load_order() == []


def test_non_strings_and_duplicates_are_dropped_keeping_first(state):
    state.parent.mkdir()
    state.write_text(json.dumps({"order": ["b", 3, None, "a", "b", ".", ["x"], "a"]}),
                     encoding="utf-8")
    assert prefs.load_order() == ["b", "a", "."]


# ── order_projects ───────────────────────────────────────────────────────────
def test_full_saved_order_is_followed_exactly():
    ps = [P("a", 99), P(".", 50, True), P("b", 1)]
    assert names(model.order_projects(ps, ["b", ".", "a"])) == ["b", ".", "a"]


def test_no_saved_order_is_activity_order_with_root_last():
    ps = [P("b", 10), P(".", 999, True), P("a", 10), P("c", 99)]
    assert names(model.order_projects(ps, [])) == ["c", "a", "b", "."]


def test_newcomers_follow_in_activity_order_root_last_among_them():
    ps = [P("old", 1), P("new1", 50), P(".", 900, True), P("new2", 70), P("fix", 2)]
    assert names(model.order_projects(ps, ["fix", "old"])) == \
        ["fix", "old", "new2", "new1", "."]


def test_saved_root_keeps_its_saved_place():
    ps = [P("a", 99), P(".", 1, True)]
    assert names(model.order_projects(ps, [".", "a"])) == [".", "a"]


def test_stale_names_are_ignored_and_input_not_mutated():
    ps = [P("a", 1), P("b", 2)]
    saved = ["gone", "a", "also-gone", "b"]
    assert names(model.order_projects(ps, saved)) == ["a", "b"]
    assert saved == ["gone", "a", "also-gone", "b"]


def test_order_save_merges_with_aliases(state):
    prefs.save_state(aliases={"a": "알파"})
    prefs.save_state(order=["b", "a"])
    assert json.loads(state.read_text(encoding="utf-8")) == {"aliases": {"a": "알파"}, "order": ["b", "a"]}
    assert not (state.parent / "state.json.tmp").exists()
    assert prefs.load_aliases() == {"a": "알파"} and prefs.load_order() == ["b", "a"]
