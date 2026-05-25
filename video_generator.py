import os
import gc
import time
import math
import asyncio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import edge_tts
from dotenv import load_dotenv

# Try importing MoviePy and detect if it is v1.x or v2.x
try:
    # MoviePy v1.x Imports
    from moviepy.editor import (
        VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, 
        CompositeAudioClip, concatenate_videoclips
    )
    from moviepy.video.fx.all import crop
    
    def apply_resize(clip, target_width: int, target_height: int):
        return clip.resize(new_size=(target_width, target_height))
        
    def apply_crop(clip, target_width: int, target_height: int):
        return crop(
            clip, 
            x_center=clip.w // 2, 
            y_center=clip.h // 2, 
            width=target_width, 
            height=target_height
        )
        
    def apply_crossfadein(clip, duration: float):
        return clip.crossfadein(duration)
        
    def apply_subclip(clip, start_time: float, end_time: float):
        return clip.subclip(start_time, end_time)
        
except ImportError:
    # MoviePy v2.x Imports
    from moviepy import (
        VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, 
        CompositeAudioClip, concatenate_videoclips
    )
    from moviepy.video.fx import Crop, CrossFadeIn
    
    def apply_resize(clip, target_width: int, target_height: int):
        return clip.resized(new_size=(target_width, target_height))
        
    def apply_crop(clip, target_width: int, target_height: int):
        return clip.with_effects([
            Crop(
                width=target_width, 
                height=target_height, 
                x_center=clip.w // 2, 
                y_center=clip.h // 2
            )
        ])
        
    def apply_crossfadein(clip, duration: float):
        return clip.with_effects([CrossFadeIn(duration)])
        
    def apply_subclip(clip, start_time: float, end_time: float):
        return clip.subclipped(start_time, end_time)

# Version agnostic wrapper setters for MoviePy clips (v2.x uses "with_", v1.x uses "set_")
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


load_dotenv()

def generate_tts_audio(text: str, output_path: str, voice: str = "ko-KR-SunHiNeural") -> float:
    """
    Generates Korean TTS audio file using edge-tts and returns its duration in seconds.
    """
    async def _generate():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        
    # Run async function in synchronous wrapper
    asyncio.run(_generate())
    
    # Read duration using AudioFileClip
    with AudioFileClip(output_path) as audio:
        return audio.duration

def wrap_text_korean(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """
    Wraps Korean text character-by-character to fit within max_width,
    ensuring neat presentation without hanging characters.
    """
    lines = []
    current_line = ""
    for char in text:
        # Prevent leading spaces in wrapped lines
        if not current_line and char == " ":
            continue
        test_line = current_line + char
        if hasattr(font, 'getbbox'):
            w = font.getbbox(test_line)[2]
        else:
            w = font.getsize(test_line)[0]
            
        if w <= max_width:
            current_line = test_line
        else:
            lines.append(current_line.strip())
            current_line = char
            
    if current_line:
        lines.append(current_line.strip())
        
    return "\n".join(lines)

def create_subtitle_frame(
    text: str, 
    width: int, 
    height: int, 
    font_path: str, 
    font_size: int, 
    box_color_rgba: tuple[int, int, int, int], 
    text_color_rgba: tuple[int, int, int, int]
) -> np.ndarray:
    """
    Generates a full-sized transparent RGBA frame with wrapped subtitle centered inside
    a semi-transparent box near the bottom. Returns a numpy array.
    """
    # Create transparent base image
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Load system or custom font
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception as e:
        print(f"Warning: Could not load font '{font_path}'. Falling back to PIL default font. Error: {e}")
        font = ImageFont.load_default()
        
    # Wrap text to fit (leave 200px margins on both sides)
    max_text_width = width - 400
    wrapped_text = wrap_text_korean(text, font, max_text_width)
    lines = wrapped_text.split('\n')
    
    # Calculate line heights and widths
    line_heights = []
    max_w = 0
    for line in lines:
        if hasattr(font, 'getbbox'):
            bbox = font.getbbox(line)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        else:
            w, h = font.getsize(line)
        max_w = max(max_w, w)
        line_heights.append(h)
        
    spacing = 10
    total_h = sum(line_heights) + spacing * (len(lines) - 1)
    
    # Box dimensions with inner padding
    box_padding_x = 30
    box_padding_y = 20
    box_w = max_w + box_padding_x * 2
    box_h = total_h + box_padding_y * 2
    
    # Centered horizontally, 100px from the bottom
    box_x1 = (width - box_w) // 2
    box_y1 = height - box_h - 100
    box_x2 = box_x1 + box_w
    box_y2 = box_y1 + box_h
    
    # Draw rounded rectangle if available, fallback to regular rectangle
    try:
        draw.rounded_rectangle([box_x1, box_y1, box_x2, box_y2], radius=15, fill=box_color_rgba)
    except AttributeError:
        draw.rectangle([box_x1, box_y1, box_x2, box_y2], fill=box_color_rgba)
        
    # Draw individual text lines centered inside the box
    current_y = box_y1 + box_padding_y
    for i, line in enumerate(lines):
        if hasattr(font, 'getbbox'):
            w = font.getbbox(line)[2]
        else:
            w = font.getsize(line)[0]
        # Align line to center of the box
        line_x = box_x1 + box_padding_x + (max_w - w) // 2
        draw.text((line_x, current_y), line, fill=text_color_rgba, font=font)
        current_y += line_heights[i] + spacing
        
    return np.array(image)

def resize_and_crop(clip, target_width: int, target_height: int):
    """
    Resizes and crops a VideoFileClip to fill the target size without black bars.
    Crops excess from the center.
    """
    w, h = clip.size
    if w == target_width and h == target_height:
        return clip
        
    target_aspect = target_width / target_height
    aspect = w / h
    
    if aspect > target_aspect:
        # Clip is too wide -> resize based on height, crop width
        new_h = target_height
        new_w = int(w * (target_height / h))
        resized_clip = apply_resize(clip, new_w, new_h)
        cropped_clip = apply_crop(resized_clip, target_width, target_height)
    else:
        # Clip is too tall -> resize based on width, crop height
        new_w = target_width
        new_h = int(h * (target_width / w))
        resized_clip = apply_resize(clip, new_w, new_h)
        cropped_clip = apply_crop(resized_clip, target_width, target_height)
        
    return cropped_clip

def build_final_video(
    scenes_data: list[dict], 
    output_video_path: str, 
    temp_dir: str = "./temp"
):
    """
    Combines TTS audio, background video downloading, cropping/looping, and subtitles
    to build the final merged video.
    """
    from media_downloader import download_video_for_keyword
    
    os.makedirs(temp_dir, exist_ok=True)
    
    # Load configuration
    width = int(os.getenv("VIDEO_WIDTH", "1920"))
    height = int(os.getenv("VIDEO_HEIGHT", "1080"))
    fps = int(os.getenv("VIDEO_FPS", "24"))
    transition_duration = float(os.getenv("TRANSITION_DURATION", "1.0"))
    voice = os.getenv("TTS_VOICE", "ko-KR-SunHiNeural")
    font_path = os.getenv("SUBTITLE_FONT_PATH", "C:\\Windows\\Fonts\\malgun.ttf")
    font_size = int(os.getenv("SUBTITLE_FONT_SIZE", "36"))
    
    def parse_rgba_string(rgba_str: str, default: tuple) -> tuple:
        try:
            return tuple(map(int, rgba_str.split(',')))
        except Exception:
            return default
            
    box_color = parse_rgba_string(os.getenv("SUBTITLE_BOX_COLOR"), (0, 0, 0, 150))
    text_color = parse_rgba_string(os.getenv("SUBTITLE_TEXT_COLOR"), (255, 255, 255, 255))
    
    video_clips = []
    audio_clips = []
    subtitle_clips = []
    temp_files = []
    raw_video_clips = []
    
    current_time = 0.0
    num_scenes = len(scenes_data)
    
    try:
        for i, scene in enumerate(scenes_data):
            keyword = scene["keyword"]
            narration = scene["narration"]
            subtitle = scene["subtitle"]
            
            print(f"\n==========================================")
            print(f" PROCESSING SCENE {i+1} / {num_scenes}")
            print(f"==========================================")
            print(f"Keyword: {keyword}")
            print(f"Narration: {narration}")
            print(f"Subtitle: {subtitle}")
            
            # 1. Generate Voiceover Audio (TTS)
            tts_path = os.path.join(temp_dir, f"tts_{i}.mp3")
            temp_files.append(tts_path)
            duration = generate_tts_audio(narration, tts_path, voice)
            print(f"--> Generated TTS Duration: {duration:.2f}s")
            
            # 2. Download Background Video
            video_path = os.path.join(temp_dir, f"video_{i}.mp4")
            temp_files.append(video_path)
            download_video_for_keyword(keyword, video_path)
            
            # Calculate the video track duration required for this scene
            # (Last scene doesn't need transition padding)
            scene_visual_duration = duration
            if i < num_scenes - 1:
                scene_visual_duration += transition_duration
                
            print(f"--> Required Visual Duration: {scene_visual_duration:.2f}s")
            
            # 3. Load and Format Video Clip
            raw_video = VideoFileClip(video_path).without_audio()
            raw_video_clips.append(raw_video)
            # Aspect ratio check, center-crop, resize
            processed_video = resize_and_crop(raw_video, width, height)
            
            # Temporal alignment (trim or loop)
            if processed_video.duration >= scene_visual_duration:
                scene_video = apply_subclip(processed_video, 0, scene_visual_duration)
            else:
                # Loop video by concatenating multiple instances
                n_loops = int(math.ceil(scene_visual_duration / processed_video.duration))
                print(f"--> Video is too short ({processed_video.duration:.2f}s). Looping {n_loops} times.")
                loop_clip = concatenate_videoclips([processed_video] * n_loops)
                scene_video = apply_subclip(loop_clip, 0, scene_visual_duration)
                
            # (Intermediate close calls removed; all raw clips are closed after composition rendering)
                
            # Set timing and position inside composition
            scene_video = set_clip_start(scene_video, current_time)
            scene_video = set_clip_duration(scene_video, scene_visual_duration)
            if i > 0:
                scene_video = apply_crossfadein(scene_video, transition_duration)
                
            video_clips.append(scene_video)
            
            # 4. Add Audio Track
            scene_audio = AudioFileClip(tts_path)
            scene_audio = set_clip_start(scene_audio, current_time)
            scene_audio = set_clip_duration(scene_audio, duration)
            audio_clips.append(scene_audio)
            
            # 5. Create Subtitle Overlay Clip
            sub_frame = create_subtitle_frame(
                subtitle, width, height, font_path, font_size, box_color, text_color
            )
            # Image is already full screen dimensions, so center position places it correctly
            sub_clip = ImageClip(sub_frame)
            sub_clip = set_clip_start(sub_clip, current_time)
            sub_clip = set_clip_duration(sub_clip, duration)
            sub_clip = set_clip_position(sub_clip, ("center", "center"))
            subtitle_clips.append(sub_clip)
            
            # Advance start time of next scene by audio duration
            current_time += duration
            
        print("\n==========================================")
        print(" RENDERING FINAL COMPOSITE")
        print("==========================================")
        
        # Subtitles lay on top of video tracks
        final_video_clips = video_clips + subtitle_clips
        
        final_video = CompositeVideoClip(final_video_clips, size=(width, height))
        final_audio = CompositeAudioClip(audio_clips)
        final_video = set_clip_audio(final_video, final_audio)
        
        # Render the file
        print(f"Writing output file to: {output_video_path}")
        final_video.write_videofile(
            output_video_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=os.path.join(temp_dir, "temp-audio.m4a"),
            remove_temp=True
        )
        
        # Close all open handles
        final_video.close()
        final_audio.close()
        for clip in video_clips:
            clip.close()
        for clip in audio_clips:
            clip.close()
        for clip in subtitle_clips:
            clip.close()
        for clip in raw_video_clips:
            clip.close()
            
        print("\nRendering completed successfully!")
        
    finally:
        # Cleanup temporary files (Garbage collect & sleep to prevent Windows permission/file lock issues)
        print("\n==========================================")
        print(" CLEANING UP TEMPORARY FILES")
        print("==========================================")
        gc.collect()
        time.sleep(1.5)
        
        for file in temp_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    print(f"Successfully deleted: {file}")
                except Exception as e:
                    print(f"Could not delete temporary file '{file}': {e}")
                    
        # Remove temp directory if empty
        try:
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
                print(f"Removed temp directory: {temp_dir}")
        except Exception as e:
            print(f"Could not remove temp directory: {e}")
            
if __name__ == "__main__":
    # Test stub
    print("Testing Video Generator module layout...")
    # Requires setup with mock parameters to run fully
