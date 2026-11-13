import json
import os

import pytest

import config
import inventory
import paths

SID_A = "aaaaaaaa-1111-2222-3333-444444444444"
SID_B = "bbbbbbbb-1111-2222-3333-444444444444"
PROJECTS = ["paper-search", "process-game"]
DEV = r"C:\dev"


def make(root, folder_slug, sid, records, pad_to=0):
    d = root / folder_slug
    d.mkdir(exist_ok=True)
    p = d / f"{sid}.jsonl"
    blob = b"".join(json.dumps(r, ensure_ascii=False).encode() + b"\n" for r in records)
    if pad_to and len(blob) < pad_to:
        filler = json.dumps({"type": "attachment", "z": "q" * 900}).encode() + b"\n"
        blob += filler * ((pad_to - len(blob)) // len(filler) + 1)
    p.write_bytes(blob)
    return str(p)


def user(text="안녕하세요 첫 메시지입니다", cwd=r"C:\dev\paper-search"):
    return {"type": "user", "cwd": cwd, "timestamp": "2020-01-01T00:00:00Z",
            "message": {"role": "user", "content": text}}


def test_format_age():
    assert inventory.format_age(5) == "방금"
    assert inventory.format_age(605) == "10분 전"
    assert inventory.format_age(7200) == "2시간 전"
    assert inventory.format_age(86400 * 3 + 5) == "3일 전"


def test_live_ended_dedup_removes_both_copies(tmp_path):
    make(tmp_path, "C--dev-paper-search", SID_A, [user()])
    make(tmp_path, "C--dev-process-game", SID_A, [user()])
    make(tmp_path, "C--dev-paper-search", SID_B, [user()])
    rows, fails = inventory.list_ended(PROJECTS, {SID_A}, str(tmp_path), dev_root=DEV)
    assert fails == 0 and [r.session_id for r in rows] == [SID_B]


def test_duplicate_session_id_two_rows_newest_keeps_resume(tmp_path):
    older = make(tmp_path, "C--dev-paper-search", SID_A, [user()])
    newer = make(tmp_path, "C--dev-process-game", SID_A,
                 [user(cwd=r"C:\dev\process-game")])
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert len(rows) == 2
    by_slug = {r.slug: r for r in rows}
    assert by_slug["C--dev-process-game"].duplicate_of_newer is False
    assert by_slug["C--dev-paper-search"].duplicate_of_newer is True
    assert by_slug["C--dev-process-game"].resume_dir == r"C:\dev\process-game"
    assert by_slug["C--dev-paper-search"].resume_dir is None   # 중복 줄은 [재개] 자체가 없다
    assert by_slug["C--dev-paper-search"].project == "paper-search"


@pytest.mark.skipif(not config.IS_WIN, reason="Windows 경로 전제")
def test_attribution_is_by_folder_slug_not_internal_cwd(tmp_path):
    # 첫 cwd가 엉뚱한 프로젝트여도 귀속은 파일이 놓인 폴더 슬러그를 따른다.
    make(tmp_path, "C--dev-process-game", SID_A, [user(cwd=r"C:\dev\paper-search")])
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert rows[0].project == "process-game"
    assert rows[0].resume_dir == r"C:\dev\process-game"   # cwd 후보가 안 맞으면 프로젝트 경로


def test_stub_true_for_small_file_with_no_user_messages(tmp_path):
    make(tmp_path, "C--dev-paper-search", SID_A,
         [{"type": "system", "i": i} for i in range(12)])
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert rows[0].is_stub is True


def test_stub_size_guard_large_file_is_never_scanned(tmp_path):
    p = make(tmp_path, "C--dev-paper-search", SID_A,
             [{"type": "system", "i": 0}], pad_to=70 * 1024)
    assert os.path.getsize(p) >= config.STUB_MAX_BYTES
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert rows[0].is_stub is False          # user 0개여도 전수 스캔에 진입하지 않는다


def test_stub_line_guard(tmp_path):
    make(tmp_path, "C--dev-paper-search", SID_A,
         [{"type": "system", "i": i} for i in range(config.STUB_MAX_LINES + 5)])
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert rows[0].is_stub is False          # 줄 수 상한 초과 → 판정하지 않음


def test_title_level1_ai_title(tmp_path):
    make(tmp_path, "C--dev-paper-search", SID_A,
         [user(), {"type": "ai-title", "aiTitle": "슬러그 모호성 조사", "sessionId": SID_A}])
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert rows[0].title == "슬러그 모호성 조사"      # 나이는 화면이 붙인다(뷰키 밖)


def test_title_level2_first_user_message_truncated(tmp_path):
    long = "가" * 200
    make(tmp_path, "C--dev-paper-search", SID_A, [user(long)])
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert rows[0].title == "가" * config.NAME_FALLBACK_CHARS


def test_title_level3_session_id_prefix(tmp_path):
    make(tmp_path, "C--dev-paper-search", SID_A, [{"type": "cost-state"}])
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert rows[0].title == SID_A[:8]


def test_cache_avoids_rereading_unchanged_files(tmp_path):
    p = make(tmp_path, "C--dev-paper-search", SID_A, [user()])
    cache = {}
    inventory.list_ended(PROJECTS, set(), str(tmp_path), cache=cache, dev_root=DEV)
    assert len(cache) == 1
    cache[p] = (cache[p][0], {"title": "CACHED", "cwds": [], "is_stub": False})
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), cache=cache, dev_root=DEV)
    assert rows[0].title == "CACHED"


def test_unknown_slug_has_no_project(tmp_path):
    make(tmp_path, "C--tmp-elsewhere", SID_A, [user(cwd=r"C:\tmp\elsewhere")])
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert rows[0].project is None and rows[0].resume_dir == r"C:\tmp\elsewhere"


def test_root_slug_maps_to_root_key(tmp_path):
    make(tmp_path, "C--dev", SID_A, [user(cwd=DEV)])
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert rows[0].project == paths.ROOT_KEY and rows[0].resume_dir == DEV


def test_subfolder_only_glob_ignores_nested_attachments(tmp_path):
    make(tmp_path, "C--dev-paper-search", SID_A, [user()])
    nested = tmp_path / "C--dev-paper-search" / "sub"
    nested.mkdir()
    (nested / f"{SID_B}.jsonl").write_bytes(b'{"type":"x"}\n')
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert [r.session_id for r in rows] == [SID_A]


def _cont(target):
    return {"type": "continued-in", "continuedInSessionId": target, "timestamp": "2020-01-02T00:00:00Z"}


def test_record_continued_in_another_is_hidden(tmp_path):
    """백그라운드로 넘어간 대화: 원본(SID_A)은 숨기고 이어받은 쪽(SID_B)만 남긴다."""
    make(tmp_path, "C--dev-paper-search", SID_A, [user(), _cont(SID_B), {"type": "cost-state"}])
    make(tmp_path, "C--dev-paper-search", SID_B, [user()])
    rows, fails = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert [r.session_id for r in rows] == [SID_B] and fails == 0


def test_original_reappears_when_the_continuation_is_gone(tmp_path):
    make(tmp_path, "C--dev-paper-search", SID_A, [user(), _cont(SID_B)])
    rows, _ = inventory.list_ended(PROJECTS, set(), str(tmp_path), dev_root=DEV)
    assert [r.session_id for r in rows] == [SID_A]


def test_original_hidden_while_the_continuation_is_live(tmp_path):
    make(tmp_path, "C--dev-paper-search", SID_A, [user(), _cont(SID_B)])
    make(tmp_path, "C--dev-paper-search", SID_B, [user()])
    rows, _ = inventory.list_ended(PROJECTS, {SID_B}, str(tmp_path), dev_root=DEV)
    assert rows == []
