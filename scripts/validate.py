#!/usr/bin/env python3
"""
Validates every agents/<agent_id>/agent.yaml against schema/agent_schema.json,
plus a few checks a JSON schema can't express on its own. Exits non-zero on
any failure -- intended to run in CI (blocks PR merge) and optionally as a
local pre-commit hook (fails fast before you even push).

Usage:
    python3 scripts/validate.py
    python3 scripts/validate.py agents/risk-summarizer-v1/agent.yaml   # single file
"""

import sys
import json
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Missing dependency: pip install pyyaml jsonschema --break-system-packages")
    sys.exit(1)

try:
    import jsonschema
except ImportError:
    print("Missing dependency: pip install pyyaml jsonschema --break-system-packages")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "agent_schema.json"
AGENTS_DIR = REPO_ROOT / "agents"


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def find_agent_files(explicit_paths):
    if explicit_paths:
        return [Path(p) for p in explicit_paths]
    return sorted(AGENTS_DIR.glob("*/agent.yaml"))


def extra_checks(agent_id_from_dir, data, errors):
    """Checks that go beyond what JSON Schema can express."""

    # agent_id in the file must match its parent directory -- prevents a
    # copy-paste error where someone duplicates a folder but forgets to
    # rename the id inside, silently aliasing two agents.
    if data.get("agent_id") != agent_id_from_dir:
        errors.append(
            f"agent_id '{data.get('agent_id')}' does not match directory name "
            f"'{agent_id_from_dir}'"
        )

    # Any agent with a tool capable of taking action (not just reading)
    # must require human approval. This is a deliberate, conservative
    # policy choice for the GxP context, not a generic best practice --
    # tighten or loosen per your own risk appetite.
    action_capable_types = {"code_execution"}
    has_action_tool = any(
        t.get("type") in action_capable_types for t in data.get("tools", [])
    )
    if has_action_tool and not data.get("human_approval_required", False):
        errors.append(
            "agent has an action-capable tool but human_approval_required is "
            "not true -- this combination is blocked by policy"
        )

    # Placeholder/lazy prompts shouldn't pass review even if they clear the
    # minLength bar in the schema.
    placeholder_markers = ["TODO", "TBD", "placeholder", "xxx"]
    prompt_lower = data.get("system_prompt", "").lower()
    if any(marker.lower() in prompt_lower for marker in placeholder_markers):
        errors.append("system_prompt appears to contain placeholder text")


def main():
    explicit_paths = sys.argv[1:]
    schema = load_schema()
    files = find_agent_files(explicit_paths)

    if not files:
        print("No agent.yaml files found under agents/")
        sys.exit(1)

    total_errors = 0

    for path in files:
        agent_id_from_dir = path.parent.name
        errors = []

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"FAIL  {path}\n  YAML parse error: {e}")
            total_errors += 1
            continue

        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as e:
            errors.append(f"schema: {e.message} (at {'.'.join(str(p) for p in e.path)})")

        extra_checks(agent_id_from_dir, data, errors)

        if errors:
            print(f"FAIL  {path}")
            for err in errors:
                print(f"  - {err}")
            total_errors += len(errors)
        else:
            print(f"OK    {path}")

    if total_errors:
        print(f"\n{total_errors} error(s) across {len(files)} file(s)")
        sys.exit(1)

    print(f"\nAll {len(files)} agent definition(s) valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
