"""새 웹 화면의 Python 쪽: 뷰 조립(web_view), 설정(prefs), 버튼(web_api), 현황(stats·activity).
창도 실제 세션도 건드리지 않는다 — 읽고 쓰는 파일은 전부 tmp_path다."""
import json
import time
from datetime import date, datetime, timezone

import pytest

import activity
import config
import highlight
import paths
import prefs
import stats
import web_api
import web_hub
import web_view
from model import WAITING, WORKING, EndedSession, LiveSession, Project, Snapshot


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path / "st"))
    f = tmp_path / "st" / "state.json"
    monkeypatch.setattr(config, "STATE_FILE", str(f))
    return f


def live(sid="L1", project="alpha", state=WORKING, **kw):
    return LiveSession(pid=1, session_id=sid, cwd=r"C:\dev\alpha", status="busy", status_updated_at=0.0,
                       proc_start=0.0, name="n", project=project, state=state, **kw)


def ended(sid="E1", project="alpha", mtime=1.0, **kw):
    return EndedSession(slug="C--dev-alpha", session_id=sid, path="p\\%s.jsonl" % sid, project=project,
                        mtime=mtime, size=1, title="t-" + sid, resume_dir=r"C:\dev\alpha", **kw)


def snap(**kw):
    kw.setdefault("projects", [Project("alpha", r"C:\dev\alpha", 5.0), Project("beta", r"C:\dev\beta", 1.0)])
    kw.setdefault("collected_at", time.time())
    return Snapshot(**kw)


def build(s, p=None, hl=None):
    return web_view.build(s, p or prefs.Prefs(), hl or highlight.Highlight(), stats.Stats(), time.time())


def test_view_groups_sessions_and_counts_the_summary(state):
    hl = highlight.Highlight()
    hl.observe("L2", WAITING)                       # 처음 본 '기다림' = 강조
    v = build(snap(live=[live(), live("L2", state=WAITING)], ended=[ended(), ended("E2", is_stub=True)]), hl=hl)
    alpha = v["projects"][0]
    assert [i["id"] for i in alpha["live"]] == ["L1", "L2"] and alpha["lit"]
    assert v["summary"] == {"working": 1, "waiting": 1, "attention": 1, "ended": 1, "projects": 2}
    assert alpha["ended"][0]["resumable"] and not alpha["ended"][1]["resumable"]


def test_view_uses_alias_as_title_and_keeps_saved_order(state):
    p = prefs.Prefs()
    p.aliases, p.order = {"beta": "베타"}, ["beta", "alpha"]
    v = build(snap(), p)
    assert [(x["title"], x["sub"]) for x in v["projects"]] == [("베타", "beta"), ("alpha", "")]


def test_view_favorites_follow_saved_order_and_skip_missing(state):
    p = prefs.Prefs()
    p.favorites = ["E1", "gone", "L1"]
    v = build(snap(live=[live()], ended=[ended()]), p)
    assert [(f["id"], f["kind"], f["project"]) for f in v["favorites"]] == [("E1", "ended", "alpha"), ("L1", "live", "alpha")]


def test_favorite_follows_a_conversation_handed_to_a_background_session():
    moved = live("NEW", also_ids=("OLD",))
    assert web_view.normalize_favorites(["x", "OLD", "NEW"], [moved]) == ["x", "NEW"]


def test_view_is_stable_while_nothing_changes(state):
    s, p, hl = snap(live=[live()], ended=[ended(mtime=100.0)]), prefs.Prefs(), highlight.Highlight()
    a = web_view.build(s, p, hl, stats.Stats(), 1000.0)
    b = web_view.build(s, p, hl, stats.Stats(), 1005.0)   # 5초 뒤 — 나이 글자는 뷰에 없다
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_prefs_round_trip_keeps_other_keys(state):
    prefs.save_state(geometry=[1, 2, 3, 4])
    p = prefs.Prefs()
    p.favorites, p.folded, p.theme = ["a", "b"], {"alpha"}, "dark"
    p.save("favorites", "folded", "theme")
    q = prefs.Prefs()
    assert (q.favorites, q.folded, q.theme) == (["a", "b"], {"alpha"}, "dark")
    assert prefs.read_state()["geometry"] == [1, 2, 3, 4]


def hub_with(s):
    hub = web_hub.Hub()
    hub.store.update("fast", 0, live=s.live)
    hub.store.update("slow", 0, projects=s.projects, ended=s.ended)
    hub.tick()
    return hub


def test_api_reorder_keeps_names_that_are_not_on_disk_now(state):
    hub = hub_with(snap())
    hub.prefs.order = ["old-folder", "alpha", "beta"]
    web_api.Api(hub).reorder(["beta", "alpha"])
    assert hub.prefs.order == ["beta", "alpha", "old-folder"]
    assert [p["name"] for p in hub.view["projects"]] == ["beta", "alpha"]
    assert json.loads(state.read_text(encoding="utf-8"))["order"] == ["beta", "alpha", "old-folder"]


def test_api_rename_fold_and_favorites_persist(state):
    hub = hub_with(snap(ended=[ended()]))
    api = web_api.Api(hub)
    api.rename("alpha", "  알파  ")
    api.fold("alpha", True)
    api.set_favorites(["E1", "E1", 7])
    alpha = hub.view["projects"][0]
    assert (alpha["title"], alpha["folded"], alpha["ended"][0]["fav"]) == ("알파", True, True)
    api.rename("alpha", "alpha")                    # 폴더 이름과 같으면 별칭을 지운다
    assert "alpha" not in hub.prefs.aliases and hub.prefs.favorites == ["E1"]


def test_api_trash_hides_the_row_at_once_and_reports_refusals(state, monkeypatch):
    hub = hub_with(snap(ended=[ended(), ended("E2")]))
    sent = []
    monkeypatch.setattr(web_api.trash, "send", lambda path: sent.append(path))
    api = web_api.Api(hub)
    api.trash("p\\E1.jsonl")
    assert sent == ["p\\E1.jsonl"] and [e["id"] for e in hub.view["projects"][0]["ended"]] == ["E2"]

    def refuse(path):
        raise web_api.trash.TrashRefused("거절")
    monkeypatch.setattr(web_api.trash, "send", refuse)
    api.trash("p\\E2.jsonl")
    assert hub.view["message"] == "거절" and len(hub.view["projects"][0]["ended"]) == 1


def test_api_resume_marks_the_row_and_skips_duplicates(state, monkeypatch):
    hub = hub_with(snap(ended=[ended(), ended("E2", duplicate_of_newer=True)]))
    calls = []
    monkeypatch.setattr(web_api.launch, "open_resume", lambda d, sid: calls.append((d, sid)))
    api = web_api.Api(hub)
    api.resume("p\\E2.jsonl")
    api.resume("p\\E1.jsonl")
    assert calls == [(r"C:\dev\alpha", "E1")] and hub.view["projects"][0]["ended"][0]["resuming"]


def test_git_status_parsing():
    assert stats.parse_git_status("## main...origin/main [ahead 1]\n M a.py\n?? b/\n") == {"branch": "main", "dirty": 2}
    assert stats.parse_git_status("## No commits yet on master\n?? x\n") == {"branch": "master", "dirty": 1}
    assert stats.parse_git_status("## dev\n") == {"branch": "dev", "dirty": 0}


def test_git_info_is_none_outside_a_repository(tmp_path):
    assert stats.git_info(str(tmp_path), exe="git") is None


def test_dir_size_sums_nested_files(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.bin").write_bytes(b"12345")
    (tmp_path / "y.bin").write_bytes(b"123")
    assert stats.dir_size(str(tmp_path)) == 8


def stamp(day, hour=12):
    """그 로컬 날짜·시각에 해당하는 transcript 한 줄(UTC로 적힌다)."""
    utc = datetime(day.year, day.month, day.day, hour).astimezone().astimezone(timezone.utc)
    return ('{"type":"user","timestamp":"%s","x":"pad"}\n' % utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")).encode()


def test_activity_counts_recent_days_only_and_reads_growth_incrementally(tmp_path):
    f, today = tmp_path / "s.jsonl", date(2026, 11, 12)
    f.write_bytes(stamp(date(2026, 10, 1)) + stamp(date(2026, 11, 10)) * 2 + stamp(today))
    cache = {}
    hist = activity.histogram({"alpha": [str(f)], "beta": []}, cache, today, days=14)
    assert hist["alpha"][-3:] == [2, 0, 1] and sum(hist["alpha"]) == 3 and sum(hist["beta"]) == 0
    with open(f, "ab") as fh:
        fh.write(stamp(today) * 4)
    assert activity.histogram({"alpha": [str(f)]}, cache, today, days=14)["alpha"][-1] == 5


def test_transcripts_by_project_counts_a_copied_conversation_once():
    s = snap(live=[live(transcript_path="a.jsonl")], ended=[ended(), ended("E2", duplicate_of_newer=True)])
    assert stats.transcripts_by_project(s) == {"alpha": ["a.jsonl", "p\\E1.jsonl"]}


def test_root_project_title_uses_the_dev_root_as_subtitle():
    root = Project(paths.ROOT_KEY, config.DEV_ROOT, 0.0, is_root=True)
    assert web_view.project_title(root, {}) == ("루트", config.DEV_ROOT)
    assert web_view.project_title(root, {paths.ROOT_KEY: "Master"}) == ("Master", config.DEV_ROOT)
