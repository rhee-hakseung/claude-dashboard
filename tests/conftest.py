import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 테스트 기대값은 C:\dev 기준이다 — 그 PC의 state.json "dev_root"와 무관하게 고정한다.
# 맥·리눅스에서는 Windows 경로를 전제한 모듈이 스스로 건너뛰고(pytestmark), 나머지는 /dev-root 기준으로 돈다.
os.environ["DEV_DASHBOARD_ROOT"] = r"C:\dev" if sys.platform == "win32" else "/dev-root"

# 예전 tk 화면(--classic) 테스트: tkinter가 없는 파이썬(예: Homebrew python에 python-tk 미설치)이면 건너뛴다.
collect_ignore = []
if importlib.util.find_spec("tkinter") is None:
    collect_ignore += ["test_aliases.py", "test_app.py", "test_order.py", "test_titles.py", "test_ui_shell.py"]
