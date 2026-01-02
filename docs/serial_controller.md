# Serial Controller (Integrated in GUI)

USBシリアルの `L:<left>,R:<right>` は GUI テレオペ（`dmc_robo_teleop`）に統合されています。
詳細仕様は `serial_controller_software_spec.md` を参照してください。

前提となるコントローラ実装（ファームウェア）:
- https://github.com/fooping-tech/DifferentialDriveController

## セットアップ

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -U pip
    python -m pip install eclipse-zenoh pyserial tomli

## 起動

シリアル入力は `lerobot-teleoperate` から利用します。

    lerobot-teleoperate --teleop.type=dmc_robo_teleop --robot.type=dmc_robo --robot.robot_id <ROBOT_ID> --robot.connect "tcp/<ROUTER_IP>:7447"

起動直後はコントローラがキャリブレーション中で `L:` 行が流れない場合があります。完了すると `L:` 行が流れ始めます。

## 設定（config.toml）

`config.toml` は `lerobot-teleoperate` 起動時に読み込まれます。

`[robot]` の主なキー:

- `robot_id`: robot_id（`dmc_robo/<robot_id>` の `<robot_id>` 部分）

`[controller]` の主なキー:

- `enabled`: GUIテレオペでシリアル入力を有効化したい場合に `true`
- `serial`: シリアルデバイスパス（必須）
- `baud`: ボーレート（USB CDC の場合は実質無視されます）
- `raw_max`: raw 最大値（L/R ボタン倍増込み）
- `max_mps`: raw_max 到達時の速度（mps）
- `publish_hz`: UI の publish 周期（Hz）
- `deadman_ms`: deadman 上書き（未指定なら `[motor].deadman_ms` を使用）
- `timeout_s`: GUIテレオペでシリアル入力が有効とみなす猶予（秒）

## デバッグ

`config.toml` の `[controller]` に以下を追加してください。

- `print_lines = true`: 受信 raw をログに出力
- `print_values = true`: 変換後の `v_l/v_r` をログに出力

## 停止

UI 終了時は `v_l=0` / `v_r=0` を送信します。UIが落ちた場合などは最小ツールで stop を投げてください。

    python docs/remote_zenoh_tool.py --robot-id <ROBOT_ID> --connect "tcp/<ROUTER_IP>:7447" stop
