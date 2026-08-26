#!/usr/bin/env bash
# Admin CSP gate com settings de PRODUÇÃO (DEBUG=false).
#
# "DEBUG local não prova CSP": o config/settings.py adiciona 'unsafe-inline' ao
# script-src quando DEBUG=true, então inline que passa na máquina de dev é
# BLOQUEADO em produção — e as telas Django-rendered do Admin/Unfold são as
# expostas. Este gate sobe o Django com DJANGO_DEBUG=false + o mesmo formato de
# env do `check --deploy` do Runtime Gate (secret forte, hosts explícitos,
# adapters mock declarados), faz login no /admin/ com Playwright e navega as
# telas coletando violação de CSP (evento `securitypolicyviolation` + console
# "Refused to ..."). Qualquer violação fora da lista de dívida reprova; o header
# Content-Security-Policy é conferido tela a tela (sem 'unsafe-inline' no
# script-src).
#
# Fonte única, rodável idêntico local e no CI (espelha run_storefront_e2e.sh):
#
#     DATABASE_URL=postgres://... bash scripts/run_admin_csp_gate.sh
#
# ⚠️ Local: o seed só CRIA o superuser `admin` se ele não existe — num banco
# reaproveitado com outra senha, o login do teste falha. Use um banco dedicado
# (ou exporte ADMIN_PASSWORD com a senha que o banco já tem).
set -euo pipefail

PYTHON_BIN="${PYTHON:-.venv/bin/python}"
DJANGO_PORT="${SHOPMAN_CSP_PORT:-8001}"
DJANGO_BASE_URL="http://127.0.0.1:${DJANGO_PORT}"
DJANGO_LOG="${SHOPMAN_CSP_SERVER_LOG:-/tmp/shopman-admin-csp-django.log}"

# ── Env de produção — espelho do bloco "Deploy checks" do runtime-gate.yml ──
# Overridável por quem chama; o DEBUG=false não é, porque é o ponto do gate.
export DJANGO_DEBUG=false
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-ci-omotenashi-csp-nonprod-aB3dE5gH7jK9mN2pQ4rS6tU8vW0xY1zC20260826}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"
export CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS:-http://localhost:${DJANGO_PORT},http://127.0.0.1:${DJANGO_PORT}}"
export AUTH_DEFAULT_DOMAIN="${AUTH_DEFAULT_DOMAIN:-shopman-ci.example}"
export DOORMAN_ACCESS_LINK_API_KEY="${DOORMAN_ACCESS_LINK_API_KEY:-ci-doorman-access-link-key}"
export EFI_WEBHOOK_TOKEN="${EFI_WEBHOOK_TOKEN:-ci-efi-webhook-token}"
export IFOOD_WEBHOOK_TOKEN="${IFOOD_WEBHOOK_TOKEN:-ci-ifood-webhook-token}"
export MANYCHAT_API_TOKEN="${MANYCHAT_API_TOKEN:-ci-manychat-api-token}"
export MANYCHAT_WEBHOOK_SECRET="${MANYCHAT_WEBHOOK_SECRET:-ci-manychat-webhook-secret}"
# CI has no real payment credentials — mock adapters with the explicit staging
# allowance (same rationale as the Runtime Gate deploy check).
export SHOPMAN_PIX_ADAPTER="${SHOPMAN_PIX_ADAPTER:-shopman.shop.adapters.payment_mock}"
export SHOPMAN_CARD_ADAPTER="${SHOPMAN_CARD_ADAPTER:-shopman.shop.adapters.payment_mock}"
export SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS="${SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS:-true}"
# runserver local fala http; sem isto o redirect para https (default fora de
# DEBUG) devolveria 301 em tudo e o gate testaria um servidor inalcançável.
export DJANGO_SECURE_SSL_REDIRECT="${DJANGO_SECURE_SSL_REDIRECT:-false}"
# A topologia do staging: DEBUG=false com flush permitido. Sem isto o env vira
# "production" (default fora de DEBUG) e o guard do seed recusa o `--flush`.
export SHOPMAN_ENVIRONMENT="${SHOPMAN_ENVIRONMENT:-staging}"
# Fora de DEBUG o seed EXIGE senha forte — e é com ela que o teste faz login.
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-ci-omotenashi-csp-admin-2026-forte}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL é obrigatório (Postgres): o gate roda como a produção roda." >&2
  exit 1
fi
if [[ -z "${REDIS_URL:-}" ]]; then
  echo "REDIS_URL é obrigatório: fora de DEBUG o cache LocMem reprova no system check (django_ratelimit.E003)." >&2
  exit 1
fi

DJANGO_PID=""
cleanup() {
  if [[ -n "${DJANGO_PID}" ]]; then
    kill "${DJANGO_PID}" >/dev/null 2>&1 || true
    wait "${DJANGO_PID}" >/dev/null 2>&1 || true
  fi
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

# ── Playwright browser (chromium) — install if missing ──
"${PYTHON_BIN}" -m playwright install chromium >/dev/null

# ── Migrate + seed + collectstatic, tudo já fora de DEBUG (como o deploy) ──
"${PYTHON_BIN}" manage.py migrate --noinput
"${PYTHON_BIN}" manage.py seed --flush
"${PYTHON_BIN}" manage.py collectstatic --noinput -v 0

# ── Servidor com settings de produção ──
"${PYTHON_BIN}" manage.py runserver --noreload "127.0.0.1:${DJANGO_PORT}" >"${DJANGO_LOG}" 2>&1 &
DJANGO_PID=$!
wait_for "${DJANGO_BASE_URL}/ready/" "${DJANGO_PID}" "Servidor Django (DEBUG=false)" "${DJANGO_LOG}"

# ── Navegar o Admin coletando violações de CSP ──
# `-m browser` re-seleciona a suíte que o config default de-seleciona.
"${PYTHON_BIN}" -m pytest shopman/shop/tests/e2e/test_admin_csp.py \
  -m browser \
  --operator-base-url="${DJANGO_BASE_URL}" \
  "$@"
