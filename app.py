"""진입점. 모듈은 `dashboard/` 폴더에 있다 — 그 폴더를 임포트 경로에 넣고 화면(webapp)을 띄운다.

바로가기·설치 스크립트는 이 파일을 실행한다: `.venv\\Scripts\\pythonw.exe -B app.py`(맥은 `.venv/bin/python -B app.py`).
PATH의 `python`은 쓰지 않는다 — Windows에서는 Store 스텁일 수 있다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard"))


def main():
    import webapp          # 창 도구(pywebview)는 여기서만 불러온다
    return webapp.main()


if __name__ == "__main__":
    main()
