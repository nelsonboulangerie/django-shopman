#!/usr/bin/env bash
# PRÉVIA A × C do PDV (modo compacto). Node 22. Cópias temporárias e dados fictícios;
# não escreve em surfaces/. A = origin/main intacto. C = A + apply-compact.mjs.
# Simulador: o da prévia anterior (prepare-mock + mock-extension de
# origin/codex/shopman-ux-product-review, docs/previews/navigation-2026-10-29/native)
# + mock-patch.mjs (Avisos e consulta de cliente). Portas fixas: mock 38910, A 4301, C 4302.
# Evidência: node evidence.mjs "$RT/A/surfaces/pos-nuxt" "$HERE" com os três de pé.
set -euo pipefail
export PATH=/opt/homebrew/opt/node@22/bin:$PATH
REPO=$(git rev-parse --show-toplevel)
HERE="$REPO/docs/previews/consolidacao-2026-10-30/pdv-compact"
PREV_REF=${PREV_REF:-origin/codex/shopman-ux-product-review}
RT=$(mktemp -d /tmp/shopman-pdv-compact.XXXX)
git -C "$REPO" archive "$PREV_REF" docs/previews/navigation-2026-10-29/native | tar -x -C "$RT"
P="$RT/docs/previews/navigation-2026-10-29/native"
mkdir -p "$RT/A" "$RT/mock"
git -C "$REPO" archive origin/main surfaces/pos-nuxt surfaces/operator-kit | tar -x -C "$RT/A"
for app in operator-kit pos-nuxt; do (cd "$RT/A/surfaces/$app" && npm ci --ignore-scripts --no-audit --no-fund); done
cp -cR "$RT/A" "$RT/C" 2>/dev/null || cp -R "$RT/A" "$RT/C"
node "$P/prepare-mock.mjs" "$RT/A/surfaces/pos-nuxt/tests/visual/mockBackend.mjs" "$RT/mock/mockBackend.mjs"
node "$HERE/mock-patch.mjs" "$RT/mock/mockBackend.mjs"
export POS_VISUAL_CLIENT_ONLY=1 NUXT_APP_BASE_URL=/
export NUXT_DJANGO_BASE_URL=http://127.0.0.1:38910 NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:38910
(cd "$RT/A/surfaces/pos-nuxt" && npx nuxt build)
(cd "$RT/C/surfaces/pos-nuxt" && node "$HERE/apply-compact.mjs" "$PWD" && npx nuxt build)
MOCK_PORT=38910 MOCK_SCENARIO=sale MOCK_TODAY=2026-09-29 node "$RT/mock/mockBackend.mjs" & m=$!
(cd "$RT/A/surfaces/pos-nuxt" && HOST=127.0.0.1 PORT=4301 node .output/server/index.mjs) & a=$!
(cd "$RT/C/surfaces/pos-nuxt" && HOST=127.0.0.1 PORT=4302 node .output/server/index.mjs) & c=$!
trap 'kill $m $a $c 2>/dev/null || true' EXIT INT TERM
echo "A http://127.0.0.1:4301/preorders  C http://127.0.0.1:4302/preorders  (runtime: $RT)"
wait
