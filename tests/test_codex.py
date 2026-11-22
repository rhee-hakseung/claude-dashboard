"""Codex 세션 수집: 명령줄 판정, 프로세스 ↔ thread 짝짓기, 기록 꼬리의 상태, sqlite 읽기.
실제 `~/.codex`도 프로세스도 건드리지 않는다 — 임시 폴더에 작은 DB를 만들어 읽는다."""
import os
import sqlite3

import codex
import config
import launch
from model import WAITING, WORKING

PROJ = os.path.join(config.DEV_ROOT, "myproj")
T0 = 1_795_000_000.0


def tid(at, tail="7aaa-8bbb-cccccccccccc"):
    """그 시각(초)에 만들어진 UUIDv7 꼴 id."""
    h = "%012x" % int(at * 1000)
    return "%s-%s-%s" % (h[:8], h[8:], tail)


def proc(pid, start, cwd=PROJ, resume=None):
    return {"pid": pid, "start": start, "cwd": cwd, "resume": resume}


def test_interactive_tells_sessions_from_servers():
    assert codex.interactive(["codex.exe"]) == (True, None)
    assert codex.interactive(["codex", "-m", "gpt", "fix the bug"]) == (True, None)
    assert codex.interactive(["codex.exe", "-c", "features.x=true", "exec-server"]) == (False, None)
    assert codex.interactive(["codex.exe", "app-server", "--listen", "unix://"]) == (False, None)
    assert codex.interactive(["codex", "exec", "hello"]) == (False, None)
    rid = tid(T0)
    assert codex.interactive(["codex", "resume", rid.upper()]) == (True, rid)
    assert codex.interactive(["codex", "resume", "--last"]) == (True, None)
    assert codex.interactive(["codex", "fork", rid]) == (True, None)     # 새 thread가 된다


def test_clean_cwd_strips_the_long_path_prefix():
    assert codex.clean_cwd("\\\\?\\C:\\dev\\x") == os.path.normpath("C:\\dev\\x")
    assert codex.clean_cwd(None) == "" and codex.clean_cwd(3) == ""


def test_uuid7_time():
    assert abs(codex.uuid7_time(tid(T0)) - T0) < 0.001
    assert codex.uuid7_time("0a1b2c3d-1111-4222-8333-444444444444") is None     # v4
    assert codex.uuid7_time("nope") is None


def test_match_prefers_the_resume_argument():
    a = tid(T0 - 5000)
    assert codex.match_threads([proc(1, T0, resume=a)], {}, set()) == {1: a}


def test_match_new_session_by_id_time_even_before_the_db_knows_it():
    a, other = tid(T0 + 0.5), tid(T0 - 300, "7111-8222-333333333333")
    assert codex.match_threads([proc(1, T0)], {}, {a, other}) == {1: a}


def test_match_skips_a_thread_of_another_folder():
    a = tid(T0 + 1)
    threads = {a: {"cwd": os.path.join(config.DEV_ROOT, "other"), "updated": T0 + 1}}
    assert codex.match_threads([proc(1, T0)], threads, {a}) == {1: None}


def test_match_two_sessions_started_close_together_get_one_thread_each():
    a, b = tid(T0 + 0.3, "7aaa-8bbb-000000000001"), tid(T0 + 4.2, "7aaa-8bbb-000000000002")
    got = codex.match_threads([proc(2, T0 + 4), proc(1, T0)], {}, {a, b})
    assert got == {1: a, 2: b}


def test_match_picker_resume_takes_the_thread_updated_after_start():
    old, older = tid(T0 - 9000, "7aaa-8bbb-000000000001"), tid(T0 - 8000, "7aaa-8bbb-000000000002")
    threads = {old: {"cwd": PROJ, "updated": T0 + 60}, older: {"cwd": PROJ, "updated": T0 - 100}}
    assert codex.match_threads([proc(1, T0)], threads, set()) == {1: old}
    threads[old]["updated"] = T0 - 1          # 아직 아무것도 안 했다 → 모른다
    assert codex.match_threads([proc(1, T0)], threads, set()) == {1: None}


def line(kind):
    return b'{"timestamp":"2026-11-11T05:48:11.904Z","ordinal":1,"type":"event_msg","payload":{"type":"' + kind + b'","turn_id":"x"}}\n'


def test_last_event_reads_the_newest_turn_event():
    assert codex.last_event(line(b"task_started") + line(b"token_count") + line(b"task_complete")) == "task_complete"
    assert codex.last_event(line(b"task_complete") + line(b"task_started") + line(b"item_completed")) == "task_started"
    assert codex.last_event(line(b"turn_aborted")) == "turn_aborted"
    assert codex.last_event(b"") is None


def test_last_event_ignores_the_same_words_inside_a_message():
    quoted = b'{"type":"response_item","payload":{"type":"message","text":"{\\"type\\":\\"event_msg\\",\\"payload\\":{\\"type\\":\\"task_started\\"}}"}}\n'
    assert codex.last_event(line(b"task_complete") + quoted) == "task_complete"


def test_tail_event_widens_the_window_and_caches(tmp_path):
    f = tmp_path / "rollout.jsonl"
    f.write_bytes(line(b"task_started") + b'{"pad":"' + b"x" * (300 * 1024) + b'"}\n')
    cache = {}
    assert codex._tail_event(str(f), cache)[0] == "task_started"      # 첫 창(256 KB) 밖에 있다
    assert codex._tail_event(str(f), cache)[0] == "task_started" and str(f) in cache
    assert codex._tail_event(str(tmp_path / "none.jsonl"), cache) == (None, 0.0)


def make_home(tmp_path, monkeypatch, rows):
    home = tmp_path / ".codex"
    home.mkdir()
    con = sqlite3.connect(str(home / "state_5.sqlite"))
    con.execute("create table threads (id text, cwd text, title text, name text, updated_at integer,"
                " updated_at_ms integer, archived integer, rollout_path text, agent_role text)")
    con.executemany("insert into threads values (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    sqlite3.connect(str(home / "state_4.sqlite")).close()            # 옛 버전 파일은 무시된다
    monkeypatch.setattr(config, "CODEX_HOME", str(home))
    return home


def test_ended_sessions_lists_project_threads_only(tmp_path, monkeypatch):
    a, b, c, d, e = (tid(T0 + i, "7aaa-8bbb-00000000000%d" % i) for i in range(5))
    make_home(tmp_path, monkeypatch, [
        (a, "\\\\?\\" + PROJ if config.IS_WIN else PROJ, "first message " * 10, "지은 이름", 1, int(T0 * 1000), 0, "", None),
        (b, os.path.join(PROJ, "sub"), "첫 메시지   앞부분", None, int(T0), None, 0, "", None),
        (c, PROJ, "보관한 것", None, 1, 1, 1, "", None),
        (d, os.path.join(os.path.dirname(config.DEV_ROOT), "elsewhere"), "밖", None, 1, 1, 0, "", None),
        (e, PROJ, "하위 에이전트", None, 1, 1, 0, "", "worker"),
    ])
    rows = {r.session_id: r for r in codex.ended_sessions(set())}
    assert set(rows) == {a, b}
    assert rows[a].title == "지은 이름" and rows[a].mtime == T0 and rows[a].project == "myproj"
    assert rows[a].path == "codex:" + a and rows[a].agent == "codex" and rows[a].resume_dir is None
    assert rows[b].title == "첫 메시지 앞부분" and rows[b].mtime == float(int(T0))
    assert codex.ended_sessions({a, b}) == []


def test_live_sessions_reads_state_from_the_rollout(tmp_path, monkeypatch):
    a = tid(T0 + 1)
    roll = tmp_path / "rollout.jsonl"
    roll.write_bytes(line(b"task_complete") + line(b"task_started"))
    make_home(tmp_path, monkeypatch, [(a, PROJ, "제목", None, int(T0), int(T0 * 1000) + 5000, 0, str(roll), None)])
    monkeypatch.setattr(codex, "_scan", lambda: [proc(77, T0), proc(78, T0, cwd=os.path.dirname(config.DEV_ROOT))])
    monkeypatch.setattr(codex.psutil, "pid_exists", lambda pid: True)
    monkeypatch.setattr(codex.term, "can_jump", lambda pid: True)
    monkeypatch.setattr(codex.term, "launcher_gone", lambda pid: False)
    memo = {}
    (s,) = codex.live_sessions(memo, now=T0 + 10)       # 프로젝트 폴더 밖의 78은 버린다
    assert (s.pid, s.session_id, s.state, s.agent, s.name) == (77, a, WORKING, "codex", "제목")
    assert s.jumpable and not s.orphan and s.tab_title == "myproj" and s.project == "myproj"
    roll.write_bytes(line(b"task_started") + line(b"task_complete") + b"\n")
    assert codex.live_sessions(memo, now=T0 + 11)[0].state == WAITING


def test_live_session_without_a_thread_waits_and_cannot_be_reopened(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch, [])
    monkeypatch.setattr(codex, "_scan", lambda: [proc(77, T0)])
    monkeypatch.setattr(codex.psutil, "pid_exists", lambda pid: True)
    monkeypatch.setattr(codex.term, "can_jump", lambda pid: False)
    monkeypatch.setattr(codex.term, "launcher_gone", lambda pid: True)
    (s,) = codex.live_sessions({}, now=T0 + 10)
    assert s.session_id == "codex-pid-77" and s.state == WAITING and s.orphan and not s.jumpable


def test_no_codex_home_means_no_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CODEX_HOME", str(tmp_path / "missing"))
    assert codex.threads() == {} and codex.ended_sessions(set()) == [] and not codex.available()


def test_launch_uses_codex_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(launch, "_open", lambda d, body: calls.append((d, body)))
    a = tid(T0)
    launch.open_resume("D", a, "codex")
    launch.open_new_codex("D")
    launch.open_resume("D", "abc")
    assert calls == [("D", "codex resume " + a), ("D", "codex"), ("D", "claude --resume abc")]
    try:
        launch.open_resume("D", "codex-pid-7; rm", "codex")
    except launch.LaunchFailed:
        pass
    else:
        raise AssertionError("UUID가 아닌 id는 띄우지 않아야 한다")
    assert len(calls) == 3
