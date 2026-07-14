#!/usr/bin/env python3
import argparse
import json
import math
import time
import urllib.request

DEFAULT_DEVICE_ID = "nvidiagpu0"
DEFAULT_API_URL = "http://127.0.0.1:27003"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Pulse the brightness of an OpenLinkHub device for testing."
    )
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument(
        "--period",
        type=float,
        default=5.0,
        help="Seconds for one complete 0 -> 100 -> 0 pulse (default: 5).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.05,
        help="Seconds between API requests (default: 0.05).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.period <= 0 or args.interval <= 0:
        raise SystemExit("--period and --interval must be greater than zero")

    url = args.api_url.rstrip("/") + "/api/brightness/gradual"
    while True:
        t = time.monotonic()
        brightness = round(
            (math.sin((t / args.period) * math.tau - math.pi / 2) + 1) * 50
        )
        payload = json.dumps(
            {"deviceId": args.device_id, "brightness": brightness}
        ).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=1) as response:
                result = json.loads(response.read())
            if result.get("status") != 1:
                print(f"brightness update failed: {result}")
        except Exception as exc:
            print(f"brightness update failed: {exc}")

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
