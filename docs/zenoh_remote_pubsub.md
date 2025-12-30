# 別PCから Zenoh を Subscribe / Publish する方法

このドキュメントは、別のPC（開発PCなど）から Zenoh 経由で本リポジトリのロボットノードに対して Subscribe / Publish を行う方法をまとめたものです。

本リポジトリの Zenoh キー命名規則は `dmc_robo/<robot_id>/<component>/<direction>` です（例: `dmc_robo/rasp-zero-01/motor/cmd`）。

## 前提

- 別PCに Python 3.9+ が入っている
- 別PCからロボット側ネットワークに到達できる（同一LAN等）
- Zenoh の Python 実装（`eclipse-zenoh`）を利用する

インストール:

    python3 -m pip install eclipse-zenoh

最小操作スクリプト:

- `docs/remote_zenoh_tool.py`（このリポジトリに同梱）
  - `motor/stop/oled/imu/camera/lidar` のサブコマンドを提供します

## ネットワーク構成（おすすめ）

複数マシンで確実に見通すには「Zenoh Router」を1台立て、全ノードをそこへ接続する構成がおすすめです。

- Router: どこか1台（例: ロボット側 or ルータ用PC）
- Robot node: `dmc_ai_mobility`（Publish/Subscribe）
- Remote PC: このドキュメントの Python スクリプト（Publish/Subscribe）

注意:
- Router の起動方法は環境で異なります（Rust版 `zenohd` など）。Router を使わない peer 構成でも動きますが、ネットワーク越しの探索が不安定になりやすいです。

## ルータに接続する設定ファイル例（remote側）

別PCに `zenoh_remote.json5` を作成し、`<ROUTER_IP>` を実際のIPに置き換えてください。

    {
      mode: "peer",
      connect: {
        endpoints: ["tcp/<ROUTER_IP>:7447"]
      }
    }

以降の例ではこの `zenoh_remote.json5` を使います。

テンプレート:

- `docs/zenoh_remote.json5.example`

### もっと簡単にする方法（おすすめ）

設定ファイルを作らずに、`--connect` で接続先を指定できます（`docs/remote_zenoh_tool.py`）。

    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 --connect "tcp/<ROUTER_IP>:7447" imu

また、環境変数 `ZENOH_CONFIG` に json5 ファイルパスを設定しておけば、`--zenoh-config` を省略できます（eclipse-zenoh 標準）。

    export ZENOH_CONFIG=/path/to/zenoh_remote.json5
    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 imu

## 共通: セッションを開く最小コード

    import zenoh
    cfg = zenoh.Config.from_file("zenoh_remote.json5")
    session = zenoh.open(cfg)

## 1) motor を Publish（ロボットを動かす）

ロボットが subscribe しているキー:
- `dmc_robo/<robot_id>/motor/cmd`

payload（JSON）例:
- `v_l` / `v_r`: 左右速度
- `unit`: `"mps"`（本リポジトリの実装は unit は現状ログ用途で、速度解釈はドライバ依存です）
- `deadman_ms`: 途絶時に停止するまでの猶予（ms）

	実行例（`robot_id=rasp-zero-01`）:

	    # (推奨) 付属の最小ツール
	    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 --zenoh-config ./zenoh_remote.json5 motor --v-l 1.0 --v-r 1.0 --duration-s 1

    python3 - <<'PY'
    import json, time
    import zenoh
    
    robot_id = "rasp-zero-01"
    key = f"dmc_robo/{robot_id}/motor/cmd"
    
    cfg = zenoh.Config.from_file("zenoh_remote.json5")
    s = zenoh.open(cfg)
    pub = s.declare_publisher(key)
    
    seq = 0
    for _ in range(50):
        payload = {
            "v_l": 0.10,
            "v_r": 0.10,
            "unit": "mps",
            "deadman_ms": 300,
            "seq": seq,
            "ts_ms": int(time.time() * 1000),
        }
        pub.put(json.dumps(payload).encode("utf-8"))
        seq += 1
        time.sleep(0.05)
    
    s.close()
    PY

止める（ゼロ指令を数回投げる）:

    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 --zenoh-config ./zenoh_remote.json5 stop

    python3 - <<'PY'
    import json, time
    import zenoh
    
    robot_id = "rasp-zero-01"
    key = f"dmc_robo/{robot_id}/motor/cmd"
    
    cfg = zenoh.Config.from_file("zenoh_remote.json5")
    s = zenoh.open(cfg)
    pub = s.declare_publisher(key)
    
    for i in range(5):
        pub.put(json.dumps({"v_l": 0.0, "v_r": 0.0, "unit": "mps", "deadman_ms": 300, "seq": i}).encode("utf-8"))
        time.sleep(0.05)
    
    s.close()
    PY

## 2) imu を Subscribe（状態を見る）

ロボットが publish しているキー:
- `dmc_robo/<robot_id>/imu/state`

実行例:

    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 --zenoh-config ./zenoh_remote.json5 imu

    python3 - <<'PY'
    import zenoh
    
    robot_id = "rasp-zero-01"
    key = f"dmc_robo/{robot_id}/imu/state"
    
    cfg = zenoh.Config.from_file("zenoh_remote.json5")
    s = zenoh.open(cfg)
    
    def on_sample(sample):
        payload = sample.payload.to_bytes()
        print(payload.decode("utf-8"))
    
    sub = s.declare_subscriber(key, on_sample)
    input("subscribing... press Enter to quit\n")
    sub.undeclare()
    s.close()
    PY

## 3) oled を Publish（表示を変える）

ロボットが subscribe しているキー:
- `dmc_robo/<robot_id>/oled/cmd`

実行例:

    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 --zenoh-config ./zenoh_remote.json5 oled --text "Hello from remote"

    python3 - <<'PY'
    import json, time
    import zenoh
    
    robot_id = "rasp-zero-01"
    key = f"dmc_robo/{robot_id}/oled/cmd"
    
    cfg = zenoh.Config.from_file("zenoh_remote.json5")
    s = zenoh.open(cfg)
    pub = s.declare_publisher(key)
    
    pub.put(json.dumps({"text": "Hello from remote", "ts_ms": int(time.time() * 1000)}).encode("utf-8"))
    time.sleep(0.2)
    
    s.close()
    PY

## 4) camera を Subscribe（JPEG と meta）

ロボットが publish しているキー:
- JPEG: `dmc_robo/<robot_id>/camera/image/jpeg`
- meta: `dmc_robo/<robot_id>/camera/meta`

JPEG は bytes のまま届くので、ファイルに保存できます。

    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 --zenoh-config ./zenoh_remote.json5 camera --out-dir ./camera_frames --print-meta

    python3 - <<'PY'
    import json
    import zenoh
    
    robot_id = "rasp-zero-01"
    key_img = f"dmc_robo/{robot_id}/camera/image/jpeg"
    key_meta = f"dmc_robo/{robot_id}/camera/meta"
    
    cfg = zenoh.Config.from_file("zenoh_remote.json5")
    s = zenoh.open(cfg)
    
    state = {"seq": None}
    
    def on_meta(sample):
        meta = json.loads(sample.payload.to_bytes().decode("utf-8"))
        state["seq"] = meta.get("seq")
        print("meta:", meta)
    
    def on_img(sample):
        jpg = sample.payload.to_bytes()
        seq = state["seq"]
        name = f"frame_{seq if seq is not None else 'unknown'}.jpg"
        with open(name, "wb") as f:
            f.write(jpg)
        print("saved:", name, len(jpg), "bytes")
    
    sub_meta = s.declare_subscriber(key_meta, on_meta)
    sub_img = s.declare_subscriber(key_img, on_img)
    input("subscribing... press Enter to quit\n")
    sub_img.undeclare()
    sub_meta.undeclare()
    s.close()
    PY

## 5) lidar を Subscribe（角度ごとの生値 / 正面サマリ）

ロボットが publish しているキー:

- scan（角度ごとの生値）: `dmc_robo/<robot_id>/lidar/scan`
- front（正面サマリ）: `dmc_robo/<robot_id>/lidar/front`

payload は環境依存になり得るため、まずは `docs/remote_zenoh_tool.py lidar --scan --print-json` で生JSONを確認してください。

実行例:

    # (デフォルト) lidar/front を subscribe して JSON を表示
    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 --zenoh-config ./zenoh_remote.json5 lidar

    # lidar/scan の JSON をそのまま表示（点群配列が大きいので注意）
    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 --zenoh-config ./zenoh_remote.json5 lidar --scan --print-json

    # lidar/scan を角度(deg)/距離(m)として表示（先頭 N 点のみ）
    python3 docs/remote_zenoh_tool.py --robot-id rasp-zero-01 --zenoh-config ./zenoh_remote.json5 lidar --scan --print-points --max-points 200

## トラブルシュート

- Remote から何も届かない:
  - `robot_id` が一致しているか確認（`config.toml` の `robot_id` と同じにする）
  - Router を使う構成なら、remote も robot も同じ router に `connect/endpoints` で接続しているか確認
- カメラが取れない（Raspberry Pi / libcamera 環境）:
  - ロボット側起動は `libcamerify` が必要なことがあります（`scripts/run_robot.sh` は自動対応済み）
