#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


LINE_RE = re.compile(r"^L:\s*(-?\d+)\s*,\s*R:\s*(-?\d+)\s*$")


def _load_toml_file(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # py3.11+
    except Exception:  # pragma: no cover
        try:
            import tomli as tomllib  # type: ignore[assignment]
        except Exception as e:  # pragma: no cover
            raise SystemExit(
                "TOML config requested but TOML parser not available.\n"
                "Use Python 3.11+ (tomllib) or `pip install tomli`."
            ) from e

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"config not found: {path}")
    except Exception as e:
        raise SystemExit(f"failed to parse config: {path} ({e})") from e

    if not isinstance(data, dict):
        raise SystemExit(f"invalid config (expected TOML table at root): {path}")
    return data


def _toml_get(obj: Any, keys: tuple[str, ...], default: Any) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


@dataclass(frozen=True)
class SerialConfig:
    robot_id: Optional[str] = None
    serial: Optional[str] = None
    baud: int = 115200
    raw_max: int = 2000
    max_mps: float = 0.5
    deadman_ms: int = 300
    publish_hz: float = 10.0
    unit: str = "mps"


def _load_serial_config(path: Optional[Path]) -> SerialConfig:
    if path is None:
        return SerialConfig()

    data = _load_toml_file(path)
    robot = _toml_get(data, ("robot",), {})
    controller = _toml_get(data, ("controller",), {})
    motor = _toml_get(data, ("motor",), {})

    def _f(x: Any, default: float) -> float:
        try:
            return float(x)
        except Exception:
            return float(default)

    def _i(x: Any, default: int) -> int:
        try:
            return int(x)
        except Exception:
            return int(default)

    def _s(x: Any, default: Optional[str]) -> Optional[str]:
        if isinstance(x, str):
            return x
        return default

    robot_id = _s(_toml_get(robot, ("robot_id",), None), None)
    if robot_id is not None and not robot_id.strip():
        robot_id = None

    serial = _s(_toml_get(controller, ("serial",), None), None)
    if serial is not None and not serial.strip():
        serial = None

    baud = _clamp_int(
        _i(_toml_get(controller, ("baud",), SerialConfig.baud), SerialConfig.baud),
        1200,
        2000000,
    )
    raw_max = _clamp_int(
        _i(_toml_get(controller, ("raw_max",), SerialConfig.raw_max), SerialConfig.raw_max),
        1,
        10000,
    )
    max_mps = _clamp(
        _f(_toml_get(controller, ("max_mps",), SerialConfig.max_mps), SerialConfig.max_mps),
        0.0,
        5.0,
    )
    publish_hz = _clamp(
        _f(_toml_get(controller, ("publish_hz",), SerialConfig.publish_hz), SerialConfig.publish_hz),
        1.0,
        60.0,
    )

    deadman_default = _i(
        _toml_get(motor, ("deadman_ms",), SerialConfig.deadman_ms),
        SerialConfig.deadman_ms,
    )
    deadman_ms = _clamp_int(
        _i(_toml_get(controller, ("deadman_ms",), deadman_default), deadman_default),
        50,
        2000,
    )

    unit = _s(_toml_get(controller, ("unit",), SerialConfig.unit), SerialConfig.unit)

    return SerialConfig(
        robot_id=robot_id,
        serial=serial,
        baud=baud,
        raw_max=raw_max,
        max_mps=max_mps,
        deadman_ms=deadman_ms,
        publish_hz=publish_hz,
        unit=unit,
    )


def _apply_connect_overrides(cfg: Any, mode: str, connect_endpoints: list[str]) -> Any:
    if mode:
        cfg.insert_json5("mode", json.dumps(mode))
    if connect_endpoints:
        cfg.insert_json5("connect/endpoints", json.dumps(connect_endpoints))
    return cfg


def _build_session_opener(
    *, config_path: Optional[Path], mode: str, connect_endpoints: list[str]
):
    import zenoh  # provided by `pip install eclipse-zenoh`

    if config_path is not None and not config_path.exists():
        raise SystemExit(
            f"zenoh config not found: {config_path}\n"
            "Create it (see docs/zenoh_remote_pubsub.md) or omit --zenoh-config to use defaults."
        )

    if config_path:
        cfg = zenoh.Config.from_file(str(config_path))
    else:
        try:
            cfg = zenoh.Config.from_env()
        except Exception:
            cfg = zenoh.Config()

    if connect_endpoints:
        cfg = _apply_connect_overrides(cfg, mode, connect_endpoints)

    def _opener() -> Any:
        try:
            return zenoh.open(cfg)
        except Exception as e:
            raise SystemExit(f"failed to open zenoh session: {e}") from e

    return _opener


def _key(robot_id: str, suffix: str) -> str:
    if not robot_id or "/" in robot_id:
        raise SystemExit("robot_id must be non-empty and must not contain '/'")
    return f"dmc_robo/{robot_id}/{suffix}"


def _parse_line(text: str) -> Optional[tuple[int, int]]:
    if not text.startswith("L:"):
        return None
    m = LINE_RE.match(text)
    if not m:
        return None
    try:
        left = int(m.group(1))
        right = int(m.group(2))
    except Exception:
        return None
    return left, right


def _map_to_mps(raw: float, raw_max: int, max_mps: float) -> float:
    if raw_max <= 0:
        return 0.0
    return float(raw) / float(raw_max) * float(max_mps)


def _send_stop(pub: Any, *, unit: str, deadman_ms: int, repeat: int = 5) -> None:
    payload = {
        "v_l": 0.0,
        "v_r": 0.0,
        "unit": unit,
        "deadman_ms": int(deadman_ms),
        "seq": 0,
        "ts_ms": int(time.time() * 1000),
    }
    for i in range(repeat):
        payload["seq"] = i
        payload["ts_ms"] = int(time.time() * 1000)
        try:
            pub.put(json.dumps(payload).encode("utf-8"))
        except Exception:
            return
        time.sleep(0.05)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Serial controller -> motor/cmd bridge")
    p.add_argument("--robot-id", default=None, help="robot_id (e.g. rasp-zero-01)")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.toml. If omitted, loads ./config.toml when it exists.",
    )
    p.add_argument(
        "--no-config",
        action="store_true",
        help="Disable loading ./config.toml (even if it exists).",
    )
    p.add_argument(
        "--zenoh-config",
        type=Path,
        default=None,
        help="Path to a zenoh json5 config. If omitted, uses defaults.",
    )
    p.add_argument(
        "--mode",
        type=str,
        default="peer",
        help="Zenoh mode override when using --connect (default: peer).",
    )
    p.add_argument(
        "--connect",
        action="append",
        default=[],
        help='Connect endpoint override (repeatable), e.g. --connect "tcp/192.168.1.10:7447". '
        "If set, it is applied on top of defaults or --zenoh-config.",
    )
    p.add_argument("--serial", type=str, default=None, help="Serial device path (e.g. /dev/tty.usbmodemXXXX)")
    p.add_argument("--baud", type=int, default=None, help="Serial baud rate (USB CDC ignores but host needs it)")
    p.add_argument("--raw-max", type=int, default=None, help="Raw max magnitude for scaling (default: 2000)")
    p.add_argument("--max-mps", type=float, default=None, help="Max speed (mps) at raw-max (default: 0.5)")
    p.add_argument("--deadman-ms", type=int, default=None, help="Deadman ms override for motor/cmd")
    p.add_argument(
        "--publish-hz", type=float, default=None, help="Publish rate (Hz) (default: 10)"
    )
    p.add_argument("--unit", type=str, default=None, help="Speed unit (default: mps)")
    p.add_argument("--print-lines", action="store_true", help="Print parsed serial values")
    p.add_argument(
        "--print-values",
        action="store_true",
        help="Print raw and converted values at publish time",
    )
    p.add_argument("--print-pub", action="store_true", help="Print published payloads")
    args = p.parse_args(argv)

    config_path: Optional[Path]
    if args.no_config:
        config_path = None
    elif args.config is not None:
        config_path = args.config
    else:
        candidate = Path("config.toml")
        config_path = candidate if candidate.exists() else None

    cfg = _load_serial_config(config_path)

    robot_id = args.robot_id if args.robot_id is not None else cfg.robot_id
    if not robot_id:
        raise SystemExit("robot_id not specified (use --robot-id or set [robot].robot_id)")

    serial_port = args.serial if args.serial is not None else cfg.serial
    if not serial_port:
        raise SystemExit("serial device not specified (use --serial or set [controller].serial)")

    baud = int(args.baud) if args.baud is not None else cfg.baud
    raw_max = int(args.raw_max) if args.raw_max is not None else cfg.raw_max
    max_mps = float(args.max_mps) if args.max_mps is not None else cfg.max_mps
    deadman_ms = int(args.deadman_ms) if args.deadman_ms is not None else cfg.deadman_ms
    publish_hz = float(args.publish_hz) if args.publish_hz is not None else cfg.publish_hz
    unit = args.unit if args.unit else cfg.unit

    if raw_max <= 0:
        raise SystemExit("--raw-max must be > 0")
    if publish_hz <= 0:
        raise SystemExit("--publish-hz must be > 0")

    open_session = _build_session_opener(
        config_path=args.zenoh_config, mode=args.mode, connect_endpoints=list(args.connect)
    )
    key = _key(robot_id, "motor/cmd")

    try:
        import serial  # provided by `pip install pyserial`
    except Exception as e:
        raise SystemExit("pyserial is required: pip install pyserial") from e

    session = open_session()
    pub = session.declare_publisher(key)
    ser = None

    seq = 0
    try:
        interval_s = 1.0 / float(publish_hz)
        ser = serial.Serial(serial_port, baudrate=baud, timeout=0.01)
        try:
            ser.reset_input_buffer()
        except Exception:
            pass

        sum_l = 0.0
        sum_r = 0.0
        count = 0
        next_pub = time.monotonic() + interval_s

        while True:
            line = ser.readline()
            if line:
                text = line.decode("utf-8", errors="replace").strip()
                parsed = _parse_line(text)
                if parsed is not None:
                    left_raw, right_raw = parsed
                    left_raw = _clamp_int(left_raw, -raw_max, raw_max)
                    right_raw = _clamp_int(right_raw, -raw_max, raw_max)
                    sum_l += float(left_raw)
                    sum_r += float(right_raw)
                    count += 1
                    if args.print_lines:
                        print(f"raw L={left_raw} R={right_raw}")

            now = time.monotonic()
            if now < next_pub:
                continue

            if count > 0:
                avg_l = sum_l / count
                avg_r = sum_r / count
            else:
                avg_l = 0.0
                avg_r = 0.0

            avg_l = _clamp(avg_l, -raw_max, raw_max)
            avg_r = _clamp(avg_r, -raw_max, raw_max)
            v_l = _map_to_mps(avg_l, raw_max, max_mps)
            v_r = _map_to_mps(avg_r, raw_max, max_mps)
            if args.print_values:
                print(
                    f"avg_raw L={avg_l:.1f} R={avg_r:.1f} -> v_l={v_l:.3f} v_r={v_r:.3f}"
                )
            payload = {
                "v_l": v_l,
                "v_r": v_r,
                "unit": unit,
                "deadman_ms": deadman_ms,
                "seq": seq,
                "ts_ms": int(time.time() * 1000),
            }
            pub.put(json.dumps(payload).encode("utf-8"))
            if args.print_pub:
                print(json.dumps(payload))
            seq += 1
            sum_l = 0.0
            sum_r = 0.0
            count = 0

            while next_pub <= now:
                next_pub += interval_s
    except KeyboardInterrupt:
        pass
    finally:
        try:
            _send_stop(pub, unit=unit, deadman_ms=deadman_ms, repeat=5)
        except Exception:
            pass
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        try:
            session.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
