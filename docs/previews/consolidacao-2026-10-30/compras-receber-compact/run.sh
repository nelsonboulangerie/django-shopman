#!/usr/bin/env bash
# PRÉVIA. Node 22. Cópias temporárias e dados fictícios; não escreve em surfaces/.
# A = origin/main intacto; C = A + compact-kit + apply-compact (só o /receive muda).
# Portas fixas: mock 38930, A 4321, C 4322. O mock tem UM cenário global (A e C dividem).
# EVIDENCE=1 roda a evidência (Playwright headless) e grava em shots/.
set -euo pipefail
export PATH=/opt/homebrew/opt/node@22/bin:$PATH
REPO=$(git rev-parse --show-toplevel)
HERE="$REPO/docs/previews/consolidacao-2026-10-30/compras-receber-compact"
RT=$(mktemp -d /tmp/shopman-compras-compact.XXXX)
mkdir -p "$RT/A"; git -C "$REPO" archive origin/main surfaces/purchase-nuxt surfaces/operator-kit | tar -x -C "$RT/A"
for app in operator-kit purchase-nuxt; do (cd "$RT/A/surfaces/$app" && npm ci --ignore-scripts --no-audit --no-fund); done
cp -cR "$RT/A" "$RT/C" 2>/dev/null || cp -R "$RT/A" "$RT/C"
node "$HERE/apply-compact.mjs" "$RT/C/surfaces/purchase-nuxt"
export NUXT_DJANGO_BASE_URL=http://127.0.0.1:38930 NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:38930
(cd "$RT/A/surfaces/purchase-nuxt" && npx nuxt build) & (cd "$RT/C/surfaces/purchase-nuxt" && npx nuxt build) & wait
MOCK_PORT=38930 PURCHASE_MOCK_SCENARIO=normal node "$RT/A/surfaces/purchase-nuxt/tests/visual/mockBackend.mjs" & m=$!
(cd "$RT/A/surfaces/purchase-nuxt" && HOST=127.0.0.1 PORT=4321 node .output/server/index.mjs) & a=$!
(cd "$RT/C/surfaces/purchase-nuxt" && HOST=127.0.0.1 PORT=4322 node .output/server/index.mjs) & c=$!
trap 'kill $m $a $c 2>/dev/null || true' EXIT INT TERM
sleep 4
if [ "${EVIDENCE:-0}" = 1 ]; then
  mkdir -p "$HERE/shots"
  node "$HERE/evidence.mjs" "$RT/A/surfaces/purchase-nuxt/node_modules/playwright/index.mjs" "$HERE/shots"
fi
echo "A http://127.0.0.1:4321/receive  C http://127.0.0.1:4322/receive  (cadastros: /base/materials)"
wait
