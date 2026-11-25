# CI local-first: plano unificado e execução (DEV-2026-098)

Compromisso: DEV-2026-098 · 25/11/2026 · fontes: propostas "agente A" (CI & DX
Excellence) e "agente B" (implementação v2), confrontadas com o repositório, a API do
GitHub, a fatura e a máquina.

**Diretriz:** o que a CI vai reprovar se vê na máquina, antes do push; a fila continua
sendo o único portão do `main`. Nenhum gate afrouxado, nenhuma despesa nova.

## 1. O que mudou nas premissas (medido hoje)

| Premissa dos planos | Medição | Consequência |
|---|---|---|
| A: "reduzir 60–80% do gasto com runners pagos" | Fatura de novembro: 725 mil min Linux e 35 mil min macOS **grátis** (repo público); o `linux-4core` custou US$ 184,46 em poucos dias e está desligado. **Medido por job (18–21/11, até 545 × 60 amostras): o 4-core rodou cada job na mesma velocidade do grátis, 0,97x a 1,12x** (`evidence/ci-dx-098/runner-4core-vs-std-2026-11-25.md`). O runner grátis de repo público já tem 4 vCPU. | O que o 4-core comprou foi **capacidade nos picos** (outro lote de máquinas), não velocidade. A pergunta certa (dono, 25/11) é acelerar por menos: seção 9. |
| A: "os 14 cores são agrupados" | Esta máquina: 8 núcleos (4P+4E), **8 GB** de RAM. | Duas worktrees rodando `pytest -n auto` disputavam tudo. Trava de máquina: 2 vagas × 4 workers. |
| A: 61,7% do backstage no seed | Perfil local antigo; o backstage já tem 3 shards e o shop 2 (Makefile). | Não reapresentar como novidade (B já apontava). O caminho crítico vem do baseline abaixo. |
| A/B: "reutilizar os mesmos comandos" | O job `quality` tem 20+ passos que só existiam no YAML. | O executor local **lê os passos do YAML** (sem lista copiada). Mudou o workflow, mudou o local. |
| Nenhum dos dois | A `.venv` compartilhada estava **36 pinos atrás** do `constraints.txt` (Django 6.1.1 × 6.1.2, DRF, psycopg-binary 3.3.5 × 3.3.6, stripe…). | Todo teste local testava outro conjunto que a CI. Novo passo `pinos` em todo nível; `make venv-sync` conserta só o que divergiu. Alinhada hoje. |
| CLAUDE.md: worktree importa da árvore principal | Provado: na worktree, `import shopman.orderman` resolvia para o checkout **principal**. | O Makefile põe a worktree no `PYTHONPATH` (na CI nada muda) e o passo `origem` reprova se qualquer pacote vier de fora. |
| B: `gh pr merge --match-head-commit` | Adotado. | `make ready` só liga o auto no HEAD conferido. |

## 2. Baseline da fila e do PR

Reproduzível: `make ci-baseline since=2026-10-26 until=2026-11-25` (`scripts/ci_baseline.py`,
só leitura, cache fora do git). Números desta rodada na seção 6; relatório bruto em `evidence/ci-dx-098/`.

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
| Hook de promoção | `scripts/preflight_merge_guard.py` | `PreToolUse` que barra `gh pr merge` sem evidência verde da árvore do HEAD do PR; saída declarada `SHOPMAN_SEM_PREFLIGHT="motivo"` (registrada em `overrides.jsonl`); `SHOPMAN_PREFLIGHT_GUARD=off` desliga; falha de infraestrutura deixa passar. Registrado em `.claude/settings.json` (dono, 25/11: "Sim, registre"). |
| Makefile | `PYTHON`, `PYTHONPATH` | worktree usa a `.venv` da raiz (nunca o `python` global) com a worktree à frente; no checkout principal e na CI, idêntico ao de antes. |
| Textos | `CLAUDE.md`, `ci-escopo.md`, `inflight.sh`, `esteira-stop-hook.sh` | o caminho ensinado passa a ser `make preflight` → `make ready pr=<N>`. |

O que **só a CI** executa sai listado como remoto, nunca como verde: retrato de pixel
(navegador da CI), PostgreSQL + Redis reais (`check --deploy` e stress), imagem Docker,
Browser QA/E2E, cobertura agregada (seis artefatos, piso 75%), PWA, supply chain,
CodeQL, e os passos que dependem do evento (`${{ }}`).

## 4. Decisões e o que não se fez

- **Nenhum runner pago ligado nesta frente**: a seção 9 diz onde pagar renderia, e o
  piloto espera o teto aprovado pelo dono.
- **Nada em `.github/workflows`, checks obrigatórios ou fila neste PR** (pedido da
  coordenação até #3631 e #3626 entrarem). As mudanças de CI que o baseline justificar
  (rebalancear shards, workflow chamar os alvos do Makefile em vez de duplicar, rodar
  `scripts/tests/test_local_ci.py` no `quality`) viram issues `ficou-de-fora`.
- **Sem scheduler, sem Nx/Turborepo**: `flock` com vagas resolve a disputa medida.
- **Preflight não substitui nada**: o `merge_group` continua rodando a suíte inteira na
  árvore candidata.

## 5. Hook de promoção (registrado)

Registrado em `.claude/settings.json` com a palavra do dono (25/11, "Sim, registre"); vale
para toda sessão do Claude Code aberta numa árvore que já tenha este commit. Trecho
(`if/else`, não `&& ||`: com `||`, o exit 2 do hook virava 0 e nada seria barrado):

```json
"hooks": {
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "f=\"$CLAUDE_PROJECT_DIR/scripts/preflight_merge_guard.py\"; if [ -r \"$f\" ]; then python3 \"$f\"; else exit 0; fi",
          "timeout": 30,
          "statusMessage": "gh pr merge: conferindo o preflight do HEAD"
        }
      ]
    }
  ]
}
```

Prova com o comando registrado, pelo shell: comando comum passa (0); `gh pr merge` sem
evidência é barrado (2) com a instrução; com `SHOPMAN_SEM_PREFLIGHT="motivo"` passa e
registra; com preflight verde da árvore passa; `SHOPMAN_PREFLIGHT_GUARD=off` desliga.

## 6. Números (medidos em 25/11/2026)

Janela 26/10–25/11, `make ci-baseline since=2026-10-26 until=2026-11-25`. "Grupo" é um
`gh-readonly-queue/main/pr-N-<base>`; o relógio vai do primeiro gate criado ao último
terminado. Antes/depois é o corte da decisão "leve no PR, pesado na fila" (17/11).

**Fila (`merge_group`)**

| | antes de 17/11 | desde 17/11 |
|---|---:|---:|
| grupos | 427 | 1.382 |
| grupos verdes | 339 | 686 |
| grupos reprovados | 71 (17%) | 671 (49%) |
| relógio do grupo verde p50 / p95 | 25,5 / 71,2 min | 26,2 / 74,4 min |
| último gate a terminar (verde) | Runtime 223 · Surfaces 115 | **Surfaces 433** · Runtime 247 |
| Surfaces Gate p50 na fila | 19,0 min | 27,2 min |
| Runtime Gate p50 na fila | 23,9 min | 23,5 min |

Nos grupos reprovados desde 17/11, o workflow que reprovou: Runtime 470, Surfaces 359,
Security 295, Omotenashi 117, Operator Groups 85, Production Contract 85, Ficou de fora 82
(um grupo pode reprovar em mais de um). A taxa de 49% mistura causas que o baseline não
separa: o estouro do orçamento do `linux-4core` em 18–19/11, que travou jobs, e o volume
três vezes maior. Medido, não atribuído.

**PR: entrada na fila → merge** (desde 17/11): 618 PRs mergeados pela fila; p50 **79,8 min**,
p95 **736 min**. **199 PRs (32%) saíram da fila sem entrar** ao menos uma vez, 0,73 saída
por PR mergeado: `failed_checks` 166, `manual` 162, `invalid_merge_commit` 82,
`merge_conflict` 30, `checks_timed_out` 13. Cada saída custa um ciclo inteiro (~26 min) e
refaz os grupos de trás.

**Jobs da fila** (24–25/11, 145 grupos, todos em `ubuntu-latest`): os mais longos em
execução p50 são `Backstage rest` 18,6 min, `Backstage heavy` 15,5, `pos-nuxt` 13,8,
`Backstage seed` 13,4, `kitchensink` 11,6, `purchase-nuxt` 11,3. Espera por runner: p50
≤ 0,8 min, **p95 10–19 min** (picos de concorrência). O Surfaces Gate leva 27 min com o
job mais longo em 14: o resto é a cadeia escopo → contrato → matriz e a espera.

**Minutos (novembro, este repositório):** Linux 725.046 min (US$ 4.350 brutos, US$ 0
líquidos), macOS 34.878 min (US$ 2.162 brutos, 0 líquidos), `linux-4core` 16.872 min
(**US$ 184,46 líquidos**, a única despesa, já desligada).

**Local (esta máquina, 8 núcleos/8 GB):** `check-fast` ≈ 4 s de passos (≈ 9 s de relógio
com o hash da árvore); `check-impact` num diff de infraestrutura (o pior caso: escopo
inteiro) 627 s, 33 passos verdes; o passo local mais lento é a governança documental
(153 s, quase todo `test_check_orchestrator_units`). Prova de isolamento: duas worktrees ao
mesmo tempo, uma com `format_money` quebrado — `make test-utils` passou numa (exit 0) e
reprovou na outra (exit 2, `test_money_field.py`), e a trava fez uma esperar a vaga da
outra; o `check-fast` da quebrada reprovou em 1,5 s.

**Primeiro `make preflight` real** (este branch, escopo inteiro por ser infraestrutura):
26 min 45 s de relógio, 34 de 35 passos verdes; `test-backstage` 828 s, `test-shop` 219 s,
`test-storefront` 102 s, `test-cores` 91 s, `make admin` 75 s. O único vermelho é
**pré-existente** e independente deste branch (que não toca `shopman/`, `packages/` nem
`config/`): um teste do PDV que reprova sob `-n 4` e passa sozinho, com a causa escondida
pelo `subTest` com `date` sob xdist (#3637). O `make ready` recusa enfileirar com essa
evidência, como deve. Diff estreito (um app, um pacote) não chama os dois shards inteiros.

## 7. Metas (calibradas pelo baseline; medir de novo em 09/12)

| Indicador | Hoje | Meta |
|---|---:|---:|
| Saídas da fila por `failed_checks` por PR mergeado | 166/618 = 0,27 | ≤ 0,10 |
| Entrada na fila → merge, p50 / p95 | 80 / 736 min | ≤ 45 / ≤ 180 min |
| Relógio do grupo verde p50 | 26 min | ≤ 20 min (WP de redução, #3635) |
| `check-fast` p50 | ≈ 9 s | ≤ 60 s |
| `preflight` de diff estreito, p50 | a medir em PRs reais | ≤ 5 min |
| Gasto pago | US$ 0 hoje | US$ 0 sem decisão do dono |
| Garantias | 29 checks, cobertura 75%, suíte inteira na árvore candidata | idênticas |

## 8. Próximas frentes (issues `ficou-de-fora`)

- #3632 — `quality` roda `test_local_ci.py`; paridade workflow↔local num lugar só.
- #3635 — reduzir o caminho crítico com estes números: rebalancear os shards do backstage
  (`rest` 18,6 × `seed` 13,4 min), encurtar a cadeia do Surfaces Gate, o
  `test_check_orchestrator_units`.
- #3637 — teste do PDV que reprova sob xdist (achado pelo primeiro preflight).
- #3636 — fila: as 162 saídas `manual` e 82 `invalid_merge_commit` (pilhas), parâmetros
  da fila (5 builds, 1–10 PRs, 120 min) contra o baseline.

## 9. Acelerar por menos (dono, 25/11: "Ter comprado máquina acelerou muito! Só que é muito caro")

O que os números dizem sobre a máquina paga:

- **Velocidade por job: nenhuma.** O `linux-4core` tem o mesmo tamanho do runner grátis de
  repositório público (4 vCPU). Os 6 jobs que seguram o relógio deram 1,00x a 1,12x.
- **O que acelerou foi capacidade.** Nos picos a espera por runner chega a 10–19 min (p95);
  o 4-core era um segundo lote de máquinas. Quando TUDO ia para ele (~17 vagas), a fila
  piorou (21/11).
- **O dinheiro ia para todos os jobs.** Por grupo da fila, Runtime + Surfaces somam ~207 min
  de job; os 6 do caminho crítico (backstage ×3, `pos-nuxt`, shop ×2) são 79 (38%).

Em ordem de custo:

1. **Pedir menos máquina (US$ 0).** 49% dos grupos reprovaram e 32% dos PRs saíram da fila
   sem entrar; cada saída refaz os grupos de trás e é isso que lota os picos. É o
   `make preflight` + `make ready` (este PR).
2. **Mais fatias nos 6 jobs críticos (US$ 0).** Minuto grátis não custa; mais shards
   encurtam o relógio enquanto houver vaga no pico (#3635).
3. **Pagar só o que falta, e medindo.** (a) Transbordo: máquina paga só quando as grátis
   esgotam; (b) máquina maior (8–16 vCPU) só nos 6 jobs críticos, onde o `-n auto` escala
   com núcleos. Em fornecedor como Ubicloud o minuto sai ~1/3 do preço do GitHub. Que
   8 vCPU acelerem esses testes é **hipótese, não medida**: o piloto mede no mesmo SHA, com
   teto aprovado pelo dono, e só fica o que baixar o relógio por menos.

### 9.1 Piloto barato, preparado e desligado (dono, 25/11: "Sim, prepare")

Duas peças, as duas sem efeito até alguém ligar:

| Peça | Onde | Liga com | Efeito desligada |
|---|---|---|---|
| Benchmark no mesmo commit | `.github/workflows/runner-benchmark.yml` | `gh workflow run runner-benchmark.yml -f runner=<rótulo> -f reps=3` (depois de entrar no `main`), ou push em `ci-bench/**` com `vars.CI_BENCH_RUNNER` | nenhum: não roda em PR nem na fila e só lê cache |
| Seletor só dos 6 jobs, só na fila | `runtime-gate.yml` (shards do backstage e do shop) e `surfaces-gate.yml` (`app-quality`) | `vars.CI_HEAVY_RUNNER=<rótulo>` e `vars.CI_HEAVY_SURFACES=["pos-nuxt"]` | runner de sempre (`CI_LINUX_RUNNER` ou `ubuntu-latest`) |

Comparação dos dois: `python3 scripts/ci_baseline.py --compare-runners --run <id>` (benchmark)
ou `--since … --until …` (fila ao vivo), por rótulo de runner. Com os dados de 18–19/11 ela
reproduz a tabela de 25/11 (`Backstage rest` 13,7 × 13,8 min).

**Etapa 1, benchmark (estimado, não medido):** 6 jobs × 3 repetições × ~12 min ≈ 216 min no
candidato. Em 8 vCPU: ~US$ 4,75 no GitHub (`linux-8core`, US$ 0,022/min) ou ~US$ 1,75 na
Ubicloud (US$ 0,008/min, preço publicado consultado pelo plano A). Teto proposto: **US$ 10**.

**Regra de decisão:** o piloto ao vivo só acontece se o benchmark mostrar **≥ 1,4x** na
mediana dos 6 jobs. Abaixo disso, não se paga por velocidade: o caminho é o grátis (preflight
e shards, #3635).

**Etapa 2, piloto ao vivo (só se a etapa 1 passar):** por grupo da fila os 6 jobs somam
~79 min em 4 vCPU; a 1,6x seriam ~50 min pagos, cerca de US$ 0,40 por grupo na Ubicloud ou
US$ 1,10 no GitHub (estimado). Com o volume de hoje (~150 grupos/dia, metade reprovando),
isso daria ~US$ 60/dia na Ubicloud; o preflight reduz o número de grupos. Teto proposto:
**US$ 50 por 2 dias**. Fica só se o relógio do grupo verde p50 cair ≥ 3 min (hoje 26,2) e o
custo por PR mergeado couber no teto mensal que o dono definir. O Surfaces Gate termina por
último em 63% dos grupos verdes por causa da cadeia e da espera, não só do `pos-nuxt`: o
ganho real pode ser menor que a aceleração do job.

**Desligar:** apagar `CI_HEAVY_RUNNER` (efeito no próximo job, sem commit). Para não repetir
o 21/11, a concorrência máxima do runner pago precisa comportar ~30 jobs (6 jobs × 5 grupos
simultâneos da fila).

**Segurança:** só código já aprovado roda ali (fila e disparo manual/push de branch da casa;
nunca PR de fork). Os seis jobs não usam segredo.

**O que depende do dono:** escolher o fornecedor e criar o runner. No GitHub: um runner
`linux-8core` em org Settings › Actions › Runners, concorrência ≥ 30, dentro do orçamento
de Actions que já existe. Na Ubicloud: a conta, o app da Ubicloud instalado só neste
repositório e o teto de gasto lá. Depois disso, a coordenação dispara o benchmark e traz a
tabela.

### 9.2 Resultado do benchmark (25/11, run 45666175682, `evidence/ci-dx-098/benchmark-linux-8core-2026-11-25.md`)

Com 8 vCPU, a mediana dos 6 jobs foi **1,20x**, abaixo da regra de 1,4x: **sem piloto pago
ao vivo.** O que os números mostram, job a job:

- **Escalam com núcleos:** `backstage seed` 1,81x (teste 1,95x) e `backstage rest` 1,44x
  (teste 1,47x). São suítes `-n auto` limitadas por CPU.
- **Quase nada:** `pos-nuxt` 1,01x (navegador, não CPU), `shop rest` 1,07x,
  `backstage heavy` 1,14x.
- **O relógio do grupo mal mudaria:** o Surfaces Gate termina por último em 63% dos grupos
  verdes e o `pos-nuxt` não acelera. Pagar encurtaria só o Runtime Gate.

**A mesma aceleração sai de graça:** dois runners grátis de 4 vCPU somam os 8 vCPU de um
pago. Dividir `backstage seed` e `backstage rest` em mais shards (#3635) dá o ganho medido
sem custo. Isso vale enquanto houver vaga no pico, e o preflight reduz a disputa por vaga.
O seletor `CI_HEAVY_RUNNER` e o benchmark ficam para medir outro fornecedor ou o transbordo
de pico, se um dia fizer sentido.

## 10. Guardar as decisões de desempenho (dono, 25/11)

> "A questão é NÃO DEIXAR que esse tipo de 'sacada' que teve se perca... daqui a pouco termos
> shards, seeds e seja lá o que for que esteja dado de um jeito que o trabalho fique lento."

Até aqui, as decisões de desempenho da suíte viviam em comentário do Makefile e eram refeitas
**depois** do estrago: o shard `rest` foi rebalanceado à mão em 30/09 e em 06/11, as duas vezes
depois de estourar o teto e tirar PR da fila. Agora há três camadas, no padrão das travas que o
repositório já tem:

| Camada | Onde | O que garante | Quando age |
|---|---|---|---|
| 1. Definição versionada | `scripts/ci-time-budget.json` (teto por job e do grupo), `scripts/test-shard-weights.json` (segundos por arquivo), `scripts/test-cost-baseline.json` (seed completo por arquivo), `BACKSTAGE_*_PARTS` no Makefile | a decisão tem número e endereço; mudar é diff num PR | sempre |
| 2. Trava do PR (determinística) | `scripts/check_test_cost.py` no job Quality; `test_local_ci.py` | teste novo que chama o seed completo reprova (35 chamadas em 20 arquivos congeladas; crescer só com `--update` à vista do revisor); quem semeia no backstage mora no `seed`/`heavy`, nunca no `rest`; shards partidos cobrem cada arquivo uma vez e ficam ≤ 1,35x pelos pesos; peso de arquivo morto reprova; partes iguais no Makefile, na matriz e no Coverage Gate | todo PR |
| 3. Vigia agendada | `.github/workflows/ci-time-watch.yml`, diária | mede a fila real (`ci_baseline.py --budget`) e re-mede os pesos com o junit da última fila verde; estourou → abre/comenta a issue "Orçamento de tempo da CI estourou" com os números e o comando (`make shard-weights run=<id>`); voltou → fecha | todo dia, sem reprovar PR (relógio oscila) |

**Primeira aplicação:** `backstage seed` e `backstage rest` partidos em dois cada, por peso
medido (`scripts/test_shards.py`, LPT determinístico). Coleta provada idêntica: `seed` 25 = 13 +
12, `rest` 13.400 = soma das partes, zero duplicata. O piso do `seed` é
`test_nelson_seed_operational.py`, 56% do shard sozinho. O próximo ganho ali é o que o Makefile já
anotava: os testes que só **leem** o catálogo semeado dividirem um seed. A trava agora conta isso.
