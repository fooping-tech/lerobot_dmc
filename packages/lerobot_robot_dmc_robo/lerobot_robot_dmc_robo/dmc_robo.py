from __future__ import annotations

import json
import logging
import time
from functools import cached_property
from io import BytesIO
from threading import Lock
from types import SimpleNamespace
from typing import Any

import numpy as np
from PIL import Image

from lerobot.robots import Robot
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .config_dmc_robo import DmcRoboConfig

logger = logging.getLogger(__name__)


def _key(robot_id: str, suffix: str) -> str:
    if not robot_id or "/" in robot_id:
        raise ValueError("robot_id must be non-empty and must not contain '/'")
    return f"dmc_robo/{robot_id}/{suffix}"


def _apply_connect_overrides(cfg: Any, mode: str, connect_endpoints: list[str]) -> Any:
    if mode:
        cfg.insert_json5("mode", json.dumps(mode))
    if connect_endpoints:
        cfg.insert_json5("connect/endpoints", json.dumps(connect_endpoints))
    return cfg


def _build_zenoh_config(config: DmcRoboConfig) -> Any:
    import zenoh

    if config.zenoh_config_path is not None and not config.zenoh_config_path.exists():
        raise FileNotFoundError(f"zenoh config not found: {config.zenoh_config_path}")

    if config.zenoh_config_path:
        cfg = zenoh.Config.from_file(str(config.zenoh_config_path))
    else:
        try:
            cfg = zenoh.Config.from_env()
        except Exception:
            cfg = zenoh.Config()

    if config.connect or config.connect_mode:
        cfg = _apply_connect_overrides(cfg, config.connect_mode, config.connect)

    return cfg


def _get_by_path(obj: Any, path: str) -> Any:
    cur = obj
    if not path or path in {".", "<root>"}:
        return cur
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, (list, tuple)):
            try:
                cur = cur[int(part)]
            except Exception:
                return None
        else:
            return None
    return cur


def _extract_vec3(payload: Any, path: str) -> tuple[float, float, float] | None:
    candidate = _get_by_path(payload, path)
    if candidate is None:
        return None

    if isinstance(candidate, dict):
        for keys in (("x", "y", "z"), ("gx", "gy", "gz"), ("wx", "wy", "wz")):
            x, y, z = candidate.get(keys[0]), candidate.get(keys[1]), candidate.get(keys[2])
            if all(isinstance(v, (int, float)) for v in (x, y, z)):
                return float(x), float(y), float(z)
        return None

    if isinstance(candidate, (list, tuple)) and len(candidate) >= 3:
        x, y, z = candidate[0], candidate[1], candidate[2]
        if all(isinstance(v, (int, float)) for v in (x, y, z)):
            return float(x), float(y), float(z)
        return None

    return None


def _autodetect_vec3(payload: Any) -> tuple[str | None, tuple[float, float, float] | None]:
    candidates = ("gyro", "gyr", "angular_velocity", "angularVelocity")
    for path in candidates:
        vec = _extract_vec3(payload, path)
        if vec is not None:
            return path, vec
    return None, None


def _coerce_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return default
    return default


def _coerce_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return default
    return default


def _coerce_str(value: Any, default: str) -> str:
    if isinstance(value, str):
        return value
    return default


def _default_motor_telemetry() -> dict[str, Any]:
    return {
        "motor.pw_l": 0,
        "motor.pw_r": 0,
        "motor.pw_l_raw": 0,
        "motor.pw_r_raw": 0,
        "motor.cmd_v_l": 0.0,
        "motor.cmd_v_r": 0.0,
        "motor.cmd_unit": "",
        "motor.cmd_deadman_ms": -1,
        "motor.cmd_seq": -1,
        "motor.cmd_ts_ms": -1,
        "motor.ts_ms": -1,
    }


def _normalize_motor_telemetry(payload: Any) -> dict[str, Any]:
    base = _default_motor_telemetry()
    if not isinstance(payload, dict):
        return base

    base["motor.pw_l"] = _coerce_int(payload.get("pw_l"), base["motor.pw_l"])
    base["motor.pw_r"] = _coerce_int(payload.get("pw_r"), base["motor.pw_r"])
    base["motor.pw_l_raw"] = _coerce_int(payload.get("pw_l_raw"), base["motor.pw_l_raw"])
    base["motor.pw_r_raw"] = _coerce_int(payload.get("pw_r_raw"), base["motor.pw_r_raw"])

    base["motor.cmd_v_l"] = _coerce_float(payload.get("cmd_v_l"), base["motor.cmd_v_l"])
    base["motor.cmd_v_r"] = _coerce_float(payload.get("cmd_v_r"), base["motor.cmd_v_r"])
    base["motor.cmd_unit"] = _coerce_str(payload.get("cmd_unit"), base["motor.cmd_unit"])
    base["motor.cmd_deadman_ms"] = _coerce_int(
        payload.get("cmd_deadman_ms"), base["motor.cmd_deadman_ms"]
    )
    base["motor.cmd_seq"] = _coerce_int(payload.get("cmd_seq"), base["motor.cmd_seq"])
    base["motor.cmd_ts_ms"] = _coerce_int(payload.get("cmd_ts_ms"), base["motor.cmd_ts_ms"])
    base["motor.ts_ms"] = _coerce_int(payload.get("ts_ms"), base["motor.ts_ms"])

    return base


def _extract_lidar_points(
    payload: Any,
) -> tuple[int | None, int | None, list[tuple[float, float, float | None]]]:
    seq = None
    ts_ms = None
    if isinstance(payload, dict):
        try:
            seq = payload.get("seq")
        except Exception:
            seq = None
        try:
            ts_ms = payload.get("ts_ms")
        except Exception:
            ts_ms = None

    points_any = payload.get("points") if isinstance(payload, dict) else None
    if not isinstance(points_any, list):
        return seq, ts_ms, []

    out: list[tuple[float, float, float | None]] = []
    for p in points_any:
        angle = None
        rng = None
        intensity: float | None = None

        if isinstance(p, dict):
            angle = p.get("angle_rad")
            rng = p.get("range_m")
            intensity_any = p.get("intensity")
            if isinstance(intensity_any, (int, float)):
                intensity = float(intensity_any)
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            angle = p[0]
            rng = p[1]
            if len(p) >= 3 and isinstance(p[2], (int, float)):
                intensity = float(p[2])

        if not isinstance(angle, (int, float)) or not isinstance(rng, (int, float)):
            continue
        out.append((float(angle), float(rng), intensity))

    return (
        int(seq) if isinstance(seq, int) else None,
        int(ts_ms) if isinstance(ts_ms, int) else None,
        out,
    )


class DmcRobo(Robot):
    config_class = DmcRoboConfig
    name = "dmc_robo"

    def __init__(self, config: DmcRoboConfig):
        super().__init__(config)
        self.config = config
        self.cameras = {
            "camera": SimpleNamespace(height=self.config.camera_height, width=self.config.camera_width)
        }
        self._session: Any | None = None
        self._pub_motor: Any | None = None
        self._sub_cam: Any | None = None
        self._sub_imu: Any | None = None
        self._sub_lidar: Any | None = None
        self._sub_motor_telemetry: Any | None = None

        self._lock = Lock()
        self._last_image: np.ndarray | None = None
        self._last_imu: np.ndarray | None = None
        self._last_lidar_points: list[tuple[float, float, float | None]] = []
        self._last_lidar_seq: int = -1
        self._last_lidar_ts_ms: int = -1
        self._last_motor_telemetry: dict[str, Any] = _default_motor_telemetry()
        self._auto_imu_path: str | None = None
        self._warned_camera_shape = False
        self._warned_camera_missing = False
        self._warned_imu_missing = False
        self._seq = 0

    @cached_property
    def observation_features(self) -> dict:
        return {
            "camera": (self.config.camera_height, self.config.camera_width, 3),
            "imu.gyro.x": float,
            "imu.gyro.y": float,
            "imu.gyro.z": float,
            "lidar.points": list,
            "lidar.seq": int,
            "lidar.ts_ms": int,
            "motor.pw_l": int,
            "motor.pw_r": int,
            "motor.pw_l_raw": int,
            "motor.pw_r_raw": int,
            "motor.cmd_v_l": float,
            "motor.cmd_v_r": float,
            "motor.cmd_unit": str,
            "motor.cmd_deadman_ms": int,
            "motor.cmd_seq": int,
            "motor.cmd_ts_ms": int,
            "motor.ts_ms": int,
        }

    @cached_property
    def action_features(self) -> dict:
        return {"v_l": float, "v_r": float}

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    def connect(self, calibrate: bool = True) -> None:
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        import zenoh

        cfg = _build_zenoh_config(self.config)
        try:
            session = zenoh.open(cfg)
        except Exception as e:
            raise ConnectionError(f"failed to open zenoh session: {e}") from e

        robot_id = self.config.robot_id
        self._pub_motor = session.declare_publisher(_key(robot_id, "motor/cmd"))

        def on_cam(sample: Any) -> None:
            jpg = sample.payload.to_bytes()
            try:
                with Image.open(BytesIO(jpg)) as img:
                    rgb = img.convert("RGB")
                    arr = np.asarray(rgb)
            except Exception as e:
                logger.warning("camera jpeg decode failed: %s", e)
                return

            if arr.dtype != np.uint8:
                arr = arr.astype(np.uint8, copy=False)

            if not self._warned_camera_shape:
                h, w = arr.shape[0], arr.shape[1]
                if h != self.config.camera_height or w != self.config.camera_width:
                    logger.warning(
                        "camera image shape mismatch (got=%sx%s expected=%sx%s)",
                        h,
                        w,
                        self.config.camera_height,
                        self.config.camera_width,
                    )
                    self._warned_camera_shape = True

            with self._lock:
                self._last_image = arr

        def on_imu(sample: Any) -> None:
            try:
                payload = json.loads(sample.payload.to_bytes().decode("utf-8"))
            except Exception as e:
                logger.warning("imu json decode failed: %s", e)
                return

            path = self.config.imu_field_path
            if not path and self._auto_imu_path:
                path = self._auto_imu_path

            vec = _extract_vec3(payload, path) if path else None
            if vec is None and not path:
                detected_path, vec = _autodetect_vec3(payload)
                if detected_path and vec is not None:
                    self._auto_imu_path = detected_path
                    logger.info("auto-detected imu field path: %s", detected_path)

            if vec is None:
                if not self._warned_imu_missing:
                    logger.warning("imu vector not found; set imu_field_path to extract gyro")
                    self._warned_imu_missing = True
                return

            with self._lock:
                self._last_imu = np.array(vec, dtype=np.float32)

        def on_lidar(sample: Any) -> None:
            try:
                payload = json.loads(sample.payload.to_bytes().decode("utf-8"))
            except Exception as e:
                logger.warning("lidar json decode failed: %s", e)
                return

            seq, ts_ms, points = _extract_lidar_points(payload)
            with self._lock:
                self._last_lidar_points = points
                if seq is not None:
                    self._last_lidar_seq = seq
                if ts_ms is not None:
                    self._last_lidar_ts_ms = ts_ms

        self._sub_cam = session.declare_subscriber(_key(robot_id, "camera/image/jpeg"), on_cam)
        self._sub_imu = session.declare_subscriber(_key(robot_id, "imu/state"), on_imu)
        self._sub_lidar = session.declare_subscriber(_key(robot_id, "lidar/scan"), on_lidar)
        if self.config.motor_telemetry_enabled:
            def on_motor_telemetry(sample: Any) -> None:
                try:
                    payload = json.loads(sample.payload.to_bytes().decode("utf-8"))
                except Exception as e:
                    logger.warning("motor telemetry json decode failed: %s", e)
                    return
                telemetry = _normalize_motor_telemetry(payload)
                with self._lock:
                    self._last_motor_telemetry = telemetry

            self._sub_motor_telemetry = session.declare_subscriber(
                _key(robot_id, "motor/telemetry"), on_motor_telemetry
            )

        self._session = session
        self.configure()
        logger.info("%s connected.", self)

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        return None

    def configure(self) -> None:
        return None

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError()

        deadline = time.monotonic() + float(self.config.camera_wait_timeout_s)
        image = None
        imu = None
        lidar_points: list[tuple[float, float, float | None]] = []
        lidar_seq = -1
        lidar_ts_ms = -1
        motor_telemetry: dict[str, Any] = _default_motor_telemetry()

        while True:
            with self._lock:
                image = self._last_image
                imu = self._last_imu
                lidar_points = list(self._last_lidar_points)
                lidar_seq = self._last_lidar_seq
                lidar_ts_ms = self._last_lidar_ts_ms
                motor_telemetry = dict(self._last_motor_telemetry)

            if image is not None:
                break
            if time.monotonic() > deadline:
                if self.config.camera_allow_missing:
                    if not self._warned_camera_missing:
                        logger.warning("no camera image received; returning blank frames")
                        self._warned_camera_missing = True
                    image = np.zeros(
                        (self.config.camera_height, self.config.camera_width, 3), dtype=np.uint8
                    )
                    break
                raise RuntimeError("no camera image received yet")
            time.sleep(0.05)

        if image is None:
            raise RuntimeError("no camera image received yet")

        if imu is None:
            imu = np.zeros(3, dtype=np.float32)

        return {
            "camera": image,
            "imu.gyro.x": float(imu[0]),
            "imu.gyro.y": float(imu[1]),
            "imu.gyro.z": float(imu[2]),
            "lidar.points": lidar_points,
            "lidar.seq": int(lidar_seq),
            "lidar.ts_ms": int(lidar_ts_ms),
            **motor_telemetry,
        }

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError()
        if self._pub_motor is None:
            raise RuntimeError("motor publisher not initialized")

        try:
            v_l = float(action["v_l"])
            v_r = float(action["v_r"])
        except Exception as e:
            raise ValueError("action must include float values for v_l and v_r") from e

        max_speed = self.config.max_speed_mps
        if max_speed is not None:
            v_l = max(-max_speed, min(max_speed, v_l))
            v_r = max(-max_speed, min(max_speed, v_r))

        with self._lock:
            seq = self._seq
            self._seq += 1

        payload = {
            "v_l": v_l,
            "v_r": v_r,
            "unit": "mps",
            "deadman_ms": int(self.config.deadman_ms),
            "seq": seq,
            "ts_ms": int(time.time() * 1000),
        }
        self._pub_motor.put(json.dumps(payload).encode("utf-8"))
        return payload

    def disconnect(self) -> None:
        if not self.is_connected:
            return

        try:
            self.send_action({"v_l": 0.0, "v_r": 0.0})
        except Exception:
            pass

        if self._sub_cam is not None:
            try:
                self._sub_cam.undeclare()
            except Exception:
                pass
            self._sub_cam = None

        if self._sub_imu is not None:
            try:
                self._sub_imu.undeclare()
            except Exception:
                pass
            self._sub_imu = None

        if self._sub_lidar is not None:
            try:
                self._sub_lidar.undeclare()
            except Exception:
                pass
            self._sub_lidar = None

        if self._sub_motor_telemetry is not None:
            try:
                self._sub_motor_telemetry.undeclare()
            except Exception:
                pass
            self._sub_motor_telemetry = None

        if self._pub_motor is not None:
            try:
                self._pub_motor.undeclare()
            except Exception:
                pass
            self._pub_motor = None

        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

        logger.info("%s disconnected.", self)
