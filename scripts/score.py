#!/usr/bin/env python3
"""Score merged models: quality gate + composite chat score.

Methodology (documented in README):
  - Intelligence signal: AA intelligenceIndex if present, else arena ELO mapped
    to 0-100. Models with NO intelligence signal are unverified -> below threshold.
  - Quality gate: bottom quartile (25th percentile) of intelligence is excluded
    from the main ranking and shown in a collapsed "below threshold" section.
  - Composite (percentile-normalized 0-100):
        intelligence 0.30
        grounding    0.25   (AA omniscience accuracy; falls back to intelligence
                             percentile when no hallucination metric exists)
        speed        0.25   (benchmark TPS -> gateway tps -> AA output speed)
        arena        0.10   (LMArena preference score)
        context      0.05
        recency      0.05
  - Missing non-intelligence metrics score 0 for that component (unknown = no
    credit), except grounding which always falls back to intelligence.

Reads: data/models_raw.json
Writes: data/models.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

WEIGHTS = {
    "intelligence": 0.30,
    "grounding": 0.25,
    "speed": 0.25,
    "arena": 0.10,
    "context": 0.05,
    "recency": 0.05,
}
GATE_PERCENTILE = 0.25  # bottom quartile excluded from main ranking

NOW = datetime.now(timezone.utc)


def percentile_rank(values, v):
    """Rank of v as a 0-100 percentile among values (higher = better)."""
    if v is None or not values:
        return 0.0
    below = sum(1 for x in values if x < v)
    return 100.0 * below / len(values)


def intel_signal(m):
    """Return an intelligence signal (higher better) or None."""
    if m.get("intelligence") is not None:
        return float(m["intelligence"])
    if m.get("arena_score") is not None:
        # arena ELO ~1400-1510; map to ~0-100
        return (float(m["arena_score"]) - 1350.0) * (100.0 / 160.0)
    return None


def speed_signal(m):
    """Return a speed signal (tokens/sec, higher better) or None."""
    for k in ("bench_tps", "tps"):
        v = m.get(k)
        if v:
            return float(v)
    return None


def recency_days(m):
    rd = m.get("release_date")
    if not rd:
        return None
    try:
        dt = datetime.fromisoformat(str(rd).replace("Z", "+00:00"))
        return max(0, (NOW - dt).days)
    except Exception:
        return None


def main():
    raw = json.load(open(DATA / "models_raw.json", encoding="utf-8"))
    models = raw["models"]

    # ---- gather signals across the dataset ----
    intel_vals = [intel_signal(m) for m in models]
    intel_vals = [v for v in intel_vals if v is not None]
    speed_vals = [speed_signal(m) for m in models]
    speed_vals = [v for v in speed_vals if v is not None]
    ctx_vals = [float(m["context"]) for m in models if m.get("context")]
    arena_vals = [float(m["arena_score"]) for m in models if m.get("arena_score")]
    # grounding: omniscience accuracy (0-1) higher better
    ground_vals = [float(m["grounding_accuracy"]) for m in models
                   if m.get("grounding_accuracy") is not None]
    recency_vals = [d for d in (recency_days(m) for m in models) if d is not None]

    rows = []
    for m in models:
        # Only free-access models belong on a free leaderboard. AA-only rows are
        # benchmark reference, not something the user can actually use for free.
        has_free_path = bool(m.get("provider_name")) or "openrouter" in m.get("sources", []) or "chat_ui" in m.get("sources", [])
        if not has_free_path:
            continue
        intel = intel_signal(m)
        if intel is None:
            intel_pct = 0.0
            unverified = True
        else:
            intel_pct = percentile_rank(intel_vals, intel)
            unverified = False

        # grounding: omniscience accuracy if available, else intelligence proxy
        if m.get("grounding_accuracy") is not None:
            ground_pct = percentile_rank(ground_vals, float(m["grounding_accuracy"]))
            grounding_src = "omniscience_accuracy"
        else:
            ground_pct = intel_pct  # user-specified proxy
            grounding_src = "intelligence_proxy"

        sp = speed_signal(m)
        speed_pct = percentile_rank(speed_vals, sp)

        arena_pct = percentile_rank(arena_vals, m.get("arena_score"))

        ctx = m.get("context")
        ctx_pct = percentile_rank(ctx_vals, float(ctx) if ctx else None)

        rdays = recency_days(m)
        # recency: newer is better; invert day-rank
        if rdays is None or not recency_vals:
            rec_pct = 0.0
        else:
            # percentile of "newer than" = 100 - percentile of days
            below = sum(1 for d in recency_vals if d < rdays)
            rec_pct = 100.0 * (1.0 - below / len(recency_vals))

        chat = (
            WEIGHTS["intelligence"] * intel_pct
            + WEIGHTS["grounding"] * ground_pct
            + WEIGHTS["speed"] * speed_pct
            + WEIGHTS["arena"] * arena_pct
            + WEIGHTS["context"] * ctx_pct
            + WEIGHTS["recency"] * rec_pct
        )

        below_threshold = unverified or intel_pct < GATE_PERCENTILE * 100.0

        rows.append(
            {
                "id": m["family"],
                "name": display_name(m),
                "family": m["family"],
                "providers": providers_list(m),
                "free_via": free_via_list(m),
                "sources": m["sources"],
                "chat_score": round(chat, 1),
                "intelligence": round(intel_pct, 1),
                "grounding": round(ground_pct, 1),
                "grounding_source": grounding_src,
                "speed": round(speed_pct, 1),
                "speed_tps": round(sp, 1) if sp else None,
                "latency_ms": latency_ms(m),
                "context_window": ctx,
                "arena_score": m.get("arena_score"),
                "recency_days": rdays,
                "reliability_notes": reliability_notes(m),
                "match_confidence": m.get("match_confidence", "high"),
                "below_threshold": bool(below_threshold),
                "unverified": bool(unverified),
                "last_updated": NOW.strftime("%Y-%m-%d"),
            }
        )

    rows.sort(key=lambda r: r["chat_score"], reverse=True)
    # assign ranks
    for i, r in enumerate(rows, 1):
        r["rank"] = i if not r["below_threshold"] else None

    payload = {
        "generated_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(rows),
        "scoring": {
            "weights": WEIGHTS,
            "gate_percentile": GATE_PERCENTILE,
            "notes": (
                "Quality is a gate, not a weight. Bottom-quartile intelligence "
                "or unverified models are excluded from the main ranking."
            ),
        },
        "models": rows,
    }
    out = DATA / "models.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    ranked = [r for r in rows if not r["below_threshold"]]
    below = [r for r in rows if r["below_threshold"]]
    print(f"Wrote {out}: {len(rows)} models "
          f"({len(ranked)} ranked, {len(below)} below threshold)")
    print("Top 10:")
    for r in ranked[:10]:
        print(f"  #{r['rank']:>3} {r['name']:<28} chat={r['chat_score']:>5.1f} "
              f"intel={r['intelligence']:>5.1f} speed={r['speed']:>5.1f} "
              f"ctx={r['context_window']}")


BRAND_UPPER = {"gpt": "GPT", "o1": "o1", "o3": "o3", "o4": "o4", "glm": "GLM",
               "kimi": "Kimi", "qwen": "Qwen", "allam": "Allam", "phi": "Phi",
               "gemini": "Gemini", "grok": "Grok", "claude": "Claude",
               "deepseek": "DeepSeek", "llama": "Llama", "gemma": "Gemma",
               "mistral": "Mistral", "nemotron": "Nemotron", "muse": "Muse"}


def display_name(m):
    fam = m["family"]
    parts = fam.split("-")
    brand = BRAND_UPPER.get(parts[0], parts[0].title())
    rest = " ".join(p.title() for p in parts[1:])
    return (brand + " " + rest).strip()


def providers_list(m):
    provs = []
    if m.get("provider_name"):
        provs.append(m["provider_name"])
    if "openrouter" in m["sources"]:
        provs.append("OpenRouter")
    if "chat_ui" in m["sources"]:
        provs.append(m.get("ui_name", "Chat app"))
    if "artificial_analysis" in m["sources"]:
        provs.append("Artificial Analysis")
    return list(dict.fromkeys(provs))


def free_via_list(m):
    via = []
    if m.get("provider_name"):
        via.append("gateway")
    if "openrouter" in m["sources"]:
        via.append("openrouter-api")
    if "chat_ui" in m["sources"]:
        via.append("chat-ui")
    if "artificial_analysis" in m["sources"]:
        via.append("aa-benchmark")
    return via


def latency_ms(m):
    tps = m.get("bench_tps") or m.get("tps")
    if tps:
        # rough time-to-first-token estimate from tps (very rough; real TTFT
        # would come from benchmark ttft_s)
        ttft = m.get("bench_ttft_s")
        if ttft:
            return round(float(ttft) * 1000)
    return None


def reliability_notes(m):
    notes = []
    if m.get("virtual_models"):
        notes.append("served via gateway virtual model: " + ", ".join(m["virtual_models"]))
    if m.get("pinned"):
        notes.append("pinned chain head (actively maintained)")
    if m.get("notes"):
        notes.append(str(m["notes"]))
    if m.get("ui_limits"):
        notes.append("chat UI: " + str(m["ui_limits"]))
    if m.get("match_confidence") == "medium":
        notes.append("name match across sources is uncertain")
    return notes


if __name__ == "__main__":
    sys.exit(main())
