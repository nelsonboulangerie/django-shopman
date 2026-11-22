#!/usr/bin/env bash
# Jornadas da cliente (surfaces/storefront-nuxt/tests/journeys) numa pilha que este script
# sobe e derruba: banco do DATABASE_URL, seed `qa` com a loja aberta 24 h, Django e worker
# com o settings do harness, o proxy lento da J9, a loja e o Gestor compilados. É a pilha da
# seção 3 do README do e2e, em um comando, igual no computador e na CI (#2611).
#
#   DATABASE_URL=postgres://… scripts/run_storefront_journeys.sh            # todas
#   DATABASE_URL=postgres://… scripts/run_storefront_journeys.sh j7 --grep J7
#   JOURNEYS_CLOSING_IN_MINUTES=4 DATABASE_URL=postgres://… scripts/run_storefront_journeys.sh j5 --grep J5
#
# Com JOURNEYS_CLOSING_IN_MINUTES=N a pilha é a da casa que fecha (J5): hoje a loja abre à
# 0h e fecha daqui a N minutos (`seed --closing-in-minutes`), sem o 24 h. Só a J5 serve
# nessa pilha; as outras precisam da loja aberta.
#
# O banco é APAGADO pelo seed (`--flush`): use um banco só de jornada, nunca o de dev.
# Só mata o que este script subiu.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
PYTHON_BIN="${PYTHON:-${ROOT}/.venv/bin/python}"
STORE_DIR="${ROOT}/surfaces/storefront-nuxt"
GESTOR_DIR="${ROOT}/surfaces/orders-nuxt"

: "${DATABASE_URL:?DATABASE_URL de um banco só de jornada (o seed o apaga)}"

DJANGO_PORT="${JOURNEYS_DJANGO_PORT:-8090}"
PROXY_PORT="${JOURNEYS_PROXY_PORT:-8091}"
STRIPE_PORT="${JOURNEYS_STRIPE_PORT:-12190}"
MANYCHAT_PORT="${JOURNEYS_MANYCHAT_PORT:-12191}"
STORE_PORT="${JOURNEYS_STORE_PORT:-3190}"
GESTOR_PORT="${JOURNEYS_GESTOR_PORT:-3194}"
# Hosts próprios: o navegador divide os cookies de um host entre as portas.
STORE_URL="http://loja.jornadas.localhost:${STORE_PORT}"
GESTOR_URL="http://gestor.jornadas.localhost:${GESTOR_PORT}"
DJANGO_URL="http://127.0.0.1:${DJANGO_PORT}"
LOGS="${JOURNEYS_LOG_DIR:-/tmp/shopman-jornadas}"
mkdir -p "${LOGS}" && chmod 700 "${LOGS}"

export DJANGO_DEBUG=true DJANGO_ALLOWED_HOSTS='*'
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-dev-local-jornadas-1234567890}"
unset REDIS_URL
# O código de entrada sai num arquivo, como o SMS da cliente.
export SHOPMAN_E2E_OTP_FILE="${LOGS}/code"
export DOORMAN_MESSAGE_SENDER_CLASS=shopman.shop.tests.e2e.otp_sender.E2EFileSender
export SHOPMAN_OTP_DELIVERY_CHAIN=""
# O cartão vai ao Stripe FALSO do harness (`shopman/shop/tests/e2e/fake_stripe.py`): o
# adapter de produção roda inteiro e só o endereço da API muda. Com captura, anulação e
# estorno (F-7, #2568), as jornadas de cartão (J6, J8) rodam nesta pilha.
export SHOPMAN_E2E_STRIPE_API_BASE="http://127.0.0.1:${STRIPE_PORT}"
export STRIPE_SECRET_KEY=sk_test_e2e_fake_local_only
export STRIPE_PUBLISHABLE_KEY=pk_test_e2e_fake_local_only
export STRIPE_WEBHOOK_SECRET=whsec_e2e_fake_local_only
# O WhatsApp vai ao ManyChat FALSO do harness (`shopman/shop/tests/e2e/fake_manychat.py`,
# #3272): o `notification_manychat` de produção manda a resposta do login de verdade, e a
# jornada lê os botões dela ("Liberar o Chrome", "Encerrar acesso") no que o fake guardou.
# O token falso é posto pelo `settings_e2e`, e só no adapter: o MANYCHAT_API_TOKEN de topo
# fica vazio, e o resolvedor do Guestman (endereço fixo do ManyChat real) não chama nada.
MANYCHAT_URL="http://127.0.0.1:${MANYCHAT_PORT}"
export MANYCHAT_API_BASE="${MANYCHAT_URL}/fb"
unset MANYCHAT_API_TOKEN
export SHOPMAN_STOREFRONT_BASE_URL="${STORE_URL}"
export SHOPMAN_ORDERS_BASE_URL="${GESTOR_URL}"
export CSRF_TRUSTED_ORIGINS="${STORE_URL},${GESTOR_URL}"

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    [[ -n "${pid}" ]] || continue
    kill "${pid}" >/dev/null 2>&1 || true
    wait "${pid}" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

wait_for () {
  local url="$1" host="$2" what="$3" log="$4"
  for _ in $(seq 1 120); do
    if curl -s -o /dev/null -w "%{http_code}" -H "Host: ${host}" "${url}" 2>/dev/null | grep -qE '^(200|302)$'; then return 0; fi
    sleep 1
  done
  echo "── ${what} não respondeu; fim do log:" >&2
  tail -40 "${log}" >&2 || true
  exit 1
}

for port in "${DJANGO_PORT}" "${PROXY_PORT}" "${STORE_PORT}" "${GESTOR_PORT}" "${STRIPE_PORT}" "${MANYCHAT_PORT}"; do
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Porta ${port} ocupada: outro servidor responderia no lugar desta pilha." >&2
    exit 1
  fi
done

# Os builds vêm antes do seed: na pilha da casa que fecha (J5), o relógio começa a contar
# no seed, e minutos de build não podem comer o tempo até o fechamento.
echo "── Builds da loja e do Gestor ──"
(cd "${STORE_DIR}" && npx nuxt build) >"${LOGS}/build-loja.log" 2>&1
(cd "${GESTOR_DIR}" && npx nuxt build) >"${LOGS}/build-gestor.log" 2>&1

"${PYTHON_BIN}" manage.py migrate --noinput
if [[ -n "${JOURNEYS_CLOSING_IN_MINUTES:-}" ]]; then
  echo "── Banco e seed (a casa fecha daqui a ${JOURNEYS_CLOSING_IN_MINUTES} min) ──"
  "${PYTHON_BIN}" manage.py seed --flush --profile qa --closing-in-minutes "${JOURNEYS_CLOSING_IN_MINUTES}"
  export JOURNEY_STORE_CLOSING=1
else
  echo "── Banco e seed (loja aberta 24 h) ──"
  # O interruptor do piloto de staging abre a loja a qualquer hora; restrito a um canal que
  # não existe, ele não aceita pedido nenhum sozinho. Só o seed o recebe.
  SHOPMAN_STAGING_AUTOPILOT=true SHOPMAN_STAGING_AUTOPILOT_CHANNELS=nenhum-canal \
    "${PYTHON_BIN}" manage.py seed --flush --profile qa
fi

echo "── Pilha ──"
# Stripe falso: a sessão hospedada, o webhook assinado de volta ao Django, e o que vem
# depois do pagamento (captura, anulação, estorno).
"${PYTHON_BIN}" -m shopman.shop.tests.e2e.fake_stripe \
  --port "${STRIPE_PORT}" \
  --webhook-url "${DJANGO_URL}/api/webhooks/stripe/" \
  --webhook-secret "${STRIPE_WEBHOOK_SECRET}" >"${LOGS}/stripe.log" 2>&1 &
PIDS+=("$!")
# ManyChat falso: aceita o que a casa manda pelo WhatsApp e guarda, para a jornada ler.
"${PYTHON_BIN}" -m shopman.shop.tests.e2e.fake_manychat --port "${MANYCHAT_PORT}" >"${LOGS}/manychat.log" 2>&1 &
PIDS+=("$!")
DJANGO_SETTINGS_MODULE=shopman.shop.tests.e2e.settings_e2e \
  "${PYTHON_BIN}" manage.py runserver "127.0.0.1:${DJANGO_PORT}" --noreload >"${LOGS}/django.log" 2>&1 &
PIDS+=("$!")
DJANGO_SETTINGS_MODULE=shopman.shop.tests.e2e.settings_e2e \
  "${PYTHON_BIN}" manage.py process_directives --watch >"${LOGS}/worker.log" 2>&1 &
PIDS+=("$!")
wait_for "${DJANGO_URL}/health/live/" "127.0.0.1" "Django" "${LOGS}/django.log"
wait_for "${SHOPMAN_E2E_STRIPE_API_BASE}/health" "127.0.0.1" "Stripe falso" "${LOGS}/stripe.log"
wait_for "${MANYCHAT_URL}/health" "127.0.0.1" "ManyChat falso" "${LOGS}/manychat.log"

# Proxy lento da J9: só da pilha de teste, entre a loja e o Django.
SLOW_PROXY_PORT="${PROXY_PORT}" SLOW_PROXY_TARGET="${DJANGO_URL}" \
  node "${STORE_DIR}/tests/journeys/support/slow-proxy.mjs" >"${LOGS}/proxy.log" 2>&1 &
PIDS+=("$!")

HOST=127.0.0.1 PORT="${STORE_PORT}" NUXT_DJANGO_BASE_URL="http://127.0.0.1:${PROXY_PORT}" \
  node "${STORE_DIR}/.output/server/index.mjs" >"${LOGS}/loja.log" 2>&1 &
PIDS+=("$!")
HOST=127.0.0.1 PORT="${GESTOR_PORT}" NUXT_DJANGO_BASE_URL="${DJANGO_URL}" NUXT_PUBLIC_DJANGO_BASE_URL="${DJANGO_URL}" \
  node "${GESTOR_DIR}/.output/server/index.mjs" >"${LOGS}/gestor.log" 2>&1 &
PIDS+=("$!")
wait_for "http://127.0.0.1:${STORE_PORT}/sacola" "loja.jornadas.localhost:${STORE_PORT}" "Loja" "${LOGS}/loja.log"
wait_for "http://127.0.0.1:${GESTOR_PORT}/" "gestor.jornadas.localhost:${GESTOR_PORT}" "Gestor" "${LOGS}/gestor.log"

echo "── Jornadas ──"
cd "${STORE_DIR}"
JOURNEY_STORE_URL="${STORE_URL}" \
JOURNEY_GESTOR_URL="${GESTOR_URL}" \
JOURNEY_DJANGO_URL="${DJANGO_URL}" \
JOURNEY_MANYCHAT_URL="${MANYCHAT_URL}" \
JOURNEY_OTP_FILE="${SHOPMAN_E2E_OTP_FILE}" \
JOURNEY_PROXY_CONTROL="http://127.0.0.1:${PROXY_PORT}" \
  npx playwright test --config=playwright.journeys.config.ts "$@"
