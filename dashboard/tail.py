"""역파서: 큰 .jsonl의 꼬리 창만 읽어 마지막 *메시지* 레코드를 찾는다.

파일 mtime은 상태 판정에 쓰지 않는다 — 첨부·system 레코드가 mtime을 밀기 때문이다.
판정에 쓰는 시계는 레코드 자신의 `timestamp`뿐이다. 실측 0.46 ms/read(크기 무관).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import config


def parse_ts(iso: str | None) -> float | None:
    """ISO-8601(끝의 `Z` 포함) → unix 초. 파싱 실패는 None.

    오프셋이 없는 순수 시각은 **UTC로 본다** — 로컬 시간대로 읽으면 거부권 B의
    `ts > su` 비교가 시차만큼 통째로 어긋난다. 극단값은 timestamp()가
    OSError/OverflowError를 내므로 함께 잡고, 에포크 이전 값도 미지로 돌린다.
    """
    if not isinstance(iso, str) or not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ts = dt.timestamp()
    except (ValueError, TypeError, OSError, OverflowError):
        return None
    return ts if ts >= 0 else None   # 1970 이전은 실제 기록 시각일 수 없다(연도 1 등)


def iter_tail_records(path: str, win: int = config.TAIL_WINDOW_BYTES):
    """꼬리 창의 레코드를 최신 → 과거 순으로 내놓는다."""
    size = os.path.getsize(path)
    start = max(0, size - win)
    with open(path, "rb") as fh:
        fh.seek(start)
        parts = fh.read().split(b"\n")
    if start > 0:
        parts = parts[1:]          # 창 경계에서 잘린 첫 조각은 버린다
    for raw in reversed(parts):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            continue               # 잘린 UTF-8·부분 JSON은 조용히 건너뛴다
        if isinstance(rec, dict):
            yield rec


def iter_head_records(path: str, max_lines: int = config.CWD_SCAN_LINES):
    """앞에서 `max_lines`줄만 읽어 레코드를 내놓는다(첫 cwd·첫 user 메시지용)."""
    with open(path, "rb") as fh:
        for i, raw in enumerate(fh):
            if i >= max_lines:
                break
            try:
                rec = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec


def read_last_message(path: str) -> dict | None:
    """마지막 `message.role`을 가진 레코드. 창 안에 없으면 1회 확장, 그래도 없으면 HOLD(None).

    85 MB 파일의 마지막 줄은 보통 `cost-state`라 뒤에서부터 걸어 올라가야 한다.
    """
    try:
        size = os.path.getsize(path)
        for win in (config.TAIL_WINDOW_BYTES, config.TAIL_WINDOW_MAX_BYTES):
            for rec in iter_tail_records(path, win):
                msg = rec.get("message")
                if isinstance(msg, dict) and "role" in msg:
                    return {"role": msg.get("role"),
                            "stop_reason": msg.get("stop_reason"),
                            "timestamp": parse_ts(rec.get("timestamp")),
                            "cwd": rec.get("cwd")}
            if size <= win:
                break              # 이미 파일 전체를 봤다 — 확장해도 결과가 같다
    except (OSError, UnicodeError):
        return None
    return None
