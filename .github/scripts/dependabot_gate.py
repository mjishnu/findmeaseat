"""Decide whether a Dependabot PR may be auto-merged (exit 0) or needs review (exit 1).

Reads the PR's head commit, as returned by `gh api repos/{repo}/commits/{sha}`, on
stdin. Fails closed: anything it can't classify is left for review.
"""

import json
import re
import sys

# Runtime images: CI's tests run on a pinned version, so even a minor bump needs review
RUNTIMES = {"python", "node"}

# Dependabot writes each change as "bump X from A to B" (title),
# "Bumps [X](url) from A to B" (single update, body), or "Updates `X` from A to B"
# (multi-dependency and grouped updates, body). Range edits such as
# "update X requirement from <9 to <10" match none of these and need review.
CHANGE = re.compile(
    r"(?:\bbump|Bumps|Updates) [\[`]?([^\s`\]]+)[\]`]?(?:\([^)\s]*\))?"
    r" from v?(\d+)\.?(\d*)\S* to v?(\d+)\.?(\d*)"
)


def needs_review(commit: dict) -> str | None:
    """The reason this commit needs a human, or None if it is safe to merge."""
    if (commit.get("author") or {}).get("login") != "dependabot[bot]":
        return "head commit isn't authored by Dependabot"
    if not commit["commit"]["verification"]["verified"]:
        return "head commit signature isn't verified"

    changes = CHANGE.findall(commit["commit"]["message"])
    if not changes:
        return "can't tell which versions change"
    for name, from_major, from_minor, to_major, to_minor in changes:
        if from_major != to_major:
            return f"{name} major update {from_major} -> {to_major}"
        if (from_major == "0" or name in RUNTIMES) and from_minor != to_minor:
            return f"{name} {from_major}.{from_minor} -> {to_major}.{to_minor}"
    return None


if __name__ == "__main__":
    reason = needs_review(json.load(sys.stdin))
    print(reason or "minor/patch updates only")
    sys.exit(1 if reason else 0)
