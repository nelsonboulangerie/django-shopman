#!/usr/bin/env bash
# Comparação A/B supervisionada (OC-23; plano da Etapa II omnicanal §9.6, docs/guides/comparacao-ab-supervisionada.md).
#
# As jornadas essenciais do §5.1 (surfaces/storefront-nuxt/tests/e2e/journeys) rodam duas
# vezes na pilha das jornadas (scripts/run_storefront_journeys.sh), uma por versão:
#
#   A: seed `qa` + experimento `prova-e2e` com a coorte internal = CLI-005 (a cliente da
#      jornada, CLI-003, fica FORA e o servidor decide "a");
#   B: o mesmo seed + o mesmo experimento com a coorte internal = CLI-003 (ela fica DENTRO
#      e o servidor decide "b").
#
# Mesmo seed, mesma cliente, mesmas jornadas; só a allow-list muda, e quem decide a versão
# é o servidor (D1), nunca a URL. A regra é gravada antes de o Django subir (sem Redis o
# cache das regras é por processo). Depois das duas rodadas, o relatório
# (surfaces/storefront-nuxt/scripts/experience-compare-report.mjs) junta as capturas, o
# axe, X9, X11 e a diferença do shell (X13) em <saída>/relatorio.html e relatorio.md.
#
#   DATABASE_URL=postgres://localhost:5432/<banco só de jornada> scripts/run_experience_compare.sh
#   ... scripts/run_experience_compare.sh 02-retirada-hoje   # filtro do Playwright, nas duas rodadas
#
# Os experimentos ligados são o de prova do harness e TODOS os que a loja anota com
# `EXPERIMENT(<ref>)` (surfaces/storefront-nuxt/app), com a mesma coorte: a rodada B vê
# toda a versão B que existe no código (OC-33 B2 em diante), sem lista à mão para
# envelhecer. EXPERIENCE_REFS="ref1,ref2" restringe.
#
# A pilha usa as portas JOURNEYS_*_PORT do run_storefront_journeys.sh. Rode sob a trava de
# prévia da máquina: `lockf /tmp/shopman-previa.lock make experience-compare`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
PYTHON_BIN="${PYTHON:-${ROOT}/.venv/bin/python}"
STORE_DIR="${ROOT}/surfaces/storefront-nuxt"
OUT="${EXPERIENCE_OUT:-${STORE_DIR}/test-results/experience-compare}"
: "${DATABASE_URL:?DATABASE_URL de um banco só de jornada (o seed o apaga, duas vezes)}"

if [[ -z "${EXPERIENCE_REFS:-}" ]]; then
  EXPERIENCE_REFS="$(
    { echo prova-e2e; grep -rhoE 'EXPERIMENT\([a-z0-9_-]+\)' "${STORE_DIR}/app" | sed -E 's/EXPERIMENT\((.*)\)/\1/'; } \
      | awk '!seen[$0]++' | paste -sd, -
  )"
fi
export EXPERIENCE_REFS
EXPERIMENT_ARGS=""
for ref in ${EXPERIENCE_REFS//,/ }; do EXPERIMENT_ARGS+=" --experiment ${ref}"; done
echo "── Experimentos: ${EXPERIENCE_REFS} ──"

rm -rf "${OUT}/a" "${OUT}/b" "${OUT}/relatorio.html" "${OUT}/relatorio.md"
mkdir -p "${OUT}"

if [[ "${EXPERIENCE_SKIP_BUILD:-0}" != "1" ]]; then
  echo "── Build da loja (uma vez, para as duas rodadas) ──"
  (cd "${STORE_DIR}" && npx nuxt build) >"${OUT}/build-loja.log" 2>&1
fi

status=0
for variant in a b; do
  if [[ "${variant}" == "a" ]]; then cohort="CLI-005"; else cohort="CLI-003"; fi
  echo "── Rodada $(echo "${variant}" | tr a-z A-Z): coorte internal = ${cohort}, cliente da jornada = CLI-003 ──"
  EXPERIENCE_VARIANT="${variant}" \
  EXPERIENCE_OUT="${OUT}" \
  JOURNEYS_PLAYWRIGHT_CONFIG=playwright.experience.config.ts \
  JOURNEYS_SKIP_BUILD=1 \
  JOURNEYS_WITH_GESTOR=0 \
  JOURNEYS_AFTER_SEED="'${PYTHON_BIN}' -m shopman.shop.tests.e2e.seed_experience --cohort ${cohort}${EXPERIMENT_ARGS}" \
    bash "${ROOT}/scripts/run_storefront_journeys.sh" "$@" || status=1
done

echo "── Relatório ──"
node "${STORE_DIR}/scripts/experience-compare-report.mjs" "${OUT}"
exit "${status}"
