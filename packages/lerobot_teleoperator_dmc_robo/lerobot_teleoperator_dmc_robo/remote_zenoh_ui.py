#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _load_toml_file(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # py3.11+
    except Exception:  # pragma: no cover
        try:
            import tomli as tomllib  # type: ignore[assignment]
        except Exception as e:  # pragma: no cover
            raise SystemExit(
                "TOML config requested but TOML parser not available.\n"
                "Use Python 3.11+ (tomllib) or `pip install tomli`."
            ) from e

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"config not found: {path}")
    except Exception as e:
        raise SystemExit(f"failed to parse config: {path} ({e})") from e

    if not isinstance(data, dict):
        raise SystemExit(f"invalid config (expected TOML table at root): {path}")
    return data


def _toml_get(obj: Any, keys: tuple[str, ...], default: Any) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


@dataclass(frozen=True)
class UIConfig:
    motor_speed_step_mps: float = 0.50
    motor_publish_hz: float = 20.0
    motor_deadman_ms: int = 300
    lidar_update_hz: float = 10.0
    lidar_max_points: int = 5000
    lidar_range_m: float = 1.0
    lidar_flip_y: bool = False


def _load_ui_config(path: Optional[Path]) -> UIConfig:
    """
    Reads `config.toml` and returns UI defaults.

    Supported TOML keys:
      [motor] speed_step_mps, publish_hz, deadman_ms
      [lidar] update_hz, max_points, range_m, flip_y
    """
    if path is None:
        return UIConfig()

    data = _load_toml_file(path)
    motor = _toml_get(data, ("motor",), {})
    lidar = _toml_get(data, ("lidar",), {})

    def _f(x: Any, default: float) -> float:
        try:
            return float(x)
        except Exception:
            return float(default)

    def _i(x: Any, default: int) -> int:
        try:
            return int(x)
        except Exception:
            return int(default)

    def _b(x: Any, default: bool) -> bool:
        if isinstance(x, bool):
            return x
        return bool(default)

    speed_step = _clamp(
        _f(
            _toml_get(motor, ("speed_step_mps",), UIConfig.motor_speed_step_mps),
            UIConfig.motor_speed_step_mps,
        ),
        0.0,
        2.0,
    )
    publish_hz = _clamp(
        _f(_toml_get(motor, ("publish_hz",), UIConfig.motor_publish_hz), UIConfig.motor_publish_hz),
        1.0,
        60.0,
    )
    deadman = _clamp_int(
        _i(_toml_get(motor, ("deadman_ms",), UIConfig.motor_deadman_ms), UIConfig.motor_deadman_ms),
        50,
        2000,
    )

    lidar_update_hz = _clamp(
        _f(_toml_get(lidar, ("update_hz",), UIConfig.lidar_update_hz), UIConfig.lidar_update_hz),
        1.0,
        60.0,
    )
    lidar_max_points = _clamp_int(
        _i(
            _toml_get(lidar, ("max_points",), UIConfig.lidar_max_points),
            UIConfig.lidar_max_points,
        ),
        100,
        50000,
    )
    lidar_range_m = _clamp(
        _f(_toml_get(lidar, ("range_m",), UIConfig.lidar_range_m), UIConfig.lidar_range_m),
        0.0,
        1.0,
    )
    lidar_flip_y = _b(_toml_get(lidar, ("flip_y",), UIConfig.lidar_flip_y), UIConfig.lidar_flip_y)

    return UIConfig(
        motor_speed_step_mps=speed_step,
        motor_publish_hz=publish_hz,
        motor_deadman_ms=deadman,
        lidar_update_hz=lidar_update_hz,
        lidar_max_points=lidar_max_points,
        lidar_range_m=lidar_range_m,
        lidar_flip_y=lidar_flip_y,
    )


def _key(robot_id: str, suffix: str) -> str:
    if not robot_id or "/" in robot_id:
        raise SystemExit("robot_id must be non-empty and must not contain '/'")
    return f"dmc_robo/{robot_id}/{suffix}"


def _apply_connect_overrides(cfg: Any, mode: str, connect_endpoints: list[str]) -> Any:
    if mode:
        cfg.insert_json5("mode", json.dumps(mode))
    if connect_endpoints:
        cfg.insert_json5("connect/endpoints", json.dumps(connect_endpoints))
    return cfg


def _build_session_opener(
    *, config_path: Optional[Path], mode: str, connect_endpoints: list[str]
):
    import zenoh  # provided by `pip install eclipse-zenoh`

    if config_path is not None and not config_path.exists():
        raise SystemExit(
            f"zenoh config not found: {config_path}\n"
            "Create it (see docs/zenoh_remote_pubsub.md) or omit --zenoh-config to use defaults."
        )

    if config_path:
        cfg = zenoh.Config.from_file(str(config_path))
    else:
        try:
            cfg = zenoh.Config.from_env()
        except Exception:
            cfg = zenoh.Config()

    if connect_endpoints:
        cfg = _apply_connect_overrides(cfg, mode, connect_endpoints)

    def _opener() -> Any:
        try:
            return zenoh.open(cfg)
        except Exception as e:
            raise SystemExit(f"failed to open zenoh session: {e}") from e

    return _opener


class _Bridge:
    def __init__(self) -> None:
        from PySide6.QtCore import QObject, Signal

        class _B(QObject):
            log = Signal(str)
            imu = Signal(object)  # dict
            cam_jpeg = Signal(bytes)
            cam_meta = Signal(object)  # dict
            lidar_scan = Signal(object)  # dict
            lidar_front = Signal(object)  # dict

        self._b = _B()

    @property
    def qobj(self):
        return self._b


def _decode_json_payload(sample: Any) -> Any:
    raw = sample.payload.to_bytes()
    return json.loads(raw.decode("utf-8"))


@dataclass
class MotorCommand:
    v_l: float
    v_r: float
    unit: str
    deadman_ms: int
    seq: int
    ts_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "v_l": self.v_l,
            "v_r": self.v_r,
            "unit": self.unit,
            "deadman_ms": int(self.deadman_ms),
            "seq": int(self.seq),
            "ts_ms": int(self.ts_ms),
        }

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict()).encode("utf-8")


class ZenohClient:
    def __init__(
        self, *, open_session: Any, robot_id: str, bridge: _Bridge, print_publish: bool
    ) -> None:
        self._open_session = open_session
        self._robot_id = robot_id
        self._bridge = bridge
        self._print_publish = bool(print_publish)

        self._session: Any = None
        self._pub_motor: Any = None
        self._pub_oled: Any = None
        self._sub_imu: Any = None
        self._sub_cam_meta: Any = None
        self._sub_cam_jpeg: Any = None
        self._sub_lidar_scan: Any = None
        self._sub_lidar_front: Any = None

    def open(self) -> None:
        self._session = self._open_session()
        key_motor = _key(self._robot_id, "motor/cmd")
        key_oled = _key(self._robot_id, "oled/cmd")
        self._pub_motor = self._session.declare_publisher(key_motor)
        self._pub_oled = self._session.declare_publisher(key_oled)
        self._key_motor = key_motor
        self._key_oled = key_oled
        if self._print_publish:
            print(f"[pub] motor: {key_motor}", flush=True)
            print(f"[pub] oled : {key_oled}", flush=True)

        def on_imu(sample: Any) -> None:
            try:
                payload = _decode_json_payload(sample)
                self._bridge.qobj.imu.emit(payload)
            except Exception as e:
                self._bridge.qobj.log.emit(f"imu decode failed: {e}")

        def on_meta(sample: Any) -> None:
            try:
                payload = _decode_json_payload(sample)
                self._bridge.qobj.cam_meta.emit(payload)
            except Exception:
                return

        def on_jpeg(sample: Any) -> None:
            try:
                jpg = sample.payload.to_bytes()
                self._bridge.qobj.cam_jpeg.emit(jpg)
            except Exception as e:
                self._bridge.qobj.log.emit(f"camera jpeg receive failed: {e}")

        def on_lidar_scan(sample: Any) -> None:
            try:
                payload = _decode_json_payload(sample)
                self._bridge.qobj.lidar_scan.emit(payload)
            except Exception as e:
                self._bridge.qobj.log.emit(f"lidar/scan decode failed: {e}")

        def on_lidar_front(sample: Any) -> None:
            try:
                payload = _decode_json_payload(sample)
                self._bridge.qobj.lidar_front.emit(payload)
            except Exception as e:
                self._bridge.qobj.log.emit(f"lidar/front decode failed: {e}")

        self._sub_imu = self._session.declare_subscriber(_key(self._robot_id, "imu/state"), on_imu)
        self._sub_cam_meta = self._session.declare_subscriber(
            _key(self._robot_id, "camera/meta"), on_meta
        )
        self._sub_cam_jpeg = self._session.declare_subscriber(
            _key(self._robot_id, "camera/image/jpeg"), on_jpeg
        )
        self._sub_lidar_scan = self._session.declare_subscriber(
            _key(self._robot_id, "lidar/scan"), on_lidar_scan
        )
        self._sub_lidar_front = self._session.declare_subscriber(
            _key(self._robot_id, "lidar/front"), on_lidar_front
        )

        self._bridge.qobj.log.emit("zenoh connected")

    def close(self) -> None:
        try:
            if self._sub_lidar_front is not None:
                self._sub_lidar_front.undeclare()
        finally:
            self._sub_lidar_front = None

        try:
            if self._sub_lidar_scan is not None:
                self._sub_lidar_scan.undeclare()
        finally:
            self._sub_lidar_scan = None

        try:
            if self._sub_cam_jpeg is not None:
                self._sub_cam_jpeg.undeclare()
        finally:
            self._sub_cam_jpeg = None

        try:
            if self._sub_cam_meta is not None:
                self._sub_cam_meta.undeclare()
        finally:
            self._sub_cam_meta = None

        try:
            if self._sub_imu is not None:
                self._sub_imu.undeclare()
        finally:
            self._sub_imu = None

        try:
            if self._session is not None:
                self._session.close()
        finally:
            self._session = None
            self._pub_motor = None
            self._pub_oled = None

    def publish_motor(self, cmd: MotorCommand) -> None:
        self.publish_motor_ex(cmd, print_msg=None)

    def publish_motor_ex(self, cmd: MotorCommand, *, print_msg: Optional[bool]) -> None:
        if self._pub_motor is None:
            return
        payload = cmd.to_dict()
        self._pub_motor.put(json.dumps(payload).encode("utf-8"))
        do_print = self._print_publish if print_msg is None else bool(print_msg)
        if do_print:
            key = getattr(self, "_key_motor", "motor/cmd")
            print(f"[pub] {key} {json.dumps(payload, ensure_ascii=False)}", flush=True)

    def publish_oled(self, text: str) -> None:
        self.publish_oled_ex(text, print_msg=None)

    def publish_oled_ex(self, text: str, *, print_msg: Optional[bool]) -> None:
        if self._pub_oled is None:
            return
        payload = {"text": str(text), "ts_ms": int(time.time() * 1000)}
        self._pub_oled.put(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        do_print = self._print_publish if print_msg is None else bool(print_msg)
        if do_print:
            key = getattr(self, "_key_oled", "oled/cmd")
            print(f"[pub] {key} {json.dumps(payload, ensure_ascii=False)}", flush=True)


def _get_by_path(obj: Any, path: str) -> Any:
    cur = obj
    if not path:
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


def _extract_vec3(payload: Any, path: str) -> Optional[tuple[float, float, float]]:
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


def _autodetect_vec3(payload: Any) -> tuple[Optional[str], Optional[tuple[float, float, float]]]:
    candidates = ("gyro", "gyr", "angular_velocity", "angularVelocity")
    for path in candidates:
        vec = _extract_vec3(payload, path)
        if vec is not None:
            return path, vec

    q: deque[tuple[str, Any]] = deque([("", payload)])
    seen: set[int] = set()
    max_nodes = 500

    def _push(base: str, k: str, v: Any) -> None:
        if base:
            q.append((f"{base}.{k}", v))
        else:
            q.append((k, v))

    while q and max_nodes > 0:
        max_nodes -= 1
        path, obj = q.popleft()
        obj_id = id(obj)
        if obj_id in seen:
            continue
        seen.add(obj_id)

        if isinstance(obj, dict):
            vec = _extract_vec3(obj, "")  # type: ignore[arg-type]
        elif isinstance(obj, (list, tuple)):
            vec = _extract_vec3({"v": obj}, "v")
        else:
            vec = None
        if vec is not None:
            return (path or "<root>"), vec

        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str):
                    _push(path, k, v)
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj[:10]):
                _push(path, str(i), v)

    return None, None


def _extract_lidar_points(payload: Any) -> tuple[Optional[int], Optional[int], list[tuple[float, float, Optional[float]]]]:
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
        return None, None, []

    out: list[tuple[float, float, Optional[float]]] = []
    for p in points_any:
        angle = None
        rng = None
        intensity: Optional[float] = None

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


class MainWindow:
    def __init__(
        self, *, client: ZenohClient, bridge: _Bridge, args: argparse.Namespace, ui_config: UIConfig
    ) -> None:
        from PySide6.QtCore import QEvent, QObject, QTimer, Qt
        from PySide6.QtGui import QAction, QCloseEvent, QFont, QKeyEvent
        from PySide6.QtWidgets import (
            QAbstractSpinBox,
            QCheckBox,
            QDoubleSpinBox,
            QFormLayout,
            QFrame,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QSpinBox,
            QSizePolicy,
            QSplitter,
            QVBoxLayout,
            QWidget,
        )

        import pyqtgraph as pg
        import numpy as np

        self._Qt = Qt
        self._QCloseEvent = QCloseEvent
        self._QEvent = QEvent
        self._QObject = QObject
        self._QKeyEvent = QKeyEvent
        self._QMessageBox = QMessageBox
        self._np = np

        self._client = client
        self._bridge = bridge
        self._args = args
        self._ui_config = ui_config

        self._seq = 0
        self._pressed: set[int] = set()
        self._last_nonzero = False
        self._closing = False
        self._print_publish = bool(getattr(args, "print_pub", False))
        self._print_pub_motor_all = bool(getattr(args, "print_pub_motor_all", False))
        self._last_motor_print: Optional[tuple[float, float]] = None
        self._last_motor_print_t = 0.0
        self._motor_last_pub_t: Optional[float] = None
        self._motor_dt_s: deque[float] = deque(maxlen=200)
        self._motor_period_last_print_t = 0.0
        self._print_motor_period = bool(getattr(args, "print_motor_period", False))

        class _Win(QMainWindow):
            def __init__(self, owner: "MainWindow"):
                super().__init__()
                self._owner = owner

            def closeEvent(self, event: QCloseEvent) -> None:
                self._owner._on_close()
                event.accept()

        self._win = _Win(self)
        self._win.setWindowTitle(f"Zenoh Remote UI ({args.robot_id})")
        self._win.setMinimumSize(1100, 700)

        central = QWidget()
        central.setFocusPolicy(Qt.StrongFocus)
        root = QHBoxLayout(central)
        self._win.setCentralWidget(central)
        self._focus_sink = central

        # Left: controls + logs
        left = QWidget()
        left_layout = QVBoxLayout(left)

        conn_box = QGroupBox("Connection")
        conn_form = QFormLayout(conn_box)
        self._lbl_status = QLabel("connecting...")
        self._lbl_status.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        conn_form.addRow("status", self._lbl_status)
        self._lbl_keys = QLabel(
            "motor: left r/f, right u/j, arrows (release to stop)\n"
            "note: key capture disabled while typing in text fields"
        )
        conn_form.addRow("keys", self._lbl_keys)
        left_layout.addWidget(conn_box)

        motor_box = QGroupBox("Motor")
        motor_form = QFormLayout(motor_box)
        self._spin_step = QDoubleSpinBox()
        self._spin_step.setRange(0.0, 2.0)
        self._spin_step.setSingleStep(0.1)
        self._spin_step.setDecimals(3)
        self._spin_step.setValue(float(self._ui_config.motor_speed_step_mps))
        motor_form.addRow("speed step (mps)", self._spin_step)
        self._spin_hz = QDoubleSpinBox()
        self._spin_hz.setRange(1.0, 60.0)
        self._spin_hz.setDecimals(1)
        self._spin_hz.setValue(float(self._ui_config.motor_publish_hz))
        motor_form.addRow("publish Hz", self._spin_hz)
        self._spin_deadman = QSpinBox()
        self._spin_deadman.setRange(50, 2000)
        self._spin_deadman.setValue(int(self._ui_config.motor_deadman_ms))
        motor_form.addRow("deadman ms", self._spin_deadman)
        self._btn_stop = QPushButton("STOP (send zero)")
        motor_form.addRow(self._btn_stop)
        self._lbl_motor = QLabel("v_l=0.000 v_r=0.000")
        self._lbl_motor.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        motor_form.addRow("last cmd", self._lbl_motor)
        self._lbl_motor_period = QLabel("dt=-- avg=--")
        self._lbl_motor_period.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        motor_form.addRow("pub period", self._lbl_motor_period)
        left_layout.addWidget(motor_box)

        oled_box = QGroupBox("OLED")
        oled_form = QFormLayout(oled_box)
        self._edit_oled = QLineEdit()
        self._btn_oled = QPushButton("Send")
        row = QWidget()
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.addWidget(self._edit_oled, 1)
        row_l.addWidget(self._btn_oled)
        oled_form.addRow("text", row)
        left_layout.addWidget(oled_box)

        imu_box = QGroupBox("IMU (gyro)")
        imu_form = QFormLayout(imu_box)
        self._combo_gyro_path = QLineEdit()
        self._combo_gyro_path.setPlaceholderText("auto (examples: gyro, angular_velocity)")
        imu_form.addRow("field path", self._combo_gyro_path)
        self._lbl_gyro_path = QLabel("auto: (not detected yet)")
        self._lbl_gyro_path.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        imu_form.addRow("auto detect", self._lbl_gyro_path)
        self._lbl_gyro = QLabel("x=-- y=-- z=--")
        self._lbl_gyro.setFont(QFont("Monospace"))
        self._lbl_gyro.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        imu_form.addRow("latest", self._lbl_gyro)
        left_layout.addWidget(imu_box)

        lidar_box = QGroupBox("LiDAR")
        lidar_form = QFormLayout(lidar_box)
        self._spin_lidar_max_points = QSpinBox()
        self._spin_lidar_max_points.setRange(100, 50000)
        self._spin_lidar_max_points.setValue(int(self._ui_config.lidar_max_points))
        lidar_form.addRow("max points", self._spin_lidar_max_points)
        self._spin_lidar_range_m = QDoubleSpinBox()
        self._spin_lidar_range_m.setRange(0.0, 1.0)
        self._spin_lidar_range_m.setDecimals(2)
        self._spin_lidar_range_m.setSingleStep(0.5)
        self._spin_lidar_range_m.setValue(float(self._ui_config.lidar_range_m))
        lidar_form.addRow("range max (m) (<=1.0)", self._spin_lidar_range_m)
        self._chk_lidar_flip_y = QCheckBox("flip Y (front/back)")
        self._chk_lidar_flip_y.setChecked(bool(self._ui_config.lidar_flip_y))
        lidar_form.addRow(self._chk_lidar_flip_y)
        self._lbl_lidar = QLabel("scan: --")
        self._lbl_lidar.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        lidar_form.addRow("status", self._lbl_lidar)
        self._lbl_lidar_front = QLabel("front: --")
        self._lbl_lidar_front.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        lidar_form.addRow("front", self._lbl_lidar_front)
        left_layout.addWidget(lidar_box)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(2000)
        left_layout.addWidget(QLabel("Log"))
        left_layout.addWidget(self._log, 1)

        # Right: camera + lidar + chart + raw json
        right_split = QSplitter()
        right_split.setOrientation(Qt.Vertical)

        cam_panel = QWidget()
        cam_layout = QVBoxLayout(cam_panel)
        cam_layout.setContentsMargins(0, 0, 0, 0)
        self._cam_label = QLabel("camera: waiting for jpeg...")
        self._cam_label.setAlignment(Qt.AlignCenter)
        self._cam_label.setMinimumHeight(300)
        self._cam_label.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self._lbl_cam_meta = QLabel("meta: --")
        self._lbl_cam_meta.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        cam_layout.addWidget(self._cam_label, 1)
        cam_layout.addWidget(self._lbl_cam_meta)
        right_split.addWidget(cam_panel)

        lidar_panel = QWidget()
        lidar_layout = QVBoxLayout(lidar_panel)
        lidar_layout.setContentsMargins(0, 0, 0, 0)

        class _SquarePlotWidget(pg.PlotWidget):
            def resizeEvent(self, ev) -> None:  # type: ignore[override]
                super().resizeEvent(ev)
                w = max(200, int(self.width()))
                self.setMinimumHeight(w)
                self.setMaximumHeight(w)

        self._lidar_plot = _SquarePlotWidget()
        self._lidar_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._lidar_plot.showGrid(x=True, y=True, alpha=0.25)
        self._lidar_plot.setAspectLocked(True)
        self._lidar_plot.setLabel("left", "y", units="m")
        self._lidar_plot.setLabel("bottom", "x", units="m")
        self._lidar_plot.enableAutoRange(False)
        self._lidar_plot.setXRange(-1.0, 1.0, padding=0.0)
        self._lidar_plot.setYRange(-1.0, 1.0, padding=0.0)
        self._lidar_plot.setTitle("LiDAR (top view) 2m x 2m")

        self._lidar_axis_x = pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen((150, 150, 150), style=Qt.DashLine))
        self._lidar_axis_y = pg.InfiniteLine(pos=0.0, angle=90, pen=pg.mkPen((150, 150, 150), style=Qt.DashLine))
        self._lidar_plot.addItem(self._lidar_axis_x)
        self._lidar_plot.addItem(self._lidar_axis_y)

        self._lidar_robot = pg.ScatterPlotItem(size=14, pen=pg.mkPen("c", width=2), brush=pg.mkBrush(0, 200, 200, 120))
        self._lidar_robot.setData(pos=[(0.0, 0.0)])
        self._lidar_plot.addItem(self._lidar_robot)

        # Robot heading is +Y (up).
        self._lidar_front_line = pg.PlotDataItem([0.0, 0.0], [0.0, 0.35], pen=pg.mkPen("c", width=3))
        self._lidar_plot.addItem(self._lidar_front_line)
        self._lidar_front_arrow = pg.ArrowItem(pos=(0.0, 0.35), angle=90, brush=pg.mkBrush("c"), pen=pg.mkPen("c"))
        self._lidar_plot.addItem(self._lidar_front_arrow)

        self._lidar_scatter = pg.ScatterPlotItem(size=2, pen=None, brush=pg.mkBrush(255, 255, 0, 200))
        self._lidar_plot.addItem(self._lidar_scatter)
        lidar_layout.addWidget(self._lidar_plot, 1)
        right_split.addWidget(lidar_panel)

        imu_panel = QWidget()
        imu_layout = QVBoxLayout(imu_panel)
        imu_layout.setContentsMargins(0, 0, 0, 0)
        pg.setConfigOptions(antialias=True)
        self._plot = pg.PlotWidget()
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.addLegend()
        self._plot.setLabel("left", "gyro")
        self._plot.setLabel("bottom", "t", units="s")
        self._curve_x = self._plot.plot([], [], pen=pg.mkPen("r", width=2), name="x")
        self._curve_y = self._plot.plot([], [], pen=pg.mkPen("g", width=2), name="y")
        self._curve_z = self._plot.plot([], [], pen=pg.mkPen("b", width=2), name="z")
        self._raw = QPlainTextEdit()
        self._raw.setReadOnly(True)
        self._raw.setMaximumBlockCount(2000)
        self._raw.setPlaceholderText("imu raw JSON will appear here")
        imu_layout.addWidget(self._plot, 2)
        imu_layout.addWidget(QLabel("IMU raw JSON"))
        imu_layout.addWidget(self._raw, 1)
        right_split.addWidget(imu_panel)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right_split)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        # Menus
        action_quit = QAction("Quit", self._win)
        action_quit.triggered.connect(self._win.close)
        self._win.menuBar().addAction(action_quit)

        # Data buffers
        self._t0 = time.monotonic()
        self._buf_t: deque[float] = deque(maxlen=400)
        self._buf_x: deque[float] = deque(maxlen=400)
        self._buf_y: deque[float] = deque(maxlen=400)
        self._buf_z: deque[float] = deque(maxlen=400)

        # Wiring
        self._btn_oled.clicked.connect(self._on_send_oled)
        self._btn_stop.clicked.connect(lambda: self._send_stop(repeat=3))

        bridge.qobj.log.connect(self._append_log)
        bridge.qobj.imu.connect(self._on_imu)
        bridge.qobj.cam_jpeg.connect(self._on_cam_jpeg)
        bridge.qobj.cam_meta.connect(self._on_cam_meta)
        bridge.qobj.lidar_scan.connect(self._on_lidar_scan)
        bridge.qobj.lidar_front.connect(self._on_lidar_front)

        # Motor publish timer
        self._motor_timer = QTimer()
        self._motor_timer.timeout.connect(self._tick_motor)
        self._motor_timer.start(int(1000 / float(self._spin_hz.value())))
        self._spin_hz.valueChanged.connect(self._on_hz_changed)

        # Global key capture
        self._typing_widgets = (QLineEdit, QPlainTextEdit, QAbstractSpinBox)

        class _KeyFilter(QObject):
            def __init__(self, owner: "MainWindow"):
                super().__init__()
                self._owner = owner

            def eventFilter(self, obj: Any, event: Any) -> bool:
                return self._owner._event_filter(obj, event)

        self._key_filter = _KeyFilter(self)

        # LiDAR update throttling
        self._lidar_last_scan: Optional[dict[str, Any]] = None
        self._lidar_timer = QTimer()
        self._lidar_timer.timeout.connect(self._tick_lidar)
        self._lidar_timer.start(max(10, int(1000.0 / float(self._ui_config.lidar_update_hz))))

        # Open Zenoh now
        try:
            self._client.open()
            self._lbl_status.setText("connected")
        except SystemExit:
            raise
        except Exception as e:
            self._lbl_status.setText("error")
            self._append_log(f"connect failed: {e}")
            QMessageBox.critical(self._win, "Zenoh connect failed", str(e))

    def show(self) -> None:
        self._win.show()

    def _append_log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{ts}] {msg}")

    def _event_filter(self, obj: Any, event: Any) -> bool:
        from PySide6.QtWidgets import QApplication, QPlainTextEdit

        if event.type() in (self._QEvent.ApplicationDeactivate, self._QEvent.WindowDeactivate):
            if self._pressed:
                self._pressed.clear()
                self._send_stop(repeat=2)
            return False

        if event.type() not in (self._QEvent.KeyPress, self._QEvent.KeyRelease):
            return False

        focused = QApplication.focusWidget()

        # ESC clears focus so arrow keys won't modify focused input widgets (spinboxes, text fields).
        # After clearing, focus goes to the main window so motor keys work immediately.
        if event.type() == self._QEvent.KeyPress:
            try:
                if event.key() == self._Qt.Key_Escape and focused is not None:
                    focused.clearFocus()
                    self._focus_sink.setFocus()
                    return True
            except Exception:
                pass

        if focused is not None:
            if isinstance(focused, QPlainTextEdit) and focused.isReadOnly():
                pass
            elif isinstance(focused, self._typing_widgets):
                return False

        ev = event  # QKeyEvent
        key = ev.key()
        if key not in (
            self._Qt.Key_R,
            self._Qt.Key_F,
            self._Qt.Key_U,
            self._Qt.Key_J,
            self._Qt.Key_Up,
            self._Qt.Key_Down,
            self._Qt.Key_Left,
            self._Qt.Key_Right,
        ):
            return False

        if event.type() == self._QEvent.KeyPress and not ev.isAutoRepeat():
            self._pressed.add(key)
            return True
        if event.type() == self._QEvent.KeyRelease and not ev.isAutoRepeat():
            self._pressed.discard(key)
            if not self._pressed:
                self._send_stop(repeat=2)
            return True
        return False

    def _on_hz_changed(self, v: float) -> None:
        try:
            interval_ms = int(1000 / float(v))
        except Exception:
            interval_ms = 50
        self._motor_timer.setInterval(max(10, interval_ms))

    def _desired_motor(self) -> tuple[float, float]:
        step = float(self._spin_step.value())

        # Arrow-key driving (combined command) takes priority over per-wheel keys.
        up = self._Qt.Key_Up in self._pressed
        right = self._Qt.Key_Right in self._pressed
        left = self._Qt.Key_Left in self._pressed
        down = self._Qt.Key_Down in self._pressed

        # When moving forward, allow "add turn" by pressing left/right:
        # - Up + Right => right wheel is 0.5x (gentle right)
        # - Up + Left  => left wheel is 0.5x (gentle left)
        if up and right and not left:
            return step, step * 0.5
        if up and left and not right:
            return step * 0.5, step

        # When moving backward, allow "add turn" by pressing left/right:
        # - Down + Right => right wheel is 0.5x (gentle right while reversing)
        # - Down + Left  => left wheel is 0.5x (gentle left while reversing)
        if down and right and not left:
            return -step, -step * 0.5
        if down and left and not right:
            return -step * 0.5, -step

        if up:
            return step, step
        if down:
            return -step, -step
        if self._Qt.Key_Left in self._pressed:
            return -step * 0.3, step * 0.3
        if self._Qt.Key_Right in self._pressed:
            return step * 0.3, -step * 0.3

        left = 0.0
        right = 0.0

        if self._Qt.Key_R in self._pressed:
            left += step
        if self._Qt.Key_F in self._pressed:
            left -= step

        if self._Qt.Key_U in self._pressed:
            right += step
        if self._Qt.Key_J in self._pressed:
            right -= step

        return left, right

    def _tick_motor(self) -> None:
        if self._closing:
            return
        v_l, v_r = self._desired_motor()
        nonzero = (abs(v_l) > 1e-9) or (abs(v_r) > 1e-9)
        if not nonzero:
            if self._last_nonzero:
                self._send_stop(repeat=1)
            self._last_nonzero = False
            return

        self._last_nonzero = True
        self._lbl_motor.setText(f"v_l={v_l:+.3f} v_r={v_r:+.3f}")
        cmd = MotorCommand(
            v_l=v_l,
            v_r=v_r,
            unit="mps",
            deadman_ms=int(self._spin_deadman.value()),
            seq=self._seq,
            ts_ms=int(time.time() * 1000),
        )
        self._seq += 1
        try:
            now = time.monotonic()
            # Avoid flooding the terminal: by default print only on change or <=1 Hz.
            if self._print_publish and not self._print_pub_motor_all:
                cur = (cmd.v_l, cmd.v_r)
                if (cur != self._last_motor_print) or (now - self._last_motor_print_t >= 1.0):
                    self._last_motor_print = cur
                    self._last_motor_print_t = now
                    self._client.publish_motor_ex(cmd, print_msg=True)
                else:
                    self._client.publish_motor_ex(cmd, print_msg=False)
            elif self._print_publish and self._print_pub_motor_all:
                self._client.publish_motor_ex(cmd, print_msg=True)
            else:
                self._client.publish_motor(cmd)

            self._record_motor_pub(now)
        except Exception as e:
            self._append_log(f"motor publish failed: {e}")

    def _record_motor_pub(self, now: float) -> None:
        last = self._motor_last_pub_t
        self._motor_last_pub_t = now
        if last is None:
            return

        dt = now - last
        if dt <= 0:
            return

        self._motor_dt_s.append(dt)
        dt_ms = dt * 1000.0
        avg = sum(self._motor_dt_s) / max(1, len(self._motor_dt_s))
        avg_ms = avg * 1000.0
        hz = 1.0 / avg if avg > 0 else 0.0
        self._lbl_motor_period.setText(f"dt={dt_ms:5.1f}ms avg={avg_ms:5.1f}ms ({hz:4.1f}Hz)")

        if self._print_motor_period and (now - self._motor_period_last_print_t >= 1.0):
            self._motor_period_last_print_t = now
            print(
                f"[motor period] dt={dt_ms:.1f}ms avg={avg_ms:.1f}ms hz={hz:.2f} (n={len(self._motor_dt_s)})",
                flush=True,
            )

    def _send_stop(self, *, repeat: int) -> None:
        self._lbl_motor.setText("v_l=+0.000 v_r=+0.000")
        for _ in range(max(1, int(repeat))):
            cmd = MotorCommand(
                v_l=0.0,
                v_r=0.0,
                unit="mps",
                deadman_ms=int(self._spin_deadman.value()),
                seq=self._seq,
                ts_ms=int(time.time() * 1000),
            )
            self._seq += 1
            try:
                now = time.monotonic()
                if self._print_publish and self._print_pub_motor_all:
                    self._client.publish_motor_ex(cmd, print_msg=True)
                else:
                    self._client.publish_motor(cmd)
                self._record_motor_pub(now)
            except Exception as e:
                self._append_log(f"stop publish failed: {e}")
                break

    def _on_send_oled(self) -> None:
        text = self._edit_oled.text()
        if not text:
            self._QMessageBox.information(self._win, "OLED", "text is empty")
            return
        try:
            self._client.publish_oled(text)
            self._append_log(f"oled sent: {text!r}")
        except Exception as e:
            self._append_log(f"oled publish failed: {e}")

    def _on_imu(self, payload: Any) -> None:
        try:
            self._raw.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception:
            self._raw.setPlainText(str(payload))

        path = self._combo_gyro_path.text().strip()
        vec = None
        if path:
            vec = _extract_vec3(payload, path)
        else:
            detected_path, vec = _autodetect_vec3(payload)
            if detected_path:
                self._lbl_gyro_path.setText(f"auto: {detected_path}")
            else:
                self._lbl_gyro_path.setText("auto: (not found)")

        if vec is None:
            self._lbl_gyro.setText("x=-- y=-- z=-- (set field path)")
            return

        x, y, z = vec
        self._lbl_gyro.setText(f"x={x:+.4f} y={y:+.4f} z={z:+.4f}")
        t = time.monotonic() - self._t0
        self._buf_t.append(t)
        self._buf_x.append(x)
        self._buf_y.append(y)
        self._buf_z.append(z)
        self._curve_x.setData(list(self._buf_t), list(self._buf_x))
        self._curve_y.setData(list(self._buf_t), list(self._buf_y))
        self._curve_z.setData(list(self._buf_t), list(self._buf_z))

    def _on_cam_meta(self, payload: Any) -> None:
        try:
            self._lbl_cam_meta.setText("meta: " + json.dumps(payload, ensure_ascii=False))
        except Exception:
            self._lbl_cam_meta.setText("meta: (decode failed)")

    def _on_cam_jpeg(self, jpg: bytes) -> None:
        from PySide6.QtGui import QImage, QPixmap

        img = QImage.fromData(jpg, "JPG")
        if img.isNull():
            self._append_log(f"camera jpeg decode failed (bytes={len(jpg)})")
            return
        pix = QPixmap.fromImage(img)
        scaled = pix.scaled(
            self._cam_label.size(), self._Qt.KeepAspectRatio, self._Qt.SmoothTransformation
        )
        self._cam_label.setPixmap(scaled)

    def _on_lidar_front(self, payload: Any) -> None:
        try:
            self._lbl_lidar_front.setText("front: " + json.dumps(payload, ensure_ascii=False))
        except Exception:
            self._lbl_lidar_front.setText("front: (decode failed)")

    def _on_lidar_scan(self, payload: Any) -> None:
        if isinstance(payload, dict):
            self._lidar_last_scan = payload
        else:
            self._lidar_last_scan = None

    def _tick_lidar(self) -> None:
        payload = self._lidar_last_scan
        if not payload:
            return

        seq, ts_ms, pts = _extract_lidar_points(payload)
        n_total = len(pts)
        if n_total == 0:
            self._lbl_lidar.setText(f"scan: seq={seq} ts_ms={ts_ms} points=0")
            self._lidar_scatter.setData(pos=[])
            return

        max_points = int(self._spin_lidar_max_points.value())
        rmax = min(1.0, float(self._spin_lidar_range_m.value()))

        np = self._np
        angles = np.fromiter((p[0] for p in pts), dtype=np.float64, count=n_total)
        ranges = np.fromiter((p[1] for p in pts), dtype=np.float64, count=n_total)

        mask = ranges > 0.0
        if rmax > 0.0:
            mask &= ranges <= rmax
        angles = angles[mask]
        ranges = ranges[mask]

        n = int(angles.shape[0])
        if n == 0:
            self._lbl_lidar.setText(f"scan: seq={seq} ts_ms={ts_ms} points=0 (after filter)")
            self._lidar_scatter.setData(pos=[])
            return

        if n > max_points:
            idx = np.linspace(0, n - 1, num=max_points, dtype=np.int64)
            angles = angles[idx]
            ranges = ranges[idx]
            n = int(angles.shape[0])

        # Convert to XY where robot front is +Y (up) and angle_rad=0 points forward.
        # x is right, y is forward.
        x = ranges * np.sin(angles)
        y = ranges * np.cos(angles)
        if self._chk_lidar_flip_y.isChecked():
            y = -y
        pos = np.column_stack((x, y))
        self._lidar_scatter.setData(pos=pos)

        # Display area is fixed to 2m x 2m centered at origin.
        # rmax is only used as a distance filter (and capped to <= 1.0 above).

        self._lbl_lidar.setText(f"scan: seq={seq} ts_ms={ts_ms} points={n}/{n_total}")

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True

        try:
            try:
                self._pressed.clear()
                self._last_nonzero = False
                self._motor_timer.stop()
            except Exception:
                pass

            # Send multiple zero commands to avoid a final non-zero tick racing the close.
            self._send_stop(repeat=5)
        finally:
            try:
                self._client.close()
            except Exception:
                pass


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Zenoh remote UI for dmc_robo")
    p.add_argument("--robot-id", required=True, help="robot_id (e.g. rasp-zero-01)")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.toml for UI defaults. If omitted, loads ./config.toml when it exists.",
    )
    p.add_argument(
        "--no-config",
        action="store_true",
        help="Disable loading ./config.toml (even if it exists).",
    )
    p.add_argument(
        "--zenoh-config",
        type=Path,
        default=None,
        help="Path to a zenoh json5 config. If omitted, uses defaults.",
    )
    p.add_argument(
        "--mode",
        type=str,
        default="peer",
        help="Zenoh mode override when using --connect (default: peer).",
    )
    p.add_argument(
        "--connect",
        action="append",
        default=[],
        help='Connect endpoint override (repeatable), e.g. --connect "tcp/192.168.1.10:7447". '
        "If set, it is applied on top of defaults or --zenoh-config.",
    )
    p.add_argument(
        "--print-pub",
        action="store_true",
        help="Print published messages to terminal (rate-limited for motor).",
    )
    p.add_argument(
        "--print-pub-motor-all",
        action="store_true",
        help="Print ALL motor publishes to terminal (very verbose). Requires --print-pub.",
    )
    p.add_argument(
        "--print-motor-period",
        action="store_true",
        help="Print measured motor publish period to terminal (about 1 line/sec).",
    )
    args = p.parse_args(argv)
    if args.print_pub_motor_all:
        args.print_pub = True

    config_path: Optional[Path]
    if args.no_config:
        config_path = None
    elif args.config is not None:
        config_path = args.config
    else:
        candidate = Path("config.toml")
        config_path = candidate if candidate.exists() else None

    ui_config = _load_ui_config(config_path)

    open_session = _build_session_opener(
        config_path=args.zenoh_config, mode=args.mode, connect_endpoints=list(args.connect)
    )

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    bridge = _Bridge()
    client = ZenohClient(
        open_session=open_session, robot_id=args.robot_id, bridge=bridge, print_publish=args.print_pub
    )
    win = MainWindow(client=client, bridge=bridge, args=args, ui_config=ui_config)
    app.installEventFilter(win._key_filter)  # global motor key capture
    win.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
