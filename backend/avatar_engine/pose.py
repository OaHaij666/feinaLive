from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MotionPose:
    head_pitch: float = 0.0
    head_yaw: float = 0.0
    head_roll: float = 0.0
    body_yaw: float | None = None
    body_roll: float | None = None
    gaze_x: float = 0.0
    gaze_y: float = 0.0
    breathing: float = 0.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale: float = 1.0


@dataclass(frozen=True)
class FacialPose:
    blink: float = 0.0
    mouth_open: float = 0.0
    eyebrow_raise: float = 0.0


class THAPoseMapper:
    """Translate named pose channels to the THA 45-value model contract."""

    @staticmethod
    def map(motion: MotionPose, face: FacialPose) -> tuple[np.ndarray, np.ndarray]:
        eyebrows = [0.0] * 12
        features = [0.0] * 27
        body = [0.0] * 6

        eyebrows[6] = face.eyebrow_raise
        eyebrows[7] = face.eyebrow_raise
        features[2] = face.blink
        features[3] = face.blink
        features[14] = face.mouth_open
        features[25] = motion.gaze_y
        features[26] = motion.gaze_x
        body[0] = motion.head_pitch
        body[1] = motion.head_yaw
        body[2] = motion.head_roll
        body[3] = motion.head_yaw if motion.body_yaw is None else motion.body_yaw
        body[4] = motion.head_roll if motion.body_roll is None else motion.body_roll
        body[5] = motion.breathing

        pose = np.asarray(eyebrows + features + body, dtype=np.float32)
        position = np.asarray(
            [motion.offset_x, motion.offset_y, 0.0, motion.scale],
            dtype=np.float32,
        )
        return pose, position
