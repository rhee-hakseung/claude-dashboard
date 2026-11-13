"""stale 필터·프로젝트 스캔·transcript 해소. 실제 `~/.claude`는 건드리지 않는다
(디렉터리를 전부 tmp_path로 주입한다). 프로세스를 새로 띄우지도 종료하지도 않는다."""
import json
import os

import psutil

import collect_fs
import config
import paths

FILETIME_EPOCH_DIFF = 11644473600.0


def ticks(unix_sec: float) -> str:
    return str(int((unix_sec + FILETIME_EPOCH_DIFF) * 1e7))


def dead_pid() -> int:
    alive = set(psutil.pids())
    for cand in range(999_999_996, 999_000_000, -4):
        if cand not in alive and not psutil.pid_exists(cand):
            return cand
    raise AssertionError("no free pid")


def reg_file(d, name, **kw):
    p = d / name
    p.write_text(json.dumps(kw), encoding="utf-8")
    return p


def test_procstart_roundtrip():
    # 계획서 실측값: 134344517771928757 → 1789978177.2
    assert round(collect_fs.procstart_to_unix("134344517771928757"), 1) == 1789978177.2


def test_stale_filter_accepts_live_process(tmp_path):
    me = psutil.Process()
    reg_file(tmp_path, f"{me.pid}.json", pid=me.pid, sessionId="s-live", cwd=r"C:\dev",
             status="busy", statusUpdatedAt=1.0, procStart=ticks(me.create_time()))
    accepted, rejected, failures = collect_fs.read_registry(str(tmp_path))
    assert [r["sessionId"] for r in accepted] == ["s-live"]
    assert (rejected, failures) == (0, 0)


def test_stale_filter_rejects_dead_pid(tmp_path):
    reg_file(tmp_path, "dead.json", pid=dead_pid(), sessionId="s-dead", status="busy",
             procStart=ticks(1_700_000_000.0))
    accepted, rejected, failures = collect_fs.read_registry(str(tmp_path))
    assert (accepted, rejected, failures) == ([], 1, 0)


def test_stale_filter_rejects_recycled_pid_with_wrong_procstart(tmp_path):
    me = psutil.Process()
    reg_file(tmp_path, "recycled.json", pid=me.pid, sessionId="s-old", status="busy",
             procStart=ticks(me.create_time() - 3600))
    accepted, rejected, failures = collect_fs.read_registry(str(tmp_path))
    assert (accepted, rejected, failures) == ([], 1, 0)


def test_registry_counts_failures_and_ignores_key_files(tmp_path):
    (tmp_path / "broken.json").write_bytes(b"{not json")
    (tmp_path / "secret.key").write_bytes(b"never-open-me")
    accepted, rejected, failures = collect_fs.read_registry(str(tmp_path))
    assert (accepted, rejected, failures) == ([], 0, 1)


def test_registry_rejects_type_drift_but_keeps_good_records(tmp_path):
    me = psutil.Process()
    reg_file(tmp_path, "a-bad.json", pid=me.pid, sessionId="s-bad", cwd=3, status="busy",
             procStart=ticks(me.create_time()))
    reg_file(tmp_path, "b-good.json", pid=me.pid, sessionId="s-good", cwd=r"C:\dev",
             status="busy", procStart=ticks(me.create_time()))
    accepted, rejected, failures = collect_fs.read_registry(str(tmp_path))
    assert [r["sessionId"] for r in accepted] == ["s-good"]
    assert (rejected, failures) == (0, 1)


def test_registry_rejects_non_string_status_and_non_int_pid(tmp_path):
    me = psutil.Process()
    reg_file(tmp_path, "s.json", pid=me.pid, sessionId="x", status=5,
             procStart=ticks(me.create_time()))
    reg_file(tmp_path, "p.json", pid=str(me.pid), sessionId="y", status="busy",
             procStart=ticks(me.create_time()))
    assert collect_fs.read_registry(str(tmp_path)) == ([], 0, 2)


def test_registry_missing_dir_is_empty(tmp_path):
    assert collect_fs.read_registry(str(tmp_path / "nope")) == ([], 0, 0)


def test_scan_projects_excludes_hidden_and_adds_root(tmp_path):
    for n in ("alpha", "beta", ".omc", "node_modules", "dev-dashboard"):
        (tmp_path / n).mkdir()
    (tmp_path / "file.txt").write_text("x")
    out = collect_fs.scan_projects(str(tmp_path))
    names = sorted(p.name for p in out)
    assert names == sorted(["alpha", "beta", paths.ROOT_KEY])
    root = [p for p in out if p.is_root]
    assert len(root) == 1 and root[0].name == paths.ROOT_KEY


def test_find_transcript_fast_path_uses_slug_of_cwd(tmp_path):
    cwd = r"C:\dev\process-game\game"
    d = tmp_path / paths.slug(cwd)
    d.mkdir()
    (d / "sid.jsonl").write_bytes(b"{}\n")
    got = collect_fs.find_transcript({"sessionId": "sid", "cwd": cwd}, str(tmp_path))
    assert got == str(d / "sid.jsonl")


def test_find_transcript_glob_fallback_picks_newest(tmp_path):
    for name, mt in (("C--dev-a", 1_000_000), ("C--dev-b", 2_000_000)):
        d = tmp_path / name
        d.mkdir()
        f = d / "sid.jsonl"
        f.write_bytes(b"{}\n")
        os.utime(f, (mt, mt))
    got = collect_fs.find_transcript({"sessionId": "sid", "cwd": r"C:\dev\zzz"}, str(tmp_path))
    assert os.path.basename(os.path.dirname(got)) == "C--dev-b"


def test_find_transcript_none(tmp_path):
    assert collect_fs.find_transcript({"sessionId": "x", "cwd": ""}, str(tmp_path)) is None
    assert collect_fs.find_transcript({}, str(tmp_path)) is None


def test_last_activity_takes_the_max():
    from model import LiveSession, Project
    p = Project("alpha", "d", 100.0, False)
    s = LiveSession(pid=1, session_id="s", cwd="", status="busy", status_updated_at=300.0,
                    proc_start=0.0, project="alpha")
    assert collect_fs.last_activity(p, {"alpha": 200.0}, [s]) == 300.0
    assert collect_fs.last_activity(p, {"alpha": 200.0}, []) == 200.0
    assert collect_fs.last_activity(p, {}, []) == 100.0          # 둘 다 없을 때만 폴더 mtime
    assert collect_fs.last_activity(p, {"alpha": 50.0}, []) == 50.0   # 기록이 있으면 폴더 mtime 무시


def test_tolerance_constant_is_used(tmp_path):
    me = psutil.Process()
    off = config.PROCSTART_TOLERANCE_SEC / 2
    reg_file(tmp_path, "near.json", pid=me.pid, sessionId="s-near", status="idle",
             procStart=ticks(me.create_time() + off))
    accepted, rejected, _ = collect_fs.read_registry(str(tmp_path))
    assert len(accepted) == 1 and rejected == 0
