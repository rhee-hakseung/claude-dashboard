"""프로젝트 별칭: state.json 저장/병합/복구와 표시 문자열. Tk 루트는 만들지 않는다.
읽고 쓰는 파일은 전부 tmp_path다(진짜 state.json은 건드리지 않는다)."""
import json

import pytest

import config
import paths
import ui_project
import ui_shell
from model import Project

ALPHA = Project("integrated-optim-solution", r"C:\dev\integrated-optim-solution", 0.0)
ROOT = Project(paths.ROOT_KEY, config.DEV_ROOT, 0.0, is_root=True)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path / "st"))
    f = tmp_path / "st" / "state.json"
    monkeypatch.setattr(config, "STATE_FILE", str(f))
    return f


class FakeRoot:
    def winfo_x(self):
        return -2560

    def winfo_y(self):
        return 10

    def winfo_width(self):
        return 1000

    def winfo_height(self):
        return 700


def test_alias_round_trip_is_saved_immediately_and_atomically(state):
    a = ui_project.set_alias({}, ALPHA.name, "  LoRR ", ALPHA.name)
    ui_shell.save_state(aliases=a)
    assert json.loads(state.read_text(encoding="utf-8")) == {"aliases": {ALPHA.name: "LoRR"}}
    assert not (state.parent / "state.json.tmp").exists()
    assert ui_shell.load_aliases() == {ALPHA.name: "LoRR"}


@pytest.mark.parametrize("text", ["", "   ", "integrated-optim-solution"])
def test_empty_or_folder_name_removes_the_alias(text):
    assert ui_project.set_alias({ALPHA.name: "LoRR", "x": "y"}, ALPHA.name, text,
                                ALPHA.name) == {"x": "y"}


def test_root_default_label_removes_the_alias():
    got = ui_project.set_alias({".": "홈"}, ".", config.ROOT_LABEL, config.ROOT_LABEL)
    assert got == {}


def test_close_path_merges_and_keeps_aliases(state):
    ui_shell.save_state(aliases={ALPHA.name: "LoRR"})
    ui_shell.save_geometry(FakeRoot())
    data = json.loads(state.read_text(encoding="utf-8"))
    assert data == {"aliases": {ALPHA.name: "LoRR"}, "geometry": [-2560, 10, 1000, 700]}
    assert ui_shell.load_geometry() == [-2560, 10, 1000, 700]


def test_alias_save_keeps_geometry(state):
    ui_shell.save_geometry(FakeRoot())
    ui_shell.save_state(aliases={})
    assert ui_shell.load_geometry() == [-2560, 10, 1000, 700]


def test_absent_file_gives_empty_aliases(state):
    assert ui_shell.load_aliases() == {}


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '"s"', json.dumps({"aliases": [1]}),
                                  json.dumps({"aliases": "x"})])
def test_corrupt_or_wrong_shape_gives_empty_aliases(state, text):
    state.parent.mkdir()
    state.write_text(text, encoding="utf-8")
    assert ui_shell.load_aliases() == {}


def test_non_string_values_are_ignored(state):
    state.parent.mkdir()
    state.write_text(json.dumps({"aliases": {"a": "A", "b": 3, "c": None, "d": ""}}),
                     encoding="utf-8")
    assert ui_shell.load_aliases() == {"a": "A"}


def test_corrupt_file_is_replaced_on_save(state):
    state.parent.mkdir()
    state.write_text("{not json", encoding="utf-8")
    ui_shell.save_state(aliases={"a": "A"})
    assert ui_shell.load_aliases() == {"a": "A"}


def test_display_name_alias_first_folder_in_parentheses():
    assert ui_project.display_name(ALPHA, {ALPHA.name: "LoRR"}) == \
        "LoRR (integrated-optim-solution)"
    assert ui_project.display_name(ALPHA, {}) == "integrated-optim-solution"


def test_display_name_root():
    assert ui_project.display_name(ROOT, {}) == config.ROOT_LABEL
    assert ui_project.display_name(ROOT, {paths.ROOT_KEY: "홈"}) == "홈 (C:\\dev)"
