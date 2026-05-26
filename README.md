# 🎾 텍스트 → 영상 자동 생성기

한국어 텍스트(블로그 글)를 입력하면, **AI가 자동으로 숏폼 영상을 생성**해주는 파이프라인입니다.

---

## 📋 개요

| 항목 | 내용 |
|------|------|
| 입력 | 한국어 텍스트 파일 (.txt) 또는 내장 샘플 |
| 출력 | 세로형(1080×1920) MP4 영상 (숏폼/릴스/쇼츠 최적화) |
| AI | Google Gemini (텍스트 분석 및 장면 분할) |
| TTS | Microsoft Edge TTS (자연스러운 한국어 음성) |
| 배경 | Pixabay 무료 영상 (자동 검색 및 다운로드) |
| 자막 | Pillow 기반 한국어 자막 자동 렌더링 |

---

## 🔄 파이프라인 흐름

```
┌─────────────┐     ┌───────────────────┐     ┌──────────────────┐
│  텍스트 입력  │ ──→ │  Gemini AI 분석     │ ──→ │  장면(Scene) 분할  │
│  (.txt 파일)  │     │  (text_processor)  │     │  keyword/나레이션  │
└─────────────┘     └───────────────────┘     └────────┬─────────┘
                                                        │
                    ┌───────────────────────────────────┘
                    ▼
    ┌───────────────────────────────────────────────────────┐
    │              각 장면(Scene)별 처리                      │
    │  ┌─────────┐  ┌──────────────┐  ┌─────────────────┐  │
    │  │ TTS 음성 │  │ Pixabay 영상  │  │   자막 프레임    │  │
    │  │ (edge-   │  │  다운로드     │  │  생성 (Pillow)  │  │
    │  │  tts)    │  │ (media_      │  │                 │  │
    │  │          │  │  downloader) │  │                 │  │
    │  └────┬─────┘  └──────┬───────┘  └───────┬─────────┘  │
    │       └───────────────┼──────────────────┘            │
    │                       ▼                                │
    │            ┌──────────────────┐                        │
    │            │   장면 합성       │                        │
    │            │   (MoviePy)      │                        │
    │            └──────────────────┘                        │
    └───────────────────────────────────────────────────────┘
                            │
                            ▼
                ┌──────────────────────┐
                │   최종 영상 결합/출력  │
                │   output_video.mp4   │
                └──────────────────────┘
```

---

## 🔑 API 키 발급 (무료)

### 1. Google Gemini API 키
1. [Google AI Studio](https://aistudio.google.com/apikey) 접속
2. Google 계정으로 로그인
3. **"Get API key"** → **"Create API key"** 클릭
4. 생성된 키를 `.env` 파일의 `GEMINI_API_KEY`에 입력

### 2. Pixabay API 키 (선택)
1. [Pixabay](https://pixabay.com/accounts/register/) 회원가입
2. [API 문서 페이지](https://pixabay.com/api/docs/) 접속
3. 로그인 후 페이지 상단에 표시되는 API 키 복사
4. `.env` 파일의 `PIXABAY_API_KEY`에 입력

> 💡 Pixabay API 키가 없어도 실행 가능합니다. 배경이 단색 합성 영상으로 대체됩니다.

---

## ⚙️ 설치

### 사전 요구사항
- **Python 3.10+**
- **ffmpeg** (MoviePy 영상 처리에 필요)

```bash
# ffmpeg 설치
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows: https://ffmpeg.org/download.html 에서 다운로드
```

### 프로젝트 설치

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 API 키 입력

# 3. (선택) 한국어 폰트 설치 (Linux)
sudo apt-get install fonts-nanum
```

---

## 🚀 사용법

### 기본 실행 (내장 샘플 텍스트)
```bash
python main.py
```

### 텍스트 파일 입력
```bash
python main.py -i my_blog.txt
```

### 전체 옵션
```bash
python main.py -i my_blog.txt -o result.mp4 --voice ko-KR-InJoonNeural --width 1080 --height 1920 --fps 30 --no-cleanup
```

### 옵션 설명

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `-i`, `--input` | (내장 샘플) | 입력 텍스트 파일 경로 |
| `-o`, `--output` | `output_video.mp4` | 출력 영상 파일 경로 |
| `--temp-dir` | `./temp` | 임시 파일 디렉토리 |
| `--voice` | `ko-KR-SunHiNeural` | TTS 음성 |
| `--width` | 1080 | 영상 너비 |
| `--height` | 1920 | 영상 높이 |
| `--fps` | 24 | 영상 FPS |
| `--no-cleanup` | (삭제) | 임시 파일 유지 |

---

## 🎙️ TTS 음성 옵션

| 음성 이름 | 성별 | 특징 |
|-----------|------|------|
| `ko-KR-SunHiNeural` | 여성 | 기본값, 밝고 또렷한 음성 |
| `ko-KR-InJoonNeural` | 남성 | 차분한 남성 음성 |
| `ko-KR-HyunsuNeural` | 남성 | 자연스럽고 부드러운 음성 |

---

## 📁 파일 구조

```
project/
├── main.py              # 진입점 (CLI + 파이프라인 실행)
├── text_processor.py    # Gemini AI 텍스트 분석 (장면 분할)
├── video_generator.py   # 영상 생성 엔진 (TTS + 자막 + 합성)
├── media_downloader.py  # Pixabay 영상 검색/다운로드
├── requirements.txt     # Python 의존성 패키지
├── .env.example         # 환경변수 템플릿
├── .env                 # 실제 환경변수 (직접 생성)
└── README.md            # 프로젝트 설명서
```

---

## 🔧 환경변수 설정

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `GEMINI_API_KEY` | ✅ | - | Google Gemini API 키 |
| `PIXABAY_API_KEY` | ❌ | - | Pixabay API 키 |
| `VIDEO_WIDTH` | ❌ | 1080 | 영상 너비 (px) |
| `VIDEO_HEIGHT` | ❌ | 1920 | 영상 높이 (px) |
| `VIDEO_FPS` | ❌ | 24 | 초당 프레임 수 |
| `FONT_SIZE` | ❌ | 40 | 자막 폰트 크기 |
| `FONT_PATH` | ❌ | (자동탐색) | 한국어 폰트 경로 |

---

## ❓ 문제 해결 (Troubleshooting)

### "GEMINI_API_KEY is not set" 오류
- `.env` 파일에 `GEMINI_API_KEY=your_key`가 올바르게 설정되어 있는지 확인
- `.env` 파일이 프로젝트 루트 디렉토리에 있는지 확인

### "ffmpeg not found" 오류
```bash
# MoviePy는 ffmpeg가 필수입니다
# macOS: brew install ffmpeg
# Linux: sudo apt-get install ffmpeg
# Windows: https://ffmpeg.org/download.html
```

### 자막이 깨져서 나오는 경우
- 한국어 폰트가 설치되지 않았을 수 있습니다
- Linux: `sudo apt-get install fonts-nanum`
- 또는 `.env`에 `FONT_PATH=/path/to/your/korean/font.ttf` 직접 지정

### Pixabay 관련 오류
- API 키 확인: [Pixabay API Docs](https://pixabay.com/api/docs/)
- 일일 요청 한도 초과 여부 확인 (무료: 100회/분)
- API 키 없이도 실행 가능 (단색 배경 대체)

### MoviePy 버전 충돌
- 이 프로젝트는 **MoviePy v1.x와 v2.x 모두 호환**됩니다
- 문제 발생 시: `pip install moviepy==1.0.3` 으로 v1 설치 권장

### 영상 생성이 매우 느린 경우
- `--fps 15` 로 FPS 낮추기
- `--width 720 --height 1280` 으로 해상도 낮추기
- 장면 수가 많으면 텍스트를 짧게 조정

---

## 📝 참고사항

- **MoviePy 호환성**: v1.x(`moviepy.editor`) 와 v2.x(`moviepy`) 모두 자동 감지하여 호환
- **기본 영상 방향**: 세로형(1080×1920) — Instagram Reels, YouTube Shorts, TikTok 최적화
- **가로형 영상**: `--width 1920 --height 1080` 으로 변경 가능
- **테니스 특화**: Pixabay 검색이 테니스 영상에 최적화되어 있지만, 프롬프트 수정으로 다른 주제도 가능

---

## 📄 라이선스

이 프로젝트는 개인 학습 및 비상업적 용도로 제작되었습니다.
사용된 API (Gemini, Pixabay, Edge TTS)의 이용약관을 준수해 주세요.
