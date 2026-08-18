#!/usr/bin/env python3
"""Fetch real-probe speed benchmark data from the public free-llm-benchmarking repo.

Source repo: https://github.com/ons96/free-llm-benchmarking (llm-speedrun data).
These CSVs contain measured TTFT/tokens-per-second for free providers, which we
use as the speed component of the chat score.

Writes: data/sources/benchmark_speed.json
"""
import csv
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sources" / "benchmark_speed.json"

BASE = "https://raw.githubusercontent.com/ons96/free-llm-benchmarking/main/data"
FILES = [
    ("all_providers_benchmark.csv", "probes"),
    ("leaderboard.csv", "leaderboard"),
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "free-llm-chat-leaderboard/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_csv(text: str):
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows


def main():
    records = {"probes": [], "leaderboard": []}
    ok = True
    for fname, target in FILES:
        try:
            text = fetch(f"{BASE}/{fname}")
            rows = parse_csv(text)
            records[target] = rows
            print(f"  {fname}: {len(rows)} rows")
        except Exception as e:
            ok = False
            print(f"  {fname}: FAILED ({e})")
    if not ok:
        print("Benchmark fetch partially failed; writing what we have", file=sys.stderr)

    # aggregate per (provider, model): median ttft, median tps from raw probes
    agg = {}
    for row in records["probes"]:
        provider = (row.get("provider") or "").strip()
        model = (row.get("model") or "").strip()
        if not provider or not model:
            continue
        key = (provider, model)
        d = agg.setdefault(key, {"ttft": [], "tps": []})
        for field, lst in (("ttft_s", d["ttft"]), ("tps", d["tps"])):
            try:
                v = float(row[field])
                if v > 0:
                    lst.append(v)
            except (KeyError, ValueError, TypeError):
                pass

    def median(xs):
        if not xs:
            return None
        xs = sorted(xs)
        n = len(xs)
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

    speed = []
    for (provider, model), d in agg.items():
        speed.append(
            {
                "provider": provider,
                "model": model,
                "ttft_s_median": median(d["ttft"]),
                "tps_median": median(d["tps"]),
                "samples": max(len(d["ttft"]), len(d["tps"])),
            }
        )
    speed.sort(key=lambda r: r["provider"])

    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_repo": "ons96/free-llm-benchmarking",
        "leaderboard_rows": records["leaderboard"],
        "per_model_speed": speed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    print(f"Wrote {OUT}: {len(speed)} (provider, model) speed records")


if __name__ == "__main__":
    sys.exit(main())
