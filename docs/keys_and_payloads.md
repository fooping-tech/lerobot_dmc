# Zenoh Keys and Payloads

このドキュメントは `docs/dmc_ai_mobility_software_design.md` と現在の実装（`src/dmc_ai_mobility/zenoh/keys.py` / `src/dmc_ai_mobility/core/types.py`）に基づき、Zenoh のキーと payload（JSON/bytes）を整理したものです。

## 命名規則

キー命名規則:

    dmc_robo/<robot_id>/<component>/<direction>

`robot_id` は `config.toml` の `robot_id`（例: `rasp-zero-01`）です。

## 一覧

### motor

- Subscribe: `dmc_robo/<robot_id>/motor/cmd`
- Publish: `dmc_robo/<robot_id>/motor/telemetry`
- 実装: `src/dmc_ai_mobility/zenoh/keys.py` の `motor_cmd()` / `motor_telemetry()`
- payload: JSON（UTF-8 bytes）

#### motor/cmd

JSON schema:

    {
      "v_l": 0.10,
      "v_r": 0.12,
      "unit": "mps",
      "deadman_ms": 300,
      "seq": 184,
      "ts_ms": 1735467890123
    }

フィールド:
- `v_l` (number): 左モータ相当の速度指令
- `v_r` (number): 右モータ相当の速度指令
- `unit` (string): 単位（既定: `"mps"`）。現状の実装は `"mps"` 前提です。
- `deadman_ms` (int): 指令が途絶した時に停止するまでの猶予（ms）
- `seq` (int, optional): 送信側のシーケンス番号
- `ts_ms` (int, optional): 送信側タイムスタンプ（epoch ms）

備考:
- `deadman_ms` はノード側でも `config.toml` の `[motor].deadman_ms` を既定値として持ちますが、payload の `deadman_ms` が来た場合はそちらが優先されます。

#### motor/telemetry

- 実装: `src/dmc_ai_mobility/zenoh/keys.py` の `motor_telemetry()`
- payload: JSON（UTF-8 bytes）

JSON schema:

    {
      "pw_l": 1500,
      "pw_r": 1500,
      "pw_l_raw": 1520,
      "pw_r_raw": 1480,
      "cmd_v_l": 0.10,
      "cmd_v_r": 0.12,
      "cmd_unit": "mps",
      "cmd_deadman_ms": 300,
      "cmd_seq": 184,
      "cmd_ts_ms": 1735467890123,
      "ts_ms": 1735467890124
    }

フィールド:
- `pw_l` / `pw_r` (int): 出力中のパルス幅（deadband 適用後）
- `pw_l_raw` / `pw_r_raw` (int): 変換後パルス幅（clamp 前）
- `cmd_v_l` / `cmd_v_r` (number|null): 最新の速度指令
- `cmd_unit` (string|null): 速度単位（既定: `"mps"`）
- `cmd_deadman_ms` (int|null): 指令に含まれる deadman 値
- `cmd_seq` (int|null): 送信側のシーケンス番号
- `cmd_ts_ms` (int|null): 送信側タイムスタンプ（epoch ms）
- `ts_ms` (int): 送信側タイムスタンプ（epoch ms）

備考:
- `cmd_*` 系は初回指令が来るまで `null` になることがあります。

### imu

- Publish: `dmc_robo/<robot_id>/imu/state`
- 実装: `src/dmc_ai_mobility/zenoh/keys.py` の `imu_state()`
- payload: JSON（UTF-8 bytes）

JSON schema:

    {
      "gx": 0.0,
      "gy": 0.0,
      "gz": 0.0,
      "ax": 0.0,
      "ay": 0.0,
      "az": 0.0,
      "ts_ms": 1735467890123
    }

フィールド:
- `gx`/`gy`/`gz` (number): 角速度（単位は IMU ドライバ依存）
- `ax`/`ay`/`az` (number): 加速度（単位は IMU ドライバ依存）
- `ts_ms` (int): 取得時刻（epoch ms）

### oled

- Subscribe: `dmc_robo/<robot_id>/oled/cmd`
- 実装: `src/dmc_ai_mobility/zenoh/keys.py` の `oled_cmd()`
- payload: JSON（UTF-8 bytes）

JSON schema:

    {
      "text": "Hello",
      "ts_ms": 1735467890123
    }

フィールド:
- `text` (string): 表示文字列
- `ts_ms` (int, optional): 送信側タイムスタンプ（epoch ms）

備考:
- ノード側は `config.toml` の `[oled].max_hz` により更新頻度を上限付きで間引きます。

### camera

- Publish (JPEG bytes): `dmc_robo/<robot_id>/camera/image/jpeg`
- Publish (meta JSON): `dmc_robo/<robot_id>/camera/meta`
- 実装: `src/dmc_ai_mobility/zenoh/keys.py` の `camera_image_jpeg()` / `camera_meta()`

#### camera/image/jpeg

- payload: JPEG bytes（そのまま `session.publish()`）
- 受信側はファイル保存やデコード（OpenCV/PIL）で利用できます

#### camera/meta

- payload: JSON（UTF-8 bytes）

JSON schema:

    {
      "width": 640,
      "height": 480,
      "fps": 10,
      "seq": 0,
      "ts_ms": 1735467890123
    }

フィールド:
- `width` / `height` (int): 画像サイズ
- `fps` (number): publish 設定上の FPS
- `seq` (int): 連番
- `ts_ms` (int): 送信側タイムスタンプ（epoch ms）

### lidar

- Publish (scan JSON): `dmc_robo/<robot_id>/lidar/scan`
- Publish (front JSON): `dmc_robo/<robot_id>/lidar/front`
- 実装: `src/dmc_ai_mobility/zenoh/keys.py` の `lidar_scan()` / `lidar_front()`
- payload: JSON（UTF-8 bytes）

#### lidar/scan

JSON schema:

    {
      "seq": 0,
      "ts_ms": 1735467890123,
      "points": [
        {"angle_rad": 0.0, "range_m": 0.60, "intensity": null}
      ]
    }

フィールド:
- `seq` (int): 連番
- `ts_ms` (int): 取得時刻（epoch ms）
- `points` (array): 点群配列
  - `angle_rad` (number): 角度（rad）
  - `range_m` (number): 距離（m）
  - `intensity` (number|null, optional): 強度（対応する LiDAR のみ）

#### lidar/front

正面方向（0度付近）の距離を軽量に使えるようにまとめたサマリです。

JSON schema:

    {
      "seq": 0,
      "ts_ms": 1735467890123,
      "window_deg": 10.0,
      "stat": "mean",
      "distance_m": 0.60,
      "samples": 1
    }

フィールド:
- `seq` (int): 連番
- `ts_ms` (int): 取得時刻（epoch ms）
- `window_deg` (number): 正面とみなす角度範囲（度）。`± window_deg/2` を使用します。
- `stat` (string): 集計方法（`"mean"` または `"min"`）
- `distance_m` (number): 集計距離（m）
- `samples` (int): 集計に使った点数

### health（参考）

- Publish: `dmc_robo/<robot_id>/health/state`
- 実装: `src/dmc_ai_mobility/zenoh/keys.py` の `health_state()`
- payload: JSON（UTF-8 bytes）

JSON schema:

    {
      "uptime_s": 12.34,
      "ts_ms": 1735467890123
    }

## エンコード/デコード

JSON は `src/dmc_ai_mobility/zenoh/schemas.py` の `encode_json()` / `decode_json()` を利用します。

- JSON -> bytes: UTF-8
- 送信: `session.publish(key, payload_bytes)`
- 受信: `sample.payload.to_bytes()`（eclipse-zenoh）
