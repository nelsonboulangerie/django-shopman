#!/usr/bin/env bash
# Prévia isolada. Não altera surfaces/ nem acessa o Django real.
set -euo pipefail
REPO=$(git rev-parse --show-toplevel)
NATIVE_DIR=$(mktemp -d /tmp/shopman-pdv-native.XXXXXX)
SOURCE_REF=e0c22ba1ffe28e20c5c453db09160e941dfae8c6
git -C "$REPO" archive "$SOURCE_REF" surfaces/pos-nuxt surfaces/operator-kit | tar -x -C "$NATIVE_DIR"
for app in operator-kit pos-nuxt; do
  (cd "$NATIVE_DIR/surfaces/$app" && npm ci --ignore-scripts --no-audit --no-fund)
done
cd "$NATIVE_DIR/surfaces/pos-nuxt"
export POS_VISUAL_CLIENT_ONLY=1
export NUXT_DJANGO_BASE_URL=http://127.0.0.1:38792
export NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:38792
npm exec nuxt build
node "$REPO/docs/previews/navigation-2026-10-29/native/apply-preview.mjs" "$PWD"
NITRO_OUTPUT_DIR=.output-proposal npm exec nuxt build
node "$REPO/docs/previews/navigation-2026-10-29/native/prepare-mock.mjs" tests/visual/mockBackend.mjs "$NATIVE_DIR/mock-preview.mjs"
MOCK_PORT=38792 MOCK_SCENARIO=sale node "$NATIVE_DIR/mock-preview.mjs" &
fixture_pid=$!
HOST=127.0.0.1 PORT=4188 node .output/server/index.mjs &
baseline_pid=$!
HOST=127.0.0.1 PORT=4189 node .output-proposal/server/index.mjs &
proposal_pid=$!
trap 'kill "$fixture_pid" "$baseline_pid" "$proposal_pid" 2>/dev/null || true' EXIT INT TERM
echo "Atual: http://127.0.0.1:4188/preorders?mode=day"
echo "Proposta: http://127.0.0.1:4189/preorders?mode=day"
echo "Runtime isolado: $NATIVE_DIR"
wait
