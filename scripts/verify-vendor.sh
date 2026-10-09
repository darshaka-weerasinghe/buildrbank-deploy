#!/usr/bin/env bash
# Prove that vendor/buildrbank/ is still exactly what the students wrote.
#
#   ./scripts/verify-vendor.sh
#
# Hashes every .py file in vendor/ and the same files taken straight out of
# git, then compares. __pycache__ is ignored - Python writes those when it
# runs the code, and they are not source.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${1:-$HERE/../agentic-ai-cohort-01-phase-01}"
BRANCH="origin/week-11"

if [ ! -d "$REPO/.git" ]; then
  echo "Cannot find the cohort repo at: $REPO"
  echo "Pass its path:  ./scripts/verify-vendor.sh /path/to/agentic-ai-cohort-01-phase-01"
  exit 2
fi

FROM_GIT=$(cd "$REPO" && git archive "$BRANCH" "Week 11/buildrbank" | tar -x -O | shasum | cut -d' ' -f1)
FROM_HERE=$(cd "$HERE/vendor" && find buildrbank -type f -name '*.py' | sort | tar -cf - -T - | tar -x -O | shasum | cut -d' ' -f1)

echo "  from git    $FROM_GIT"
echo "  from vendor $FROM_HERE"
if [ "$FROM_GIT" = "$FROM_HERE" ]; then
  echo "  IDENTICAL - the agent has not been modified."
else
  echo "  DIFFERENT - something in vendor/ has been edited. It should not be."
  exit 1
fi
