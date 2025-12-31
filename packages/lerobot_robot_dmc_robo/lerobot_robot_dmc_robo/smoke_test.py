from __future__ import annotations

import argparse
import time
from pathlib import Path

from .config_dmc_robo import DmcRoboConfig
from .dmc_robo import DmcRobo


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DmcRobo smoke test")
    parser.add_argument("--robot-id", default="robo1")
    parser.add_argument("--connect", action="append", default=[], help="zenoh endpoint, e.g. tcp/192.168.0.2:7447")
    parser.add_argument("--zenoh-config", type=Path, default=None)
    parser.add_argument("--camera-height", type=int, default=480)
    parser.add_argument("--camera-width", type=int, default=640)
    parser.add_argument("--deadman-ms", type=int, default=300)
    parser.add_argument(
        "--imu-field-path",
        "--robot.imu_field_path",
        dest="imu_field_path",
        type=str,
        default=None,
    )
    parser.add_argument("--wait-lidar", action="store_true", help="wait for lidar scan before exiting")
    parser.add_argument("--timeout-s", type=float, default=10.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    config = DmcRoboConfig(
        robot_id=args.robot_id,
        zenoh_config_path=args.zenoh_config,
        connect=args.connect,
        camera_height=args.camera_height,
        camera_width=args.camera_width,
        deadman_ms=args.deadman_ms,
        imu_field_path=args.imu_field_path,
    )

    robot = DmcRobo(config)
    robot.connect(calibrate=False)
    print("zenoh session opened")

    try:
        deadline = time.monotonic() + args.timeout_s
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("timed out waiting for camera image")
            try:
                obs = robot.get_observation()
                break
            except RuntimeError:
                time.sleep(0.1)

        image = obs["camera"]
        imu = obs["imu.gyro"]
        lidar_points = obs.get("lidar.points", [])
        lidar_seq = obs.get("lidar.seq")
        lidar_ts = obs.get("lidar.ts_ms")
        motor_cmd_ts = obs.get("motor.cmd_ts_ms")
        motor_cmd_seq = obs.get("motor.cmd_seq")
        motor_pw_l = obs.get("motor.pw_l")
        motor_pw_r = obs.get("motor.pw_r")
        print(f"decoded image shape={image.shape} dtype={image.dtype}")
        print(f"imu gyro={imu}")
        print(f"lidar points={len(lidar_points)} seq={lidar_seq} ts_ms={lidar_ts}")
        print(
            "motor telemetry: "
            f"cmd_ts_ms={motor_cmd_ts} cmd_seq={motor_cmd_seq} pw_l={motor_pw_l} pw_r={motor_pw_r}"
        )

        if args.wait_lidar and len(lidar_points) == 0:
            deadline = time.monotonic() + args.timeout_s
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError("timed out waiting for lidar scan")
                obs = robot.get_observation()
                lidar_points = obs.get("lidar.points", [])
                if len(lidar_points) > 0:
                    lidar_seq = obs.get("lidar.seq")
                    lidar_ts = obs.get("lidar.ts_ms")
                    print(f"lidar points={len(lidar_points)} seq={lidar_seq} ts_ms={lidar_ts}")
                    break
                time.sleep(0.1)
    finally:
        try:
            robot.send_action({"v_l": 0.0, "v_r": 0.0})
        except Exception:
            pass
        robot.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
