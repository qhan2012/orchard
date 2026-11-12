#!/usr/bin/env python3
"""PreToolUse guard for the master's Bash commands. Three rules only.

Reads the hook JSON on stdin. Prints a decision for a match; prints nothing
otherwise, so the normal permission flow applies.

It matches the command text, so it can also match a command that only
mentions these words (for example inside a prompt). That is accepted: the
reason tells the master what to do.
"""
import json
import re
import sys

RULES = [
    # (decision, pattern, reason)
    ("deny", r"\bherdr\b.*\b(agent|pane)\s+send-keys\b",
     "orchard guard: the master does not send keys to an agent. A blocked agent "
     "waits for the person. Read its screen and report."),
    ("ask", r"\bherdr\b.*\b(server|session)\s+stop\b",
     "orchard guard: this stops a herdr server and every agent in it. "
     "Only the person decides this."),
    ("deny", r"\bgit\b.*\badd\b.*\s(--force\b|-[A-Za-z]*f[A-Za-z]*\b)",
     "orchard guard: this repo is public. A forced add can publish gitignored "
     "site data (targets, tasks, machine memory, reports)."),
]


def decide(command: str):
    for decision, pattern, reason in RULES:
        if re.search(pattern, command, flags=re.S):
            return decision, reason
    return None


def main() -> int:
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        return 0
    hit = decide(str(data.get("tool_input", {}).get("command", "")))
    if hit:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": hit[0],
            "permissionDecisionReason": hit[1],
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
