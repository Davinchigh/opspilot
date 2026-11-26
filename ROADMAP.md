# Roadmap

Do these in order. Each is small enough for one or two sittings and has a check that proves it is done.
After each one: tests pass, README updated, commit, push.

## Stage 1: make it real (highest value for applications)

- [ ] **1. Run the n8n workflow** (no account or key needed). The JSON is hand-written and has never
  been imported, so fix whatever breaks. Follow `docs/N8N.md`, then add a Slack, Telegram or email node
  on the escalated branch. *Done when:* a screenshot of a successful execution is in the README.
- [ ] **2. Run with a real model.** Get a free API key (links in `.env.example`), set `.env`, run
  `python -m opspilot eval`. *Done when:* the README compares rules and model scores, latency and cost.
- [ ] **3. Honest test set.** Ask 3 or more people to write 60 messages the way they would text a bakery,
  typos and local phrasing included. Label them as split `real` (add it to `--split` in `__main__.py`).
  Never tune on them. *Done when:* the README reports `real` scores and explains 3 failures.
- [ ] **4. Improve from evidence.** Fix the worst failure type using `dev` only. Known bug to start with:
  "How much is an 8 inch celebration cake?" extracts quantity 1 (case `dev-03`).
  *Done when:* before and after scores are in `docs/EVAL-LOG.md`.
- [ ] **5. Deploy a live demo** on a free host. First add rate limiting and a periodic data reset, keep
  the token on, and keep the offline provider so strangers cannot spend your quota.
  *Done when:* the README links to it.
- [ ] **6. Record a 2-minute video:** message in, flags, edit, approve, audit log, eval run.
  Add it and two screenshots to the README.

## Stage 2: close common job-ad gaps

- [ ] **7. Semantic search.** Add embeddings with Postgres and pgvector beside BM25. Add more documents
  first and score top 1, because the current set is too small to separate methods.
  *Done when:* eval compares keyword, vector and hybrid hit rates.
- [ ] **8. FastAPI and Pydantic** version of `server.py` and the validators.
  *Done when:* the same API tests pass.
- [ ] **9. Agent with tools.** Let the model call `check_delivery_fee`, `check_lead_time` and
  `create_order_draft`, with a step limit and a stored trace. Writes still need approval.
  *Done when:* eval has multi-step cases and a tool-choice score.
- [ ] **10. Rebuild the workflow in one agent framework** (for example LangGraph) on a branch.
  *Done when:* `docs/FRAMEWORK-NOTES.md` says what it added and what it cost.

## Stage 3: production habits

- [ ] 11. Tracing with Langfuse or an OpenTelemetry-based tool.
- [ ] 12. Build the Docker image in CI.
- [ ] 13. Real login for reviewers.
- [ ] 14. One real channel (email or Telegram) behind the approval step.
- [ ] 15. Pilot with a real small business, with written permission. Measure minutes saved per message.
