#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py - 텍스트 → 영상 자동 생성 파이프라인 (진입점)

사용법:
    python main.py                           # 내장 샘플 텍스트 사용
    python main.py -i blog.txt               # txt 파일 입력
    python main.py -i blog.txt -o result.mp4 # 출력 파일 지정
"""

import os
import sys
import argparse
import time
from dotenv import load_dotenv

# 모듈 임포트
from text_processor import analyze_blog_post
from video_generator import build_final_video

# ─── 기본 샘플 블로그 (텍스트 파일 미지정 시 사용) ────────────────────
DEFAULT_SAMPLE_BLOG = (
    "테니스는 유산소와 무산소 운동이 결합된 최고의 전신 스포츠입니다. "
    "처음 코트에 들어설 때 가장 설레는 순간은 역시 강한 서브를 성공시키는 모습일 텐데요. "
    "서브의 기초는 정확한 토스에서 시작됩니다. 볼을 가볍게 머리 위로 올리고 타점을 맞춰야 합니다. "
    "토스가 일관되지 않으면 좋은 샷을 날리기 어렵기 때문에 매일 반복 연습하는 것이 중요합니다. "
    "올바른 그립법과 함께 라켓을 끝까지 스윙해 팔로우 스루를 해주는 것도 잊지 마세요. "
    "꾸준히 연습하면 머지않아 완벽한 서브로 포인트를 낼 수 있을 것입니다. 즐거운 테니스 라이프를 즐겨보세요!"
)


def validate_environment():
    """필수 환경변수 검증. 없으면 경고, API 키 없이도 합성 영상으로 대체 가능."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    pixabay_key = os.getenv("PIXABAY_API_KEY")

    warnings = []
    if not gemini_key:
        warnings.append(
            "[경고] GEMINI_API_KEY가 설정되지 않았습니다. "
            "텍스트 분석(장면 분할)이 실패할 수 있습니다."
        )
    if not pixabay_key:
        warnings.append(
            "[경고] PIXABAY_API_KEY가 설정되지 않았습니다. "
            "배경 영상이 단색 합성 영상으로 대체됩니다."
        )

    for w in warnings:
        print(w)

    return gemini_key is not None  # Gemini 키가 있어야 최소 실행 가능


def parse_args():
    """커맨드라인 인자 파싱"""
    parser = argparse.ArgumentParser(
        description="텍스트(블로그) → 숏폼 영상 자동 생성기 🎾",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="예시:\n"
               "  python main.py\n"
               "  python main.py -i my_blog.txt\n"
               "  python main.py -i my_blog.txt -o output.mp4 --voice ko-KR-InJoonNeural\n"
    )
    parser.add_argument(
        "-i", "--input",
        type=str, default=None,
        help="입력 텍스트 파일 경로 (.txt). 미지정 시 내장 샘플 사용"
    )
    parser.add_argument(
        "-o", "--output",
        type=str, default="output_video.mp4",
        help="출력 영상 파일 경로 (기본: output_video.mp4)"
    )
    parser.add_argument(
        "--temp-dir",
        type=str, default="./temp",
        help="임시 파일 저장 디렉토리 (기본: ./temp)"
    )
    parser.add_argument(
        "--user-videos",
        type=str, default="./user_videos",
        help="사용자 수집 영상 디렉토리 (기본: ./user_videos)"
    )
    parser.add_argument(
        "--voice",
        type=str, default="ko-KR-SunHiNeural",
        help="TTS 음성 (기본: ko-KR-SunHiNeural). 남성: ko-KR-InJoonNeural"
    )
    parser.add_argument(
        "--width",
        type=int, default=None,
        help="영상 너비 (기본: VIDEO_WIDTH 환경변수 또는 1080)"
    )
    parser.add_argument(
        "--height",
        type=int, default=None,
        help="영상 높이 (기본: VIDEO_HEIGHT 환경변수 또는 1920)"
    )
    parser.add_argument(
        "--fps",
        type=int, default=None,
        help="영상 FPS (기본: VIDEO_FPS 환경변수 또는 24)"
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="완료 후 임시 파일을 삭제하지 않음"
    )
    return parser.parse_args()


def cleanup_temp(temp_dir: str):
    """임시 디렉토리 정리"""
    import shutil
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            print(f"[정리] 임시 디렉토리 삭제 완료: {temp_dir}")
        except Exception as e:
            print(f"[경고] 임시 디렉토리 정리 중 오류 발생 (윈도우 파일 잠금 등): {e}")


def main():
    """메인 파이프라인 실행"""
    # 1. 환경변수 로드
    load_dotenv()

    # 2. 커맨드라인 인자 파싱
    args = parse_args()

    # 3. CLI에서 지정한 값을 환경변수로 설정 (모듈에서 참조)
    if args.width:
        os.environ["VIDEO_WIDTH"] = str(args.width)
    if args.height:
        os.environ["VIDEO_HEIGHT"] = str(args.height)
    if args.fps:
        os.environ["VIDEO_FPS"] = str(args.fps)

    print("=" * 60)
    print("🎬 텍스트 → 영상 자동 생성기 시작")
    print("=" * 60)

    # 4. 환경변수 검증
    has_gemini = validate_environment()

    # 5. 입력 텍스트 로드
    if args.input:
        if not os.path.isfile(args.input):
            print(f"[오류] 입력 파일을 찾을 수 없습니다: {args.input}")
            sys.exit(1)
        with open(args.input, "r", encoding="utf-8") as f:
            blog_text = f.read().strip()
        if not blog_text:
            print("[오류] 입력 파일이 비어 있습니다.")
            sys.exit(1)
        print(f"[1/4] 📄 입력 파일 로드 완료: {args.input} ({len(blog_text)}자)")
    else:
        blog_text = DEFAULT_SAMPLE_BLOG
        print(f"[1/4] 📄 내장 샘플 텍스트 사용 ({len(blog_text)}자)")

    # 6. 텍스트 분석 → 장면 분할 (Gemini AI)
    print("[2/4] 🤖 AI 텍스트 분석 중 (장면 분할)...")
    start_time = time.time()
    try:
        scenes = analyze_blog_post(blog_text)
    except Exception as e:
        print(f"[오류] 텍스트 분석 실패: {e}")
        sys.exit(1)

    elapsed = time.time() - start_time
    print(f"       ✅ {len(scenes)}개 장면 생성 완료 ({elapsed:.1f}초)")
    for i, scene in enumerate(scenes):
        print(f"       장면 {i+1}: keyword=\"{scene.get('keyword', '')}\" "
              f"| 나레이션={len(scene.get('narration', ''))}자 "
              f"| 자막={len(scene.get('subtitle', ''))}자")

    # 7. 영상 생성
    print(f"[3/4] 🎥 영상 생성 중...")
    start_time = time.time()
    try:
        build_final_video(
            scenes_data=scenes,
            output_video_path=args.output,
            temp_dir=args.temp_dir,
            voice=args.voice,
            user_videos_dir=args.user_videos,
        )
    except Exception as e:
        print(f"[오류] 영상 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start_time
    print(f"       ✅ 영상 생성 완료 ({elapsed:.1f}초)")

    # 8. 정리
    if not args.no_cleanup:
        cleanup_temp(args.temp_dir)

    print("=" * 60)
    output_size = os.path.getsize(args.output) / (1024 * 1024)
    print(f"[4/4] 🎉 최종 영상 저장 완료: {args.output} ({output_size:.1f}MB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
