#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
download_pinterest.py - Pinterest 테니스 영상 검색 및 다운로드 스크립트

사용법:
    python download_pinterest.py --max 10
"""

import os
import sys
import re
import time
import argparse
import subprocess
import io

# Windows 콘솔 인코딩 대응 (UTF-8 출력 강제 및 인코딩 불가 문자 대체)
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def install_and_import(package):
    try:
        __import__(package)
    except ImportError:
        print(f"[정보] {package} 패키지가 설치되어 있지 않아 설치를 진행합니다...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"[성공] {package} 패키지가 성공적으로 설치되었습니다.")
        except Exception as err:
            print(f"[오류] {package} 패키지 설치 실패: {err}")
            print(f"수동으로 'pip install {package}'를 실행해 주세요.")
            sys.exit(1)

# 필수 패키지 확인
install_and_import("playwright")
install_and_import("yt_dlp")

from playwright.sync_api import sync_playwright
import yt_dlp

def scrape_pin_urls(search_url, scrolls=6):
    """Playwright를 이용해 Pinterest 검색 페이지에서 Pin URL들을 수집합니다."""
    pin_urls = []
    
    # Playwright 브라우저 설치 확인 및 실행
    try:
        print("[정보] Playwright Chromium 브라우저 확인 중...")
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    except Exception as e:
        print(f"[경고] Playwright 브라우저 설치 시도 중 메시지: {e}")

    print("\n[시작] Pinterest 검색 페이지 분석을 시작합니다...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            
            print(f"[정보] Pinterest 접속 중: {search_url}")
            page.goto(search_url, wait_until="load", timeout=60000)
            time.sleep(5)  # 페이지 로딩 및 렌더링 대기
            
            # 스크롤을 내려서 더 많은 핀 로딩
            for i in range(scrolls):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(3)
                print(f"  -> 스크롤 {i+1}/{scrolls} 완료 (추가 핀 로딩 중)")
                
            # 모든 a 태그의 href 추출
            hrefs = page.eval_on_selector_all("a", "elements => elements.map(el => el.href)")
            
            # /pin/숫자/ 패턴 필터링
            pin_regex = re.compile(r'https://[^/]+/pin/(\d+)/?')
            for href in hrefs:
                match = pin_regex.match(href)
                if match:
                    pin_id = match.group(1)
                    pin_urls.append(f"https://www.pinterest.com/pin/{pin_id}/")
                    
            # 중복 제거 및 순서 보존
            seen = set()
            unique_pins = []
            for url in pin_urls:
                if url not in seen:
                    seen.add(url)
                    unique_pins.append(url)
                    
            print(f"[완료] 총 {len(unique_pins)}개의 핀 URL을 발견했습니다.")
            browser.close()
            return unique_pins
            
        except Exception as e:
            print(f"[오류] Playwright 브라우저 실행 중 오류 발생: {e}")
            return []

def download_videos_from_pins(pin_urls, output_dir="./user_videos", max_downloads=10):
    """Pin URL 목록 중 비디오 핀을 탐색하여 최적의 비디오를 다운로드합니다."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"[정보] 저장 폴더가 생성되었습니다: {output_dir}")
        
    print(f"\n[다운로드 시작] 최대 {max_downloads}개의 비디오 다운로드를 시도합니다...")
    downloaded_count = 0
    
    for i, pin_url in enumerate(pin_urls):
        if downloaded_count >= max_downloads:
            print(f"\n[알림] 설정한 최대 다운로드 수({max_downloads}개)에 도달하여 작업을 종료합니다.")
            break
            
        print(f"\n[{i+1}/{len(pin_urls)}] 핀 분석 중: {pin_url}")
        
        # yt-dlp로 비디오 여부 확인
        ydl_opts_check = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts_check) as ydl:
                info = ydl.extract_info(pin_url, download=False)
                
                # 비디오 포맷 확인
                if info and 'formats' in info and len(info['formats']) > 0:
                    title = info.get('title') or f"pinterest_video_{info.get('id')}"
                    # 파일명 안전하게 처리 (특수문자 제거)
                    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip()
                    safe_title = safe_title[:50]  # 너무 긴 파일명 방지
                    
                    filename_template = f"pinterest_{info.get('id')}_{safe_title}.%(ext)s"
                    output_template = os.path.join(output_dir, filename_template)
                    
                    print(f"  -> [비디오 감지됨] 제목: '{title}'")
                    print(f"  -> 다운로드 시도 중...")
                    
                    ydl_opts_download = {
                        'format': 'best[ext=mp4]/best',
                        'outtmpl': output_template,
                        'quiet': False,
                        'no_warnings': True
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts_download) as ydl_down:
                        ydl_down.download([pin_url])
                        
                    downloaded_count += 1
                    print(f"  -> [성공] 다운로드 완료! (현재 누적: {downloaded_count}/{max_downloads})")
                else:
                    print("  -> [건너뜀] 비디오 포맷이 없는 이미지 핀입니다.")
        except Exception as e:
            print(f"  -> [건너뜀] 추출 실패 (이유: {e})")
            
    print(f"\n==================================================")
    print(f"[완료] 모든 작업이 완료되었습니다!")
    print(f"[다운로드 결과] 다운로드된 총 비디오 개수: {downloaded_count}개")
    print(f"[저장 폴더] 저장된 폴더: {os.path.abspath(output_dir)}")
    print(f"==================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pinterest에서 비디오를 추출하여 다운로드합니다.")
    parser.add_argument("--max", type=int, default=10, help="최대 다운로드할 비디오 개수 (기본값: 10)")
    parser.add_argument("--scrolls", type=int, default=6, help="검색 페이지 스크롤 횟수 (기본값: 6)")
    parser.add_argument("--url", type=str, 
                        default="https://kr.pinterest.com/search/pins/?q=%ED%85%8C%EB%8B%88%EC%8A%A4%20%EC%98%81%EC%83%81&rs=typed",
                        help="Pinterest 검색 URL 또는 보드 URL")
    
    args = parser.parse_args()
    
    # 핀 수집
    pins = scrape_pin_urls(args.url, scrolls=args.scrolls)
    
    if pins:
        # 비디오 다운로드
        download_videos_from_pins(pins, output_dir="./user_videos", max_downloads=args.max)
    else:
        print("[오류] 수집된 핀 URL이 없습니다. 검색 URL 또는 네트워크 상태를 확인해 주세요.")
