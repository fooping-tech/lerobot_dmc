# 概要（現行仕様）

このリポジトリは、Zenoh 経由で `dmc_robo/<robot_id>` を操作・観測するための LeRobot プラグイン群と、運用に必要なドキュメントを提供します。

## 目的

- LeRobot の CLI（例: `lerobot-teleoperate` / `lerobot-record`）から `dmc_robo` を Robot として扱えるようにする
- GUI テレオペ（カメラ/IMU/LiDAR 表示 + モータ操作）を提供する
- シリアルコントローラ入力を GUI に統合し、操作入力の一元化と競合回避を行う

## 構成

### Robot プラグイン（観測 + モータ指令）

- パッケージ: `packages/lerobot_robot_dmc_robo`
- 役割:
  - Zenoh subscribe による観測取得（例: `camera/image/jpeg`, `imu/state`, `lidar/*`）
  - Zenoh publish によるモータ指令送信（`motor/cmd`）
- 主に参照するドキュメント:
  - `lerobot_dmc_robo_usage.md`
  - `zenoh_remote_pubsub.md`
  - `keys_and_payloads.md`

### Teleoperator プラグイン（GUI テレオペ + 既定設定）

- パッケージ: `packages/lerobot_teleoperator_dmc_robo`
- 役割:
  - GUI（`remote_zenoh_ui.py`）を起動してテレオペを行う
  - `lerobot-teleoperate` から GUI を透過的に利用できるようにする
- 主に参照するドキュメント:
  - `remote_ui.md`

### シリアルコントローラ統合

- コントローラの出力（`L:<left>,R:<right>`）を GUI が直接読み取り、モータ入力に反映します。
- 入力仲裁は「シリアル優先」です（シリアルが有効な間は GUI キー入力より優先されます）。
- 仕様の詳細:
  - `serial_controller_software_spec.md`
  - `serial_controller.md`
  - `serial-communication-spec.md`

## 設定（config.toml）

- 代表的な設定はリポジトリ直下の `config.toml` に置きます。
- 主に使うセクション:
  - `[robot]`: robot_id
  - `[controller]`: シリアル入力設定（ポート/スケール/タイムアウト/ログ）
  - `[motor]`: deadman 等

## ドキュメント運用（MkDocs）

- `mkdocs.yml` で MkDocs Material のサイト構成を定義しています。
- GitHub Actions により GitHub Pages へデプロイ可能です（`.github/workflows/mkdocs.yml`）。
