import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard"))
# 테스트 기대값은 C:\dev 기준이다 — 그 PC의 state.json "dev_root"와 무관하게 고정한다.
# 맥·리눅스에서는 Windows 경로를 전제한 모듈이 스스로 건너뛰고(pytestmark), 나머지는 /dev-root 기준으로 돈다.
os.environ["DEV_DASHBOARD_ROOT"] = r"C:\dev" if sys.platform == "win32" else "/dev-root"
