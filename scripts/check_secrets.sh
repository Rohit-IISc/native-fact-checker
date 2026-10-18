#!/usr/bin/env bash
# Refuse a commit that adds anything secret-looking (the repo is public; a leaked key could disqualify us).
# Installed as .git/hooks/pre-commit by `make hooks`. Cloud Build runs gitleaks on every deploy as well.
set -euo pipefail
PATTERNS='AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"private_key"[[:space:]]*:|ya29\.[0-9A-Za-z_-]{20,}|GOCSPX-[0-9A-Za-z_-]{10,}|ghp_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{30,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|xox[bp]-[0-9A-Za-z-]{10,}'
hits=$(git diff --cached -U0 --no-color | grep -E '^\+' | grep -nE "$PATTERNS" || true)
bad_files=$(git diff --cached --name-only --diff-filter=AM | grep -E '(^|/)node_modules(/|$)|(^|/)(samples|artifacts|runs)(/|$)|\.pem$|-key\.json$|service-account.*\.json$|(^|/)\.env$' || true)
if [[ -n "$hits" || -n "$bad_files" ]]; then
  echo "BLOCKED: this commit looks like it contains a secret or private file." >&2
  [[ -n "$hits" ]] && echo "$hits" | sed -E 's/(AIza|GOCSPX-|ghp_|ya29\.|sk-)[0-9A-Za-z_-]{4}[0-9A-Za-z_.-]*/\1****/g' >&2
  [[ -n "$bad_files" ]] && echo "$bad_files" >&2
  exit 1
fi
