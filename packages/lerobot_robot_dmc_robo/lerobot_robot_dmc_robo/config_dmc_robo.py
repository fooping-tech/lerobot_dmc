from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lerobot.robots import RobotConfig


@RobotConfig.register_subclass("dmc_robo")
@dataclass
class DmcRoboConfig(RobotConfig):
    robot_id: str = "rasp-zero-01"
    zenoh_config_path: Path | None = None
    connect: list[str] = field(default_factory=list)
    connect_mode: str = ""  # optional override for zenoh config 'mode'

    deadman_ms: int = 200
    camera_height: int = 480
    camera_width: int = 640
    camera_wait_timeout_s: float = 5.0
    camera_allow_missing: bool = False
    motor_telemetry_enabled: bool = True
    imu_field_path: str | None = None
    imu_accel_field_path: str | None = None

    max_speed_mps: float | None = 1.0

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = self.robot_id
        super().__post_init__()
