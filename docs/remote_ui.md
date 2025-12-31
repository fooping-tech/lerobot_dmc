# Zenoh Remote UI（操作UIアプリ）

このリポジトリの `packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/remote_zenoh_ui.py` は、Zenoh pub/sub 経由でロボットを操作し、IMU（ジャイロ）とカメラを表示し、OLED表示文字列を送るデスクトップUIです。

前提となる Zenoh キーやネットワーク構成の説明は `docs/zenoh_remote_pubsub.md` を参照してください。

## セットアップ

例（venv）:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -U pip
    python -m pip install -r requirements.txt

`PySide6` のインストールで `*.tmpl.py` が `SyntaxError` になる場合（pip の bytecode compile が原因のケース）は、次で回避できます:

    python -m pip install --no-compile -r requirements.txt

## 起動

routerへ接続する例（推奨）:

    python packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/remote_zenoh_ui.py --robot-id <ROBOT_ID> --connect "tcp/<ROUTER_IP>:7447"

json5設定ファイルを使う例:

    python packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/remote_zenoh_ui.py --robot-id <ROBOT_ID> --zenoh-config ./zenoh_remote.json5

## config.toml（UIのデフォルト設定）

`remote_zenoh_ui.py` は、カレントディレクトリに `config.toml` があれば自動で読み込み、UIの初期値に反映します。

- 例: `config.toml.example` を `config.toml` にコピーして編集
- 明示的に指定: `--config /path/to/config.toml`
- 自動読み込みを無効化: `--no-config`

publish しているメッセージをターミナルに出したい場合:

    python packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/remote_zenoh_ui.py --robot-id <ROBOT_ID> --connect "tcp/<ROUTER_IP>:7447" --print-pub

モータ指令を「全て」確認したい場合（止まる瞬間の揺れ等の解析用、かなり大量に出ます）:

    python packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/remote_zenoh_ui.py --robot-id <ROBOT_ID> --connect "tcp/<ROUTER_IP>:7447" --print-pub-motor-all

モータの publish 周期（実測）を確認したい場合:

    python packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/remote_zenoh_ui.py --robot-id <ROBOT_ID> --connect "tcp/<ROUTER_IP>:7447" --print-motor-period

## 操作（キーボード）

WASD 系の合成操作が優先です（キー押下中だけ一定周期で publish し、離すと停止指令を送ります）。

- `w`: 前進
- `s` / `x`: 後進
- `a`: 左回転(0.3倍)
- `d`: 右回転(0.3倍)
- `q`: `w` + `a` 相当（左前、左タイヤは0.5倍）
- `e`: `w` + `d` 相当（右前、右タイヤは0.5倍）
- `z`: `s` + `a` 相当（左後、左タイヤは0.5倍）
- `c`: `s` + `d` 相当（右後、右タイヤは0.5倍）

左右タイヤの独立操作も使えます（WASD操作より優先度は低いです）。

- 左タイヤ: `r` 前進 / `f` 後進
- 右タイヤ: `u` 前進 / `j` 後進

注意:

- 入力欄（数値欄やテキスト欄）にフォーカスがあると、キー入力で値が変わることがあります。`Esc` を押すとフォーカスを外してモータ操作に戻せます。
- テキスト入力欄（OLEDやIMU rawなど）にフォーカスがある間は、誤操作防止のためモータキーを拾いません。
- `STOP` ボタンでもゼロ指令を送れます。
- `duration` 指定で一定時間だけ動かしたい場合は `docs/remote_zenoh_tool.py motor --duration-s ...` を使ってください（UIは押している間だけ動かす設計です）。

## IMU（ジャイロ）チャート

`imu/state` の JSON スキーマは環境依存の可能性があるため、UIの `field path` でジャイロ3軸（x,y,z）が入っているフィールドを指定できます。

例:

- `gyro`
- `angular_velocity`

raw JSON を見て、`gyro.x` のように `.` 区切りで辿れるパスを指定してください（配列は `0` / `1` / `2` の添字も可）。

## カメラ表示

- `camera/image/jpeg` を受信すると最新フレームを画面に表示します。
- `camera/meta` が届く場合、meta JSON を表示します。

## LiDAR（点群/スキャン）表示

- `lidar/scan` を受信すると 2D（俯瞰）散布図として点群を表示します（極座標: angle/range → XY、表示は自機のフロントが +y になるように 90°回転）。
- グラフはできるだけ正方形に近い見た目になるようにし、2m x 2m（x/y がそれぞれ -1.0〜+1.0m）を表示します。
- 中心(0,0)とフロント方向（+y方向）が分かるように、中心アイコンとフロント矢印を表示します。
- 点数が多い場合は `max points` で間引いて描画します。
- 表示範囲は 2m x 2m（x/y がそれぞれ -1.0〜+1.0m）に固定です。`range max (m)` は近距離だけに絞るためのフィルタで、最大 1.0m です。
- もし点群が前後反転して見える場合は `flip Y (front/back)` を切り替えてください（センサ/座標系の定義差を吸収します）。
- `lidar/front` が届く場合はサマリJSONを表示します。

## OLED

テキストボックスに入力して `Send` を押すと `oled/cmd` に送信します。

## 緊急停止（別ターミナル）

UIが落ちた場合などは、付属の最小ツールで stop を投げてください。

    python docs/remote_zenoh_tool.py --robot-id <ROBOT_ID> --connect "tcp/<ROUTER_IP>:7447" stop
