#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pose_extractor.py - 테니스 영상 → 졸라맨 키프레임 자동 추출기

실제 선수 영상(유튜브 URL 또는 로컬 파일)에서 MediaPipe Pose로
관절 데이터를 추출하고, tennis_animation.py 호환 키프레임을 자동 생성합니다.

사용법:
    python pose_extractor.py video.mp4                          # 로컬 영상
    python pose_extractor.py "https://youtube.com/shorts/..."   # 유튜브 URL
    python pose_extractor.py video.mp4 --name "알카라즈 서브"      # 이름 지정
    python pose_extractor.py video.mp4 --type serve             # 동작 타입 지정
    python pose_extractor.py video.mp4 --start 2.0 --end 5.5   # 구간 지정 (초)
    python pose_extractor.py video.mp4 --keyframes 7            # 키프레임 수
    python pose_extractor.py video.mp4 --preview                # 미리보기 창
    python pose_extractor.py video.mp4 -o motion.json           # JSON 출력
"""

import os, sys, math, json, argparse, subprocess
import warnings
warnings.filterwarnings("ignore")

if sys.platform.startswith('win'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError: pass

# ═══════════════════════════════════════════════════════════════
# 패키지 자동 설치 헬퍼
# ═══════════════════════════════════════════════════════════════
def _ensure_package(pkg_name, import_name=None):
    """패키지가 없으면 pip install 시도"""
    import_name = import_name or pkg_name
    try:
        __import__(import_name)
    except ImportError:
        print(f"[설치] {pkg_name} 패키지를 설치합니다...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg_name],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[설치] {pkg_name} 설치 완료")
        except Exception as e:
            print(f"[오류] {pkg_name} 설치 실패: {e}")
            print(f"       수동으로 'pip install {pkg_name}'을 실행해주세요.")
            sys.exit(1)

_ensure_package("numpy")
_ensure_package("opencv-python", "cv2")
_ensure_package("mediapipe")

import numpy as np
import cv2
import mediapipe as mp

# ═══════════════════════════════════════════════════════════════
# 상수 정의
# ═══════════════════════════════════════════════════════════════
# MediaPipe Pose 랜드마크 인덱스
LM = {
    "nose": 0,
    "l_shoulder": 11, "r_shoulder": 12,
    "l_elbow": 13, "r_elbow": 14,
    "l_wrist": 15, "r_wrist": 16,
    "l_pinky": 17, "r_pinky": 18,
    "l_index": 19, "r_index": 20,
    "l_hip": 23, "r_hip": 24,
    "l_knee": 25, "r_knee": 26,
    "l_ankle": 27, "r_ankle": 28,
}

KEY_JOINTS = [11,12,13,14,15,16,23,24,25,26,27,28]  # 필수 관절

# 동작 타입별 라벨 템플릿
LABEL_TEMPLATES = {
    "serve":   ["준비 자세 (Ready)","볼 토스 (Toss)","트로피 자세 (Trophy Pose)",
                "라켓 드롭 (Racket Drop)","임팩트 (Impact)","팔로우 스루 (Follow Through)","피니시 (Finish)"],
    "forehand": ["준비 자세 (Ready)","스플릿 스텝 (Split Step)","유닛 턴 (Unit Turn)",
                 "라켓 드롭 (Racket Drop)","임팩트 (Impact)","팔로우 스루 (Follow Through)","피니시 (Finish)"],
    "backhand": ["준비 자세 (Ready)","스플릿 스텝 (Split Step)","유닛 턴 (Unit Turn)",
                 "라켓 드롭 (Racket Drop)","임팩트 (Impact)","팔로우 스루 (Follow Through)","피니시 (Finish)"],
    "volley":  ["준비 자세 (Ready)","준비 동작 (Prep)","스텝 인 (Step In)",
                "컨택트 (Contact)","푸시 스루 (Push Through)","리커버리 (Recovery)"],
    "smash":   ["준비 (Ready)","포지셔닝 (Position)","로딩 (Loading)",
                "라켓 드롭 (Racket Drop)","임팩트 (Impact)","팔로우 스루 (Follow Through)","피니시 (Finish)"],
    "slice":   ["준비 (Ready)","유닛 턴 (Unit Turn)","높은 준비 (High Prep)",
                "포워드 스윙 (Forward Swing)","임팩트 (Impact)","팔로우 스루 (낮게)","피니시 (Finish)"],
}

# 공 파라미터 기본값
BALL_DEFAULTS = {
    "serve":    {"start_from":"left_wrist","post_vx":22,"post_vy":4,"appear_offset":-0.50},
    "forehand": {"start_from":"right_edge","post_vx":20,"post_vy":-3,"appear_offset":-0.15},
    "backhand": {"start_from":"right_edge","post_vx":18,"post_vy":-2,"appear_offset":-0.15},
    "volley":   {"start_from":"right_edge","post_vx":16,"post_vy":1,"appear_offset":-0.20},
    "smash":    {"start_from":"top","post_vx":25,"post_vy":8,"appear_offset":-0.48},
    "slice":    {"start_from":"right_edge","post_vx":14,"post_vy":-1,"appear_offset":-0.17},
}

# ═══════════════════════════════════════════════════════════════
# 1. 비디오 입력 모듈
# ═══════════════════════════════════════════════════════════════
def download_youtube(url, output_dir="./temp_videos"):
    """YouTube/Instagram URL → 로컬 파일 다운로드"""
    _ensure_package("yt-dlp", "yt_dlp")
    import yt_dlp

    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, "%(title).50s.%(ext)s")

    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': output_template,
        'no_warnings': True, 'quiet': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    }
    print(f"[다운로드] 영상 다운로드 중: {url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
    print(f"[다운로드] 완료: {filepath}")
    return filepath

def load_video(source, start_sec=None, end_sec=None):
    """영상 로드 및 프레임 범위 설정. (path, fps, total_frames, start_frame, end_frame) 반환"""
    # URL 판별
    if source.startswith("http://") or source.startswith("https://"):
        source = download_youtube(source)

    if not os.path.isfile(source):
        print(f"[오류] 파일을 찾을 수 없습니다: {source}")
        sys.exit(1)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[오류] 영상을 열 수 없습니다: {source}")
        print(f"       파일이 손상되었거나 코덱이 지원되지 않을 수 있습니다.")
        sys.exit(1)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        print(f"[오류] 영상 프레임을 읽을 수 없습니다 (프레임 수: {total})")
        sys.exit(1)
    cap.release()

    start_f = int(start_sec * fps) if start_sec else 0
    end_f = int(end_sec * fps) if end_sec else total
    start_f = max(0, min(start_f, total - 1))
    end_f = max(start_f + 1, min(end_f, total))

    print(f"[영상 정보] {os.path.basename(source)}")
    print(f"   FPS: {fps:.1f} | 총 프레임: {total} | 길이: {total/fps:.1f}초")
    print(f"   추출 범위: {start_f}~{end_f} 프레임 ({(end_f-start_f)/fps:.1f}초)")
    return source, fps, total, start_f, end_f

# ═══════════════════════════════════════════════════════════════
# 2. 포즈 추출 모듈 (MediaPipe)
# ═══════════════════════════════════════════════════════════════
def extract_poses(video_path, start_frame, end_frame, show_preview=False):
    """MediaPipe Pose로 프레임별 랜드마크 추출. (N, 33, 4) ndarray 반환."""
    mp_pose = mp.solutions.pose
    mp_draw = mp.solutions.drawing_utils if show_preview else None

    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    all_landmarks = []
    n_frames = end_frame - start_frame
    detected = 0

    print(f"[포즈 추출] MediaPipe Pose 실행 중 (model_complexity=2)...")

    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        for i in range(n_frames):
            ret, frame = cap.read()
            if not ret:
                all_landmarks.append(None)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb)

            if result.pose_landmarks:
                lm = np.array([[l.x, l.y, l.z, l.visibility]
                               for l in result.pose_landmarks.landmark])
                # 핵심 관절 신뢰도 체크
                key_vis = np.mean([lm[j][3] for j in KEY_JOINTS])
                if key_vis < 0.3:
                    all_landmarks.append(None)
                else:
                    all_landmarks.append(lm)
                    detected += 1
            else:
                all_landmarks.append(None)

            if show_preview and result.pose_landmarks:
                mp_draw.draw_landmarks(frame, result.pose_landmarks,
                                       mp_pose.POSE_CONNECTIONS)
                cv2.imshow("Pose Preview", frame)
                if cv2.waitKey(1) & 0xFF == 27: break  # ESC

            if (i + 1) % 50 == 0 or i == n_frames - 1:
                print(f"   {i+1}/{n_frames} 프레임 처리 ({detected}개 감지)")

    cap.release()
    if show_preview:
        cv2.destroyAllWindows()

    print(f"[포즈 추출 완료] {detected}/{n_frames} 프레임 감지 ({detected/max(n_frames,1)*100:.1f}%)")

    # None 프레임 보간 (전후 유효 프레임에서 선형 보간)
    all_landmarks = _interpolate_missing(all_landmarks)
    return all_landmarks, n_frames

def _interpolate_missing(landmarks_list):
    """None인 프레임을 전후 유효 프레임에서 선형 보간"""
    n = len(landmarks_list)
    # 유효 인덱스 목록
    valid_indices = [i for i in range(n) if landmarks_list[i] is not None]
    if not valid_indices:
        print("[경고] 포즈가 감지된 프레임이 없습니다!")
        return landmarks_list
    if len(valid_indices) == n:
        return landmarks_list

    # 첫/마지막 유효값으로 앞뒤 채우기
    for i in range(valid_indices[0]):
        landmarks_list[i] = landmarks_list[valid_indices[0]].copy()
    for i in range(valid_indices[-1]+1, n):
        landmarks_list[i] = landmarks_list[valid_indices[-1]].copy()

    # 중간 빈 프레임 선형 보간
    for idx in range(len(valid_indices)-1):
        i0, i1 = valid_indices[idx], valid_indices[idx+1]
        if i1 - i0 <= 1: continue
        for i in range(i0+1, i1):
            alpha = (i - i0) / (i1 - i0)
            landmarks_list[i] = (1 - alpha) * landmarks_list[i0] + alpha * landmarks_list[i1]

    interpolated = sum(1 for x in landmarks_list if x is None)
    if interpolated > 0:
        print(f"[보간] {interpolated}개 프레임이 여전히 None — 대체 불가 구간")
    return landmarks_list

# ═══════════════════════════════════════════════════════════════
# 3. 시간 축 스무딩
# ═══════════════════════════════════════════════════════════════
def smooth_landmarks(landmarks_list, sigma=2.0):
    """가우시안 시간축 스무딩. landmarks_list는 ndarray 리스트."""
    from scipy.ndimage import gaussian_filter1d

    valid = [i for i in range(len(landmarks_list)) if landmarks_list[i] is not None]
    if len(valid) < 5:
        return landmarks_list

    # numpy 배열로 변환
    arr = np.stack([landmarks_list[i] for i in valid])  # (V, 33, 4)
    # x, y, z에만 스무딩 적용 (visibility는 유지)
    for coord in range(3):
        arr[:, :, coord] = gaussian_filter1d(arr[:, :, coord], sigma=sigma, axis=0)

    result = [lm.copy() if lm is not None else None for lm in landmarks_list]
    for idx_in_valid, orig_idx in enumerate(valid):
        result[orig_idx] = arr[idx_in_valid]
    return result

def smooth_landmarks_simple(landmarks_list, window=5):
    """scipy 없을 때 간단한 이동 평균 스무딩"""
    valid = [i for i in range(len(landmarks_list)) if landmarks_list[i] is not None]
    if len(valid) < window:
        return landmarks_list

    arr = np.stack([landmarks_list[i] for i in valid])
    result_arr = arr.copy()
    half = window // 2
    for i in range(len(arr)):
        lo = max(0, i - half)
        hi = min(len(arr), i + half + 1)
        result_arr[i, :, :3] = np.mean(arr[lo:hi, :, :3], axis=0)

    result = [lm.copy() if lm is not None else None for lm in landmarks_list]
    for idx_in_valid, orig_idx in enumerate(valid):
        result[orig_idx] = result_arr[idx_in_valid]
    return result

def apply_smoothing(landmarks_list, sigma=2.0):
    """스무딩 적용 (scipy 있으면 가우시안, 없으면 이동평균)"""
    try:
        from scipy.ndimage import gaussian_filter1d
        return smooth_landmarks(landmarks_list, sigma)
    except ImportError:
        print("[정보] scipy 미설치 → 간단한 이동 평균 스무딩 사용")
        return smooth_landmarks_simple(landmarks_list)

# ═══════════════════════════════════════════════════════════════
# 4. 좌표 → 각도 변환
# ═══════════════════════════════════════════════════════════════
def calc_angle(start, end):
    """두 점 사이의 각도 (도). 0°=오른쪽, 90°=위, 180°=왼쪽, 270°=아래."""
    dx = end[0] - start[0]
    dy = -(end[1] - start[1])  # 화면 y축 반전
    return math.degrees(math.atan2(dy, dx)) % 360

def calc_relative_angle(parent_abs, child_start, child_end):
    """부모 세그먼트 대비 자식 각도 (상대 각도)."""
    child_abs = calc_angle(child_start, child_end)
    rel = ((child_abs - parent_abs + 180) % 360) - 180
    return rel

def landmarks_to_angles(landmarks_list):
    """프레임별 랜드마크 → 프레임별 관절 각도 딕셔너리 리스트 반환."""
    n = len(landmarks_list)
    angles_list = []

    # 기준값 계산을 위한 사전 패스
    hip_centers = []
    shoulder_dists = []
    for lm in landmarks_list:
        if lm is None:
            hip_centers.append(None)
            shoulder_dists.append(None)
            continue
        hc = (lm[23][:2] + lm[24][:2]) / 2.0
        sd = np.linalg.norm(lm[11][:2] - lm[12][:2])
        hip_centers.append(hc)
        shoulder_dists.append(sd)

    # 유효 값들의 통계
    valid_hcs = [hc for hc in hip_centers if hc is not None]
    valid_sds = [sd for sd in shoulder_dists if sd is not None]
    avg_hip_center = np.mean(valid_hcs, axis=0) if valid_hcs else np.array([0.5, 0.5])
    max_shoulder_dist = max(valid_sds) if valid_sds else 0.15
    median_hip_y = float(np.median([hc[1] for hc in valid_hcs])) if valid_hcs else 0.5

    # 사람 키 추정 (정규화 좌표에서)
    all_heights = []
    for lm in landmarks_list:
        if lm is None: continue
        head_y = lm[0][1]
        ankle_y = max(lm[27][1], lm[28][1])
        all_heights.append(ankle_y - head_y)
    person_height = np.median(all_heights) if all_heights else 0.5
    hip_scale = 130.0 / max(person_height, 0.1)  # 정규화→ tennism_animation.py hip 스케일

    print(f"[각도 변환] 기준 어깨폭: {max_shoulder_dist:.3f} | 사람 높이: {person_height:.3f}")

    for i, lm in enumerate(landmarks_list):
        if lm is None:
            angles_list.append(None)
            continue

        # 편의 함수
        def p(idx): return lm[idx][:2]  # (x, y)

        hip_center = (p(23) + p(24)) / 2.0
        shoulder_center = (p(11) + p(12)) / 2.0

        # 몸통 각도
        torso_deg = calc_angle(hip_center, shoulder_center)

        # 어깨 회전 추정
        sd = np.linalg.norm(p(11) - p(12))
        ratio = np.clip(sd / max(max_shoulder_dist, 0.01), 0.25, 1.0)
        rot_mag = math.degrees(math.acos(ratio))
        # 회전 방향 결정: z좌표 + x변위 복합 판단
        z_reliable = min(lm[11][3], lm[12][3]) > 0.5  # 양 어깨 가시성
        if z_reliable and abs(lm[12][2] - lm[11][2]) > 0.01:
            rot_sign = -1 if lm[12][2] > lm[11][2] else 1
        else:
            # 폴백: 어깨 중심 vs 골반 중심의 x 변위
            sh_cx = (lm[11][0] + lm[12][0]) / 2
            hp_cx = (lm[23][0] + lm[24][0]) / 2
            rot_sign = 1 if sh_cx > hp_cx else -1
        body_rotation = rot_sign * rot_mag

        # 오른팔 (라켓 팔)
        r_shoulder_abs = calc_angle(p(12), p(14))
        r_elbow_rel = calc_relative_angle(r_shoulder_abs, p(14), p(16))
        # 손목 각도 (검지→손끝 방향으로 추정, 핀키 폴백)
        forearm_abs = calc_angle(p(14), p(16))
        r_wrist_rel = 0.0
        if lm[20][3] > 0.3:  # r_index 가시성
            r_wrist_rel = calc_relative_angle(forearm_abs, p(16), p(20))
        elif lm[18][3] > 0.3:  # r_pinky 폴백
            r_wrist_rel = calc_relative_angle(forearm_abs, p(16), p(18))
        elif lm[20][3] > 0.1 and lm[18][3] > 0.1:  # 두 점 중간값
            mid = (p(20) + p(18)) / 2.0
            r_wrist_rel = calc_relative_angle(forearm_abs, p(16), mid)
        r_wrist_rel = np.clip(r_wrist_rel, -80, 80)

        # 왼팔
        l_shoulder_abs = calc_angle(p(11), p(13))
        l_elbow_rel = calc_relative_angle(l_shoulder_abs, p(13), p(15))

        # 오른다리
        r_hip_abs = calc_angle(p(24), p(26))
        r_knee_rel = calc_relative_angle(r_hip_abs, p(26), p(28))

        # 왼다리
        l_hip_abs = calc_angle(p(23), p(25))
        l_knee_rel = calc_relative_angle(l_hip_abs, p(25), p(27))

        # 골반 이동량 (정규화 좌표 → tennis_animation 스케일)
        hip_x = (hip_center[0] - avg_hip_center[0]) * hip_scale
        hip_y = (hip_center[1] - median_hip_y) * hip_scale  # 중앙값 기준 (음수=점프, 양수=앉기)

        # 범위 클램핑
        hip_x = np.clip(hip_x, -55, 55)
        hip_y = np.clip(hip_y, -60, 60)
        body_rotation = np.clip(body_rotation, -90, 90)
        r_elbow_rel = np.clip(r_elbow_rel, -150, 10)
        l_elbow_rel = np.clip(l_elbow_rel, -150, 10)
        r_knee_rel = np.clip(r_knee_rel, -90, 10)
        l_knee_rel = np.clip(l_knee_rel, -90, 10)

        angles_list.append({
            "hip_x": int(round(float(hip_x))),
            "hip_y": int(round(float(hip_y))),
            "body_rotation": int(round(float(body_rotation))),
            "torso": int(round(float(torso_deg))),
            "r_shoulder": int(round(float(r_shoulder_abs))),
            "r_elbow": int(round(float(r_elbow_rel))),
            "r_wrist": int(round(float(r_wrist_rel))),
            "l_shoulder": int(round(float(l_shoulder_abs))),
            "l_elbow": int(round(float(l_elbow_rel))),
            "r_hip_angle": int(round(float(r_hip_abs))),
            "r_knee": int(round(float(r_knee_rel))),
            "l_hip_angle": int(round(float(l_hip_abs))),
            "l_knee": int(round(float(l_knee_rel))),
        })

    # None 보간
    valid_idx = [i for i in range(n) if angles_list[i] is not None]
    if len(valid_idx) < n and valid_idx:
        # 앞뒤 채우기
        for i in range(valid_idx[0]):
            angles_list[i] = angles_list[valid_idx[0]].copy()
        for i in range(valid_idx[-1]+1, n):
            angles_list[i] = angles_list[valid_idx[-1]].copy()
        # 중간 보간
        for vi in range(len(valid_idx)-1):
            i0, i1 = valid_idx[vi], valid_idx[vi+1]
            if i1 - i0 <= 1: continue
            a0, a1 = angles_list[i0], angles_list[i1]
            for i in range(i0+1, i1):
                alpha = (i - i0) / (i1 - i0)
                angles_list[i] = {k: int(round(a0[k] + (a1[k] - a0[k]) * alpha)) for k in a0}

    # 통계 요약 출력
    valid_angles = [a for a in angles_list if a is not None]
    if valid_angles:
        print(f"[각도 변환 완료] {len(valid_angles)} 프레임 변환됨")
        print(f"   ┌─── 주요 각도 범위 (min ~ max) ───")
        for key in ["torso","r_shoulder","r_elbow","body_rotation","hip_x","hip_y"]:
            vals = [a[key] for a in valid_angles]
            print(f"   │ {key:15s}: {min(vals):6.0f}° ~ {max(vals):6.0f}° (평균 {np.mean(vals):6.0f}°)")
        print(f"   └─────────────────────────────────")
    else:
        print(f"[각도 변환 완료] 유효 프레임 없음")
    return angles_list

# ═══════════════════════════════════════════════════════════════
# 5. 키프레임 자동 감지
# ═══════════════════════════════════════════════════════════════
def detect_keyframes(angles_list, num_keyframes=7, min_spacing_ratio=0.04):
    """각도 변화 속도 기반 키프레임 자동 감지. 프레임 인덱스 리스트 반환."""
    n = len(angles_list)
    if n < num_keyframes:
        return list(range(n)), np.zeros(n), n // 2

    # 프레임간 각도 변화량 (속도) 계산
    velocities = np.zeros(n)
    for i in range(1, n):
        if angles_list[i] is None or angles_list[i-1] is None:
            continue
        v = 0.0
        for key in ["r_shoulder", "r_elbow", "r_wrist", "hip_x", "hip_y", "body_rotation"]:
            diff = angles_list[i][key] - angles_list[i-1][key]
            v += diff * diff
        velocities[i] = math.sqrt(v)

    # 스무딩
    kernel = np.ones(7) / 7
    if len(velocities) >= 7:
        velocities_smooth = np.convolve(velocities, kernel, mode='same')
    else:
        velocities_smooth = velocities

    # 가속도 (속도의 미분)
    acceleration = np.gradient(velocities_smooth)

    min_spacing = max(int(n * min_spacing_ratio), 2)

    # 후보 지점: 속도 극값 + 가속도 부호 변경점
    candidates = set()

    # 속도 로컬 극값
    for i in range(1, n-1):
        if velocities_smooth[i] > velocities_smooth[i-1] and velocities_smooth[i] > velocities_smooth[i+1]:
            candidates.add(i)  # 속도 극대 (임팩트 근처)
        if velocities_smooth[i] < velocities_smooth[i-1] and velocities_smooth[i] < velocities_smooth[i+1]:
            candidates.add(i)  # 속도 극소 (정지/전환점)

    # 가속도 부호 변경점
    for i in range(1, n):
        if acceleration[i] * acceleration[i-1] < 0:
            candidates.add(i)

    # 첫/마지막 프레임은 항상 포함
    candidates.add(0)
    candidates.add(n-1)

    # 중요도 점수 계산 (속도 극대 > 가속도 변경 > 속도 극소)
    scored = []
    for c in candidates:
        score = velocities_smooth[c] + abs(acceleration[c]) * 0.3
        scored.append((c, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    # 최소 간격 유지하며 선별
    selected = [0, n-1]
    for frame_idx, score in scored:
        if len(selected) >= num_keyframes:
            break
        if all(abs(frame_idx - s) >= min_spacing for s in selected):
            selected.append(frame_idx)

    # 부족하면 균등 분할로 보충
    while len(selected) < num_keyframes:
        # 가장 넓은 간격 찾기
        selected_sorted = sorted(selected)
        max_gap, insert_at = 0, 0
        for i in range(len(selected_sorted)-1):
            gap = selected_sorted[i+1] - selected_sorted[i]
            if gap > max_gap:
                max_gap = gap
                insert_at = (selected_sorted[i] + selected_sorted[i+1]) // 2
        if insert_at not in selected:
            selected.append(insert_at)
        else:
            break

    selected = sorted(set(selected))[:num_keyframes]
    # 첫/마지막 보장
    if 0 not in selected: selected[0] = 0
    if n-1 not in selected: selected[-1] = n-1

    selected.sort()

    # 임팩트 프레임 찾기 (최대 속도 시점)
    impact_frame = int(np.argmax(velocities_smooth))
    # selected에서 가장 가까운 프레임을 임팩트로 표시
    closest_to_impact = min(selected, key=lambda x: abs(x - impact_frame))
    impact_idx_in_selected = selected.index(closest_to_impact)

    print(f"[키프레임 감지] 감지된 키프레임: {selected}")
    print(f"   추정 임팩트: 프레임 {impact_frame} (키프레임 #{impact_idx_in_selected+1})")

    return selected, velocities_smooth, impact_idx_in_selected

# ═══════════════════════════════════════════════════════════════
# 6. Easing 자동 할당
# ═══════════════════════════════════════════════════════════════
def assign_easings(keyframe_indices, velocities, impact_kf_idx):
    """키프레임 간 속도 프로파일 기반 이징 할당."""
    impact_kf_idx = min(impact_kf_idx, len(keyframe_indices) - 1)
    easings = ["linear"]  # 첫 키프레임

    for i in range(1, len(keyframe_indices)):
        f0, f1 = keyframe_indices[i-1], keyframe_indices[i]
        segment_vel = velocities[f0:f1+1]
        avg_vel = np.mean(segment_vel) if len(segment_vel) > 0 else 0
        vel_trend = segment_vel[-1] - segment_vel[0] if len(segment_vel) > 1 else 0

        if i == impact_kf_idx:
            easings.append("explosive")
        elif i == len(keyframe_indices) - 1:
            easings.append("ease_out")
        elif i == impact_kf_idx + 1:
            easings.append("decelerate")
        elif vel_trend > 0.5:
            easings.append("ease_in" if avg_vel < np.median(velocities) else "ease_in_cubic")
        elif vel_trend < -0.5:
            easings.append("ease_out_cubic" if abs(vel_trend) > 1.0 else "decelerate")
        else:
            easings.append("ease_in_out")

    return easings

# ═══════════════════════════════════════════════════════════════
# 7. 라벨 생성
# ═══════════════════════════════════════════════════════════════
def generate_labels(num_keyframes, motion_type="forehand"):
    """동작 타입에 맞는 한국어 라벨 생성."""
    base = motion_type.replace("_1h","").replace("_2h","").replace("_fh","").replace("_bh","")
    if base not in LABEL_TEMPLATES:
        base = "forehand"
    template = LABEL_TEMPLATES[base]

    if num_keyframes == len(template):
        return [f"{i+1}. {t}" for i, t in enumerate(template)]
    elif num_keyframes < len(template):
        # 앞뒤 유지, 중간 균등 선택
        labels = [template[0], template[-1]]
        step = (len(template) - 2) / max(num_keyframes - 2, 1)
        for i in range(1, num_keyframes - 1):
            idx = min(int(1 + i * step), len(template) - 2)
            labels.insert(-1, template[idx])
        return [f"{i+1}. {l}" for i, l in enumerate(labels)]
    else:
        # 템플릿보다 많으면 번호만
        labels = []
        for i in range(num_keyframes):
            ratio = i / max(num_keyframes - 1, 1)
            template_idx = min(int(ratio * (len(template) - 1)), len(template) - 1)
            labels.append(f"{i+1}. {template[template_idx]}")
        return labels

# ═══════════════════════════════════════════════════════════════
# 8. 최종 출력 생성
# ═══════════════════════════════════════════════════════════════
def build_output(angles_list, keyframe_indices, easings, labels, velocities,
                 impact_kf_idx, motion_name, motion_type, output_filename,
                 source_video, fps, n_frames):
    """JSON + Python snippet 출력 생성."""

    # 키프레임 데이터 구성
    kf_data = []
    for i, fi in enumerate(keyframe_indices):
        t = fi / max(n_frames - 1, 1)
        kf_data.append({
            "t": round(t, 3),
            "label": labels[i],
            "easing": easings[i],
            "source_frame": fi,
            "joints": angles_list[fi],
        })

    # 공 파라미터 추정
    base_type = motion_type.replace("_1h","").replace("_2h","").replace("_fh","").replace("_bh","")
    ball_defaults = BALL_DEFAULTS.get(base_type, BALL_DEFAULTS["forehand"])
    impact_t = kf_data[impact_kf_idx]["t"] if impact_kf_idx < len(kf_data) else 0.6
    appear_t = max(0.0, impact_t + ball_defaults["appear_offset"])

    ball_config = {
        "appear_t": round(appear_t, 2),
        "impact_t": round(impact_t, 2),
        "start_from": ball_defaults["start_from"],
        "post_vx": ball_defaults["post_vx"],
        "post_vy": ball_defaults["post_vy"],
    }

    # 안전한 출력 파일명
    safe_name = "".join(c for c in motion_name if c.isalnum() or c in (' ','_','-','(',')') ).strip()
    if not output_filename:
        output_filename = f"tennis_{safe_name.replace(' ','_')}.mp4"

    result = {
        "name": motion_name,
        "output": output_filename,
        "source_video": source_video,
        "source_fps": fps,
        "source_frames": n_frames,
        "ball": ball_config,
        "keyframes": kf_data,
    }

    return result

def save_json(result, json_path):
    """JSON 파일 저장."""
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[저장] JSON 저장 완료: {json_path}")

def print_python_snippet(result):
    """tennis_animation.py에 복사-붙여넣기 가능한 Python dict 출력."""
    name = result["name"]
    output = result["output"]
    ball = result["ball"]
    kfs = result["keyframes"]

    print("\n" + "=" * 65)
    print(" 📋 tennis_animation.py에 붙여넣을 코드 (MOTIONS dict에 추가)")
    print("=" * 65)

    key = output.replace("tennis_","").replace(".mp4","").replace(" ","_")
    print(f'\n"{key}": {{')
    print(f'    "name": "{name}", "output": "{output}",')
    print(f'    "ball": {json.dumps(ball)},')
    print(f'    "keyframes": [')

    for kf in kfs:
        j = kf["joints"]
        print(f'        {{"t":{kf["t"]:.3f},"label":"{kf["label"]}","easing":"{kf["easing"]}",')
        args_str = (f'hip_x={j["hip_x"]},hip_y={j["hip_y"]},body_rotation={j["body_rotation"]},'
                   f'torso={j["torso"]},r_shoulder={j["r_shoulder"]},r_elbow={j["r_elbow"]},'
                   f'r_wrist={j["r_wrist"]},l_shoulder={j["l_shoulder"]},l_elbow={j["l_elbow"]},'
                   f'r_hip_angle={j["r_hip_angle"]},r_knee={j["r_knee"]},'
                   f'l_hip_angle={j["l_hip_angle"]},l_knee={j["l_knee"]}')
        print(f'         "joints":_jt({args_str})}},')

    print('    ],')
    print('},')
    print("=" * 65)

# ═══════════════════════════════════════════════════════════════
# 메인 파이프라인
# ═══════════════════════════════════════════════════════════════
def _auto_suggest_type(landmarks_list):
    """랜드마크 궤적으로 동작 타입 자동 추정 (참고용 출력)."""
    valid = [lm for lm in landmarks_list if lm is not None]
    if len(valid) < 10:
        return
    # 오른손목 y 궤적 분석
    r_wrist_y = [lm[16][1] for lm in valid]
    r_wrist_x = [lm[16][0] for lm in valid]
    min_y = min(r_wrist_y)
    max_y = max(r_wrist_y)
    y_range = max_y - min_y
    x_start = np.mean(r_wrist_x[:len(r_wrist_x)//4])
    x_end = np.mean(r_wrist_x[3*len(r_wrist_x)//4:])
    x_direction = x_end - x_start  # 양수 = 오른쪽으로 이동

    # 가장 높은 지점의 위치 (비율)
    min_y_pos = r_wrist_y.index(min_y) / len(r_wrist_y)

    suggestion = "forehand"
    reason = ""
    if y_range > 0.3 and min_y < 0.2:  # 손이 매우 높이 올라감
        if min_y_pos > 0.4:  # 후반부에 높이 올라감
            suggestion = "serve"
            reason = "손목이 매우 높이 올라감 + 후반부 최고점"
        else:
            suggestion = "smash"
            reason = "손목이 매우 높이 올라감 + 전반부 최고점"
    elif x_direction > 0.1:
        suggestion = "forehand"
        reason = f"오른손이 왼→오른쪽으로 이동 (Δx={x_direction:.2f})"
    elif x_direction < -0.1:
        if y_range > 0.15 and min_y < 0.35:
            suggestion = "slice"
            reason = f"오른손이 높→낮 + 오른→왼쪽 (Δx={x_direction:.2f})"
        else:
            suggestion = "backhand"
            reason = f"오른손이 오른→왼쪽으로 이동 (Δx={x_direction:.2f})"
    else:
        suggestion = "volley"
        reason = f"손목 이동 범위 작음 (Δx={x_direction:.2f})"

    print(f"[타입 추정] 💡 감지된 동작: {suggestion} ({reason})")
    print(f"           --type {suggestion} 으로 지정하면 라벨이 자동 매칭됩니다.")

def run_pipeline(source, output_json=None, motion_name=None, motion_type="forehand",
                 start_sec=None, end_sec=None, num_keyframes=7, preview=False,
                 smoothing_sigma=2.0, mirror=False):
    """전체 파이프라인 실행."""
    print("=" * 60)
    print("  🎾 테니스 포즈 추출기 (pose_extractor.py)")
    print("=" * 60)

    # 1. 비디오 로드
    video_path, fps, total, start_f, end_f = load_video(source, start_sec, end_sec)

    # 2. 포즈 추출
    landmarks_raw, n_frames = extract_poses(video_path, start_f, end_f, preview)

    # 2.5. 좌우 반전 (--mirror)
    if mirror:
        print("[반전] 좌우 미러링 적용 중...")
        for i in range(len(landmarks_raw)):
            if landmarks_raw[i] is not None:
                lm = landmarks_raw[i].copy()
                lm[:, 0] = 1.0 - lm[:, 0]  # x좌표 반전
                lm[:, 2] = -lm[:, 2]        # z좌표 반전
                # L↔R 스왑
                swap_pairs = [(11,12),(13,14),(15,16),(17,18),(19,20),(23,24),(25,26),(27,28)]
                for a, b in swap_pairs:
                    lm[[a,b]] = lm[[b,a]]
                landmarks_raw[i] = lm

    # 3. 스무딩
    print("[스무딩] 시간축 가우시안 필터 적용 중...")
    landmarks_smooth = apply_smoothing(landmarks_raw, smoothing_sigma)

    # 3.5 동작 타입 자동 추정
    _auto_suggest_type(landmarks_smooth)

    # 4. 각도 변환
    angles_list = landmarks_to_angles(landmarks_smooth)

    # None 체크 + 짧은 영상 경고
    valid_count = sum(1 for a in angles_list if a is not None)
    if valid_count < 5:
        print(f"[오류] 유효한 프레임이 {valid_count}개밖에 없습니다. 최소 5개 필요합니다.")
        sys.exit(1)
    if valid_count < num_keyframes:
        print(f"[경고] 유효 프레임({valid_count})이 요청 키프레임 수({num_keyframes})보다 적습니다.")
        num_keyframes = max(3, valid_count // 2)
        print(f"        키프레임 수를 {num_keyframes}개로 자동 축소합니다.")

    # 5. 키프레임 감지
    kf_indices, velocities, impact_idx = detect_keyframes(angles_list, num_keyframes)

    # 6. Easing 할당
    easings = assign_easings(kf_indices, velocities, impact_idx)

    # 7. 라벨 생성
    labels = generate_labels(len(kf_indices), motion_type)

    # 8. 출력 생성
    if not motion_name:
        motion_name = f"커스텀 {motion_type} 모션"
    output_filename = f"tennis_{motion_type}.mp4"

    result = build_output(
        angles_list, kf_indices, easings, labels, velocities,
        impact_idx, motion_name, motion_type, output_filename,
        os.path.basename(video_path), fps, n_frames
    )

    # JSON 저장
    if not output_json:
        output_json = f"motion_{motion_type}.json"
    save_json(result, output_json)

    # Python 코드 출력
    print_python_snippet(result)

    # 통합 가이드 출력
    print_integration_guide(output_json, motion_type)

    return result

# ═══════════════════════════════════════════════════════════════
# JSON 로더 (tennis_animation.py 연동용)
# ═══════════════════════════════════════════════════════════════
def load_motion_from_json(json_path):
    """JSON 파일에서 모션 데이터를 로드하여 tennis_animation.py 호환 dict 반환."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

# ═══════════════════════════════════════════════════════════════
# tennis_animation.py 통합 헬퍼
# ═══════════════════════════════════════════════════════════════
def integrate_with_tennis_animation(json_path):
    """
    JSON 파일을 로드하여 tennis_animation.py MOTIONS 호환 dict 반환.
    
    사용 예시 (tennis_animation.py 내에서):
        from pose_extractor import integrate_with_tennis_animation
        custom = integrate_with_tennis_animation("motion_serve.json")
        MOTIONS["custom_serve"] = custom
        render_motion(custom, custom["output"])
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # tennis_animation.py 형식으로 변환
    motion = {
        "name": data["name"],
        "output": data["output"],
        "ball": data.get("ball", {}),
        "keyframes": [],
    }
    for kf in data["keyframes"]:
        motion["keyframes"].append({
            "t": kf["t"],
            "label": kf["label"],
            "easing": kf["easing"],
            "joints": kf["joints"],
        })
    return motion

def print_integration_guide(json_path, motion_type):
    """통합 가이드 출력."""
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  📖 tennis_animation.py 연동 가이드                          ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  방법 1: Python 코드 직접 붙여넣기                              ║
║  ─────────────────────────────────────────────────            ║
║  위에 출력된 코드를 tennis_animation.py의                       ║
║  MOTIONS 딕셔너리에 추가하세요.                                  ║
║                                                              ║
║  방법 2: JSON 파일 로드 (권장)                                  ║
║  ─────────────────────────────────────────────────            ║
║  tennis_animation.py에 다음 코드를 추가하세요:                   ║
║                                                              ║
║    from pose_extractor import integrate_with_tennis_animation ║
║    custom = integrate_with_tennis_animation("{json_path}")     ║
║    MOTIONS["custom_{motion_type}"] = custom                    ║
║                                                              ║
║  그런 다음:                                                    ║
║    python tennis_animation.py custom_{motion_type}             ║
║                                                              ║
║  방법 3: 커맨드라인에서 바로 렌더링                               ║
║  ─────────────────────────────────────────────────            ║
║    python -c "                                                ║
║    from pose_extractor import integrate_with_tennis_animation  ║
║    from tennis_animation import render_motion                  ║
║    m = integrate_with_tennis_animation('{json_path}')          ║
║    render_motion(m, m['output'])"                              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝""")

# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="🎾 테니스 영상 → 졸라맨 키프레임 자동 추출기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python pose_extractor.py video.mp4
  python pose_extractor.py "https://youtube.com/shorts/xxx"
  python pose_extractor.py video.mp4 --name "알카라즈 서브" --type serve
  python pose_extractor.py video.mp4 --start 2.0 --end 5.5 --keyframes 7
        """)
    parser.add_argument("source", help="영상 경로 또는 YouTube URL")
    parser.add_argument("-o", "--output", default=None, help="출력 JSON 파일 경로")
    parser.add_argument("--name", default=None, help="모션 이름 (예: '알카라즈 서브')")
    parser.add_argument("--type", default="forehand",
                        choices=["serve","forehand","backhand","volley","smash","slice"],
                        help="동작 타입 (라벨/공 파라미터 결정)")
    parser.add_argument("--start", type=float, default=None, help="시작 시간 (초)")
    parser.add_argument("--end", type=float, default=None, help="종료 시간 (초)")
    parser.add_argument("--keyframes", type=int, default=7, help="추출할 키프레임 수 (기본: 7)")
    parser.add_argument("--preview", action="store_true", help="추출 중 미리보기 창 표시")
    parser.add_argument("--sigma", type=float, default=2.0, help="스무딩 sigma (기본: 2.0)")
    parser.add_argument("--mirror", action="store_true", help="좌우 반전 (반대쪽 촬영 영상용)")

    args = parser.parse_args()

    run_pipeline(
        source=args.source,
        output_json=args.output,
        motion_name=args.name,
        motion_type=args.type,
        start_sec=args.start,
        end_sec=args.end,
        num_keyframes=args.keyframes,
        preview=args.preview,
        smoothing_sigma=args.sigma,
        mirror=args.mirror,
    )

if __name__ == "__main__":
    main()
