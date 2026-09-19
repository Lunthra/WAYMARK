"""
WAYMARK M20.5.1 backend bridge smoke test.
Read-only. Does not modify MAL or Serializd.
"""

from __future__ import annotations

import json
import urllib.request


BASE = "http://127.0.0.1:8765"


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post(action: str, payload: dict):
    body = json.dumps({"action": action, "payload": payload}).encode("utf-8")
    request = urllib.request.Request(
        BASE + "/api/invoke",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    health = get("/health")
    assert health["ok"] is True
    print("[PASS] /health")

    status = get("/api/status")
    assert status["ok"] is True
    assert status["result"]["phase"] == "M20.5.1"
    assert status["result"]["read_only"] is True
    print("[PASS] /api/status")

    # Non-anime movie intentionally routes to no current service.
    result = post(
        "search",
        {
            "query": "Example",
            "is_anime": False,
            "media_type": "movie",
        },
    )
    assert result["ok"] is True
    assert result["result"]["routing"]["mal"] is False
    assert result["result"]["routing"]["serializd"] is False
    print("[PASS] structured search routing")

    print("M20.5.1 BACKEND BRIDGE CONTRACT PASSED")


if __name__ == "__main__":
    main()
