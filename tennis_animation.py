#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tennis_animation.py - 테니스 졸라맨 애니메이션 생성기 (단일 파일, 외부 데이터 불필요)

8가지 테니스 동작의 졸라맨 애니메이션을 MP4 영상으로 생성합니다.
바이오메카닉스 기반 키프레임 + Cubic Easing + 체중 이동 + 몸통 회전

사용법:
    python tennis_animation.py                  # 대화형 메뉴
    python tennis_animation.py serve            # 서브 영상 생성
    python tennis_animation.py forehand         # 포핸드 영상 생성
    python tennis_animation.py backhand_1h      # 원핸드 백핸드
    python tennis_animation.py backhand_2h      # 투핸드 백핸드
    python tennis_animation.py volley_fh        # 포핸드 발리
    python tennis_animation.py volley_bh        # 백핸드 발리
    python tennis_animation.py smash            # 오버헤드 스매시
    python tennis_animation.py slice            # 슬라이스
    python tennis_animation.py serve -o out.mp4 # 출력 파일 지정
"""

import os, sys, math, argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont

if sys.platform.startswith('win'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError: pass

try:
    from moviepy.editor import ImageSequenceClip
except ImportError:
    try:
        from moviepy.video.io.ImageSequenceClip import ImageSequenceClip
    except ImportError:
        from moviepy import ImageSequenceClip

# ═══════════════════════════════════════════════════════════════
# 상수 설정
# ═══════════════════════════════════════════════════════════════
WIDTH, HEIGHT = 1080, 1920
FPS = 30
TOTAL_FRAMES = 180
SSAA = 2  # 안티앨리어싱 배율

# 신체 비율 (픽셀 단위, 기본값)
BODY = {
    "head_r": 28, "torso": 110,
    "upper_arm": 58, "forearm": 55,
    "thigh": 70, "shin": 68,
    "shoulder_hw": 50, "hip_hw": 25,
    "racket_handle": 30, "racket_head_w": 18, "racket_head_h": 30,
}

# ═══════════════════════════════════════════════════════════════
# Easing 함수
# ═══════════════════════════════════════════════════════════════
def _ease_linear(t): return t
def _ease_in(t): return t * t
def _ease_out(t): return 1 - (1 - t) ** 2
def _ease_in_out(t):
    return 4*t*t*t if t < 0.5 else 1 - (-2*t+2)**3/2
def _ease_in_cubic(t): return t*t*t
def _ease_out_cubic(t): return 1 - (1-t)**3
def _ease_explosive(t): return 0 if t==0 else 2**(10*(t-1))
def _ease_decelerate(t): return 1 - (1-t)**3

EASINGS = {
    "linear": _ease_linear, "ease_in": _ease_in, "ease_out": _ease_out,
    "ease_in_out": _ease_in_out, "ease_in_cubic": _ease_in_cubic,
    "ease_out_cubic": _ease_out_cubic, "explosive": _ease_explosive,
    "decelerate": _ease_decelerate,
}

# ═══════════════════════════════════════════════════════════════
# 키프레임 보간
# ═══════════════════════════════════════════════════════════════
def _angle_lerp(a, b, t):
    """최단 경로 각도 보간 (음수 각도 지원)"""
    diff = ((b - a + 180) % 360) - 180
    return a + diff * t

def interpolate_keyframes(keyframes, t_global):
    """키프레임 리스트에서 t(0~1) 시점의 보간값 반환"""
    if t_global <= keyframes[0]["t"]:
        return keyframes[0]["joints"].copy(), keyframes[0]["label"]
    if t_global >= keyframes[-1]["t"]:
        return keyframes[-1]["joints"].copy(), keyframes[-1]["label"]

    for i in range(len(keyframes) - 1):
        t0, t1 = keyframes[i]["t"], keyframes[i+1]["t"]
        if t0 <= t_global <= t1:
            local_t = (t_global - t0) / (t1 - t0) if t1 != t0 else 0
            easing_name = keyframes[i+1].get("easing", "linear")
            easing_fn = EASINGS.get(easing_name, _ease_linear)
            et = easing_fn(local_t)

            j0 = keyframes[i]["joints"]
            j1 = keyframes[i+1]["joints"]
            result = {}
            angle_keys = {"torso","r_shoulder","r_elbow","r_wrist","l_shoulder","l_elbow",
                          "r_hip_angle","r_knee","l_hip_angle","l_knee","body_rotation"}
            for key in j0:
                if key in angle_keys:
                    result[key] = _angle_lerp(j0[key], j1[key], et)
                else:
                    result[key] = j0[key] + (j1[key] - j0[key]) * et

            label = keyframes[i]["label"] if local_t < 0.5 else keyframes[i+1]["label"]
            return result, label

    return keyframes[-1]["joints"].copy(), keyframes[-1]["label"]

# ═══════════════════════════════════════════════════════════════
# FK (Forward Kinematics) 계산
# ═══════════════════════════════════════════════════════════════
def compute_fk(joints, base_x, base_y, scale):
    """관절 딕셔너리 → 화면 좌표 딕셔너리"""
    B = {k: v * scale for k, v in BODY.items()}
    hx = base_x + joints.get("hip_x", 0) * scale * 1.8  # 체중이동 강조
    hy = base_y + joints.get("hip_y", 0) * scale * 1.8
    body_rot = math.radians(joints.get("body_rotation", 0))
    torso_rad = math.radians(joints["torso"])

    # 어깨 폭 압축 (몸통 회전 시)
    sw = B["shoulder_hw"] * max(0.25, abs(math.cos(body_rot)))
    hw = B["hip_hw"] * max(0.25, abs(math.cos(body_rot)))
    s_offset_x = B["shoulder_hw"] * 0.3 * math.sin(body_rot)
    h_offset_x = B["hip_hw"] * 0.15 * math.sin(body_rot)

    # 척추
    neck_x = hx + B["torso"] * math.cos(torso_rad)
    neck_y = hy - B["torso"] * math.sin(torso_rad)

    # 머리
    head_dist = B["head_r"] * 1.5
    head_x = neck_x + head_dist * math.cos(torso_rad)
    head_y = neck_y - head_dist * math.sin(torso_rad)

    # 어깨 좌표
    perp = torso_rad - math.pi/2  # 올바른 좌우 방향 (torso=90°일 때 perp=0°=오른쪽)
    r_sh_x = neck_x + sw * math.cos(perp) + s_offset_x
    r_sh_y = neck_y - sw * math.sin(perp)
    l_sh_x = neck_x - sw * math.cos(perp) + s_offset_x
    l_sh_y = neck_y + sw * math.sin(perp)

    # 골반 좌표
    r_hp_x = hx + hw * math.cos(perp) + h_offset_x
    r_hp_y = hy - hw * math.sin(perp)
    l_hp_x = hx - hw * math.cos(perp) + h_offset_x
    l_hp_y = hy + hw * math.sin(perp)

    def _arm_chain(sh_x, sh_y, shoulder_a, elbow_a, wrist_a=None):
        sa = math.radians(shoulder_a)
        ex = sh_x + B["upper_arm"] * math.cos(sa)
        ey = sh_y - B["upper_arm"] * math.sin(sa)
        ea = sa + math.radians(elbow_a)
        wx = ex + B["forearm"] * math.cos(ea)
        wy = ey - B["forearm"] * math.sin(ea)
        ra = None
        rcx, rcy, rtx, rty = None,None,None,None
        if wrist_a is not None:
            ra = ea + math.radians(wrist_a)
            rcx = wx + B["racket_handle"] * math.cos(ra)
            rcy = wy - B["racket_handle"] * math.sin(ra)
            rtx = rcx + (B["racket_head_h"]) * math.cos(ra)
            rty = rcy - (B["racket_head_h"]) * math.sin(ra)
        return (ex, ey), (wx, wy), ra, (rcx, rcy), (rtx, rty)

    def _leg_chain(hp_x, hp_y, hip_a, knee_a):
        ha = math.radians(hip_a)
        kx = hp_x + B["thigh"] * math.cos(ha)
        ky = hp_y - B["thigh"] * math.sin(ha)
        ka = ha + math.radians(knee_a)
        ax = kx + B["shin"] * math.cos(ka)
        ay = ky - B["shin"] * math.sin(ka)
        return (kx, ky), (ax, ay)

    r_elb, r_wri, racket_rad, racket_center, racket_tip = _arm_chain(
        r_sh_x, r_sh_y, joints["r_shoulder"], joints["r_elbow"], joints.get("r_wrist", 0))
    l_elb, l_wri, _, _, _ = _arm_chain(
        l_sh_x, l_sh_y, joints["l_shoulder"], joints["l_elbow"])

    r_knee, r_ankle = _leg_chain(r_hp_x, r_hp_y, joints["r_hip_angle"], joints["r_knee"])
    l_knee, l_ankle = _leg_chain(l_hp_x, l_hp_y, joints["l_hip_angle"], joints["l_knee"])

    return {
        "hip": (hx, hy), "neck": (neck_x, neck_y), "head": (head_x, head_y),
        "r_shoulder": (r_sh_x, r_sh_y), "l_shoulder": (l_sh_x, l_sh_y),
        "r_elbow": r_elb, "l_elbow": l_elb,
        "r_wrist": r_wri, "l_wrist": l_wri,
        "r_hip": (r_hp_x, r_hp_y), "l_hip": (l_hp_x, l_hp_y),
        "r_knee": r_knee, "l_knee": l_knee,
        "r_ankle": r_ankle, "l_ankle": l_ankle,
        "racket_rad": racket_rad,
        "racket_center": racket_center, "racket_tip": racket_tip,
        "head_r": B["head_r"], "body_rotation": body_rot,
        "racket_head_w": B["racket_head_w"], "racket_head_h": B["racket_head_h"],
    }

# ═══════════════════════════════════════════════════════════════
# 폰트 탐색
# ═══════════════════════════════════════════════════════════════
def get_font(size):
    paths = [
        "C:/Windows/Fonts/malgunbd.ttf","C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothicBold.ttf","C:/Windows/Fonts/NanumGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in paths:
        if os.path.isfile(p):
            try: return ImageFont.truetype(p, size)
            except: pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()

# ═══════════════════════════════════════════════════════════════
# 렌더링 함수
# ═══════════════════════════════════════════════════════════════
def draw_stickman(draw, fk, s, color=(0,0,0,255), lw_body=None, lw_arm=None):
    """졸라맨 하나를 그림. s = SSAA scale, color = 선/채우기 색상"""
    if lw_body is None: lw_body = int(8*s)
    if lw_arm is None: lw_arm = int(6*s)
    fill_head = (255,255,255,255) if color==(0,0,0,255) else (255,255,255, color[3] if len(color)>3 else 255)

    rot = fk["body_rotation"]
    # 앞/뒤 판단: body_rotation > 0 → 오른쪽이 카메라 쪽(가까움)
    far_side = "l" if rot > 0 else "r"
    near_side = "r" if rot > 0 else "l"

    def _draw_limb(side):
        # 다리
        draw.line([fk[f"{side}_hip"], fk[f"{side}_knee"]], fill=color, width=lw_body)
        draw.line([fk[f"{side}_knee"], fk[f"{side}_ankle"]], fill=color, width=lw_body)
        # 발
        ax, ay = fk[f"{side}_ankle"]
        # 발 방향: 오른발은 오른쪽, 왼발은 왼쪽으로 향함
        if side == "r":
            draw.ellipse([ax-int(8*s), ay-int(4*s), ax+int(16*s), ay+int(5*s)], fill=color)
        else:
            draw.ellipse([ax-int(16*s), ay-int(4*s), ax+int(8*s), ay+int(5*s)], fill=color)
        # 팔
        draw.line([fk[f"{side}_shoulder"], fk[f"{side}_elbow"]], fill=color, width=lw_arm)
        draw.line([fk[f"{side}_elbow"], fk[f"{side}_wrist"]], fill=color, width=lw_arm)
        # 손
        wx, wy = fk[f"{side}_wrist"]
        jr = int(6*s)
        draw.ellipse([wx-jr, wy-jr, wx+jr, wy+jr], fill=color)

    # 먼 쪽 팔다리
    _draw_limb(far_side)
    # 몸통
    draw.line([fk["hip"], fk["neck"]], fill=color, width=lw_body)
    # 머리
    hx, hy = fk["head"]
    hr = fk["head_r"] * s
    draw.ellipse([hx-hr, hy-hr, hx+hr, hy+hr], fill=fill_head, outline=color, width=int(3*s))
    # 가까운 쪽 팔다리
    _draw_limb(near_side)
    # 관절점 
    for jk in ["hip","neck","r_elbow","l_elbow","r_knee","l_knee"]:
        jx, jy = fk[jk]
        jr = lw_body//2
        draw.ellipse([jx-jr, jy-jr, jx+jr, jy+jr], fill=color)

def draw_racket(img, draw, fk, s, color_handle=(30,30,180,255), color_head=(220,50,50,255)):
    """라켓 그리기 (회전된 헤드 포함)"""
    if fk["racket_center"] is None: return
    wx, wy = fk["r_wrist"]
    cx, cy = fk["racket_center"]
    tx, ty = fk["racket_tip"]
    # 핸들
    draw.line([(wx,wy),(cx,cy)], fill=color_handle, width=int(5*s))
    # 헤드 (회전된 타원 - 별도 이미지 생성 후 합성)
    rw = int(fk["racket_head_w"] * s * 2.2)
    rh = int(fk["racket_head_h"] * s * 1.4)
    pad = max(rw, rh) + 4
    head_img = Image.new("RGBA", (pad*2, pad*2), (0,0,0,0))
    head_draw = ImageDraw.Draw(head_img)
    head_draw.ellipse([pad-rw, pad-rh, pad+rw, pad+rh], fill=color_head, outline=(0,0,0,255), width=int(2*s))
    # 라켓 각도로 회전
    angle_deg = math.degrees(fk["racket_rad"]) - 90
    rotated = head_img.rotate(angle_deg, resample=Image.Resampling.BICUBIC, expand=True)
    mid_x = int((cx + tx) / 2)
    mid_y = int((cy + ty) / 2)
    paste_x = mid_x - rotated.width // 2
    paste_y = mid_y - rotated.height // 2
    img.paste(rotated, (paste_x, paste_y), rotated)

def draw_ball(draw, bx, by, s, radius=None):
    if radius is None: radius = int(12*s)
    draw.ellipse([bx-radius, by-radius, bx+radius, by+radius],
                 fill=(230,255,0,255), outline=(0,0,0,255), width=int(2*s))

def draw_impact_effect(draw, cx, cy, progress, s):
    """임팩트 시 확장하는 충격파 원"""
    max_r = int(80*s*progress)
    min_r = int(20*s*progress)
    alpha = int(200*(1-progress))
    if alpha < 10: return
    col = (255, 80, 0, alpha)
    for r in range(min_r, max_r, int(8*s)):
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=col, width=int(3*s))

# ═══════════════════════════════════════════════════════════════
# 공 물리 시뮬레이션
# ═══════════════════════════════════════════════════════════════
def simulate_ball(motion, keyframes, fk_list, total_frames, scale):
    """프레임별 공 위치 리스트 반환. None이면 공 안 보임."""
    ball_cfg = motion.get("ball", {})
    if not ball_cfg: return [None]*total_frames

    appear_t = ball_cfg.get("appear_t", 0.0)
    impact_t = ball_cfg.get("impact_t", 0.6)
    start_from = ball_cfg.get("start_from", "left_wrist")
    post_vx = ball_cfg.get("post_vx", 18) * scale
    post_vy = ball_cfg.get("post_vy", 3) * scale
    gravity = 0.35 * scale

    appear_f = int(appear_t * total_frames)
    impact_f = int(impact_t * total_frames)

    positions = [None] * total_frames

    # 임팩트 시 라켓 팁 위치
    if impact_f < total_frames and fk_list[impact_f]["racket_tip"][0] is not None:
        impact_x, impact_y = fk_list[impact_f]["racket_tip"]
    else:
        impact_x, impact_y = fk_list[min(impact_f, total_frames-1)]["r_wrist"]

    # 시작 위치
    if appear_f < total_frames:
        if start_from == "right_edge":
            start_x = (WIDTH * SSAA) * 0.92
            start_y = (HEIGHT * SSAA) * 0.35
        elif start_from == "top":
            start_x = impact_x + 50 * scale
            start_y = (HEIGHT * SSAA) * 0.05
        else:  # left_wrist (serve toss)
            sx, sy = fk_list[appear_f]["l_wrist"]
            start_x, start_y = sx, sy
    else:
        start_x, start_y = 0, 0

    # 프리-임팩트 궤적 (시작→임팩트 사이 포물선)
    pre_frames = impact_f - appear_f
    if pre_frames > 0:
        # 역계산: 시작→끝 포물선
        dt = pre_frames
        vx0 = (impact_x - start_x) / dt
        vy0 = (impact_y - start_y - 0.5 * gravity * dt * dt) / dt
        for f in range(appear_f, impact_f):
            df = f - appear_f
            bx = start_x + vx0 * df
            by = start_y + vy0 * df + 0.5 * gravity * df * df
            positions[f] = (bx, by)

    # 임팩트 프레임
    if impact_f < total_frames:
        positions[impact_f] = (impact_x, impact_y)

    # 포스트-임팩트 궤적
    bx, by = impact_x, impact_y
    bvx, bvy = post_vx, post_vy
    ground_y = HEIGHT * SSAA * 0.72
    for f in range(impact_f + 1, total_frames):
        bvy += gravity
        bx += bvx
        by += bvy
        if by > ground_y:
            by = ground_y
            bvy = -bvy * 0.55
            bvx *= 0.8
        positions[f] = (bx, by)

    return positions

# ═══════════════════════════════════════════════════════════════
# 메인 렌더링 함수
# ═══════════════════════════════════════════════════════════════
def render_motion(motion, output_path):
    keyframes = motion["keyframes"]
    motion_name = motion["name"]
    cw, ch = WIDTH * SSAA, HEIGHT * SSAA
    scale = float(SSAA)  # 캐릭터 스케일 = SSAA (BODY 치수는 1920px 기준 정의)
    s = scale

    ground_y = int(ch * 0.72)
    base_x = int(cw * 0.32)
    base_y = ground_y - int(145 * scale)

    font_big = get_font(int(44 * SSAA))    # 88px on 2x canvas → 44px after downscale
    font_small = get_font(int(30 * SSAA))  # 60px on 2x canvas → 30px after downscale

    print(f"[시작] '{motion_name}' 애니메이션 렌더링 ({WIDTH}x{HEIGHT}, {FPS}fps, {TOTAL_FRAMES}프레임)")

    # 1단계: 모든 프레임의 FK 계산
    fk_list = []
    label_list = []
    for frame in range(TOTAL_FRAMES):
        t = frame / (TOTAL_FRAMES - 1)
        joints, label = interpolate_keyframes(keyframes, t)
        fk = compute_fk(joints, base_x, base_y, scale)
        fk_list.append(fk)
        label_list.append(label)

    # 2단계: 공 시뮬레이션
    ball_positions = simulate_ball(motion, keyframes, fk_list, TOTAL_FRAMES, scale)
    impact_t = motion.get("ball", {}).get("impact_t", -1)
    impact_frame = int(impact_t * TOTAL_FRAMES) if impact_t >= 0 else -1

    # 3단계: 프레임 렌더링
    frames_buffer = []
    ball_trail = []

    for frame in range(TOTAL_FRAMES):
        img = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)

        # 코트 (바닥 영역 연한 초록)
        draw.rectangle([(0, ground_y), (cw, ch)], fill=(235,245,235,255))
        # 베이스라인
        draw.line([(0, ground_y), (cw, ground_y)], fill=(50,50,50,255), width=int(5*s))
        # 서비스라인 (베이스라인에서 약간 아래)
        svc_y = ground_y + int(80*s)
        draw.line([(int(cw*0.05), svc_y), (int(cw*0.72), svc_y)], fill=(160,160,160,200), width=int(2*s))
        # 사이드라인
        draw.line([(int(cw*0.05), ground_y), (int(cw*0.05), ch)], fill=(140,140,140,200), width=int(2*s))
        draw.line([(int(cw*0.72), ground_y), (int(cw*0.72), ch)], fill=(140,140,140,200), width=int(2*s))
        # 센터 마크
        draw.line([(int(cw*0.385), ground_y), (int(cw*0.385), ground_y+int(25*s))], fill=(140,140,140,200), width=int(3*s))
        # 센터 서비스라인
        draw.line([(int(cw*0.385), ground_y), (int(cw*0.385), svc_y)], fill=(160,160,160,150), width=int(2*s))
        # 네트 (지주 + 네트선 + 상단 밴드)
        net_x = int(cw * 0.78)
        net_top = ground_y - int(100*scale)
        draw.rectangle([net_x-int(4*s), net_top-int(8*s), net_x+int(4*s), ground_y],
                        fill=(230,230,230,255), outline=(80,80,80,255), width=int(2*s))
        # 네트 망
        mesh = int(10*s)
        for ny in range(net_top, ground_y, mesh):
            draw.line([(net_x, ny), (cw, ny)], fill=(180,180,180,120), width=1)
        for nx in range(net_x, cw, mesh):
            draw.line([(nx, net_top), (nx, ground_y)], fill=(180,180,180,120), width=1)
        # 네트 상단 밴드
        draw.rectangle([net_x, net_top-int(6*s), cw, net_top+int(2*s)],
                        fill=(255,255,255,255), outline=(60,60,60,255), width=int(2*s))

        # 발밑 그림자
        fk_cur = fk_list[frame]
        shadow_y = ground_y + int(3*s)
        for ankle_key in ["r_ankle", "l_ankle"]:
            sx, sy = fk_cur[ankle_key]
            shadow_w = int(22*s)
            shadow_h = int(5*s)
            draw.ellipse([sx-shadow_w, shadow_y-shadow_h, sx+shadow_w, shadow_y+shadow_h],
                         fill=(180,180,180,120))

        # 고스트 트레일 (이전 프레임들)
        for gi, ghost_frame in enumerate([frame-6, frame-3]):
            if 0 <= ghost_frame < TOTAL_FRAMES:
                gray = [225, 200][gi]
                ghost_col = (gray, gray, gray, 255)
                ghost_lw = max(1, int(4*s))
                draw_stickman(draw, fk_list[ghost_frame], s, color=ghost_col, lw_body=ghost_lw, lw_arm=max(1,int(3*s)))

        # 메인 졸라맨
        fk = fk_list[frame]
        draw_stickman(draw, fk, s)
        draw_racket(img, draw, fk, s)

        # 공 잔상
        bp = ball_positions[frame]
        if bp:
            ball_trail.append(bp)
            if len(ball_trail) > 5: ball_trail.pop(0)
            for ti, (tx, ty) in enumerate(ball_trail[:-1]):
                ratio = (ti+1) / len(ball_trail)
                tr = int(8*s*ratio)
                alpha = int(120*ratio)
                draw.ellipse([tx-tr, ty-tr, tx+tr, ty+tr], fill=(255,200,0,alpha))
            draw_ball(draw, bp[0], bp[1], s)
        else:
            ball_trail.clear()

        # 스피드 라인 (임팩트 직전 3프레임)
        if impact_frame > 0 and -4 <= frame - impact_frame <= 0:
            speed_alpha = int(180 * (1 - abs(frame - impact_frame) / 4.0))
            wx, wy = fk["r_wrist"]
            ra = fk.get("racket_rad", 0) or 0
            for offset in range(-3, 4):
                line_len = int(50 * s)
                ox = int(offset * 8 * s)
                oy = int(offset * 4 * s)
                end_x = wx - line_len * math.cos(ra) + ox
                end_y = wy + line_len * math.sin(ra) + oy
                draw.line([(end_x, end_y), (wx+ox, wy+oy)],
                          fill=(200, 100, 0, min(255, speed_alpha)), width=max(1, int(2*s)))

        # 임팩트 효과
        if impact_frame > 0 and 0 <= frame - impact_frame <= 6:
            prog = (frame - impact_frame) / 6.0
            ix, iy = fk["racket_tip"] if fk["racket_tip"][0] else fk["r_wrist"]
            draw_impact_effect(draw, ix, iy, prog, s)

        # 텍스트 오버레이
        # 모션 이름 (상단)
        draw.text((int(50*s), int(40*s)), f"🎾 {motion_name}", font=font_big, fill=(0,0,0,255))
        # 페이즈 라벨
        draw.text((int(50*s), int(100*s)), label_list[frame], font=font_small, fill=(50,50,50,255))
        # 프레임 번호
        draw.text((cw - int(200*s), int(40*s)), f"{frame+1}/{TOTAL_FRAMES}", font=font_small, fill=(150,150,150,255))

        # SSAA 다운스케일
        frame_img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        frames_buffer.append(np.array(frame_img.convert("RGB")))

        if (frame + 1) % 30 == 0:
            print(f"  [렌더링] {frame+1}/{TOTAL_FRAMES} 프레임 완료")

    # 4단계: MP4 합성
    print("[합성] MP4 비디오 생성 중...")
    clip = ImageSequenceClip(frames_buffer, fps=FPS)
    try:
        clip.write_videofile(output_path, codec="libx264", audio=False, threads=4,
                             preset="medium", bitrate="5000k", logger=None)
    except TypeError:
        clip.write_videofile(output_path, codec="libx264", audio=False, threads=4,
                             preset="medium", bitrate="5000k")
    clip.close()
    print(f"[완료] ✅ 저장 완료: {output_path}")

# ═══════════════════════════════════════════════════════════════
# 8가지 모션 데이터  (바이오메카닉스 기반 키프레임)
# ═══════════════════════════════════════════════════════════════
def _jt(hip_x=0,hip_y=0,body_rotation=0,torso=88,
        r_shoulder=260,r_elbow=-25,r_wrist=0,
        l_shoulder=260,l_elbow=-25,
        r_hip_angle=268,r_knee=-8,l_hip_angle=272,l_knee=-8):
    return {"hip_x":hip_x,"hip_y":hip_y,"body_rotation":body_rotation,"torso":torso,
            "r_shoulder":r_shoulder,"r_elbow":r_elbow,"r_wrist":r_wrist,
            "l_shoulder":l_shoulder,"l_elbow":l_elbow,
            "r_hip_angle":r_hip_angle,"r_knee":r_knee,"l_hip_angle":l_hip_angle,"l_knee":l_knee}

MOTIONS = {
# ──────────── 서브 (Serve) ────────────
"serve": {
    "name": "서브 (Serve)", "output": "tennis_serve.mp4",
    "ball": {"appear_t":0.10, "impact_t":0.60, "start_from":"left_wrist", "post_vx":22, "post_vy":4},
    "keyframes": [
        {"t":0.00,"label":"1. 준비 자세 (Ready)","easing":"linear",
         "joints":_jt(hip_x=0,hip_y=0,body_rotation=20,torso=88, r_shoulder=250,r_elbow=-30,r_wrist=0, l_shoulder=250,l_elbow=-20, r_hip_angle=265,r_knee=-10,l_hip_angle=275,l_knee=-10)},
        {"t":0.15,"label":"2. 볼 토스 (Toss)","easing":"ease_out",
         "joints":_jt(hip_x=10,hip_y=10,body_rotation=35,torso=92, r_shoulder=200,r_elbow=-50,r_wrist=-20, l_shoulder=120,l_elbow=-10, r_hip_angle=265,r_knee=-15,l_hip_angle=275,l_knee=-10)},
        {"t":0.42,"label":"3. 트로피 자세 (Trophy Pose)","easing":"ease_out",
         "joints":_jt(hip_x=25,hip_y=50,body_rotation=55,torso=105, r_shoulder=170,r_elbow=-110,r_wrist=-60, l_shoulder=100,l_elbow=-5, r_hip_angle=255,r_knee=-45,l_hip_angle=265,l_knee=-40)},
        {"t":0.52,"label":"4. 라켓 드롭 (Racket Drop)","easing":"ease_in_cubic",
         "joints":_jt(hip_x=20,hip_y=30,body_rotation=40,torso=95, r_shoulder=160,r_elbow=-120,r_wrist=-70, l_shoulder=130,l_elbow=-30, r_hip_angle=260,r_knee=-25,l_hip_angle=270,l_knee=-20)},
        {"t":0.60,"label":"5. 임팩트 (Impact)","easing":"explosive",
         "joints":_jt(hip_x=5,hip_y=-55,body_rotation=5,torso=82, r_shoulder=95,r_elbow=-5,r_wrist=10, l_shoulder=240,l_elbow=-70, r_hip_angle=268,r_knee=-5,l_hip_angle=275,l_knee=-5)},
        {"t":0.78,"label":"6. 팔로우 스루 (Follow Through)","easing":"decelerate",
         "joints":_jt(hip_x=-15,hip_y=5,body_rotation=-25,torso=75, r_shoulder=220,r_elbow=-40,r_wrist=30, l_shoulder=260,l_elbow=-60, r_hip_angle=270,r_knee=-5,l_hip_angle=280,l_knee=-5)},
        {"t":1.00,"label":"7. 피니시 (Finish)","easing":"ease_out",
         "joints":_jt(hip_x=0,hip_y=0,body_rotation=0,torso=88, r_shoulder=250,r_elbow=-30,r_wrist=0, l_shoulder=260,l_elbow=-20, r_hip_angle=268,r_knee=-8,l_hip_angle=272,l_knee=-8)},
    ],
},
# ──────────── 포핸드 (Forehand) ────────────
"forehand": {
    "name": "포핸드 (Forehand)", "output": "tennis_forehand.mp4",
    "ball": {"appear_t":0.50, "impact_t":0.68, "start_from":"right_edge", "post_vx":20, "post_vy":-3},
    "keyframes": [
        {"t":0.00,"label":"1. 준비 자세 (Ready)","easing":"linear",
         "joints":_jt()},
        {"t":0.15,"label":"2. 스플릿 스텝 (Split Step)","easing":"ease_out",
         "joints":_jt(hip_y=15,body_rotation=10,torso=86, r_shoulder=255,r_elbow=-30,l_shoulder=255,l_elbow=-30, r_hip_angle=265,r_knee=-20,l_hip_angle=275,l_knee=-20)},
        {"t":0.32,"label":"3. 유닛 턴 (Unit Turn)","easing":"ease_out",
         "joints":_jt(hip_x=20,hip_y=10,body_rotation=65,torso=90, r_shoulder=190,r_elbow=-40,r_wrist=-10, l_shoulder=240,l_elbow=-30, r_hip_angle=260,r_knee=-15,l_hip_angle=275,l_knee=-15)},
        {"t":0.50,"label":"4. 라켓 드롭 (Racket Drop)","easing":"ease_in",
         "joints":_jt(hip_x=25,hip_y=25,body_rotation=75,torso=92, r_shoulder=230,r_elbow=-60,r_wrist=-40, l_shoulder=235,l_elbow=-35, r_hip_angle=258,r_knee=-30,l_hip_angle=278,l_knee=-25)},
        {"t":0.68,"label":"5. 임팩트 (Impact)","easing":"explosive",
         "joints":_jt(hip_x=-5,body_rotation=-5,torso=85, r_shoulder=150,r_elbow=-20,r_wrist=5, l_shoulder=250,l_elbow=-40, r_hip_angle=270,r_knee=-5,l_hip_angle=270,l_knee=-10)},
        {"t":0.82,"label":"6. 팔로우 스루 (Follow Through)","easing":"decelerate",
         "joints":_jt(hip_x=-20,hip_y=-5,body_rotation=-40,torso=80, r_shoulder=110,r_elbow=-30,r_wrist=20, l_shoulder=265,l_elbow=-50, r_hip_angle=272,r_knee=-5,l_hip_angle=268,l_knee=-8)},
        {"t":1.00,"label":"7. 피니시 (Finish)","easing":"ease_out",
         "joints":_jt()},
    ],
},
# ──────────── 원핸드 백핸드 (1H Backhand) ────────────
"backhand_1h": {
    "name": "원핸드 백핸드 (1H Backhand)", "output": "tennis_backhand_1h.mp4",
    "ball": {"appear_t":0.50, "impact_t":0.68, "start_from":"right_edge", "post_vx":18, "post_vy":-2},
    "keyframes": [
        {"t":0.00,"label":"1. 준비 (Ready)","easing":"linear",
         "joints":_jt()},
        {"t":0.15,"label":"2. 스플릿 스텝","easing":"ease_out",
         "joints":_jt(hip_y=15,body_rotation=-10,torso=86, r_shoulder=255,r_elbow=-30,l_shoulder=255,l_elbow=-30, r_hip_angle=265,r_knee=-20,l_hip_angle=275,l_knee=-20)},
        {"t":0.32,"label":"3. 유닛 턴 (Unit Turn)","easing":"ease_out",
         "joints":_jt(hip_x=-20,hip_y=10,body_rotation=-70,torso=90, r_shoulder=190,r_elbow=-35,r_wrist=-15, l_shoulder=200,l_elbow=-30, r_hip_angle=275,r_knee=-15,l_hip_angle=260,l_knee=-15)},
        {"t":0.50,"label":"4. 라켓 드롭","easing":"ease_in",
         "joints":_jt(hip_x=-25,hip_y=25,body_rotation=-80,torso=92, r_shoulder=220,r_elbow=-55,r_wrist=-35, l_shoulder=250,l_elbow=-20, r_hip_angle=278,r_knee=-28,l_hip_angle=258,l_knee=-25)},
        {"t":0.68,"label":"5. 임팩트 (Impact)","easing":"explosive",
         "joints":_jt(hip_x=5,body_rotation=5,torso=85, r_shoulder=135,r_elbow=-10,r_wrist=5, l_shoulder=270,l_elbow=-15, r_hip_angle=270,r_knee=-5,l_hip_angle=270,l_knee=-10)},
        {"t":0.82,"label":"6. 팔로우 스루","easing":"decelerate",
         "joints":_jt(hip_x=15,hip_y=-5,body_rotation=35,torso=82, r_shoulder=100,r_elbow=-15,r_wrist=15, l_shoulder=280,l_elbow=-30, r_hip_angle=268,r_knee=-5,l_hip_angle=272,l_knee=-8)},
        {"t":1.00,"label":"7. 피니시","easing":"ease_out",
         "joints":_jt()},
    ],
},
# ──────────── 투핸드 백핸드 (2H Backhand) ────────────
"backhand_2h": {
    "name": "투핸드 백핸드 (2H Backhand)", "output": "tennis_backhand_2h.mp4",
    "ball": {"appear_t":0.50, "impact_t":0.68, "start_from":"right_edge", "post_vx":19, "post_vy":-2},
    "keyframes": [
        {"t":0.00,"label":"1. 준비 (Ready)","easing":"linear",
         "joints":_jt()},
        {"t":0.15,"label":"2. 스플릿 스텝","easing":"ease_out",
         "joints":_jt(hip_y=15,body_rotation=-10,torso=86, r_shoulder=255,r_elbow=-30,l_shoulder=255,l_elbow=-30, r_hip_angle=265,r_knee=-20,l_hip_angle=275,l_knee=-20)},
        {"t":0.32,"label":"3. 유닛 턴","easing":"ease_out",
         "joints":_jt(hip_x=-15,hip_y=10,body_rotation=-55,torso=90, r_shoulder=200,r_elbow=-35,r_wrist=-10, l_shoulder=195,l_elbow=-40, r_hip_angle=275,r_knee=-15,l_hip_angle=262,l_knee=-15)},
        {"t":0.50,"label":"4. 라켓 드롭","easing":"ease_in",
         "joints":_jt(hip_x=-20,hip_y=25,body_rotation=-60,torso=92, r_shoulder=225,r_elbow=-50,r_wrist=-30, l_shoulder=220,l_elbow=-55, r_hip_angle=278,r_knee=-28,l_hip_angle=260,l_knee=-25)},
        {"t":0.68,"label":"5. 임팩트 (Impact)","easing":"explosive",
         "joints":_jt(hip_x=5,body_rotation=0,torso=85, r_shoulder=140,r_elbow=-15,r_wrist=5, l_shoulder=145,l_elbow=-20, r_hip_angle=270,r_knee=-5,l_hip_angle=270,l_knee=-10)},
        {"t":0.82,"label":"6. 팔로우 스루","easing":"decelerate",
         "joints":_jt(hip_x=15,hip_y=-5,body_rotation=30,torso=82, r_shoulder=105,r_elbow=-20,r_wrist=15, l_shoulder=110,l_elbow=-25, r_hip_angle=268,r_knee=-5,l_hip_angle=272,l_knee=-8)},
        {"t":1.00,"label":"7. 피니시","easing":"ease_out",
         "joints":_jt()},
    ],
},
# ──────────── 포핸드 발리 (FH Volley) ────────────
"volley_fh": {
    "name": "포핸드 발리 (FH Volley)", "output": "tennis_volley_fh.mp4",
    "ball": {"appear_t":0.35, "impact_t":0.55, "start_from":"right_edge", "post_vx":16, "post_vy":1},
    "keyframes": [
        {"t":0.00,"label":"1. 준비 자세 (Ready)","easing":"linear",
         "joints":_jt(torso=88, r_shoulder=140,r_elbow=-30,r_wrist=10, l_shoulder=250,l_elbow=-20, r_hip_angle=268,r_knee=-10,l_hip_angle=272,l_knee=-10)},
        {"t":0.20,"label":"2. 준비 (Prep)","easing":"ease_out",
         "joints":_jt(body_rotation=25,torso=90, r_shoulder=130,r_elbow=-35,r_wrist=15, l_shoulder=245,l_elbow=-25, r_hip_angle=265,r_knee=-15,l_hip_angle=275,l_knee=-15)},
        {"t":0.40,"label":"3. 스텝 인 (Step In)","easing":"ease_in",
         "joints":_jt(hip_x=-10,body_rotation=15,torso=87, r_shoulder=125,r_elbow=-25,r_wrist=10, l_shoulder=255,l_elbow=-30, r_hip_angle=268,r_knee=-10,l_hip_angle=260,l_knee=-20)},
        {"t":0.55,"label":"4. 컨택트 (Contact)","easing":"linear",
         "joints":_jt(hip_x=-15,body_rotation=5,torso=85, r_shoulder=120,r_elbow=-15,r_wrist=15, l_shoulder=260,l_elbow=-35, r_hip_angle=270,r_knee=-5,l_hip_angle=265,l_knee=-10)},
        {"t":0.75,"label":"5. 푸시 스루 (Push Through)","easing":"decelerate",
         "joints":_jt(hip_x=-20,body_rotation=-5,torso=84, r_shoulder=110,r_elbow=-10,r_wrist=10, l_shoulder=265,l_elbow=-40, r_hip_angle=272,r_knee=-5,l_hip_angle=268,l_knee=-8)},
        {"t":1.00,"label":"6. 리커버리 (Recovery)","easing":"ease_out",
         "joints":_jt(torso=88, r_shoulder=140,r_elbow=-30,r_wrist=10, l_shoulder=250,l_elbow=-20, r_hip_angle=268,r_knee=-10,l_hip_angle=272,l_knee=-10)},
    ],
},
# ──────────── 백핸드 발리 (BH Volley) ────────────
"volley_bh": {
    "name": "백핸드 발리 (BH Volley)", "output": "tennis_volley_bh.mp4",
    "ball": {"appear_t":0.35, "impact_t":0.55, "start_from":"right_edge", "post_vx":15, "post_vy":1},
    "keyframes": [
        {"t":0.00,"label":"1. 준비 (Ready)","easing":"linear",
         "joints":_jt(torso=88, r_shoulder=140,r_elbow=-30,r_wrist=10, l_shoulder=250,l_elbow=-20, r_hip_angle=268,r_knee=-10,l_hip_angle=272,l_knee=-10)},
        {"t":0.20,"label":"2. 준비 (Prep)","easing":"ease_out",
         "joints":_jt(body_rotation=-25,torso=90, r_shoulder=160,r_elbow=-35,r_wrist=5, l_shoulder=240,l_elbow=-25, r_hip_angle=275,r_knee=-15,l_hip_angle=265,l_knee=-15)},
        {"t":0.40,"label":"3. 스텝 인","easing":"ease_in",
         "joints":_jt(hip_x=-10,body_rotation=-15,torso=87, r_shoulder=150,r_elbow=-25,r_wrist=10, l_shoulder=250,l_elbow=-30, r_hip_angle=270,r_knee=-10,l_hip_angle=262,l_knee=-18)},
        {"t":0.55,"label":"4. 컨택트 (Contact)","easing":"linear",
         "joints":_jt(hip_x=-15,body_rotation=-5,torso=85, r_shoulder=135,r_elbow=-12,r_wrist=15, l_shoulder=260,l_elbow=-35, r_hip_angle=270,r_knee=-5,l_hip_angle=268,l_knee=-10)},
        {"t":0.75,"label":"5. 푸시 스루","easing":"decelerate",
         "joints":_jt(hip_x=-20,body_rotation=5,torso=84, r_shoulder=115,r_elbow=-10,r_wrist=10, l_shoulder=268,l_elbow=-40, r_hip_angle=268,r_knee=-5,l_hip_angle=272,l_knee=-8)},
        {"t":1.00,"label":"6. 리커버리","easing":"ease_out",
         "joints":_jt(torso=88, r_shoulder=140,r_elbow=-30,r_wrist=10, l_shoulder=250,l_elbow=-20, r_hip_angle=268,r_knee=-10,l_hip_angle=272,l_knee=-10)},
    ],
},
# ──────────── 오버헤드 스매시 (Smash) ────────────
"smash": {
    "name": "오버헤드 스매시 (Smash)", "output": "tennis_smash.mp4",
    "ball": {"appear_t":0.10, "impact_t":0.58, "start_from":"top", "post_vx":25, "post_vy":8},
    "keyframes": [
        {"t":0.00,"label":"1. 준비 (Ready)","easing":"linear",
         "joints":_jt()},
        {"t":0.18,"label":"2. 포지셔닝 (Position)","easing":"ease_out",
         "joints":_jt(hip_x=30,hip_y=5,body_rotation=15,torso=88, r_shoulder=200,r_elbow=-40,r_wrist=-10, l_shoulder=120,l_elbow=-10, r_hip_angle=268,r_knee=-12,l_hip_angle=272,l_knee=-12)},
        {"t":0.38,"label":"3. 준비 자세 (Loading)","easing":"ease_out",
         "joints":_jt(hip_x=20,hip_y=40,body_rotation=45,torso=100, r_shoulder=175,r_elbow=-100,r_wrist=-55, l_shoulder=110,l_elbow=-10, r_hip_angle=258,r_knee=-40,l_hip_angle=268,l_knee=-35)},
        {"t":0.48,"label":"4. 라켓 드롭","easing":"ease_in_cubic",
         "joints":_jt(hip_x=15,hip_y=25,body_rotation=35,torso=95, r_shoulder=165,r_elbow=-115,r_wrist=-65, l_shoulder=135,l_elbow=-25, r_hip_angle=262,r_knee=-22,l_hip_angle=270,l_knee=-18)},
        {"t":0.58,"label":"5. 임팩트 (Impact)","easing":"explosive",
         "joints":_jt(hip_x=0,hip_y=-45,body_rotation=0,torso=82, r_shoulder=92,r_elbow=-5,r_wrist=8, l_shoulder=245,l_elbow=-65, r_hip_angle=268,r_knee=-5,l_hip_angle=275,l_knee=-5)},
        {"t":0.78,"label":"6. 팔로우 스루","easing":"decelerate",
         "joints":_jt(hip_x=-15,hip_y=8,body_rotation=-20,torso=76, r_shoulder=225,r_elbow=-35,r_wrist=25, l_shoulder=260,l_elbow=-55, r_hip_angle=270,r_knee=-5,l_hip_angle=278,l_knee=-5)},
        {"t":1.00,"label":"7. 피니시","easing":"ease_out",
         "joints":_jt()},
    ],
},
# ──────────── 슬라이스 (Slice) ────────────
"slice": {
    "name": "슬라이스 (Slice)", "output": "tennis_slice.mp4",
    "ball": {"appear_t":0.45, "impact_t":0.62, "start_from":"right_edge", "post_vx":14, "post_vy":-1},
    "keyframes": [
        {"t":0.00,"label":"1. 준비 (Ready)","easing":"linear",
         "joints":_jt()},
        {"t":0.15,"label":"2. 스플릿 스텝","easing":"ease_out",
         "joints":_jt(hip_y=15,body_rotation=-10,torso=86, r_shoulder=255,r_elbow=-30,l_shoulder=255,l_elbow=-30, r_hip_angle=265,r_knee=-20,l_hip_angle=275,l_knee=-20)},
        {"t":0.30,"label":"3. 유닛 턴","easing":"ease_out",
         "joints":_jt(hip_x=-15,hip_y=8,body_rotation=-50,torso=90, r_shoulder=130,r_elbow=-20,r_wrist=20, l_shoulder=220,l_elbow=-25, r_hip_angle=275,r_knee=-12,l_hip_angle=262,l_knee=-12)},
        {"t":0.45,"label":"4. 높은 준비 (High Prep)","easing":"ease_in",
         "joints":_jt(hip_x=-18,hip_y=15,body_rotation=-55,torso=92, r_shoulder=120,r_elbow=-25,r_wrist=25, l_shoulder=235,l_elbow=-20, r_hip_angle=278,r_knee=-22,l_hip_angle=260,l_knee=-20)},
        {"t":0.62,"label":"5. 임팩트 (Impact)","easing":"ease_in_out",
         "joints":_jt(hip_x=5,body_rotation=-5,torso=85, r_shoulder=155,r_elbow=-15,r_wrist=20, l_shoulder=265,l_elbow=-30, r_hip_angle=270,r_knee=-5,l_hip_angle=270,l_knee=-10)},
        {"t":0.80,"label":"6. 팔로우 스루 (낮게)","easing":"decelerate",
         "joints":_jt(hip_x=10,hip_y=-5,body_rotation=15,torso=83, r_shoulder=200,r_elbow=-20,r_wrist=15, l_shoulder=270,l_elbow=-35, r_hip_angle=268,r_knee=-5,l_hip_angle=272,l_knee=-8)},
        {"t":1.00,"label":"7. 피니시","easing":"ease_out",
         "joints":_jt()},
    ],
},
}

# ═══════════════════════════════════════════════════════════════
# CLI / 대화형 메뉴
# ═══════════════════════════════════════════════════════════════
MOTION_LIST = [
    ("serve",       "서브 (Serve)"),
    ("forehand",    "포핸드 (Forehand)"),
    ("backhand_1h", "원핸드 백핸드 (1H Backhand)"),
    ("backhand_2h", "투핸드 백핸드 (2H Backhand)"),
    ("volley_fh",   "포핸드 발리 (FH Volley)"),
    ("volley_bh",   "백핸드 발리 (BH Volley)"),
    ("smash",       "오버헤드 스매시 (Smash)"),
    ("slice",       "슬라이스 (Slice)"),
]

def interactive_menu():
    print("=" * 55)
    print("  🎾 테니스 졸라맨 애니메이션 생성기")
    print("=" * 55)
    for i, (key, name) in enumerate(MOTION_LIST):
        print(f"  {i+1}. {name}")
    print(f"  9. 전체 생성 (8개 모두)")
    print(f"  0. 종료")
    print("-" * 55)
    choice = input("  번호를 선택하세요: ").strip()
    if choice == "0": sys.exit(0)
    if choice == "9": return "all"
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(MOTION_LIST):
            return MOTION_LIST[idx][0]
    except ValueError:
        pass
    print("[오류] 올바른 번호를 입력하세요.")
    return None

def main():
    parser = argparse.ArgumentParser(description="테니스 졸라맨 애니메이션 생성기 🎾")
    parser.add_argument("motion", nargs="?", default=None,
                        choices=list(MOTIONS.keys()) + ["all"],
                        help="생성할 동작 (미입력시 대화형 메뉴)")
    parser.add_argument("-o","--output", default=None, help="출력 파일 경로")
    args = parser.parse_args()

    motion_key = args.motion
    if motion_key is None:
        motion_key = interactive_menu()
        if motion_key is None: return

    if motion_key == "all":
        for key, _ in MOTION_LIST:
            m = MOTIONS[key]
            out = args.output if args.output else m["output"]
            if args.output and len(MOTION_LIST) > 1:
                base, ext = os.path.splitext(args.output)
                out = f"{base}_{key}{ext}"
            render_motion(m, out)
        print("\n[완료] ✅ 전체 8개 영상 생성 완료!")
    else:
        m = MOTIONS[motion_key]
        out = args.output if args.output else m["output"]
        render_motion(m, out)

if __name__ == "__main__":
    main()
