from __future__ import annotations

import json
import sys
import time
from functools import cached_property
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from lerobot.teleoperators.teleoperator import Teleoperator
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .config_dmc_robo_teleop import DmcRoboTeleopConfig


def _get_cli_value(flag: str) -> str | None:
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1]
        if arg == flag and i + 1 < len(args):
            return args[i + 1]
    return None


def _get_cli_list(flag: str) -> list[str]:
    args = sys.argv[1:]
    raw_values: list[str] = []
    for i, arg in enumerate(args):
        if arg.startswith(flag + "="):
            raw_values.append(arg.split("=", 1)[1])
        elif arg == flag and i + 1 < len(args):
            raw_values.append(args[i + 1])

    out: list[str] = []
    for raw in raw_values:
        raw = raw.strip()
        if raw.startswith("["):
            try:
                data = json.loads(raw)
            except Exception:
                data = raw
            if isinstance(data, list):
                out.extend(str(v) for v in data)
            else:
                out.append(str(data))
        else:
            out.append(raw)
    return out


def _load_remote_ui_module() -> Any:
    try:
        from . import remote_zenoh_ui as module
    except Exception as e:
        raise RuntimeError("failed to import bundled remote_zenoh_ui module") from e
    return module


class DmcRoboTeleop(Teleoperator):
    config_class = DmcRoboTeleopConfig
    name = "dmc_robo_teleop"

    def __init__(self, config: DmcRoboTeleopConfig):
        super().__init__(config)
        self.config = config
        self._connected = False
        self._action = {"v_l": 0.0, "v_r": 0.0}
        self._app = None
        self._viewer_window = None
        self._viewer_client = None
        self._viewer_bridge = None
        self._viewer_module = None
        self._closing = False
        self._last_input_ts = 0.0

    @cached_property
    def action_features(self) -> dict:
        return {"v_l": float, "v_r": float}

    @cached_property
    def feedback_features(self) -> dict:
        return {}

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self, calibrate: bool = True) -> None:
        if self._connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        if not self.config.viewer.enabled:
            self._connected = True
            self.configure()
            return

        try:
            from PySide6.QtWidgets import QApplication
        except Exception as e:  # pragma: no cover - optional GUI dependency
            raise RuntimeError("PySide6 is required for GUI teleop. Install it first.") from e

        module = _load_remote_ui_module()
        self._viewer_module = module

        robot_id = self.config.viewer.robot_id
        if not robot_id:
            robot_id = _get_cli_value("--robot.robot_id") or _get_cli_value("--robot.id")
        if not robot_id:
            raise RuntimeError("teleop.viewer.robot_id is required to launch the viewer")

        zenoh_config_path = self.config.viewer.zenoh_config_path
        if zenoh_config_path is None:
            zpath = _get_cli_value("--robot.zenoh_config_path")
            if zpath:
                zenoh_config_path = Path(zpath)

        connect_endpoints = list(self.config.viewer.connect)
        if not connect_endpoints:
            connect_endpoints = _get_cli_list("--robot.connect")

        connect_mode = self.config.viewer.connect_mode or _get_cli_value("--robot.connect_mode") or "peer"

        ui_config = module.UIConfig(
            motor_speed_step_mps=float(self.config.motor.speed_step_mps),
            motor_publish_hz=float(self.config.motor.publish_hz),
            motor_deadman_ms=int(self.config.motor.deadman_ms),
            lidar_update_hz=float(self.config.lidar.update_hz),
            lidar_max_points=int(self.config.lidar.max_points),
            lidar_range_m=float(self.config.lidar.range_m),
            lidar_flip_y=bool(self.config.lidar.flip_y),
        )

        open_session = module._build_session_opener(
            config_path=zenoh_config_path, mode=connect_mode, connect_endpoints=list(connect_endpoints)
        )

        args = SimpleNamespace(
            robot_id=robot_id,
            print_pub=False,
            print_pub_motor_all=False,
            print_motor_period=False,
        )

        app = QApplication.instance() or QApplication(sys.argv[:1])
        bridge = module._Bridge()
        client = module.ZenohClient(
            open_session=open_session, robot_id=robot_id, bridge=bridge, print_publish=False
        )
        win = module.MainWindow(client=client, bridge=bridge, args=args, ui_config=ui_config)
        app.installEventFilter(win._key_filter)
        try:
            win._motor_timer.stop()
        except Exception:
            pass
        win.show()

        self._app = app
        self._viewer_window = win
        self._viewer_client = client
        self._viewer_bridge = bridge
        self._last_input_ts = time.monotonic()
        self._connected = True
        self.configure()

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        return None

    def configure(self) -> None:
        return None

    def get_action(self) -> dict[str, Any]:
        if not self._connected:
            raise DeviceNotConnectedError()
        if self._viewer_window is None:
            return dict(self._action)

        if self._app is not None:
            try:
                self._app.processEvents()
            except Exception:
                self._closing = True

        if self._closing or getattr(self._viewer_window, "_closing", False):
            self._action["v_l"] = 0.0
            self._action["v_r"] = 0.0
            return dict(self._action)

        pressed = set(getattr(self._viewer_window, "_pressed", set()))
        if pressed:
            self._last_input_ts = time.monotonic()

        try:
            v_l, v_r = self._viewer_window._desired_motor()
        except Exception:
            v_l, v_r = 0.0, 0.0

        deadman_s = float(self.config.motor.deadman_ms) / 1000.0
        if deadman_s > 0 and (time.monotonic() - self._last_input_ts) > deadman_s:
            v_l, v_r = 0.0, 0.0

        self._action["v_l"] = float(v_l)
        self._action["v_r"] = float(v_r)
        if hasattr(self._viewer_window, "_lbl_motor"):
            try:
                self._viewer_window._lbl_motor.setText(f"v_l={v_l:+.3f} v_r={v_r:+.3f}")
            except Exception:
                pass
        return dict(self._action)

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        if not self._connected:
            raise DeviceNotConnectedError()
        return None

    def disconnect(self) -> None:
        if self._viewer_window is not None:
            try:
                self._viewer_window.close()
            except Exception:
                pass
            self._viewer_window = None
        if self._viewer_client is not None:
            try:
                self._viewer_client.close()
            except Exception:
                pass
            self._viewer_client = None
        self._connected = False
