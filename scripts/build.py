#!/usr/bin/env python3
"""Full build pipeline: fetch live sources -> merge -> score -> models.json.

Run locally or in GitHub Actions:
    python3 scripts/build.py

Steps:
  1. fetch_arena.py      (arena.ai text leaderboard, no auth)
  2. fetch_aa.py         (Artificial Analysis: API if AA_API_KEY set, else RSC scrape)
  3. fetch_openrouter.py (OpenRouter :free models, no auth)
  4. fetch_benchmarks.py (free-llm-benchmarking speed probes, no auth)
  5. merge.py            (normalize + fuzzy match across sources)
  6. score.py            (quality gate + composite chat score -> data/models.json)

data/gateway_models.json is the gateway snapshot, refreshed by CI via the
restricted VPS_SSH_KEY deploy key before this script runs. To refresh it
manually from a local config mirror:
    python3 scripts/parse_gateway.py <dir-with-gateway-configs>
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

STEPS = ["fetch_arena.py", "fetch_aa.py", "fetch_openrouter.py",
         "fetch_benchmarks.py", "merge.py", "score.py"]


def main():
    failed = []
    for step in STEPS:
        print(f"\n=== {step} ===")
        r = subprocess.run([sys.executable, str(SCRIPTS / step)], cwd=ROOT)
        if r.returncode != 0:
            failed.append(step)
    if failed:
        print(f"\nFAILED steps: {failed}", file=sys.stderr)
        sys.exit(1)
    print("\nBuild complete: data/models.json is fresh.")


if __name__ == "__main__":
    main()
