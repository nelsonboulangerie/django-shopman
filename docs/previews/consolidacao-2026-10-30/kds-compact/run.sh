#!/usr/bin/env bash
# PRÉVIA. Node 22. Cópias temporárias e dados fictícios; não escreve em surfaces/.
# A = origin/main intacto (+ só a simulação de conexão), B = prévia anterior (PR #2048),
# C = compacto (B + apply-compact). Portas: mock 38898, A 4291, B 4292, C 4293.
set -euo pipefail
REPO=$(git rev-parse --show-toplevel)
HERE="$REPO/docs/previews/consolidacao-2026-10-30/kds-compact"
PREV_REF=${PREV_REF:-origin/codex/shopman-ux-product-review}
RT=$(mktemp -d /tmp/shopman-kds-compact.XXXXXX)
git -C "$REPO" archive "$PREV_REF" docs/previews/navigation-2026-10-29/kds-native | tar -x -C "$RT"
P="$RT/docs/previews/navigation-2026-10-29/kds-native"
mkdir -p "$RT/A"; git -C "$REPO" archive origin/main surfaces/kds-nuxt surfaces/operator-kit | tar -x -C "$RT/A"
for app in operator-kit kds-nuxt; do (cd "$RT/A/surfaces/$app" && npm ci --ignore-scripts --no-audit --no-fund); done
cp -cR "$RT/A" "$RT/B" 2>/dev/null || cp -R "$RT/A" "$RT/B"
cp -cR "$RT/A" "$RT/C" 2>/dev/null || cp -R "$RT/A" "$RT/C"
node "$P/prepare-mock.mjs" "$RT/A/surfaces/kds-nuxt/tests/e2e" "$RT/mock"
export NUXT_DJANGO_BASE_URL=http://127.0.0.1:38898
(cd "$RT/A/surfaces/kds-nuxt" && node "$HERE/apply-conn-sim.mjs" "$PWD" && npm exec nuxt build)
(cd "$RT/B/surfaces/kds-nuxt" && for s in apply-preview apply-navigation apply-refinement; do node "$P/$s.mjs" "$PWD"; done && node "$HERE/apply-conn-sim.mjs" "$PWD" && npm exec nuxt build)
(cd "$RT/C/surfaces/kds-nuxt" && for s in apply-preview apply-navigation apply-refinement; do node "$P/$s.mjs" "$PWD"; done && node "$HERE/apply-conn-sim.mjs" "$PWD" && node "$HERE/apply-compact.mjs" "$PWD" && npm exec nuxt build)
MOCK_PORT=38898 KDS_MOCK_FIXTURE=preview node "$RT/mock/mockBackend.mjs" & m=$!
(cd "$RT/A/surfaces/kds-nuxt" && HOST=127.0.0.1 PORT=4291 node .output/server/index.mjs) & a=$!
(cd "$RT/B/surfaces/kds-nuxt" && HOST=127.0.0.1 PORT=4292 node .output-proposal/server/index.mjs) & b=$!
(cd "$RT/C/surfaces/kds-nuxt" && HOST=127.0.0.1 PORT=4293 node .output-proposal/server/index.mjs) & c=$!
trap 'kill $m $a $b $c 2>/dev/null || true' EXIT INT TERM
echo "A http://127.0.0.1:4291/bancada  B http://127.0.0.1:4292/bancada  C http://127.0.0.1:4293/bancada"
wait
