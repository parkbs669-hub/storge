#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_tennis_serve.py - 테니스 서브 졸라맨 애니메이션 생성기
- 관절 각도 제어를 위한 Forward Kinematics 및 Keyframe 보간 적용
- 공의 움직임을 위한 중력 및 속도 벡터 물리 연산 적용
- 테니스 코트, 라켓, 공 잔상(Trail), 타격 임팩트 쇼크웨이브 등 프리미엄 시각 효과 적용
- Headless(화면 없음) 방식으로 Pillow 렌더링 후 MoviePy를 통해 MP4 합성 저장
"""

import os
import sys
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

# Windows 터미널 한글/이모지 출력 인코딩 오류 방지
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# MoviePy 호환 임포트
try:
    from moviepy.editor import ImageSequenceClip
except ImportError:
    from moviepy.video.io.ImageSequenceClip import ImageSequenceClip

load_dotenv()

# --- 설정값 (유튜브 쇼츠용 세로형 1080x1920 강제 지정) ---
WIDTH = 1080
HEIGHT = 1920
FPS = 30
TOTAL_FRAMES = 180  # 6초 애니메이션 (30 FPS 기준, 이전보다 천천히 재생)
OUTPUT_PATH = "tennis_serve.mp4"

# --- 테니스 서브 키프레임 정의 ---
# 각 키프레임에서의 관절 각도 (단위: 도, 0도 = 우측, 90도 = 상측, 180도 = 좌측, 270도 = 하측)
# x_offset: 활 모양(Bow) 자세 연출을 위한 골반의 X축 변화량
# y_offset: 무릎 굽힘이나 점프에 따른 골반(Hip)의 Y축 변화량
KEYFRAMES = {
    0: {   # 1. 준비 동작 (Ready)
        "torso": 90,
        "l_shoulder": -50, "l_elbow": 30,
        "r_shoulder": 240, "r_elbow": 60, "racket": -30,
        "l_hip": 270, "l_knee": 0,
        "r_hip": 270, "r_knee": 0,
        "x_offset": 0,
        "y_offset": 0,
        "phase_text": "1. 준비 자세 (Ready)"
    },
    40: {  # 2. 토스 시작 (Start Toss) - 시간 간격을 넓혀 동작을 느리게 유도
        "torso": 90,
        "l_shoulder": 50, "l_elbow": 0,     # 왼팔 수직 위로 뻗어 토스
        "r_shoulder": 220, "r_elbow": 70, "racket": -45,
        "l_hip": 270, "l_knee": 0,
        "r_hip": 270, "r_knee": 0,
        "x_offset": 0,
        "y_offset": 0,
        "phase_text": "2. 볼 토스 (Toss)"
    },
    90: {  # 3. 트로피 자세 (Trophy Pose - 무릎 깊게 굽힘, 상체 뒤로 젖혀 활 모양 몸체 완성)
        "torso": 115, # 상체 뒤로 깊게 젖힘 (Bow 형태)
        "l_shoulder": 85, "l_elbow": 0,      # 왼팔은 수직 위로 쭉 뻗어 공 지향
        "r_shoulder": 185, "r_elbow": 110, "racket": -95, # 등 뒤로 라켓 깊이 드롭 (Back Scratch)
        "l_hip": 245, "l_knee": 45,          # 깊은 무릎 굽힘
        "r_hip": 260, "r_knee": 45,
        "x_offset": 35,                      # 골반을 코트 안쪽(오른쪽)으로 35px 밀어 넣어 'D자형 활 모양' 극대화
        "y_offset": 45,                      # 깊은 무릎 굽힘으로 골반이 45px 아래로 내려감
        "phase_text": "3. 트로피 자세 (Trophy Pose)"
    },
    120: {  # 4. 임팩트 (Impact - 점프 후 최정점에서 타격)
        "torso": 80,  # 상체 앞으로 숙이며 에너지 전달
        "l_shoulder": -60, "l_elbow": 90,    # 왼팔 회수 (몸 안쪽으로 접음)
        "r_shoulder": 85, "r_elbow": 0, "racket": 0,     # 오른팔과 라켓 일직선 연장
        "l_hip": 270, "l_knee": -10,         # 다리 쭉 폄 (점프)
        "r_hip": 265, "r_knee": -10,
        "x_offset": 15,                      # 공 타격을 향해 골반 이동
        "y_offset": -50,                     # 50px 강력한 점프 업
        "phase_text": "4. 임팩트 (Impact)"
    },
    155: { # 5. 팔로우 스루 (Follow Through - 앞으로 기울여 착지)
        "torso": 70,  # 상체 크게 앞으로 숙임
        "l_shoulder": -80, "l_elbow": 90,    # 왼팔 회수 유지
        "r_shoulder": -20, "r_elbow": 80, "racket": 45,  # 라켓 스윙 피니시 궤적
        "l_hip": 250, "l_knee": 20,
        "r_hip": 290, "r_knee": 10,          # 뒷다리를 차주어 수평 균형 유지
        "x_offset": -10,
        "y_offset": 10,                      # 지면 착지
        "phase_text": "5. 팔로우 스루 (Follow Through)"
    },
    180: { # 6. 피니시 및 원위치 복귀
        "torso": 90,
        "l_shoulder": -50, "l_elbow": 30,
        "r_shoulder": -120, "r_elbow": 60, "racket": -30, # -120도는 240도와 동일하여 회전 튐(windmill) 방지
        "l_hip": 270, "l_knee": 0,
        "r_hip": 270, "r_knee": 0,
        "x_offset": 0,
        "y_offset": 0,
        "phase_text": "6. 피니시 (Finish)"
    }
}

# --- 관절 각도 선형 보간 함수 ---
def interpolate_pose(frame):
    keys = sorted(KEYFRAMES.keys())
    
    # 프레임 범위를 벗어난 경우 양 끝값 사용
    if frame <= keys[0]:
        return KEYFRAMES[keys[0]]
    if frame >= keys[-1]:
        return KEYFRAMES[keys[-1]]
    
    # 보간할 앞뒤 키프레임 찾기
    for i in range(len(keys) - 1):
        k1, k2 = keys[i], keys[i+1]
        if k1 <= frame <= k2:
            t = (frame - k1) / (k2 - k1)
            pose1, pose2 = KEYFRAMES[k1], KEYFRAMES[k2]
            
            # 각 각도 및 오프셋 보간
            interpolated = {}
            for key in pose1.keys():
                if key == "phase_text":
                    # 텍스트는 보간 비율이 높은 쪽을 사용
                    interpolated[key] = pose1[key] if t < 0.5 else pose2[key]
                else:
                    interpolated[key] = pose1[key] + (pose2[key] - pose1[key]) * t
            return interpolated

# --- 정역학 (Forward Kinematics) 기반 졸라맨 좌표 계산 ---
def get_joint_coordinates(hip_x, hip_y, pose, scale=1.0):
    # 각 신체 부위 길이 설정 (scale 적용)
    torso_len = 100 * scale
    head_r = 25 * scale
    upper_arm_len = 55 * scale
    lower_arm_len = 55 * scale
    thigh_len = 65 * scale
    shin_len = 65 * scale
    racket_len = 70 * scale
    
    # 골반 X 및 Y 오프셋 적용 (활 모양 자세 및 무릎 굽힘 제어)
    hip_x = hip_x + pose.get("x_offset", 0) * scale
    hip_y = hip_y + pose["y_offset"] * scale
    
    # 척추 각도 (라디안)
    torso_rad = math.radians(pose["torso"])
    
    # 목/어깨 위치
    neck_x = hip_x + torso_len * math.cos(torso_rad)
    neck_y = hip_y - torso_len * math.sin(torso_rad)
    
    # 머리 위치 (목에서 조금 더 척추 방향으로 올림)
    head_dist = 35 * scale
    head_x = neck_x + head_dist * math.cos(torso_rad)
    head_y = neck_y - head_dist * math.sin(torso_rad)
    
    # 1. 왼팔 (공 던지는 팔)
    l_sh_rad = math.radians(pose["l_shoulder"])
    l_elb_x = neck_x + upper_arm_len * math.cos(l_sh_rad)
    l_elb_y = neck_y - upper_arm_len * math.sin(l_sh_rad)
    
    l_wrist_rad = l_sh_rad + math.radians(pose["l_elbow"])
    l_wrist_x = l_elb_x + lower_arm_len * math.cos(l_wrist_rad)
    l_wrist_y = l_elb_y - lower_arm_len * math.sin(l_wrist_rad)
    
    # 2. 오른팔 (라켓 쥐는 팔)
    r_sh_rad = math.radians(pose["r_shoulder"])
    r_elb_x = neck_x + upper_arm_len * math.cos(r_sh_rad)
    r_elb_y = neck_y - upper_arm_len * math.sin(r_sh_rad)
    
    r_wrist_rad = r_sh_rad + math.radians(pose["r_elbow"])
    r_wrist_x = r_elb_x + lower_arm_len * math.cos(r_wrist_rad)
    r_wrist_y = r_elb_y - lower_arm_len * math.sin(r_wrist_rad)
    
    # 라켓 방향 각도
    racket_rad = r_wrist_rad + math.radians(pose["racket"])
    
    # 3. 왼다리
    l_hip_rad = math.radians(pose["l_hip"])
    l_knee_x = hip_x + thigh_len * math.cos(l_hip_rad)
    l_knee_y = hip_y - thigh_len * math.sin(l_hip_rad)
    
    l_ankle_rad = l_hip_rad + math.radians(pose["l_knee"])
    l_ankle_x = l_knee_x + shin_len * math.cos(l_ankle_rad)
    l_ankle_y = l_knee_y - shin_len * math.sin(l_ankle_rad)
    
    # 4. 오른다리
    r_hip_rad = math.radians(pose["r_hip"])
    r_knee_x = hip_x + thigh_len * math.cos(r_hip_rad)
    r_knee_y = hip_y - thigh_len * math.sin(r_hip_rad)
    
    r_ankle_rad = r_hip_rad + math.radians(pose["r_knee"])
    r_ankle_x = r_knee_x + shin_len * math.cos(r_ankle_rad)
    r_ankle_y = r_knee_y - shin_len * math.sin(r_ankle_rad)
    
    return {
        "hip": (hip_x, hip_y),
        "neck": (neck_x, neck_y),
        "head": (head_x, head_y),
        "l_elbow": (l_elb_x, l_elb_y),
        "l_wrist": (l_wrist_x, l_wrist_y),
        "r_elbow": (r_elb_x, r_elb_y),
        "r_wrist": (r_wrist_x, r_wrist_y),
        "r_ankle": (r_ankle_x, r_ankle_y),
        "l_knee": (l_knee_x, l_knee_y),
        "l_ankle": (l_ankle_x, l_ankle_y),
        "r_knee": (r_knee_x, r_knee_y),
        "r_ankle": (r_ankle_x, r_ankle_y),
        "head_r": head_r,
        "racket_rad": racket_rad,
        "racket_len": racket_len
    }

# --- 시스템 폰트 탐색 함수 ---
def get_system_font(size):
    font_paths = [
        "C:/Windows/Fonts/malgunbd.ttf",  # 맑은 고딕 Bold
        "C:/Windows/Fonts/malgun.ttf",    # 맑은 고딕 Regular
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

# --- 라켓 이미지 템플릿 생성 (2x SSAA 스케일용) ---
def create_racket_template(scale):
    w = int(180 * scale * 2)
    h = int(180 * scale * 2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    cx, cy = w // 2, h // 2
    
    handle_len = 50 * scale * 2
    head_w = 26 * scale * 2
    head_h = 35 * scale * 2
    
    # 1. 라켓 그립 & 샤프트 그리기 (검은색 잉크 펜 느낌)
    draw.line([(cx, cy), (cx, cy + handle_len)], fill=(0, 0, 0, 255), width=int(6 * scale * 2))
    
    # 2. 라켓 헤드 타원 프레임 그리기 (안에는 흰색을 채워 뒷배경 가림)
    head_cy = cy - head_h / 2
    draw.ellipse([cx - head_w, head_cy - head_h, cx + head_w, head_cy + head_h], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=int(5 * scale * 2))
    
    # 3. 라켓 거트(줄) 그리기 (얇은 검은색 격자선)
    # 가로줄
    for y_offset in range(-int(head_h) + 10, int(head_h), int(10 * scale * 2)):
        draw.line([cx - head_w + 5, head_cy + y_offset, cx + head_w - 5, head_cy + y_offset], fill=(0, 0, 0, 150), width=int(1.5 * scale * 2))
    # 세로줄
    for x_offset in range(-int(head_w) + 10, int(head_w), int(10 * scale * 2)):
        draw.line([cx + x_offset, head_cy - head_h + 5, cx + x_offset, head_cy + head_h - 5], fill=(0, 0, 0, 150), width=int(1.5 * scale * 2))
        
    return img

def paste_rotated_racket(canvas, racket_img, wrist_x, wrist_y, racket_rad, scale):
    # 라켓 기본 방향(위쪽 = 90도)에서 목표 각도로의 회전각 계산
    angle_deg = math.degrees(racket_rad) - 90
    
    # 회전 처리 (BICUBIC으로 부드럽게)
    rotated = racket_img.rotate(angle_deg, resample=Image.Resampling.BICUBIC, expand=True)
    
    # 원래 라켓 하단 손잡이(그립) 끝점 계산
    cx = racket_img.width / 2
    cy = racket_img.height / 2
    handle_len = 50 * scale * 2
    pivot_x = cx
    pivot_y = cy + handle_len
    
    # 중심점 대비 손잡이 끝점 벡터
    dx_orig = pivot_x - cx
    dy_orig = pivot_y - cy
    
    # 2D 화면 좌표계 회전 연산 (Y축 아래 방향 고려)
    rad = math.radians(angle_deg)
    dx = dx_orig * math.cos(rad) + dy_orig * math.sin(rad)
    dy = -dx_orig * math.sin(rad) + dy_orig * math.cos(rad)
    
    # 회전된 이미지 속의 손잡이 끝점 좌표
    rot_cx = rotated.width / 2
    rot_cy = rotated.height / 2
    rot_pivot_x = rot_cx + dx
    rot_pivot_y = rot_cy + dy
    
    # 손잡이 끝점을 손목 좌표와 정확히 일치시켜 붙임
    paste_x = int(wrist_x - rot_pivot_x)
    paste_y = int(wrist_y - rot_pivot_y)
    
    canvas.paste(rotated, (paste_x, paste_y), rotated)

# --- 메인 애니메이션 연산 및 비디오 생성 함수 ---
def build_tennis_video():
    print(f"[Start] Animation rendering started (Resolution: {WIDTH}x{HEIGHT}, FPS: {FPS})")
    
    # 레이아웃 정의 (세로형 최적화 기준)
    scale_factor = HEIGHT / 1920.0
    
    # 캐릭터 자체 스케일을 기존보다 약 2.2배 크게 확대 (Shorts 화면에 꽉 찬 크기)
    char_scale = scale_factor * 2.2
    
    ground_y = int(HEIGHT * 0.72)  # 지면 Y 좌표를 약간 낮춤
    stickman_x = int(WIDTH * 0.25) # 왼쪽 배치
    # 대퇴골(65) + 경골(65) = 130 길이만큼 골반을 위로 올려 발이 지면 위에 서게 맞춤
    stickman_y = ground_y - int(130 * char_scale)
    
    net_x = int(WIDTH * 0.76)
    net_height = int(140 * scale_factor)
    net_top_y = ground_y - net_height
    
    ball_radius = int(14 * scale_factor * 1.5)  # 공 크기도 스케일에 맞춰 1.5배 확대
    
    # 2x SSAA 렌더링용 라켓 템플릿 생성 (캐릭터 스케일에 연동)
    racket_template = create_racket_template(char_scale)
    
    # 물리 연산용 중력 및 타격 시점 상수 정의 (느린 재생에 맞추어 중력을 낮추어 토스 높이가 과해지지 않게 제어)
    gravity = 0.18 * scale_factor
    dt_toss = 120 - 40  # 토스(40프레임)부터 타격(120프레임)까지 프레임 수 (80 프레임)
    
    # --- 1단계: 토스 물리 궤적 역계산 ---
    # 임팩트 시점(frame 120)의 라켓 헤드 중앙(스위트 스폿)의 좌표를 먼저 구함
    impact_pose = interpolate_pose(120)
    impact_joints = get_joint_coordinates(stickman_x, stickman_y, impact_pose, char_scale)
    
    # 라켓 헤드 중앙의 상대적 거리 (손목에서 라켓 길이의 0.75배 만큼 연장선 상)
    impact_racket_len = impact_joints["racket_len"]
    impact_racket_rad = impact_joints["racket_rad"]
    r_wrist_x, r_wrist_y = impact_joints["r_wrist"]
    racket_sweet_spot_x = r_wrist_x + (impact_racket_len * 0.75) * math.cos(impact_racket_rad)
    racket_sweet_spot_y = r_wrist_y - (impact_racket_len * 0.75) * math.sin(impact_racket_rad)
    
    # 토스 시작 시점(frame 40)의 왼손(wrist) 좌표 구함
    toss_pose = interpolate_pose(40)
    toss_joints = get_joint_coordinates(stickman_x, stickman_y, toss_pose, char_scale)
    toss_start_x, toss_start_y = toss_joints["l_wrist"]
    
    # 등가속도 물리 공식을 적용해 임팩트 지점에 정밀 타격 가능한 토스 초기 속도(vx, vy) 역계산
    # x_t = x_0 + vx * t  =>  vx = (x_t - x_0) / t
    # y_t = y_0 + vy * t + 0.5 * g * t^2  =>  vy = (y_t - y_0 - 0.5 * g * t^2) / t
    ball_vx_toss = (racket_sweet_spot_x - toss_start_x) / dt_toss
    ball_vy_toss = (racket_sweet_spot_y - toss_start_y - 0.5 * gravity * (dt_toss ** 2)) / dt_toss
    
    # --- 2단계: 프레임 루프를 돌며 위치 정보 시뮬레이션 ---
    ball_history = []  # 공의 물리 궤적 캐시 [(x, y), ...]
    ball_vx = 0.0
    ball_vy = 0.0
    ball_x, ball_y = 0.0, 0.0
    is_ball_hit = False
    
    # 프레임별 상태 사전 연산
    simulated_positions = []
    
    for frame in range(TOTAL_FRAMES):
        pose = interpolate_pose(frame)
        joints = get_joint_coordinates(stickman_x, stickman_y, pose, char_scale)
        
        # 공의 위치 연산
        if frame < 40:
            # 토스 전: 왼손에 공이 들려 있음
            ball_x, ball_y = joints["l_wrist"]
            ball_vx = 0.0
            ball_vy = 0.0
        elif frame == 40:
            # 토스 순간: 역계산한 토스 초기 속도 대입
            ball_x, ball_y = joints["l_wrist"]
            ball_vx = ball_vx_toss
            ball_vy = ball_vy_toss
        elif 40 < frame < 120:
            # 토스 비행 중: 중력 적용
            ball_vy += gravity
            ball_x += ball_vx
            ball_y += ball_vy
        elif frame == 120:
            # 임팩트 타격 순간: 높은 속도로 코트 반대편으로 스매시 (물리 속도 강제 리셋)
            ball_x, ball_y = racket_sweet_spot_x, racket_sweet_spot_y
            ball_vx = 26.0 * scale_factor  # 빠른 속도로 전진
            ball_vy = 2.0 * scale_factor   # 약간 내리꽂는 탑스핀 궤적
            is_ball_hit = True
        else:
            # 타격 후 공의 날아감: 중력 및 바닥/네트 충돌 감지
            ball_vy += gravity
            ball_x += ball_vx
            ball_y += ball_vy
            
            # 네트 충돌 검사
            net_x_2d = net_x
            if (ball_x - ball_vx) < net_x_2d <= ball_x:
                # 네트 위치를 통과하는 순간 높이가 네트 탑(net_top_y)보다 낮으면 걸림
                if ball_y > net_top_y:
                    ball_x = net_x_2d
                    ball_vx = -ball_vx * 0.08  # 네트에 맞아 속도 극단적 감쇄 후 튕김
                    ball_vy = 2.0 * scale_factor  # 뚝 떨어짐
            
            # 바닥 바운드 충돌 검사
            if ball_y >= ground_y - ball_radius:
                ball_y = ground_y - ball_radius
                ball_vy = -ball_vy * 0.65  # 탄성 계수 0.65 적용해 튕김
                ball_vx *= 0.82            # 마찰력에 따른 속도 감쇄
        
        simulated_positions.append({
            "frame": frame,
            "pose": pose,
            "joints": joints,
            "ball": (ball_x, ball_y),
            "is_ball_hit": is_ball_hit
        })
        
    # --- 3단계: 이미지 프레임 렌더링 (SSAA 2x 적용하여 안티앨리어싱 극대화) ---
    frames_buffer = []
    font = get_system_font(int(45 * scale_factor))
    font_sub = get_system_font(int(30 * scale_factor))
    
    print("[Render] Starting frame drawing...")
    
    for f_idx, state in enumerate(simulated_positions):
        frame = state["frame"]
        pose = state["pose"]
        joints = state["joints"]
        bx, by = state["ball"]
        
        # 2배 해상도의 캔버스 생성 (스케치북 느낌의 순백색 배경)
        canvas_w, canvas_h = WIDTH * 2, HEIGHT * 2
        img = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # 스케일 변수 2배 보정
        s2 = scale_factor * 2
        
        # 1. 지면(Ground Line) 그리기 (검은색 잉크선)
        ground_y2 = ground_y * 2
        draw.line([(0, ground_y2), (canvas_w, ground_y2)], fill=(40, 40, 40, 255), width=int(5 * s2))
        
        # 2. 테니스 코트 라인 그리기 (심플한 2D 스케치북 스타일)
        court_color = (120, 130, 140, 255)
        draw.line([(int(WIDTH * 0.05 * 2), ground_y2), (int(WIDTH * 0.05 * 2), canvas_h)], fill=court_color, width=int(4 * s2))
        draw.line([(int(WIDTH * 0.4 * 2), ground_y2), (int(WIDTH * 0.4 * 2), canvas_h)], fill=court_color, width=int(3 * s2))
        
        # 3. 테니스 네트 그리기 (손그림 지주목 & 격자 패턴)
        net_x2 = net_x * 2
        net_top_y2 = net_top_y * 2
        
        # 네트 포스트 (검은색 테두리의 지주목)
        draw.rectangle([net_x2 - int(5 * s2), net_top_y2 - int(12 * s2), net_x2 + int(5 * s2), ground_y2], fill=(240, 240, 240, 255), outline=(0, 0, 0, 255), width=int(3 * s2))
        
        # 네트 격자망
        mesh_step = int(8 * s2)
        for nx in range(net_x2, canvas_w, mesh_step):
            draw.line([(nx, net_top_y2), (nx, ground_y2)], fill=(150, 150, 150, 100), width=1)
        for ny in range(net_top_y2, ground_y2, mesh_step):
            draw.line([(net_x2, ny), (canvas_w, ny)], fill=(150, 150, 150, 100), width=1)
            
        # 네트 상단 백색 밴드 (검은색 얇은 테두리가 있는 밴드)
        draw.rectangle([net_x2, net_top_y2, canvas_w, net_top_y2 + int(8 * s2)], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=int(2 * s2))
        
        # 4. 마커 펜 드로잉 스타일 졸라맨(Stick Figure Sketch Style) 그리기
        j2 = {k: (v[0] * 2, v[1] * 2) if isinstance(v, tuple) else v * 2 for k, v in joints.items()}
        
        # 캐릭터 크기 확대에 맞춘 마커 선 굵기 보정
        s_char = char_scale * 2
        lw = int(8 * s_char)  # 캐릭터 크기에 비례하여 굵은 마커 펜 효과 유지
        
        ink_color = (0, 0, 0, 255)  # 검은색 잉크
        fill_color = (255, 255, 255, 255)  # 내부 흰색 채움
        
        # (A) 다리 그리기 (검은색 잉크선)
        # 왼다리
        draw.line([j2["hip"], j2["l_knee"]], fill=ink_color, width=lw)
        draw.line([j2["l_knee"], j2["l_ankle"]], fill=ink_color, width=lw)
        # 오른다리
        draw.line([j2["hip"], j2["r_knee"]], fill=ink_color, width=lw)
        draw.line([j2["r_knee"], j2["r_ankle"]], fill=ink_color, width=lw)
        
        # (B) 몸통 (Spine)
        draw.line([j2["hip"], j2["neck"]], fill=ink_color, width=lw)
        
        # (C) 팔 그리기
        # 왼팔
        draw.line([j2["neck"], j2["l_elbow"]], fill=ink_color, width=lw)
        draw.line([j2["l_elbow"], j2["l_wrist"]], fill=ink_color, width=lw)
        # 오른팔
        draw.line([j2["neck"], j2["r_elbow"]], fill=ink_color, width=lw)
        draw.line([j2["r_elbow"], j2["r_wrist"]], fill=ink_color, width=lw)
        
        # (D) 머리 그리기 (흰색 바탕 채우고 검은색 테두리 - 원본 이미지 완벽 싱크)
        head_cx, head_cy = j2["head"]
        hr = j2["head_r"] * 1.1  # 큼직한 머리 크기
        draw.ellipse([head_cx - hr, head_cy - hr, head_cx + hr, head_cy + hr], fill=fill_color, outline=ink_color, width=int(4 * s_char))
        
        # (E) 관절 구체 마감 (검은색 마커로 칠한 자연스러운 꺾임점)
        for joint_key in ["hip", "neck", "l_elbow", "r_elbow", "l_knee", "r_knee"]:
            jx, jy = j2[joint_key]
            jr = lw // 2
            draw.ellipse([jx - jr, jy - jr, jx + jr, jy + jr], fill=ink_color)
            
        # 손/발 끝부분 연출 (wrist는 작은 동그라미 손, ankle은 납작하고 둥근 평평한 발 형태)
        # 왼발 (동글납작한 발)
        l_ax, l_ay = j2["l_ankle"]
        draw.ellipse([l_ax - int(12 * s_char), l_ay - int(4 * s_char), l_ax + int(24 * s_char), l_ay + int(4 * s_char)], fill=ink_color)
        # 오른발 (동글납작한 발)
        r_ax, r_ay = j2["r_ankle"]
        draw.ellipse([r_ax - int(12 * s_char), r_ay - int(4 * s_char), r_ax + int(24 * s_char), r_ay + int(4 * s_char)], fill=ink_color)
        
        # 손 (작은 검은색 원)
        for wrist_key in ["l_wrist", "r_wrist"]:
            jx, jy = j2[wrist_key]
            jr = int(7 * s_char)
            draw.ellipse([jx - jr, jy - jr, jx + jr, jy + jr], fill=ink_color)
            
        # (F) 라켓 페이스트 (오른손 손목 좌표 기준 회전 합성)
        paste_rotated_racket(img, racket_template, j2["r_wrist"][0], j2["r_wrist"][1], joints["racket_rad"], char_scale)
        
        # 5. 공의 모션 블러 잔상(Motion Trail) 그리기 (화이트보드 풍 옅은 궤적)
        ball_history.append((bx * 2, by * 2))
        if len(ball_history) > 10:
            ball_history.pop(0)
            
        for idx, (hx, hy) in enumerate(ball_history[:-1]):
            trail_ratio = (idx + 1) / len(ball_history)
            trail_r = int(ball_radius * 2 * (0.3 + 0.7 * trail_ratio))
            # 옅은 형광 노랑 궤적
            draw.ellipse([hx - trail_r, hy - trail_r, hx + trail_r, hy + trail_r], fill=(230, 255, 0, int(100 * trail_ratio)))
            
        # 6. 실시간 공 (형광 노랑색 볼에 검은색 아웃라인 코팅)
        bx2, by2 = bx * 2, by * 2
        br2 = ball_radius * 2
        draw.ellipse([bx2 - br2, by2 - br2, bx2 + br2, by2 + br2], fill=(220, 255, 0, 255), outline=ink_color, width=int(2.5 * s2))
        
        # 7. 타격 순간 임팩트 만화적 연출 (스파크와 팝 효과 - POP/POW 만화 효과선)
        if 120 <= frame <= 130:
            impact_progress = (frame - 120) / 10.0
            # 8방향 사방으로 뻗어 나가는 검은색 충격 지시선
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
                
        # 8. 텍스트 정보 레이블 오버레이 (순백색 배경 대비 짙은 검은색 잉크 폰트 적용)
        # (A) 동작 상태 타이틀
        draw.text((int(60 * 2), int(80 * 2)), pose["phase_text"], font=font, fill=ink_color)
        
        # (B) 테니스 정보 팁 자막 박스 (만화책 만화 컷 느낌의 흰색 판넬 + 검은색 테두리 + 그림자)
        box_y = int(HEIGHT * 0.8 * 2)
        box_h = int(140 * scale_factor * 2)
        
        # 만화 컷 드롭 섀도우 (검은색 섀도 박스 오프셋)
        shadow_offset = int(7 * s2)
        draw.rectangle([int(WIDTH * 0.1 * 2) + shadow_offset, box_y + shadow_offset, int(WIDTH * 0.9 * 2) + shadow_offset, box_y + box_h + shadow_offset], fill=(40, 40, 40, 255))
        
        # 메인 흰색 박스 패널
        draw.rectangle([int(WIDTH * 0.1 * 2), box_y, int(WIDTH * 0.9 * 2), box_y + box_h], fill=(255, 255, 255, 255), outline=ink_color, width=int(3.5 * s2))
        
        # 자막 문구 세팅
        tips = {
            "1. 준비 자세 (Ready)": "무릎을 살짝 굽히고 어깨를 릴랙스하여 대기합니다.",
            "2. 볼 토스 (Toss)": "일정한 타점을 위해 공을 머리 앞 방향으로 곧게 던져 올립니다.",
            "3. 트로피 자세 (Trophy Pose)": "무릎을 최대로 굽히고 상체를 젖혀 점프 파워를 비축합니다.",
            "4. 임팩트 (Impact)": "가장 높은 타점에서 뻗어 치며 강력한 포인트를 만들어 냅니다.",
            "5. 팔로우 스루 (Follow Through)": "스윙의 궤적을 끝까지 가져가며 어깨 너머로 마무리합니다.",
            "6. 피니시 (Finish)": "코트에 안정적으로 착지하며 다음 리턴 랠리를 준비합니다."
        }
        tip_text = tips.get(pose["phase_text"], "")
        draw.text((int(WIDTH * 0.15 * 2), box_y + int(30 * scale_factor * 2)), "💡 코칭 팁:", font=font_sub, fill=(230, 160, 0, 255))
        draw.text((int(WIDTH * 0.15 * 2), box_y + int(75 * scale_factor * 2)), tip_text, font=font_sub, fill=ink_color)

        # 9. 2x 해상도를 1x 해상도로 고품질 축소 (LANCZOS 필터 안티앨리어싱 완성)
        frame_img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        
        # RGB 넘파이 배열 변환 후 버퍼 추가
        frames_buffer.append(np.array(frame_img.convert("RGB")))
        
        # 30프레임마다 로그 출력
        if (f_idx + 1) % 30 == 0:
            print(f"   [렌더링 진행도] {f_idx + 1} / {TOTAL_FRAMES} 프레임 처리 완료...")
            
    # --- 4단계: MoviePy를 이용해 최종 MP4 비디오 합성 및 보관 ---
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
