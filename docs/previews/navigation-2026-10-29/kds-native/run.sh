#!/usr/bin/env bash
# Node 22. Somente cópias temporárias e dados fictícios.
set -euo pipefail
REPO=$(git rev-parse --show-toplevel)
KDS_DIR=$(mktemp -d /tmp/shopman-kds-native.XXXXXX)
git -C "$REPO" archive e0c22ba1ffe28e20c5c453db09160e941dfae8c6 surfaces/kds-nuxt surfaces/operator-kit | tar -x -C "$KDS_DIR"
for app in operator-kit kds-nuxt; do
 (cd "$KDS_DIR/surfaces/$app" && npm ci --ignore-scripts --no-audit --no-fund)
done
node "$REPO/docs/previews/navigation-2026-10-29/kds-native/prepare-mock.mjs" "$KDS_DIR/surfaces/kds-nuxt/tests/e2e" "$KDS_DIR/mock"
cd "$KDS_DIR/surfaces/kds-nuxt"
export NUXT_DJANGO_BASE_URL=http://127.0.0.1:38798
npm exec nuxt build
node "$REPO/docs/previews/navigation-2026-10-29/kds-native/apply-preview.mjs" "$PWD"
node "$REPO/docs/previews/navigation-2026-10-29/kds-native/apply-navigation.mjs" "$PWD"
node "$REPO/docs/previews/navigation-2026-10-29/kds-native/apply-refinement.mjs" "$PWD"
npm exec nuxt build
MOCK_PORT=38798 KDS_MOCK_FIXTURE=preview node "$KDS_DIR/mock/mockBackend.mjs" &
fixture_pid=$!
HOST=127.0.0.1 PORT=4192 node .output/server/index.mjs &
baseline_pid=$!
HOST=127.0.0.1 PORT=4193 node .output-proposal/server/index.mjs &
proposal_pid=$!
trap 'kill "$fixture_pid" "$baseline_pid" "$proposal_pid" 2>/dev/null || true' EXIT INT TERM
echo "Atual: http://127.0.0.1:4192/bancada"
echo "Proposta: http://127.0.0.1:4193/bancada"
echo "Runtime: $KDS_DIR"
wait
