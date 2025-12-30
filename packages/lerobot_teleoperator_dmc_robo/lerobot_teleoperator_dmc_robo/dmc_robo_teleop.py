from __future__ import annotations

import os
import select
import sys
import termios
import time
import tty
from functools import cached_property
from typing import Any

from lerobot.teleoperators.teleoperator import Teleoperator
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .config_dmc_robo_teleop import DmcRoboTeleopConfig


class DmcRoboTeleop(Teleoperator):
    config_class = DmcRoboTeleopConfig
    name = "dmc_robo_teleop"

    def __init__(self, config: DmcRoboTeleopConfig):
        super().__init__(config)
        self.config = config
        self._connected = False
        self._action = {"v_l": 0.0, "v_r": 0.0}
        self._stdin_fd: int | None = None
        self._stdin_termios: list[Any] | None = None
        self._last_input_ts = 0.0
        self._key_last_seen: dict[str, float] = {}

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
        if not sys.stdin.isatty():
            raise RuntimeError("stdin is not a TTY; keyboard teleop requires a terminal")
        self._stdin_fd = sys.stdin.fileno()
        self._stdin_termios = termios.tcgetattr(self._stdin_fd)
        tty.setcbreak(self._stdin_fd)
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

    def _read_keys(self) -> list[str]:
        if self._stdin_fd is None:
            return []
        ready, _, _ = select.select([self._stdin_fd], [], [], 0)
        if not ready:
            return []
        data = os.read(self._stdin_fd, 32)
        keys: list[str] = []
        i = 0
        while i < len(data):
            b = data[i]
            if b == 0x1B and i + 2 < len(data) and data[i + 1] == 0x5B:
                code = data[i + 2]
                if code == 0x41:
                    keys.append("UP")
                elif code == 0x42:
                    keys.append("DOWN")
                elif code == 0x43:
                    keys.append("RIGHT")
                elif code == 0x44:
                    keys.append("LEFT")
                i += 3
                continue
            if 0x20 <= b < 0x7F:
                keys.append(chr(b))
            i += 1
        return keys

    def _pressed_keys(self) -> set[str]:
        now = time.monotonic()
        hz = float(self.config.motor.publish_hz)
        hold_timeout = 0.2 if hz <= 0 else max(0.2, 1.5 / hz)
        pressed = {k for k, t in self._key_last_seen.items() if (now - t) <= hold_timeout}
        if not pressed:
            self._key_last_seen.clear()
        return pressed

    def get_action(self) -> dict[str, Any]:
        if not self._connected:
            raise DeviceNotConnectedError()
        step = float(self.config.motor.speed_step_mps)
        keys = self._read_keys()
        if keys:
            now = time.monotonic()
            self._last_input_ts = now
            for key in keys:
                self._key_last_seen[key] = now

        pressed = self._pressed_keys()

        if "UP" in pressed or "DOWN" in pressed or "LEFT" in pressed or "RIGHT" in pressed:
            up = "UP" in pressed
            down = "DOWN" in pressed
            left = "LEFT" in pressed
            right = "RIGHT" in pressed

            if up and right and not left:
                v_l, v_r = step, step * 0.5
            elif up and left and not right:
                v_l, v_r = step * 0.5, step
            elif down and right and not left:
                v_l, v_r = -step, -step * 0.5
            elif down and left and not right:
                v_l, v_r = -step * 0.5, -step
            elif up:
                v_l, v_r = step, step
            elif down:
                v_l, v_r = -step, -step
            elif left:
                v_l, v_r = -step * 0.3, step * 0.3
            elif right:
                v_l, v_r = step * 0.3, -step * 0.3
            else:
                v_l, v_r = 0.0, 0.0
        else:
            v_l = 0.0
            v_r = 0.0
            if "r" in pressed or "R" in pressed:
                v_l += step
            if "f" in pressed or "F" in pressed:
                v_l -= step
            if "u" in pressed or "U" in pressed:
                v_r += step
            if "j" in pressed or "J" in pressed:
                v_r -= step

        if " " in pressed or "x" in pressed or "X" in pressed or "0" in pressed:
            v_l, v_r = 0.0, 0.0

        deadman_s = float(self.config.motor.deadman_ms) / 1000.0
        if deadman_s > 0 and (time.monotonic() - self._last_input_ts) > deadman_s:
            v_l, v_r = 0.0, 0.0

        self._action["v_l"] = float(v_l)
        self._action["v_r"] = float(v_r)
        return dict(self._action)

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        if not self._connected:
            raise DeviceNotConnectedError()
        return None

    def disconnect(self) -> None:
        if self._stdin_fd is not None and self._stdin_termios is not None:
            termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, self._stdin_termios)
            self._stdin_fd = None
            self._stdin_termios = None
        self._connected = False
