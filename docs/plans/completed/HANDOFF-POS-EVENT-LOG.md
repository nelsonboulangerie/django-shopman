# Log de eventos do PDV + trava da gaveta

> ⛔ **SUPERADO. Não execute por este documento.** O `cashman` absorveu o log de
> eventos como livro-caixa imutável, e a trava da gaveta virou o
> [WP-8 do CASHMAN-PLAN](../CASHMAN-PLAN.md), com as mesmas regras (iniciar, sem
> carência, só quando sabe, um destrave uma venda). O PR #198 fechou sem merge.
> Guardado aqui porque a lição P3 da
> [CASH-LEDGER-ARCHITECTURE](../CASH-LEDGER-ARCHITECTURE.md) cita a seção
> "Por que o log existe" como fonte.

> Prompt de handoff para sessão limpa. Contém o contexto suficiente e nada além.

## O que construir

**Duas peças, nesta ordem. A segunda depende da primeira.**

1. **Log de eventos do PDV** — append-only, imutável, cidadão de primeira classe.
2. **Trava da gaveta** — o PDV recusa iniciar a próxima venda enquanto a gaveta
   estiver aberta; gerente destrava com PIN, e o destrave é registrado no log.

## Por que o log existe (leia antes de desenhar)

Hoje não há log. Há **cinco rastros parciais**, cada um num lugar:

| rastro | onde |
|---|---|
| aberturas de gaveta sem venda | `CashShift.metadata["drawer_openings"]` (`shopman/backstage/services/pos.py:163`) |
| pedidos de troco | `CashShift.metadata["change_requests"]` (`services/pos.py:339`) |
| sangria / suprimento | `CashMovement` — `shopman/backstage/models/cash_register.py` |
| falhas operacionais | `OperatorAlert` — `models/alerts.py` |
| fechamento do dia | `DayClosing.data` — `models/closing.py` |

Nenhum responde *"o que aconteceu no caixa hoje, em ordem"*.

⚠️ **A causa foi a regra da casa aplicada fora de lugar.** "Dado contextual vai em
JSONField" está certo para **estado** (como está o turno) e errado para **evento**
(o que aconteceu, em ordem). Cada feature nova acrescentou sua listinha; dois
desses cinco nasceram na sessão de 2026-08-18.

## O padrão a seguir já existe no repo — NÃO invente outro

`packages/stockman/shopman/stockman/models/move.py`. Leia antes de escrever
qualquer linha. Resumo do que ele faz certo:

- `MoveQuerySet` sobrescreve `update()` e `delete()` e **levanta** — mensagem em
  português dizendo o que fazer no lugar.
- `Move.delete()` também levanta.
- `ordering = ['timestamp']` + índices.
- Docstring afirma o invariante: *"este é o ÚNICO model que muda quantidade"*.
- **Correção é lançamento novo com sinal invertido**, nunca edição.

Pagamentos (`packages/payman`) seguem a mesma ideia. O PDV é a lacuna, não o
conceito.

⚠️ **Limite honesto de "imutável":** a guarda no QuerySet protege do acidente e do
descuido, não de quem tem acesso ao banco. Imutabilidade real exigiria trigger ou
permissão no Postgres. O `Move` também é só app-level. **Não prometa mais do que
entrega** — nem no código, nem na tela.

## Desenho pedido

Um model no `backstage`, append-only:

- `at`, `shift` (FK), `terminal`, `operator`, `kind` (choices), `payload`
  (JSONField para o específico de cada tipo), FK opcional para `CashMovement` e
  ref do pedido quando houver.
- Guarda de imutabilidade **igual à do `Move`**.
- Indexado por dia e por operador — são as duas perguntas que o gerente faz.

**Os cinco rastros migram para dentro dele.** Sem isso ficam seis trilhas *mais*
um log, pior que hoje. `drawer_openings` e `change_requests` viram tipos de
evento e saem do `metadata`; `CashMovement` continua sendo a tabela do dinheiro
(não duplique valor), mas **gera** evento.

**Alimenta o B.I.** Uma sequência de eventos com autor e hora é o formato que
responde "quem abre a gaveta 3× mais que os outros", "quantos destraves por
operador", "em que horário" — que é o uso que motivou tudo isso. Ver
`shopman/backstage/projections/bi_*.py` e `services/day_similarity.py`.

## A trava — regras decididas, não reabrir

- **Trava ao INICIAR a próxima venda.** Nunca no meio de uma: venda começada não
  vira refém.
- **SEM carência.** Foi discutido e descartado: se a trava é na próxima venda, o
  operador já teve o tempo dele. Carência transforma a exceção em rotina
  invisível — e o dono foi explícito: *"a exceção tratada como tal tem mais
  chance de ser escancarada"*.
- ⚠️ **Só trava quando SABE que está aberta.** Se o estado for desconhecido,
  **nunca trava**. Isso inverte o modo de falha: sensor ruim degrada para "sem
  controle", jamais para "balcão parado com fila".
- **Gerente destrava com PIN**, e o destrave **vai para o log**. É para a gaveta
  emperrada, que existe.

### Como saber o estado da gaveta

O agente do balcão (`tools/pos-counter-agent/counter_agent.py`) expõe
`GET /drawer` → `{known, open, raw}`. Quem alcança o agente é **a página do PDV**
(loopback do balcão); o servidor não alcança. Use
`surfaces/pos-nuxt/app/composables/useCashDrawer.ts`, que já fala com ele.

⚠️ **A polaridade é MEDIDA, nunca constante.** No balcão da Nelson:
`DLE EOT 1`, bit `0x04`, **fechada `0x16`** (bit ligado) e **aberta `0x12`**
(desligado) — o inverso do que a leitura ingênua do manual sugere. O agente grava
o medido em `config["drawer_status"]`. Se alguém cravar a constante, o alerta
grita o dia todo com a gaveta fechada, o balcão aprende a ignorar, e o aviso
legítimo morre junto.

## Convenções da casa (obrigatórias)

Leia o `CLAUDE.md` da raiz. As que mais pegam nesta tarefa:

- **URL sempre em inglês** (Admin, backstage, Nuxt, API). Texto de tela em pt-BR.
- Dinheiro em centavos com sufixo `_q`. Identificador textual é `ref`, não `code`.
- Chave nova em JSONField → documentar em `docs/reference/data-schemas.md`.
- **Sem jargão inventado**; nomes descritivos. Rótulo de tela ≠ identificador.
- Copy **sentence case**, **sem travessão em prosa de UI**.
- PDV é **desktop-first**; UI de operador **neutra**, cor só funcional. Só classes
  Tailwind já usadas; sem biblioteca de componentes nova.
- Comentário explica **por quê**, não o quê — em português, com o motivo e a
  consequência de errar.
- Tela do Admin segue o **Unfold Canonical Gate** (`make admin`).

## Armadilhas de execução (custaram horas)

- Venv canônico: `/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python`.
  **Nunca** o `python` global (editable-installs apontam para worktrees antigas).
- Worktree não tem `.venv` → passe na linha do make:
  `make test-framework PYTHON=/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python`
- **Exporte PYTHONPATH** com o worktree primeiro, senão você testa o código do
  `main` e passa verde sem testar nada:
  `export PYTHONPATH="$PWD:$PWD/packages/utils:$PWD/packages/refs:$PWD/packages/offerman:$PWD/packages/stockman:$PWD/packages/craftsman:$PWD/packages/orderman:$PWD/packages/guestman:$PWD/packages/doorman:$PWD/packages/payman:$PWD/packages/buyman:$PWD/packages/fiscalman"`
- **Nunca misture suítes numa só chamada do pytest** — dezenas de falhas falsas.
  Um alvo do Makefile por vez.
- **Migração:** o `backstage` já vai até `0021`. Duas no mesmo número quebram o
  deploy — aconteceu **três vezes** nesta semana. Rode
  `manage.py makemigrations --check --dry-run` **e** um `migrate --noinput` de
  banco zerado (apague o `db.sqlite3`; não existe env var para trocar o caminho).
- Verdes obrigatórios: `make test-framework`, `make admin`, `ruff check shopman/
  config/ scripts/`. Em `surfaces/pos-nuxt`: `npm run test` **e**
  `npm run typecheck` (o typecheck é o gate que vale; se faltar `node_modules`,
  `npm ci` lá **e** em `surfaces/operator-kit`).

## CI e deploy

- `main` tem branch protection com **`strict` ligado** (branch precisa estar em
  dia) e **17 checks obrigatórios**. PR que fica para trás **reroda o CI inteiro**.
- Ciclo: CI ~10 min + deploy ~6 min. **Não prometa "7 minutos"** — isso é só a
  última perna.
- Deploy: `doctl apps create-deployment 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`.
  Migrações rodam sozinhas no job `release` (PRE_DEPLOY).
- A API GraphQL do GitHub cai com alguma frequência; a REST costuma seguir de pé:
  `gh api repos/pablondrina/django-shopman/pulls/<n>` e
  `.../commits/<sha>/check-runs`.
- ⚠️ **Check verde não prova que o merge funciona** — prova que funcionava na base
  em que o CI rodou. Antes de mergear PR parado, mescle o `main` e rode de novo.

## Como entregar

- Branch e PR com base `main`; corpo em português explicando **o porquê**.
- Commits no estilo do repo: título curto no imperativo, corpo com o motivo e o
  que quebraria sem aquilo, terminando com
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **NÃO mergeie sem o dono mandar.** Ele acompanha e decide quando publicar.

## O que NÃO fazer

- Não invente um segundo padrão de ledger — siga o `Move`.
- Não deixe os cinco rastros onde estão "para migrar depois".
- Não crave a polaridade da gaveta em constante.
- Não ponha carência na trava.
- Não trave quando o estado for desconhecido.
- Não prometa imutabilidade que o app-level não entrega.
