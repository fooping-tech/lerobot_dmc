# lerobot_dmc

Zenoh 経由で `dmc_robo/<robot_id>` デバイスを制御する LeRobot プラグインパッケージ。

このリポジトリには、インストール可能な 2 つのプラグインが含まれます。

- Robot: `lerobot_robot_dmc_robo`（カメラ/IMU/LiDAR の I/O とモーター指令の Zenoh ベース実装）
- Teleoperator: `lerobot_teleoperator_dmc_robo`（`docs/remote_ui.md` に合わせたキーボードテレオペのデフォルト）

## クイックスタート

Python 3.10+ が必要です。

ローカル仮想環境を作成（任意ですが推奨）:

```
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

両プラグインを editable モードでインストール:

```
pip install -e packages/lerobot_robot_dmc_robo
pip install -e packages/lerobot_teleoperator_dmc_robo
```

## Hugging Face ログイン（データセットのアップロード用）

Hugging Face Hub にデータセットをアップロードする場合（例: `lerobot-record --dataset.repo_id ...`）、一度ログインしてください:

```
hf auth login
```

手順:
- https://huggingface.co/settings/tokens でアクセストークンを作成（権限: `write`）。
- プロンプトが出たらトークンを貼り付け（入力は非表示）。
- 「Add token as git credential?」と聞かれたら `Y` を選び、OS のキーチェーンに保存。

ログイン後、トークンは `~/.cache/huggingface/` に保存され、以後の Hub 操作で再利用されます。

## ロボットのスモークテスト

```
python -m lerobot_robot_dmc_robo.smoke_test \
  --robot-id <ROBOT_ID> \
  --connect tcp/<ROUTER_IP>:7447 \
  --imu-field-path .
```

LiDAR スキャンも待つ場合:

```
--wait-lidar
```

期待されるログ:
- "zenoh session opened"
- "decoded image shape=(H,W,3)"

## LeRobot CLI で使用

```
lerobot-teleoperate --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447 --robot.imu_field_path .
lerobot-record --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447 --robot.imu_field_path .
```

GUI ビューア（カメラ + LiDAR + IMU チャート）付きでテレオペ起動:

```
lerobot-teleoperate --teleop.type=dmc_robo_teleop --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect tcp/<ROUTER_IP>:7447 --robot.imu_field_path .
```

このビューアは `packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/remote_zenoh_ui.py` を再利用しており、`PySide6` と `pyqtgraph` が必要です。
無効化したい場合:

```
--teleop.viewer.enabled false
```

テレオペキー（GUI）:
- `w`: 前進、`s`/`x`: 後退
- `a`: 左旋回、`d`: 右旋回
- `q`/`e`/`z`/`c`: 斜め（前/後 + 左/右）
- `r`/`f` + `u`/`j`: 各輪操作（WASD より優先度は低い）
詳細: `docs/remote_ui.md`。

プラグイン発見と Zenoh 設定を含む完全な例:

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

記録例（dataset FPS フラグに注意）:

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

IMU ペイロードが root レベルの `gx/gy/gz`（ジャイロ）または `ax/ay/az`（加速度）を使う場合:

```
--robot.imu_field_path .
```

ジャイロと加速度が同じ階層（フラット）に並んでいる場合は、`--robot.imu_field_path .` だけで両方に適用されます（`imu_accel_field_path` は省略可）。

ジャイロと加速度を別キーで同時に記録したい場合（例: `gyro` と `accel` を別に持つpayload）:

```
--robot.imu_field_path gyro
--robot.imu_accel_field_path accel
```

カメラストリームの開始が遅い場合は、初期待機を延ばします:

```
--robot.camera_wait_timeout_s 10.0
```

カメラフレームが欠けてもテレオペを継続したい場合:

```
--robot.camera_allow_missing true
```

## 注記

- ロボット制御と Zenoh トピックの詳細は `docs/remote_ui.md` と `docs/zenoh_remote_pubsub.md` を参照。
- `dmc_ai_host` リポジトリに元の UI と参照ツールがあり、本リポジトリはオフライン用にドキュメントをミラーしています。
- LeRobot 上流の参照は `../lerobot` にあります（`docs/source/integrate_hardware.mdx` を参照）。
