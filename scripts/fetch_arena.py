#!/usr/bin/env python3
"""Fetch the full LMArena (arena.ai) text leaderboard from the public page.

arena.ai/leaderboard/text embeds the leaderboard as a Next.js RSC payload.
No auth needed. The full list (hundreds of models) is stored so the merge step
can use arena ELO as an intelligence proxy + preference signal for as many
free models as possible. data/arena_scores.json remains the hand-curated
subset the user edits; this file is the auto-refreshed superset.

Writes: data/sources/arena_leaderboard.json
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sources" / "arena_leaderboard.json"

URL = "https://arena.ai/leaderboard/text"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_entries(html):
    pushes = []
    for m in re.finditer(r'self\.__next_f\.push\(\[.*?,\s*(".*?")\]\s*\)', html, re.DOTALL):
        try:
            pushes.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    combined = "\n".join(pushes)
    i = combined.find('"leaderboard"')
    idx = combined.find('"entries"', i)
    if idx == -1:
        return None
    arr_start = combined.find("[", idx)
    depth, in_str, esc, j = 0, False, False, arr_start
    while j < len(combined):
        ch = combined[j]
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"' and not in_str:
            in_str = True
        elif ch == '"' and in_str:
            in_str = False
        elif not in_str:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return json.loads(combined[arr_start : j + 1])
        j += 1
    return None


def main():
    html = fetch(URL)
    entries = extract_entries(html)
    if not entries:
        print("ERROR: could not parse arena leaderboard", file=sys.stderr)
        sys.exit(1)
    out = [
        {
            "model_key": e.get("modelKey"),
            "display_name": e.get("modelDisplayName"),
            "rank": e.get("rank"),
            "arena_score": round(e.get("rating") or 0),
            "votes": e.get("votes"),
            "context_length": e.get("contextLength"),
            "organization": e.get("modelOrganization"),
        }
        for e in entries
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_url": URL,
        "count": len(out),
        "entries": out,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    print(f"Wrote {OUT}: {len(out)} arena entries")


if __name__ == "__main__":
    sys.exit(main())
