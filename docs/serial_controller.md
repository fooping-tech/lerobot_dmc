# Serial Controller -> Motor Command Bridge

USBシリアルの `L:<left>,R:<right>` を Zenoh の `motor/cmd` に変換して publish するブリッジです。

## セットアップ

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -U pip
    python -m pip install eclipse-zenoh pyserial tomli

## 起動

シリアルデバイスを直接指定する例（リポジトリルートで実行）:

    python serial_motor_bridge.py \
      --robot-id <ROBOT_ID> \
      --serial /dev/tty.usbmodemXXXX \
      --connect "tcp/<ROUTER_IP>:7447"

起動直後はコントローラがキャリブレーション中で `L:` 行が流れない場合があります。完了すると `L:` 行が流れ始めます。

`config.toml` を使う例（`[controller]` を設定）:

    python serial_motor_bridge.py \
      --robot-id <ROBOT_ID> \
      --connect "tcp/<ROUTER_IP>:7447"

## 設定（config.toml）

`serial_motor_bridge.py` は、カレントディレクトリに `config.toml` があれば自動で読み込みます。

- 明示的に指定: `--config /path/to/config.toml`
- 自動読み込みを無効化: `--no-config`

`[robot]` の主なキー:

- `robot_id`: robot_id（`dmc_robo/<robot_id>` の `<robot_id>` 部分）

`[controller]` の主なキー:

- `serial`: シリアルデバイスパス（必須）
- `baud`: ボーレート（USB CDC の場合は実質無視されます）
- `raw_max`: raw 最大値（L/R ボタン倍増込み）
- `max_mps`: raw_max 到達時の速度（mps）
- `publish_hz`: publish 周期（Hz）。間隔内の `L/R` を平均して送信します
- `deadman_ms`: deadman 上書き（未指定なら `[motor].deadman_ms` を使用）

## デバッグ

- 受信値の表示: `--print-lines`
- 変換前後の表示: `--print-values`
- publish payload の表示: `--print-pub`

## 停止

ブリッジ終了時は `v_l=0` / `v_r=0` を送信します。UIが落ちた場合などは最小ツールで stop を投げてください。

    python docs/remote_zenoh_tool.py --robot-id <ROBOT_ID> --connect "tcp/<ROUTER_IP>:7447" stop
