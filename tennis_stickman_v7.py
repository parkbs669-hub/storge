# 테니스 동작 영상을 스틱맨 애니메이션으로 변환하는 생성기 (v7: 라켓 래그 + 신발 모핑)
"""
Tennis Stickman Animation Generator v7 (Racket Wrist-Lag + Shoe Morphing)

사용법:
  python tennis_stickman_v7.py <YouTube_URL_또는_로컬파일> <동작명> [--left] [--speed <배속>]

v7 변경 사항:
  1. 라켓 손목 래그(Wrist Lag): 스프링-댐퍼 물리 엔진으로 채찍 효과 재현
  2. 신발 시점 부드러운 전환(Shoe Shape Morphing): 연속 블렌드 팩터로 끊김 없는 형태 전환
"""

import cv2
import mediapipe as mp
import numpy as np
import subprocess
import os
import math
import urllib.request
import argparse
from types import SimpleNamespace
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


# ─────────────────────────────────────────
# CLI 인자 파싱
# ─────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="테니스 스틱맨 애니메이션 생성기 v7",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url",  help="YouTube 영상 URL 또는 로컬 파일 경로")
    parser.add_argument("name", help="동작명 (파일명에 사용)")
    parser.add_argument("--left", action="store_true", help="왼손잡이 선수")
    parser.add_argument("--label", default=None, help="화면 자막")
    parser.add_argument("--desc",  default=None, help="자막 아래 설명")
    parser.add_argument("--speed", type=float, default=1.0, help="재생 속도 배율")
    return parser.parse_args()


# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────

MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
MODEL_PATH = "pose_landmarker_full.task"

SSAA  = 2
OUT_H = 720
LW = SSAA

def configure_thickness(render_h):
    global LW, LIMB_THICKNESS, NECK_THICKNESS, HEAD_OUTLINE_THICKNESS, TORSO_OUTLINE_THICKNESS
    LW = SSAA * (render_h / 720.0)
    LIMB_THICKNESS          = max(int(6 * LW), 2)
    NECK_THICKNESS          = max(int(7 * LW), 2)
    HEAD_OUTLINE_THICKNESS  = max(int(8 * LW), 2)
    TORSO_OUTLINE_THICKNESS = max(int(6 * LW), 2)

BODY_COLOR        = (20, 20, 20)
LIMB_THICKNESS    = 6 * SSAA
NECK_THICKNESS    = 7 * SSAA
HEAD_OUTLINE_THICKNESS  = 8 * SSAA
TORSO_OUTLINE_THICKNESS = 6 * SSAA
HEAD_FILL_COLOR   = (255, 255, 255)
OUTLINE_COLOR     = (20, 20, 20)
SHOE_FILL_COLOR   = (155, 155, 155)
SHOE_OUTLINE_COLOR = (20, 20, 20)
HAND_FILL_COLOR   = (60, 60, 60)
HAND_OUTLINE_COLOR = (20, 20, 20)
RACKET_FRAME_COLOR  = (30, 30, 220)
RACKET_STRING_COLOR = (210, 210, 215)
RACKET_GRIP_COLOR   = (40, 40, 40)
COURT_GREEN         = (78, 115, 76)
SKY_GRADIENT_START  = (215, 215, 215)
SKY_GRADIENT_END    = (238, 238, 238)

ONE_EURO_MIN_CUTOFF = 1.0
ONE_EURO_BETA       = 0.7
ONE_EURO_D_CUTOFF   = 1.0

SCALE_FACTOR = 0.9
OFFSET_X     = 0
OFFSET_Y     = 10

FONT_PATH = "C:/Windows/Fonts/malgun.ttf"

NOSE = 0
L_SHOULDER = 11; R_SHOULDER = 12
L_ELBOW = 13;    R_ELBOW = 14
L_WRIST = 15;    R_WRIST = 16
L_HIP = 23;      R_HIP = 24
L_KNEE = 25;     R_KNEE = 26
L_ANKLE = 27;    R_ANKLE = 28
L_HEEL = 29;     R_HEEL = 30
L_FOOT_INDEX = 31; R_FOOT_INDEX = 32

_shoe_blend_prev = {}


# ─────────────────────────────────────────
# One-Euro 필터
# ─────────────────────────────────────────

class OneEuroFilter:
    def __init__(self, freq, min_cutoff, beta, d_cutoff):
        self.freq = freq
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0

    @staticmethod
    def _alpha(cutoff, freq):
        tau = 1.0 / (2 * math.pi * cutoff)
        te = 1.0 / freq
        return 1.0 / (1.0 + tau / te)

    def __call__(self, x):
        if self.x_prev is None:
            self.x_prev = x
            return x
        dx = (x - self.x_prev) * self.freq
        a_d = self._alpha(self.d_cutoff, self.freq)
        edx = a_d * dx + (1 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(edx)
        a = self._alpha(cutoff, self.freq)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev = x_hat
        self.dx_prev = edx
        return x_hat


class PoseSmoother:
    def __init__(self, freq, n=33):
        mk = lambda: OneEuroFilter(freq, ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_D_CUTOFF)
        self.fx = [mk() for _ in range(n)]
        self.fy = [mk() for _ in range(n)]
        self.fz = [mk() for _ in range(n)]

    def apply(self, raw):
        return [SimpleNamespace(
            x=self.fx[i](raw[i].x),
            y=self.fy[i](raw[i].y),
            z=self.fz[i](raw[i].z),
        ) for i in range(len(raw))]


# ─────────────────────────────────────────
# v7: 라켓 래그 시뮬레이터 (Spring-Damper)
# ─────────────────────────────────────────

class RacketLagSimulator:
    """손목 각속도에 반응하는 스프링-댐퍼 시스템 (채찍 효과)."""
    def __init__(self, stiffness=15.0, damping=4.0):
        self.stiffness = stiffness
        self.damping = damping
        self.racket_angle = 0.0
        self.angular_velocity = 0.0
        self.prev_target = None

    @staticmethod
    def _wrap_angle(a):
        return (a + math.pi) % (2 * math.pi) - math.pi

    def update(self, target_angle, dt):
        if self.prev_target is None:
            self.racket_angle = target_angle
            self.angular_velocity = 0.0
            self.prev_target = target_angle
            return self.racket_angle
        angle_diff = self._wrap_angle(target_angle - self.racket_angle)
        spring_torque = self.stiffness * angle_diff
        damping_torque = -self.damping * self.angular_velocity
        angular_accel = spring_torque + damping_torque
        self.angular_velocity += angular_accel * dt
        self.racket_angle += self.angular_velocity * dt
        self.racket_angle = self._wrap_angle(self.racket_angle)
        self.prev_target = target_angle
        return self.racket_angle

    def reset(self):
        self.racket_angle = 0.0
        self.angular_velocity = 0.0
        self.prev_target = None
