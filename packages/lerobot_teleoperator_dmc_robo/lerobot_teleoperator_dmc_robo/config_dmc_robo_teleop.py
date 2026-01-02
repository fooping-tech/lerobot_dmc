from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lerobot.teleoperators.config import TeleoperatorConfig


@dataclass
class MotorConfig:
    speed_step_mps: float = 0.30
    publish_hz: float = 10.0
    deadman_ms: int = 200


@dataclass
class LidarConfig:
    update_hz: float = 10.0
    max_points: int = 5000
    range_m: float = 1.0
    flip_y: bool = False


@dataclass
class ViewerConfig:
    enabled: bool = True
    robot_id: str | None = None
    zenoh_config_path: Path | None = None
    connect: list[str] = field(default_factory=list)
    connect_mode: str = ""


@dataclass
class SerialConfig:
    enabled: bool = False
    port: str | None = None
    baud: int = 115200
    raw_max: int = 2000
    max_mps: float = 0.5
    timeout_s: float = 0.5
    print_lines: bool = False
    print_values: bool = False


@TeleoperatorConfig.register_subclass("dmc_robo_teleop")
@dataclass
class DmcRoboTeleopConfig(TeleoperatorConfig):
    motor: MotorConfig = field(default_factory=MotorConfig)
    lidar: LidarConfig = field(default_factory=LidarConfig)
    viewer: ViewerConfig = field(default_factory=ViewerConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)
