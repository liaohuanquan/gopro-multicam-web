import asyncio
import re
from collections import defaultdict
from pathlib import Path
from statistics import median

import cv2

from .media_clipper import MediaClipper
from .models import CaptureSession, SyncValidationCameraResult, SyncValidationReport


class SyncValidationAnalyzer:
    """读取测试片二维码，按 MP4 内嵌时间码比较各机位的采样相位。"""

    _payload_pattern = re.compile(r"^GOPRO_SYNC_V1\|FRAME=(\d{6})\|FPS=30$")

    def __init__(self, clipper: MediaClipper | None = None) -> None:
        self._clipper = clipper or MediaClipper()

    async def analyze(self, session: CaptureSession, session_dir: Path) -> SyncValidationReport:
        observations: dict[str, dict[int, int]] = {}
        for camera_id in session.camera_ids:
            paths = [
                session_dir / item.local_path
                for item in session.collected_files
                if item.camera_id == camera_id and item.local_path.lower().endswith(".mp4")
            ]
            camera_frames: dict[int, int] = {}
            for path in paths:
                info = await self._clipper.probe(path)
                decoded = await asyncio.to_thread(self._decode_video, path, info.started_at.timestamp())
                camera_frames.update(decoded)
            observations[camera_id] = camera_frames

        reference_id = max(session.camera_ids, key=lambda item: len(observations[item]))
        reference = observations[reference_id]
        if not reference:
            raise RuntimeError("没有从任何相机素材中识别到同步验证二维码")

        results = []
        for camera_id in session.camera_ids:
            current = observations[camera_id]
            deltas = [current[tick] - reference[tick] for tick in current.keys() & reference.keys()]
            offset = float(median(deltas)) if deltas else None
            jitter = float(median(abs(value - offset) for value in deltas)) if deltas and offset is not None else None
            results.append(SyncValidationCameraResult(
                camera_id=camera_id,
                camera_name=session.camera_names[camera_id],
                decoded_frames=len(current),
                compared_frames=len(deltas),
                offset_frames=offset,
                jitter_frames=jitter,
            ))

        return SyncValidationReport(
            session_id=session.id,
            reference_camera_id=reference_id,
            reference_camera_name=session.camera_names[reference_id],
            results=results,
        )

    @classmethod
    def _decode_video(cls, path: Path, started_at_seconds: float) -> dict[int, int]:
        capture = cv2.VideoCapture(str(path))
        detector = cv2.QRCodeDetector()
        observations: dict[int, list[int]] = defaultdict(list)
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                payload, _, _ = detector.detectAndDecode(frame)
                match = cls._payload_pattern.fullmatch(payload)
                if not match:
                    continue
                timestamp = started_at_seconds + capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                global_tick = round(timestamp * 30)
                observations[global_tick].append(int(match.group(1)))
        finally:
            capture.release()
        return {tick: round(median(values)) for tick, values in observations.items()}
