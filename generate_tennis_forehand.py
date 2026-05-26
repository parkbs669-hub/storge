#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_tennis_forehand.py - 테니스 포핸드 스윙 졸라맨 애니메이션 생성기
- 노박 조코비치 실제 포핸드 영상 모션 캡처 데이터 적용 (MediaPipe Pose 기반)
- 화이트보드 마커 드로잉 스타일 적용 (흰 배경에 검은 잉크)
- 물리 공식을 통한 바운드 및 임팩트 궤적 구현
- 1080x1920 세로형 비디오 (유튜브 쇼츠 최적화)
"""

import os
import sys
import math
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

try:
    from moviepy.editor import ImageSequenceClip
except ImportError:
    from moviepy.video.io.ImageSequenceClip import ImageSequenceClip

load_dotenv()

WIDTH = 1080
HEIGHT = 1920
FPS = 30
TOTAL_FRAMES = 180
OUTPUT_PATH = "tennis_forehand_pro.mp4"

# --- 모션 캡처 데이터 로드 ---
POSE_DATA_PATH = r"c:\Users\bagch\Downloads\text_to_video_project\user_videos\pose_data_bottom.json"

if not os.path.exists(POSE_DATA_PATH):
    print(f"[오류] 모션 캡처 데이터 파일을 찾을 수 없습니다: {POSE_DATA_PATH}")
    sys.exit(1)

with open(POSE_DATA_PATH, 'r') as f:
    POSE_DATA = json.load(f)
POSE_FRAMES = POSE_DATA["frames"]

def get_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# --- 시간별 랜드마크 보간 함수 ---
def get_landmarks_at_time(t_video):
    idx_low = int(math.floor(t_video))
    idx_high = int(math.ceil(t_video))
    
    idx_low = max(0, min(len(POSE_FRAMES) - 1, idx_low))
    idx_high = max(0, min(len(POSE_FRAMES) - 1, idx_high))
    
    lms_low = POSE_FRAMES[idx_low]["landmarks"]
    lms_high = POSE_FRAMES[idx_high]["landmarks"]
    
    if not lms_low or not lms_high:
        # 유효한 프레임 검색
        for offset in range(1, 30):
            test_idx = max(0, min(len(POSE_FRAMES) - 1, idx_low - offset))
            if POSE_FRAMES[test_idx]["landmarks"]:
                return POSE_FRAMES[test_idx]["landmarks"]
            test_idx = max(0, min(len(POSE_FRAMES) - 1, idx_high + offset))
            if POSE_FRAMES[test_idx]["landmarks"]:
                return POSE_FRAMES[test_idx]["landmarks"]
        return None
        
    if idx_low == idx_high:
        return lms_low
        
    alpha = t_video - idx_low
    
    lms_interp = {}
    for key in lms_low.keys():
        if key in lms_high:
            p_low = lms_low[key]
            p_high = lms_high[key]
            lms_interp[key] = {
                "x": p_low["x"] + (p_high["x"] - p_low["x"]) * alpha,
                "y": p_low["y"] + (p_high["y"] - p_low["y"]) * alpha,
                "z": p_low["z"] + (p_high["z"] - p_low["z"]) * alpha
            }
    return lms_interp

# --- 모션 캡처 기반 졸라맨 좌표 계산 함수 ---
def get_captured_joints(frame_idx, stickman_x, stickman_y, char_scale):
    # 애니메이션 프레임(0-180)을 비디오 프레임(100-180, 조코비치 스윙 루프)으로 매핑
    # 임팩트를 프레임 100에 맞추기 위해 구간별 선형 매핑 적용
    # - 0 ~ 100 프레임: 비디오 100 ~ 123 프레임 (백스윙 및 다운스윙)
    # - 100 ~ 180 프레임: 비디오 123 ~ 180 프레임 (팔로우 스루 및 피니시)
    if frame_idx <= 100:
        t_video = 100.0 + frame_idx * (123.0 - 100.0) / 100.0
    else:
        t_video = 123.0 + (frame_idx - 100.0) * (180.0 - 123.0) / 80.0
        
    lms = get_landmarks_at_time(t_video)
    if not lms:
        return None
        
    l_sh = np.array([lms["11"]["x"], lms["11"]["y"]])
    r_sh = np.array([lms["12"]["x"], lms["12"]["y"]])
    l_el = np.array([lms["13"]["x"], lms["13"]["y"]])
    r_el = np.array([lms["14"]["x"], lms["14"]["y"]])
    l_wr = np.array([lms["15"]["x"], lms["15"]["y"]])
    r_wr = np.array([lms["16"]["x"], lms["16"]["y"]])
    l_hp = np.array([lms["23"]["x"], lms["23"]["y"]])
    r_hp = np.array([lms["24"]["x"], lms["24"]["y"]])
    l_kn = np.array([lms["25"]["x"], lms["25"]["y"]])
    r_kn = np.array([lms["26"]["x"], lms["26"]["y"]])
    l_ak = np.array([lms["27"]["x"], lms["27"]["y"]])
    r_ak = np.array([lms["28"]["x"], lms["28"]["y"]])
    nose = np.array([lms["0"]["x"], lms["0"]["y"]])
    r_idx = np.array([lms["20"]["x"], lms["20"]["y"]])
    
    # 신체 기준점 계산
    hip_center = (l_hp + r_hp) / 2.0
    neck = (l_sh + r_sh) / 2.0
    torso_len_video = get_distance(hip_center, neck)
    if torso_len_video == 0:
        torso_len_video = 0.1
        
    # 타겟 크기로 스케일링
    target_torso_len = 100.0 * char_scale
    scale = target_torso_len / torso_len_video
    
    # 2D 좌표 리타게팅
    def map_joint(v_pos):
        rel = v_pos - hip_center
        # 화면의 net_x 방향(오른쪽)으로 스윙을 연결하기 위해
        # x좌표의 relative 오프셋 방향을 유지
        return (stickman_x + rel[0] * scale, stickman_y + rel[1] * scale)
        
    joints = {
        "hip": (stickman_x, stickman_y),
        "neck": map_joint(neck),
        "head": map_joint(nose),
        "l_elbow": map_joint(l_el),
        "l_wrist": map_joint(l_wr),
        "r_elbow": map_joint(r_el),
        "r_wrist": map_joint(r_wr),
        "l_knee": map_joint(l_kn),
        "l_ankle": map_joint(l_ak),
        "r_knee": map_joint(r_kn),
        "r_ankle": map_joint(r_ak),
        "head_r": 25.0 * char_scale,
        "racket_len": 70.0 * char_scale
    }
    
    # 라켓 각도 계산 (손목 -> 검지 방향 벡터 활용)
    racket_dx = r_idx[0] - r_wr[0]
    racket_dy = r_wr[1] - r_idx[1]
    joints["racket_rad"] = math.atan2(racket_dy, racket_dx)
    
    return joints

# --- 코칭 팁 상태 확인 함수 ---
def get_captured_phase_text(frame_idx):
    if frame_idx <= 40:
        return "1. 준비 자세 (Ready)"
    elif frame_idx <= 75:
        return "2. 백스윙 (Backswing)"
    elif frame_idx <= 90:
        return "3. 라켓 드롭 (Racket Drop)"
    elif frame_idx <= 110:
        return "4. 임팩트 (Impact)"
    elif frame_idx <= 150:
        return "5. 팔로우 스루 (Follow Through)"
    else:
        return "6. 피니시 (Finish)"

# --- 시스템 폰트 탐색 함수 ---
def get_system_font(size):
    font_paths = [
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothicBold.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    ]
    for path in font_paths:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

# --- 라켓 이미지 템플릿 생성 ---
def create_racket_template(scale):
    w = int(180 * scale * 2)
    h = int(180 * scale * 2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    
    handle_len = 50 * scale * 2
    head_w = 26 * scale * 2
    head_h = 35 * scale * 2
    
    draw.line([(cx, cy), (cx, cy + handle_len)], fill=(0, 0, 0, 255), width=int(6 * scale * 2))
    
    head_cy = cy - head_h / 2
    draw.ellipse([cx - head_w, head_cy - head_h, cx + head_w, head_cy + head_h], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=int(5 * scale * 2))
    
    for y_offset in range(-int(head_h) + 10, int(head_h), int(10 * scale * 2)):
        draw.line([cx - head_w + 5, head_cy + y_offset, cx + head_w - 5, head_cy + y_offset], fill=(0, 0, 0, 150), width=int(1.5 * scale * 2))
    for x_offset in range(-int(head_w) + 10, int(head_w), int(10 * scale * 2)):
        draw.line([cx + x_offset, head_cy - head_h + 5, cx + x_offset, head_cy + head_h - 5], fill=(0, 0, 0, 150), width=int(1.5 * scale * 2))
        
    return img

def paste_rotated_racket(canvas, racket_img, wrist_x, wrist_y, racket_rad, scale):
    angle_deg = math.degrees(racket_rad) - 90
    rotated = racket_img.rotate(angle_deg, resample=Image.Resampling.BICUBIC, expand=True)
    
    cx = racket_img.width / 2
    cy = racket_img.height / 2
    handle_len = 50 * scale * 2
    pivot_x = cx
    pivot_y = cy + handle_len
    
    dx_orig = pivot_x - cx
    dy_orig = pivot_y - cy
    
    rad = math.radians(angle_deg)
    dx = dx_orig * math.cos(rad) + dy_orig * math.sin(rad)
    dy = -dx_orig * math.sin(rad) + dy_orig * math.cos(rad)
    
    rot_cx = rotated.width / 2
    rot_cy = rotated.height / 2
    rot_pivot_x = rot_cx + dx
    rot_pivot_y = rot_cy + dy
    
    paste_x = int(wrist_x - rot_pivot_x)
    paste_y = int(wrist_y - rot_pivot_y)
    
    canvas.paste(rotated, (paste_x, paste_y), rotated)

# --- 메인 애니메이션 연산 및 비디오 생성 ---
def build_tennis_video():
    print(f"[Start] Djokovic Forehand Animation rendering started (Resolution: {WIDTH}x{HEIGHT}, FPS: {FPS})")
    
    scale_factor = HEIGHT / 1920.0
    char_scale = scale_factor * 2.2
    
    ground_y = int(HEIGHT * 0.72)
    stickman_x = int(WIDTH * 0.35)
    stickman_y = ground_y - int(130 * char_scale)
    
    net_x = int(WIDTH * 0.76)
    net_height = int(140 * scale_factor)
    net_top_y = ground_y - net_height
    
    ball_radius = int(14 * scale_factor * 1.5)
    racket_template = create_racket_template(char_scale)
    
    gravity = 0.18 * scale_factor
    
    # --- 1단계: 임팩트(Frame 100)의 스위트 스폿 추출 ---
    impact_joints = get_captured_joints(100, stickman_x, stickman_y, char_scale)
    
    impact_racket_len = impact_joints["racket_len"]
    impact_racket_rad = impact_joints["racket_rad"]
    r_wrist_x, r_wrist_y = impact_joints["r_wrist"]
    racket_sweet_spot_x = r_wrist_x + (impact_racket_len * 0.75) * math.cos(impact_racket_rad)
    racket_sweet_spot_y = r_wrist_y - (impact_racket_len * 0.75) * math.sin(impact_racket_rad)
    
    # --- 2단계: 공의 물리 파라미터 역계산 ---
    # 공은 프레임 0에 시작하여, 프레임 50에 바운드하고, 프레임 100에 sweet spot에 도착
    ball_start_x = WIDTH * 0.9
    dt = 50.0
    e = 0.65
    f = 0.82
    
    # X축 속도 역계산
    bounce_x = (racket_sweet_spot_x + f * ball_start_x) / (1 + f)
    ball_vx_start = (bounce_x - ball_start_x) / dt
    
    # Y축 속도 역계산
    term = ground_y - racket_sweet_spot_y + 0.5 * (1.0 - e) * gravity * (dt ** 2)
    ball_start_y = ground_y - term / e
    ball_vy_start = (ground_y - ball_start_y - 0.5 * gravity * (dt ** 2)) / dt
    
    # --- 3단계: 프레임 루프 시뮬레이션 ---
    ball_history = []
    ball_x, ball_y = ball_start_x, ball_start_y
    ball_vx, ball_vy = ball_vx_start, ball_vy_start
    is_ball_hit = False
    
    simulated_positions = []
    for frame in range(TOTAL_FRAMES):
        joints = get_captured_joints(frame, stickman_x, stickman_y, char_scale)
        phase_text = get_captured_phase_text(frame)
        
        # 물리 업데이트
        if frame > 100:
            ball_vy += gravity
            ball_x += ball_vx
            ball_y += ball_vy
            
            # 네트 충돌
            net_x_2d = net_x
            if (ball_x - ball_vx) < net_x_2d <= ball_x:
                if ball_y > net_top_y:
                    ball_x = net_x_2d
                    ball_vx = -ball_vx * 0.08
                    ball_vy = 2.0 * scale_factor
            
            # 지면 충돌
            if ball_y >= ground_y - ball_radius:
                ball_y = ground_y - ball_radius
                ball_vy = -ball_vy * 0.65
                ball_vx *= 0.82
        elif frame == 100:
            ball_x, ball_y = racket_sweet_spot_x, racket_sweet_spot_y
            ball_vx = 26.0 * scale_factor
            ball_vy = -4.0 * scale_factor
            is_ball_hit = True
        else:
            ball_vy += gravity
            ball_x += ball_vx
            ball_y += ball_vy
            
            # 바운드 처리
            if ball_y >= ground_y - ball_radius:
                ball_y = ground_y - ball_radius
                ball_vy = -ball_vy * e
                ball_vx = ball_vx * f
                
        simulated_positions.append({
            "frame": frame,
            "phase_text": phase_text,
            "joints": joints,
            "ball": (ball_x, ball_y),
            "is_ball_hit": is_ball_hit
        })
        
    # --- 4단계: 이미지 프레임 렌더링 ---
    frames_buffer = []
    font = get_system_font(int(45 * scale_factor))
    font_sub = get_system_font(int(30 * scale_factor))
    
    for f_idx, state in enumerate(simulated_positions):
        frame = state["frame"]
        phase_text = state["phase_text"]
        joints = state["joints"]
        bx, by = state["ball"]
        
        canvas_w, canvas_h = WIDTH * 2, HEIGHT * 2
        img = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        s2 = scale_factor * 2
        
        # 1. 지면
        ground_y2 = ground_y * 2
        draw.line([(0, ground_y2), (canvas_w, ground_y2)], fill=(40, 40, 40, 255), width=int(5 * s2))
        
        # 2. 코트 라인
        court_color = (120, 130, 140, 255)
        draw.line([(int(WIDTH * 0.05 * 2), ground_y2), (int(WIDTH * 0.05 * 2), canvas_h)], fill=court_color, width=int(4 * s2))
        draw.line([(int(WIDTH * 0.4 * 2), ground_y2), (int(WIDTH * 0.4 * 2), canvas_h)], fill=court_color, width=int(3 * s2))
        
        # 3. 네트
        net_x2 = net_x * 2
        net_top_y2 = net_top_y * 2
        draw.rectangle([net_x2 - int(5 * s2), net_top_y2 - int(12 * s2), net_x2 + int(5 * s2), ground_y2], fill=(240, 240, 240, 255), outline=(0, 0, 0, 255), width=int(3 * s2))
        
        mesh_step = int(8 * s2)
        for nx in range(net_x2, canvas_w, mesh_step):
            draw.line([(nx, net_top_y2), (nx, ground_y2)], fill=(150, 150, 150, 100), width=1)
        for ny in range(net_top_y2, ground_y2, mesh_step):
            draw.line([(net_x2, ny), (canvas_w, ny)], fill=(150, 150, 150, 100), width=1)
        draw.rectangle([net_x2, net_top_y2, canvas_w, net_top_y2 + int(8 * s2)], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=int(2 * s2))
        
        # 4. 졸라맨 그리기
        j2 = {k: (v[0] * 2, v[1] * 2) if isinstance(v, tuple) else v * 2 for k, v in joints.items()}
        s_char = char_scale * 2
        lw = int(8 * s_char)
        
        ink_color = (0, 0, 0, 255)
        fill_color = (255, 255, 255, 255)
        
        # 다리
        draw.line([j2["hip"], j2["l_knee"]], fill=ink_color, width=lw)
        draw.line([j2["l_knee"], j2["l_ankle"]], fill=ink_color, width=lw)
        draw.line([j2["hip"], j2["r_knee"]], fill=ink_color, width=lw)
        draw.line([j2["r_knee"], j2["r_ankle"]], fill=ink_color, width=lw)
        
        # 몸통
        draw.line([j2["hip"], j2["neck"]], fill=ink_color, width=lw)
        
        # 팔
        draw.line([j2["neck"], j2["l_elbow"]], fill=ink_color, width=lw)
        draw.line([j2["l_elbow"], j2["l_wrist"]], fill=ink_color, width=lw)
        draw.line([j2["neck"], j2["r_elbow"]], fill=ink_color, width=lw)
        draw.line([j2["r_elbow"], j2["r_wrist"]], fill=ink_color, width=lw)
        
        # 머리
        head_cx, head_cy = j2["head"]
        hr = j2["head_r"] * 1.1
        draw.ellipse([head_cx - hr, head_cy - hr, head_cx + hr, head_cy + hr], fill=fill_color, outline=ink_color, width=int(4 * s_char))
        
        # 관절 구체
        for joint_key in ["hip", "neck", "l_elbow", "r_elbow", "l_knee", "r_knee"]:
            jx, jy = j2[joint_key]
            jr = lw // 2
            draw.ellipse([jx - jr, jy - jr, jx + jr, jy + jr], fill=ink_color)
            
        # 손/발
        l_ax, l_ay = j2["l_ankle"]
        draw.ellipse([l_ax - int(12 * s_char), l_ay - int(4 * s_char), l_ax + int(24 * s_char), l_ay + int(4 * s_char)], fill=ink_color)
        r_ax, r_ay = j2["r_ankle"]
        draw.ellipse([r_ax - int(12 * s_char), r_ay - int(4 * s_char), r_ax + int(24 * s_char), r_ay + int(4 * s_char)], fill=ink_color)
        
        for wrist_key in ["l_wrist", "r_wrist"]:
            jx, jy = j2[wrist_key]
            jr = int(7 * s_char)
            draw.ellipse([jx - jr, jy - jr, jx + jr, jy + jr], fill=ink_color)
            
        # 라켓
        paste_rotated_racket(img, racket_template, j2["r_wrist"][0], j2["r_wrist"][1], joints["racket_rad"], char_scale)
        
        # 5. 잔상
        ball_history.append((bx * 2, by * 2))
        if len(ball_history) > 10:
            ball_history.pop(0)
            
        for idx, (hx, hy) in enumerate(ball_history[:-1]):
            trail_ratio = (idx + 1) / len(ball_history)
            trail_r = int(ball_radius * 2 * (0.3 + 0.7 * trail_ratio))
            draw.ellipse([hx - trail_r, hy - trail_r, hx + trail_r, hy + trail_r], fill=(230, 255, 0, int(100 * trail_ratio)))
            
        # 6. 공
        bx2, by2 = bx * 2, by * 2
        br2 = ball_radius * 2
        draw.ellipse([bx2 - br2, by2 - br2, bx2 + br2, by2 + br2], fill=(220, 255, 0, 255), outline=ink_color, width=int(2.5 * s2))
        
        # 7. 임팩트 특수 효과
        if 100 <= frame <= 110:
            impact_progress = (frame - 100) / 10.0
            spark_start = int(25 * scale_factor * 2 * impact_progress)
            spark_end = int(120 * scale_factor * 2 * impact_progress)
            wrist_x, wrist_y = j2["r_wrist"]
            for angle in range(0, 360, 45):
                rad_sp = math.radians(angle)
                x1 = wrist_x + spark_start * math.cos(rad_sp)
                y1 = wrist_y - spark_start * math.sin(rad_sp)
                x2 = wrist_x + spark_end * math.cos(rad_sp)
                y2 = wrist_y - spark_end * math.sin(rad_sp)
                draw.line([(x1, y1), (x2, y2)], fill=ink_color, width=int(3 * s2))
                
        # 8. 텍스트 레이블 및 코칭 팁 박스
        draw.text((int(60 * 2), int(80 * 2)), phase_text, font=font, fill=ink_color)
        
        box_y = int(HEIGHT * 0.8 * 2)
        box_h = int(140 * scale_factor * 2)
        
        shadow_offset = int(7 * s2)
        draw.rectangle([int(WIDTH * 0.1 * 2) + shadow_offset, box_y + shadow_offset, int(WIDTH * 0.9 * 2) + shadow_offset, box_y + box_h + shadow_offset], fill=(40, 40, 40, 255))
        draw.rectangle([int(WIDTH * 0.1 * 2), box_y, int(WIDTH * 0.9 * 2), box_y + box_h], fill=(255, 255, 255, 255), outline=ink_color, width=int(3.5 * s2))
        
        tips = {
            "1. 준비 자세 (Ready)": "라켓을 몸 앞에 두고 상대편 공에 집중합니다.",
            "2. 백스윙 (Backswing)": "어깨와 골반을 돌려 라켓을 뒤로 크게 가져갑니다.",
            "3. 라켓 드롭 (Racket Drop)": "탑스핀을 위해 라켓을 공보다 낮은 위치로 떨어뜨립니다.",
            "4. 임팩트 (Impact)": "공을 몸 앞쪽에서 맞추며 손목 각도를 유지합니다.",
            "5. 팔로우 스루 (Follow Through)": "라켓을 반대편 어깨 너머로 휘둘러 스윙을 마무리합니다.",
            "6. 피니시 (Finish)": "동작을 완료하고 원래 준비 자세로 매끄럽게 복귀합니다."
        }
        tip_text = tips.get(phase_text, "")
        draw.text((int(WIDTH * 0.15 * 2), box_y + int(30 * scale_factor * 2)), "💡 코칭 팁:", font=font_sub, fill=(230, 160, 0, 255))
        draw.text((int(WIDTH * 0.15 * 2), box_y + int(75 * scale_factor * 2)), tip_text, font=font_sub, fill=ink_color)
        
        frame_img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        frames_buffer.append(np.array(frame_img.convert("RGB")))
        
        if (f_idx + 1) % 30 == 0:
            print(f"   [렌더링 진행도] {f_idx + 1} / {TOTAL_FRAMES} 프레임 처리 완료...")
            
    print("[Synthesize] Compiling MP4 video...")
    clip = ImageSequenceClip(frames_buffer, fps=FPS)
    clip.write_videofile(
        OUTPUT_PATH,
        codec="libx264",
        audio=False,
        threads=4,
        preset="medium",
        bitrate="6000k"
    )
    clip.close()
    print(f"[Success] Video generation completed successfully! Saved to: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_tennis_video()
