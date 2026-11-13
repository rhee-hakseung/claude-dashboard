"""프로젝트 고정 순서(끌기): state.json 로드 관용성, order_projects, 옮기기와 저장 병합.
Tk 루트를 만들지 않는다. 읽고 쓰는 파일은 전부 tmp_path다(진짜 state.json은 건드리지 않는다)."""
import json

import pytest

import config
import model
import ui_order
import ui_shell
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


class FakeRows:
    """ui_order.commit이 만지는 속성만 가진 가짜 Rows."""

    def __init__(self, shown, order):
        self._groups = [(P(n), [], [], []) for n in shown]
        self.order, self.message, self.invalidated = order, "", 0

    def invalidate(self):
        self.invalidated += 1


# ── 로드 관용성 ──────────────────────────────────────────────────────────────
def test_absent_file_gives_empty_order(state):
    assert ui_shell.load_order() == []


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", json.dumps({"order": "abc"}),
                                  json.dumps({"order": {"a": 1}}), json.dumps({"order": None})])
def test_corrupt_or_wrong_shape_gives_empty_order(state, text):
    state.parent.mkdir()
    state.write_text(text, encoding="utf-8")
    assert ui_shell.load_order() == []


def test_non_strings_and_duplicates_are_dropped_keeping_first(state):
    state.parent.mkdir()
    state.write_text(json.dumps({"order": ["b", 3, None, "a", "b", ".", ["x"], "a"]}),
                     encoding="utf-8")
    assert ui_shell.load_order() == ["b", "a", "."]


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


def test_arrange_orders_view_groups():
    groups = [(P("a", 1), ["la"], [], []), (P("b", 2), [], ["eb"], [])]
    out = ui_order.arrange(groups, ["a"])
    assert [g[0].name for g in out] == ["a", "b"] and out[0][1] == ["la"]


# ── 끌어 옮기기 ──────────────────────────────────────────────────────────────
def test_drop_saves_whole_shown_order_including_newcomers(state):
    rows = FakeRows(["fix", "new2", "new1", "."], ["fix"])
    ui_order.commit(rows, 0, 2)          # fix를 new1 앞 틈으로
    assert rows.order == ["new2", "fix", "new1", "."]
    assert json.loads(state.read_text(encoding="utf-8")) == {"order": rows.order}
    assert rows.invalidated == 1 and rows.message == ""


@pytest.mark.parametrize("i,slot,want", [
    (0, 4, ["b", "c", "d", "a"]),        # 맨 뒤로
    (3, 0, ["d", "a", "b", "c"]),        # 맨 앞으로
    (1, 3, ["a", "c", "b", "d"]),        # 아래로 한 칸
    (2, 1, ["a", "c", "b", "d"]),        # 위로 한 칸
    (1, 1, ["a", "b", "c", "d"]),        # 자기 위 틈 = 제자리
    (1, 2, ["a", "b", "c", "d"]),        # 자기 아래 틈 = 제자리
    (0, 99, ["b", "c", "d", "a"]),       # 범위 밖 틈은 끝으로 자른다
    (7, 0, ["a", "b", "c", "d"]),        # 없는 줄은 그대로
])
def test_moved(i, slot, want):
    assert ui_order.moved(["a", "b", "c", "d"], i, slot) == want


@pytest.mark.parametrize("y,slot", [(0, 0), (15, 1), (50, 2), (200, 3)])
def test_slot_for_counts_midpoints_above_pointer(y, slot):
    assert ui_order.slot_for([10, 40, 90], y) == slot


def test_drop_in_place_does_not_write(state):
    rows = FakeRows(["a", "b"], ["b", "a"])
    ui_order.commit(rows, 0, 1)
    assert rows.order == ["b", "a"] and not state.exists() and rows.invalidated == 1


def test_stale_saved_names_are_kept_at_the_end():
    assert ui_order.reorder(["a", "b"], ["gone", "b", "a"], 0, 2) == ["b", "a", "gone"]


def test_order_save_merges_with_aliases_and_geometry(state):
    ui_shell.save_state(geometry=[-2560, 10, 1000, 700], aliases={"a": "알파"})
    ui_order.commit(FakeRows(["a", "b"], []), 1, 0)
    data = json.loads(state.read_text(encoding="utf-8"))
    assert data == {"geometry": [-2560, 10, 1000, 700], "aliases": {"a": "알파"},
                    "order": ["b", "a"]}
    assert not (state.parent / "state.json.tmp").exists()
    assert ui_shell.load_aliases() == {"a": "알파"} and ui_shell.load_order() == ["b", "a"]


def test_save_failure_goes_to_the_status_line(state, monkeypatch):
    def boom(**kw):
        raise OSError("disk")
    monkeypatch.setattr(ui_shell, "save_state", boom)
    rows = FakeRows(["a", "b"], [])
    ui_order.commit(rows, 0, 2)
    assert rows.order == ["b", "a"] and "disk" in rows.message and rows.invalidated == 1
