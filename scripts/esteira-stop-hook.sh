#!/usr/bin/env bash
#
# esteira-stop-hook.sh — a sessão NÃO encerra com trabalho dormente.
#
# Hook de `Stop` do Claude Code (registrado em ~/.claude/settings.json com o
# mesmo padrão do guard-paralelo: o wrapper procura este arquivo na raiz do repo
# e, se não existir, libera). Roda quando o Claude termina o turno.
#
# Por que existe: em 16/09/2026 o Pablo mediu 150 worktrees, dezenas de branches
# com 10 a 77 commits sem PR e decisões aprovadas que nunca viraram código no ar.
# A regra "aprovado = commit + push + PR + fila" já estava escrita e era ignorada.
# Regra sem trava é lembrete. Isto é a trava.
#
# O que bloqueia (só na worktree DESTA sessão, nunca no checkout principal):
#   - arquivo não commitado          → commit por arquivo nomeado
#   - commit não empurrado           → git push -u origin <branch>
#   - delta real sem PR              → gh pr create (draft + "WIP:" se parcial)
#   - PR verde fora da fila          → gh pr merge <N>
#   - PR vermelho / em conflito      → conserte, ou nomeie a causa no relatório
#   - PR mergeado e branch com delta → PR de seguimento
#
# Bloqueia UMA vez por turno (stop_hook_active): a segunda tentativa passa, para
# que "estou esperando a palavra do Pablo sobre X" continue sendo uma saída
# legítima — desde que dita, e com o trabalho já publicado.
#
# Contrato: stdin JSON {cwd, stop_hook_active, ...}; exit 2 + stderr = bloqueia
# e mostra o texto ao Claude. https://code.claude.com/docs/en/hooks

set -uo pipefail
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"

payload="$(cat)"
[ "$(printf '%s' "${payload}" | jq -r '.stop_hook_active // false')" = "true" ] && exit 0
cwd="$(printf '%s' "${payload}" | jq -r '.cwd // empty')"
[ -n "${cwd}" ] || cwd="${PWD}"

git -C "${cwd}" rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Checkout principal é chão compartilhado: o que está sujo ali pode ser de outra
# sessão. O guard-paralelo já cuida da escrita lá. Aqui só a worktree própria.
gd="$(git -C "${cwd}" rev-parse --absolute-git-dir 2>/dev/null)" || exit 0
gc="$(cd "${cwd}" 2>/dev/null && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd)" || exit 0
[ "${gd}" = "${gc}" ] && exit 0

branch="$(git -C "${cwd}" branch --show-current 2>/dev/null)"
[ -n "${branch}" ] || exit 0
[ "${branch}" = "main" ] && exit 0

# Artefato de dev que não é trabalho: não conta como "sujo". Casa em qualquer
# subpasta (o .nuxtrc mora em surfaces/<app>/).
NOISE='^.. (.*/)?(\.nuxtrc|\.alpha-tmp/|\.claude/|\.codex/|\.local-tests/|\.artifacts/|output/|\.env|\.env\.local)$'
pend=""

dirty="$(git -C "${cwd}" status --porcelain 2>/dev/null | grep -Ev "${NOISE}" | grep -c . || true)"
[ "${dirty}" -gt 0 ] && pend+="  - ${dirty} arquivo(s) não commitados (git status --short)\n"

git -C "${cwd}" fetch --quiet origin main 2>/dev/null || true
git -C "${cwd}" rev-parse --verify --quiet origin/main >/dev/null || exit 0
ahead="$(git -C "${cwd}" rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"

if up="$(git -C "${cwd}" rev-parse --abbrev-ref '@{u}' 2>/dev/null)"; then
  n="$(git -C "${cwd}" rev-list --count "${up}..HEAD" 2>/dev/null || echo 0)"
  [ "${n}" -gt 0 ] && pend+="  - ${n} commit(s) não empurrados (git push)\n"
elif [ "${ahead}" -gt 0 ]; then
  pend+="  - branch nunca empurrada, ${ahead} commit(s) só nesta máquina (git push -u origin ${branch})\n"
fi

if [ "${ahead}" -gt 0 ] && command -v gh >/dev/null 2>&1; then
  pr="$(gh pr list --head "${branch}" --state all --limit 5 \
    --json number,state,isDraft,mergeStateStatus,autoMergeRequest,statusCheckRollup \
    --jq '(map(select(.state=="OPEN"))[0]) // (map(select(.state=="MERGED"))[0]) // .[0] // empty' 2>/dev/null || true)"
  if [ -z "${pr}" ]; then
    base_tree="$(git -C "${cwd}" rev-parse 'origin/main^{tree}')"
    merged_tree="$(git -C "${cwd}" merge-tree --write-tree origin/main HEAD 2>/dev/null | head -1 || true)"
    if [ "${merged_tree}" != "${base_tree}" ]; then
      pend+="  - ${ahead} commit(s) à frente do main e NENHUM PR (gh pr create; parcial = --draft com 'WIP:' no título)\n"
    fi
  else
    prn="$(printf '%s' "${pr}" | jq -r .number)"
    state="$(printf '%s' "${pr}" | jq -r .state)"
    draft="$(printf '%s' "${pr}" | jq -r .isDraft)"
    mss="$(printf '%s' "${pr}" | jq -r '.mergeStateStatus // ""')"
    queued="$(printf '%s' "${pr}" | jq -r '.autoMergeRequest != null')"
    fail="$(printf '%s' "${pr}" | jq -r '[.statusCheckRollup[]? | select(.conclusion=="FAILURE")] | length')"
    case "${state}" in
      OPEN)
        if [ "${draft}" != "true" ]; then
          if [ "${mss}" = "DIRTY" ]; then
            pend+="  - PR #${prn} em CONFLITO com o main (merge do main no branch, resolva, push)\n"
          elif [ "${fail}" -gt 0 ]; then
            pend+="  - PR #${prn} VERMELHO: ${fail} check(s) reprovados — conserte, ou nomeie a causa e o próximo passo no relatório\n"
          elif [ "${queued}" != "true" ] && { [ "${mss}" = "CLEAN" ] || [ "${mss}" = "BEHIND" ] || [ "${mss}" = "UNSTABLE" ]; }; then
            pend+="  - PR #${prn} verde e FORA DA FILA (gh pr merge ${prn} — sem flag de estratégia; a fila é dona)\n"
          fi
        fi ;;
      MERGED)
        base_tree="$(git -C "${cwd}" rev-parse 'origin/main^{tree}')"
        merged_tree="$(git -C "${cwd}" merge-tree --write-tree origin/main HEAD 2>/dev/null | head -1 || true)"
        [ "${merged_tree}" != "${base_tree}" ] && \
          pend+="  - PR #${prn} já mergeado, mas o branch tem commits além dele — PR de seguimento em branch novo\n" ;;
    esac
  fi
fi

[ -n "${pend}" ] || exit 0

{
  echo "ESTEIRA: a sessão não encerra com trabalho dormente. Pendente em ${branch}:"
  printf '%b' "${pend}"
  echo
  echo "Regra da casa (CLAUDE.md, 'A ESTEIRA'): aprovado = commit → push → PR → gh pr merge <N>, no mesmo turno."
  echo "Versionamento reverte; trabalho parado na worktree é invisível para o Pablo e para as outras sessões."
  echo "Faça agora: commit por ARQUIVO nomeado, push, PR (draft 'WIP:' se parcial), enfileire se verde."
  echo "Se está bloqueado por decisão que só o Pablo pode tomar: publique o que existe, escreva a pergunta"
  echo "no relatório final com o número do PR, e encerre — a segunda tentativa de parar passa."
} >&2
exit 2
