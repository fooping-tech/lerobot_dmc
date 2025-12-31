# lerobot_dmc

LeRobot plugin packages for controlling `dmc_robo/<robot_id>` devices over Zenoh.

This repository contains two installable plugins:

- Robot: `lerobot_robot_dmc_robo` (Zenoh-based robot I/O for camera/IMU/LiDAR and motor commands)
- Teleoperator: `lerobot_teleoperator_dmc_robo` (keyboard teleop defaults aligned with `docs/remote_ui.md`)

## Quick Start

Python 3.10+ is required.

Create a local virtual environment (optional but recommended):  

```
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

Install both plugins in editable mode:

```
pip install -e packages/lerobot_robot_dmc_robo
pip install -e packages/lerobot_teleoperator_dmc_robo
```

## Robot Smoke Test

```
python -m lerobot_robot_dmc_robo.smoke_test \
  --robot-id <ROBOT_ID> \
  --connect tcp/<ROUTER_IP>:7447 \
  --imu-field-path .
```

To wait for a LiDAR scan as well:

```
--wait-lidar
```

Expected logs:
- "zenoh session opened"
- "decoded image shape=(H,W,3)"

## Use With LeRobot CLI

```
lerobot-teleoperate --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447 --robot.imu_field_path .
lerobot-record --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447 --robot.imu_field_path .
```

To launch teleop with the GUI viewer (camera + LiDAR + IMU charts): 

```
lerobot-teleoperate --teleop.type=dmc_robo_teleop --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447 --robot.imu_field_path .
```

This viewer reuses `packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/remote_zenoh_ui.py` and requires `PySide6` and `pyqtgraph`.
Disable it if needed:

```
--teleop.viewer.enabled false
```

Teleop keys (GUI):
- `w`: forward, `s`/`x`: backward
- `a`: left rotate, `d`: right rotate
- `q`/`e`/`z`/`c`: diagonals (forward/back + left/right)
- `r`/`f` + `u`/`j`: per-wheel control (lower priority than WASD)
Full details: `docs/remote_ui.md`.

Full example with plugin discovery and Zenoh config:

```
lerobot-teleoperate \
  --teleop.discover_packages_path=lerobot_teleoperator_dmc_robo \
  --robot.discover_packages_path=lerobot_robot_dmc_robo \
  --teleop.type=dmc_robo_teleop \
  --robot.type=dmc_robo \
  --robot.robot_id rasp-zero-01 \
  --robot.zenoh_config_path zenoh_remote.json5 \
  --robot.imu_field_path . \
  --fps 10
```

Recording example (note the dataset FPS flag):

```
lerobot-record \
  --teleop.discover_packages_path=lerobot_teleoperator_dmc_robo \
  --robot.discover_packages_path=lerobot_robot_dmc_robo \
  --teleop.type=dmc_robo_teleop \
  --robot.type=dmc_robo \
  --robot.robot_id rasp-zero-01 \
  --robot.zenoh_config_path zenoh_remote.json5 \
  --robot.imu_field_path . \
  --dataset.repo_id <DATASET_NAME> \
  --dataset.single_task <TASK_NAME> \
  --dataset.fps 10
```

If IMU payload uses root-level `gx/gy/gz`, pass:

```
--robot.imu_field_path .
```

If the camera stream is slow to start, increase the initial wait:

```
--robot.camera_wait_timeout_s 10.0
```

If you want to keep teleop running even when camera frames are missing:

```
--robot.camera_allow_missing true
```

## Notes

- Robot control and Zenoh topic details are documented in `docs/remote_ui.md` and `docs/zenoh_remote_pubsub.md`.
- The `dmc_ai_host` repository contains the original UI and reference tools; this repo mirrors the docs for offline use.
- LeRobot upstream references live in `../lerobot` (see `docs/source/integrate_hardware.mdx`).
