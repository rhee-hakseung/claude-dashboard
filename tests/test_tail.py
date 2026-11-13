import json

import config
import tail


def write(p, records_or_bytes):
    if isinstance(records_or_bytes, bytes):
        p.write_bytes(records_or_bytes)
    else:
        p.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in records_or_bytes))
    return str(p)


def msg(role, stop=None, ts="2020-01-01T00:00:00Z", cwd=None):
    r = {"type": role, "message": {"role": role, "stop_reason": stop}, "timestamp": ts}
    if cwd:
        r["cwd"] = cwd
    return r


def test_parse_ts_handles_z_and_garbage():
    assert tail.parse_ts("1970-01-01T00:00:00Z") == 0.0
    assert tail.parse_ts("nope") is None and tail.parse_ts(None) is None


def test_parse_ts_naive_is_utc():
    assert tail.parse_ts("2020-01-01T00:00:00") == tail.parse_ts("2020-01-01T00:00:00Z")


def test_parse_ts_out_of_range_is_none():
    assert tail.parse_ts("0001-01-01T00:00:00") is None   # timestamp()가 OSError를 낸다


def test_last_line_is_cost_state_walks_backwards(tmp_path):
    p = write(tmp_path / "a.jsonl", [
        msg("user"),
        msg("assistant", "end_turn", "2020-01-01T00:00:10Z"),
        {"type": "system", "subtype": "turn_duration"},
        {"type": "cost-state", "totalCostUSD": 1.0},
    ])
    got = tail.read_last_message(p)
    assert got["role"] == "assistant" and got["stop_reason"] == "end_turn"
    assert got["timestamp"] == tail.parse_ts("2020-01-01T00:00:10Z")


def test_first_fragment_is_discarded(tmp_path):
    ghost = b'{"message":{"role":"GHOST"},"timestamp":"2000-01-01T00:00:00Z"}'
    line1 = b"X" * 500 + ghost                      # 창이 `{` 정확히 앞에서 잘리도록 만든다
    line2 = json.dumps(msg("user")).encode()
    data = line1 + b"\n" + line2 + b"\n"
    p = tmp_path / "b.jsonl"
    p.write_bytes(data)
    win = len(data) - line1.index(b"{")             # start == ghost의 시작 오프셋
    recs = list(tail.iter_tail_records(str(p), win))
    assert [r["message"]["role"] for r in recs] == ["user"]   # GHOST는 버려진다


def test_expand_window_then_hold(tmp_path, monkeypatch):
    filler = {"type": "attachment", "blob": "z" * 200}
    p = write(tmp_path / "c.jsonl", [msg("user")] + [filler] * 40)
    monkeypatch.setattr(config, "TAIL_WINDOW_BYTES", 256)         # 1차 창에는 메시지가 없다
    monkeypatch.setattr(config, "TAIL_WINDOW_MAX_BYTES", 10 * 1024)
    assert tail.read_last_message(p)["role"] == "user"            # 확장 후 발견

    monkeypatch.setattr(config, "TAIL_WINDOW_MAX_BYTES", 512)     # 확장해도 못 찾으면
    assert tail.read_last_message(p) is None                      # HOLD


def test_no_message_record_at_all_is_hold(tmp_path):
    p = write(tmp_path / "d.jsonl", [{"type": "cost-state"}, {"type": "ai-title", "aiTitle": "x"}])
    assert tail.read_last_message(p) is None


def test_truncated_utf8_at_window_edge_does_not_raise(tmp_path):
    line1 = json.dumps({"type": "attachment", "t": "한" * 60}, ensure_ascii=False).encode("utf-8")
    line2 = json.dumps(msg("assistant", "tool_use")).encode()
    data = line1 + b"\n" + line2 + b"\n"
    p = tmp_path / "e.jsonl"
    p.write_bytes(data)
    # 한글 한 글자(3바이트)의 한가운데에서 창을 연다 — 잘린 조각은 버려지고 예외도 없다
    win = len(data) - (line1.index("한".encode()) + 1)
    assert [r.get("message", {}).get("role") for r in tail.iter_tail_records(str(p), win)] \
        == ["assistant"]
    assert tail.read_last_message(str(p))["role"] == "assistant"


def test_missing_file_returns_none(tmp_path):
    assert tail.read_last_message(str(tmp_path / "nope.jsonl")) is None


def test_iter_head_records_is_bounded(tmp_path):
    p = write(tmp_path / "f.jsonl", [{"type": "x", "i": i} for i in range(100)])
    assert len(list(tail.iter_head_records(p, 5))) == 5


def test_read_last_message_returns_cwd(tmp_path):
    p = write(tmp_path / "g.jsonl", [msg("user", cwd=r"C:\dev\a"), msg("assistant", "end_turn",
                                                                       cwd=r"C:\dev\b")])
    assert tail.read_last_message(p)["cwd"] == r"C:\dev\b"
