"""창 위치 복원의 입력 검증. Tk 루트는 만들지 않는다 — load_geometry는 순수 함수다.
읽는 파일은 전부 tmp_path다(진짜 state.json은 건드리지 않는다)."""
import json

import config
import ui_shell


def state(tmp_path, monkeypatch, text=None):
    f = tmp_path / "state.json"
    if text is not None:
        f.write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "STATE_FILE", str(f))
    return f


def test_absent_file_returns_none(tmp_path, monkeypatch):
    state(tmp_path, monkeypatch)
    assert ui_shell.load_geometry() is None


def test_corrupt_json_returns_none(tmp_path, monkeypatch):
    state(tmp_path, monkeypatch, "{not json")
    assert ui_shell.load_geometry() is None


def test_missing_key_returns_none(tmp_path, monkeypatch):
    state(tmp_path, monkeypatch, json.dumps({"other": [1, 2, 3, 4]}))
    assert ui_shell.load_geometry() is None


def test_wrong_shape_returns_none(tmp_path, monkeypatch):
    state(tmp_path, monkeypatch, json.dumps({"geometry": [1, 2, 3]}))
    assert ui_shell.load_geometry() is None


def test_non_sized_value_returns_none(tmp_path, monkeypatch):
    state(tmp_path, monkeypatch, json.dumps({"geometry": 5}))
    assert ui_shell.load_geometry() is None


def test_non_int_values_return_none(tmp_path, monkeypatch):
    state(tmp_path, monkeypatch, json.dumps({"geometry": ["a", "b", "c", "d"]}))
    assert ui_shell.load_geometry() is None


def test_null_values_return_none(tmp_path, monkeypatch):
    state(tmp_path, monkeypatch, json.dumps({"geometry": [None, None, None, None]}))
    assert ui_shell.load_geometry() is None


def test_valid_geometry_survives_including_negative_x(tmp_path, monkeypatch):
    state(tmp_path, monkeypatch, json.dumps({"geometry": [-2560, 0, 1000, 700]}))
    assert ui_shell.load_geometry() == [-2560, 0, 1000, 700]
