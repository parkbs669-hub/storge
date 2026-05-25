import os
import random
import requests
from dotenv import load_dotenv

load_dotenv()

def get_best_video_url(videos_dict: dict) -> str | None:
    """
    Finds the best video URL from the videos dictionary.
    Prefers 1080p (width >= 1920 or height >= 1080).
    If 1080p is not available, falls back to the highest resolution available.
    """
    formats = []
    for fmt_name, fmt_info in videos_dict.items():
        if isinstance(fmt_info, dict) and 'url' in fmt_info:
            width = fmt_info.get('width', 0)
            height = fmt_info.get('height', 0)
            url = fmt_info.get('url')
            # Calculate pixel count to evaluate resolution
            resolution_pixels = width * height
            formats.append((resolution_pixels, width, height, url))
            
    if not formats:
        return None
        
    # Sort by resolution (pixel count) descending
    formats.sort(key=lambda x: x[0], reverse=True)
    
    # First, look for standard 1080p (1920x1080) or higher (like 4K)
    for _, w, h, url in formats:
        if w >= 1920 or h >= 1080:
            return url
            
    # Fallback to the largest available (which is formats[0] after sorting)
    return formats[0][3]

def search_pixabay_videos(query: str, api_key: str) -> list[dict]:
    """
    Calls the Pixabay Video API with the search query.
    """
    url = "https://pixabay.com/api/videos/"
    params = {
        "key": api_key,
        "q": query,
        "video_type": "film",
        "per_page": 20
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("hits", [])

def is_strictly_tennis(hit: dict) -> bool:
    """
    Checks if the video is strictly related to standard lawn/court tennis.
    Filters out table tennis, beach tennis, badminton, padel, and squash.
    """
    tags = [t.strip().lower() for t in hit.get("tags", "").split(",")]
    if "tennis" not in tags:
        return False
        
    # List of tags to exclude to ensure standard court tennis
    exclude_tags = [
        "table tennis", "ping pong", "squash", "beach", "sand", 
        "vacation", "badminton", "padel", "matkot", "courtroom"
    ]
    for tag in exclude_tags:
        if tag in tags:
            return False
            
    return True

def download_video_for_keyword(keyword: str, output_path: str) -> str:
    """
    Searches for and downloads a video for the given keyword.
    Includes a fallback logic that simplifies the search query if no results are found,
    eventually falling back to a general 'tennis' query if everything fails.
    """
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        print(f"--> PIXABAY_API_KEY is not set. Generating a synthetic background video as a placeholder for keyword: '{keyword}'...")
        try:
            from moviepy.editor import ColorClip
        except ImportError:
            from moviepy import ColorClip
        import hashlib
        
        # Generate a distinct color based on the keyword hash
        h = hashlib.md5(keyword.encode('utf-8')).hexdigest()
        r = int(h[0:2], 16) % 120 + 30
        g = int(h[2:4], 16) % 120 + 30
        b = int(h[4:6], 16) % 120 + 30
        color = (r, g, b)
        
        width = int(os.getenv("VIDEO_WIDTH", "1920"))
        height = int(os.getenv("VIDEO_HEIGHT", "1080"))
        
        # Create a 25-second synthetic color clip (plenty of duration to trim or loop)
        clip = ColorClip(size=(width, height), color=color, duration=25)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        clip.write_videofile(output_path, fps=24, codec="libx264", logger=None)
        clip.close()
        print(f"--> Successfully generated synthetic video: {output_path}")
        return output_path
        
    words = keyword.strip().split()
    hits = []
    
    # Try searching with successively simpler queries (removing words from the right)
    for i in range(len(words), 0, -1):
        sub_query = " ".join(words[:i])
        try:
            raw_hits = search_pixabay_videos(sub_query, api_key)
            # Strict tag filter to ensure only actual court tennis
            filtered = [h for h in raw_hits if is_strictly_tennis(h)]
            if filtered:
                hits = filtered
                print(f"Found {len(hits)} strictly tennis-tagged videos for query: '{sub_query}' (original: '{keyword}')")
                break
        except Exception as e:
            print(f"Error searching for query '{sub_query}': {e}")
            
    # If still no hits, try a hardcoded default 'tennis' and filter it
    if not hits:
        print(f"No strictly tennis-tagged videos found for '{keyword}'. Trying fallback query 'tennis'...")
        try:
            raw_hits = search_pixabay_videos("tennis", api_key)
            filtered = [h for h in raw_hits if is_strictly_tennis(h)]
            if filtered:
                hits = filtered
        except Exception as e:
            print(f"Error searching for fallback query 'tennis': {e}")
            
    if not hits:
        raise ValueError(
            f"Failed to find any strictly tennis-tagged videos on Pixabay for keyword '{keyword}' and fallback 'tennis'."
        )
        
    # Pick a video randomly from the list of hits to keep the result dynamic
    hit = random.choice(hits)
    
    # Get the best video URL
    video_url = get_best_video_url(hit.get('videos', {}))
    if not video_url:
        raise ValueError(f"No valid video URL found in Pixabay hit ID: {hit.get('id')}")
        
    print(f"Selected Video ID: {hit.get('id')} | Tags: {hit.get('tags')}")
    print(f"Downloading from URL: {video_url}")
    
    # Download the video file in chunks
    response = requests.get(video_url, stream=True)
    response.raise_for_status()
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                
    print(f"Successfully downloaded video to: {output_path}")
    return output_path

if __name__ == "__main__":
    # Quick test if run directly
    # Make sure to set PIXABAY_API_KEY in your .env or run env first
    import sys
    test_key = "tennis court top view"
    test_out = "./temp/test_video.mp4"
    print("Testing Pixabay downloader...")
    try:
        download_video_for_keyword(test_key, test_out)
        print("Success! File downloaded.")
    except Exception as e:
        print(f"Error during test: {e}")
        print("Check if PIXABAY_API_KEY is set in your .env file.")
