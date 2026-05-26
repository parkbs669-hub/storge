#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
download_clip.py - 유튜브 쇼츠/동영상 및 인스타그램 릴스 다운로드 스크립트

사용법:
    python download_clip.py "https://www.youtube.com/shorts/..."
    python download_clip.py "https://www.instagram.com/reels/..."
"""

import os
import sys

def download_video(url, output_dir="./user_videos"):
    # 1. yt-dlp 설치 여부 확인 및 자동 설치
    try:
        import yt_dlp
    except ImportError:
        print("[정보] yt-dlp 패키지가 설치되어 있지 않아 설치를 진행합니다...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
            import yt_dlp
            print("[성공] yt-dlp 패키지가 성공적으로 설치되었습니다.")
        except Exception as install_err:
            print(f"[오류] yt-dlp 패키지 설치 실패: {install_err}")
            print("수동으로 'pip install yt-dlp'를 실행한 후 다시 시도해 주세요.")
            return None

    # 2. 출력 폴더 생성
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"[정보] 영상을 저장할 폴더가 생성되었습니다: {output_dir}")

    # 3. 다운로드 옵션 설정 (MP4 선호)
    print(f"\n[시작] 영상 다운로드 시도 중: {url}")
    ydl_opts = {
        # MP4 단일 포맷의 최적 비디오 다운로드 (ffmpeg 병합 방지)
        'format': 'best[ext=mp4]/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'no_warnings': True,
        'quiet': False,
        # 인스타그램/유튜브 차단 방지를 위한 일반 브라우저 User-Agent 설정
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }

    # 4. 다운로드 실행
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            print("=" * 60)
            print("[완료] 다운로드 완료!")
            # 윈도우 인코딩 오류 방지를 위해 경로 안전 출력
            try:
                print(f"[저장 위치] {filename}")
            except UnicodeEncodeError:
                print(f"[저장 위치] {filename.encode('utf-8', errors='replace').decode('cp949', errors='replace')}")
            print("=" * 60)
            return filename
    except Exception as e:
        # 오류 출력시 인코딩 예외 방지
        try:
            print(f"\n[오류] 다운로드 중 문제가 발생했습니다: {e}")
        except UnicodeEncodeError:
            print(f"\n[오류] 다운로드 중 문제가 발생했습니다: {str(e).encode('utf-8', errors='replace').decode('cp949', errors='replace')}")
        print("URL이 유효한지 확인하시거나, 잠시 후 다시 시도해 주세요.")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python download_clip.py <유튜브_또는_인스타그램_URL>")
        print("예시: python download_clip.py \"https://www.youtube.com/shorts/AbCdEfGhIj\"")
        sys.exit(1)
    
    target_url = sys.argv[1]
    download_video(target_url)
