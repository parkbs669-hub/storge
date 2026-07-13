# Antigravity CLI (`agy`) 자동 실행 및 권한 프롬프트 생략 설정 가이드

Antigravity CLI(`agy`) 환경에서 에이전트가 실행하는 명령어(`run_command`), 파일 수정 등의 동작 시 매번 등장하는 **"Do you want to proceed? [y/N]"** 프롬프트를 생략하고 자동으로 실행되도록 하는 방법입니다.

> [!WARNING]
> 이 설정을 활성화하면 에이전트가 사용자의 개입 없이 파괴적인 명령(예: 파일 삭제, 푸시 등)을 수행할 수 있게 되므로, 신뢰할 수 있는 개발 환경에서만 주의하여 사용하시기 바랍니다.

---

## 방법 1: 설정 파일 (`settings.json`) 수정 (영구 적용)

가장 추천하는 방법은 Antigravity CLI의 글로벌 설정 파일에 `dangerouslySkipPermissions` 옵션을 추가하는 것입니다.

### 1. 설정 파일 경로 찾기
각 운영체제별로 아래 경로에 설정 파일이 위치합니다.
* **Windows**: `C:\Users\<사용자명>\.gemini\antigravity-cli\settings.json`
* **macOS / Linux**: `~/.gemini/antigravity-cli/settings.json`

### 2. 설정 값 추가
`settings.json` 파일을 텍스트 에디터로 열어 **`"dangerouslySkipPermissions": true`** 항목을 추가합니다.

**예시 (`settings.json`):**
```json
{
  "allowNonWorkspaceAccess": true,
  "dangerouslySkipPermissions": true,
  "model": "Claude Opus 4.6 (Thinking)",
  "trustedWorkspaces": [
    "C:\\Users\\박범서",
    "C:\\Users\\박범서\\OneDrive\\Desktop"
  ]
}
```

이렇게 구성하면 이후 실행되는 모든 `agy` 세션에서 권한 요청 없이 즉시 명령어가 승인 및 실행됩니다.

---

## 방법 2: 명령줄 실행 플래그 사용 (일회성 적용)

CLI를 실행할 때 특정 명령어로 실행하여 일시적으로 질문을 생략하게 만들 수 있습니다.

### 실행 명령어
터미널에서 `agy`를 시작할 때 `--dangerously-skip-permissions` 플래그를 붙여서 실행합니다.

```bash
agy --dangerously-skip-permissions
```

이 방식으로 진입한 세션 내에서는 종료 시까지 질문을 묻지 않고 자동으로 모든 작업을 속행합니다.
