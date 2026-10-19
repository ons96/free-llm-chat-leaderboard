#!/usr/bin/env python3
"""Fetch the full LMArena (arena.ai) text leaderboard from the public page.

arena.ai/leaderboard/text embeds the leaderboard as a Next.js RSC payload.
No auth needed. The full list (hundreds of models) is stored so the merge step
can use arena ELO as an intelligence proxy + preference signal for as many
free models as possible. data/arena_scores.json remains the hand-curated
subset the user edits; this file is the auto-refreshed superset.

Writes: data/sources/arena_leaderboard.json

arena.ai now answers automated requests with a Cloudflare "Just a moment..."
challenge (HTTP 403), from CI runners and laptops alike. A blocked fetch keeps
the last known snapshot and ends successfully so one unreachable source cannot
fail the whole weekly build. Set ARENA_STRICT=1 to turn that into a hard error
for monitoring; see BLOCKED.md for what a real fix needs.
"""
import json
import os
import re
import sys
import time
import urllib.error
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


STRICT = os.environ.get("ARENA_STRICT", "").strip() == "1"


def previous_snapshot():
    if not OUT.exists():
        return None
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def skip_with_last_snapshot(reason):
    """Keep the previous file and let the build continue unless ARENA_STRICT=1."""
    if STRICT:
        print(f"ERROR: arena fetch failed ({reason}); ARENA_STRICT=1", file=sys.stderr)
        return 1
    prev = previous_snapshot()
    if prev is None:
        print(
            f"ERROR: arena fetch failed ({reason}) and no previous snapshot exists",
            file=sys.stderr,
        )
        return 1
    print(
        "WARNING: arena fetch failed ({reason}); keeping snapshot from {when} "
        "({count} entries)".format(
            reason=reason,
            when=prev.get("fetched_at", "unknown"),
            count=prev.get("count", 0),
        ),
        file=sys.stderr,
    )
    return 0


def main():
    try:
        html = fetch(URL)
    except urllib.error.HTTPError as e:
        return skip_with_last_snapshot(f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return skip_with_last_snapshot(str(e))
    entries = extract_entries(html)
    if not entries:
        return skip_with_last_snapshot("could not parse the RSC payload")
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
