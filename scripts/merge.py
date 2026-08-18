#!/usr/bin/env python3
"""Merge all sources into one normalized row set (before scoring).

Sources:
  - data/gateway_models.json        (committed snapshot of VPS-40 config)
  - data/sources/aa_models.json     (Artificial Analysis, API or RSC scrape)
  - data/sources/openrouter_free.json (OpenRouter :free models)
  - data/sources/benchmark_speed.json (real-probe TTFT/TPS)
  - data/arena_scores.json          (hand-maintained LMArena scores)
  - data/free_chat_uis.json         (hand-maintained free chat apps)

Output: data/models_raw.json (merged, unranked, with match_confidence)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# --------------------------------------------------------------------------
# Name normalization / fuzzy matching
# --------------------------------------------------------------------------

# explicit aliases: (canonical family, [source id patterns])
ALIASES = [
    # (family, [patterns])
    ("gpt-5", ["gpt-5", "openai/gpt-5"]),
    ("gpt-5-mini", ["gpt-5-mini", "openai/gpt-5-mini"]),
    ("gpt-5.5", ["gpt-5.5", "openai/gpt-5.5"]),
    ("gpt-5.5-mini", ["gpt-5.5-mini", "openai/gpt-5.5-mini"]),
    ("gpt-5.6", ["gpt-5.6", "openai/gpt-5.6"]),
    ("gpt-4o", ["gpt-4o", "openai/gpt-4o"]),
    ("gpt-4o-mini", ["gpt-4o-mini", "openai/gpt-4o-mini"]),
    ("gpt-4.1", ["gpt-4.1", "openai/gpt-4.1"]),
    ("gpt-4.1-mini", ["gpt-4.1-mini", "openai/gpt-4.1-mini"]),
    ("o3-mini", ["o3-mini", "openai/o3-mini"]),
    ("o4-mini", ["o4-mini", "openai/o4-mini"]),
    ("gpt-oss-120b", ["gpt-oss-120b", "openai/gpt-oss-120b"]),
    ("gpt-oss-20b", ["gpt-oss-20b", "openai/gpt-oss-20b"]),
    ("claude-3.5-haiku", ["claude-3.5-haiku", "anthropic/claude-3.5-haiku"]),
    ("claude-haiku-4-5", ["claude-haiku-4-5", "anthropic/claude-haiku-4-5"]),
    ("claude-sonnet-4-5", ["claude-sonnet-4-5", "anthropic/claude-sonnet-4-5"]),
    ("gemini-2.5-flash", ["gemini-2.5-flash", "google/gemini-2.5-flash"]),
    ("gemini-2.5-pro", ["gemini-2.5-pro", "google/gemini-2.5-pro"]),
    ("gemini-3-flash", ["gemini-3-flash", "google/gemini-3-flash"]),
    ("gemini-3-pro", ["gemini-3-pro", "google/gemini-3-pro"]),
    ("llama-3.3-70b", ["llama-3.3-70b", "meta-llama/llama-3.3-70b",
                        "llama-3.3-70b-versatile", "llama-3.3-70b-instruct"]),
    ("llama-3.1-8b", ["llama-3.1-8b", "meta-llama/llama-3.1-8b",
                       "llama-3.1-8b-instant", "llama-3.1-8b-instruct"]),
    ("llama-3.1-70b", ["llama-3.1-70b", "meta-llama/llama-3.1-70b",
                        "llama-3.1-70b-instruct"]),
    ("llama-3.1-405b", ["llama-3.1-405b", "meta-llama/llama-3.1-405b",
                         "llama-3.1-405b-instruct"]),
    ("llama-3-8b", ["llama-3-8b", "meta-llama/llama-3-8b"]),
    ("gemma-3-27b", ["gemma-3-27b", "gemma-3-27b-it", "google/gemma-3-27b"]),
    ("gemma-2-27b", ["gemma-2-27b", "gemma-2-27b-it", "google/gemma-2-27b"]),
    ("gemma-2-9b", ["gemma-2-9b", "gemma-2-9b-it", "google/gemma-2-9b"]),
    ("llama-3.1-405b", ["llama-3.1-405b", "meta-llama/llama-3.1-405b"]),
    ("deepseek-v3.1", ["deepseek-v3.1", "deepseek/deepseek-v3.1"]),
    ("deepseek-r1", ["deepseek-r1", "deepseek/deepseek-r1"]),
    ("deepseek-v4", ["deepseek-v4", "deepseek/deepseek-v4"]),
    ("qwen3-235b", ["qwen-3-235b-a22b", "qwen3-235b", "qwen/qwen3-235b"]),
    ("qwen3-32b", ["qwen-3-32b", "qwen3-32b", "qwen/qwen3-32b"]),
    ("qwen3-coder", ["qwen3-coder", "qwen/qwen3-coder"]),
    ("kimi-k2", ["kimi-k2", "moonshotai/kimi-k2"]),
    ("kimi-k2.5", ["kimi-k2.5", "moonshotai/kimi-k2.5"]),
    ("glm-4.5", ["glm-4.5", "zhipu/glm-4.5"]),
    ("glm-4.6", ["glm-4.6", "zhipu/glm-4.6"]),
    ("glm-5", ["glm-5", "zhipu/glm-5"]),
    ("glm-4.7", ["glm-4.7", "zhipu/glm-4.7"]),
    ("grok-3", ["grok-3", "x-ai/grok-3"]),
    ("grok-4", ["grok-4", "x-ai/grok-4"]),
    ("mistral-small", ["mistral-small", "mistralai/mistral-small"]),
    ("mistral-medium", ["mistral-medium", "mistralai/mistral-medium"]),
    ("gemma-3-27b", ["gemma-3-27b", "google/gemma-3-27b"]),
    ("phi-4", ["phi-4", "microsoft/phi-4"]),
    ("command-a", ["command-a", "cohere/command-a"]),
    ("allam-2-7b", ["allam-2-7b", "allam/2-7b"]),
    ("nemotron-70b", ["llama-3.1-nemotron-70b", "nvidia/llama-3.1-nemotron-70b"]),
    ("nemotron-4-340b", ["nemotron-4-340b", "nvidia/nemotron-4-340b"]),
]


def strip_noise(model_id: str) -> str:
    """Lowercase, drop slash-prefixed provider names, :free suffix, noise."""
    s = model_id.lower().strip()
    # Provider prefixes in gateway ids use a slash (e.g. 'opc/deepseek-v4-flash-free').
    # Hyphen-prefixed segments (e.g. 'glm-4.5-flash', 'gemini-3-flash') are part of
    # the real model name and must be kept.
    s = s.split("/")[-1]
    s = s.replace(":free", "")
    s = s.replace(":fp8", "")
    s = s.replace("_", "-")
    return s


def normalize_family(model_id: str) -> str:
    """Map a raw model id to a canonical family name."""
    s = strip_noise(model_id)
    for family, patterns in ALIASES:
        for pat in patterns:
            p = strip_noise(pat)
            if s == p or s.startswith(p + "-") or s.startswith(p + "."):
                return family
    # arena-specific suffixes that don't change the model family
    s = re.sub(r"-(text|chat)$", "", s)
    # training/inference suffixes that don't change the family
    s = re.sub(r"-(instruct|it|bf16|fp8|non-thinking|no-thinking)$", "", s)
    # date-stamped variants collapse to base family (e.g. qwen3-235b-a22b-instruct-2507)
    s = re.sub(r"-(\d{4,8})$", "", s)
    return s


def match_confidence(family: str, raw: str) -> str:
    """Heuristic confidence for a normalization."""
    stripped = strip_noise(raw)
    if family in stripped or stripped in family:
        return "high"
    return "medium"


# --------------------------------------------------------------------------
# Source loaders
# --------------------------------------------------------------------------

def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def rows_from_gateway():
    d = load_json(DATA / "gateway_models.json", {})
    rows = []
    for m in d.get("models", []):
        if m.get("blocked"):
            continue
        rows.append(
            {
                "model_id": m["model_id"],
                "family": normalize_family(m["model_id"]),
                "provider_id": m["provider_id"],
                "provider_name": m["provider_name"],
                "context": m.get("context"),
                "tps": m.get("tps"),
                "virtual_models": m.get("virtual_models", []),
                "pinned": m.get("pinned", False),
                "notes": m.get("notes", ""),
                "source": "gateway",
                "raw": m["model_id"],
            }
        )
    return rows


def rows_from_openrouter():
    d = load_json(DATA / "sources" / "openrouter_free.json", {})
    rows = []
    for m in d.get("models", []):
        mid = m["id"]
        family = normalize_family(mid)
        ctx = m.get("context_length")
        rows.append(
            {
                "model_id": mid,
                "family": family,
                "provider_id": None,
                "provider_name": "OpenRouter",
                "context": ctx,
                "tps": None,
                "virtual_models": [],
                "pinned": False,
                "notes": "",
                "source": "openrouter",
                "raw": mid,
            }
        )
    return rows


def rows_from_aa():
    d = load_json(DATA / "sources" / "aa_models.json", {})
    rows = []
    for m in d.get("models", []):
        slug = m.get("slug") or m.get("name") or ""
        family = normalize_family(slug)
        omni = m.get("omniscienceBreakdown") or {}
        speed = m.get("timescaleData") or {}
        rows.append(
            {
                "model_id": slug,
                "family": family,
                "provider_id": None,
                "provider_name": "Artificial Analysis",
                "context": m.get("contextWindowTokens"),
                "tps": speed.get("outputTokensPerSecond"),
                "intelligence": m.get("intelligenceIndex"),
                "grounding_accuracy": omni.get("accuracy"),
                "hallucination_rate": omni.get("hallucinationRate"),
                "release_date": m.get("releaseDate"),
                "price_input_1m": m.get("price1mInputTokens"),
                "price_output_1m": m.get("price1mOutputTokens"),
                "source": "artificial_analysis",
                "raw": slug,
            }
        )
    return rows


def rows_from_arena():
    """Arena scores: hand-curated arena_scores.json first, then the full
    auto-fetched arena_leaderboard.json (superset)."""
    rows = []
    seen = set()
    for d in (load_json(DATA / "arena_scores.json", {}),
              load_json(DATA / "sources" / "arena_leaderboard.json", {})):
        entries = d.get("models") or d.get("entries") or []
        for m in entries:
            ident = m.get("display_name") or m.get("model_key") or m.get("id", "")
            if not ident or ident in seen:
                continue
            seen.add(ident)
            ctx = m.get("context_length") or m.get("context")
            rows.append(
                {
                    "model_id": ident,
                    "family": normalize_family(ident),
                    "arena_score": m.get("arena_score") or m.get("rating"),
                    "arena_rank": m.get("rank"),
                    "arena_url": m.get("url") or "https://arena.ai/leaderboard/text",
                    "context": ctx,
                    "source": "arena",
                    "raw": ident,
                }
            )
    return rows


def rows_from_chat_uis():
    d = load_json(DATA / "free_chat_uis.json", {})
    rows = []
    for m in d.get("models", []):
        rows.append(
            {
                "model_id": m.get("id", ""),
                "family": normalize_family(m.get("id", "")),
                "ui_name": m.get("ui"),
                "ui_url": m.get("url"),
                "ui_limits": m.get("limits"),
                "source": "chat_ui",
                "raw": m.get("id", ""),
            }
        )
    return rows


def rows_from_benchmark():
    d = load_json(DATA / "sources" / "benchmark_speed.json", {})
    by_provider = {}
    for rec in d.get("per_model_speed", []):
        by_provider.setdefault((rec["provider"], rec["model"]), rec)
    # leaderboard rows (ranked, real probes) also carry TTFT/TPS
    for rec in d.get("leaderboard_rows", []):
        provider = (rec.get("provider") or "").strip()
        model = (rec.get("model") or "").strip()
        if not provider or not model:
            continue
        entry = by_provider.setdefault((provider, model), {})
        for src_key, dst_key in (("TTFT_sec", "ttft_s_median"), ("TPS", "tps_median")):
            try:
                v = float(rec[src_key])
                if v > 0 and dst_key not in entry:
                    entry[dst_key] = v
            except (KeyError, ValueError, TypeError):
                pass
    return by_provider


# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------

def main():
    gateway = rows_from_gateway()
    or_rows = rows_from_openrouter()
    aa_rows = rows_from_aa()
    arena_rows = rows_from_arena()
    ui_rows = rows_from_chat_uis()
    bench = rows_from_benchmark()

    merged = {}  # family -> row
    order = []

    def upsert(family, row):
        if family not in merged:
            merged[family] = {"family": family, "sources": [], "match_confidence": "high"}
            order.append(family)
        target = merged[family]
        src = row["source"]
        if src not in target["sources"]:
            target["sources"].append(src)
        # fill fields by precedence: gateway > openrouter > aa > arena > chat_ui
        prec = {"gateway": 0, "openrouter": 1, "artificial_analysis": 2, "arena": 3, "chat_ui": 4}
        if prec[src] <= prec.get(target.get("_prec_source"), 99):
            target["_prec_source"] = src
            target["_prec_row"] = row
            # carry over common fields
            for k in ("model_id", "provider_id", "provider_name", "tps"):
                if row.get(k) is not None:
                    target[k] = row[k]
            target["match_confidence"] = match_confidence(family, row.get("raw", family))
        # context: prefer the LARGEST value seen (verified sources like AA/arena
        # report real context; gateway static configs are sometimes wrong/low)
        if row.get("context") is not None:
            cur = target.get("context")
            if cur is None or int(row["context"]) > int(cur):
                target["context"] = row["context"]
        # merge metadata lists
        for k in ("virtual_models", "arena_score", "intelligence", "grounding_accuracy",
                  "hallucination_rate", "release_date", "price_input_1m", "price_output_1m",
                  "ui_name", "ui_url", "ui_limits", "notes", "pinned"):
            v = row.get(k)
            if v is not None and k not in target:
                target[k] = v
        # benchmark speed attach
        if src == "gateway":
            b = bench.get((row["provider_id"], row["model_id"]))
            if b:
                target["bench_ttft_s"] = b.get("ttft_s_median")
                target["bench_tps"] = b.get("tps_median")
                target["bench_samples"] = b.get("samples")

    for r in gateway:
        upsert(r["family"], r)
    for r in or_rows:
        upsert(r["family"], r)
    for r in aa_rows:
        upsert(r["family"], r)
    for r in arena_rows:
        upsert(r["family"], r)
    for r in ui_rows:
        upsert(r["family"], r)

    # finalize
    out = []
    for fam in order:
        rec = merged[fam]
        rec.pop("_prec_row", None)
        rec.pop("_prec_source", None)
        out.append(rec)
    out.sort(key=lambda r: (r["family"]))

    payload = {
        "generated_at": None,
        "count": len(out),
        "models": out,
    }
    out_path = DATA / "models_raw.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Wrote {out_path}: {len(out)} merged model families")
    for fam in out[:10]:
        print("  -", fam["family"], "| sources:", ",".join(fam["sources"]))


if __name__ == "__main__":
    sys.exit(main())
