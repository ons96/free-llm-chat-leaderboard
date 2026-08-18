#!/usr/bin/env python3
"""Fetch OpenRouter model list and keep only :free models.

No auth needed for GET /api/v1/models.
Writes: data/sources/openrouter_free.json
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sources" / "openrouter_free.json"

URL = "https://openrouter.ai/api/v1/models"


def main():
    req = urllib.request.Request(
        URL,
        headers={"User-Agent": "free-llm-chat-leaderboard/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())

    all_models = data.get("data", [])
    free = []
    for m in all_models:
        if m.get("id", "").endswith(":free"):
            free.append(
                {
                    "id": m["id"],
                    "name": m.get("name"),
                    "context_length": m.get("context_length"),
                    "pricing": m.get("pricing"),
                    "top_provider": m.get("top_provider"),
                    "created": m.get("created"),
                    "description": m.get("description"),
                }
            )
    free.sort(key=lambda m: m["id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_models": len(all_models),
        "free_models_count": len(free),
        "models": free,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    print(f"Wrote {OUT}: {len(free)} free models (of {len(all_models)} total)")


if __name__ == "__main__":
    sys.exit(main())
