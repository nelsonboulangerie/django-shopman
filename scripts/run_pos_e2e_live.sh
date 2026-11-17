#!/usr/bin/env bash
# Harness AO VIVO do PDV (WP-E12): um comando sobe a pilha inteira e entrega ao
# Playwright uma sessão de operador real.
#
#   Django semeado (banco próprio) + worker de directives
#   PDV compilado (pos-nuxt)  +  Cozinha compilada (kds-nuxt)
#   Playwright: tests/e2e-live/operador.live.spec.ts e as jornadas jN-*.live.spec.ts
#
# O teste entra PELA TELA: a Gerente com senha, o vínculo do posto, a trava e o
# PIN da Caixa. Nada de superusuário, `force_login`, API ou banco para chegar a um
# estado. A única escrita fora da tela é declarada abaixo (trava automática do
# terminal de teste em 900 s) e não muda regra de negócio.
#
# Uso (da raiz do repositório ou da worktree):
#   scripts/run_pos_e2e_live.sh                 # sobe, roda a fumaça + jornadas, derruba
#   scripts/run_pos_e2e_live.sh j2              # filtros do Playwright passam adiante
#   PDV_LIVE_KEEP=1 scripts/run_pos_e2e_live.sh # deixa a pilha de pé ao fim (escrever jornada)
#   PDV_LIVE_UP_ONLY=1 scripts/run_pos_e2e_live.sh  # só sobe a pilha e espera (Ctrl+C derruba)
#   PDV_LIVE_SKIP_BUILD=1 ...                   # reaproveita os .output já compilados
#   PDV_LIVE_SKIP_SEED=1 ...                    # reaproveita o banco (sem migrate/seed)
#
# Documentação completa: surfaces/pos-nuxt/tests/e2e-live/README.md.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
cd "${REPO}"
# Numa worktree o `.venv` mora na árvore principal (o diretório do .git comum).
MAIN_ROOT="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
PYTHON_BIN="${PYTHON:-${MAIN_ROOT}/.venv/bin/python}"

# ── A pilha: portas, banco e host próprios ─────────────────────────────────────
# O host próprio não é enfeite: o cookie de sessão é por HOST, não por porta, e
# outras pilhas usam 127.0.0.1 no mesmo navegador. Um `*.localhost` resolve para
# o loopback no Chromium sem mexer em /etc/hosts.
DJANGO_PORT="${PDV_LIVE_DJANGO_PORT:-8052}"
POS_PORT="${PDV_LIVE_POS_PORT:-3162}"
KDS_PORT="${PDV_LIVE_KDS_PORT:-3163}"
DB_NAME="${PDV_LIVE_DB:-shopman_pdv_e12}"
LIVE_HOST="${PDV_LIVE_HOST:-pdve12.localhost}"
AUTO_LOCK_SECONDS="${PDV_LIVE_AUTO_LOCK_SECONDS:-900}"

DJANGO_URL="http://127.0.0.1:${DJANGO_PORT}"
POS_URL="http://${LIVE_HOST}:${POS_PORT}"
KDS_URL="http://${LIVE_HOST}:${KDS_PORT}"

LOG_DIR="${PDV_LIVE_LOG_DIR:-${TMPDIR:-/tmp}/shopman-pdv-live-${DJANGO_PORT}}"
mkdir -p "${LOG_DIR}"
DJANGO_LOG="${LOG_DIR}/django.log"
WORKER_LOG="${LOG_DIR}/worker.log"
POS_LOG="${LOG_DIR}/pos.log"
KDS_LOG="${LOG_DIR}/kds.log"

# ── Python: a worktree e cada packages/* na frente do .venv ────────────────────
# O `.venv` da raiz tem editable installs apontando para a árvore principal; sem
# isto a worktree testaria o código de outra pessoa.
PY_PATH="${REPO}"
for pkg in "${REPO}"/packages/*/; do PY_PATH="${PY_PATH}:${pkg%/}"; done

# psycopg descompassado do psycopg-binary (medido em 16/11: 3.3.6 × 3.3.5) quebra
# o Postgres com `wait_c() got an unexpected keyword argument 'timeout'`. Contorno
# sem tocar o `.venv` compartilhado: o psycopg da versão do binário numa pasta de
# cache, na frente do PYTHONPATH.
read -r PSYCOPG_V BINARY_V < <("${PYTHON_BIN}" - <<'PY'
import importlib.metadata as m
def v(name):
    try:
        return m.version(name)
    except m.PackageNotFoundError:
        return "-"
print(v("psycopg"), v("psycopg-binary"))
PY
)
if [[ "${BINARY_V}" != "-" && "${PSYCOPG_V}" != "${BINARY_V}" ]]; then
  SHIM="${XDG_CACHE_HOME:-${HOME}/.cache}/shopman-e2e/psycopg-${BINARY_V}"
  if [[ ! -d "${SHIM}/psycopg" ]]; then
    echo "── psycopg ${PSYCOPG_V} × psycopg-binary ${BINARY_V}: instalando psycopg ${BINARY_V} em ${SHIM}"
    "${PYTHON_BIN}" -m pip install -q --no-deps --target "${SHIM}" "psycopg==${BINARY_V}"
  fi
  PY_PATH="${SHIM}:${PY_PATH}"
fi
export PYTHONPATH="${PY_PATH}${PYTHONPATH:+:${PYTHONPATH}}"

# ── Ambiente do Django ─────────────────────────────────────────────────────────
export DATABASE_URL="postgres://localhost:5432/${DB_NAME}"
export DJANGO_DEBUG=true
export DJANGO_ALLOWED_HOSTS='*'
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-dev-local-pdv-live-harness-1234567890}"
# Pool de conexões ligado como no deploy: sem ele cada request abre conexão e a
# tela estoura o limite de 15 s numa máquina carregada.
export DATABASE_CONN_MAX_AGE=0
export SHOPMAN_OTP_DELIVERY_CHAIN=console
export SHOPMAN_POS_BASE_URL="${POS_URL}"
export SHOPMAN_KDS_BASE_URL="${KDS_URL}"
export CSRF_TRUSTED_ORIGINS="${POS_URL},${KDS_URL}"
unset REDIS_URL

manage() { "${PYTHON_BIN}" manage.py "$@"; }

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    [[ -n "${pid}" ]] || continue
    kill "${pid}" >/dev/null 2>&1 || true
    wait "${pid}" >/dev/null 2>&1 || true
  done
}

wait_for() {
  local url="$1" pid="$2" label="$3" log="$4"
  for _ in $(seq 1 180); do
    if curl -fsS -o /dev/null "${url}" 2>/dev/null; then return 0; fi
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      echo "${label} encerrou antes de ficar pronto. Log (${log}):" >&2
      tail -80 "${log}" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "${label} não ficou pronto em ${url}. Log (${log}):" >&2
  tail -80 "${log}" >&2 || true
  return 1
}

port_free() {
  local port="$1"
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "A porta ${port} já está ocupada (lsof -nP -iTCP:${port} -sTCP:LISTEN). Derrube a pilha anterior ou escolha outra porta." >&2
    exit 1
  fi
}
port_free "${DJANGO_PORT}"
port_free "${POS_PORT}"
port_free "${KDS_PORT}"

# ── Banco, migrate, seed ───────────────────────────────────────────────────────
if [[ "${PDV_LIVE_SKIP_SEED:-}" != "1" ]]; then
  if ! psql -lqt | cut -d'|' -f1 | grep -qw "${DB_NAME}"; then
    echo "── Criando o banco ${DB_NAME}"
    createdb "${DB_NAME}"
  fi
  echo "── migrate"
  # Migração com trava de produção (`SET LOCAL statement_timeout = '30s'`, ex.:
  # shop.0053) estoura em máquina carregada mesmo com tabela vazia (medido 17/11,
  # carga 90). Cada migração é atômica: tentar de novo continua de onde parou.
  migrated=0
  for attempt in 1 2 3; do
    if manage migrate --noinput >"${LOG_DIR}/migrate.log" 2>&1; then migrated=1; break; fi
    grep -q "statement timeout" "${LOG_DIR}/migrate.log" || break
    echo "   (tempo esgotado numa migração; tentativa ${attempt} de 3, continuando)"
  done
  [ "$migrated" = 1 ] || { tail -40 "${LOG_DIR}/migrate.log" >&2; exit 1; }
  echo "── seed --flush (o elenco de setup_operators vem junto: joyce, fran, diofer)"
  manage seed --flush >"${LOG_DIR}/seed.log" 2>&1 || { tail -40 "${LOG_DIR}/seed.log" >&2; exit 1; }
fi

# Ajuste DECLARADO do ambiente de teste: a trava automática do terminal de teste
# passa de 60 s para ${AUTO_LOCK_SECONDS} s. Com 60 s o PDV trava no meio de uma
# jornada lenta (máquina carregada) e o teste mede a trava, não a jornada. É
# config de terminal (`cashman_terminal.metadata.auto_lock_seconds`, a mesma que o
# Admin edita), não estado de venda; a jornada da trava por ociosidade (J9) baixa
# o valor por conta própria.
echo "── Trava automática do PDV principal: ${AUTO_LOCK_SECONDS} s"
manage shell -c "
from shopman.cashman.models import Terminal
t = Terminal.objects.get(ref='pdv-main')
t.metadata = {**(t.metadata or {}), 'auto_lock_seconds': ${AUTO_LOCK_SECONDS}}
t.save(update_fields=['metadata'])
print(f'   {t.label}: auto_lock_seconds={t.metadata[\"auto_lock_seconds\"]}')
"

# ── PDV e Cozinha compilados ───────────────────────────────────────────────────
# Build de produção, não `nuxt dev`: o dev recarrega sozinho e derruba jornada
# longa. Um por vez: com a máquina disputada, dois builds juntos (ou build e
# vitest juntos) levam muitos minutos cada.
for app in operator-kit pos-nuxt kds-nuxt; do
  if [[ ! -d "surfaces/${app}/node_modules" ]]; then
    echo "── npm ci em surfaces/${app}"
    (cd "surfaces/${app}" && npm ci --no-audit --no-fund --loglevel=error)
  fi
done
if [[ "${PDV_LIVE_SKIP_BUILD:-}" != "1" ]]; then
  for app in pos-nuxt kds-nuxt; do
    echo "── nuxt build ${app} (log em ${LOG_DIR}/build-${app}.log)"
    (cd "surfaces/${app}" && npx nuxt build) >"${LOG_DIR}/build-${app}.log" 2>&1 \
      || { tail -60 "${LOG_DIR}/build-${app}.log" >&2; exit 1; }
  done
fi
for app in pos-nuxt kds-nuxt; do
  [[ -f "surfaces/${app}/.output/server/index.mjs" ]] || { echo "surfaces/${app} sem .output: rode sem PDV_LIVE_SKIP_BUILD." >&2; exit 1; }
done

# ── Sobe tudo ──────────────────────────────────────────────────────────────────
trap cleanup EXIT INT TERM

manage runserver --noreload "127.0.0.1:${DJANGO_PORT}" >"${DJANGO_LOG}" 2>&1 &
PIDS+=($!)
DJANGO_PID=$!
manage process_directives --watch >"${WORKER_LOG}" 2>&1 &
PIDS+=($!)

HOST=127.0.0.1 PORT="${POS_PORT}" NUXT_DJANGO_BASE_URL="${DJANGO_URL}" NUXT_PUBLIC_DJANGO_BASE_URL="${DJANGO_URL}" \
  node surfaces/pos-nuxt/.output/server/index.mjs >"${POS_LOG}" 2>&1 &
PIDS+=($!)
POS_PID=$!
HOST=127.0.0.1 PORT="${KDS_PORT}" NUXT_DJANGO_BASE_URL="${DJANGO_URL}" NUXT_PUBLIC_DJANGO_BASE_URL="${DJANGO_URL}" \
  node surfaces/kds-nuxt/.output/server/index.mjs >"${KDS_LOG}" 2>&1 &
PIDS+=($!)
KDS_PID=$!

wait_for "${DJANGO_URL}/health/live/" "${DJANGO_PID}" "Django" "${DJANGO_LOG}"
wait_for "http://127.0.0.1:${POS_PORT}/" "${POS_PID}" "PDV" "${POS_LOG}"
wait_for "http://127.0.0.1:${KDS_PORT}/" "${KDS_PID}" "Cozinha" "${KDS_LOG}"

export PDV_LIVE_URL="${POS_URL}"
export PDV_LIVE_KITCHEN_URL="${KDS_URL}"
export PDV_LIVE_DJANGO_URL="${DJANGO_URL}"
export PDV_LIVE_DJANGO_LOG="${DJANGO_LOG}"

cat <<EOF
── Pilha de pé
   Django   ${DJANGO_URL}   (banco ${DB_NAME}; log ${DJANGO_LOG})
   PDV      ${POS_URL}
   Cozinha  ${KDS_URL}
   Para rodar o Playwright à mão contra ela (de surfaces/pos-nuxt):
     PDV_LIVE_URL=${POS_URL} PDV_LIVE_KITCHEN_URL=${KDS_URL} PDV_LIVE_DJANGO_LOG=${DJANGO_LOG} npm run test:live -- operador
EOF

if [[ "${PDV_LIVE_UP_ONLY:-}" == "1" ]]; then
  echo "── PDV_LIVE_UP_ONLY=1: a pilha fica de pé até Ctrl+C."
  wait
  exit 0
fi

# ── Playwright ─────────────────────────────────────────────────────────────────
# Sem filtro, roda a fumaça (J0) e toda jornada `jN-*.live.spec.ts`. As sondas de
# texto cortado e de latência ficam de fora: pedem outro papel (README).
if [[ $# -eq 0 ]]; then
  set -- "operador\.live" "/j[0-9]+-[^/]*\.live"
fi
status=0
(cd surfaces/pos-nuxt && npx playwright test -c playwright.live.config.ts "$@") || status=$?

if [[ "${PDV_LIVE_KEEP:-}" == "1" ]]; then
  echo "── PDV_LIVE_KEEP=1: a pilha fica de pé até Ctrl+C (Playwright saiu com ${status})."
  wait
fi
exit "${status}"
