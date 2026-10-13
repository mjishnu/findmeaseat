#!/usr/bin/env bash
# Deploy findmeaseat on this host: fast-forward the checkout to a commit on
# origin/main, rebuild the images, restart the stack, and smoke-test it.
#
# GitHub Actions runs this over SSH with a key restricted to this one command
# (see "Continuous deployment" in README.md); the commit SHA to deploy arrives in
# $SSH_ORIGINAL_COMMAND. By hand:  deploy/deploy.sh [<commit-sha>]
#
# Wrapped in main() so bash parses the whole file before `git merge` can rewrite it.

main() {
  set -euo pipefail

  local target="${1:-${SSH_ORIGINAL_COMMAND:-}}"
  if [[ -n "$target" && ! "$target" =~ ^[0-9a-f]{40}$ ]]; then
    echo "deploy: expected a 40-character commit SHA, got '$target'" >&2
    return 2
  fi

  cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.."

  exec 9>/tmp/findmeaseat-deploy.lock
  if ! flock -n 9; then
    echo "deploy: another deploy is running" >&2
    return 1
  fi

  # Never deploy over edits made directly on the server: they'd ship untracked.
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "deploy: the checkout has uncommitted changes; commit or stash them first" >&2
    git status --short >&2
    return 1
  fi

  git fetch --quiet origin main
  target="${target:-$(git rev-parse origin/main)}"
  if ! git merge-base --is-ancestor "$target" origin/main; then
    echo "deploy: $target is not on origin/main" >&2
    return 1
  fi
  # Only moves forward: re-running an older workflow never rolls the server back.
  git merge --ff-only --quiet "$target"
  echo "deploy: checkout at $(git rev-parse --short HEAD)"

  docker compose up -d --build --remove-orphans

  echo "deploy: smoke test"
  local ok=""
  for _ in $(seq 1 30); do
    # nginx -> backend through the same path browsers use (127.0.0.1: nginx
    # listens on IPv4 only and busybox resolves localhost to ::1)
    if docker compose exec -T frontend wget -qO /dev/null "http://127.0.0.1/api/stations?q=ERS&limit=1"; then
      ok=1
      break
    fi
    sleep 2
  done
  if [[ -z "$ok" ]]; then
    echo "deploy: smoke test failed" >&2
    docker compose ps >&2
    docker compose logs --tail=50 backend >&2
    return 1
  fi

  docker image prune -f >/dev/null
  echo "deploy: done ($(git rev-parse --short HEAD))"
}

main "$@"
exit
