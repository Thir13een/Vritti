from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

GATEWAY_HEARTBEAT_URL = os.getenv("GATEWAY_HEARTBEAT_URL", "").strip()
DEVICE_ID = os.getenv("DEVICE_ID", "pi-unknown").strip()
DEVICE_TOKEN = os.getenv("GATEWAY_DEVICE_TOKEN", "").strip()
INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "60"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("device_agent")
_missing_heartbeat_url_logged = False


def post_heartbeat() -> None:
    global _missing_heartbeat_url_logged
    if not GATEWAY_HEARTBEAT_URL:
        if not _missing_heartbeat_url_logged:
            logger.info("heartbeat disabled because GATEWAY_HEARTBEAT_URL is not configured")
            _missing_heartbeat_url_logged = True
        return
    _missing_heartbeat_url_logged = False
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
        logger.debug("heartbeat sent", extra={"device_id": DEVICE_ID})
        return


def main() -> int:
    logger.info(
        "device agent started",
        extra={"device_id": DEVICE_ID, "interval_seconds": INTERVAL_SECONDS},
    )
    while True:
        try:
            post_heartbeat()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            logger.warning(
                "heartbeat request failed",
                extra={"device_id": DEVICE_ID, "status_code": exc.code, "body": body},
            )
        except urllib.error.URLError as exc:
            logger.warning(
                "heartbeat network error",
                extra={"device_id": DEVICE_ID, "error": str(exc)},
            )
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
