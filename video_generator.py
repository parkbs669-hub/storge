#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video_generator.py - TTS 음성, 자막, 배경 영상을 합성하여 최종 영상을 생성하는 모듈

MoviePy v1.x와 v2.x 모두 호환됩니다.
"""

import os
import gc
import sys
import time

# Windows 터미널 한글/이모지 출력 인코딩 오류 방지
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
import math
import glob
import random
import asyncio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import edge_tts
from dotenv import load_dotenv

load_dotenv()

# ─── MoviePy 버전 감지 및 호환 임포트 ────────────────────────────────
MOVIEPY_V2 = False

try:
    # MoviePy v1.x
    from moviepy.editor import (
        VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
        CompositeAudioClip, concatenate_videoclips, ColorClip,
    )
    from moviepy.video.fx.all import crop as moviepy_crop
    print("  [video_generator] MoviePy v1.x 감지됨")
except ImportError:
    # MoviePy v2.x
    from moviepy import (
        VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
        CompositeAudioClip, concatenate_videoclips, ColorClip,
    )
    from moviepy.video.fx import Crop
    MOVIEPY_V2 = True
    print("  [video_generator] MoviePy v2.x 감지됨")


# ─── MoviePy 버전 호환 래퍼 함수 ─────────────────────────────────────

def set_clip_start(clip, start_time: float):
    if hasattr(clip, "with_start"):
        return clip.with_start(start_time)
    return clip.set_start(start_time)


def set_clip_duration(clip, duration: float):
    if hasattr(clip, "with_duration"):
        return clip.with_duration(duration)
    return clip.set_duration(duration)


def set_clip_position(clip, position):
    if hasattr(clip, "with_position"):
        return clip.with_position(position)
    return clip.set_position(position)


def set_clip_audio(clip, audio):
    if hasattr(clip, "with_audio"):
        return clip.with_audio(audio)
    return clip.set_audio(audio)


def set_clip_fps(clip, fps):
    if hasattr(clip, "with_fps"):
        return clip.with_fps(fps)
    return clip.set_fps(fps)


# ─── 설정값 (환경변수에서 로드) ───────────────────────────────────────

def get_config():
    """환경변수에서 영상 설정값을 로드합니다."""
    return {
        "width": int(os.getenv("VIDEO_WIDTH", "1080")),
        "height": int(os.getenv("VIDEO_HEIGHT", "1920")),
        "fps": int(os.getenv("VIDEO_FPS", "24")),
        "font_size": int(os.getenv("FONT_SIZE", "40")),
        "font_path": os.getenv("FONT_PATH", ""),
    }


# ─── 한국어 폰트 탐색 ─────────────────────────────────────────────

def find_system_font() -> str | None:
    """시스템에서 사용 가능한 한국어 폰트를 탐색합니다."""
    # 일반적인 한국어 폰트 경로 목록
    font_candidates = [
        # Windows
        "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕
        "C:/Windows/Fonts/malgunbd.ttf",     # 맑은 고딕 Bold
        "C:/Windows/Fonts/gulim.ttc",        # 굴림
        "C:/Windows/Fonts/batang.ttc",       # 바탕
        "C:/Windows/Fonts/NanumGothic.ttf",
        "C:/Windows/Fonts/NanumGothicBold.ttf",
        # macOS
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/Library/Fonts/NanumGothic.ttf",
        "/Library/Fonts/NanumGothicBold.ttf",
        # Linux (Ubuntu/Debian/CentOS)
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # 프로젝트 로컬 폰트
        "./fonts/NanumGothic.ttf",
        "./fonts/NanumGothicBold.ttf",
    ]

    for path in font_candidates:
        if os.path.isfile(path):
            return path

    return None


def _load_font(font_path: str, font_size: int) -> ImageFont.FreeTypeFont:
    """폰트를 로드합니다. 실패 시 기본 폰트로 폴백."""
    if font_path and os.path.isfile(font_path):
        try:
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            pass

    # 시스템 폰트 탐색
    system_font = find_system_font()
    if system_font:
        try:
            return ImageFont.truetype(system_font, font_size)
        except Exception:
            pass

    # 최종 폴백: Pillow 기본 폰트
    print("  [경고] 한국어 폰트를 찾을 수 없습니다. 기본 폰트를 사용합니다.")
    try:
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        return ImageFont.load_default()


# ─── TTS 음성 생성 ────────────────────────────────────────────────

def generate_tts_audio(text: str, output_path: str, voice: str = "ko-KR-SunHiNeural") -> float:
    """
    edge-tts를 사용하여 한국어 TTS 음성 파일을 생성합니다.

    Args:
        text: 나레이션 텍스트 (한국어)
        output_path: 출력 mp3 파일 경로
        voice: TTS 음성 이름

    Returns:
        생성된 오디오의 재생 시간 (초)
    """
    async def _generate():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)

    # 이벤트 루프 처리 (이미 실행 중인 루프가 있을 수 있음)
    try:
        loop = asyncio.get_running_loop()
        # 이미 루프가 실행 중이면 nest_asyncio 시도 또는 새 스레드에서 실행
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _generate())
            future.result(timeout=60)
    except RuntimeError:
        # 루프가 없으면 새로 생성
        asyncio.run(_generate())

    # 생성된 오디오 파일의 재생 시간 측정
    try:
        audio_clip = AudioFileClip(output_path)
        duration = audio_clip.duration
        audio_clip.close()
    except Exception:
        # 폴백: 텍스트 길이 기반 추정 (한국어 3.5자/초)
        duration = max(3.0, len(text) / 3.5)
        print(f"  [경고] 오디오 길이 측정 실패, 추정값 사용: {duration:.1f}초")

    return duration


# ─── 자막 텍스트 줄바꿈 ───────────────────────────────────────────

def wrap_text_korean(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """
    한국어 텍스트를 글자 단위로 줄바꿈합니다.

    Args:
        text: 원본 텍스트
        font: Pillow 폰트 객체
        max_width: 최대 줄 너비 (픽셀)

    Returns:
        줄바꿈이 적용된 텍스트
    """
    lines = []
    current_line = ""

    for char in text:
        # 새 줄 시작 시 선행 공백 제거
        if not current_line and char == " ":
            continue

        test_line = current_line + char

        # Pillow 버전 호환성: getbbox (신) vs getsize (구)
        if hasattr(font, 'getbbox'):
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
        else:
            w = font.getsize(test_line)[0]

        if w > max_width:
            if current_line:
                lines.append(current_line)
            current_line = char if char != " " else ""
        else:
            current_line += char

    if current_line:
        lines.append(current_line)

    return "\n".join(lines) if lines else text


# ─── 자막 프레임 생성 ─────────────────────────────────────────────

def create_subtitle_frame(
    text: str,
    width: int,
    height: int,
    font_path: str,
    font_size: int,
    box_color_rgba: tuple = (0, 0, 0, 160),
    text_color_rgba: tuple = (255, 255, 255, 255),
) -> np.ndarray:
    """
    자막이 포함된 투명 RGBA 프레임을 생성합니다.
    화면 하단부에 반투명 배경 박스와 함께 자막을 렌더링합니다.

    Args:
        text: 자막 텍스트
        width: 프레임 너비
        height: 프레임 높이
        font_path: 폰트 파일 경로
        font_size: 폰트 크기
        box_color_rgba: 배경 박스 색상 (RGBA)
        text_color_rgba: 텍스트 색상 (RGBA)

    Returns:
        numpy 배열 (RGBA)
    """
    # 투명 베이스 이미지 생성
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 폰트 로드
    font = _load_font(font_path, font_size)

    # 텍스트 줄바꿈 (양쪽 여백 고려)
    margin_x = int(width * 0.08)
    max_text_width = width - (margin_x * 2)
    wrapped_text = wrap_text_korean(text, font, max_text_width)

    # 텍스트 바운딩 박스 계산
    if hasattr(font, 'getbbox'):
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        text_w, text_h = draw.multiline_textsize(wrapped_text, font=font)

    # 박스 위치 계산 (하단 15% 영역)
    padding_x = 24
    padding_y = 16
    box_w = text_w + padding_x * 2
    box_h = text_h + padding_y * 2

    box_x = (width - box_w) // 2
    box_y = int(height * 0.78) - box_h // 2

    # 반투명 배경 박스 그리기
    box_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    box_draw = ImageDraw.Draw(box_overlay)

    box_coords = [box_x, box_y, box_x + box_w, box_y + box_h]
    corner_radius = 16

    try:
        # Pillow 8.2+ rounded_rectangle 지원
        box_draw.rounded_rectangle(box_coords, radius=corner_radius, fill=box_color_rgba)
    except AttributeError:
        # 구버전 Pillow 폴백: 일반 사각형
        box_draw.rectangle(box_coords, fill=box_color_rgba)

    image = Image.alpha_composite(image, box_overlay)
    draw = ImageDraw.Draw(image)

    # 텍스트 그리기 (박스 중앙 정렬)
    text_x = box_x + padding_x
    text_y = box_y + padding_y

    draw.multiline_text(
        (text_x, text_y),
        wrapped_text,
        font=font,
        fill=text_color_rgba,
        align="center",
    )

    return np.array(image)


# ─── 영상 리사이즈 및 크롭 ────────────────────────────────────────

def resize_and_crop(clip, target_width: int, target_height: int):
    """
    영상을 목표 크기에 맞게 리사이즈하되, 비율이 다르면 잘라내지 않고 
    검은색 배경 위에 중앙 정렬하여 여백(레터박스/필러박스)을 남깁니다.
    """
    w, h = clip.size
    if w == target_width and h == target_height:
        return clip

    # 비율 유지하며 프레임 안에 맞추기 (Fit)
    scale = min(target_width / w, target_height / h)

    new_w = int(math.ceil(w * scale))
    new_h = int(math.ceil(h * scale))

    # 리사이즈
    if hasattr(clip, "resized"):
        resized = clip.resized((new_w, new_h))
    else:
        resized = clip.resize((new_w, new_h))

    # 검은색 배경 클립 생성
    bg_color = (0, 0, 0)
    bg = ColorClip(size=(target_width, target_height), color=bg_color, duration=clip.duration)
    if hasattr(bg, "with_fps"):
        bg = bg.with_fps(clip.fps if clip.fps else 24)
    else:
        bg = bg.set_fps(clip.fps if clip.fps else 24)

    # 중앙에 배치
    pos_x = (target_width - new_w) // 2
    pos_y = (target_height - new_h) // 2

    if hasattr(resized, "with_position"):
        positioned_resized = resized.with_position((pos_x, pos_y))
    else:
        positioned_resized = resized.set_position((pos_x, pos_y))

    # 합성
    composite = CompositeVideoClip([bg, positioned_resized], size=(target_width, target_height))
    if hasattr(composite, "with_duration"):
        composite = composite.with_duration(clip.duration)
    else:
        composite = composite.set_duration(clip.duration)

    return composite


# ─── 영상 루핑 ────────────────────────────────────────────────────

def loop_clip_to_duration(clip, target_duration: float):
    """
    영상이 목표 시간보다 짧으면 반복하여 늘립니다.
    충분히 길면 앞에서부터 잘라서 사용합니다.
    """
    clip_duration = clip.duration

    if clip_duration is None or clip_duration <= 0:
        return set_clip_duration(clip, target_duration)

    if clip_duration >= target_duration:
        # 충분히 길면 앞쪽만 사용
        if hasattr(clip, 'subclipped'):
            return clip.subclipped(0, target_duration)
        else:
            return clip.subclip(0, target_duration)

    # 반복 횟수 계산
    n_loops = math.ceil(target_duration / clip_duration)
    clips = [clip] * n_loops
    looped = concatenate_videoclips(clips)

    # 목표 길이로 트림
    if hasattr(looped, 'subclipped'):
        return looped.subclipped(0, target_duration)
    else:
        return looped.subclip(0, target_duration)


# ─── 최종 영상 빌드 ──────────────────────────────────────────────

def find_local_video(user_videos_dir: str, keyword: str, used_videos: set) -> str | None:
    """
    사용자 수집 영상 디렉토리에서 키워드와 매칭되는 영상을 찾거나, 랜덤으로 반환합니다.
    """
    if not os.path.isdir(user_videos_dir):
        return None

    # 지원하는 영상 확장자
    extensions = ["*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm"]
    video_files = []
    for ext in extensions:
        video_files.extend(glob.glob(os.path.join(user_videos_dir, ext)))
        video_files.extend(glob.glob(os.path.join(user_videos_dir, ext.upper())))

    # 중복 제거 및 절대 경로 정규화
    video_files = list(set(os.path.abspath(f) for f in video_files))
    if not video_files:
        return None

    # 아직 사용되지 않은 파일들 우선 선택
    unused_files = [f for f in video_files if f not in used_videos]
    pool = unused_files if unused_files else video_files

    # 키워드 매칭 시도 (tennis 제외)
    keyword_words = [w.lower() for w in keyword.replace("tennis", "").split() if len(w) > 1]
    matched_files = []
    if keyword_words:
        for f in pool:
            filename_lower = os.path.basename(f).lower()
            if any(word in filename_lower for word in keyword_words):
                matched_files.append(f)

    if matched_files:
        selected = random.choice(matched_files)
    else:
        selected = random.choice(pool)

    used_videos.add(selected)
    return selected


def apply_fair_use_effects(clip):
    """
    공정 이용(Fair Use) 가이드라인을 위해 원본 영상을 변형합니다:
    1. 최적 구간의 2.5초 분량 슬라이스
    2. 좌우 반전
    3. 15% 줌인 및 크롭 (방송 로고 제거 및 프레이밍 왜곡)
    4. 대비 상승 및 warm 색조 조절 필터
    """
    import numpy as np

    # 1. 2.5초 슬라이스
    duration = clip.duration
    clip_len = 2.5
    if duration and duration > clip_len:
        start_time = max(0.0, (duration - clip_len) / 2.0)
        end_time = start_time + clip_len
        if hasattr(clip, 'subclipped'):
            clip = clip.subclipped(start_time, end_time)
        else:
            clip = clip.subclip(start_time, end_time)

    # 2. 좌우 반전 (Mirror)
    if MOVIEPY_V2:
        clip = clip.transform(lambda get_frame, t: get_frame(t)[:, ::-1])
    else:
        clip = clip.fl_image(lambda img: img[:, ::-1])

    # 3. 15% 줌인 및 크롭
    w, h = clip.size
    crop_w = int(w * 0.85)
    crop_h = int(h * 0.85)
    x1 = (w - crop_w) // 2
    y1 = (h - crop_h) // 2
    x2 = x1 + crop_w
    y2 = y1 + crop_h

    if MOVIEPY_V2:
        clip = clip.with_effects([Crop(x1=x1, y1=y1, x2=x2, y2=y2)])
    else:
        clip = moviepy_crop(clip, x1=x1, y1=y1, x2=x2, y2=y2)

    # 4. 대비 및 색조 조정 필터
    def color_filter(img):
        # NumPy 연산을 통한 이미지 가공
        img_float = img.astype(np.float32)
        # 대비 1.15배 조정 (128 기준)
        img_float = (img_float - 128.0) * 1.15 + 128.0
        # 따뜻한 톤 적용
        img_float[:, :, 0] += 12.0  # Red 채널 상승
        img_float[:, :, 2] -= 6.0   # Blue 채널 하락
        return np.clip(img_float, 0, 255).astype(np.uint8)

    if MOVIEPY_V2:
        clip = clip.transform(lambda get_frame, t: color_filter(get_frame(t)))
    else:
        clip = clip.fl_image(color_filter)

    return clip


def build_final_video(
    scenes_data: list[dict],
    output_video_path: str,
    temp_dir: str = "./temp",
    voice: str = "ko-KR-SunHiNeural",
    user_videos_dir: str = "./user_videos",
):
    """
    장면 데이터를 기반으로 최종 영상을 생성합니다.

    파이프라인:
    1. 각 장면별 TTS 음성 생성
    2. 배경 영상 다운로드
    3. 리사이즈/크롭/루핑
    4. 자막 오버레이
    5. 모든 장면 결합
    6. 최종 영상 출력

    Args:
        scenes_data: 장면 정보 리스트 [{keyword, narration, subtitle}, ...]
        output_video_path: 최종 출력 영상 경로
        temp_dir: 임시 파일 디렉토리
        voice: TTS 음성
    """
    from media_downloader import download_video_for_keyword

    config = get_config()
    target_w = config["width"]
    target_h = config["height"]
    fps = config["fps"]
    font_size = config["font_size"]
    font_path = config["font_path"]

    os.makedirs(temp_dir, exist_ok=True)

    used_local_videos = set()
    scene_clips = []
    total_scenes = len(scenes_data)

    print(f"\n  영상 설정: {target_w}x{target_h} @ {fps}fps, 폰트 크기: {font_size}")
    print(f"  총 {total_scenes}개 장면 처리 시작\n")

    for idx, scene in enumerate(scenes_data):
        scene_num = idx + 1
        keyword = scene.get("keyword", "tennis")
        narration = scene.get("narration", "")
        subtitle = scene.get("subtitle", narration)

        print(f"  ── 장면 {scene_num}/{total_scenes} ──────────────────────")
        print(f"  keyword: {keyword}")
        print(f"  narration: {narration[:40]}...")

        # (A) TTS 음성 생성
        tts_path = os.path.join(temp_dir, f"scene_{scene_num:03d}_tts.mp3")
        print(f"  [A] TTS 음성 생성 중...")
        try:
            tts_duration = generate_tts_audio(narration, tts_path, voice=voice)
        except Exception as e:
            print(f"  [경고] TTS 생성 실패: {e}. 추정 길이 사용.")
            tts_duration = max(3.0, len(narration) / 3.5)

        scene_duration = tts_duration + 0.5  # 여유 시간 추가
        print(f"      TTS 길이: {tts_duration:.1f}초 → 장면 길이: {scene_duration:.1f}초")

        # (B) 배경 영상 준비 (직접 지정 ➔ 로컬 수집 폴더 우선 탐색 ➔ 기존 임시 파일 ➔ Pixabay 다운로드 순서)
        local_video = scene.get("video_path")
        if not local_video:
            local_video = find_local_video(user_videos_dir, keyword, used_local_videos)
        bg_path = os.path.join(temp_dir, f"scene_{scene_num:03d}_bg.mp4")

        if local_video:
            print(f"  [B] 📂 지정되거나 수집된 로컬 영상 사용: {local_video}")
            bg_path = local_video
        elif os.path.exists(bg_path) and os.path.getsize(bg_path) > 0:
            print(f"  [B] 📂 기존 임시 영상 감지됨 (기존 파일 사용): {bg_path}")
        else:
            print(f"  [B] 배경 영상 다운로드 중... ('{keyword}')")
            try:
                download_video_for_keyword(keyword, bg_path)
            except Exception as e:
                print(f"  [경고] 배경 영상 다운로드 실패: {e}")
                print(f"       단색 배경으로 대체합니다.")
                # 단색 클립으로 대체
                bg_clip = ColorClip(
                    size=(target_w, target_h),
                    color=(30, 60, 30),
                    duration=scene_duration,
                )
                bg_clip = set_clip_fps(bg_clip, fps)
                bg_path = None

        # (C) 배경 영상 로드 → 리사이즈 → 루핑
        if bg_path and os.path.isfile(bg_path):
            print(f"  [C] 배경 영상 처리 중...")
            try:
                bg_clip = VideoFileClip(bg_path)
                
                # 공정 이용(Fair Use) 효과 적용
                if scene.get("apply_fair_use"):
                    print("      [Fair Use] 2.5초 분할 + 좌우 반전 + 줌인 + 대비/색상 필터 적용")
                    bg_clip = apply_fair_use_effects(bg_clip)

                bg_clip = resize_and_crop(bg_clip, target_w, target_h)
                bg_clip = loop_clip_to_duration(bg_clip, scene_duration)
            except Exception as e:
                print(f"  [경고] 배경 영상 처리 실패: {e}. 단색 배경 사용.")
                bg_clip = ColorClip(
                    size=(target_w, target_h),
                    color=(30, 60, 30),
                    duration=scene_duration,
                )
                bg_clip = set_clip_fps(bg_clip, fps)

        # (D) 자막 프레임 생성
        print(f"  [D] 자막 생성 중...")
        try:
            subtitle_frame = create_subtitle_frame(
                text=subtitle,
                width=target_w,
                height=target_h,
                font_path=font_path,
                font_size=font_size,
            )
            if MOVIEPY_V2:
                subtitle_clip = ImageClip(subtitle_frame, is_mask=False, transparent=True)
            else:
                subtitle_clip = ImageClip(subtitle_frame, ismask=False, transparent=True)
            subtitle_clip = set_clip_duration(subtitle_clip, scene_duration)
            subtitle_clip = set_clip_position(subtitle_clip, ("center", "center"))
        except Exception as e:
            print(f"  [경고] 자막 생성 실패: {e}. 자막 없이 진행.")
            subtitle_clip = None

        # (E) 오디오 로드
        audio_clip = None
        if os.path.isfile(tts_path):
            try:
                audio_clip = AudioFileClip(tts_path)
            except Exception as e:
                print(f"  [경고] 오디오 로드 실패: {e}")

        # (F) 장면 합성 (배경 + 자막 + 오디오)
        print(f"  [E] 장면 합성 중...")
        layers = [bg_clip]
        if subtitle_clip is not None:
            layers.append(subtitle_clip)

        scene_clip = CompositeVideoClip(layers, size=(target_w, target_h))
        scene_clip = set_clip_duration(scene_clip, scene_duration)

        if audio_clip is not None:
            scene_clip = set_clip_audio(scene_clip, audio_clip)

        scene_clips.append(scene_clip)
        print(f"  ✅ 장면 {scene_num} 완료 ({scene_duration:.1f}초)\n")

    # ─── 전체 장면 결합 ───────────────────────────────────────────
    print(f"  ── 최종 결합 중 ({len(scene_clips)}개 장면) ──────────────")
    try:
        final_clip = concatenate_videoclips(scene_clips, method="compose")
    except Exception:
        # method 파라미터 미지원 시 폴백
        final_clip = concatenate_videoclips(scene_clips)

    total_duration = final_clip.duration
    print(f"  총 영상 길이: {total_duration:.1f}초")

    # ─── 최종 영상 출력 ───────────────────────────────────────────
    print(f"  영상 인코딩 시작: {output_video_path}")
    os.makedirs(os.path.dirname(output_video_path) if os.path.dirname(output_video_path) else ".", exist_ok=True)

    try:
        final_clip.write_videofile(
            output_video_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            logger="bar",
            preset="medium",
            bitrate="5000k",
        )
    except TypeError:
        # 일부 MoviePy 버전에서 지원하지 않는 파라미터 제거
        final_clip.write_videofile(
            output_video_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
        )

    # ─── 정리 ─────────────────────────────────────────────────────
    print(f"  리소스 정리 중...")
    for clip in scene_clips:
        try:
            clip.close()
        except Exception:
            pass
    try:
        final_clip.close()
    except Exception:
        pass

    gc.collect()
    print(f"  ✅ 최종 영상 생성 완료: {output_video_path}")


if __name__ == "__main__":
    print("=" * 50)
    print("video_generator.py 모듈 로드 테스트")
    print("=" * 50)
    config = get_config()
    print(f"  설정: {config}")
    font = find_system_font()
    print(f"  시스템 폰트: {font or '미발견'}")
    print("  ✅ 모듈 정상 로드됨")
