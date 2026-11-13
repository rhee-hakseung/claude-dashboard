import pytest

import config
import paths
from paths import ROOT_KEY

pytestmark = pytest.mark.skipif(not config.IS_WIN, reason="Windows 경로 전제 — 맥·리눅스는 test_posix.py")

DEV = r"C:\dev"
PROJECTS = ["paper-search", "process-game", "process", "potts-annealer"]


def test_slug_is_ambiguous_by_design():
    # 같은 슬러그가 서로 다른 두 경로에서 나온다 → 디코딩은 불가능하다.
    assert paths.slug(r"C:\dev\process-game") == paths.slug(r"C:\dev\process\game") == "C--dev-process-game"


# ── attribute_cwd 6케이스 ────────────────────────────────────────────────────
def test_attr_cwd_root():
    assert paths.attribute_cwd(r"C:\dev", DEV) == ROOT_KEY


def test_attr_cwd_root_trailing_and_slash():
    assert paths.attribute_cwd("C:/dev/", DEV) == ROOT_KEY


def test_attr_cwd_project():
    assert paths.attribute_cwd(r"C:\dev\paper-search", DEV) == "paper-search"


def test_attr_cwd_subfolder():
    assert paths.attribute_cwd(r"C:\dev\process-game\game\sub", DEV) == "process-game"


def test_attr_cwd_case_insensitive_and_forward_slash():
    assert paths.attribute_cwd("c:/DEV/Paper-Search/x", DEV) == "Paper-Search"


def test_attr_cwd_outside():
    assert paths.attribute_cwd(r"C:\other\thing", DEV) is None
    assert paths.attribute_cwd(r"C:\development\x", DEV) is None
    assert paths.attribute_cwd("", DEV) is None


# ── attribute_slug ───────────────────────────────────────────────────────────
def test_attr_slug_exact():
    assert paths.attribute_slug("C--dev-paper-search", PROJECTS, DEV) == "paper-search"


def test_attr_slug_root():
    assert paths.attribute_slug("C--dev", PROJECTS, DEV) == ROOT_KEY


def test_attr_slug_longest_prefix_wins():
    # C--dev-process-game-game 은 "process"(접두)와 "process-game"(접두) 둘 다 맞지만
    # 가장 긴 것이 이긴다.
    assert paths.attribute_slug("C--dev-process-game-game", PROJECTS, DEV) == "process-game"


def test_attr_slug_exact_beats_prefix():
    # C--dev-process-game 은 "process-game" 완전 일치이자 "process" 접두 일치다.
    assert paths.attribute_slug("C--dev-process-game", PROJECTS, DEV) == "process-game"


def test_attr_slug_unknown():
    assert paths.attribute_slug("C--tmp-somewhere", PROJECTS, DEV) is None


# ── resume_dir (계획 Step 2 규칙 ②) ──────────────────────────────────────────
def test_resume_dir_uses_first_cwd_whose_slug_matches_folder():
    got = paths.resume_dir("C--dev-process-game",
                           [r"C:\dev\paper-search", r"C:\dev\process-game"],
                           r"C:\dev\process-game")
    assert got == r"C:\dev\process-game"


def test_resume_dir_falls_back_to_project_dir():
    assert paths.resume_dir("C--dev-paper-search", [r"C:\tmp"], r"C:\dev\paper-search") \
        == r"C:\dev\paper-search"


def test_resume_dir_none_when_nothing_matches():
    assert paths.resume_dir("C--dev-paper-search", [r"C:\tmp"], r"C:\dev\process-game") is None
    assert paths.resume_dir("C--dev-x", [], None) is None


def test_resume_dir_finds_a_project_moved_into_a_subfolder(tmp_path):
    base = tmp_path / "spi"
    (base / "project" / "process-game").mkdir(parents=True)
    (base / "project" / "other").mkdir()
    fs = paths.slug(str(base / "project" / "process-game"))
    got = paths.resume_dir(fs, [r"C:\dev\process-game"], str(base))
    assert got == str(base / "project" / "process-game")


def test_resume_dir_nested_search_gives_none_when_no_folder_matches(tmp_path):
    (tmp_path / "project").mkdir()
    fs = paths.slug(str(tmp_path / "project" / "gone"))
    assert paths.resume_dir(fs, [], str(tmp_path)) is None
