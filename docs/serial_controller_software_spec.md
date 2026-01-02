# シリアルコントローラ ソフトウェア仕様書（GUI統合版）

## 1. 概要

本仕様書は、GUIテレオペレーション（`dmc_robo_teleop`）に統合された
シリアルコントローラ入力の仕様を定義する。

前提となるコントローラ実装（ファームウェア）:
- https://github.com/fooping-tech/DifferentialDriveController

## 2. スコープ

対象範囲:
- GUIプロセス内でのUSBシリアル入力（`L:<left>,R:<right>`）の受信
- raw 値からモータ速度（m/s）への変換
- シリアル入力とGUIキー入力の仲裁（シリアル優先）
- GUI単体起動および LeRobot teleop でのモータ指令送信

対象外:
- コントローラファームウェアの挙動
- Zenohルータやネットワーク設定
- ロボット側モータ制御実装

## 3. 構成要素

### 3.1 GUI テレオペレータ
- モジュール: `packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/remote_zenoh_ui.py`
- クラス: `MainWindow`（`SerialReader` を内包）
- シリアル入力は `UIConfig.serial` で有効化される

### 3.2 LeRobot Teleoperator ラッパー
- モジュール: `packages/lerobot_teleoperator_dmc_robo/lerobot_teleoperator_dmc_robo/dmc_robo_teleop.py`
- Teleop設定にシリアル情報が無い場合、`config.toml` を読み込む
- GUIのシリアル入力を使って `lerobot-teleoperate` の action を生成する

### 3.3 シリアルリーダ（スレッド）
- クラス: `SerialReader`（デーモンスレッド）
- シリアル行を読み取り、`L:/R:` を解析して共有状態に反映
- エラー時は自動再接続する

## 4. シリアル入力フォーマット

各フレームはASCII 1行:

```
L:<left>,R:<right>\n
```

例:
```
L:0,R:0
L:250,R:240
L:-300,R:-310
```

## 5. 設定

設定は `config.toml` から読み込む。`[controller]` を使用し、`[serial]` は
エイリアスとして扱う。

### 5.1 設定キー

```
[controller]
enabled = true
serial = "/dev/tty.usbmodemXXXX"
baud = 115200
raw_max = 2000
max_mps = 0.5
timeout_s = 0.5
print_lines = false
print_values = false
```

キー説明:
- `enabled`: シリアル入力を有効化。未指定時は `serial` があれば自動で有効。
- `serial`: シリアルデバイスパス。
- `baud`: ボーレート（USB CDCでは実質無視だがホスト側に必要）。
- `raw_max`: raw 入力の最大値（clamp 上限）。
- `max_mps`: `raw_max` 到達時の速度（m/s）。
- `timeout_s`: 直近入力からの有効期限（秒）。
- `print_lines`: raw 値をターミナルに出力。
- `print_values`: raw と変換後の値をターミナルとUIログに出力。

### 5.2 既定値
- `baud = 115200`
- `raw_max = 2000`
- `max_mps = 0.5`
- `timeout_s = 0.5`
- `enabled = false`（`serial` 指定時は自動で有効）

## 6. 実行時挙動

### 6.1 起動時
- GUIは `config.toml` を読み込み、UI既定値とシリアル設定を取得する。
- `lerobot-teleoperate` 起動時は `dmc_robo_teleop` が `config.toml` を読み込む。

### 6.2 シリアル読取
- バックグラウンドスレッドで実行。
- 成功時ログ: `serial connected: <port> @ <baud>`
- 読取エラー: `serial read failed: <error>` を出して再接続。
- Openエラー: `serial open failed: <error> (retrying)` を出して再接続。
- 1秒間隔で再接続を試行する。

### 6.3 変換
- raw の `L/R` を `[-raw_max, raw_max]` に clamp。
- 速度変換:
  - `v = raw / raw_max * max_mps`

### 6.4 入力仲裁（シリアル優先）
- `timeout_s` 以内のシリアル入力があればシリアルを採用。
- シリアルが無効/未入力の場合はGUIキー入力を採用。
- UI 表示:
  - `input source: serial | ui`
  - `serial input: raw L=.. R=.. age=..ms` または `serial: waiting`

### 6.5 モータ送信
- GUI単体起動:
  - UIの `publish_hz` で `motor/cmd` を送信。
  - 入力は「シリアル優先」。
- `lerobot-teleoperate`:
  - UIのモータタイマーは停止する（直接publishしない）。
  - `dmc_robo_teleop` が GUI の入力解決結果を action として返す。

### 6.6 Deadman
- 入力が無い場合は `v_l=0, v_r=0` を送信。
- Teleop 側の `deadman_ms` により、一定時間入力がない場合はゼロに戻る。

## 7. ログとデバッグ

UIログ（約1Hzのレート制限）:
- `serial input raw L=... R=... -> v_l=... v_r=...`

ターミナル出力（設定により有効化）:
- `print_lines = true`: raw 値を出力
- `print_values = true`: raw と変換後を出力

## 8. 依存関係

- `pyserial`（シリアル入力）
- `PySide6`, `pyqtgraph`（GUI）
- `eclipse-zenoh`（通信）

## 9. 既知の制約

- シリアル入力はGUIテレオペレータ実行時のみ対応。
- `L:` で始まらない行は破棄される。
- ソフト側で deadzone は適用しない（線形変換のみ）。

## 10. 受け入れ条件

- UIログに `serial connected: ...` が出る。
- UIの `serial input` が更新される。
- UIの `last cmd` が変化し、`source=serial` が表示される。
- シリアル入力とGUI入力の競合が発生しない。
