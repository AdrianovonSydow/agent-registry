#!/usr/bin/env python3
"""
Run after a PR changing agents/<agent_id>/agent.yaml is approved and
merged to main. Computes a content hash of the file as it exists at the
given commit, and inserts one row into audit.agent_versions recording:
agent_id, git_commit, content_hash, approver, merged_at.

That row's content_hash becomes the agent_version_hash every execution
event in audit.agent_event_log should reference going forward -- it is
the durable pointer from "what happened" back to "exactly what config
produced it."

This script does NOT deploy the agent anywhere. Deployment (pushing the
config into whatever runtime executes it) is a separate, later step --
keeping them separate means promotion (the audited, approved fact of
"this version is sanctioned") can't be silently skipped by a deploy
script that also writes the audit row.

Usage:
    python3 scripts/promote.py <agent_id> <git_commit_sha> <approver_username>

Requires env vars:
    AUDIT_DB_HOST, AUDIT_DB_PORT, AUDIT_DB_NAME, AUDIT_DB_USER, AUDIT_DB_PASSWORD
"""

import sys
import os
import subprocess
import hashlib
import json
from datetime import datetime, timezone

try:
    import psycopg2
except ImportError:
    print("Missing dependency: pip install psycopg2-binary --break-system-packages")
    sys.exit(1)


def get_file_content_at_commit(agent_id: str, commit: str) -> str:
    path = f"agents/{agent_id}/agent.yaml"
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        capture_output=True, text=True, check=True
    )
    return result.stdout


def content_hash(content: str) -> str:
    # Hash the raw file bytes as committed -- this must match exactly what
    # a reviewer approved, not a re-serialized or re-formatted version of it.
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def insert_version_record(agent_id, git_commit, hash_value, approver, content):
    conn = psycopg2.connect(
        host=os.environ["AUDIT_DB_HOST"],
        port=os.environ.get("AUDIT_DB_PORT", "5432"),
        dbname=os.environ["AUDIT_DB_NAME"],
        user=os.environ["AUDIT_DB_USER"],
        password=os.environ["AUDIT_DB_PASSWORD"],
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit.agent_versions
                    (agent_id, git_commit, content_hash, approver, merged_at, raw_content)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING version_id
                """,
                (agent_id, git_commit, hash_value, approver,
                 datetime.now(timezone.utc), content)
            )
            version_id = cur.fetchone()[0]
            return version_id
    finally:
        conn.close()


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    agent_id, git_commit, approver = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        content = get_file_content_at_commit(agent_id, git_commit)
    except subprocess.CalledProcessError:
        print(f"Could not read agents/{agent_id}/agent.yaml at commit {git_commit}")
        sys.exit(1)

    hash_value = content_hash(content)
    version_id = insert_version_record(agent_id, git_commit, hash_value, approver, content)

    print(json.dumps({
        "version_id": version_id,
        "agent_id": agent_id,
        "git_commit": git_commit,
        "content_hash": hash_value,
        "approver": approver
    }, indent=2))
    print(f"\nagent_version_hash for future audit.agent_event_log rows: {hash_value}")


if __name__ == "__main__":
    main()
