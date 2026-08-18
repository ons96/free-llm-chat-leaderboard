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

## 2. ~~Gateway config auto-refresh in CI~~ — RESOLVED

Wired up on 2026-08-18. A dedicated, restricted SSH deploy key (`VPS_SSH_KEY`
repo secret) lets the weekly workflow pull the live gateway config from VPS-40.
The key is locked down on the VPS via an `authorized_keys` forced command: it
can ONLY run `~/bin/gw-config-fetch.sh`, which tars exactly the 5 config files
the pipeline needs. No shell access, no port forwarding, no pty, host key
pinned in the workflow. The workflow skips the fetch gracefully if the secret
is ever removed, falling back to the committed snapshot.

---

## 3. ~~GitHub Pages deployment~~ — RESOLVED, no action needed

Pages was enabled via the GitHub API during the build (source: branch `main`, path `/`).
Live at https://ons96.github.io/free-llm-chat-leaderboard/.

---

## Not blocked

- All data sources (gateway snapshot, AA public scrape, OpenRouter, arena,
  benchmarks, hand-maintained JSONs) are working.
- Scoring, frontend, weekly GitHub Action, README: complete.
- No paid services, no credit cards, no paid CI used anywhere.
