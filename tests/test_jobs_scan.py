"""jobs.scan: 캐시 재사용·사라진 pid 축출·순회 중 예외 생존.
psutil.process_iter를 스텁으로 갈아 끼운다 — 실제 프로세스는 읽지도 건드리지도 않는다."""
import contextlib
import os

import psutil

import config
import jobs

NOW = 1_000_000.0
PROJECTS = ["myproj"]


class Stub:
    """jobs.scan이 쓰는 인터페이스만 흉내낸다: info / oneshot() / exe() / cmdline() / cwd()."""

    def __init__(self, pid, calls, raises=False, cwd=os.path.join(config.DEV_ROOT, "myproj")):
        self.info = {"pid": pid, "name": "python.exe", "create_time": NOW - 3600}
        self._calls, self._raises, self._cwd = calls, raises, cwd

    def oneshot(self):
        if self._raises:
            raise psutil.NoSuchProcess(self.info["pid"])
        return contextlib.nullcontext()

    def exe(self):
        return r"C:\Python313\python.exe"

    def cmdline(self):
        self._calls.append(self.info["pid"])
        return ["python.exe", "run.py"]

    def cwd(self):
        return self._cwd


def iter_of(*stubs):
    def process_iter(attrs=None):
        return iter(stubs)
    return process_iter


def test_scan_survives_nosuchprocess_midway(monkeypatch):
    calls = []
    monkeypatch.setattr(psutil, "process_iter",
                        iter_of(Stub(1, calls), Stub(2, calls, raises=True), Stub(3, calls)))
    out = jobs.scan({}, PROJECTS, now=NOW)
    assert sorted(j["pid"] for j in out) == [1, 3]
    assert calls == [1, 3]


def test_scan_reuses_cache_for_known_key(monkeypatch):
    calls = []
    monkeypatch.setattr(psutil, "process_iter", iter_of(Stub(1, calls)))
    cache = {}
    assert len(jobs.scan(cache, PROJECTS, now=NOW)) == 1
    assert calls == [1]
    monkeypatch.setattr(psutil, "process_iter", iter_of(Stub(1, calls)))
    assert len(jobs.scan(cache, PROJECTS, now=NOW)) == 1
    assert calls == [1]                      # 두 번째 스캔은 cmdline()을 다시 부르지 않는다


def test_scan_evicts_vanished_pids(monkeypatch):
    calls = []
    monkeypatch.setattr(psutil, "process_iter", iter_of(Stub(1, calls), Stub(2, calls)))
    cache = {}
    jobs.scan(cache, PROJECTS, now=NOW)
    assert len(cache) == 2
    monkeypatch.setattr(psutil, "process_iter", iter_of(Stub(1, calls)))
    jobs.scan(cache, PROJECTS, now=NOW)
    assert [k[0] for k in cache] == [1]


def test_scan_skips_processes_outside_dev_root(monkeypatch):
    calls = []
    monkeypatch.setattr(psutil, "process_iter",
                        iter_of(Stub(1, calls, cwd=r"C:\Users\USER\scratch")))
    assert jobs.scan({}, PROJECTS, now=NOW) == []
