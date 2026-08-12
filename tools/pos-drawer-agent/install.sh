#!/usr/bin/env bash
# Instala o agente da gaveta na máquina do balcão (Linux, systemd --user).
#
# Idempotente: rodar de novo atualiza o código e a unit sem trocar o token nem
# a fila já configurados. Trocar o token quebraria o PDV até alguém colar o novo
# no Admin, e ninguém quer descobrir isso no meio de um sábado.
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/.local/share/nelson-pos-drawer"
CONFIG_DIR="${HOME}/.config/nelson-pos-drawer"
CONFIG_FILE="${CONFIG_DIR}/agent.json"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT_FILE="${UNIT_DIR}/nelson-pos-drawer.service"

die() { echo "erro: $*" >&2; exit 1; }

command -v python3 >/dev/null || die "python3 não encontrado."
command -v lp >/dev/null || die "comando 'lp' não encontrado — instale o CUPS."
command -v systemctl >/dev/null || die "systemctl não encontrado (este instalador é para Linux com systemd)."

mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$UNIT_DIR"
install -m 0755 "${AGENT_DIR}/drawer_agent.py" "${INSTALL_DIR}/drawer_agent.py"

if [[ -f "$CONFIG_FILE" ]]; then
  echo "config já existe em ${CONFIG_FILE} — mantida (token e fila preservados)."
else
  QUEUE="${1:-}"
  if [[ -z "$QUEUE" ]]; then
    echo "Filas CUPS disponíveis:"
    lpstat -a 2>/dev/null | awk '{print "  - " $1}' || echo "  (nenhuma)"
    read -r -p "Nome da fila da impressora térmica: " QUEUE
  fi
  [[ -n "$QUEUE" ]] || die "fila não informada."
  lpstat -a "$QUEUE" >/dev/null 2>&1 || die "fila '$QUEUE' não existe no CUPS."

  TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  ORIGIN="${2:-https://pos.staging.nelsonboulangerie.com.br}"

  umask 077
  cat > "$CONFIG_FILE" <<JSON
{
  "queue": "${QUEUE}",
  "token": "${TOKEN}",
  "port": 47811,
  "host": "127.0.0.1",
  "allowed_origins": ["${ORIGIN}"]
}
JSON
  chmod 600 "$CONFIG_FILE"
  echo
  echo "Config criada em ${CONFIG_FILE}"
  echo
  echo "  ┌─ COLE ESTE TOKEN no Admin ─────────────────────────────────"
  echo "  │  Admin → Terminais do PDV → gaveta → token"
  echo "  │"
  echo "  │  ${TOKEN}"
  echo "  └─────────────────────────────────────────────────────────────"
  echo
fi

cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=Agente da gaveta de dinheiro do PDV (Nelson)
Documentation=https://github.com/pablondrina/django-shopman/blob/main/tools/pos-drawer-agent/README.md
After=cups.service

[Service]
Type=simple
ExecStart=/usr/bin/env python3 ${INSTALL_DIR}/drawer_agent.py
Restart=always
RestartSec=3
# O balcão abre cedo e ninguém vai olhar journal: se cair, sobe de novo.

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now nelson-pos-drawer.service

# Sem isto o agente só existe enquanto o operador estiver logado na sessão
# gráfica — e morre no logout, que é exatamente quando ninguém percebe.
loginctl enable-linger "$(id -un)" 2>/dev/null || \
  echo "aviso: não consegui habilitar linger; rode 'sudo loginctl enable-linger $(id -un)'."

sleep 1
systemctl --user --no-pager --lines=5 status nelson-pos-drawer.service || true

echo
echo "Pronto. Teste o caminho até o spooler sem navegador:"
echo "  python3 ${INSTALL_DIR}/drawer_agent.py --kick"
