#!/bin/bash
# Background watcher for the ship loop: run it as a supervised process, never in the foreground.
#   hub start name=pr<N>-ci application=bash cwd=<worktree> pty=false \
#     args=["<skill-dir>/scripts/pr-watch.sh", "<N>", "<worktree>", "<max-min>", "<grace-sec>"]
# Waits until every check on PR <N> (CI + review bots) has settled, mirrors progress onto the Orca card,
# prints one line per state change and ends with a single RESULT line:
#   exit 0 RESULT: GREEN · exit 1 RESULT: FAILED <checks> · exit 2 RESULT: TIMEOUT
# <grace-sec>: do not accept "all settled" before this many seconds (use ~120 right after `gh pr ready`,
# so review bots have time to register new runs instead of the stale "skipping" ones).
set -u
PR=${1:?usage: pr-watch.sh <pr> [worktree] [max-min=45] [grace-sec=0]}
WT=${2:-}
MAX_MIN=${3:-45}
GRACE=${4:-0}
ORCA=${ORCA_CLI_COMMAND:-/Applications/Orca.app/Contents/Resources/bin/orca}
start=$(date +%s)
deadline=$((start + MAX_MIN * 60))
last=""

card() {
  [ -n "$WT" ] && "$ORCA" worktree set --worktree "path:$WT" --comment "$1" --json >/dev/null 2>&1
}

comments() {
  local inline convo
  inline=$(gh api "repos/{owner}/{repo}/pulls/$PR/comments" --paginate --jq 'length' 2>/dev/null | awk '{s+=$1} END {print s+0}')
  convo=$(gh pr view "$PR" --json reviews,comments --jq '"reviews=\(.reviews | length) conversation=\(.comments | length)"' 2>/dev/null)
  echo "COMMENTS: inline=$inline $convo"
}

while :; do
  checks=$(gh pr checks "$PR" --json name,bucket,link 2>/dev/null)
  if [ -n "$checks" ] && [ "$checks" != "[]" ]; then
    total=$(jq 'length' <<<"$checks")
    done_ok=$(jq '[.[] | select(.bucket == "pass" or .bucket == "skipping")] | length' <<<"$checks")
    pending=$(jq '[.[] | select(.bucket == "pending")] | length' <<<"$checks")
    failed=$(jq -r '[.[] | select(.bucket == "fail" or .bucket == "cancel") | .name] | join(", ")' <<<"$checks")
    pending_txt=""
    [ "$pending" != 0 ] && pending_txt=", $pending pending"
    state="CI: $done_ok/$total passed${failed:+, failed: $failed}$pending_txt"
    if [ "$state" != "$last" ]; then
      echo "$(date +%H:%M:%S) $state"
      card "PR #$PR $state"
      last=$state
    fi
    if [ "$pending" = 0 ] && [ $(($(date +%s) - start)) -ge "$GRACE" ]; then
      if [ -z "$failed" ]; then
        card "PR #$PR CI Green ✅ $done_ok/$total"
        comments
        echo "RESULT: GREEN $done_ok/$total"
        exit 0
      fi
      jq -r '.[] | select(.bucket == "fail" or .bucket == "cancel") | "FAILED-CHECK: \(.name) \(.link)"' <<<"$checks"
      comments
      echo "RESULT: FAILED $failed"
      exit 1
    fi
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "RESULT: TIMEOUT after ${MAX_MIN}m (${last:-no checks reported})"
    exit 2
  fi
  sleep 30
done
