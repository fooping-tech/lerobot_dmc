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

If your environment uses a Zenoh config file instead of direct endpoints, pass:

```
--robot.zenoh_config_path path/to/zenoh_remote.json5
```

## References

- `docs/remote_zenoh_tool.py` for Zenoh publish/subscribe examples.
- `docs/zenoh_remote_pubsub.md` for key names and payload structure.
