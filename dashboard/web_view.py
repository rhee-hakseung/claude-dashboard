"""웹 화면에 보낼 뷰(dict → JSON)를 조립하는 순수 함수. 파일·프로세스·창을 건드리지 않는다.

시간에 따라 변하는 글자(“3분 전”)는 넣지 않는다 — 시각(mtime)만 보내고 화면이 스스로 고친다.
그래야 값이 그대로인 동안 JSON이 같고, 화면은 다시 그리지 않는다.
"""
from __future__ import annotations

import config
import jobs
import model
import paths
import win_tabs
from model import WAITING, WORKING
from viewmodel import status_line, viewmodel


def live_label(s):
    """탭 제목(/rename → ai-title)을 그대로 보인다. 아직 기본값("Claude Code")인 새 세션만
    레지스트리 name(자동 이름)으로 대신하고, 둘 다 없으면 sessionId 앞 8자."""
    if s.tab_title and s.tab_title != win_tabs.DEFAULT_TITLE:
        return s.tab_title
    return s.name or s.tab_title or s.session_id[:8]


def project_title(p, aliases):
    """`(큰 글씨, 작은 글씨)`. 별칭이 있으면 별칭 + 폴더 이름, 없으면 폴더 이름만."""
    alias = aliases.get(p.name)
    plain = "루트" if p.is_root else p.name
    sub = config.DEV_ROOT if p.is_root else (p.name if alias else "")
    return alias or plain, sub


def _live(s, hl, favs):
    return {"kind": "live", "id": s.session_id, "title": live_label(s), "state": s.state,
            "label": config.LABELS.get(s.state, s.state), "shell": s.shell_tag,
            "disagree": s.sources_disagree, "hl": hl.is_on(s.session_id),
            "jumpable": s.jumpable or s.background, "host": "bg" if s.background else
            "desktop" if s.desktop else "orphan" if s.orphan else "window",
            "fav": any(i in favs for i in (s.session_id, *s.also_ids))}


def _ended(e, hl, favs, now):
    resuming = hl.is_resuming(e.session_id, now)
    return {"kind": "ended", "id": e.session_id, "path": e.path, "title": e.title,
            "mtime": e.mtime, "stub": e.is_stub, "dup": e.duplicate_of_newer,
            "resuming": resuming, "fav": e.session_id in favs and not e.duplicate_of_newer,
            "resumable": bool(not resuming and not e.is_stub and not e.duplicate_of_newer
                              and e.resume_dir)}


def normalize_favorites(favorites, live):
    """대화가 백그라운드 세션으로 넘어가면 id가 바뀐다(also_ids) — 즐겨찾기도 새 id로 따라간다."""
    moved = {old: s.session_id for s in live for old in s.also_ids}
    return list(dict.fromkeys(moved.get(f, f) for f in favorites))


def build(snap, prefs, hl, stats, now, message="", msg_seq=0):
    favs = set(prefs.favorites)
    groups = viewmodel(snap)
    by = {g[0].name: g for g in groups}
    ordered = [by[p.name] for p in model.order_projects([g[0] for g in groups], prefs.order)]
    projects, index = [], {}
    for p, lives, ends, js in ordered:
        title, sub = project_title(p, prefs.aliases)
        lv = [_live(s, hl, favs) for s in lives]
        en = [_ended(e, hl, favs, now) for e in ends]
        for item in lv + en:
            if item["fav"]:
                index.setdefault(item["id"], dict(item, project=title, project_key=p.name))
        projects.append({
            "name": p.name, "title": title, "sub": sub, "root": p.is_root, "path": p.path,
            "alias": prefs.aliases.get(p.name, ""), "folded": p.name in prefs.folded,
            "lit": any(i["hl"] for i in lv), "last_activity": p.last_activity,
            "live": lv, "ended": en, "jobs": [jobs.display(j) for j in js],
            "stats": stats.get(p.name)})
    live_all = [i for p in projects for i in p["live"]]
    stale = now - snap.collected_at > config.STALE_SNAPSHOT_SEC
    return {
        "projects": projects,
        "favorites": [index[f] for f in prefs.favorites if f in index],
        "summary": {"working": sum(1 for i in live_all if i["state"] == WORKING),
                    "waiting": sum(1 for i in live_all if i["state"] == WAITING),
                    "attention": sum(1 for i in live_all if i["hl"]),
                    "ended": sum(1 for p in projects for i in p["ended"] if not i["stub"]),
                    "projects": sum(1 for p in projects if p["name"] != paths.ROOT_KEY)},
        "status": status_line(snap, "", stale), "message": message, "msg_seq": msg_seq,
        "theme": prefs.theme, "root": config.DEV_ROOT,
        "labels": {"shell": config.SHELL_LABEL, "files": config.FILES_LABEL}}
