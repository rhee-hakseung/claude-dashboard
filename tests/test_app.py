"""UI 층의 순수 함수 3개: 뷰모델 dedup, 상태줄 조립, 강조 FSM 적용.
순수 함수만 본다(viewmodel 모듈을 app이라는 이름으로 부른다)."""
import viewmodel as app
from model import ENDED, WAITING, WORKING, EndedSession, LiveSession, Project, Snapshot

SID = "aaaa-1111"


def live(sid=SID, project="alpha", state=WORKING, disagree=False):
    return LiveSession(pid=1, session_id=sid, cwd=r"C:\dev\alpha", status="busy",
                       status_updated_at=0.0, proc_start=0.0, name="n",
                       project=project, state=state, sources_disagree=disagree)


def ended(sid=SID, project="alpha", mtime=1.0):
    return EndedSession(slug="C--dev-alpha", session_id=sid, path="p\\%s.jsonl" % sid,
                        project=project, mtime=mtime, size=1, title="t")


def snap(**kw):
    kw.setdefault("projects", [Project("alpha", r"C:\dev\alpha", 0.0)])
    return Snapshot(**kw)


class FakeHighlight:
    """호출 순서까지 기록한다 — ENDED 관측이 forget보다 **먼저**여야 OFF ③이 산다."""

    def __init__(self):
        self.calls = []

    def observe(self, sid, state):
        self.calls.append(("observe", sid, state))

    def set_disagree(self, sid, value):
        self.calls.append(("set_disagree", sid, bool(value)))

    def clear_resuming(self, sid):
        self.calls.append(("clear_resuming", sid))

    def forget(self, sid):
        self.calls.append(("forget", sid))


def test_viewmodel_drops_an_ended_row_whose_session_is_live_again():
    """SI-5: 끝남 목록은 5초마다만 dedup되고 레지스트리는 0.5초마다다 — 신선한 쪽이 이긴다."""
    s = snap(live=[live()], ended=[ended(), ended(sid="bbbb-2222")])
    (_p, lives, ends, _js), = app.viewmodel(s)
    assert [x.session_id for x in lives] == [SID]
    assert [e.session_id for e in ends] == ["bbbb-2222"]


def test_viewmodel_keeps_ended_rows_when_nothing_is_live():
    s = snap(ended=[ended()])
    (_p, lives, ends, _js), = app.viewmodel(s)
    assert lives == [] and [e.session_id for e in ends] == [SID]


def test_viewmodel_groups_jobs_by_project():
    s = snap(jobs=[{"project": "alpha", "name": "x"}])
    (_p, _lives, _ends, js), = app.viewmodel(s)
    assert js[0]["name"] == "x"


def test_status_line_emits_the_four_fragments_in_order():
    s = snap(failures=2, disagreements=1)
    assert app.status_line(s, "창을 찾을 수 없음", True) == (
        "수집 실패 2회   ·   상태 출처 불일치 1건   ·   "
        "창을 찾을 수 없음   ·   수집 중단 — 재시작 필요")


def test_status_line_is_empty_when_nothing_to_say():
    assert app.status_line(snap(), "", False) == ""


def test_status_line_shows_only_the_stale_fragment():
    assert app.status_line(snap(), "", True) == "수집 중단 — 재시작 필요"


def test_apply_highlight_clears_resuming_for_a_session_that_came_back():
    hl = FakeHighlight()
    ids = app.apply_highlight(hl, snap(live=[live(state=WAITING, disagree=True)]), set())
    assert ids == {SID}
    assert hl.calls == [("observe", SID, WAITING), ("set_disagree", SID, True),
                        ("clear_resuming", SID)]


def test_apply_highlight_observes_ended_before_forget_for_a_departed_session():
    hl = FakeHighlight()
    ids = app.apply_highlight(hl, snap(), {SID})
    assert ids == set()
    assert hl.calls == [("observe", SID, ENDED), ("forget", SID)]


def test_apply_highlight_does_not_forget_a_session_that_is_still_live():
    hl = FakeHighlight()
    app.apply_highlight(hl, snap(live=[live()]), {SID})
    assert ("forget", SID) not in hl.calls


def test_viewmodel_hides_the_window_side_record_of_a_merged_row():
    """창 쪽 기록(대화가 백그라운드로 넘어간 원본)은 살아 있는 줄의 일부다 — [재개] 줄로 뜨면 안 된다."""
    merged = live(sid="bg-1")
    merged.also_ids = (SID,)
    s = snap(live=[merged], ended=[ended(), ended(sid="bbbb-2222")])
    (_p, _lives, ends, _js), = app.viewmodel(s)
    assert [e.session_id for e in ends] == ["bbbb-2222"]
