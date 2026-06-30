# Agent Registry — Git-Based Definition Workflow

## What this is

The "agent definitions are code" half of the GxP-flavored prototype.
Every agent's configuration (prompt, model, tools) lives as a YAML
file in this repo. Changes go through a pull request, automated
validation, and human approval before being recorded as an approved
version in the `audit.agent_versions` table — the bridge to the
hash-chained execution log built earlier.

## What this does NOT do

It does not deploy an agent anywhere. Promotion (recording "this
version is approved") and deployment (making it actually run
somewhere — Flowise, a custom LiteLLM-routed wrapper, whatever
runtime you pick) are deliberately separate steps. Conflating them
would mean a deploy script could also write its own audit row,
which defeats the point of an independent approval record.

## Workflow

1. Edit or create `agents/<agent_id>/agent.yaml`.
2. Open a PR. GitHub Actions runs `scripts/validate.py` automatically
   — schema check plus policy lints (placeholder prompts, action-capable
   tools missing the approval flag, id/directory mismatches).
3. A human reviews and approves the PR. **Set up branch protection on
   `main` requiring at least one approving review and the validation
   check to pass before merge is allowed** — without this, the workflow
   is advisory, not enforced.
4. On merge, the promotion step should run `scripts/promote.py
   <agent_id> <commit_sha> <approver>`, which hashes the file content
   and inserts a row into `audit.agent_versions`.
5. That row's `content_hash` becomes the `agent_version_hash` your
   agent runtime should pass into every row it writes to
   `audit.agent_event_log` for executions using this version.

## Known gap: GitHub Actions can't reach your Postgres

Your database is at `192.168.68.65`, LAN-only. GitHub-hosted runners
have no path to it. Before relying on `.github/workflows/validate.yml`'s
promote job, do one of:

- **Self-hosted runner** (install on the NUC, polls GitHub, no inbound
  ports needed) — heavier to maintain but keeps everything in GitHub.
- **n8n webhook** (recommended, reuses what you already run): configure
  a GitHub webhook on this repo for the `pull_request` merged event,
  pointed at an n8n workflow that runs `promote.py` (or replicates its
  logic in an n8n Postgres node) using credentials already scoped on
  your LAN. This avoids exposing the database to the internet at all.

Until one of these is wired up, run `scripts/promote.py` manually
after each approved merge — it still produces a correct, auditable
row, it's just not automatic yet.

## Known gap: approver identity in the workflow file

The `validate.yml` workflow has a placeholder for looking up who
actually approved the PR (GitHub's merge-commit author is usually
the person who clicked "merge," not necessarily the reviewer who
approved — these can differ). Before this is anything beyond a
prototype, that step needs to call the GitHub API
(`gh api repos/{owner}/{repo}/pulls/{pr}/reviews`) to pull the actual
approving reviewer(s), not assume the committer.

## Setup checklist

1. Run `scripts/sql/05_agent_versions.sql` against your `postgres`
   database, `audit` schema (same place as the rest of the audit
   log) — set the `CHANGE_ME` password for `audit_promoter` first.
2. Create this repo on GitHub (or your git host of choice), push
   this structure.
3. Enable branch protection on `main`: require PR review, require
   the validation status check.
4. Wire up promotion via n8n or a self-hosted runner (see above).
5. Add `AUDIT_DB_*` secrets to the repo (or to the n8n credential
   store, if going that route).
