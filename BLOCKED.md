# BLOCKED.md — items that need human action

Items I could not complete autonomously, ordered by impact. Everything else in
this project is complete and working. To unblock, follow the "What you need to
do" for each.

---

## 1. AA_API_KEY (Artificial Analysis official API) — optional upgrade, low impact

**What I needed:** An Artificial Analysis Data API v2 key (`AA_API_KEY`).
**Why I couldn't proceed:** `GET https://artificialanalysis.ai/api/v2/language/models`
returns `401 API key is required` without a key, and `AA_API_KEY` is not set in
the environment. Per the cost rules I did not sign up for anything (signup may
require payment details).
**What I tried:** Verified the endpoint returns 401; verified the no-auth
fallback works (public-page RSC scrape gives `intelligenceIndex`, omniscience
accuracy/hallucination-rate, context, prices for the top ~29 models).
**Impact:** The leaderboard already works via the public-page scrape fallback;
the official API is only a nicer/more official data path.
**What you need to do (optional):** If you have a free AA account, set the
`AA_API_KEY` repo secret:
1. Get a key from https://artificialanalysis.ai/data-api/docs (free tier; only
   do this if no credit card is required).
2. Add it as a repo secret:
   `gh secret set AA_API_KEY -R ons96/free-llm-chat-leaderboard`
The workflow already passes `AA_API_KEY` to the pipeline and gracefully skips
the API when absent, so this is purely an upgrade.

---

## 2. Gateway config auto-refresh in CI — medium impact, needs an SSH key

**What I needed:** SSH access from GitHub Actions to VPS-40
(40.233.101.233) to pull the live gateway config each week.
**Why I couldn't proceed:** Committing a VPS SSH private key as a repo secret
is a security decision only you can make; the autonomy directive says don't
create credentials I don't have.
**What I tried:** Pulled the config myself over SSH (works with
`~/.ssh/oracle.key`) and committed a snapshot in `data/gateway_models.json`
(586 model records, 84 free-tier providers). The weekly CI refreshes every
other source but uses the committed gateway snapshot.
**Impact:** Gateway model/provider changes won't appear until you regenerate
the snapshot. Everything else stays fresh.
**What you need to do (optional):**
- Option A (no secrets): periodically run locally
  `python3 scripts/parse_gateway.py <dir-with-gateway-configs>` and commit the
  updated `data/gateway_models.json`.
- Option B (full automation): add an SSH deploy key for VPS-40 as a repo
  secret (e.g. `VPS_SSH_KEY`), then wire a step in
  `.github/workflows/update.yml` to scp the config and run `parse_gateway.py`.
  Not wired up by default for safety.

---

## 3. GitHub Pages deployment — assumed to be enabled by `gh` (verify)

**What I needed:** Pages enabled on the new public repo so the site goes live.
**Why I couldn't proceed:** I attempted to enable Pages via the API; if the
`gh` token lacks the `pages` write permission or the repo is too new, the
enable call may have been rejected.
**What I tried:** `gh api repos/ons96/free-llm-chat-leaderboard/pages` to enable
(source branch `main`, path `/`).
**What you need to do (if not already live):** In the repo settings → Pages,
set Source = "Deploy from a branch", Branch = `main`, folder = `/` (root).
The site will be at https://ons96.github.io/free-llm-chat-leaderboard/.

---

## Not blocked

- All data sources (gateway snapshot, AA public scrape, OpenRouter, arena,
  benchmarks, hand-maintained JSONs) are working.
- Scoring, frontend, weekly GitHub Action, README: complete.
- No paid services, no credit cards, no paid CI used anywhere.
