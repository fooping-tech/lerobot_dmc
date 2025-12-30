# LeRobot Zenoh Robot Plugin: `dmc_robo/<robot_id>` を `lerobot` から操作・記録できるようにする

このExecPlanは living document です。実装中は `Progress` / `Surprises & Discoveries` / `Decision Log` / `Outcomes & Retrospective` を必ず更新し、途中停止してもこの1ファイルだけで再開できる状態を維持します。

このリポジトリは現状、設計・実装ガイドがこの `PLANS.md` しかありません。以降の作業はこのExecPlanの記述を唯一の仕様として進めます（外部ドキュメント参照に依存しないよう、本計画内に必要事項を埋め込みます）。ただし、ロボットの動かし方は `../dmc_ai_host` を参照すること。LeRobot の最新仕様は `../lerobot` を参照すること。


## Purpose / Big Picture

この変更でやりたいことは「Zenoh越しに動いている `dmc_robo/<robot_id>` を、HuggingFace LeRobot の CLI ツール（例: `lerobot-record` / `lerobot-teleoperate`）から “Robot” として扱えるようにする」ことです。

ユーザー視点の成果は次の2つです。

1) `pip install -e ...` でインストールした自作パッケージが、`lerobot` のプラグインとして自動検出される。  
2) `--robot.type=dmc_robo` のように “type” を指定して、Zenoh 経由のセンサ観測（カメラ/IMUなど）取得と、アクション送信（左右車輪速度コマンド publish）を LeRobot 経由で実行できる。

「動いた」の判定は、(a) ロボットから届く `camera/image/jpeg` が `get_observation()` で画像（`uint8` の `HWC`）として取れる、(b) `send_action()` が `dmc_robo/<robot_id>/motor/cmd` に publish され、ロボットが反応する（または別subscriberでpayloadが確認できる）、の両方が満たされることです。


## Progress

- [x] (2025-12-30) LeRobot のプラグイン規約（パッケージprefix/命名/配置/`__init__.py`公開）を本計画に落とし込む。
- [x] (2025-12-30) `lerobot_robot_dmc_robo` パッケージ骨格（`pyproject.toml` / モジュール構成 / import公開）を追加する。
- [x] (2025-12-30) `DmcRoboConfig` / `DmcRobo`（Zenoh接続、obs/action I/F、I/O実装）を実装する。
- [x] (2025-12-30) 最小スモークテスト（接続、1回観測、停止コマンド）を `python -m ...` で実行可能にする。
- [x] (2025-12-30) `lerobot-*` CLI からの起動手順（実機/疑似）を docs に追加し、受け入れ確認する。


## Surprises & Discoveries

- Observation: `imu/state` / `lidar/*` のJSONスキーマは環境依存で確定していない可能性がある。
  Evidence: このリポジトリの既存ツール（`docs/remote_zenoh_tool.py` / `remote_zenoh_ui.py`）は raw JSON を扱えるようにしている。

- Observation: Playwright MCP で HuggingFace Docs を直接ブラウズできなかった（Chromium/Chrome が手元環境に無く、インストールも sudo が必要だった）。
  Evidence: `browserType.launchPersistentContext: Chromium distribution 'chrome' is not found` と表示され、`browser_install` は sudo 要求で失敗した。


## Decision Log

- Decision: LeRobot 側には一切パッチを当てず、「別の installable package として Robot を追加する」方式を採用する。
  Rationale: LeRobot の推奨する拡張方法で、アップストリーム更新に追従しやすい。
  Date/Author: 2025-12-30 / Codex

- Decision: `DmcRobo` の “action” は `motor/cmd` の payload に合わせて `v_l` / `v_r`（float, m/s）を基本にする。
  Rationale: 既存の Zenoh I/F（`docs/remote_zenoh_tool.py` とロボット側）と整合させ、変換ロジックを最小化する。
  Date/Author: 2025-12-30 / Codex

- Decision: JPEG デコードは Pillow を使い、`camera/image/jpeg` を RGB 配列として返す。
  Rationale: 依存を最小限に保ちつつ、`numpy` 配列（HWC, uint8）を安定して得られるため。
  Date/Author: 2025-12-30 / Codex


## Outcomes & Retrospective

（未完了。実装が進んだら、できたこと・できなかったこと・原因をここに追記する）


## Context and Orientation

このリポジトリ（`dmc_ai_host`）にはすでに Zenoh 経由の remote 側ツールがあります。

- `remote_zenoh_ui.py`: デスクトップUI（publish: `motor/cmd`, `oled/cmd` / subscribe: `imu/state`, `camera/*`, `lidar/*`）
- `docs/remote_zenoh_tool.py`: 最小CLI（publish/subscribe の切り分けや stop 指令送信に利用できる）
- キー命名: `dmc_robo/<robot_id>/<suffix>`（例: `dmc_robo/robo1/motor/cmd`）

本件で追加するのは「LeRobot が自動検出できる “Robot プラグイン” パッケージ」です。LeRobot の CLI は Python 環境にインストールされたプラグインを探索し、`--robot.type=<name>` のような “type” で指定できるようにします（内部実装に手を入れない）。

このExecPlan内で使う用語:

- LeRobot: HuggingFace のロボット学習・データ収集フレームワーク。CLI（`lerobot-record` など）と、Robot/Teleoperator/Camera などの抽象I/Fを持つ。
- plugin（プラグイン）: `lerobot` 本体を変更せず、別の Python パッケージを `pip install` するだけで機能追加する仕組み。
- Robot: “観測（observation）を返し、アクション（action）を送れる” ものとして LeRobot が扱う抽象クラス。
- observation_features / action_features: それぞれ `get_observation()` / `send_action()` の辞書フォーマットを宣言する “契約”。重要: これらは robot 未接続でも呼べる必要がある（ハード状態に依存しない）。


## Plan of Work

### 1) LeRobot のプラグイン発見規約を満たすパッケージを作る（4つの必須ルール）

LeRobot が自動で検出するために、以下の4ルールを厳守します（この4つが満たされれば、`lerobot` 本体に変更を入れずに CLI から使える前提）。

1. Installable package + prefix:
   - `pyproject.toml`（または `setup.py`）を持つ “pip install できる” パッケージにする。
   - パッケージ名（distribution name）は、対象に応じて prefix を付ける。Robot の場合は `lerobot_robot_` で始める。
2. `SomethingConfig` / `Something` 命名:
   - 設定クラスが `DmcRoboConfig` なら、実装クラスは `DmcRobo` のように “Config を外した名前” にする。
3. 予測可能なファイル配置:
   - Device クラスは Config クラスから見て予測可能な場所に置く。
   - 推奨: 同じパッケージ配下に `config_*.py` と本体 `*.py` を分ける。
4. `__init__.py` で公開:
   - パッケージの `__init__.py` から、Config と Robot の両方を import して公開する（これにより探索/参照が安定する）。

この規約に従い、`lerobot_robot_dmc_robo` というパッケージをこのリポジトリに追加します（編集可能インストール `pip install -e` で開発する）。

このExecPlanでは、追加するディレクトリ構造を次で固定します（迷わないために “例” ではなくこれを正とする）。

    packages/lerobot_robot_dmc_robo/
    ├── pyproject.toml
    └── lerobot_robot_dmc_robo/
        ├── __init__.py
        ├── config_dmc_robo.py
        ├── dmc_robo.py
        └── smoke_test.py

`pyproject.toml` の最低限の要件:

- `[project] name = "lerobot_robot_dmc_robo"`（prefix ルール: `lerobot_robot_` で始める）
- dependencies に `lerobot`, `eclipse-zenoh`, `numpy` を含める
- JPEG decode に Pillow を使う場合は `Pillow` を含める（OpenCV を使うなら `opencv-python` を含める）

`__init__.py` の最低限の要件（公開ルール）:

- `from .config_dmc_robo import DmcRoboConfig`
- `from .dmc_robo import DmcRobo`


### 2) `DmcRoboConfig` を実装する（Zenoh 接続情報 + ロボットID + 観測仕様）

`DmcRoboConfig` は次を保持します（少なくともここにある情報だけで `DmcRobo` が動くようにする）。

- `robot_id`: Zenoh キーの `<robot_id>` 部分
- Zenoh接続:
  - `zenoh_config_path`（任意）: `zenoh.Config.from_file(...)` で読む
  - `connect`（任意、複数可）: `tcp/<ip>:7447` 等（`remote_zenoh_ui.py` と同様の思想）
- `deadman_ms`（デフォルト 300）: `motor/cmd` の安全停止用
- `camera`:
  - `camera_height` / `camera_width`（観測契約用。実際のJPEGのサイズが違っていたら警告を出す）
- `imu`:
  - `imu_field_path`（任意）: JSON 内の gyro 3軸を取り出すためのパス指定（スキーマ差異を吸収する）

登録:

- `@RobotConfig.register_subclass("dmc_robo")` を付与し、CLI から `--robot.type=dmc_robo` で選べるようにする。


### 3) `DmcRobo` を実装する（Robot I/F の最小実装 + Zenoh I/O）

LeRobot の Robot 抽象I/Fに従い、次を実装します（必要最低限）。

- `observation_features`（未接続でも呼べる）
  - `camera` を `(<H>, <W>, 3)` の `uint8` として宣言（キー名は `camera` など固定）
  - `imu.gyro` を `(3,)` の float として宣言（キー名は固定）
  - 追加で `ts_ms` / `seq` のようなメタ情報を入れる場合は `int` として宣言
- `action_features`（未接続でも呼べる）
  - `v_l`, `v_r` を float として宣言（単位は m/s とする）
- `is_connected` / `connect()` / `disconnect()`
  - Zenoh session open/close
  - publisher: `dmc_robo/<robot_id>/motor/cmd`
  - subscribers: `dmc_robo/<robot_id>/camera/image/jpeg`, `dmc_robo/<robot_id>/imu/state`（まずはこの2つに限定）
  - subscribe は “最新値を保持する” 方式でよい（バックグラウンドで受け取り、`get_observation()` は最新を返す）
- `is_calibrated` / `calibrate()` / `configure()`
  - このロボットでは物理的キャリブレーションは扱わず `is_calibrated=True`、`calibrate()` は no-op にする（将来の拡張余地だけ残す）
  - `configure()` も当面 no-op（将来 `deadman_ms` などを publish 側初期化する場合はここ）
- `get_observation()`
  - 未接続なら `ConnectionError`
  - `camera/image/jpeg` は decode して `np.ndarray`（`HWC`, `uint8`, BGR/RGBのどちらかに統一）にする
  - `imu/state` は JSON decode し、`imu_field_path` で 3軸を抽出できるようにする（抽出できない場合は例外ではなく “欠損” として扱い、ログ/警告を出す）
- `send_action(action)`
  - `action` から `v_l` / `v_r` を取り、`motor/cmd` に JSON を publish する
  - payload は既存の `docs/remote_zenoh_tool.py` と同形を踏襲し、最低限:
    - `v_l`, `v_r`, `unit`(="mps"), `deadman_ms`, `seq`, `ts_ms`
  - 速度の safety clip（最大速度）は config に持たせ、ここで clamp する（将来事故防止のため、最初から入れておく）

Zenoh キー生成は既存コードの規約に合わせ、`remote_zenoh_ui.py` と同等の helper（`dmc_robo/{robot_id}/{suffix}`）を使う。

実装するクラス/属性（最低限、ここまで到達すれば LeRobot 側で “Robot” として扱える前提）:

- `packages/lerobot_robot_dmc_robo/lerobot_robot_dmc_robo/config_dmc_robo.py`
  - `@RobotConfig.register_subclass("dmc_robo")`
  - `@dataclass class DmcRoboConfig(RobotConfig): ...`
- `packages/lerobot_robot_dmc_robo/lerobot_robot_dmc_robo/dmc_robo.py`
  - `class DmcRobo(Robot):`
    - `config_class = DmcRoboConfig`
    - `name = "dmc_robo"`
    - `observation_features` / `action_features`
    - `connect` / `disconnect` / `get_observation` / `send_action`


### 4) スモークテストと CLI 連携の確認

LeRobot の CLI 側が実際にこの Robot を “発見できる” ことの検証が最重要です。そこで、2段階で確認します。

- 段階A（lerobot不要の最小確認）:
  - `python -m lerobot_robot_dmc_robo.smoke_test --robot-id ...` のような形で、Zenoh接続→camera 1枚取得→stop publish までを確認する。
- 段階B（lerobot経由）:
  - `lerobot-* --help` を見て `--robot.type` の指定方法を確認する。
  - `--robot.type=dmc_robo` で起動し、`get_observation()` と `send_action()` が呼ばれていることをログで確認する（実機が無い場合は subscriber/publisher の確認で代替する）。


## Concrete Steps

以下のコマンドはこのリポジトリ root（`dmc_ai_host/`）で実行します。

1) venv 作成と依存導入（既存 UI 用依存はそのまま利用）

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -U pip
    python -m pip install -r requirements.txt

2) LeRobot を導入（どちらか片方でOK。失敗したらもう片方）

    python -m pip install lerobot

    # もし PyPI に無い/古い場合:
    python -m pip install 'git+https://github.com/huggingface/lerobot.git'

3) プラグインパッケージを追加し、editable install

    # 例: packages/lerobot_robot_dmc_robo を作った場合
    python -m pip install -e packages/lerobot_robot_dmc_robo

4) 段階A: スモークテスト

    python -m lerobot_robot_dmc_robo.smoke_test --robot-id <ROBOT_ID> --connect 'tcp/<ROUTER_IP>:7447'

期待する挙動（短い目安）:

- “Zenoh session opened” が表示される
- `camera/image/jpeg` を受けたら “decoded image shape=(H,W,3)” のようなログが出る
- 終了時に `motor/cmd` へ stop（`v_l=v_r=0`）が publish される

5) 段階B: LeRobot CLI で発見できるかを確認

    lerobot-teleoperate --help
    lerobot-record --help

ここで “robot.type” に相当する指定が見つかったら、それに従って `dmc_robo` を指定して起動する。


## Validation and Acceptance

受け入れ条件（実機あり）:

1) インストール:
   - `pip install -e packages/lerobot_robot_dmc_robo` 後に import エラーが無い。
2) Zenoh I/O:
   - `smoke_test` が `camera/image/jpeg` を decode して返せる。
   - `smoke_test` の停止 publish（`v_l=v_r=0`）が `dmc_robo/<robot_id>/motor/cmd` に流れる（別subscriberで確認してよい）。
3) LeRobot 経由:
   - `lerobot-*` の CLI から `dmc_robo` を type 指定でき、内部で connect→observation→action が進む（少なくともエラーで落ちず、ログで確認できる）。

受け入れ条件（実機なし/ネットワークのみ）:

- `docs/remote_zenoh_tool.py` を別ターミナルで subscriber として立て、`smoke_test` の publish が観測できること。


## Idempotence and Recovery

- `pip install -e ...` は何度実行しても安全（再インストール）です。
- Zenoh接続が失敗する場合は `--zenoh-config` を優先して切り替え可能にし、失敗時ログに “どの config / connect を使ったか” を必ず出します。
- 走行安全: 例外や Ctrl+C で終了しても、可能な範囲で `motor/cmd` の stop を送る（`try/finally` で保証する）。


## Artifacts and Notes

実装後、このExecPlanに貼るべき最小ログ:

- `smoke_test` の起動ログ（robot_id, connect/config の要約）
- 最初に受け取った `imu/state` の raw JSON のサンプル（個人情報や秘密情報は除く）
- `camera/image/jpeg` の decode 成功ログ（shape, dtype）


## Interfaces and Dependencies

### Zenoh キー

- publish: `dmc_robo/<robot_id>/motor/cmd`
- subscribe: `dmc_robo/<robot_id>/camera/image/jpeg`
- subscribe: `dmc_robo/<robot_id>/imu/state`

（将来追加候補: `camera/meta`, `lidar/*`, `oled/cmd`）

### `motor/cmd` payload（JSON）

最低限この形を送る（既存ツール互換）:

    {
      "v_l": <float>,
      "v_r": <float>,
      "unit": "mps",
      "deadman_ms": <int>,
      "seq": <int>,
      "ts_ms": <int>
    }

### Python依存

- `eclipse-zenoh`（新規）
- `lerobot`（新規）
- `numpy`（画像/IMU を配列にするため。既存UIでも使用）
- JPEG decode 用（どれか1つに統一する）:
  - 既存環境が `opencv-python` を持つならそれを使用、無ければ `Pillow` を依存に追加


---
変更メモ（なぜ変えたか）:

- 2025-12-30: 既存の “remote UI” ではなく、LeRobot 連携（Robot プラグイン）を新しい目的として ExecPlan を刷新した。理由は「LeRobot の CLI で `dmc_robo` を robot として扱いたい」という要求が最優先になったため。
