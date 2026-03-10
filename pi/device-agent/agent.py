from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

GATEWAY_HEARTBEAT_URL = os.getenv("GATEWAY_HEARTBEAT_URL", "").strip()
DEVICE_ID = os.getenv("DEVICE_ID", "pi-unknown").strip()
DEVICE_TOKEN = os.getenv("GATEWAY_DEVICE_TOKEN", "").strip()
INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "60"))


def post_heartbeat() -> None:
    if not GATEWAY_HEARTBEAT_URL:
        return
    headers = {"Content-Type": "application/json"}
    if DEVICE_TOKEN:
        headers["Authorization"] = f"Bearer {DEVICE_TOKEN}"
    payload = {"device_id": DEVICE_ID, "timestamp": int(time.time())}
    req = urllib.request.Request(
        GATEWAY_HEARTBEAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15):
        return


def main() -> int:
    while True:
        try:
            post_heartbeat()
        except urllib.error.URLError:
            pass
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
