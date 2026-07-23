import asyncio
import bisect
import csv
import json
import math
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import cv2

from .media_clipper import MediaClipper
from .models import CaptureSession, TimelineSyncDeviceResult, TimelineSyncReport


@dataclass(frozen=True)
class VideoFrame:
    index: int
    device_time: float
    decoded_qr: float | None


@dataclass(frozen=True)
class TimeModel:
    slope: float
    intercept: float
    inliers: int
    anchor_span_seconds: float
    rmse_seconds: float

    def global_time(self, device_time: float) -> float:
        return self.slope * device_time + self.intercept


@dataclass(frozen=True)
class DeviceFrames:
    device_id: str
    device_name: str
    role: str
    stream: str
    frames: list[VideoFrame]


class EgoExoTimelineSynchronizer:
    """用二维码公共时钟拟合 EGO/EXO 时间轴，并按 EGO 左目匹配最近帧。"""

    _frame_payload = re.compile(r"^GOPRO_SYNC_V1\|FRAME=(\d+)\|FPS=(\d+(?:\.\d+)?)$")
    _utc_payload = re.compile(r"oT(\d{12})\.(\d{3})")

    def __init__(self, clipper: MediaClipper | None = None) -> None:
        self._clipper = clipper or MediaClipper()

    async def synchronize(self, session: CaptureSession, session_dir: Path) -> TimelineSyncReport:
        ego_paths = {item.stream: session_dir / item.local_path for item in session.ego_files}
        if set(ego_paths) != {"left", "right"}:
            raise RuntimeError("请先导入 EGO 左目和右目素材")

        devices: list[DeviceFrames] = []
        for stream in ("left", "right"):
            frames = await asyncio.to_thread(self._decode_video, ego_paths[stream], 0.0, 0)
            devices.append(DeviceFrames(
                device_id=f"EGO_{stream.upper()}",
                device_name=f"EGO {'左目' if stream == 'left' else '右目'}",
                role="ego",
                stream=stream,
                frames=frames,
            ))

        for index, camera_id in enumerate(session.camera_ids, start=1):
            paths = [
                session_dir / item.local_path
                for item in session.collected_files
                if item.camera_id == camera_id and item.local_path.lower().endswith((".mp4", ".mov"))
            ]
            if not paths:
                raise RuntimeError(f"{session.camera_names[camera_id]} 没有可同步的视频素材")
            frames: list[VideoFrame] = []
            frame_offset = 0
            for path in paths:
                info = await self._clipper.probe(path)
                decoded = await asyncio.to_thread(
                    self._decode_video,
                    path,
                    info.started_at.timestamp(),
                    frame_offset,
                )
                frames.extend(decoded)
                frame_offset += len(decoded)
            devices.append(DeviceFrames(
                device_id=f"EXO{index:02d}",
                device_name=session.camera_names[camera_id],
                role="exo",
                stream="video",
                frames=frames,
            ))

        models = {item.device_id: self.fit_time_model(item.frames) for item in devices}
        reference = next(item for item in devices if item.device_id == "EGO_LEFT")
        output_dir = session_dir / "timesync"
        output_dir.mkdir(parents=True, exist_ok=True)
        for device in devices:
            self._write_device_table(output_dir / f"{device.device_id.lower()}_timesync.csv", device, models[device.device_id])

        match_errors = self._write_master_table(output_dir / "timesync.csv", reference, devices, models)
        results = []
        for device in devices:
            model = models[device.device_id]
            errors = match_errors.get(device.device_id, [])
            decoded_count = sum(frame.decoded_qr is not None for frame in device.frames)
            results.append(TimelineSyncDeviceResult(
                device_id=device.device_id,
                device_name=device.device_name,
                role=device.role,
                stream=device.stream,
                total_frames=len(device.frames),
                decoded_qr_frames=decoded_count,
                inlier_qr_frames=model.inliers,
                anchor_span_seconds=model.anchor_span_seconds,
                slope=model.slope,
                intercept=model.intercept,
                fit_rmse_ms=model.rmse_seconds * 1000,
                median_match_error_ms=median(errors) * 1000 if errors else None,
                max_match_error_ms=max(errors) * 1000 if errors else None,
            ))

        report = TimelineSyncReport(
            session_id=session.id,
            timeline_rows=len(reference.frames),
            devices=results,
        )
        (output_dir / "timesync.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report

    @classmethod
    def parse_qr_time(cls, payload: str) -> float | None:
        frame_match = cls._frame_payload.fullmatch(payload)
        if frame_match:
            fps = float(frame_match.group(2))
            return int(frame_match.group(1)) / fps if fps > 0 else None
        utc_match = cls._utc_payload.search(payload)
        if utc_match:
            value, milliseconds = utc_match.groups()
            parsed = datetime.strptime(value, "%y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return parsed.timestamp() + int(milliseconds) / 1000
        return None

    @classmethod
    def fit_time_model(cls, frames: list[VideoFrame]) -> TimeModel:
        anchors = [(frame.device_time, frame.decoded_qr) for frame in frames if frame.decoded_qr is not None]
        if len(anchors) < 2:
            raise RuntimeError("二维码有效锚点不足，至少需要 2 帧")
        unique_times = {item[0] for item in anchors}
        if len(unique_times) < 2:
            raise RuntimeError("二维码锚点没有覆盖不同时间")

        rng = random.Random(0)
        best: list[tuple[float, float]] = []
        for _ in range(min(800, max(50, len(anchors) * 4))):
            first, second = rng.sample(anchors, 2)
            if math.isclose(first[0], second[0]):
                continue
            slope = (second[1] - first[1]) / (second[0] - first[0])
            if not 0.95 <= slope <= 1.05:
                continue
            intercept = first[1] - slope * first[0]
            current = [item for item in anchors if abs((slope * item[0] + intercept) - item[1]) <= 0.04]
            if len(current) > len(best):
                best = current
        if len(best) < 2:
            raise RuntimeError("二维码锚点无法拟合稳定的线性时间映射")

        slope, intercept = cls._least_squares(best)
        residuals = [(slope * x + intercept) - y for x, y in best]
        rmse = math.sqrt(sum(value * value for value in residuals) / len(residuals))
        span = max(x for x, _ in best) - min(x for x, _ in best)
        return TimeModel(slope, intercept, len(best), span, rmse)

    @staticmethod
    def _least_squares(points: list[tuple[float, float]]) -> tuple[float, float]:
        mean_x = sum(item[0] for item in points) / len(points)
        mean_y = sum(item[1] for item in points) / len(points)
        denominator = sum((item[0] - mean_x) ** 2 for item in points)
        if denominator == 0:
            raise RuntimeError("二维码锚点时间跨度为 0")
        slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
        return slope, mean_y - slope * mean_x

    @classmethod
    def _decode_video(cls, path: Path, local_origin: float, frame_offset: int) -> list[VideoFrame]:
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise RuntimeError(f"无法读取视频：{path.name}")
        detector = cv2.QRCodeDetector()
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        frames: list[VideoFrame] = []
        try:
            index = 0
            while True:
                ok, image = capture.read()
                if not ok:
                    break
                position = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                if position <= 0 and index > 0:
                    position = index / fps
                payload, _, _ = detector.detectAndDecode(image)
                frames.append(VideoFrame(
                    index=frame_offset + index,
                    device_time=local_origin + position,
                    decoded_qr=cls.parse_qr_time(payload),
                ))
                index += 1
        finally:
            capture.release()
        if not frames:
            raise RuntimeError(f"视频没有可读取的帧：{path.name}")
        return frames

    @staticmethod
    def _write_device_table(path: Path, device: DeviceFrames, model: TimeModel) -> None:
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(["frame_number", "device_time", "decoded_qr", "global_time"])
            for frame in device.frames:
                writer.writerow([
                    frame.index,
                    f"{frame.device_time:.9f}",
                    "" if frame.decoded_qr is None else f"{frame.decoded_qr:.9f}",
                    f"{model.global_time(frame.device_time):.9f}",
                ])

    @staticmethod
    def _nearest_index(values: list[float], target: float) -> int:
        position = bisect.bisect_left(values, target)
        candidates = [index for index in (position - 1, position) if 0 <= index < len(values)]
        return min(candidates, key=lambda index: abs(values[index] - target))

    @classmethod
    def _write_master_table(
        cls,
        path: Path,
        reference: DeviceFrames,
        devices: list[DeviceFrames],
        models: dict[str, TimeModel],
    ) -> dict[str, list[float]]:
        global_times = {
            device.device_id: [models[device.device_id].global_time(frame.device_time) for frame in device.frames]
            for device in devices
        }
        errors: dict[str, list[float]] = {device.device_id: [] for device in devices if device is not reference}
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            header = ["global_time"]
            for device in devices:
                header.extend([f"{device.device_id}_frame_number", f"{device.device_id}_device_time", f"{device.device_id}_global_time"])
            writer.writerow(header)
            for ref_index, ref_frame in enumerate(reference.frames):
                target = global_times[reference.device_id][ref_index]
                row: list[str | int] = [f"{target:.9f}"]
                for device in devices:
                    if device is reference:
                        index = ref_index
                    else:
                        index = cls._nearest_index(global_times[device.device_id], target)
                        errors[device.device_id].append(abs(global_times[device.device_id][index] - target))
                    frame = device.frames[index]
                    row.extend([frame.index, f"{frame.device_time:.9f}", f"{global_times[device.device_id][index]:.9f}"])
                writer.writerow(row)
        return errors
