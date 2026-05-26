#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
text_processor.py - Gemini AI를 사용한 블로그 텍스트 → 장면 분할 모듈

블로그 글을 입력받아 각 10~15초 분량의 영상 장면(Scene)으로 분할합니다.
각 장면은 keyword(영어), narration(한국어), subtitle(한국어)로 구성됩니다.
"""

import os
import re
import json
import google.generativeai as genai
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# ─── Gemini 모델 우선순위 목록 ─────────────────────────────────────
MODEL_CANDIDATES = [
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-pro",
]

# ─── 프롬프트 템플릿 ───────────────────────────────────────────────
SYSTEM_PROMPT = """You are a professional video producer. Your task is to analyze and split the following tennis blog post into sequential scenes to generate a high-quality video.

Each scene must represent approximately 10 to 15 seconds of video.
A typical reading speed for narration is about 3 to 4 Korean characters (syllables) per second. Therefore, each scene's narration should be about 30 to 50 Korean characters long.

For each scene, generate:
- keyword: An English search keyword or short phrase that MUST be strictly relevant to tennis. To ensure Pixabay returns actual tennis videos, the keyword MUST consist of 1 to 3 words and ALWAYS include the word "tennis" directly (e.g., "tennis play", "tennis serve", "tennis court", "tennis player", "tennis match", "tennis hit", "tennis training"). Avoid abstract terms like "scoreboard", "coach", "audience", "hands", "tired" as they cause Pixabay to return unrelated general videos.
- narration: The voice-over text in Korean. It should flow naturally from the previous scene and cover a sequential part of the blog post.
- subtitle: The subtitle text in Korean. This will be overlayed on screen. It can be the same as the narration or slightly shortened for readability.

You MUST respond with ONLY a JSON array containing objects with the exact keys: "keyword", "narration", "subtitle".
Do NOT include markdown code blocks, explanations, or any text outside the JSON array.
Ensure the output is valid JSON.

### Here is the blog post text to analyze:

"""


def _get_model(api_key: str):
    """사용 가능한 Gemini 모델을 순서대로 시도하여 반환합니다."""
    genai.configure(api_key=api_key)

    for model_name in MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name)
            # 간단한 테스트 호출로 모델 사용 가능 여부 확인
            print(f"  [text_processor] 모델 시도: {model_name}")
            model.generate_content("test")
            return model, model_name
        except Exception as e:
            print(f"  [text_processor] 모델 {model_name} 사용 불가: {e}")
            continue

    raise RuntimeError(
        "사용 가능한 Gemini 모델이 없습니다. "
        f"시도한 모델: {MODEL_CANDIDATES}"
    )


def _clean_json_response(text: str) -> str:
    """Gemini 응답에서 JSON 배열만 추출합니다."""
    # 1. 마크다운 코드 블록 제거 (```json ... ``` 또는 ``` ... ```)
    cleaned = re.sub(r'```(?:json)?\s*\n?', '', text)
    cleaned = re.sub(r'```', '', cleaned)
    cleaned = cleaned.strip()

    # 2. 이미 JSON 배열이면 그대로 반환
    if cleaned.startswith('['):
        return cleaned

    # 3. JSON 배열을 정규식으로 추출
    match = re.search(r'\[[\s\S]*\]', cleaned)
    if match:
        return match.group(0)

    return cleaned


def _validate_scenes(scenes: list) -> list:
    """장면 데이터 유효성 검증 및 자동 수정."""
    required_keys = {"keyword", "narration", "subtitle"}
    validated = []

    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            print(f"  [경고] 장면 {i+1}: dict가 아닌 항목 무시")
            continue

        # 필수 키 확인
        missing = required_keys - set(scene.keys())
        if missing:
            print(f"  [경고] 장면 {i+1}: 누락된 키 {missing}, 기본값으로 보완")
            for key in missing:
                if key == "keyword":
                    scene[key] = "tennis"
                elif key == "narration":
                    scene[key] = scene.get("subtitle", "테니스")
                elif key == "subtitle":
                    scene[key] = scene.get("narration", "테니스")

        # keyword에 'tennis'가 없으면 자동 추가
        keyword = scene.get("keyword", "").strip().lower()
        if "tennis" not in keyword:
            original = scene["keyword"]
            scene["keyword"] = f"tennis {original}".strip()
            print(f"  [자동수정] 장면 {i+1}: keyword \"{original}\" → \"{scene['keyword']}\"")

        # 빈 값 체크
        for key in required_keys:
            if not scene.get(key, "").strip():
                scene[key] = "tennis" if key == "keyword" else "테니스"

        validated.append(scene)

    return validated


def analyze_blog_post(blog_text: str) -> list[dict]:
    """
    블로그 글을 Gemini AI로 분석하여 장면 목록을 반환합니다.

    Args:
        blog_text: 한국어 블로그 본문 텍스트

    Returns:
        list[dict]: 각 장면 정보 (keyword, narration, subtitle)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY가 설정되지 않았습니다. "
            ".env 파일에 GEMINI_API_KEY=your_key 를 추가해주세요.\n"
            "무료 API 키: https://aistudio.google.com/apikey"
        )

    # 모델 선택
    model, model_name = _get_model(api_key)
    print(f"  [text_processor] 사용 모델: {model_name}")

    # 프롬프트 구성
    full_prompt = SYSTEM_PROMPT + blog_text

    # 생성 설정
    generation_config = genai.types.GenerationConfig(
        temperature=0.3,
        max_output_tokens=4096,
    )

    # API 호출
    try:
        response = model.generate_content(
            full_prompt,
            generation_config=generation_config,
        )
    except Exception as e:
        raise RuntimeError(f"Gemini API 호출 실패: {e}")

    # 응답 텍스트 추출
    raw_text = response.text
    if not raw_text:
        raise ValueError("Gemini에서 빈 응답을 받았습니다.")

    # JSON 파싱
    cleaned_text = _clean_json_response(raw_text)
    try:
        scenes = json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        print(f"  [경고] JSON 파싱 실패, 재시도 중...")
        print(f"  원본 응답: {raw_text[:500]}")
        # 한 번 더 정규식으로 시도
        match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', raw_text)
        if match:
            try:
                scenes = json.loads(match.group(0))
            except json.JSONDecodeError:
                raise ValueError(
                    f"Gemini 응답을 JSON으로 파싱할 수 없습니다.\n"
                    f"파싱 오류: {e}\n"
                    f"응답 내용: {raw_text[:1000]}"
                )
        else:
            raise ValueError(
                f"Gemini 응답에서 JSON 배열을 찾을 수 없습니다.\n"
                f"응답 내용: {raw_text[:1000]}"
            )

    if not isinstance(scenes, list) or len(scenes) == 0:
        raise ValueError(f"Gemini 응답이 비어 있거나 배열이 아닙니다: {type(scenes)}")

    # 유효성 검증 및 자동 수정
    scenes = _validate_scenes(scenes)

    if not scenes:
        raise ValueError("유효한 장면이 하나도 생성되지 않았습니다.")

    return scenes


if __name__ == "__main__":
    # 단독 실행 시 테스트
    test_text = (
        "테니스를 시작하는 초보자분들을 위해 오늘 테니스 라켓 고르는 꿀팁을 준비했습니다. "
        "우선 라켓의 무게가 중요합니다. 남성은 보통 280~300g, 여성은 250~270g으로 시작하는 것이 좋습니다. "
        "또한 헤드 사이즈는 100sq inch 정도가 스윗스팟이 넓어 공을 맞추기 편합니다. "
        "꾸준히 연습하면 누구나 멋진 서브를 넣을 수 있습니다. 다들 테니스 코트에서 만나요!"
    )
    print("=" * 50)
    print("text_processor.py 테스트")
    print("=" * 50)
    try:
        scenes = analyze_blog_post(test_text)
        print(f"\n✅ {len(scenes)}개 장면 생성 완료:")
        print(json.dumps(scenes, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"\n❌ 오류: {e}")
