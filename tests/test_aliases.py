"""프로젝트 별칭: state.json 저장/병합/복구.
읽고 쓰는 파일은 전부 tmp_path다(진짜 state.json은 건드리지 않는다)."""
import json

import pytest

import config
import prefs
from model import Project

ALPHA = Project("integrated-optim-solution", r"C:\dev\integrated-optim-solution", 0.0)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path / "st"))
    f = tmp_path / "st" / "state.json"
    monkeypatch.setattr(config, "STATE_FILE", str(f))
    return f


def test_alias_round_trip_is_saved_immediately_and_atomically(state):
    a = prefs.set_alias({}, ALPHA.name, "  LoRR ", ALPHA.name)
    prefs.save_state(aliases=a)
    assert json.loads(state.read_text(encoding="utf-8")) == {"aliases": {ALPHA.name: "LoRR"}}
    assert not (state.parent / "state.json.tmp").exists()
    assert prefs.load_aliases() == {ALPHA.name: "LoRR"}


@pytest.mark.parametrize("text", ["", "   ", "integrated-optim-solution"])
def test_empty_or_folder_name_removes_the_alias(text):
    assert prefs.set_alias({ALPHA.name: "LoRR", "x": "y"}, ALPHA.name, text,
                                ALPHA.name) == {"x": "y"}


def test_root_default_label_removes_the_alias():
    got = prefs.set_alias({".": "홈"}, ".", config.ROOT_LABEL, config.ROOT_LABEL)
    assert got == {}


def test_absent_file_gives_empty_aliases(state):
    assert prefs.load_aliases() == {}


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '"s"', json.dumps({"aliases": [1]}),
                                  json.dumps({"aliases": "x"})])
def test_corrupt_or_wrong_shape_gives_empty_aliases(state, text):
    state.parent.mkdir()
    state.write_text(text, encoding="utf-8")
    assert prefs.load_aliases() == {}


def test_non_string_values_are_ignored(state):
    state.parent.mkdir()
    state.write_text(json.dumps({"aliases": {"a": "A", "b": 3, "c": None, "d": ""}}),
                     encoding="utf-8")
    assert prefs.load_aliases() == {"a": "A"}


def test_corrupt_file_is_replaced_on_save(state):
    state.parent.mkdir()
    state.write_text("{not json", encoding="utf-8")
    prefs.save_state(aliases={"a": "A"})
    assert prefs.load_aliases() == {"a": "A"}
