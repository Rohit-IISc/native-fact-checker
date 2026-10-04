#!/usr/bin/env bash
# Build the PWA and deploy Hosting, Firestore rules and indexes.
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
(cd frontend && pnpm install --frozen-lockfile && pnpm build)
firebase deploy --project "$PROJECT_ID" --only hosting,firestore:rules,firestore:indexes
