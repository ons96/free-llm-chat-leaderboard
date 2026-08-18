#!/usr/bin/env python3
"""Fetch Artificial Analysis language-model data.

Primary path: AA Data API v2 (needs AA_API_KEY env var; free tier).
Fallback path: parse the public https://artificialanalysis.ai/models page
(Next.js RSC payload) — no auth required. The fallback is what keeps this
working in GitHub Actions without any secrets.

Writes: data/sources/aa_models.json
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sources" / "aa_models.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------- API path
def fetch_api():
    """Use the official AA Data API v2. Requires AA_API_KEY."""
    key = os.environ.get("AA_API_KEY", "").strip()
    if not key:
        return None
    url = "https://artificialanalysis.ai/api/v2/language/models"
    req = urllib.request.Request(url, headers={**HEADERS, "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        print("AA API path OK")
        return data
    except Exception as e:
        print(f"AA API failed ({e}); falling back to RSC scrape")
        return None


# ------------------------------------------------------------- RSC scrape path
def extract_rsc_pushes(html: str):
    pushes = []
    pattern = re.compile(r'self\.__next_f\.push\(\[.*?,\s*(".*?")\]\s*\)', re.DOTALL)
    for m in pattern.finditer(html):
        try:
            pushes.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    return pushes


def find_model_arrays(combined: str, key: str):
    """Yield arrays found under `key` whose elements look like model records."""
    search_from = 0
    while True:
        idx = combined.find(f'"{key}"', search_from)
        if idx == -1:
            return
        start = idx + len(f'"{key}"')
        while start < len(combined) and combined[start] not in "[{":
            start += 1
        if start >= len(combined) or combined[start] != "[":
            search_from = idx + 1
            continue
        depth, in_str, esc, i = 0, False, False, start
        while i < len(combined):
            ch = combined[i]
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
                        yield json.loads(combined[start : i + 1])
                        search_from = i + 1
                        break
            i += 1
        else:
            return


def scrape_rsc():
    html = fetch("https://artificialanalysis.ai/models")
    pushes = extract_rsc_pushes(html)
    if not pushes:
        raise RuntimeError("No RSC push data found on /models page")
    combined = "\n".join(pushes)

    flat = []
    # The /models page embeds the model table under "initialModels" (29 top
    # models). Fall back to scanning any "models" array with real records.
    for key in ("initialModels", "models"):
        for arr in find_model_arrays(combined, key):
            if not isinstance(arr, list):
                continue
            for m in arr:
                if isinstance(m, dict) and "slug" in m and "intelligenceIndex" in m:
                    flat.append(m)
            if flat:
                break
        if flat:
            break
    if not flat:
        raise RuntimeError("Could not locate model records in RSC payload")
    print(f"AA RSC scrape OK: {len(flat)} models from /models page")
    return flat


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = fetch_api()
    source = "api"
    if data is None:
        data = scrape_rsc()
        source = "rsc_scrape"

    payload = {
        "source": source,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_note": (
            "AA_API_KEY env var absent -> used public-page RSC scrape fallback"
            if source == "rsc_scrape"
            else "AA Data API v2"
        ),
        "models": data,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    print(f"Wrote {OUT} ({len(data)} models, source={source})")


if __name__ == "__main__":
    sys.exit(main())
