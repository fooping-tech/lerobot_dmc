# Using Your Own LeRobot Devices (Summary + Detailed Notes)

This doc is a concise, practical summary of the HuggingFace LeRobot guide
"Using Your Own LeRobot Devices". It is intentionally short and focused so
we can work offline while keeping the core rules and example layout.


## Quick Summary (4 Core Conventions)

1) Installable package + prefix
   - Your plugin must be a standard, installable Python package.
   - The package name must start with a prefix:
     - `lerobot_robot_` for robots
     - `lerobot_camera_` for cameras
     - `lerobot_teleoperator_` for teleoperation devices

2) `SomethingConfig` / `Something` naming
   - The device class name must match the config class name without `Config`.
   - Example: `MyAwesomeTeleopConfig` -> `MyAwesomeTeleop`

3) Predictable structure
   - The device class must be in a predictable module relative to its config.
   - Acceptable locations:
     - Same module as the config
     - A submodule named after the device (e.g., `my_awesome_teleop.py`)

4) Export in `__init__.py`
   - The package's `__init__.py` must import and expose both the config and
     the device classes.


## Detailed Guide (Practical Template)

Below is a minimal, working example for a teleoperator plugin.
For a robot plugin, replace `teleoperator` with `robot`.


### Directory Structure

```
lerobot_teleoperator_my_awesome_teleop/
├── pyproject.toml  # or setup.py
└── lerobot_teleoperator_my_awesome_teleop/
    ├── __init__.py
    ├── config_my_awesome_teleop.py
    └── my_awesome_teleop.py
```


### config_my_awesome_teleop.py

```python
from dataclasses import dataclass

from lerobot.teleoperators.config import TeleoperatorConfig

@TeleoperatorConfig.register_subclass("my_awesome_teleop")
@dataclass
class MyAwesomeTeleopConfig(TeleoperatorConfig):
    # Your configuration fields go here
    port: str = "192.168.1.1"
```


### my_awesome_teleop.py

```python
from lerobot.teleoperators.teleoperator import Teleoperator

from .config_my_awesome_teleop import MyAwesomeTeleopConfig

class MyAwesomeTeleop(Teleoperator):
    config_class = MyAwesomeTeleopConfig
    name = "my_awesome_teleop"

    def __init__(self, config: MyAwesomeTeleopConfig):
        super().__init__(config)
        self.config = config
        # Device logic goes here
```


### __init__.py

```python
from .config_my_awesome_teleop import MyAwesomeTeleopConfig
from .my_awesome_teleop import MyAwesomeTeleop
```


### Install and Use

```
# Local editable install
cd lerobot_teleoperator_my_awesome_teleop
pip install -e .

# Use in CLI
lerobot-teleoperate --teleop.type=my_awesome_teleop
```


## Notes for This Repo (dmc_ai_host)

We are implementing a robot plugin, so we will follow the same rules but
use the `lerobot_robot_` prefix and `RobotConfig` / `Robot` base classes.

Planned local structure (see `PLANS.md` for the full ExecPlan):

```
packages/lerobot_robot_dmc_robo/
├── pyproject.toml
└── lerobot_robot_dmc_robo/
    ├── __init__.py
    ├── config_dmc_robo.py
    ├── dmc_robo.py
    └── smoke_test.py
```

Key requirement: `__init__.py` must expose `DmcRoboConfig` and `DmcRobo`
so the LeRobot CLI can discover the plugin after `pip install -e ...`.

