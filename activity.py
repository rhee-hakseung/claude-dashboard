"""프로젝트별 '최근 N일 활동' 막대: transcript 레코드의 timestamp **날짜만** 센다.

본문은 읽지 않는다 — 바이트에서 `"timestamp":"YYYY-MM-DDTHH` 꼴만 정규식으로 집는다(SI: 대화
내용 비공개). 파일은 뒤에서부터 덩어리로 읽고 창(cutoff)보다 오래된 날짜가 나오면 멈춘다 —
몇 달짜리 90 MB 기록도 최근 부분만 읽는다. 커진 파일은 늘어난 꼬리만 더 읽는다(캐시).
결과는 메모리에만 둔다(디스크에 쓰지 않는다).
"""
from __future__ import annotations

import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

CHUNK = 1 << 20
_PAT = re.compile(rb'"timestamp":"(\d{4})-(\d\d)-(\d\d)T(\d\d)')
_local: dict[bytes, date] = {}


def _day(m) -> date:
    """UTC 시각(시 단위) → 로컬 날짜. 같은 시각 문자열은 한 번만 변환한다."""
    key = m.group(0)
    d = _local.get(key)
    if d is None:
        y, mo, dd, hh = (int(g) for g in m.groups())
        d = _local[key] = datetime(y, mo, dd, hh, tzinfo=timezone.utc).astimezone().date()
        if len(_local) > 5000:
            _local.clear()
    return d


def _count(path: str, start: int, end: int, cutoff: date) -> Counter:
    """[start, end) 바이트를 뒤에서부터 읽어 날짜별 레코드 수를 센다. cutoff 이전이 나오면 멈춘다."""
    out: Counter = Counter()
    with open(path, "rb") as fh:
        pos = end
        while pos > start:
            lo = max(start, pos - CHUNK)
            fh.seek(lo)
            days = [_day(m) for m in _PAT.finditer(fh.read(pos - lo))]
            out.update(d for d in days if d >= cutoff)
            if days and min(days) < cutoff:
                break
            pos = lo
    return out


def day_counts(path: str, cache: dict, cutoff: date) -> Counter:
    """파일 하나의 날짜별 레코드 수. `cache[path] = (size, Counter)` — 커졌으면 늘어난 만큼만 읽는다."""
    try:
        size = os.stat(path).st_size
    except OSError:
        cache.pop(path, None)
        return Counter()
    hit = cache.get(path)
    if hit and hit[0] == size:
        return hit[1]
    try:
        if hit and hit[0] < size:
            counts = hit[1] + _count(path, hit[0], size, cutoff)
        else:
            counts = _count(path, 0, size, cutoff)
    except OSError:
        return hit[1] if hit else Counter()
    cache[path] = (size, counts)
    return counts


def histogram(paths_by_project: dict, cache: dict, today: date, days: int = 14) -> dict:
    """`{프로젝트: [가장 오래된 날 … 오늘]}`(길이 `days`). 이번에 안 본 경로는 캐시에서 버린다."""
    cutoff = today - timedelta(days=days - 1)
    seen, out = set(), {}
    for name, paths in paths_by_project.items():
        total: Counter = Counter()
        for p in paths:
            seen.add(p)
            total.update(day_counts(p, cache, cutoff))
        out[name] = [total.get(cutoff + timedelta(days=i), 0) for i in range(days)]
    for gone in [k for k in cache if k not in seen]:
        del cache[gone]
    return out
