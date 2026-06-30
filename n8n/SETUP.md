# Setting Up: GitHub Polling → n8n Promotion Workflow

This replaces an earlier webhook-based design. Reasoning: you don't
currently run a reverse proxy or tunnel, and standing one up purely
to receive this one webhook would add infrastructure and attack
surface for a benefit (near-real-time promotion) that doesn't
actually matter here — `audit.agent_versions` records the PR's
`merged_at` time regardless of when n8n got around to processing it,
so a 5-minute polling lag costs nothing on the traceability claim.

## What this workflow does, step by step

1. Every 5 minutes, reads `ops.poll_state` to find the timestamp of
   the last merged PR it already processed.
2. Asks GitHub for recently closed PRs against `main`, sorted by
   most recently updated.
3. Filters to only PRs merged after that last-checked timestamp —
   this is what makes polling idempotent: re-running never
   reprocesses the same PR twice.
4. For each newly merged PR, checks which changed files match
   `agents/<id>/agent.yaml`.
5. Pulls the PR's reviews, requires a real `APPROVED` review to
   exist — throws and stops if not, refusing to promote an
   unapproved merge.
6. Hashes the file content at the merge commit, inserts the row into
   `audit.agent_versions`.
7. Updates `ops.poll_state` to the newest `merged_at` it saw, so the
   next run starts from there.

No inbound exposure of anything. n8n only makes outbound calls to
GitHub's API, same as your other LiteLLM/OpenClaw integrations
already do.

## 1. Apply the new SQL

Run `scripts/sql/06_poll_state.sql` against the same `postgres`
database as before (Adminer, same pattern as `05_agent_versions.sql`).
This creates a new `ops` schema and the `ops.poll_state` table.

## 2. Import the workflow

n8n: **Workflows → Import from File** →
`agent-registry-promotion-polling-workflow.json`.

## 3. Fill in the placeholders

Two things need editing before this runs:

- **Get Recently Closed PRs** node: replace `REPLACE_OWNER` and
  `REPLACE_REPO` in the URL with your actual GitHub username/org and
  repo name.
- Every node showing `REPLACE_WITH_CREDENTIAL_ID`: attach real
  credentials (see step 4).

## 4. Credentials

- **GitHub credential**: fine-grained Personal Access Token, scoped
  to this repo only, **Pull requests: Read-only** and **Contents:
  Read-only**. Attach to the three GitHub HTTP Request nodes
  (*Get Recently Closed PRs*, *Get Changed Files*, *Get PR Reviews*,
  *Get File Content At Merge Commit*).
- **Postgres credential**: the `audit_promoter` role (from the SQL
  migrations), host `192.168.68.65`, database `postgres`. Attach to
  all three Postgres nodes (*Get Last Checked Timestamp*, *Insert
  agent_versions Row*, *Update Last Checked Timestamp*).

No webhook secret to configure this time — nothing to verify since
nothing is receiving inbound requests.

## 5. Activate the workflow

Toggle **Active**. It runs on its own every 5 minutes from then on —
no GitHub-side webhook configuration needed at all.

## Known limitations, honestly

- **Polling interval is a trade-off, not free.** 5 minutes means up
  to 5 minutes between a merge and its promotion record existing.
  Adjust the schedule node if you want tighter or looser.
- **The "newest merged_at" bookmark only advances correctly if the
  whole run succeeds.** If one agent's promotion fails partway
  through a batch of several (transient GitHub or Postgres error),
  the current logic still advances the bookmark using the max
  `merged_at` across all newly-merged PRs in that run, which could
  skip a retry of the failed one. Fine for a prototype; for
  production, track per-PR success and only advance the bookmark
  past PRs that fully succeeded.
- **Re-approval after force-push is not checked.** If a PR is
  approved, then changed via force-push, then merged without fresh
  review, GitHub's API still shows the original approval, and this
  workflow treats it as valid.
- **GitHub API rate limits**: a 5-minute poll is well within
  free-tier limits for any reasonable repo size. Worth checking
  headroom (`GET /rate_limit`) if you add more repos or a tighter
  interval later.

## Test it end to end

Edit `agents/risk-summarizer-v1/agent.yaml`, open a PR, get it
approved by a second account, merge it, then either wait up to 5
minutes or manually execute the workflow once in n8n's UI to trigger
it immediately. Check `audit.agent_versions` in Adminer for the new
row, and check `ops.poll_state` to confirm the bookmark advanced.
