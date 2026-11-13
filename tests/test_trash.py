"""휴지통 3중 가드. 실제 휴지통으로 무엇도 보내지 않는다 — send2trash를 가로채 기록만 한다.
디렉터리는 전부 tmp_path다. 프로세스를 새로 띄우지도, 건드리지도 않는다."""
import json
import os

import psutil
import pytest

import collect_fs
import config
import trash

FILETIME_EPOCH_DIFF = 11644473600.0


@pytest.fixture
def calls(monkeypatch):
    """send2trash 호출을 가로채 인자만 모은다 — 실제 휴지통은 쓰지 않는다."""
    got = []
    monkeypatch.setattr(trash.send2trash, "send2trash", lambda p: got.append(p))
    return got


@pytest.fixture
def dirs(tmp_path):
    projects = tmp_path / "projects"
    sessions = tmp_path / "sessions"
    (projects / "C--dev-alpha").mkdir(parents=True)
    sessions.mkdir()
    return projects, sessions


def make(projects, name, slug="C--dev-alpha", age=3600.0, now=1_800_000_000.0):
    p = projects / slug / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b'{"type":"x"}\n')
    os.utime(p, (now - age, now - age))
    return p


def test_normal_goes_to_trash(dirs, calls):
    projects, sessions = dirs
    f = make(projects, "abc-123.jsonl")
    trash.send(str(f), str(projects), str(sessions), now=1_800_000_000.0)
    assert calls == [str(f)]


def test_other_extension_is_refused(dirs, calls):
    projects, sessions = dirs
    f = make(projects, "abc-123.txt")
    with pytest.raises(trash.TrashRefused):
        trash.send(str(f), str(projects), str(sessions), now=1_800_000_000.0)
    assert calls == []


def test_wrong_depth_is_refused(dirs, calls):
    projects, sessions = dirs
    deep = make(projects, "c.jsonl", slug=os.path.join("a", "b"))
    shallow = projects / "c.jsonl"
    shallow.write_bytes(b"{}\n")
    for target in (deep, shallow):
        with pytest.raises(trash.TrashRefused):
            trash.send(str(target), str(projects), str(sessions), now=1_800_000_000.0)
    assert calls == []


def test_dotdot_escape_is_refused(dirs, calls):
    projects, sessions = dirs
    f = make(projects, "abc-123.jsonl")
    sneaky = os.path.join(str(projects), "C--dev-alpha", "..", "..", "outside.jsonl")
    (projects.parent / "outside.jsonl").write_bytes(b"{}\n")
    with pytest.raises(trash.TrashRefused):
        trash.send(sneaky, str(projects), str(sessions), now=1_800_000_000.0)
    assert calls == [] and f.exists()


def test_live_session_id_is_refused(dirs, calls):
    """레지스트리를 호출 시점에 다시 읽는지 본다. 형제 `x.key`는 절대 열리면 안 된다."""
    projects, sessions = dirs
    me = psutil.Process()
    sid = "live-abc"
    ticks = str(int((me.create_time() + FILETIME_EPOCH_DIFF) * 1e7))
    (sessions / ("%d.json" % os.getpid())).write_text(
        json.dumps({"pid": me.pid, "sessionId": sid, "cwd": config.DEV_ROOT,
                    "status": "busy", "procStart": ticks}), encoding="utf-8")
    (sessions / "x.key").write_bytes(b"never-open-me")
    f = make(projects, sid + ".jsonl")
    with pytest.raises(trash.TrashRefused) as ei:
        trash.send(str(f), str(projects), str(sessions), now=1_800_000_000.0)
    assert "살아있는" in str(ei.value)
    assert calls == []
    # 가드 2가 실제로 레지스트리를 읽었는지 교차 확인 (`*.key`는 글롭 밖이다).
    assert [r["sessionId"] for r in collect_fs.read_registry(str(sessions))[0]] == [sid]


def test_fresh_mtime_is_refused_and_old_is_allowed(dirs, calls):
    projects, sessions = dirs
    now = 1_800_000_000.0
    fresh = make(projects, "fresh.jsonl", age=1.0, now=now)
    with pytest.raises(trash.TrashRefused) as ei:
        trash.send(str(fresh), str(projects), str(sessions), now=now)
    assert "5초" in str(ei.value)
    assert calls == []
    old = make(projects, "old.jsonl", age=6.0, now=now)
    trash.send(str(old), str(projects), str(sessions), now=now)
    assert calls == [str(old)]


def test_unreadable_registry_fails_closed(dirs, calls):
    """가드 ②는 fail-closed다 — 못 읽은 `*.json`이 하필 이 세션이었을 수 있다."""
    projects, sessions = dirs
    (sessions / "broken.json").write_text("{not json", encoding="utf-8")
    f = make(projects, "abc-123.jsonl")
    with pytest.raises(trash.TrashRefused) as ei:
        trash.send(str(f), str(projects), str(sessions), now=1_800_000_000.0)
    assert "확인할 수 없어" in str(ei.value)
    assert calls == [] and f.exists()


def test_session_id_comparison_is_case_insensitive(dirs, calls):
    projects, sessions = dirs
    me = psutil.Process()
    ticks = str(int((me.create_time() + FILETIME_EPOCH_DIFF) * 1e7))
    (sessions / ("%d.json" % os.getpid())).write_text(
        json.dumps({"pid": me.pid, "sessionId": "LIVE-ABC", "cwd": config.DEV_ROOT,
                    "status": "busy", "procStart": ticks}), encoding="utf-8")
    f = make(projects, "live-abc.jsonl")
    with pytest.raises(trash.TrashRefused) as ei:
        trash.send(str(f), str(projects), str(sessions), now=1_800_000_000.0)
    assert "살아있는" in str(ei.value)
    assert calls == []


def test_min_age_constant_is_used():
    assert config.TRASH_MIN_AGE_SEC == 5
