# lerobot_dmc

LeRobot plugin packages for controlling `dmc_robo/<robot_id>` devices over Zenoh.

This repository contains two installable plugins:

- Robot: `lerobot_robot_dmc_robo` (Zenoh-based robot I/O for camera/IMU/LiDAR and motor commands)
- Teleoperator: `lerobot_teleoperator_dmc_robo` (keyboard teleop defaults aligned with `docs/remote_ui.md`)

## Quick Start

Install both plugins in editable mode:

```
pip install -e packages/lerobot_robot_dmc_robo
pip install -e packages/lerobot_teleoperator_dmc_robo
```

## Robot Smoke Test

```
python -m lerobot_robot_dmc_robo.smoke_test \
  --robot-id <ROBOT_ID> \
  --connect tcp/<ROUTER_IP>:7447
```

Expected logs:
- "zenoh session opened"
- "decoded image shape=(H,W,3)"

## Use With LeRobot CLI

```
lerobot-teleoperate --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447
lerobot-record --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447
```

## Notes

- Robot control and Zenoh topic details are documented in `docs/remote_ui.md` and `docs/zenoh_remote_pubsub.md`.
- The `dmc_ai_host` repository contains the original UI and reference tools; this repo mirrors the docs for offline use.
- LeRobot upstream references live in `../lerobot` (see `docs/source/integrate_hardware.mdx`).
