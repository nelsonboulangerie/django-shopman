#!/usr/bin/env bash
# Omotenashi browser-QA gate against the surfaces that ACTUALLY exist:
# a loja do cliente + os quatro apps de operador, todos em Nuxt, com o Django
# servindo API e Admin/Unfold.
#
# The headless cutover retired the Django customer PAGES, so the old gate (which
# navigated them) was dropped from CI. This orchestration brings it back, rebuilt
# for the real topology:
#   · Django serves the API + Admin pages (relative matrix URLs).
#   · A loja Nuxt serve as páginas do cliente (SHOPMAN_STOREFRONT_BASE_URL).
#   · Gestor de Pedidos, KDS, Produção e PDV servem as telas de operador
#     (SHOPMAN_{ORDERS,KDS,PRODUCTION,POS}_BASE_URL → operator_links/pos_links →
#     matriz omotenashi_qa).
#
# ⚠️ Até 20/08/2026 este gate subia SÓ a loja. Os seis checks de operador — fila
# de pedidos, KDS, produção, PDV, fechamento do dia e caixa — nasciam com URL
# vazia e eram pulados com um aviso, sem reprovar: nenhum browser automatizado
# jamais tocou nas telas por onde o dinheiro passa, e o relatório dizia "11
# checks" como se as tivesse visto. Agora todas sobem, e `--strict` reprova tanto
# em check pulado quanto em navegação que não chegou ao servidor.
#
# It is the single source for the gate, runnable identically locally and in CI:
# seed Django, build + serve every surface pointing at the Django API, then drive
# the Omotenashi matrix in headless Chrome (--strict) and tear everything down.
set -euo pipefail

PYTHON_BIN="${PYTHON:-.venv/bin/python}"
NUXT_DIR="${SHOPMAN_QA_NUXT_DIR:-surfaces/storefront-nuxt}"

DJANGO_PORT="${SHOPMAN_QA_PORT:-${PORT:-8001}}"
NUXT_PORT="${SHOPMAN_QA_NUXT_PORT:-3100}"
DJANGO_BASE_URL="http://127.0.0.1:${DJANGO_PORT}"
STOREFRONT_BASE_URL="http://127.0.0.1:${NUXT_PORT}"

# ⚠️ As superfícies de OPERADOR também sobem aqui. Enquanto elas ficavam de fora,
# os seis checks delas (fila de pedidos, KDS, produção, PDV, fechamento do dia e
# caixa) nasciam com `url = ""` e o runner os PULAVA em silêncio — nenhum browser
# automatizado jamais tocou nas telas por onde o dinheiro passa, e o gate ficava
# verde. Agora o `--strict` reprova em check pulado, então "não subiu" vira
# vermelho em vez de virar nada.
ORDERS_PORT="${SHOPMAN_QA_ORDERS_PORT:-3101}"
KDS_PORT="${SHOPMAN_QA_KDS_PORT:-3102}"
PRODUCTION_PORT="${SHOPMAN_QA_PRODUCTION_PORT:-3103}"
POS_PORT="${SHOPMAN_QA_POS_PORT:-3104}"

DJANGO_LOG="${SHOPMAN_QA_SERVER_LOG:-/tmp/shopman-omotenashi-browser-ci-django.log}"
NUXT_LOG="${SHOPMAN_QA_NUXT_LOG:-/tmp/shopman-omotenashi-browser-ci-nuxt.log}"

# Customer links the matrix builds (PDP, checkout, tracking, payment) must resolve
# to the Nuxt store; operator links resolve to the operator apps. Estes knobs são
# lidos por storefront_links/operator_links/pos_links → matriz omotenashi_qa.
export SHOPMAN_STOREFRONT_BASE_URL="${STOREFRONT_BASE_URL}"
export SHOPMAN_ORDERS_BASE_URL="http://127.0.0.1:${ORDERS_PORT}"
export SHOPMAN_KDS_BASE_URL="http://127.0.0.1:${KDS_PORT}"
export SHOPMAN_PRODUCTION_BASE_URL="http://127.0.0.1:${PRODUCTION_PORT}"
export SHOPMAN_POS_BASE_URL="http://127.0.0.1:${POS_PORT}"

DJANGO_PID=""
NUXT_PIDS=()
cleanup() {
  for pid in "${NUXT_PIDS[@]:-}" "${DJANGO_PID}"; do
    if [[ -n "${pid}" ]]; then
      kill "${pid}" >/dev/null 2>&1 || true
      wait "${pid}" >/dev/null 2>&1 || true
    fi
  done
}
trap cleanup EXIT INT TERM

wait_for() {
  local url="$1" pid="$2" label="$3" log="$4"
  for _ in $(seq 1 90); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      echo "${label} encerrou antes de ficar pronto. Log:" >&2
      tail -120 "${log}" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "${label} nao ficou pronto em ${url}. Log:" >&2
  tail -120 "${log}" >&2 || true
  return 1
}

# ── Django: migrate + canonical seed (deterministic Omotenashi scenarios) ──
"${PYTHON_BIN}" manage.py migrate --noinput
"${PYTHON_BIN}" manage.py seed --flush

# ── Superfícies Nuxt: instalar (se preciso) + build de produção ──
# Os apps de operador estendem a layer `operator-kit`, cujo node_modules precisa
# existir para o build resolver 'vue'/'@vueuse/core' (mesma razão do Surfaces Gate).
build_surface() {
  local dir="$1" label="$2"
  if [[ ! -d "${dir}/node_modules" ]]; then
    echo "── Instalando dependências: ${label} ──"
    (cd "${dir}" && npm ci)
  fi
  echo "── Build: ${label} ──"
  (cd "${dir}" && npm run build)
}

if [[ ! -d "surfaces/operator-kit/node_modules" ]]; then
  echo "── Instalando dependências: operator-kit (layer) ──"
  (cd surfaces/operator-kit && npm ci)
fi

build_surface "${NUXT_DIR}" "loja Nuxt"
build_surface "surfaces/orders-nuxt" "Gestor de Pedidos"
build_surface "surfaces/kds-nuxt" "KDS"
build_surface "surfaces/production-nuxt" "Produção"
build_surface "surfaces/pos-nuxt" "PDV"

# ── Start Django (API + Admin/Unfold) ──
"${PYTHON_BIN}" manage.py runserver --noreload "127.0.0.1:${DJANGO_PORT}" >"${DJANGO_LOG}" 2>&1 &
DJANGO_PID=$!
wait_for "${DJANGO_BASE_URL}/ready/" "${DJANGO_PID}" "Servidor Django" "${DJANGO_LOG}"

serve_surface() {
  local dir="$1" port="$2" label="$3" log="$4"
  # NUXT_APP_BASE_URL=/ espelha o deployment (.do/app.subdomains.yaml): cada app
  # vive na RAIZ do seu subdomínio. Sem isto, KDS e PDV assumem o prefixo /kds/
  # e /pos/ do default de produção e as URLs que `operator_links`/`pos_links`
  # constroem (sem prefixo) cairiam fora do app — o gate testaria um caminho que
  # o Django nunca gera.
  HOST=127.0.0.1 PORT="${port}" \
    NUXT_APP_BASE_URL="/" \
    NUXT_DJANGO_BASE_URL="${DJANGO_BASE_URL}" \
    NUXT_PUBLIC_DJANGO_BASE_URL="${DJANGO_BASE_URL}" \
    node "${dir}/.output/server/index.mjs" >"${log}" 2>&1 &
  local pid=$!
  NUXT_PIDS+=("${pid}")
  wait_for "http://127.0.0.1:${port}/" "${pid}" "${label}" "${log}"
}

serve_surface "${NUXT_DIR}" "${NUXT_PORT}" "Loja Nuxt" "${NUXT_LOG}"
serve_surface "surfaces/orders-nuxt" "${ORDERS_PORT}" "Gestor de Pedidos" "/tmp/shopman-omotenashi-browser-ci-orders.log"
serve_surface "surfaces/kds-nuxt" "${KDS_PORT}" "KDS" "/tmp/shopman-omotenashi-browser-ci-kds.log"
serve_surface "surfaces/production-nuxt" "${PRODUCTION_PORT}" "Produção" "/tmp/shopman-omotenashi-browser-ci-production.log"
serve_surface "surfaces/pos-nuxt" "${POS_PORT}" "PDV" "/tmp/shopman-omotenashi-browser-ci-pos.log"

# Navigate the matrix: --base-url is Django (operator relative URLs + /health/),
# while the storefront checks are already absolute Nuxt URLs from the matrix.
PYTHON="${PYTHON_BIN}" node scripts/run_omotenashi_browser_qa.mjs --strict --base-url="${DJANGO_BASE_URL}"
