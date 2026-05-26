#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
media_downloader.py - Pixabay 영상 검색 및 다운로드 모듈

키워드 기반으로 Pixabay에서 테니스 관련 영상을 검색, 필터링, 다운로드합니다.
API 키가 없을 경우 합성 단색 영상으로 대체합니다.
"""

import os
import random
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()


def get_best_video_url(videos_dict: dict) -> str | None:
    """
    Pixabay 영상 딕셔너리에서 최적 해상도 URL을 반환합니다.
    1080p 이상 우선, 없으면 최고 해상도 선택.
    """
    formats = []
    for fmt_name, fmt_info in videos_dict.items():
        if isinstance(fmt_info, dict) and 'url' in fmt_info:
            width = fmt_info.get('width', 0)
            height = fmt_info.get('height', 0)
            url = fmt_info.get('url')
            resolution_pixels = width * height
            formats.append((resolution_pixels, width, height, url))

    if not formats:
        return None

    # 해상도 내림차순 정렬
    formats.sort(key=lambda x: x[0], reverse=True)

    # 1080p 이상 우선 선택
    for _, w, h, url in formats:
        if w >= 1920 or h >= 1080:
            return url

    # 폴백: 최고 해상도
    return formats[0][3]


def search_pixabay_videos(query: str, api_key: str) -> list[dict]:
    """Pixabay Video API로 영상 검색."""
    url = "https://pixabay.com/api/videos/"
    params = {
        "key": api_key,
        "q": query,
        "video_type": "film",
        "per_page": 20,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("hits", [])


def is_strictly_tennis(hit: dict) -> bool:
    """
    표준 코트 테니스 영상만 통과시키는 필터.
    탁구, 비치테니스, 배드민턴, 패들 등을 제외합니다.
    """
    tags = [t.strip().lower() for t in hit.get("tags", "").split(",")]

    # 'tennis' 태그가 반드시 있어야 함
    if "tennis" not in tags:
        return False

    # 제외할 태그 목록
    exclude_tags = [
        "table tennis", "ping pong", "squash", "beach", "sand",
        "vacation", "badminton", "padel", "matkot", "courtroom",
        "ping-pong", "table-tennis",
    ]
    for tag in tags:
        for exclude in exclude_tags:
            if exclude in tag:
                return False

    return True


def _generate_synthetic_video(keyword: str, output_path: str) -> str:
    """API 키 없을 때 합성 단색 영상 생성 (MoviePy v1/v2 호환)."""
    try:
        from moviepy.editor import ColorClip
    except ImportError:
        from moviepy import ColorClip

    # 키워드 기반 고유 색상 생성
    h = hashlib.md5(keyword.encode('utf-8')).hexdigest()
    r = int(h[0:2], 16) % 120 + 30
    g = int(h[2:4], 16) % 120 + 30
    b = int(h[4:6], 16) % 120 + 30
    color = (r, g, b)

    width = int(os.getenv("VIDEO_WIDTH", "1080"))
    height = int(os.getenv("VIDEO_HEIGHT", "1920"))

    # 충분한 길이의 합성 영상 생성 (루핑 대비)
    clip = ColorClip(size=(width, height), color=color, duration=25)
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    # MoviePy v1/v2 호환 write
    try:
        clip.write_videofile(output_path, fps=24, codec="libx264", logger=None)
    except TypeError:
        clip.write_videofile(output_path, fps=24, codec="libx264")

    clip.close()
    return output_path


def download_video_for_keyword(keyword: str, output_path: str) -> str:
    """
    키워드에 맞는 Pixabay 영상을 검색하고 다운로드합니다.

    검색 전략:
    1. 전체 키워드로 검색
    2. 단어를 하나씩 줄여가며 재검색
    3. 'tennis'로 폴백 검색
    4. API 키 없으면 합성 영상 생성

    Args:
        keyword: 영어 검색 키워드
        output_path: 다운로드 파일 저장 경로

    Returns:
        다운로드된 파일 경로
    """
    api_key = os.getenv("PIXABAY_API_KEY")

    if not api_key:
        print(f"  --> PIXABAY_API_KEY 미설정. 합성 영상으로 대체: '{keyword}'")
        try:
            _generate_synthetic_video(keyword, output_path)
            print(f"  --> 합성 영상 생성 완료: {output_path}")
            return output_path
        except Exception as e:
            raise RuntimeError(f"합성 영상 생성 실패: {e}")

    words = keyword.strip().split()
    hits = []

    # 단계적 검색: 전체 → 줄여가며 검색
    for i in range(len(words), 0, -1):
        sub_query = " ".join(words[:i])
        try:
            raw_hits = search_pixabay_videos(sub_query, api_key)
            filtered = [h for h in raw_hits if is_strictly_tennis(h)]
            if filtered:
                hits = filtered
                print(f"  --> '{sub_query}' 검색 성공: {len(hits)}개 테니스 영상 발견")
                break
        except Exception as e:
            print(f"  --> '{sub_query}' 검색 오류: {e}")

    # 폴백: 'tennis'로 검색
    if not hits:
        print(f"  --> '{keyword}' 검색 실패. 'tennis'로 폴백 검색...")
        try:
            raw_hits = search_pixabay_videos("tennis", api_key)
            filtered = [h for h in raw_hits if is_strictly_tennis(h)]
            if filtered:
                hits = filtered
                print(f"  --> 'tennis' 폴백 성공: {len(hits)}개 영상 발견")
        except Exception as e:
            print(f"  --> 'tennis' 폴백 검색 오류: {e}")

    if not hits:
        raise ValueError(
            f"Pixabay에서 '{keyword}' 및 'tennis' 검색 모두 실패했습니다. "
            "API 키를 확인하거나 네트워크 연결을 점검해주세요."
        )

    # 랜덤 선택 (영상 다양성)
    hit = random.choice(hits)
    video_url = get_best_video_url(hit.get('videos', {}))

    if not video_url:
        raise ValueError(f"선택된 영상(ID: {hit.get('id')})에서 유효한 URL을 찾을 수 없습니다.")

    print(f"  --> 선택 영상 ID: {hit.get('id')} | Tags: {hit.get('tags')}")
    print(f"  --> 다운로드 URL: {video_url}")

    # 파일 다운로드 (청크 단위)
    response = requests.get(video_url, stream=True, timeout=60)
    response.raise_for_status()

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    downloaded_size = 0
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded_size += len(chunk)

    print(f"  --> 다운로드 완료: {output_path} ({downloaded_size / 1024 / 1024:.1f}MB)")
    return output_path


if __name__ == "__main__":
    # 단독 테스트
    import sys

    test_key = "tennis court top view"
    test_out = "./temp/test_video.mp4"

    print("=" * 50)
    print("media_downloader.py 테스트")
    print("=" * 50)
    try:
        result = download_video_for_keyword(test_key, test_out)
        print(f"✅ 다운로드 완료: {result}")
    except Exception as e:
        print(f"❌ 오류: {e}")
        print("PIXABAY_API_KEY가 .env 파일에 설정되어 있는지 확인해주세요.")
