import json
from pathlib import Path

import httpx

from app.adapters import CohnCameraAdapter, RegisteredCamera
from app.models import DiscoverCameraRequest, NetworkConfig, RecordingConfig, RecordingPreset, ShutterAction, UpdateCameraRequest


def test_builds_optional_recording_command_and_label() -> None:
    config = RecordingConfig(
        resolution="4K",
        fps=30,
        lens="wide",
        bit_depth=10,
        high_bitrate=True,
    )

    assert CohnCameraAdapter._build_recording_command(config) == "mVr4p30fWd10b1"
    assert CohnCameraAdapter._recording_config_label(config) == "4K · 30 FPS · Wide · 10-bit · 高码率"


def test_builds_sync_validation_preset_command_and_label() -> None:
    config = RecordingConfig(
        resolution="1080P",
        fps=30,
        lens="wide",
        bit_depth=8,
        color="natural",
        high_bitrate=False,
        stabilization="off",
        hindsight=False,
        shutter_speed=120,
        iso=400,
    )

    assert CohnCameraAdapter._build_recording_command(config) == (
        "mVr1p30fWd8cNb0e0hS0$EXPQ=120i4M4"
    )
    assert CohnCameraAdapter._recording_config_label(config) == (
        "1080P · 30 FPS · Wide · 8-bit · Natural · 标准码率 · "
        "防抖关 · Hindsight 关 · 快门 1/120 · ISO 400"
    )


def test_adapts_recording_config_to_hero9_capabilities() -> None:
    camera = RegisteredCamera(
        id="hero9", name="GP09", serial="SERIAL9", model_name="HERO9 Black",
        location="未设置", ip_address="192.168.1.9", username="gopro", password="secret",
        profile_label="", firmware_version="HD9.01.72.70",
    )
    config = RecordingConfig(
        resolution="5.3K_8_7", fps=60, lens="hyperview", bit_depth=10,
        color="natural", high_bitrate=True, stabilization="auto_boost",
        hindsight=False, shutter_speed=120, iso=400,
    )

    adapted = CohnCameraAdapter._config_for_camera(camera, config)

    assert adapted.resolution == "4K"
    assert adapted.fps == 60
    assert adapted.lens == "wide"
    assert adapted.bit_depth == 8
    assert adapted.color is None
    assert adapted.stabilization == "high"
    assert adapted.shutter_speed is None
    assert adapted.iso is None
    assert CohnCameraAdapter._hero9_setting_changes(adapted) == [
        (2, 1), (3, 5), (121, 0), (182, 1), (135, 2), (167, 0),
    ]
    assert "59.94 FPS" in CohnCameraAdapter._recording_config_label(adapted, hero9=True)


async def test_updates_recording_config_without_changing_credentials(tmp_path: Path) -> None:
    credentials_path = tmp_path / "config.json"
    credentials_path.write_text(json.dumps({
        "version": 1,
        "recording_config": {"resolution": "4K", "fps": 30},
        "cameras": [{"username": "gopro", "password": "secret", "last_known_ip": "192.168.1.10"}],
    }), encoding="utf-8")
    adapter = CohnCameraAdapter(tmp_path / "cameras.json", credentials_path=credentials_path)

    updated = await adapter.update_recording_config(RecordingConfig(resolution="1080P", fps=60))

    payload = json.loads(credentials_path.read_text(encoding="utf-8"))
    assert updated.resolution == "1080P"
    assert payload["recording_config"]["fps"] == 60
    assert payload["cameras"][0]["password"] == "secret"


async def test_saves_lists_and_deletes_custom_recording_preset(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "version": 1,
        "recording_config": {"resolution": "4K", "fps": 30},
        "cameras": [],
    }), encoding="utf-8")
    adapter = CohnCameraAdapter(tmp_path / "cameras.json", credentials_path=config_path)

    saved = await adapter.save_recording_preset(RecordingPreset(
        name="室内采集",
        config=RecordingConfig(resolution="4K", fps=60, stabilization="off"),
    ))

    assert saved.name == "室内采集"
    assert [preset.name for preset in adapter.get_recording_presets()] == [
        "日常 4K", "高帧率采集", "同步验证", "室内采集",
    ]
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["recording_presets"]["室内采集"]["fps"] == 60

    await adapter.delete_recording_preset("室内采集")

    assert "室内采集" not in json.loads(config_path.read_text(encoding="utf-8"))["recording_presets"]


async def test_updates_network_section_without_changing_other_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "version": 1,
        "recording_config": {"resolution": "4K", "fps": 30},
        "cameras": [{"username": "gopro", "password": "camera-secret"}],
    }), encoding="utf-8")
    adapter = CohnCameraAdapter(tmp_path / "cameras.json", credentials_path=config_path)

    updated = await adapter.update_network_config(NetworkConfig(ssid="EGO4D", password="wifi-secret"))

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert updated.ssid == "EGO4D"
    assert adapter.get_network_config().password == "wifi-secret"
    assert payload["recording_config"]["resolution"] == "4K"
    assert payload["cameras"][0]["password"] == "camera-secret"




async def test_discovers_controls_locates_and_reads_monitor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recording = False
    locate_calls = 0
    stream_start_calls = 0

    class FakeProcess:
        returncode = None

        class Stdout:
            def __init__(self) -> None:
                self.chunks = [b"noise\xff\xd8live-jpeg-data\xff\xd9", b""]

            async def read(self, size: int) -> bytes:
                return self.chunks.pop(0)

        stdout = Stdout()

        def terminate(self) -> None:
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr("app.adapters.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal recording, locate_calls, stream_start_calls
        if request.url.path == "/gopro/camera/info":
            return httpx.Response(200, json={
                "model_number": 91,
                "model_name": "HERO13 Black",
                "firmware_version": "HD13.02.10.70",
                "serial_number": "C3531234567890",
            })
        if request.url.path == "/gopro/camera/state":
            return httpx.Response(200, json={
                "status": {
                    "6": 0,
                    "10": 1 if recording else 0,
                    "13": 8,
                    "35": 7200,
                    "54": 64 * 1024 * 1024,
                    "70": 87,
                },
                "settings": {},
            })
        if request.url.path == "/gopro/camera/shutter/start":
            recording = True
            return httpx.Response(200, json={})
        if request.url.path == "/gopro/camera/shutter/stop":
            recording = False
            return httpx.Response(200, json={})
        if request.url.path == "/gopro/qrcode":
            if request.url.params["code"] == "!B2":
                locate_calls += 1
            else:
                assert request.url.params["code"].startswith("oT")
            return httpx.Response(200, json={})
        if request.url.path == "/gopro/camera/stream/start":
            stream_start_calls += 1
            assert request.url.params["port"] == "8554"
            return httpx.Response(200, json={})
        if request.url.path == "/gopro/camera/stream/stop":
            return httpx.Response(200, json={})
        if request.url.path == "/gopro/media/list":
            return httpx.Response(200, json={
                "id": "1",
                "media": [{"d": "100GOPRO", "fs": [{"n": "GX010001.MP4", "cre": "10", "s": "10"}]}],
            })
        if request.url.path == "/videos/DCIM/100GOPRO/GX010001.MP4":
            return httpx.Response(200, content=b"video-data")
        if request.url.path == "/gopro/media/thumbnail":
            assert request.url.params["path"] == "100GOPRO/GX010001.MP4"
            return httpx.Response(200, content=b"jpeg-data", headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    adapter = CohnCameraAdapter(
        tmp_path / "cameras.json",
        scan_cidrs="192.168.1.120/32",
        transport=httpx.MockTransport(handler),
    )
    discovered = await adapter.discover(DiscoverCameraRequest())

    assert discovered.discovered_count == 1
    registered = discovered.cameras[0]
    assert registered.name == "GP01"
    assert registered.serial == "C3531234567890"
    assert registered.model_name == "HERO13 Black"
    assert registered.firmware_version == "HD13.02.10.70"
    assert registered.battery_percent == 87
    assert registered.sd_remaining_minutes == 120
    assert registered.sd_remaining_gb == 64.0
    assert registered.timecode_synced_at is not None

    started = await adapter.set_shutter(registered.id, ShutterAction.START)
    assert started.recording is True
    stream = await adapter.open_monitor_stream(registered.id)
    frame = await anext(stream)
    assert b"live-jpeg-data" in frame
    await stream.aclose()
    assert stream_start_calls == 1
    stopped = await adapter.set_shutter(registered.id, ShutterAction.STOP)
    assert stopped.recording is False

    await adapter.locate(registered.id)
    assert locate_calls == 1
    content, content_type = await adapter.latest_thumbnail(registered.id)
    assert content == b"jpeg-data"
    assert content_type == "image/jpeg"
    media = await adapter.list_media(registered.id)
    assert media[0].path == "100GOPRO/GX010001.MP4"
    destination = tmp_path / "download.mp4"
    progress = 0

    async def record_progress(size: int) -> None:
        nonlocal progress
        progress += size

    await adapter.download_media(registered.id, media[0].path, destination, record_progress)
    assert destination.read_bytes() == b"video-data"
    assert progress == len(b"video-data")

    renamed = await adapter.update(registered.id, UpdateCameraRequest(name="头戴视角"))
    assert renamed.name == "头戴视角"

    reloaded = CohnCameraAdapter(
        tmp_path / "cameras.json",
        scan_cidrs="192.168.1.120/32",
        transport=httpx.MockTransport(handler),
    )
    assert len(await reloaded.list_statuses()) == 1


async def test_multiple_devices_keep_unique_monotonic_names(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/gopro/camera/info":
            suffix = request.url.host.split(".")[-1]
            return httpx.Response(200, json={
                "model_name": "HERO13 Black",
                "serial_number": f"SERIAL-{suffix}",
            })
        if request.url.path == "/gopro/camera/state":
            return httpx.Response(200, json={"status": {"10": 0, "35": 600, "54": 1024 * 1024}})
        if request.url.path == "/gopro/qrcode":
            return httpx.Response(200, json={})
        return httpx.Response(404)

    adapter = CohnCameraAdapter(
        tmp_path / "cameras.json",
        scan_cidrs="192.168.1.120/31",
        transport=httpx.MockTransport(handler),
    )
    first_discovery = await adapter.discover(DiscoverCameraRequest())
    assert [camera.name for camera in first_discovery.cameras] == ["GP01", "GP02"]

    await adapter.update("serial-120", UpdateCameraRequest(name="头戴视角"))
    await adapter.remove("serial-121")
    second_discovery = await adapter.discover(DiscoverCameraRequest())

    assert sorted(camera.name for camera in second_discovery.cameras) == ["GP03", "头戴视角"]

    reloaded = CohnCameraAdapter(
        tmp_path / "cameras.json",
        scan_cidrs="192.168.1.120/31",
        transport=httpx.MockTransport(handler),
    )
    assert sorted(camera.name for camera in await reloaded.list_statuses()) == ["GP03", "头戴视角"]


async def test_discovers_with_targeted_cohn_credentials(tmp_path: Path) -> None:
    credentials_path = tmp_path / "config.json"
    credentials_path.write_text(
        '{"cameras":[{"last_known_ip":"192.168.1.203","username":"gopro","password":"secret"}]}',
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.scheme == "https"
        assert request.url.host == "192.168.1.203"
        assert request.headers["authorization"] == "Basic Z29wcm86c2VjcmV0"
        if request.url.path == "/gopro/camera/info":
            return httpx.Response(200, json={
                "model_name": "HERO13 Black",
                "serial_number": "C3531325771270",
            })
        if request.url.path == "/gopro/camera/state":
            return httpx.Response(200, json={"status": {"10": 0, "35": 600}})
        if request.url.path == "/gopro/qrcode":
            return httpx.Response(200, json={})
        return httpx.Response(404)

    adapter = CohnCameraAdapter(
        tmp_path / "cameras.json",
        credentials_path=credentials_path,
        transport=httpx.MockTransport(handler),
    )

    discovered = await adapter.discover(DiscoverCameraRequest())

    assert discovered.discovered_count == 1
    assert discovered.cameras[0].serial == "C3531325771270"
    stored = json.loads((tmp_path / "cameras.json").read_text(encoding="utf-8"))
    assert stored["cameras"][0]["open_network"] is False
    assert stored["cameras"][0]["username"] == "gopro"
    assert stored["cameras"][0]["password"] == "secret"
