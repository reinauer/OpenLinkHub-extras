#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request


DEFAULT_API = "http://127.0.0.1:27003"
DEFAULT_DEVICE_ID = ""
DEFAULT_MEMORY_DEVICE_ID = ""
DEFAULT_CHANNEL_ID = 1
LCD_IMAGE_MODE = 10
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def image_name(path):
    return Path(path).stem


def validate_image_name(path):
    name = image_name(path)
    if not re.fullmatch(r"[A-Za-z0-9]+", name):
        raise RuntimeError(
            f"{path.name} is not accepted by OpenLinkHub; use only letters and numbers "
            "before the extension"
        )
    return name


def api_json(api_url, path, payload=None, success_statuses=(1,)):
    data = None
    headers = {}
    method = "GET"

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"

    req = request.Request(
        api_url.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
    except error.URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{method} {path} returned non-JSON: {raw[:200]}") from exc

    if parsed.get("status") not in success_statuses:
        raise RuntimeError(f"{method} {path} failed: {parsed}")

    return parsed


def upload_image(api_url, path):
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise RuntimeError(
            f"{path} is {size} bytes; OpenLinkHub upload limit is {MAX_UPLOAD_BYTES} bytes"
        )

    boundary = "----openlinkhub-load-lcd-" + uuid.uuid4().hex
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    file_data = path.read_bytes()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("ascii"),
            (
                'Content-Disposition: form-data; name="animationFile"; '
                f'filename="{path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("ascii"),
            file_data,
            b"\r\n",
            f"--{boundary}--\r\n".encode("ascii"),
        ]
    )

    req = request.Request(
        api_url.rstrip("/") + "/api/lcd/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        if exc.code == 409:
            return {"status": 1, "message": f"{path.name} already uploaded"}
        raise RuntimeError(f"upload {path} failed: HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"upload {path} failed: {exc}") from exc

    parsed = json.loads(raw)
    if parsed.get("status") != 1:
        raise RuntimeError(f"upload {path} failed: {parsed}")
    return parsed


def set_lcd_mode(api_url, device_id, channel_id):
    return api_json(
        api_url,
        "/api/lcd",
        {"deviceId": device_id, "channelId": channel_id, "mode": LCD_IMAGE_MODE},
    )


def set_lcd_image(api_url, device_id, channel_id, name):
    return api_json(
        api_url,
        "/api/lcd/image",
        {"deviceId": device_id, "channelId": channel_id, "image": name},
    )


def discover_fan_channels(api_url, device_id):
    response = api_json(
        api_url, f"/api/devices/{device_id}", success_statuses=(0, 1)
    )
    device = response.get("device") or {}
    channels = []

    for channel_id, details in (device.get("devices") or {}).items():
        description = str(details.get("description", "")).lower()
        name = str(details.get("name", "")).lower()
        if details.get("AIO"):
            continue
        if description == "fan" or "fan" in name:
            channels.append(int(channel_id))

    if not channels:
        raise RuntimeError("no fan channels found in OpenLinkHub device data")
    return sorted(channels)


def discover_memory_channels(api_url, device_id):
    response = api_json(
        api_url, f"/api/devices/{device_id}", success_statuses=(0, 1)
    )
    device = response.get("device") or {}
    channels = []

    for channel_id, details in (device.get("devices") or {}).items():
        if int(details.get("ledChannels") or 0) > 0:
            channels.append(int(channel_id))

    if not channels:
        raise RuntimeError("no memory RGB channels found in OpenLinkHub device data")
    return sorted(channels)


def parse_channels(value):
    if not value:
        return None
    if value.strip().lower() in ("none", "off"):
        return []
    channels = []
    for item in value.split(","):
        item = item.strip()
        if item:
            channels.append(int(item))
    return channels


def unique_channels(*groups):
    seen = set()
    channels = []
    for group in groups:
        for channel_id in group:
            if channel_id not in seen:
                seen.add(channel_id)
                channels.append(channel_id)
    return channels


def set_rgb_profile(api_url, device_id, channel_id, profile):
    return api_json(
        api_url,
        "/api/color",
        {"deviceId": device_id, "channelId": channel_id, "profile": profile},
    )


def rgb_color(red, green, blue, temperature):
    return {
        "red": red,
        "green": green,
        "blue": blue,
        "temperature": temperature,
    }


def set_rgb_override(api_url, device_id, channel_id, enabled, speed):
    return api_json(
        api_url,
        "/api/color/setOverride",
        {
            "deviceId": device_id,
            "channelId": channel_id,
            "subDeviceId": 0,
            "enabled": enabled,
            "startColor": rgb_color(255, 0, 0, 20),
            "middleColor": rgb_color(255, 18, 0, 40),
            "endColor": rgb_color(255, 45, 0, 60),
            "speed": speed,
        },
    )


def apply_rgb_channels(api_url, device_id, channels, profile, override_enabled, speed):
    for channel_id in channels:
        set_rgb_override(api_url, device_id, channel_id, override_enabled, speed)
        set_rgb_profile(api_url, device_id, channel_id, profile)


def apply_rgb_state(args, rgb_channels, memory_channels, state):
    if args.no_rgb:
        return

    if state == "high":
        apply_rgb_channels(
            args.api_url,
            args.device_id,
            rgb_channels,
            args.high_rgb_profile,
            True,
            args.high_rgb_speed,
        )
        if not args.no_memory_rgb:
            apply_rgb_channels(
                args.api_url,
                args.memory_device_id,
                memory_channels,
                args.high_memory_rgb_profile,
                True,
                args.high_rgb_speed,
            )
        return

    apply_rgb_channels(
        args.api_url,
        args.device_id,
        rgb_channels,
        args.low_rgb_profile,
        False,
        args.high_rgb_speed,
    )
    if not args.no_memory_rgb:
        apply_rgb_channels(
            args.api_url,
            args.memory_device_id,
            memory_channels,
            args.low_memory_rgb_profile,
            False,
            args.high_rgb_speed,
        )


def choose_state(load_average, current, high_threshold, low_threshold):
    if load_average > high_threshold:
        return "high"
    if load_average < low_threshold:
        return "low"
    return current or "low"


def load_config(path, valid_keys):
    try:
        with Path(path).open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except OSError as exc:
        raise SystemExit(f"unable to read config file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in config file {path}: {exc}") from exc

    if not isinstance(config, dict):
        raise SystemExit(f"config file {path} must contain a JSON object")

    unknown_keys = sorted(set(config) - valid_keys)
    if unknown_keys:
        raise SystemExit(
            "unknown config option(s): " + ", ".join(unknown_keys)
        )
    return config


def parse_args(argv=None):
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--config", type=Path)
    config_args, _ = config_parser.parse_known_args(argv)

    parser = argparse.ArgumentParser(
        description="Switch an OpenLinkHub AIO LCD image based on system load."
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="JSON configuration file. Command-line options override its values.",
    )
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument(
        "--device-id",
        default=DEFAULT_DEVICE_ID,
        help="OpenLinkHub device ID containing the LCD (required unless set in config).",
    )
    parser.add_argument("--channel-id", type=int, default=DEFAULT_CHANNEL_ID)
    parser.add_argument(
        "--high-image",
        default="",
        help="Image/GIF shown when 1-minute load is above the high threshold.",
    )
    parser.add_argument(
        "--low-image",
        default="",
        help="Image/GIF shown when 1-minute load is below the low threshold.",
    )
    parser.add_argument("--high-threshold", type=float, default=8.0)
    parser.add_argument(
        "--low-threshold",
        type=float,
        default=8.0,
        help="Set lower than high-threshold for hysteresis.",
    )
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument(
        "--fan-channels",
        default="",
        help="Comma-separated fan channel ids. Defaults to auto-discovery.",
    )
    parser.add_argument(
        "--ring-channels",
        default="",
        help="Comma-separated LCD ring channel ids. Defaults to the LCD channel.",
    )
    parser.add_argument("--high-rgb-profile", default="spinner")
    parser.add_argument("--low-rgb-profile", default="rainbow")
    parser.add_argument(
        "--memory-device-id",
        default=DEFAULT_MEMORY_DEVICE_ID,
        help="OpenLinkHub memory RGB device ID; required unless --no-memory-rgb is set.",
    )
    parser.add_argument(
        "--memory-channels",
        default="",
        help="Comma-separated memory channel ids. Defaults to auto-discovery.",
    )
    parser.add_argument("--high-memory-rgb-profile", default="spinner")
    parser.add_argument("--low-memory-rgb-profile", default="rainbow")
    parser.add_argument("--high-rgb-speed", type=float, default=1.0)
    parser.add_argument("--no-rgb", action="store_true")
    parser.add_argument("--no-memory-rgb", action="store_true")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--verbose", action="store_true")

    if config_args.config:
        valid_keys = {
            action.dest
            for action in parser._actions
            if action.dest not in {argparse.SUPPRESS, "config", "help"}
        }
        parser.set_defaults(**load_config(config_args.config, valid_keys))

    return parser.parse_args(argv)


def main():
    args = parse_args()
    if args.low_threshold > args.high_threshold:
        raise SystemExit("--low-threshold must be <= --high-threshold")
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than zero")
    if not args.device_id:
        raise SystemExit("--device-id is required")
    if not args.high_image or not args.low_image:
        raise SystemExit("--high-image and --low-image are required")
    if not args.no_rgb and not args.no_memory_rgb and not args.memory_device_id:
        raise SystemExit(
            "--memory-device-id is required unless --no-memory-rgb is set"
        )

    high_path = Path(args.high_image)
    low_path = Path(args.low_image)
    for path in (high_path, low_path):
        if not path.is_file():
            raise SystemExit(f"missing image file: {path}")

    high_name = validate_image_name(high_path)
    low_name = validate_image_name(low_path)

    if not args.no_upload:
        for path in (high_path, low_path):
            if args.verbose:
                print(f"uploading {path}", flush=True)
            upload_image(args.api_url, path)

    set_lcd_mode(args.api_url, args.device_id, args.channel_id)
    fan_channels = []
    ring_channels = []
    rgb_channels = []
    memory_channels = []
    if not args.no_rgb:
        fan_channels = parse_channels(args.fan_channels)
        if fan_channels is None:
            fan_channels = discover_fan_channels(args.api_url, args.device_id)
        ring_channels = parse_channels(args.ring_channels)
        if ring_channels is None:
            ring_channels = [args.channel_id]
        rgb_channels = unique_channels(fan_channels, ring_channels)
        if not args.no_memory_rgb:
            memory_channels = parse_channels(args.memory_channels)
            if memory_channels is None:
                memory_channels = discover_memory_channels(
                    args.api_url, args.memory_device_id
                )
        if args.verbose:
            print(f"fan channels: {','.join(str(c) for c in fan_channels)}", flush=True)
            print(f"ring channels: {','.join(str(c) for c in ring_channels)}", flush=True)
            print(f"rgb channels: {','.join(str(c) for c in rgb_channels)}", flush=True)
            if not args.no_memory_rgb:
                print(
                    f"memory channels: {','.join(str(c) for c in memory_channels)}",
                    flush=True,
                )

    state = None
    while True:
        load1 = os.getloadavg()[0]
        next_state = choose_state(
            load1, state, args.high_threshold, args.low_threshold
        )

        if next_state != state:
            name = high_name if next_state == "high" else low_name
            set_lcd_image(args.api_url, args.device_id, args.channel_id, name)
            apply_rgb_state(args, rgb_channels, memory_channels, next_state)
            state = next_state
            print(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} load={load1:.2f} "
                f"state={state} image={name}",
                flush=True,
            )
        elif args.verbose:
            print(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} load={load1:.2f} "
                f"state={state}",
                flush=True,
            )

        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
