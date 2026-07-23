import asyncio
import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from ipaddress import ip_network
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
import imageio_ffmpeg

from .models import CameraStatus, DiscoverCameraRequest, DiscoveryResponse, RecordingConfig, ShutterAction, UpdateCameraRequest


class CameraUnavailableError(RuntimeError):
    pass


class CameraNotFoundError(KeyError):
    pass


class CameraRegistrationError(RuntimeError):
    pass


class CameraAdapter(ABC):
    name: str

    @abstractmethod
    async def list_statuses(self) -> list[CameraStatus]:
        raise NotImplementedError

    @abstractmethod
    async def set_shutter(self, camera_id: str, action: ShutterAction) -> CameraStatus:
        raise NotImplementedError

    @abstractmethod
    async def mark_timecode_synced(self, camera_id: str) -> CameraStatus:
        raise NotImplementedError

    @abstractmethod
    async def apply_recording_config(self, camera_id: str) -> CameraStatus:
        raise NotImplementedError


@dataclass
class RegisteredCamera:
    id: str
    name: str
    serial: str
    model_name: str
    location: str
    ip_address: str
    username: str
    password: str
    profile_label: str
    timecode_synced_at: str | None = None
    open_network: bool = False
    sequence: int = 0


@dataclass
class PreviewSession:
    port: int
    process: asyncio.subprocess.Process
    reader_active: bool = False


@dataclass(frozen=True)
class CameraMediaFile:
    path: str
    size_bytes: int
    created_at: datetime | None = None


@dataclass(frozen=True)
class CohnCredential:
    ip_address: str
    username: str
    password: str


class CohnCameraAdapter(CameraAdapter):
    """通过 GoPro COHN HTTPS 接口控制已登记的真实相机。"""

    name = "cohn"

    def __init__(
        self,
        store_path: Path,
        scan_cidrs: str = "192.168.1.0/24",
        preview_port_start: int = 8554,
        transport: httpx.AsyncBaseTransport | None = None,
        credentials_path: Path | None = None,
    ) -> None:
        self._store_path = store_path
        self._scan_cidrs = scan_cidrs
        self._preview_port_start = preview_port_start
        self._transport = transport
        self._credentials_path = credentials_path
        self._store_lock = asyncio.Lock()
        self._preview_lock = asyncio.Lock()
        self._preview_sessions: dict[str, PreviewSession] = {}
        self._camera_locks: dict[str, asyncio.Lock] = {}
        self._online_states: dict[str, bool] = {}
        self._next_camera_sequence = 1
        self._cameras = self._load()

    def _load_credentials(self) -> list[CohnCredential]:
        if self._credentials_path is None or not self._credentials_path.exists():
            return []
        try:
            payload = json.loads(self._credentials_path.read_text(encoding="utf-8"))
            credentials: list[CohnCredential] = []
            for item in payload.get("cameras", []):
                address = str(item.get("last_known_ip") or "").strip()
                username = str(item.get("username") or "").strip()
                password = str(item.get("password") or "")
                if address and username:
                    credentials.append(CohnCredential(address, username, password))
            return credentials
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise CameraRegistrationError("COHN 凭据文件格式不正确") from exc

    def _load_recording_config(self) -> RecordingConfig:
        if self._credentials_path is None or not self._credentials_path.exists():
            raise CameraRegistrationError("未配置 COHN 凭据文件")
        try:
            payload = json.loads(self._credentials_path.read_text(encoding="utf-8"))
            config = RecordingConfig.model_validate(payload.get("recording_config", {}))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise CameraRegistrationError("recording_config 格式不正确") from exc
        if all(value is None for value in config.model_dump().values()):
            raise CameraRegistrationError("recording_config 没有填写任何参数")
        return config

    def get_recording_config(self) -> RecordingConfig:
        return self._load_recording_config()

    async def update_recording_config(self, config: RecordingConfig) -> RecordingConfig:
        if self._credentials_path is None or not self._credentials_path.exists():
            raise CameraRegistrationError("未配置 COHN 凭据文件")
        if all(value is None for value in config.model_dump().values()):
            raise CameraRegistrationError("recording_config 至少保留一个参数")
        async with self._store_lock:
            try:
                payload = json.loads(self._credentials_path.read_text(encoding="utf-8"))
                payload["recording_config"] = config.model_dump()
                self._credentials_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                self._credentials_path.chmod(0o600)
            except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
                raise CameraRegistrationError("recording_config 保存失败") from exc
        return config

    @staticmethod
    def _build_recording_command(config: RecordingConfig) -> str:
        mappings: dict[str, dict[Any, str]] = {
            "resolution": {"1080P": "r1", "4K": "r4", "5.3K_8_7": "r5X"},
            "fps": {24: "p24", 25: "p25", 30: "p30", 50: "p50", 60: "p60"},
            "lens": {"wide": "fW", "linear": "fL", "hyperview": "fV"},
            "bit_depth": {8: "d8", 10: "d10"},
            "color": {"natural": "cN", "flat": "cF", "vibrant": "cG"},
            "high_bitrate": {False: "b0", True: "b1"},
            "stabilization": {"off": "e0", "high": "e2", "auto_boost": "e4"},
            "hindsight": {False: "hS0", True: "hS1"},
            "shutter_speed": {0: "$EXPQ=0", 120: "$EXPQ=120", 240: "$EXPQ=240", 480: "$EXPQ=480"},
            "iso": {100: "i1M1", 200: "i2M2", 400: "i4M4", 800: "i8M8", 1600: "i16M16"},
        }
        values = config.model_dump()
        return "mV" + "".join(
            mappings[field][values[field]]
            for field in mappings
            if values[field] is not None
        )

    @staticmethod
    def _recording_config_label(config: RecordingConfig) -> str:
        values = config.model_dump()
        labels = {
            "resolution": {"1080P": "1080P", "4K": "4K", "5.3K_8_7": "5.3K 8:7"},
            "fps": {value: f"{value} FPS" for value in (24, 25, 30, 50, 60)},
            "lens": {"wide": "Wide", "linear": "Linear", "hyperview": "HyperView"},
            "bit_depth": {8: "8-bit", 10: "10-bit"},
            "color": {"natural": "Natural", "flat": "Flat", "vibrant": "Vibrant"},
            "high_bitrate": {False: "标准码率", True: "高码率"},
            "stabilization": {"off": "防抖关", "high": "HyperSmooth High", "auto_boost": "AutoBoost"},
            "hindsight": {False: "Hindsight 关", True: "Hindsight 开"},
            "shutter_speed": {0: "快门自动", 120: "快门 1/120", 240: "快门 1/240", 480: "快门 1/480"},
            "iso": {value: f"ISO {value}" for value in (100, 200, 400, 800, 1600)},
        }
        return " · ".join(
            labels[field][values[field]]
            for field in labels
            if values[field] is not None
        )

    def _load(self) -> dict[str, RegisteredCamera]:
        if not self._store_path.exists():
            return {}
        try:
            payload = json.loads(self._store_path.read_text(encoding="utf-8"))
            items = payload.get("cameras", []) if isinstance(payload, dict) else payload
            cameras = {item["id"]: RegisteredCamera(**item) for item in items}
            inferred_next = 1
            for index, camera in enumerate(cameras.values(), start=1):
                if camera.sequence <= 0:
                    match = re.fullmatch(r"GP(\d+)", camera.name, flags=re.IGNORECASE)
                    camera.sequence = int(match.group(1)) if match else index
                inferred_next = max(inferred_next, camera.sequence + 1)
            self._next_camera_sequence = (
                max(int(payload.get("next_camera_sequence", inferred_next)), inferred_next)
                if isinstance(payload, dict)
                else inferred_next
            )
            self._camera_locks = {camera_id: asyncio.Lock() for camera_id in cameras}
            return cameras
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"设备存储文件损坏：{self._store_path}") from exc

    async def _save(self) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {
                "next_camera_sequence": self._next_camera_sequence,
                "cameras": [asdict(camera) for camera in self._cameras.values()],
            },
            ensure_ascii=False,
            indent=2,
        )
        temporary_path = self._store_path.with_suffix(".tmp")
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.chmod(0o600)
        temporary_path.replace(self._store_path)

    def _get_camera(self, camera_id: str) -> RegisteredCamera:
        try:
            return self._cameras[camera_id]
        except KeyError as exc:
            raise CameraNotFoundError(camera_id) from exc

    def _client(self, camera: RegisteredCamera) -> httpx.AsyncClient:
        if camera.open_network:
            return httpx.AsyncClient(
                base_url=f"http://{camera.ip_address}",
                timeout=httpx.Timeout(4.0),
                transport=self._transport,
            )
        return httpx.AsyncClient(
            base_url=f"https://{camera.ip_address}",
            auth=httpx.BasicAuth(camera.username, camera.password),
            verify=False,
            timeout=httpx.Timeout(4.0),
            transport=self._transport,
        )

    @staticmethod
    def _read_int(values: dict[str, Any], key: str) -> int | None:
        value = values.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def _fetch_status(self, camera: RegisteredCamera) -> CameraStatus:
        request_started_at = perf_counter()
        async with self._client(camera) as client:
            response = await client.get("/gopro/camera/state")
            response.raise_for_status()
            payload = response.json()
        statuses = payload.get("status", {})
        remaining_seconds = self._read_int(statuses, "35")
        latency_ms = round((perf_counter() - request_started_at) * 1000)
        return CameraStatus(
            id=camera.id,
            name=camera.name,
            serial=camera.serial,
            location=camera.location,
            online=True,
            battery_percent=self._read_int(statuses, "70"),
            sd_remaining_minutes=(remaining_seconds // 60 if remaining_seconds is not None else None),
            sd_remaining_gb=(
                round(sd_remaining_kb / 1024 / 1024, 1)
                if (sd_remaining_kb := self._read_int(statuses, "54")) is not None
                else None
            ),
            latency_ms=latency_ms,
            overheating=bool(statuses.get("6")) if "6" in statuses else None,
            recording=bool(statuses.get("10", False)),
            recording_seconds=self._read_int(statuses, "13") or 0,
            mode=camera.profile_label,
            timecode_synced_at=(
                datetime.fromisoformat(camera.timecode_synced_at)
                if camera.timecode_synced_at
                else None
            ),
            last_seen_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _offline_status(camera: RegisteredCamera) -> CameraStatus:
        return CameraStatus(
            id=camera.id,
            name=camera.name,
            serial=camera.serial,
            location=camera.location,
            online=False,
            battery_percent=None,
            sd_remaining_minutes=None,
            sd_remaining_gb=None,
            latency_ms=None,
            overheating=None,
            recording=False,
            recording_seconds=0,
            mode=camera.profile_label,
            timecode_synced_at=(
                datetime.fromisoformat(camera.timecode_synced_at)
                if camera.timecode_synced_at
                else None
            ),
            last_seen_at=datetime.now(timezone.utc),
        )

    async def list_statuses(self) -> list[CameraStatus]:
        async def fetch(camera: RegisteredCamera) -> CameraStatus:
            try:
                camera_status = await self._fetch_status(camera)
                became_online = not self._online_states.get(camera.id, False)
                self._online_states[camera.id] = not camera_status.recording
                if became_online and not camera_status.recording:
                    try:
                        await self._sync_timecode(camera)
                        camera_status.timecode_synced_at = datetime.fromisoformat(camera.timecode_synced_at)
                    except CameraUnavailableError:
                        pass
                if not camera_status.recording and camera.id in self._preview_sessions:
                    await self._stop_preview(camera)
                return camera_status
            except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                self._online_states[camera.id] = False
                return self._offline_status(camera)

        return await asyncio.gather(*(fetch(camera) for camera in self._cameras.values()))

    async def discover(self, request: DiscoverCameraRequest) -> DiscoveryResponse:
        credentials = self._load_credentials()
        addresses: list[str] = []
        if not credentials:
            try:
                for cidr in self._scan_cidrs.split(","):
                    network = ip_network(cidr.strip(), strict=False)
                    if network.num_addresses > 1024:
                        raise CameraRegistrationError(f"扫描网段过大：{network}")
                    addresses.extend(str(address) for address in network.hosts())
            except ValueError as exc:
                raise CameraRegistrationError("GOPRO_SCAN_CIDRS 配置不正确") from exc

        semaphore = asyncio.Semaphore(48)

        async def probe(
            address: str,
            credential: CohnCredential | None = None,
        ) -> tuple[str, dict[str, Any], CohnCredential | None] | None:
            async with semaphore:
                try:
                    async with httpx.AsyncClient(
                        auth=(
                            httpx.BasicAuth(credential.username, credential.password)
                            if credential
                            else None
                        ),
                        verify=False,
                        timeout=httpx.Timeout(4.0 if credential else 0.8),
                        transport=self._transport,
                    ) as client:
                        scheme = "https" if credential else "http"
                        response = await client.get(f"{scheme}://{address}/gopro/camera/info")
                        response.raise_for_status()
                        info = response.json()
                    if not str(info.get("serial_number", "")).strip():
                        return None
                    return address, info, credential
                except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                    return None

        probes = (
            [probe(credential.ip_address, credential) for credential in credentials]
            if credentials
            else [probe(address) for address in addresses]
        )
        found = [item for item in await asyncio.gather(*probes) if item]
        discovered_ids: list[str] = []
        async with self._store_lock:
            for address, info, credential in found:
                serial = str(info["serial_number"]).strip()
                camera_id = serial.lower()
                existing = self._cameras.get(camera_id)
                if existing:
                    existing.ip_address = address
                    existing.username = credential.username if credential else ""
                    existing.password = credential.password if credential else ""
                    existing.open_network = credential is None
                    existing.profile_label = request.profile_label
                else:
                    sequence = self._next_camera_sequence
                    self._next_camera_sequence += 1
                    self._cameras[camera_id] = RegisteredCamera(
                        id=camera_id,
                        name=f"GP{sequence:02d}",
                        serial=serial,
                        model_name=str(info.get("model_name", "GoPro")).strip(),
                        location="未设置",
                        ip_address=address,
                        username=credential.username if credential else "",
                        password=credential.password if credential else "",
                        profile_label=request.profile_label,
                        open_network=credential is None,
                        sequence=sequence,
                    )
                self._camera_locks.setdefault(camera_id, asyncio.Lock())
                discovered_ids.append(camera_id)
            if found:
                await self._save()

        statuses = await self.list_statuses()
        return DiscoveryResponse(
            discovered_count=len(set(discovered_ids)),
            cameras=statuses,
        )

    async def remove(self, camera_id: str) -> None:
        camera = self._get_camera(camera_id)
        await self._stop_preview(camera)
        async with self._store_lock:
            self._cameras.pop(camera_id, None)
            self._camera_locks.pop(camera_id, None)
            await self._save()

    async def update(self, camera_id: str, request: UpdateCameraRequest) -> CameraStatus:
        camera = self._get_camera(camera_id)
        camera.name = request.name.strip()
        async with self._store_lock:
            await self._save()
        try:
            return await self._fetch_status(camera)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError):
            return self._offline_status(camera)

    async def set_shutter(self, camera_id: str, action: ShutterAction) -> CameraStatus:
        camera = self._get_camera(camera_id)
        async with self._camera_locks[camera_id]:
            try:
                async with self._client(camera) as client:
                    response = await client.get(f"/gopro/camera/shutter/{action.value}")
                    response.raise_for_status()
                camera_status = await self._fetch_status(camera)
                if action == ShutterAction.STOP:
                    await self._stop_preview(camera)
                return camera_status
            except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
                raise CameraUnavailableError(f"{camera.name} 控制失败或当前离线") from exc

    async def locate(self, camera_id: str) -> CameraStatus:
        camera = self._get_camera(camera_id)
        try:
            async with self._client(camera) as client:
                response = await client.get(
                    "/gopro/qrcode",
                    params={"labs": "1", "code": "!B2"},
                )
                response.raise_for_status()
            return await self._fetch_status(camera)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise CameraUnavailableError(f"{camera.name} 定位信号发送失败") from exc

    async def apply_recording_config(self, camera_id: str) -> CameraStatus:
        camera = self._get_camera(camera_id)
        try:
            status = await self._fetch_status(camera)
            if status.recording:
                raise CameraUnavailableError(f"{camera.name} 正在录制，不能修改录制参数")
            config = self._load_recording_config()
            command = self._build_recording_command(config)
            async with self._client(camera) as client:
                response = await client.get(
                    "/gopro/qrcode",
                    params={"labs": "1", "code": command},
                )
                response.raise_for_status()
            camera.profile_label = self._recording_config_label(config)
            async with self._store_lock:
                await self._save()
            return await self._fetch_status(camera)
        except CameraUnavailableError:
            raise
        except (CameraRegistrationError, httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise CameraUnavailableError(f"{camera.name} 录制参数应用失败：{exc}") from exc

    async def _start_preview(self, camera: RegisteredCamera) -> PreviewSession:
        async with self._preview_lock:
            current = self._preview_sessions.get(camera.id)
            if current and current.process.returncode is None:
                return current

            try:
                camera_index = list(self._cameras).index(camera.id)
            except ValueError as exc:
                raise CameraNotFoundError(camera.id) from exc
            port = self._preview_port_start + camera_index
            process = await asyncio.create_subprocess_exec(
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-fflags",
                "nobuffer",
                "-flags",
                "low_delay",
                "-analyzeduration",
                "0",
                "-probesize",
                "32768",
                "-i",
                f"udp://0.0.0.0:{port}?fifo_size=5000000&overrun_nonfatal=1&reuse=1",
                "-an",
                "-vf",
                "fps=10,scale=960:-2",
                "-q:v",
                "5",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            session = PreviewSession(port=port, process=process)
            self._preview_sessions[camera.id] = session
            try:
                async with self._client(camera) as client:
                    # 相机异常结束上一次预览时可能仍保留旧的 UDP 目标，先清理再启动。
                    try:
                        await client.get("/gopro/camera/stream/stop")
                    except httpx.HTTPError:
                        pass
                    response = await client.get("/gopro/camera/stream/start", params={"port": port})
                    response.raise_for_status()
            except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
                process.terminate()
                await process.wait()
                self._preview_sessions.pop(camera.id, None)
                raise CameraUnavailableError(f"{camera.name} 无法启动录制监看") from exc
            return session

    async def _stop_preview(self, camera: RegisteredCamera) -> None:
        async with self._preview_lock:
            session = self._preview_sessions.pop(camera.id, None)
            if not session:
                return
            try:
                async with self._client(camera) as client:
                    await client.get("/gopro/camera/stream/stop")
            except httpx.HTTPError:
                pass
            if session.process.returncode is None:
                session.process.terminate()
                try:
                    await asyncio.wait_for(session.process.wait(), timeout=2)
                except TimeoutError:
                    session.process.kill()
                    await session.process.wait()

    async def open_monitor_stream(self, camera_id: str):
        camera = self._get_camera(camera_id)
        try:
            camera_status = await self._fetch_status(camera)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise CameraUnavailableError(f"{camera.name} 当前离线") from exc
        if not camera_status.recording:
            await self._stop_preview(camera)
            raise CameraUnavailableError("开始录制后才会启动实时监看")

        session = await self._start_preview(camera)
        if session.process.stdout is None:
            raise CameraUnavailableError("实时监看解码器启动失败")
        if session.reader_active:
            raise CameraUnavailableError(f"{camera.name} 已有录制监看连接")
        session.reader_active = True

        async def frames():
            buffer = bytearray()
            try:
                while session.process.returncode is None:
                    try:
                        chunk = await asyncio.wait_for(session.process.stdout.read(65536), timeout=5)
                    except TimeoutError:
                        # 没收到首帧或流中断时结束响应，让浏览器自动重新建立监看。
                        break
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    while True:
                        start = buffer.find(b"\xff\xd8")
                        end = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                        if start < 0 or end < 0:
                            if len(buffer) > 2_000_000:
                                del buffer[:-2]
                            break
                        jpeg = bytes(buffer[start:end + 2])
                        del buffer[:end + 2]
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                            + jpeg
                            + b"\r\n"
                        )
            finally:
                session.reader_active = False
                await self._stop_preview(camera)

        return frames()

    async def latest_thumbnail(self, camera_id: str) -> tuple[bytes, str]:
        camera = self._get_camera(camera_id)
        try:
            async with self._client(camera) as client:
                media_response = await client.get("/gopro/media/list")
                media_response.raise_for_status()
                files = [
                    (str(item.get("cre", "0")), f'{directory.get("d")}/{item.get("n")}')
                    for directory in media_response.json().get("media", [])
                    for item in directory.get("fs", [])
                    if directory.get("d") and item.get("n")
                ]
                if not files:
                    raise CameraUnavailableError("相机中还没有可显示的素材")
                _, path = max(files, key=lambda item: int(item[0]) if item[0].isdigit() else 0)
                thumbnail_response = await client.get("/gopro/media/thumbnail", params={"path": path})
                thumbnail_response.raise_for_status()
                return thumbnail_response.content, thumbnail_response.headers.get("content-type", "image/jpeg")
        except CameraUnavailableError:
            raise
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise CameraUnavailableError(f"{camera.name} 最近画面读取失败") from exc

    async def list_media(self, camera_id: str) -> list[CameraMediaFile]:
        camera = self._get_camera(camera_id)
        try:
            async with self._client(camera) as client:
                response = await client.get("/gopro/media/list")
                response.raise_for_status()
                payload = response.json()
            files: list[CameraMediaFile] = []
            for directory in payload.get("media", []):
                directory_name = str(directory.get("d", "")).strip("/")
                for item in directory.get("fs", []):
                    filename = str(item.get("n", ""))
                    if not directory_name or not filename.upper().endswith(".MP4"):
                        continue
                    try:
                        size_bytes = max(0, int(item.get("s", 0)))
                    except (TypeError, ValueError):
                        size_bytes = 0
                    try:
                        created_at = datetime.fromtimestamp(int(item["cre"]), tz=timezone.utc)
                    except (KeyError, TypeError, ValueError, OSError):
                        created_at = None
                    files.append(CameraMediaFile(
                        path=f"{directory_name}/{filename}",
                        size_bytes=size_bytes,
                        created_at=created_at,
                    ))
            return files
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise CameraUnavailableError(f"{camera.name} 素材列表读取失败") from exc

    async def download_media(self, camera_id: str, remote_path: str, destination: Path, progress) -> int:
        camera = self._get_camera(camera_id)
        if remote_path.startswith("/") or ".." in Path(remote_path).parts:
            raise CameraUnavailableError("相机素材路径不合法")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        downloaded = 0
        try:
            async with self._client(camera) as client:
                async with client.stream(
                    "GET",
                    f"/videos/DCIM/{remote_path}",
                    timeout=httpx.Timeout(connect=5.0, read=None, write=30.0, pool=5.0),
                ) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as output:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            output.write(chunk)
                            downloaded += len(chunk)
                            await progress(len(chunk))
            temporary.replace(destination)
            return downloaded
        except (httpx.HTTPError, OSError) as exc:
            temporary.unlink(missing_ok=True)
            raise CameraUnavailableError(f"{camera.name} 下载 {remote_path} 失败") from exc
        except asyncio.CancelledError:
            temporary.unlink(missing_ok=True)
            raise

    async def mark_timecode_synced(self, camera_id: str) -> CameraStatus:
        camera = self._get_camera(camera_id)
        await self._sync_timecode(camera)
        return await self._fetch_status(camera)

    @staticmethod
    def _timecode_command(now: datetime | None = None) -> str:
        current = now or datetime.now(timezone.utc)
        milliseconds = current.microsecond // 1000
        return f'oT{current.strftime("%y%m%d%H%M%S")}.{milliseconds:03d}oTD0oTZ0oTI0'

    async def _sync_timecode(self, camera: RegisteredCamera) -> None:
        command = self._timecode_command()
        try:
            async with self._client(camera) as client:
                response = await client.get(
                    "/gopro/qrcode",
                    params={"labs": "1", "code": command},
                )
                response.raise_for_status()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise CameraUnavailableError(f"{camera.name} 时间码同步失败") from exc
        camera.timecode_synced_at = datetime.now(timezone.utc).isoformat()
        async with self._store_lock:
            await self._save()
