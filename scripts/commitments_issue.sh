#!/usr/bin/env bash
#
# Abre, atualiza ou fecha a issue semanal de compromissos vencidos.
#
# Uso: GITHUB_REPOSITORY=owner/repo bash scripts/commitments_issue.sh <relatorio.md>
# O relatório vem de: python3 scripts/check_commitments.py --format issue --no-fail-overdue
#
# A primeira linha do relatório é `<!-- commitments-overdue: N -->`; N decide se
# a issue nasce, é atualizada ou fecha. Uma issue por vez, sempre com o mesmo
# título, para o dono não caçar várias.

set -euo pipefail

report="${1:?uso: commitments_issue.sh <relatorio.md>}"
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY não definido}"
title="Compromissos vencidos"

count="$(sed -n 's/.*commitments-overdue: \([0-9][0-9]*\).*/\1/p' "${report}" | head -1)"
count="${count:-0}"
number="$(gh issue list --repo "${repo}" --state open --search "${title} in:title" \
  --json number --jq '.[0].number // empty')"

if [ "${count}" -gt 0 ]; then
  if [ -n "${number}" ]; then
    gh issue edit "${number}" --repo "${repo}" --body-file "${report}"
    echo "issue #${number} atualizada (${count} vencidos)"
  else
    gh issue create --repo "${repo}" --title "${title}" --body-file "${report}"
    echo "issue criada (${count} vencidos)"
  fi
elif [ -n "${number}" ]; then
  gh issue close "${number}" --repo "${repo}" \
    --comment "Sem compromissos vencidos nesta semana."
  echo "issue #${number} fechada"
else
  echo "nada vencido; nenhuma issue aberta"
fi
