# Claude dashboard

여러 프로젝트에서 동시에 돌리는 [Claude Code](https://claude.com/claude-code) 세션을 한 화면에서 보는 데스크톱 앱입니다.
어느 세션이 **작업 중**이고 어느 세션이 **나를 기다리는지** 바로 보이고, 버튼 하나로 그 터미널 탭으로 건너갑니다.

- Windows와 macOS에서 동작합니다.
- 세션을 **보기만** 합니다. 어떤 프로세스도 끝내지 않고, Claude Code의 설정이나 대화 내용을 바꾸지 않습니다.
- 서버나 계정이 필요 없습니다. 내 PC 안에서만 돌고 외부로 아무것도 보내지 않습니다.

## 무엇을 할 수 있나

| 기능 | 설명 |
|---|---|
| 세션 상태 | 프로젝트별로 세션을 **작업 중 / 나를 기다림 / 끝남**으로 보여 줍니다. 기다리는 세션은 빨간 점으로 표시합니다 |
| **점프** | 그 세션이 떠 있는 터미널 창과 탭을 앞으로 가져옵니다 |
| **재개** | 끝난 세션을 새 탭에서 `claude --resume`으로 다시 엽니다 |
| **새 claude** | 그 프로젝트 폴더에서 새 세션을 엽니다 |
| **PowerShell**(맥은 **터미널**) · **탐색기**(맥은 **Finder**) | 그 프로젝트 폴더에서 셸이나 폴더 창을 엽니다 |
| **휴지통** | 끝난 세션의 기록을 휴지통으로 보냅니다(복구 가능) |
| 검색 | `Ctrl+K` 또는 `/`로 세션 이름·프로젝트 이름을 찾습니다 |
| 즐겨찾기 | 세션 줄의 ☆를 누르거나 즐겨찾기 칸으로 끌어다 놓습니다 |
| 프로젝트 현황 | 마지막 활동, 폴더 용량, git 브랜치와 커밋 안 한 변경 수, 최근 14일 활동 |
| 작업 모니터 | 프로젝트 폴더에서 1분 넘게 돌고 있는 프로그램(학습, 빌드 등)을 보여 줍니다 |

프로젝트 카드는 끌어서 순서를 바꾸고, 이름을 더블클릭해 표시 이름을 바꾸고, 접어 둘 수 있습니다. 밝은 테마와 어두운 테마가 있습니다.

## 설치

먼저 필요한 것:

- **Claude Code** (`claude` 명령이 터미널에서 실행되어야 합니다)
- **Python 3.10 이상**
- **git**
- Windows는 **Windows Terminal** 권장 (Windows 11에는 기본으로 들어 있습니다)

대시보드는 **프로젝트 폴더 하나**(예: `C:\dev`, `~/dev`)를 정해 두고, 그 바로 아래 폴더들을 프로젝트로 봅니다. 설치할 때 이 폴더를 묻습니다.

### Windows

PowerShell에서:

```powershell
git clone https://github.com/rhee-hakseung/claude-dashboard.git C:\dev\claude-dashboard
C:\dev\claude-dashboard\install.cmd
```

설치가 끝나면 바탕화면에 **Claude dashboard** 아이콘이 생깁니다. 더블클릭해서 엽니다.
Python이 없으면 설치 스크립트가 `winget`으로 설치할지 묻습니다.

### macOS

터미널에서:

```bash
git clone https://github.com/rhee-hakseung/claude-dashboard.git ~/dev/claude-dashboard
cd ~/dev/claude-dashboard && ./install.sh
```

설치가 끝나면 `~/Applications/Claude dashboard.app`이 생깁니다. Spotlight에서 열거나 Dock에 끌어 둡니다.
Python이 없으면 먼저 `brew install python@3.13`으로 설치합니다.

> **macOS 지원은 아직 실제 Mac에서 확인하지 못했습니다.** Windows에서 만들고 리눅스에서 테스트와 설치 스크립트만 확인했습니다.
> 처음 쓸 때 [점프]와 [새 claude]를 한 번씩 눌러 보고, 안 되는 것이 있으면 Issue로 알려 주세요.

### 업데이트와 삭제

- **업데이트**: 받은 폴더에서 `git pull`을 한 뒤 설치 스크립트를 한 번 더 실행합니다. 다시 실행해도 안전합니다.
- **프로젝트 폴더 바꾸기**: 설치 스크립트를 다시 실행해 새 폴더를 입력합니다.
- **삭제**: 받은 폴더와 바탕화면 아이콘(맥은 앱)을 지웁니다. 설정 파일은 아래 위치에 따로 있습니다.

설정(창 위치, 표시 이름, 순서, 즐겨찾기, 테마)은 받은 폴더 밖에 저장되어 업데이트해도 유지됩니다.

| | 설정 위치 |
|---|---|
| Windows | `%LOCALAPPDATA%\dev-dashboard\state.json` |
| macOS | `~/Library/Application Support/dev-dashboard/state.json` |

## Windows와 macOS의 차이

| | Windows | macOS |
|---|---|---|
| 새 탭이 열리는 곳 | 열려 있는 Windows Terminal 창의 새 탭. 열린 창이 없으면 새 창 | Terminal 새 창. iTerm2를 쓰려면 `state.json`에 `"terminal": "iTerm2"`를 넣습니다 |
| [점프]가 되는 터미널 | Windows Terminal, PowerShell 콘솔 창 | Terminal, iTerm2 |
| 처음 한 번 묻는 권한 | 없음 | "Terminal 제어 허용"(시스템 설정 › 개인정보 보호 및 보안 › 자동화) |

## 알아 둘 점

- **[점프]가 꺼져 있는 세션**: VS Code 내장 터미널이나 tmux 안의 세션처럼 대시보드가 창을 찾지 못하는 경우입니다. 상태는 그대로 보입니다.
- **"창 닫힘" + [이어 열기]**: 터미널 창을 닫았는데 세션 프로세스만 남은 경우입니다. 누르면 새 탭에서 같은 대화를 이어 엽니다.
- **같은 제목의 탭이 여러 개**면 [점프]는 창만 앞으로 가져오고 탭은 고르지 않습니다. 엉뚱한 탭을 고르지 않기 위해서입니다.
- **세션 줄 옆의 `?`**: 상태를 알려 주는 두 출처가 서로 다르다는 표시이고 오류는 아닙니다.
- **끝난 세션이 목록에서 사라졌다면** Claude Code가 오래된 기록을 스스로 정리한 것입니다(기본 30일). 대시보드는 사용자가 [휴지통]을 누른 기록만 옮깁니다.
- 아이콘을 두 번 누르면 창이 두 개 뜹니다. 이미 떠 있으면 작업 표시줄에서 찾습니다.

## 건드리는 것과 건드리지 않는 것

- **프로세스를 끝내지 않습니다.** 대시보드를 닫아도 세션에는 영향이 없습니다.
- **`~/.claude` 아래는 읽기만 합니다.** 예외는 사용자가 [휴지통]을 누른 기록 파일 하나를 휴지통으로 옮기는 것뿐입니다. 살아 있는 세션의 기록은 옮기지 않습니다.
- **대화 내용을 밖으로 보내거나 다른 곳에 저장하지 않습니다.** 화면에는 세션 제목과 상태, 시각만 나옵니다. 제목이 아직 없는 끝난 세션은 첫 메시지의 앞부분을 제목 대신 보여 줍니다.
- **Claude Code 설정 파일은 읽지도 쓰지도 않습니다.**
- 쓰는 파일은 위의 `state.json`과 같은 폴더의 캐시뿐입니다.

## 개발

```bash
# Windows
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest tests -q

# macOS / Linux
.venv/bin/python -m pip install pytest && .venv/bin/python -m pytest tests -q
```

- 파이썬 코드는 `dashboard/`에, 화면은 `web/`의 HTML/CSS/JS에 있습니다. 화면은 `pywebview` 창에 띄우고, 수집과 버튼 동작은 Python이 합니다.
- 실행 파일은 맨 위의 `app.py`입니다(설치 스크립트가 만드는 아이콘이 이 파일을 실행합니다).
- 파일별 역할, 상태 판정 규칙, [점프]의 동작 방식 같은 내부 기록은 [docs/INTERNALS.md](docs/INTERNALS.md)에 있습니다.
- GitHub 없이 전달하려면 Windows에서 `build-zip.ps1`을 실행해 `dist\`에 zip을 만듭니다. 받는 쪽은 압축을 풀고 `install.cmd`를 실행합니다.

## 라이선스

[MIT](LICENSE)
