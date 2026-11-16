#!/usr/bin/env bash
# Sonda da TaOn da sua máquina (docs/runbooks/courier-machine-homologacao.md).
#
#   make taon-probe homolog=1 args='--ride <id>'
#
# Com --homolog, pergunta as três credenciais da HOMOLOGAÇÃO aqui no terminal (a
# senha e a chave não aparecem na tela), aponta para a base de homologação da
# TaOn e roda `manage.py courier_machine_probe`. Nada é gravado: as credenciais
# vivem só neste processo e somem quando ele termina. Nunca cole credencial em
# arquivo do repositório, em mensagem ou no chat.
#
# Sem --homolog, roda com o ambiente que já estiver exportado.
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
homolog=0
args=()
for arg in "$@"; do
  if [ "$arg" = "--homolog" ]; then homolog=1; else args+=("$arg"); fi
done

if [ "$homolog" = "1" ]; then
  echo "Homologação da TaOn: as credenciais ficam só neste terminal."
  read -r -p "Usuário de API (homologação): " MACHINE_API_USER
  read -r -s -p "Senha (não aparece): " MACHINE_API_PASSWORD; echo
  read -r -s -p "API Key de homologação (não aparece): " MACHINE_API_KEY; echo
  export MACHINE_API_USER MACHINE_API_PASSWORD MACHINE_API_KEY
  export MACHINE_API_BASE="https://api-vendas.taximachine.com.br/api/integracao"
  export MACHINE_DETAILS_BASE="https://api-vendas.taximachine.com.br/api/integracao/v1"
  export SHOPMAN_MACHINE_ALLOW_IN_DEBUG=true
fi

# Worktree sem .env: sobe em perfil de desenvolvimento com chave descartável.
if [ ! -f .env ] && [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  export DJANGO_DEBUG=true DJANGO_SECRET_KEY=local-probe-not-a-secret
fi

exec "$PYTHON_BIN" manage.py courier_machine_probe ${args[@]+"${args[@]}"}
