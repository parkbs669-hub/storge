import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# Load env variables in case they are not loaded yet
load_dotenv()

def analyze_blog_post(blog_text: str) -> list[dict]:
    """
    Splits the blog post text into logical scenes of 10-15 seconds.
    Each scene consists of:
    - keyword: English keyword for Pixabay video search.
    - narration: Voice-over text (Korean) to be spoken by TTS.
    - subtitle: Subtitle text (Korean) to be rendered on screen.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Please set it in your .env file.")
    
    genai.configure(api_key=api_key)
    
    # We use gemini-3.5-flash as the default capable model on this system
    model = genai.GenerativeModel("gemini-3.5-flash")
    
    prompt = f"""
You are a professional video producer. Your task is to analyze and split the following tennis blog post into sequential scenes to generate a high-quality video.
Each scene must represent approximately 10 to 15 seconds of video.
A typical reading speed for narration is about 3 to 4 Korean characters (syllables) per second. Therefore, each scene's narration should be about 30 to 50 Korean characters long.

For each scene, generate:
1. `keyword`: An English search keyword or short phrase that MUST be strictly relevant to tennis. To ensure Pixabay returns actual tennis videos, the keyword MUST consist of 1 to 3 words and ALWAYS include the word "tennis" directly (e.g., "tennis play", "tennis serve", "tennis court", "tennis player", "tennis match", "tennis hit", "tennis training"). Avoid abstract terms like "scoreboard", "coach", "audience", "hands", "tired" as they cause Pixabay to return unrelated general videos.
2. `narration`: The voice-over text in Korean. It should flow naturally from the previous scene and cover a sequential part of the blog post.
3. `subtitle`: The subtitle text in Korean. This will be overlayed on screen. It can be the same as the narration or slightly shortened for readability.

You MUST respond with a JSON array containing objects with the exact keys: "keyword", "narration", "subtitle".
Ensure the output is valid JSON.

Here is the blog post text to analyze:
---
{blog_text}
---
"""
    
    # Enforce JSON output format using generation_config
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    
    response_text = response.text.strip()
    
    try:
        scenes = json.loads(response_text)
        if not isinstance(scenes, list):
            raise ValueError("Expected a list of scenes, but got a different structure.")
        return scenes
    except json.JSONDecodeError:
        # Fallback parsing in case the model returns markdown code block formatting
        cleaned_text = response_text
        if cleaned_text.startswith("```"):
            lines = cleaned_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_text = "\n".join(lines).strip()
        return json.loads(cleaned_text)

if __name__ == "__main__":
    # Quick test if run directly
    test_text = (
        "테니스를 시작하는 초보자분들을 위해 오늘 테니스 라켓 고르는 꿀팁을 준비했습니다. "
        "우선 라켓의 무게가 중요합니다. 남성은 보통 280~300g, 여성은 250~270g으로 시작하는 것이 좋습니다. "
        "또한 헤드 사이즈는 100sq inch 정도가 스윗스팟이 넓어 공을 맞추기 편합니다. "
        "꾸준히 연습하면 누구나 멋진 서브를 넣을 수 있습니다. 다들 테니스 코트에서 만나요!"
    )
    print("Testing blog parsing...")
    try:
        scenes = analyze_blog_post(test_text)
        print("Successfully parsed scenes:")
        print(json.dumps(scenes, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error during test: {e}")
