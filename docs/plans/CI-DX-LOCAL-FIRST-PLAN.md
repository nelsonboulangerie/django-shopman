# CI local-first: plano unificado e execução (DEV-2026-098)

Compromisso: DEV-2026-098 · 25/11/2026 · fontes: propostas "agente A" (CI & DX
Excellence) e "agente B" (implementação v2), confrontadas com o repositório, a API do
GitHub, a fatura e a máquina.

**Diretriz:** o que a CI vai reprovar se vê na máquina, antes do push; a fila continua
sendo o único portão do `main`. Nenhum gate afrouxado, nenhuma despesa nova.

## 1. O que mudou nas premissas (medido hoje)

| Premissa dos planos | Medição | Consequência |
|---|---|---|
| A: "reduzir 60–80% do gasto com runners pagos" | Fatura de novembro, este repositório: 724.498 min Linux e 34.878 min macOS **grátis** (repo público); a única linha paga é o `linux-4core` (16.872 min, US$ 184,46), já desligado (`CI_LINUX_RUNNER` não existe hoje). | O gasto pago já é ~zero. Ubicloud/Blacksmith/larger **acrescentam** despesa; só entram se comprarem latência que o grátis não dá. O custo real é tempo e concorrência. |
| A: "os 14 cores são agrupados" | Esta máquina: 8 núcleos (4P+4E), **8 GB** de RAM. | Duas worktrees rodando `pytest -n auto` disputavam tudo. Trava de máquina: 2 vagas × 4 workers. |
| A: 61,7% do backstage no seed | Perfil local antigo; o backstage já tem 3 shards e o shop 2 (Makefile). | Não reapresentar como novidade (B já apontava). O caminho crítico vem do baseline abaixo. |
| A/B: "reutilizar os mesmos comandos" | O job `quality` tem 20+ passos que só existiam no YAML. | O executor local **lê os passos do YAML** (sem lista copiada). Mudou o workflow, mudou o local. |
| Nenhum dos dois | A `.venv` compartilhada estava **36 pinos atrás** do `constraints.txt` (Django 6.1.1 × 6.1.2, DRF, psycopg-binary 3.3.5 × 3.3.6, stripe…). | Todo teste local testava outro conjunto que a CI. Novo passo `pinos` em todo nível; `make venv-sync` conserta só o que divergiu. Alinhada hoje. |
| CLAUDE.md: worktree importa da árvore principal | Provado: na worktree, `import shopman.orderman` resolvia para o checkout **principal**. | O Makefile põe a worktree no `PYTHONPATH` (na CI nada muda) e o passo `origem` reprova se qualquer pacote vier de fora. |
| B: `gh pr merge --match-head-commit` | Adotado. | `make ready` só liga o auto no HEAD conferido. |

## 2. Baseline da fila e do PR

Reproduzível: `make ci-baseline since=2026-10-26 until=2026-11-25` (`scripts/ci_baseline.py`,
só leitura, cache fora do git). Números desta rodada na seção 6.

## 3. O que foi implementado (este PR)

| Peça | Onde | Garantia |
|---|---|---|
| `make check-fast` | `scripts/local_ci.py run fast` | pinos, origem dos imports, colisão de migração, ruff e testes dos arquivos tocados (`test_<módulo>*`), unit do app Nuxt tocado. Segundos. |
| `make check-impact` | `run impact` | paridade com o `pull_request`: passos de `runtime-gate.yml#quality`, `#silent-swallow-gate`, `#admin-gate`, `surfaces-gate.yml#surface-versions`, `surface_contract.mjs validate`, `test-cores/storefront/counter-agent`, e unit/component/lint/typecheck dos apps no escopo, pela **mesma** `ci_scope.classify()`. |
| `make preflight` | `run preflight` | + o pesado da fila que o diff alcança: `test-shop`/`test-backstage` por domínio (Core, `config`, `shop` → os dois; `backstage` → ele), fases de navegador dos apps tocados, testes que varrem o repositório (`rglob`/`os.walk`/`git ls-files`) e, com doc mudado, os que leem `docs/`. |
| `make ci-local` | `run full` | tudo o que esta máquina executa, como diff de infraestrutura (instala `node_modules` que faltarem). |
| `make ready pr=<N>` | `local_ci.py ready` | árvore limpa, HEAD empurrado e igual ao do PR, não draft, sem conflito, "Ficou de fora" e "Compromissos" aprovam o corpo do PR, preflight verde **da árvore do HEAD**; então `gh pr merge <N> --auto --match-head-commit <sha>`. Avisa se o `main` andou nos mesmos arquivos. |
| Evidência | `~/Library/Caches/shopman-local-ci/evidence/<tree>.json` | chave = hash da árvore testada (inclui o não commitado; índice temporário, sem stash). Depois do commit, `HEAD^{tree}` bate; um byte a mais invalida. Rodada em que a árvore mudou no meio vira `stale`. Visível a todas as worktrees: a coordenação enfileira PR de outra sessão se aquela sessão provou. |
| Trava de máquina | `flock` em `…/locks/` | `cpu`: N vagas (`min(núcleos/4, RAM/4)`), `-n` por vaga via `PYTEST_XDIST_AUTO_NUM_WORKERS`; `browser`: 1 (portas); `venv`: 1. |
| Isolamento | ambiente do executor | `DATABASE_URL=''`/`REDIS_URL=''` → SQLite em memória por worker, como o job de testes da CI; um `.env` com Postgres não junta mais duas worktrees no mesmo `test_shopman`. |
| Hook de promoção | `scripts/preflight_merge_guard.py` | `PreToolUse` que barra `gh pr merge` sem evidência verde da árvore do HEAD do PR; saída declarada `SHOPMAN_SEM_PREFLIGHT="motivo"` (registrada em `overrides.jsonl`); `SHOPMAN_PREFLIGHT_GUARD=off` desliga; falha de infraestrutura deixa passar. **Não registrado**: ver seção 5. |
| Makefile | `PYTHON`, `PYTHONPATH` | worktree usa a `.venv` da raiz (nunca o `python` global) com a worktree à frente; no checkout principal e na CI, idêntico ao de antes. |
| Textos | `CLAUDE.md`, `ci-escopo.md`, `inflight.sh`, `esteira-stop-hook.sh` | o caminho ensinado passa a ser `make preflight` → `make ready pr=<N>`. |

O que **só a CI** executa sai listado como remoto, nunca como verde: retrato de pixel
(navegador da CI), PostgreSQL + Redis reais (`check --deploy` e stress), imagem Docker,
Browser QA/E2E, cobertura agregada (seis artefatos, piso 75%), PWA, supply chain,
CodeQL, e os passos que dependem do evento (`${{ }}`).

## 4. Decisões e o que não se fez

- **Sem fornecedor novo e sem runner pago** (WP1 dos dois planos): com gasto pago zero e
  a medição de 21/11 (o `linux-4core` com ~17 vagas piorou a fila contra as ~60 do
  grátis), comprar CPU não é o gargalo. Piloto pago só com classe de job identificada no
  baseline e teto aprovado pelo dono.
- **Nada em `.github/workflows`, checks obrigatórios ou fila neste PR** (pedido da
  coordenação até #3631 e #3626 entrarem). As mudanças de CI que o baseline justificar
  (rebalancear shards, workflow chamar os alvos do Makefile em vez de duplicar, rodar
  `scripts/tests/test_local_ci.py` no `quality`) viram issues `ficou-de-fora`.
- **Sem scheduler, sem Nx/Turborepo**: `flock` com vagas resolve a disputa medida.
- **Preflight não substitui nada**: o `merge_group` continua rodando a suíte inteira na
  árvore candidata.

## 5. Decisão pendente do dono

O hook de promoção precisa ser registrado em `.claude/settings.json` (afeta toda sessão
do Claude Code neste repositório; o classificador de permissões não deixa um agente
editar hooks sozinho). Trecho:

```json
"hooks": {
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "f=\"$CLAUDE_PROJECT_DIR/scripts/preflight_merge_guard.py\"; [ -r \"$f\" ] && python3 \"$f\" || exit 0",
          "timeout": 30,
          "statusMessage": "gh pr merge: conferindo o preflight do HEAD"
        }
      ]
    }
  ]
}
```

Sem ele, a regra vale pelo `make ready` e pelo texto do `CLAUDE.md`, como hoje vale o
"auto só com o local verde".

## 6. Números

(preenchido na seção seguinte pela rodada desta data)
