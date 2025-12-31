# LeRobot DmcRobo Plugin Usage

This document describes how to install and use the `dmc_robo` LeRobot plugin.

## Install

From this repository root:

```
pip install -e packages/lerobot_robot_dmc_robo
```

## Smoke Test

```
python -m lerobot_robot_dmc_robo.smoke_test \
  --robot-id <ROBOT_ID> \
  --connect tcp/<ROUTER_IP>:7447
```

Expected output:
- "zenoh session opened"
- "decoded image shape=(H,W,3)"
- stop command published on exit

## Use With LeRobot CLI

```
lerobot-teleoperate --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447
lerobot-record --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447
```

Teleop with GUI viewer (camera + LiDAR + IMU charts):

```
lerobot-teleoperate --teleop.type=dmc_robo_teleop --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447
```

Recording example (dataset fields are required):

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

If your environment uses a Zenoh config file instead of direct endpoints, pass:

```
--robot.zenoh_config_path path/to/zenoh_remote.json5
```

If IMU payload uses root-level `gx/gy/gz`, pass:

```
--robot.imu_field_path .
```

If you want to keep teleop running even when camera frames are missing:

```
--robot.camera_allow_missing true
```

## References

- `docs/remote_zenoh_tool.py` for Zenoh publish/subscribe examples.
- `docs/zenoh_remote_pubsub.md` for key names and payload structure.
