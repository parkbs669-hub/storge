import os
import argparse
from dotenv import load_dotenv

# Import module functions
from text_processor import analyze_blog_post
from video_generator import build_final_video

# Default tennis blog post used as a fallback or for demonstration
DEFAULT_SAMPLE_BLOG = (
    "테니스는 유산소와 무산소 운동이 결합된 최고의 전신 스포츠입니다. "
    "처음 코트에 들어설 때 가장 설레는 순간은 역시 강한 서브를 성공시키는 모습일 텐데요. "
    "서브의 기초는 정확한 토스에서 시작됩니다. 볼을 가볍게 머리 위로 올리고 타점을 맞춰야 합니다. "
    "토스가 일관되지 않으면 좋은 샷을 날리기 어렵기 때문에 매일 반복 연습하는 것이 중요합니다. "
    "올바른 그립법과 함께 라켓을 끝까지 스윙해 팔로우 스루를 해주는 것도 잊지 마세요. "
    "꾸준히 연습하면 머지않아 완벽한 서브로 포인트를 낼 수 있을 것입니다. 즐거운 테니스 라이프를 즐겨보세요!"
)

def main():
    # Load environment variables from .env
    load_dotenv()
    
    # Retrieve and check API keys
    gemini_key = os.getenv("GEMINI_API_KEY")
    pixabay_key = os.getenv("PIXABAY_API_KEY")
    
    if not gemini_key:
        print("\n==========================================")
        print(" [오류] GEMINI_API_KEY 설정이 완료되지 않았습니다!")
        print("==========================================")
        print("프로젝트 루트 폴더의 '.env' 파일을 메모장 등으로 열고")
        print("GEMINI_API_KEY= (Google Gemini API 키 입력) 값을 채워주세요.")
        print("==========================================\n")
        return
        
    if not pixabay_key:
        print("\n==========================================")
        print(" [알림] PIXABAY_API_KEY가 설정되지 않았습니다.")
        print(" 실제 동영상 검색 대신 씬 단색 배경 비디오를 생성하여 테스트를 진행합니다.")
        print("==========================================\n")
        
    # Command-line arguments setup
    parser = argparse.ArgumentParser(description="Tennis Blog to Video Automation Pipeline")
    parser.add_argument(
        "--file", 
        type=str, 
        help="Path to the blog text file (.txt) to convert"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default="output_video.mp4", 
        help="Target output filename for the MP4 video (default: output_video.mp4)"
    )
    args = parser.parse_args()
    
    # Load text content
    blog_text = ""
    if args.file:
        if os.path.exists(args.file):
            print(f"Reading blog post content from file: {args.file}")
            with open(args.file, "r", encoding="utf-8") as f:
                blog_text = f.read().strip()
        else:
            print(f"[오류] 파일이 존재하지 않습니다: {args.file}")
            return
    else:
        print("No input file provided via --file. Running with the default sample tennis blog post...")
        blog_text = DEFAULT_SAMPLE_BLOG
        
    print("\n------------------------------------------")
    print(" INPUT BLOG TEXT:")
    print("------------------------------------------")
    print(blog_text)
    print("------------------------------------------\n")
    
    try:
        # Step 1: LLM text analysis & scene composition
        print("[Step 1] Analyzing blog text and splitting into scenes using Gemini LLM...")
        try:
            scenes = analyze_blog_post(blog_text)
            print(f"--> Successfully partitioned text into {len(scenes)} scenes.")
        except Exception as e:
            print(f"\n[알림] Gemini API 호출 실패 (이유: {e}).")
            print(" 문장 단위 분할 기반의 플레이스홀더 씬 데이터로 자동 대체하여 테스트를 진행합니다.")
            import re
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', blog_text.strip()) if s.strip()]
            scenes = []
            tennis_keywords = ["tennis rally", "tennis serve", "tennis court", "tennis player", "tennis racket", "tennis ball close up"]
            for idx, sentence in enumerate(sentences):
                kw = tennis_keywords[idx % len(tennis_keywords)]
                scenes.append({
                    "keyword": kw,
                    "narration": sentence,
                    "subtitle": sentence
                })
            print(f"--> 임시 생성된 {len(scenes)}개의 씬으로 진행합니다.")
        
        # Step 2: Automated video composition
        print("\n[Step 2] Processing scenes (TTS + Video Download + Crop/Loop + Subtitles + Transitions)...")
        temp_dir = "./temp"
        build_final_video(scenes, args.output, temp_dir)
        
        print("\n==========================================")
        print(" ★ SUCCESS: AUTOMATED VIDEO GENERATED! ★")
        print("==========================================")
        print(f"Output File: {os.path.abspath(args.output)}")
        print("==========================================\n")
        
    except Exception as e:
        print(f"\n[오류] 비디오 생성 프로세스 중 에러가 발생하였습니다: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
