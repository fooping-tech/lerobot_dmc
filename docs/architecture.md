# ソフトウェア構造（Mermaid）

```mermaid
flowchart LR
  %% --- Users / Entry points ---
  subgraph User["User"]
    CLI["LeRobot CLI\nlerobot-teleoperate / lerobot-record"]
    GUI["Standalone GUI\nremote_zenoh_ui.py"]
  end

  %% --- Config ---
  CFG["config.toml\nrobot_id / controller / motor"]

  %% --- Teleoperator ---
  subgraph TeleopPkg["Teleoperator Plugin\nlerobot_teleoperator_dmc_robo"]
    Teleop[DmcRoboTeleop]
    UI["remote_zenoh_ui.py\nMainWindow"]
    Serial["SerialReader\n(thread)"]
    SerialState[SerialState]
  end

  %% --- Robot plugin ---
  subgraph RobotPkg["Robot Plugin\nlerobot_robot_dmc_robo"]
    Robot[DmcRobo]
  end

  %% --- External devices / networks ---
  subgraph Controller["Serial Controller"]
    FW["DifferentialDriveController\n(USB CDC)"]
  end

  subgraph Zenoh["Zenoh"]
    ZRouter["Zenoh Router (optional)"]
    ZSession["Zenoh Session"]
  end

  subgraph Robo["dmc_robo/ROBOT_ID (topics)"]
    Motor["motor/cmd"]
    Cam["camera/image/jpeg"]
    IMU["imu/state"]
    LiDARScan["lidar/scan"]
    LiDARFront["lidar/front"]
  end

  %% --- Connections ---
  CLI --> Teleop
  CLI --> Robot
  CFG --> Teleop
  CFG --> UI
  CFG --> Robot

  Teleop -->|processEvents / input resolve| UI
  UI -->|serial priority arbitration| SerialState
  FW -->|L:left R:right| Serial
  Serial --> SerialState

  %% Standalone GUI publishes directly
  GUI --> UI
  UI -->|open| ZSession
  Robot -->|open| ZSession
  ZSession --> ZRouter
  ZSession --> Motor
  ZSession --> Cam
  ZSession --> IMU
  ZSession --> LiDARScan
  ZSession --> LiDARFront

  %% Motor command path
  UI -->|publish motor/cmd| Motor
  Teleop -->|action v_l v_r| Robot
  Robot -->|publish motor/cmd| Motor

  %% Observation path (Robot plugin)
  Cam -->|publish| Robot
  IMU -->|publish| Robot
  LiDARScan -->|publish| Robot
  LiDARFront -->|publish| Robot
```

ポイント:
- シリアル入力は `remote_zenoh_ui.py` 内で受け取り、仲裁は「シリアル優先」です。
- GUI単体起動時は UI が `motor/cmd` を直接 publish します。
- `lerobot-teleoperate` 経由では Teleop が UI から入力を取得し、Robot プラグイン経由で `motor/cmd` を publish します。
