#!/usr/bin/env python3
"""生成逐帧编号的多机同步验证视频。"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np


def build_frame(frame_number: int, fps: int) -> np.ndarray:
    width, height = 1920, 1080
    frame = np.full((height, width, 3), 245, dtype=np.uint8)
    payload = f"GOPRO_SYNC_V1|FRAME={frame_number:06d}|FPS={fps}"
    qr = cv2.QRCodeEncoder_create().encode(payload)
    qr = cv2.resize(qr, (540, 540), interpolation=cv2.INTER_NEAREST)
    qr = cv2.copyMakeBorder(qr, 35, 35, 35, 35, cv2.BORDER_CONSTANT, value=255)
    qr = cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)
    frame[225:835, 655:1265] = qr

    cv2.putText(frame, "GOPRO SYNC VALIDATION", (560, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (25, 25, 25), 3, cv2.LINE_AA)
    cv2.putText(frame, f"{frame_number:06d}", (690, 190), cv2.FONT_HERSHEY_DUPLEX, 2.5, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(frame, f"FRAME {frame_number:06d}   {frame_number / fps:08.3f} s   30 FPS", (480, 940), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (40, 40, 40), 3, cv2.LINE_AA)
    cv2.putText(frame, "KEEP THE FULL QR INSIDE EVERY CAMERA", (515, 1010), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (55, 55, 55), 2, cv2.LINE_AA)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
        "-pix_fmt", "bgr24", "-s", "1920x1080", "-r", str(args.fps), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "12",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-y", str(args.output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_number in range(args.seconds * args.fps):
            process.stdin.write(build_frame(frame_number, args.fps).tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise SystemExit("生成同步验证视频失败")
    args.output.chmod(0o644)


if __name__ == "__main__":
    main()
