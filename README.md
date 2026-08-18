# Free LLM Chat Leaderboard

A sortable static table that ranks **free LLMs/chatbots for general
question-asking** — reasoning quality, factual reliability, and fast responses.
Deployed on GitHub Pages, zero build step, personal reference only. It is
**not** for gateway routing logic and **not** for coding/agentic model
selection (separate profile).

Live: https://ons96.github.io/free-llm-chat-leaderboard/

## What it does

- Merges several free data sources into `data/models.json` (one row per model,
  normalized fields, a `sources` array).
- Applies a **quality gate** then computes a **composite chat score**.
- Renders a sortable, dark, mobile-readable table. Default sort: composite
  chat score, best first. Models below the quality threshold are shown in a
  collapsed section.

## Data sources (priority order)

| # | Source | Access | Notes |
|---|--------|--------|-------|
| 1 | **VPS-40 gateway config** (`LLM-API-Key-Proxy`) | pushed weekly by a cron on VPS-40 itself (no secrets needed) | 84 free-tier providers, 586 model records, virtual-model chains, dead-provider flags. Tagged `source: gateway`. |
| 2 | **Artificial Analysis** | public page RSC scrape (no auth); official Data API v2 if `AA_API_KEY` is set | `intelligenceIndex`, `omniscience` accuracy/hallucination-rate, context, prices for top ~29 models. |
| 3 | **OpenRouter** models API | no auth | IDs ending in `:free` (currently 16). |
| 4 | **Hand-maintained JSONs** | `data/arena_scores.json`, `data/free_chat_uis.json` | See "Updating hand-maintained data". |
| 5 | **free-llm-benchmarking** (real-probe speed) | public repo CSVs | TTFT / tokens-per-sec for free providers (mostly aggregators; used where it matches). |

Cadence: a cron on VPS-40 pushes the gateway snapshot (Mon 05:30 UTC), then
the GitHub Action refreshes all other sources (AA, OpenRouter, arena,
benchmarks) weekly (Mon 06:00 UTC) plus on manual dispatch, merges everything
into `models.json` and commits; Pages auto-deploys. No secrets are involved
anywhere in the gateway refresh — the VPS owns its config and pushes it.

## Scoring methodology

**Quality is a gate, not a weight.** A fast model that gives wrong answers is
worthless, so intelligence is a hard floor.

1. **Intelligence signal** — Artificial Analysis `intelligenceIndex` when
   available; otherwise arena.ai ELO mapped to 0–100. Models with **no**
   intelligence signal are treated as unverified and go to the below-threshold
   section.
2. **Hard floor** — the bottom quartile (25th percentile) of intelligence is
   excluded from the main ranking and shown in the collapsed "below threshold"
   section.
3. **Composite chat score** (each metric percentile-normalized to 0–100):

   | Component | Weight | Source |
   |-----------|--------|--------|
   | Intelligence | 0.30 | AA index or arena-ELO mapping |
   | Grounding / reliability | 0.25 | AA omniscience accuracy; falls back to intelligence percentile as proxy |
   | Speed | 0.25 | gateway-provided tps → real-probe benchmark TPS |
   | Arena preference | 0.10 | LMArena (arena.ai) text ELO |
   | Context window | 0.05 | largest context across sources |
   | Recency bonus | 0.05 | release date (newer = better) |

   Missing non-intelligence metrics score 0 for that component (unknown = no
   credit). Weights are a starting point and documented here for easy review.

4. Each row carries a `reliability_notes` array sourced from the gateway
   config (virtual-model chain membership, pinned chain heads, dead-provider
   flags, uncertain name matches, chat-UI limits).

## Updating hand-maintained data

- **`data/arena_scores.json`** — the hand-curated top-60 arena entries (used
  as the arena signal). The pipeline also auto-fetches the full ~390-model
  arena list into `data/sources/arena_leaderboard.json`; the curated file
  takes precedence. To refresh the curated file, re-scrape
  https://arena.ai/leaderboard/text and update entries (or just run the
  pipeline — the auto list covers it).
- **`data/free_chat_uis.json`** — models free only via consumer chat apps
  (ChatGPT Free, Gemini app, Le Chat, etc.). Edit URLs/limits as they change.
- **`data/gateway_models.json`** — auto-refreshed weekly by a cron on VPS-40
  (`~/bin/lb-gateway-sync.sh`), which parses its own config and pushes.
  Manual refresh from a local config mirror:
  `python3 scripts/parse_gateway.py <config-dir>`.

## Running locally

```bash
pip install pyyaml
python3 scripts/build.py        # fetch live sources -> merge -> score -> data/models.json
python3 -m http.server 8000     # serve; open http://localhost:8000
```

## Known limitations

- **Free-tier rate limits vary** by provider and over time; the leaderboard is
  a snapshot, not a guarantee.
- **Arena scores are manual/curated** (top-60) and the auto list is a point-in-
  time scrape; arena preference is only a 0.10 tiebreaker.
- **Benchmarks ≠ real-world**: AA intelligence and arena ELO are proxies, not
  ground truth for your specific questions.
- **Gateway free tiers may be unstable**: many gateway providers are free
  aggregators that can go down or change. `reliability_notes` flags dead
  providers and uncertain matches.
- **Speed data is sparse**: most frontier models have no free-API speed probe,
  so their speed percentile is 0.
- Models that are free only through a consumer app (chat UI) include rate/usage
  limits noted in `free_chat_uis.json`.

## Phase 0 recon findings (existing projects)

Checked GitHub repos and the web for existing work before building:

- **`ons96/ai-leaderboard`** (public) — Artificial Analysis *provider*
  leaderboard → static site. Borrowed the RSC-scrape + GH Actions + Pages
  pattern (MIT-style reuse of a pattern, no code copied wholesale).
- **`ons96/free-llm-benchmarking`** (public) — real-probe speed benchmarks of
  free providers; used as the speed data source.
- **`ons96/llm-leaderboard`, `llm-leaderboard-aggregate`, `llm-meta-leaderboard`**
  — older aggregate leaderboards; patterns only.
- External: llm-stats.com, BenchLM.ai, OpenRouter rankings, arena.ai are
  closed products (nothing to fork). HuggingFace Open LLM Leaderboard is
  archived. No GPL/AGPL code was copied.

## Decisions made autonomously

These are reasonable defaults I chose without asking; override any of them:

1. **Repo name/location**: new public repo `ons96/free-llm-chat-leaderboard`
   (public so Actions + Pages stay free), built in the existing
   `~/CodingProjects/` workspace.
2. **Gateway is not LiteLLM**: VPS-40 actually runs `LLM-API-Key-Proxy`
   (TypeScript), not LiteLLM. Parsed its YAML configs instead.
3. **AA API key not present** → used the no-auth public-page RSC scrape (the
   same technique as `ai-leaderboard`) instead of the official API. The
   pipeline uses the official API automatically if `AA_API_KEY` is ever set.
4. **Gateway auto-refresh via VPS cron** — approved by the user on
   2026-08-18. A cron on VPS-40 (`lb-gateway-sync.sh`, Mon 05:30 UTC) parses
   its own gateway config and pushes `gateway_models.json`; the CI merges it
   at 06:00. Zero new credentials: the VPS uses its existing `gh` auth, and
   no repo secrets or deploy keys exist. (An SSH-deploy-key variant was
   tried first but VPS-40's firewall blocks port 22 from GitHub runners; the
   push design is simpler anyway.)
5. **Arena as intelligence fallback + tiebreaker**: models without an AA score
   use arena ELO (mapped to 0–100) as the intelligence signal, and arena ELO
   is the 0.10 preference component.
6. **Grounding proxy**: AA omniscience accuracy when present, else intelligence
   percentile (per the spec's suggestion).
7. **Only free-access models are ranked**: arena/AA-only rows (no gateway /
   OpenRouter / chat-UI path) are excluded from the leaderboard — it ranks what
   you can actually use for free.
8. **Context = max across sources** (verified sources like AA/arena override
   sometimes-wrong gateway static context values).
9. **Below-threshold = bottom quartile of intelligence OR unverified** (no
   intelligence signal at all).
10. **Speed percentile over models that have speed data**; missing speed = 0.
11. **Weekly cron only** (Mon 06:00 UTC) to stay comfortably within free
    Actions minutes; manual dispatch available.
12. **No CDN dependency** in the frontend (vanilla JS, self-contained) so the
    page works offline and never depends on a third-party script host.

## Project layout

```
index.html                  # frontend (vanilla JS, dark, sortable)
data/
  models.json               # GENERATED merged+scored output (the data layer)
  models_raw.json           # GENERATED merged (pre-score)
  gateway_models.json       # snapshot of VPS-40 gateway config (CI-refreshed)
  arena_scores.json         # hand-maintained top-60 arena scores
  free_chat_uis.json        # hand-maintained free chat apps
  sources/                  # GENERATED raw source snapshots
scripts/
  build.py                  # orchestrator: fetch -> merge -> score
  fetch_arena.py            # arena.ai text leaderboard (no auth)
  fetch_aa.py               # AA API (if key) else public-page RSC scrape
  fetch_openrouter.py       # OpenRouter :free models (no auth)
  fetch_benchmarks.py       # free-llm-benchmarking speed probes
  parse_gateway.py          # VPS gateway YAML -> gateway_models.json (local)
  merge.py                  # normalize + fuzzy match across sources
  score.py                  # quality gate + composite chat score
.github/workflows/update.yml # weekly + manual dispatch refresh
```

## License

MIT. See LICENSE.
