#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_alcaraz_shorts.py - 카를로스 알카라즈 유투브 숏 영상 생성기
"""

import os
import sys
from dotenv import load_dotenv

# Windows 터미널 한글/이모지 출력 인코딩 오류 방지
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# 로컬 모듈 임포트를 위해 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from video_generator import build_final_video

def main():
    load_dotenv()
    
    # 1. 숏폼을 위한 환경변수 설정 강제화 (1080x1920 세로형)
    os.environ["VIDEO_WIDTH"] = "1080"
    os.environ["VIDEO_HEIGHT"] = "1920"
    os.environ["VIDEO_FPS"] = "24"
    os.environ["FONT_SIZE"] = "42"  # 자막이 잘 보이도록 약간 크게 설정

    # 2. 입력 텍스트 파일 경로 및 비디오 파일 목록
    text_file_path = r"C:\Users\bagch\Downloads\알카라즈.txt"
    user_videos_dir = r"C:\Users\bagch\Downloads\text_to_video_project\user_videos"
    output_video_path = r"C:\Users\bagch\Downloads\text_to_video_project\alcaraz_shorts_fairuse.mp4"

    video_files = [
        "pinterest_1011902609998539011_Tennis serve follow me on Instagram oliviahr.mp4",
        "pinterest_68749662341_Pinterest video 68749662341.mp4",
        "pinterest_23714335536748429_Pinterest video 23714335536748429.mp4",
        "pinterest_35817759532208826_Pinterest video 35817759532208826.mp4",
        "pinterest_423549539977815859_Pinterest video 423549539977815859.mp4",
        "pinterest_437904763787417079_Pinterest video 437904763787417079.mp4",
    ]

    # 3. 텍스트 파일 로드 및 줄바꿈 처리
    if not os.path.isfile(text_file_path):
        print(f"[오류] 텍스트 파일을 찾을 수 없습니다: {text_file_path}")
        sys.exit(1)

    with open(text_file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    print(f"텍스트 파일 로드 완료: 총 {len(lines)}개 문장")
    for idx, line in enumerate(lines):
        print(f"  라인 {idx+1}: {line}")

    if len(lines) != len(video_files):
        print(f"[경고] 텍스트 라인 수({len(lines)})와 비디오 파일 수({len(video_files)})가 일치하지 않습니다.")
        # 일치하도록 슬라이스 혹은 보정
        min_len = min(len(lines), len(video_files))
        lines = lines[:min_len]
        video_files = video_files[:min_len]

    # 4. 장면 데이터 구성 (narration, subtitle, video_path 매핑)
    scenes_data = []
    for idx, (line, vid_name) in enumerate(zip(lines, video_files)):
        vid_path = os.path.join(user_videos_dir, vid_name)
        if not os.path.isfile(vid_path):
            print(f"[오류] 비디오 파일을 찾을 수 없습니다: {vid_path}")
            sys.exit(1)
            
        scenes_data.append({
            "keyword": f"scene_{idx+1}",
            "narration": line,
            "subtitle": line,
            "video_path": vid_path,
            "apply_fair_use": True
        })

    # 5. 영상 생성 파이프라인 호출
    print("\n알카라즈 숏폼 영상 생성을 진행합니다...")
    try:
        build_final_video(
            scenes_data=scenes_data,
            output_video_path=output_video_path,
            temp_dir="./temp_alcaraz",
            voice="ko-KR-SunHiNeural",  # 기본 여성 음성 사용
            user_videos_dir=user_videos_dir,
        )
        print(f"\n[성공] 최종 영상이 성공적으로 저장되었습니다: {output_video_path}")
    except Exception as e:
        print(f"\n[오류] 영상 생성 도중 오류가 발생했습니다: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
