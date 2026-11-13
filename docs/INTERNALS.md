# 내부 동작 노트

개발하면서 적어 둔 설계·실측 기록이다. 설치와 사용법은 [README](../README.md)를 본다.
경로 예시의 `C:\dev\dev-dashboard`는 개발 PC의 설치 위치다 — 받은 폴더 위치로 바꿔 읽는다.

프로젝트 폴더(Windows 기본 `C:\dev`, macOS 기본 `~/dev`)의 프로젝트와 각 프로젝트의 Claude Code 세션을
**관찰만** 한다. 세션을 소유하지 않는다 — 어떤 프로세스도 종료시키지 않고, `~/.claude` 아래는 읽기 전용이다
(유일한 예외는 사용자가 [휴지통]을 누른 기록 파일 1개).

## Windows와 macOS의 차이

| | Windows | macOS |
|---|---|---|
| 창 | WebView2 (Windows 11 기본 포함) | WKWebView (pyobjc, pip가 함께 설치) |
| [새 claude]·[재개]·셸 버튼 | 열려 있는 Windows Terminal 창에 새 탭(열린 창이 없으면 새 창, Windows Terminal이 없으면 PowerShell 창) — 버튼 이름 **PowerShell** | Terminal 새 창 — 버튼 이름 **터미널**. iTerm2를 쓰려면 `state.json`에 `"terminal": "iTerm2"` |
| 폴더 버튼 | **탐색기** | **Finder** |
| [점프] | 호스트 창을 찾아 앞으로 + UI Automation으로 탭 고르기 | claude의 tty를 Terminal·iTerm2 탭과 대조해 그 탭을 앞으로(AppleScript). 처음 한 번 "Terminal 제어 허용"을 묻는다 → 시스템 설정 › 개인정보 보호 및 보안 › 자동화 |
| [점프]가 안 되는 세션 | — | VS Code·Ghostty·Warp 등 다른 터미널, tmux 안의 세션(버튼이 꺼진다) |
| 창을 닫았는데 프로세스만 남은 세션 | "창 닫힘" 표시 + [이어 열기] — 새 탭에서 `claude --resume`으로 같은 대화를 연다. 남은 프로세스는 건드리지 않는다 | 같음 |
| 휴지통 | 휴지통 | 휴지통(Trash) |

macOS 지원은 Windows PC에서 작성했고 리눅스(WSL)에서 테스트·설치 스크립트·수집 루프까지 확인했다.
실제 Mac에서의 창·AppleScript 동작은 아직 확인하지 못했다 — 처음 쓸 때 [점프]·[새 claude]를 한 번씩 눌러 볼 것.
macOS에서 Claude Code 레지스트리의 `procStart` 형식을 알 수 없어, 해석이 안 되면 pid 생존만으로 살아 있는 세션을 판정한다.

## 화면 (2026-11-12 개편: 웹 화면)

화면은 `web\`의 HTML/CSS/JS이고, 전용 창(pywebview = Windows의 WebView2)에 띄운다. 브라우저도 서버도
쓰지 않는다 — 화면(JS)이 0.3초마다 `Api.view(rev)`로 물어 가고, 버튼은 `Api`의 메서드를 직접 부른다.

- **요약 타일**(맨 위): 나를 기다림 / 작업 중 / 끝난 세션 / 프로젝트 수. 누르면 그 상태의 세션만 본다(다시 누르면 해제).
- **검색**(`Ctrl+K` 또는 `/`): 세션 이름·프로젝트 이름. 맞는 줄만 남고 끝난 세션도 전부 펼쳐진다. `Esc`로 지운다.
- **즐겨찾기**: 세션 줄을 즐겨찾기 칸으로 끌어다 놓거나 줄의 ☆를 누른다. 칸 안에서 끌면 순서가 바뀐다.
  즐겨찾기 칸이 화면 밖으로 밀려나 있으면 끄는 동안 맨 위에 "여기에 놓으면 즐겨찾기에 추가됩니다" 띠가 뜬다
  (창이 작으면 세션 줄과 즐겨찾기 칸이 한 화면에 안 들어와 놓을 곳이 없었다 — 2026-11-12).
  `state.json`의 `"favorites"`(sessionId 목록)에 저장한다. 대화가 백그라운드 세션으로 넘어가 id가 바뀌면 따라간다.
- **프로젝트 카드**: 손잡이(⋮⋮)를 끌어 순서 변경, 연필(또는 이름 더블클릭)로 표시 이름 변경, ⌄로 접기(`"folded"`에 저장).
  끝난 세션은 최근 3개만 보이고 "N개 더 보기"로 펼친다.
- **프로젝트 현황**(카드 둘째 줄): 마지막 활동, 세션 수, 폴더 용량(30분마다), git 브랜치와 커밋 안 한 변경 수(1분마다,
  `git --no-optional-locks status`), 최근 14일 활동 막대(transcript의 timestamp **날짜만** 센다 — 본문은 읽지 않는다).
- **테마**: 오른쪽 위 버튼으로 밝게/어둡게(`"theme"`에 저장, 없으면 Windows 설정을 따른다).
- 창 자리는 닫을 때 `"window"`(실제 픽셀)로 저장한다. 최소화·최대화 상태에서는 저장하지 않는다.

예전 tkinter 화면은 예비로 남아 있다: `pythonw.exe -B app.py --classic`.
화면을 창 없이 확인하려면 뷰 JSON을 `window.MOCK_VIEW = {...};`로 저장한 js 파일을 만들어
`web\index.html?mock=<그 파일의 file:// 주소>`를 Edge 헤드리스(`--headless=new --screenshot=…`)로 찍는다.

## 실행

macOS: `Claude dashboard` 앱(또는 `.venv/bin/python app.py`). 아래는 Windows 이야기다.

**바탕화면의 `Claude dashboard` 아이콘을 더블클릭**한다(창 제목도 `Claude dashboard`). 바로가기 내용:
대상 `C:\dev\dev-dashboard\.venv\Scripts\pythonw.exe`, 인수 `-B "C:\dev\dev-dashboard\app.py"`,
아이콘 `dashboard.ico`. (`-B` = `__pycache__`를 만들지 않음, `pythonw` = 콘솔 창 없음.)
두 번 누르면 창이 두 개 뜬다 — 이미 떠 있으면 작업 표시줄에서 찾을 것.

### 다른 PC에 설치 (zip으로 — GitHub를 쓸 수 없을 때)

1. 이 PC에서 `build-zip.ps1`을 실행 → `dist\claude-dashboard-<날짜>.zip`(≈100 KB; `.venv`·캐시 제외).
2. 새 PC에서 zip을 원하는 곳에 푼다(예: `C:\dev` 또는 `%LOCALAPPDATA%\Programs`). 안에 `dev-dashboard` 폴더 하나.
3. 그 폴더의 **`install.cmd` 더블클릭**. 하는 일:
   - Python 3.10+ 찾기(없으면 `winget`으로 3.13 설치할지 묻는다) → `.venv` 생성 → `requirements.txt` 설치
   - **프로젝트 폴더를 묻는다**(기본 `C:\dev`) → `state.json`의 `"dev_root"`에 저장
   - 바탕화면 `Claude dashboard` 아이콘 생성(작업 표시줄 아이콘 id 포함)
4. 다시 실행해도 안전하다 — 프로젝트 폴더를 바꿀 때도 `install.cmd`를 다시 누르면 된다.

프로젝트 폴더는 **환경 변수 `DEV_DASHBOARD_ROOT` → `state.json`의 `"dev_root"` → `C:\dev`** 순서로 정한다.
대시보드 자기 폴더는 어디에 풀었든 그 위치(`config.OWN_DIR`)이며 프로젝트 목록에서 숨긴다.
새 PC에도 Claude Code와 Windows Terminal이 있어야 한다.

PowerShell에서 실행하려면:

```powershell
C:\dev\dev-dashboard\run-dashboard.ps1
```

`.venv`가 없으면 먼저 만든다:

```powershell
C:\dev\dev-dashboard\install.cmd          # 또는 수동으로:
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv C:\dev\dev-dashboard\.venv
& "C:\dev\dev-dashboard\.venv\Scripts\pip.exe" install -r C:\dev\dev-dashboard\requirements.txt pytest
```

의존성: `psutil`(프로세스), `send2trash`(휴지통), `comtypes`(Windows만 — UI Automation, [점프]의 탭 고르기),
`pywebview`(새 화면의 창 — Windows는 WebView2, macOS는 WKWebView), `pytest`(테스트). `comtypes`가 없어도 앱은 그대로 돈다 — [점프]가 창만 올리고 상태줄로 알린다.

**PATH의 `python`을 쓰지 말 것.** `%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe`는 Microsoft
Store 별칭 스텁이라 "Python was not found"로 조용히 실패한다. 런처·바로가기 모두
`.venv\Scripts\pythonw.exe` **전체 경로**를 쓴다. 런처가 `PYTHONDONTWRITEBYTECODE=1`을 설정하므로
실행해도 프로젝트 폴더에 `__pycache__`가 생기지 않는다.

테스트: `& "C:\dev\dev-dashboard\.venv\Scripts\python.exe" -m pytest C:\dev\dev-dashboard\tests -q`
(macOS: `.venv/bin/python -m pip install pytest && .venv/bin/python -m pytest tests -q` — Windows 경로를 전제한
테스트는 스스로 건너뛰고, 맥 쪽은 `tests/test_posix.py`가 본다.)

## 파일

| 파일 | 하는 일 |
|---|---|
| `config.py` | 모든 상수 — 경로, 폴링 주기, 판정 임계, 화면 문구 |
| `paths.py` | 경로 ↔ 슬러그 인코딩, 프로젝트 귀속, [재개] 폴더 결정 |
| `model.py` | dataclass(세션/프로젝트/작업/스냅샷), 프로젝트 순서 `order_projects`(순수) |
| `highlight.py` | 강조 상태기계(FSM) |
| `collect_fs.py` | `C:\dev` scandir, 라이브 레지스트리 읽기 + stale 필터, transcript 해소 |
| `tail.py` | 큰 `.jsonl`의 꼬리 창만 읽는 역파서 |
| `status.py` | D1 상태 판정 규칙 표(레지스트리 + 꼬리 거부권) |
| `inventory.py` | 끝난 기록 열거 — 동일성, 귀속, stub 판정, 이름 3단 fallback |
| `jobs.py` | 작업 모니터 — 프로세스 분류와 '작업'만 추리기 |
| `term.py` | 운영체제별 창 다루기의 단일 창구 — [점프] 가능 여부·[점프]·사후 확인·창 자리 검사 |
| `mac_term.py` | macOS — Terminal·iTerm2 새 창 열기, tty로 탭 찾아 [점프], 모니터 사각형 |
| `win_window.py` | Windows — 대시보드 창 자리 복원·저장, 아이콘, 작업 표시줄 id |
| `win_find.py` | pid → 호스트 창 hwnd 해소, 모니터 사각형 |
| `win_focus.py` | [점프]의 포그라운드 전환과 200 ms 사후 확인 |
| `win_tabs.py` | [점프]의 탭 고르기 — UI Automation으로 탭 제목을 대조해 Select |
| `launch.py` | [재개] / [새 claude] / [PowerShell] / [탐색기] 런처 |
| `trash.py` | [휴지통] — 3중 가드 뒤 send2trash |
| `workers.py` | 수집 스레드 2개(fast 0.5 s / slow 데드라인 루프)와 공유 스냅샷 |
| `live.py` | 라이브 세션 조립 — 레지스트리 → 꼬리 캐시 → D1 판정 → [점프] 가능 판정 |
| `ui_shell.py` | 창 껍데기 — 스크롤 Canvas, 상태줄, `state.json`(창 위치·별칭·순서) 읽기/병합 저장 |
| `ui_rows.py` | 라이브·끝남·작업 행의 배치와 나이 문자열 제자리 갱신 |
| `ui_project.py` | 프로젝트 머리 줄(끌기 손잡이 ≡·접기·이름·버튼, 기다림 빨간 점)과 이름(별칭) 더블클릭 제자리 편집 |
| `ui_order.py` | 프로젝트 순서 — 손잡이 끌어 옮기기(표시줄·자동 스크롤·Esc 취소), 놓는 즉시 `state.json`의 `"order"`에 저장 |
| `ui_actions.py` | 버튼 6종의 동작 — [점프]/[재개]/[새 claude]/[PowerShell]/[탐색기]/[휴지통] |
| `app.py` | 진입점 — 기본은 새 화면(`webapp.main`), `--classic`이면 예전 tk 화면(셸 + 워커 + 100 ms UI 틱) |
| `webapp.py` | 새 화면의 창 — 위치·크기 복원/저장, 아이콘, 닫기 |
| `web_hub.py` | 새 화면의 상태 — 수집 스레드 4개, 강조, 설정, 마지막 뷰(JSON)와 rev |
| `web_view.py` | 스냅샷 → 화면에 보낼 뷰(dict) 조립(순수) |
| `web_api.py` | 화면이 부르는 버튼 동작 — 점프/재개/휴지통/새 claude/순서/이름/접기/즐겨찾기/테마 |
| `viewmodel.py` | 프로젝트별 묶기·상태줄·강조 적용(순수, 두 화면 공용) |
| `prefs.py` | `state.json` 읽기/병합 저장과 설정 묶음(별칭·순서·접힘·즐겨찾기·테마) |
| `stats.py` | 프로젝트 현황 수집 스레드 — git 상태, 폴더 용량, 활동 막대 |
| `activity.py` | 활동 막대 계산 — transcript를 뒤에서부터 읽어 날짜별 레코드 수만 센다 |
| `web\index.html` `style.css` `icons.js` `render.js` `app.js` | 화면 — 뼈대 / 색·배치 / 아이콘 / 뷰→HTML / 갱신·버튼·끌어다 놓기 |
| `install.cmd` `install.ps1` / `install.sh` | 설치 — Windows / macOS(리눅스는 앱 묶음 없이) |

## 고치는 곳

- **새 화면의 모양을 바꾸려면** → `web\style.css`(색은 맨 위 토큰), **줄·카드 구성** → `web\render.js`,
  **버튼 동작** → `web_api.py`, **화면에 보낼 값** → `web_view.py`
- (예전 tk 화면) **버튼의 동작** → `ui_actions.py`, **배치** → `ui_rows.py`
- **프로젝트 순서 규칙을 바꾸려면** → `model.order_projects`(+ 끌기·저장은 `ui_order.py`)
- **폴링 주기·판정 임계·문구를 바꾸려면** → `config.py` 한 파일
- **상태 판정 규칙을 바꾸려면** → `status.py`(+ 꼬리 읽기는 `tail.py`)

## 이름 표시

- **라이브 세션 줄** = 탭 제목과 같다(기록의 최신 `custom-title` → 최신 `ai-title`). Claude Code의
  이름 바꾸기(`/rename`)가 1초 안에 반영된다. 아직 제목이 없는(`"Claude Code"`) 새 세션만
  레지스트리 `name`(`dev-2e` 같은 자동 이름)으로 대신한다.
- **끝난 기록 줄**도 최신 `custom-title`을 `ai-title`보다 먼저 쓴다 — 이름 바꾼 세션은 끝난 뒤에도
  그 이름을 유지한다.
- **프로젝트 별칭**: 프로젝트 이름을 더블클릭하면 그 자리에서 고친다(Enter 저장, Esc·다른 곳 클릭
  취소). 화면은 `별칭 (폴더 이름)`, 루트는 `별칭 (C:\dev)`. 비우거나 폴더 이름을 그대로 넣으면
  별칭이 지워진다. 저장은 Enter 즉시 `state.json`의 `"aliases"`에 한다. **순서는 별칭과 무관하다**
  (키는 언제나 폴더 이름). 편집 중에는 화면 재생성이 멈춘다.

## 프로젝트 순서

- **순서는 사용자가 끌어서 정한 순서로 고정** — 기다리는 세션은 빨간 점 ●으로만 알림(`나를 기다림`
  글자 오른쪽; 프로젝트를 **접어 두었을 때만** 이름 오른쪽에도 찍힌다 — 2026-09-22 사용자
  요청으로 노란 배경을 대체); 새 폴더는 최근 활동 순으로 뒤에 붙고(루트는
  그중 맨 뒤), 한 번 끌어 놓으면 그 순서까지 고정됨. 줄은 저절로 움직이지 않는다 — 누르려던
  버튼이 막 움직여 엉뚱한 것을 누르는 일을 막기 위해서다.
- 머리 줄 맨 왼쪽의 손잡이 **≡**(커서가 십자 화살표로 바뀜)를 잡고 끌면 파란 가로줄이 놓일 자리를
  보인다. 창 위·아래 끝으로 끌면 저절로 스크롤된다. 놓으면 **지금 보이는 전체 순서**를 곧바로
  `state.json`의 `"order"`(폴더 이름 목록, 루트는 `"."`)에 저장하고 다시 그린다. 끄는 도중 **Esc**
  = 취소, 제자리에 놓으면 저장하지 않는다. 끄는 동안에는 화면 재생성이 멈춘다. 지금 없는 폴더의
  이름은 목록에서 지우지 않고 맨 뒤에 남긴다. (2026-09-22 ▲▼ 버튼에서 끌기로 교체 — 사용자 요청.)
- **계획서와 다른 점(의도된 변경)**: 계획서의 원래 정렬은 상태 우선순위(기다림 → 작업 중 → …)였고
  "기다리는 프로젝트가 위로 올라온다"는 AC가 있었다. 이 AC는 **2026-09-22 사용자 결정으로
  대체되었다** — 상태는 순서에 관여하지 않고 빨간 점으로만 알린다.

## 상태 판정 요약 (D1)

위에서부터 처음 일치하는 행을 쓴다. **레지스트리가 1차 출처이고, 꼬리(transcript의 마지막
메시지)는 거부권만 가진다.**

| # | 조건 | 결과 |
|---|---|---|
| 1 | 레지스트리에 없음 / stale 필터 탈락 | **끝남** |
| 2 | (경고 A, 기본 꺼짐) busy ∧ 마지막이 `end_turn`이며 오래됨 | 작업 중 유지 + `?` |
| 3 | (거부권 B) busy 아님 ∧ 마지막 메시지 시각 > `statusUpdatedAt` + 5 s | **작업 중**으로 뒤집기 + `?` |
| 4 | `status == busy` | **작업 중** |
| 5 | 그 밖의 `status` | **나를 기다림** |
| 6 | 어느 행도 성립하지 않음(읽기 실패 등) | **HOLD** — 직전 상태를 그대로 유지 |

행 2·3은 연속 3틱 관측돼야 발동한다. 꼬리를 못 읽어도 행 4·5는 흔들리지 않는다(그래야 기록이
아직 없는 새 세션이 HOLD에 갇히지 않는다). `?`는 "상태 출처 불일치"라는 뜻이지 오류가 아니다.

## 관측된 어휘 (실측)

레지스트리 `<pid>.json`의 `status`:

| 값 | 화면 | 비고 |
|---|---|---|
| `busy` | 작업 중 | |
| `idle` | 나를 기다림 | 구버전에서 주로 관측 |
| `waiting` | 나를 기다림 | |
| `shell` | 나를 기다림 + `백그라운드 실행 중` 꼬리표 | 턴은 끝났고 백그라운드 셸 명령이 아직 도는 중 |

꼬리 레코드의 `stop_reason`: `tool_use`, `end_turn`, `stop_sequence`.

**아직 확인하지 못한 상황** — 값이 무엇으로 나오는지 미검증이며, 화면이 틀릴 수 있는 구간이다:
권한 대화상자가 떠 있는 동안 / 프롬프트를 한 번도 넣지 않은 새 세션 / 세션이 끝난 뒤에도
`<pid>.json`이 남아 있는 경우(→ stale 필터가 pid와 `procStart`로 걸러 '끝남'으로 본다).

## 끝난 기록 목록

- **'빈 기록'(stub)** = user 메시지가 0개인 기록. 회색으로 표시하고 [재개]를 만들지 않는다.
  판정은 **크기 < 64 KB 그리고 줄 수 ≤ 200**일 때만 전수 스캔해서 내린다. 그 밖은 무조건
  non-stub으로 본다 — 85 MB짜리 기록을 매 5초 전부 읽지 않기 위해서다. **자동 삭제는 없다.**
- **중복 sessionId 주의**: 같은 sessionId가 두 슬러그 폴더에 동시에 존재할 수 있다(실측 있음).
  두 줄 모두 표시하고, [재개]는 mtime이 최신인 줄에만 만든다(다른 줄에는 "다른 프로젝트에 같은
  기록 있음"). 한쪽이 라이브면 `trash.send`의 가드 2가 **다른 슬러그의 복사본 삭제도 함께
  막는다** — 보수적이며 의도된 동작이다.
- **기록 30일 자동 삭제**: Claude Code 자신이 오래된 transcript를 정리할 수 있다(기본 30일).
  목록에서 기록이 사라졌다면 그쪽일 가능성이 높다. **대시보드는 아무것도 지우지 않는다.**
  보관 기간을 늘리려면 Claude Code 설정을 사용자가 직접 바꿔야 하며, 대시보드는 그 파일을
  읽지도 쓰지도 않는다.

## 상태줄 읽는 법

- `수집 실패 n회` — 파일 읽기가 실패한 **누적** 횟수. **이것이 유일한 신호인 상황이 있다**:
  워커 스레드는 살아 있는데 모든 읽기가 실패하면 스냅샷 시각은 계속 갱신되므로
  "수집 중단"이 끝내 울리지 않는다. n이 계속 올라가면 화면 내용을 믿지 말 것.
- `상태 출처 불일치 n건` — 지금 `?`가 붙어 있는 라이브 세션의 수(D1 행 2·3). 누적이 아니다.
- `수집 중단 — 재시작 필요` — 스냅샷이 15초 넘게 갱신되지 않았다. 워커가 죽은 것이다.
  판정은 **두 워커 중 더 오래 침묵한 쪽**을 기준으로 한다 — 하나만 멈춰도 뜬다.
- 그 밖에 마지막 동작 결과가 뜬다: `창을 찾을 수 없음`, `창을 확신할 수 없음`,
  `휴지통으로 이동: …`, `아직 살아있는 세션의 기록입니다`,
  `방금 쓰인 기록이라 5초 뒤 다시 시도하세요`,
  `세션 목록을 확인할 수 없어 안전을 위해 지우지 않습니다`,
  `창은 올렸지만 같은 제목의 탭이 여러 개라 탭을 고르지 못함`, `창은 올렸지만 탭을 찾지 못함`,
  `탭 전환 불가(UIA) — 창만 올림`, `폴더가 없습니다: …`([탐색기]), `이름 저장 실패: …`.
  **확인 대화상자는 어디에도 없다.**

## 백그라운드로 넘어간 세션 (한 줄로 합침)

Claude Code는 창에서 쓰던 대화를 **백그라운드 세션**(레지스트리 `kind: "bg"`)으로 넘길 수 있다.
그러면 대화는 새 sessionId로 복사되어 그쪽 기록에서만 이어지고(원래 기록에는 `continued-in`
레코드가 남고 그 뒤로는 메시지가 없다), 원래 창은 그 세션을 보여 주는 화면이 된다. 레지스트리에는
둘 다 남는다 — 창 쪽 `parkedJobId` = 백그라운드 쪽 `jobId`(2026-10-14 실측).

- 두 항목을 **한 줄로 합친다**(`live._merge_parked`): 상태·제목·id는 백그라운드 쪽(실제 대화가 도는
  곳), [점프]는 창 쪽 pid로 그 창의 탭을 고른다. 창 쪽 원래 기록은 '끝남'/[재개]에 뜨지 않는다.
- 창을 닫아 백그라운드 세션만 남으면 [점프] 대신 **[열기]**(새 탭에서
  `claude attach <id 앞 8자>`)가 뜬다. "백그라운드" 꼬리표는 달지 않는다(사용자 요청 — 사용자에겐 같은 대화다).
- 세션이 끝난 뒤에도 원래 기록(`continued-in`이 든 쪽)은 '끝남' 목록에서 **숨긴다** — 이어받은 기록이
  그 대화의 최신본이고, 원본을 [재개]하면 넘어가기 전 시점으로 돌아간다. 이어받은 기록이 지워지면 원본이 다시 보인다. 세션을 멈추는 것은 사용자가 `claude stop <id>`로 직접 한다 —
  **이 세션이 지금 쓰는 대화일 수 있으니** 멈추기 전에 확인할 것.

## Claude 데스크톱 앱 세션, 같은 대화를 두 곳에서 연 경우

- 레지스트리의 `entrypoint`가 `claude-desktop`이면 Claude 데스크톱 앱 안의 세션이다. 앱 창은 트레이로
  숨어 있어 pid로 찾을 수 없으므로, [점프]는 PowerShell 새 탭에서 `claude --resume <id>`로 같은 대화를
  이어 연다. 앱 쪽 세션은 대시보드가 멈추지 않는다 — 앱에서 닫는다.
- 같은 sessionId가 두 프로세스에 동시에 나오면 한 줄로 합친다. [점프] 대상은 터미널 쪽이 앱 쪽보다
  먼저이고(그래야 [점프]가 또 새 탭을 열지 않는다), 그다음 가장 최근에 상태가 바뀐 쪽이다. 하나라도
  작업 중이면 '작업 중'이다.

## [점프] — 창 + 탭

세션의 호스트 창(Windows Terminal)을 pid에서 해소해 앞으로 가져온다. **한 창에 탭이 여러 개면
창만 올려서는 아무 일도 안 일어난 것처럼 보인다** — 엉뚱한 탭이 떠 있기 때문이다. 그래서 창을
올리기 **전에** UI Automation(`comtypes`)으로 그 창의 `TabItem`들을 열거해 제목이 맞는 탭을
고른다(실측: 열거 30 ms, `Select()` 25 ms).

- 숨은 `PseudoConsoleWindow`의 제목은 비어 있다 — **세션 ↔ 탭을 잇는 유일한 끈은 탭 제목**이다.
  레지스트리의 `name`은 탭 제목이 **아니다**(실측: `dev-2e` ↔ 탭 `PowerShell 세션 관리 도구`).
- 탭 제목 = `<상태 글리프> ` + T, 그리고 **T = 기록의 최신 `custom-title` → 없으면 최신
  `ai-title` → 그래도 없으면 `"Claude Code"`**(갓 만든 세션). 두 종류 모두 한 기록 안에 여러 번
  나오므로 최신 것이 이긴다. 계산은 수집 워커가 꼬리 캐시에 얹어서 한다(추가 비용 0).
- 비교는 앞머리 글리프 토큰 하나를 뗀 뒤 **정확히 일치**할 때만 맞는 것으로 본다.
- **같은 제목의 탭이 둘 이상이면 아무 탭도 고르지 않는다.** 창만 올리고 상태줄로 알린다 —
  조용히 엉뚱한 탭을 고르는 것이 더 나쁜 실패다. 탭을 못 찾았을 때·UIA를 못 쓸 때도 같다.
- 탭이 하나뿐인 창(그리고 고전 콘솔)에서는 할 일이 없으므로 그냥 창만 올린다.

## 작업 모니터 (`▶ 이름 경과`)

프로젝트 폴더에서 오래 도는 프로세스를 보여준다. 위에서부터 처음 맞는 규칙을 쓴다.

1. 자기 자신(대시보드) → 제외
2. 셸 계열(`powershell.exe`, `pwsh.exe`, `cmd.exe`, `conhost.exe`, `wt.exe`,
   `WindowsTerminal.exe`, `OpenConsole.exe`, `claude.exe`, `git.exe`, 그리고 WSL 다리 `wsl.exe`·`wslhost.exe`·`wslrelay.exe`
   — Claude의 Bash 도구가 `wsl -e bash -lc …`로 띄우는 것) → 제외
3. `exe`가 `~/.claude\`, `node_modules\`, `%APPDATA%\npm`, `%LOCALAPPDATA%\AnthropicClaude\`,
   `C:\Program Files\Git\usr\bin\`(Git Bash 유틸 grep/tail/sleep — Claude 도구가 남긴 프로세스)
   아래 → 도우미로 제외. 목록은 `config.HELPER_EXE_DIRS`.
4. `node.exe` ∧ 명령줄에 `mcp` / `--stdio` / `@modelcontextprotocol` / `language-server` /
   `.claude\plugins` → 도우미로 제외
4b. venv `python.exe`는 실제 인터프리터를 자식으로 한 번 더 띄우는 중계기다 — 부모와 명령줄이
   같은 자식은 중복으로 보고 한 줄만 남긴다
4c. `claude.exe`가 **직접** 띄운 프로세스(= MCP 서버, 예: `python -m paper_search.server`) →
   도우미로 제외. Claude가 명령 실행 도구로 띄운 실험은 셸을 거치므로 계속 보인다
5. `cwd`가 `C:\dev\<프로젝트>` 아래가 아니면 제외
6. 경과 < 60초 → 아직 '작업'이 아니다
7. 나머지 → **작업**. Claude가 띄운 `python.exe`도 여기 포함된다(일부러 숨기지 않는다)

## 안전 불변식

- **프로세스 종료 0건.** 어떤 프로세스에도 신호를 보내지 않는다. 소스 전체에 종료 API 호출이
  없음을 정적 검사로 확인한다.
- **`~/.claude`는 읽기 전용**이고 예외는 딱 하나 — 사용자가 [휴지통]을 누른 `.jsonl` **1개**를
  `send2trash`로 옮기는 것. `trash.send`가 스스로 3중 가드를 강제한다: ① `projects\<슬러그>\
  <이름>.jsonl` 정확한 깊이 ② 호출 시점에 레지스트리를 다시 읽어 라이브가 아님을 확인
  ③ mtime 나이 ≥ 5초. 가드 ②는 fail-closed다 — 레지스트리 파일을 하나라도 못 읽으면 거절한다.
  첨부 폴더 등 부속 데이터는 건드리지 않는다.
- **`*.key`는 글롭에서 원천 배제**한다(`*.json`만 읽는다).
- **Claude Code 설정 파일은 읽지도 쓰지도 않는다.**
- **hwnd를 캐시하지 않는다.** 탭을 떼거나 합치면 호스트 창이 바뀌는데, 캐시된 hwnd는 실패하지
  않고 *엉뚱한 창을 성공적으로* 앞에 가져온다. 그래서 [점프]는 매번 pid에서 다시 해소하고,
  200 ms 뒤 사후 확인까지 한다. 탭도 같은 원칙이다 — `win_tabs`는 hwnd를 인자로만 받고,
  고르기 직전에 탭을 **다시 열거**한다(첫 순회의 인덱스를 믿지 않는다).
- **탭에는 고르기(Select) 외의 조작을 하지 않는다.** 탭을 닫거나 옮기거나 이름을 바꾸지 않고,
  키 입력도 보내지 않는다. 같은 제목이 둘 이상이면 아무것도 고르지 않는다.
- **런처는 `CLAUDECODE`/`CLAUDE_CODE_*`/`CLAUDE_PID`를 벗겨서** 새 셸을 띄운다 — 대시보드가
  Claude 세션 안에서 실행됐을 때 이 표식이 물려지면 새 claude가 자신을 자식 세션으로 오인해
  transcript 저장을 끄고 레지스트리에도 나타나지 않는다(실측).
- **쓰기는 전부 세 곳뿐**: `%LOCALAPPDATA%\dev-dashboard\state.json`(창 위치는 닫을 때, 프로젝트
  별칭은 Enter로 확정할 때 — 언제나 기존 내용을 읽어 합친 뒤 같은 폴더의 `state.json.tmp`에 쓰고
  `os.replace`로 바꿔 끼운다. 키는 `geometry`·`aliases`·`order`(끌어 놓을 때 즉시) 세 개),
  같은 폴더의 `comtypes_gen\`(UI Automation 래퍼 캐시 — comtypes 기본값이 `.venv` 안이라
  프로젝트 폴더 밖으로 돌렸다), 그리고 위의 휴지통 이동.
- **창을 항상 위로 올리지 않고**(`-topmost` 없음), 소리도 토스트도 내지 않는다. 강조는 빨간 점
  ●(`나를 기다림` 글자 오른쪽, 접힌 프로젝트는 이름 오른쪽)뿐이다 — 배경색도, 순서도 바뀌지 않는다.
- **대시보드를 닫아도 어떤 세션에도 영향이 없다.** 워커는 daemon 스레드다.
