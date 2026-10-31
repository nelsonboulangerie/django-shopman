#!/usr/bin/env bash
# PRÉVIA. Node 22. Cópias temporárias e dados fictícios; não escreve em surfaces/.
# A = origin/main intacto (+ só a simulação de conexão `?conn=`), C = A + apply-compact.
# Portas: mock 38920, A 4311, C 4312. Evidência: EVIDENCE=1 ./run.sh
set -euo pipefail
export PATH=/opt/homebrew/opt/node@22/bin:$PATH
REPO=$(git rev-parse --show-toplevel)
HERE="$REPO/docs/previews/consolidacao-2026-10-30/gestor-compact"
RT=$(mktemp -d /tmp/shopman-gestor-compact.XXXX)
mkdir -p "$RT/A"; git -C "$REPO" archive origin/main surfaces/orders-nuxt surfaces/operator-kit | tar -x -C "$RT/A"
for app in operator-kit orders-nuxt; do (cd "$RT/A/surfaces/$app" && npm ci --ignore-scripts --no-audit --no-fund); done
cp -cR "$RT/A" "$RT/C" 2>/dev/null || cp -R "$RT/A" "$RT/C"
export ORDERS_VISUAL_CLIENT_ONLY=1 NUXT_DJANGO_BASE_URL=http://127.0.0.1:38920 NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:38920
(cd "$RT/A/surfaces/orders-nuxt" && node "$HERE/apply-conn-sim.mjs" "$PWD" && npx nuxt build)
(cd "$RT/C/surfaces/orders-nuxt" && node "$HERE/apply-conn-sim.mjs" "$PWD" && node "$HERE/apply-compact.mjs" "$PWD" && npx nuxt build)
(cd "$RT/A/surfaces/orders-nuxt" && MOCK_PORT=38920 node tests/visual/mockBackend.mjs) & m=$!
(cd "$RT/A/surfaces/orders-nuxt" && HOST=127.0.0.1 PORT=4311 node .output/server/index.mjs) & a=$!
(cd "$RT/C/surfaces/orders-nuxt" && HOST=127.0.0.1 PORT=4312 node .output/server/index.mjs) & c=$!
trap 'kill $m $a $c 2>/dev/null || true' EXIT INT TERM
sleep 3
echo "A http://127.0.0.1:4311/  C http://127.0.0.1:4312/  (cenário: curl 127.0.0.1:38920/__visual/scenario?set=normal|dense|empty|error|gallery)"
if [ "${EVIDENCE:-}" = 1 ]; then node "$HERE/evidence.mjs" "$RT/A/surfaces/orders-nuxt" "$HERE"; fi
wait
