import cv2
import mediapipe as mp
import numpy as np
import math
from types import SimpleNamespace

MODEL_PATH = "pose_landmarker_full.task"
video_path = r"C:\Users\박범서\Downloads\federer_forehand_input.mp4"

# Set up MediaPipe Pose Landmarker
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
options = vision.PoseLandmarkerOptions(
    base_options=base_options,
    running_mode=vision.RunningMode.VIDEO,
    num_poses=1,
    min_pose_detection_confidence=0.5,
    min_pose_presence_confidence=0.5,
    min_tracking_confidence=0.5,
)
landmarker = vision.PoseLandmarker.create_from_options(options)

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print("Cannot open video")
    exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)

def correct_leg_swaps(landmarks, prev_landmarks):
    if prev_landmarks is None:
        return landmarks
        
    pairs = [
        (23, 24), # L_HIP, R_HIP
        (25, 26), # L_KNEE, R_KNEE
        (27, 28), # L_ANKLE, R_ANKLE
        (29, 30), # L_HEEL, R_HEEL
        (31, 32), # L_FOOT_INDEX, R_FOOT_INDEX
    ]
    
    # 1. No-swap total squared distance
    dist_no_swap = 0.0
    for l_idx, r_idx in pairs:
        pl = prev_landmarks[l_idx]
        pr = prev_landmarks[r_idx]
        cl = landmarks[l_idx]
        cr = landmarks[r_idx]
        
        dist_no_swap += (cl.x - pl.x)**2 + (cl.y - pl.y)**2
        dist_no_swap += (cr.x - pr.x)**2 + (cr.y - pr.y)**2
        
    # 2. Swap total squared distance
    dist_swap = 0.0
    for l_idx, r_idx in pairs:
        pl = prev_landmarks[l_idx]
        pr = prev_landmarks[r_idx]
        cl = landmarks[l_idx]
        cr = landmarks[r_idx]
        
        dist_swap += (cl.x - pr.x)**2 + (cl.y - pr.y)**2
        dist_swap += (cr.x - pl.x)**2 + (cr.y - pl.y)**2
        
    if dist_swap < dist_no_swap and (dist_no_swap - dist_swap) > 0.015:
        # Perform swap
        print(f"  [SWAP DETECTED] dist_no_swap={dist_no_swap:.5f}, dist_swap={dist_swap:.5f}")
        for l_idx, r_idx in pairs:
            lx, ly, lz = landmarks[l_idx].x, landmarks[l_idx].y, landmarks[l_idx].z
            rx, ry, rz = landmarks[r_idx].x, landmarks[r_idx].y, landmarks[r_idx].z
            
            landmarks[l_idx].x, landmarks[l_idx].y, landmarks[l_idx].z = rx, ry, rz
            landmarks[r_idx].x, landmarks[r_idx].y, landmarks[r_idx].z = lx, ly, lz
            
    return landmarks

start_input_frame = 570
end_input_frame = 640

cap.set(cv2.CAP_PROP_POS_FRAMES, start_input_frame)
frame_idx = start_input_frame

prev_raw_landmarks = None
L_KNEE, R_KNEE = 25, 26
prev_l_knee = None
prev_r_knee = None

print("Frame | Corrected L_Knee | Corrected R_Knee | L_Jump | R_Jump")
print("-" * 70)

while frame_idx <= end_input_frame:
    ret, frame = cap.read()
    if not ret:
        break
        
    timestamp_ms = int(frame_idx * 1000.0 / fps)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(mp_image, timestamp_ms)
    
    if result.pose_landmarks and len(result.pose_landmarks) > 0:
        lm = result.pose_landmarks[0]
        mutable_landmarks = [
            SimpleNamespace(x=pt.x, y=pt.y, z=pt.z)
            for pt in lm
        ]
        
        # Apply correction
        mutable_landmarks = correct_leg_swaps(mutable_landmarks, prev_raw_landmarks)
        prev_raw_landmarks = mutable_landmarks
        
        lk = (mutable_landmarks[L_KNEE].x, mutable_landmarks[L_KNEE].y)
        rk = (mutable_landmarks[R_KNEE].x, mutable_landmarks[R_KNEE].y)
        
        l_jump = 0.0
        r_jump = 0.0
        if prev_l_knee is not None:
            l_jump = math.sqrt((lk[0] - prev_l_knee[0])**2 + (lk[1] - prev_l_knee[1])**2)
            r_jump = math.sqrt((rk[0] - prev_r_knee[0])**2 + (rk[1] - prev_r_knee[1])**2)
            
        print(f"{frame_idx:5d} | ({lk[0]:.3f}, {lk[1]:.3f}) | ({rk[0]:.3f}, {rk[1]:.3f}) | {l_jump:.4f} | {r_jump:.4f}")
        
        prev_l_knee = lk
        prev_r_knee = rk
    else:
        print(f"{frame_idx:5d} | [No landmarks]")
        prev_raw_landmarks = None
        prev_l_knee = None
        prev_r_knee = None
        
    frame_idx += 1

cap.release()
landmarker.close()
