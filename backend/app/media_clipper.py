import asyncio
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import imageio_ffmpeg

from .models import CaptureSession, TaskEvent, TaskEventType


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    started_at: datetime
    duration_seconds: float
    fps: float

    @property
    def ended_at(self) -> datetime:
        return self.started_at + timedelta(seconds=self.duration_seconds)


class MediaClipper:
    """按 GoPro MP4 内嵌时间码切出各任务的多机位素材。"""

    async def create_clips(
        self,
        session: CaptureSession,
        session_dir: Path,
        events: list[TaskEvent],
    ) -> int:
        tasks = self._pair_tasks(events)
        if not tasks:
            return 0

        videos_by_camera: dict[str, list[VideoInfo]] = {}
        for camera_id in session.camera_ids:
            camera_name = session.camera_names[camera_id]
            paths = [
                session_dir / item.local_path
                for item in session.collected_files
                if item.camera_id == camera_id and item.local_path.lower().endswith(".mp4")
            ]
            if not paths:
                raise RuntimeError(f"{camera_name} 没有可切片的 MP4 素材")
            videos_by_camera[camera_id] = sorted(
                [await self.probe(path) for path in paths],
                key=lambda item: item.started_at,
            )

        created = 0
        for camera_id in session.camera_ids:
            camera_name = session.camera_names[camera_id]
            videos = videos_by_camera[camera_id]
            for index, (start_event, end_event) in enumerate(tasks, start=1):
                output = session_dir / "clips" / f"task_{index:03d}" / f"{camera_name}.mp4"
                await self._cut_task(videos, start_event.utc_at, end_event.utc_at, output)
                created += 1
        return created

    async def create_grid_previews(
        self,
        session: CaptureSession,
        session_dir: Path,
        task_count: int,
    ) -> int:
        camera_names = [session.camera_names[camera_id] for camera_id in session.camera_ids]
        if len(camera_names) <= 1:
            return 0

        created = 0
        for index in range(1, task_count + 1):
            task_dir = session_dir / "clips" / f"task_{index:03d}"
            inputs = [task_dir / f"{camera_name}.mp4" for camera_name in camera_names]
            missing = [path.name for path in inputs if not path.exists()]
            if missing:
                raise RuntimeError(f"task_{index:03d} 缺少宫格输入：{', '.join(missing)}")
            await self._create_grid(inputs, task_dir / "preview_grid.mp4")
            created += 1
        return created

    async def _create_grid(self, inputs: list[Path], output: Path) -> None:
        filter_complex = self._grid_filter(len(inputs))
        command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error"]
        for path in inputs:
            command.extend(["-i", str(path)])
        command.extend([
            "-filter_complex",
            filter_complex,
            "-map",
            "[grid]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-shortest",
            "-y",
            str(output),
        ])
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            output.unlink(missing_ok=True)
            raise RuntimeError(f"生成 {output.name} 失败：{result.stderr.strip()}")

    @staticmethod
    def _grid_filter(camera_count: int) -> str:
        if camera_count == 2:
            width, height = 960, 1080
            layout = "0_0|960_0"
        elif camera_count == 3:
            width, height = 960, 540
            layout = "0_0|960_0|480_540"
        elif camera_count == 4:
            width, height = 960, 540
            layout = "0_0|960_0|0_540|960_540"
        else:
            raise RuntimeError("宫格预览仅支持 2 至 4 台相机")
        scaled = "".join(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1[v{index}];"
            for index in range(camera_count)
        )
        streams = "".join(f"[v{index}]" for index in range(camera_count))
        return f"{scaled}{streams}xstack=inputs={camera_count}:layout={layout}:fill=black[grid]"

    @staticmethod
    def _pair_tasks(events: list[TaskEvent]) -> list[tuple[TaskEvent, TaskEvent]]:
        starts: dict[str, TaskEvent] = {}
        pairs: list[tuple[TaskEvent, TaskEvent]] = []
        for event in sorted(events, key=lambda item: item.utc_at):
            if event.event is TaskEventType.START:
                starts[event.task_id] = event
            elif event.task_id in starts and starts[event.task_id].utc_at < event.utc_at:
                pairs.append((starts.pop(event.task_id), event))
        return sorted(pairs, key=lambda item: item[0].utc_at)

    async def probe(self, path: Path) -> VideoInfo:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:format_tags=creation_time,timecode:stream=avg_frame_rate:stream_tags=timecode",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"无法读取 {path.name} 的时间码：{result.stderr.strip()}")
        payload = json.loads(result.stdout)
        format_info = payload.get("format", {})
        streams = payload.get("streams", [])
        tags = format_info.get("tags", {})
        creation_time = self._parse_datetime(tags.get("creation_time"))
        fps = self._parse_fps(next((item.get("avg_frame_rate") for item in streams if item.get("avg_frame_rate")), "0/1"))
        timecode = tags.get("timecode") or next(
            (item.get("tags", {}).get("timecode") for item in streams if item.get("tags", {}).get("timecode")),
            None,
        )
        started_at = self._combine_timecode(creation_time, timecode, fps) if timecode else creation_time
        return VideoInfo(
            path=path,
            started_at=started_at,
            duration_seconds=float(format_info["duration"]),
            fps=fps,
        )

    async def _cut_task(
        self,
        videos: list[VideoInfo],
        task_start: datetime,
        task_end: datetime,
        output: Path,
    ) -> None:
        tolerance = timedelta(seconds=0.15)
        selected = [
            video for video in videos
            if video.started_at < task_end and video.ended_at > task_start
        ]
        if not selected or selected[0].started_at > task_start + tolerance or selected[-1].ended_at < task_end - tolerance:
            raise RuntimeError(f"{output.stem} 的素材未覆盖任务 UTC 区间")
        for previous, current in zip(selected, selected[1:]):
            if abs(current.started_at - previous.ended_at) > tolerance:
                raise RuntimeError(f"{output.stem} 的素材章节时间不连续")

        output.parent.mkdir(parents=True, exist_ok=True)
        concat_file = output.with_suffix(".concat.txt")
        concat_file.write_text(
            "".join(f"file '{self._escape_concat(video.path)}'\n" for video in selected),
            encoding="utf-8",
        )
        offset = max(0.0, (task_start - selected[0].started_at).total_seconds())
        duration = (task_end - task_start).total_seconds()
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_file),
                    "-ss",
                    f"{offset:.6f}",
                    "-t",
                    f"{duration:.6f}",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "18",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    "-y",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                output.unlink(missing_ok=True)
                raise RuntimeError(f"切片 {output.name} 失败：{result.stderr.strip()}")
        finally:
            concat_file.unlink(missing_ok=True)

    @staticmethod
    def _escape_concat(path: Path) -> str:
        return str(path.resolve()).replace("'", "'\\''")

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime:
        if not value:
            raise RuntimeError("MP4 缺少 creation_time，无法映射 UTC")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _parse_fps(value: str) -> float:
        numerator, denominator = value.split("/", maxsplit=1)
        fps = float(numerator) / float(denominator)
        if fps <= 0:
            raise RuntimeError("MP4 帧率无效")
        return fps

    @staticmethod
    def _combine_timecode(created_at: datetime, value: str, fps: float) -> datetime:
        match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})[:;](\d{2})", value)
        if not match:
            raise RuntimeError(f"无法解析 MP4 时间码：{value}")
        hour, minute, second, frame = (int(part) for part in match.groups())
        candidate = datetime.combine(
            created_at.date(),
            time(hour, minute, second, tzinfo=timezone.utc),
        ) + timedelta(seconds=frame / fps)
        if candidate - created_at > timedelta(hours=12):
            candidate -= timedelta(days=1)
        elif created_at - candidate > timedelta(hours=12):
            candidate += timedelta(days=1)
        return candidate
