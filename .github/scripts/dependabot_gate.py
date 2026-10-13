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
# The commit's "updated-dependencies:" metadata names every dependency it touches
# (quoted when the name has special characters, e.g. "@base-ui/react")
DECLARED = re.compile(r'^- dependency-name: "?([^"\s]+)"?', re.MULTILINE)
# Present for version updates (not security updates)
UPDATE_TYPE = re.compile(r"^\s+update-type: (\S+)", re.MULTILINE)
SAFE_UPDATE_TYPES = {"version-update:semver-minor", "version-update:semver-patch"}


def needs_review(commit: dict) -> str | None:
    """The reason this commit needs a human, or None if it is safe to merge."""
    if (commit.get("author") or {}).get("login") != "dependabot[bot]":
        return "head commit isn't authored by Dependabot"
    if not commit["commit"]["verification"]["verified"]:
        return "head commit signature isn't verified"

    message = commit["commit"]["message"]
    declared = set(DECLARED.findall(message))
    if not declared:
        return "no updated-dependencies metadata"
    for update_type in UPDATE_TYPE.findall(message):
        if update_type not in SAFE_UPDATE_TYPES:
            return f"update type {update_type}"

    # Every declared dependency must have a version change we can classify
    changes = CHANGE.findall(message)
    unclassified = declared - {name for name, *_ in changes}
    if unclassified:
        return f"can't tell how {', '.join(sorted(unclassified))} changes"
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
