# PDV ao vivo: harness de operador e sondas

Tudo aqui roda contra um PDV de verdade (Django semeado + pos-nuxt compilado), nunca
contra o mock. Duas famílias:

- **Jornadas de operador** (`operador.live.spec.ts` e `jN-*.live.spec.ts`): a pessoa
  fazendo o que faz, pela tela. É o chão das provas da revisão de excelência do PDV
  (`docs/plans/EXCELENCIA-PDV-PLANO.md`, WP-E12, jornadas da seção 4).
- **Sondas** (`copy-overflow`, `checkout-latency`): medições de tela cheia e de tempo,
  descritas no fim deste arquivo.

## Harness de operador (WP-E12)

### Um comando

Da raiz do repositório (ou da worktree):

```bash
lockf /tmp/shopman-pesado.lock scripts/run_pos_e2e_live.sh
```

O `lockf` é a trava única da máquina (coordenação, 17/11/2026): build, seed, pilha e
Playwright de todas as frentes esperam a vez nela, para não haver dois pesados juntos.
Na CI, ou numa máquina só sua, o script roda sem ele.

O script, em ordem:

1. cria o banco `shopman_pdv_e12` se faltar, roda `migrate` e `seed --flush` (o elenco de
   `setup_operators` vem junto). O seed roda com `SHOPMAN_STAGING_AUTOPILOT=true`, que no
   seed só abre a casa todo dia, o dia inteiro, sem feriado, como na pilha do Gestor.
   Assim a jornada que vende "Hoje" roda em qualquer dia; com o horário real, ela caía no
   domingo (#3295). O runserver e o worker sobem sem a variável;
2. põe a trava automática do PDV principal em **900 s** (ver "Ajustes declarados");
3. compila o PDV e a Cozinha (`nuxt build`, um de cada vez);
4. sobe Django `:8052` (com o worker de directives), PDV `:3162` e Cozinha `:3163`;
5. roda o Playwright: a fumaça J0 e toda jornada `jN-*.live.spec.ts`;
6. derruba tudo ao sair.

O navegador abre o PDV em `http://pdve12.localhost:3162`, não em `127.0.0.1`: o cookie de
sessão é por **host**, não por porta, e outras pilhas usam `127.0.0.1` no mesmo navegador.
Um `*.localhost` resolve para o loopback no Chromium sem mexer em `/etc/hosts`.

Variáveis do script:

| Variável | Para quê |
|---|---|
| `PDV_LIVE_SKIP_BUILD=1` | reaproveita os `.output` já compilados (mudou só o teste) |
| `PDV_LIVE_SKIP_SEED=1` | reaproveita o banco (sem `migrate` nem `seed`) |
| `PDV_LIVE_KEEP=1` | deixa a pilha de pé depois do Playwright (Ctrl+C derruba) |
| `PDV_LIVE_UP_ONLY=1` | só sobe a pilha e espera: para escrever jornada com o Playwright à mão |
| `PDV_LIVE_SHOTS=<pasta>` | copia as capturas de cada passo para a pasta (para o PR) |
| `PDV_LIVE_DJANGO_PORT`, `PDV_LIVE_POS_PORT`, `PDV_LIVE_KDS_PORT`, `PDV_LIVE_DB`, `PDV_LIVE_HOST` | outra pilha ao lado desta |
| `PDV_LIVE_AUTO_LOCK_SECONDS` | outro valor para a trava automática |

Argumentos depois do script vão para o Playwright como filtro (`scripts/run_pos_e2e_live.sh
j2` roda só a J2). Os logs ficam em `$TMPDIR/shopman-pdv-live-8052/` (Django, worker, PDV,
Cozinha, builds); o script diz onde.

Para iterar num spec com a pilha de pé (`PDV_LIVE_UP_ONLY=1` noutro terminal), de
`surfaces/pos-nuxt`:

```bash
PDV_LIVE_URL=http://pdve12.localhost:3162 PDV_LIVE_KITCHEN_URL=http://pdve12.localhost:3163 \
  npm run test:live -- operador
```

As capturas de cada passo ficam em `test-results/` (fora do git) e no relatório do
Playwright.

### O que a fumaça prova (J0 Entrar)

`operador.live.spec.ts`, em **375 px** (celular, toque) e **1366 px** (balcão), cada um num
dispositivo novo em folha:

1. "Entre para operar o caixa": a Gerente (`joyce`) entra com usuário e senha;
2. no diálogo "Vincular este dispositivo a um posto de trabalho?", que sobe sozinho,
   vincula o dispositivo ao posto "PDV principal" (no segundo dispositivo do mesmo posto
   o servidor pede a segunda palavra, "Vincular também a este posto", e ela confirma);
3. trava: no balcão pelo "Bloquear" do rail; no celular pelo trocador de seções do
   cabeçalho, "Trocar ou bloquear";
4. a Caixa (`fran`) toca no próprio nome, digita o PIN no teclado da tela e confirma;
5. o quadro de comandas aparece, com a Fran operando (no celular, conferida no
   "Operando: Fran" do trocador).

### Regras da casa (não negociáveis)

Vêm de `docs/coordination/ROUNDS/EXCELENCIA-base.md`, seção "Teste como um operador de
verdade":

- **Pela tela.** Nada de superusuário, `force_login`, API, Admin ou banco para chegar a um
  estado. Se a jornada precisa de uma encomenda pronta, a encomenda nasce pela tela,
  no mesmo teste, antes do passo que a usa.
- **Papel real.** Gerente `joyce` (senha `admin`, PIN 1234), Caixa `fran` (PIN 1234),
  Cozinha `diofer` (PIN 1234), todos de
  `shopman/shop/management/commands/setup_operators.py`. Nunca o `admin`.
- **Dois tamanhos.** Toda jornada roda em 375 e 1366 px.
- **Um dispositivo é um contexto de navegador.** Nunca dois papéis no mesmo contexto.

### Ajustes declarados do ambiente

Nenhum muda regra de negócio; são do ambiente de teste e o script os faz às claras:

- **Trava automática do PDV principal em 900 s** (`cashman_terminal.metadata.auto_lock_seconds`,
  a mesma config que o Admin edita; padrão 60 s). Com 60 s o PDV trava no meio de uma
  jornada lenta e o teste mede a trava, não a jornada. A J9 (trava por ociosidade) baixa o
  valor por conta própria.
- **Pool de conexões ligado como no deploy** (`DATABASE_CONN_MAX_AGE=0`). Sem ele cada
  request abre conexão e a tela estoura o limite de 15 s numa máquina carregada.
- **Código de entrada por console** (`SHOPMAN_OTP_DELIVERY_CHAIN=console`): nenhum SMS sai
  da pilha.

### Como escrever as jornadas J1 a J10

Cada WP do PDV escreve a jornada que canoniza (tabela da seção 4 do plano) como um arquivo
`jN-<nome>.live.spec.ts` nesta pasta: o script já o pega pelo nome. O ponto de partida é a
fixture `cashierAtCounter` de `support/operator.ts`: um dispositivo novo, iniciado pela
Gerente no PDV principal, travado, e a Fran no quadro de comandas.

```ts
import { capture, expect, test } from "./support/operator";

for (const device of ["phone", "counter"] as const) {
  test.describe(`J2 Balcão em dinheiro · ${device === "phone" ? "375 px" : "1366 px"}`, () => {
    test.use({ device });

    test("dois itens, R$ 50, troco, próxima venda", async ({ cashierAtCounter: page }, testInfo) => {
      await page.getByRole("button", { name: /Próxima livre/ }).first().click();
      // ... os passos da Fran, pela tela, com uma captura por passo:
      await capture(page, testInfo, "troco");
    });
  });
}
```

O que a fixture oferece:

| Peça | O que é |
|---|---|
| `test` (`device`, `freshDevice`, `cashierAtCounter`) | o `test` do Playwright com o tamanho do dispositivo, um dispositivo novo e a Caixa já operando |
| `newDevice(browser, "phone" \| "counter", url?)` | um segundo dispositivo (a Gerente noutro balcão, a Cozinha em `stack.kitchen`) |
| `managerSignsIn`, `managerBindsStation`, `lockDevice`, `operatorUnlocksWithPin`, `seesOperator`, `seesTabs` | os gestos da J0, para jornada que troca de operador no meio (J3, J7, J9, J10) |
| `cast`, `MAIN_STATION`, `stack` | o elenco, o posto do seed e as URLs da pilha |
| `capture(page, testInfo, nome)` | captura numerada do passo, anexada ao relatório |
| `settled(page)` | espera o Nuxt hidratar antes de digitar |

Para uma assinatura da Gerente no meio da venda (J3, J7), a jornada abre o diálogo de
autorização pela tela e digita o PIN dela (`cast.manager.pin`); para a Cozinha (J4), abre
um segundo dispositivo em `stack.kitchen` com `newDevice` e faz a Gerente iniciá-lo do
mesmo jeito. A jornada roda de novo sem reseed: cada execução é um dispositivo novo e cria
as próprias comandas. Use nomes de cliente ou observações únicos por execução se a
jornada procurar algo pelo texto.

Os gestos da encomenda (abrir, identificar o cliente, escolher o dia pelo calendário,
montar a comanda) moram em `support/order.ts`, para a J5 e a J-P5 usarem os mesmos.

### J-P5: pedido à Produção (plano da Produção, WP-F13)

`jp5-pedido-a-producao.live.spec.ts` cruza o PDV e a Produção: a Caixa encomenda 30
croissants para daqui a doze dias, uma data que o seed não planejou, e a encomenda fecha
sem gerente; a Cozinha, com PIN, abre o Planejamento daquela data no celular e no tablet
(1024 px) e lê a encomenda no chip da linha do Croissant ("30 un. · <dia> <hora>"), cuja
sugestão já a conta: a faixa do topo não a repete (a faixa é só para o que nenhuma linha
cobre). Ela planeja a sugestão pela linha, e o detalhe da encomenda no PDV segue sem
"Promessa em risco". `JP5_DAYS_AHEAD` escolhe outra data num banco já usado. Pede a
Produção compilada na pilha, em `PDV_LIVE_PRODUCTION_URL` (o script não a sobe), e pula
sem ela:

```bash
(cd surfaces/production-nuxt && NUXT_DJANGO_BASE_URL=<django> NUXT_SHOPMAN_ENVIRONMENT=local npx nuxt build \
  && NUXT_SHOPMAN_ENVIRONMENT=test SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1 NUXT_DJANGO_BASE_URL=<django> \
     HOST=127.0.0.1 PORT=<porta> node .output/server/index.mjs &)
```

O filtro padrão do script (`jN-*`) não a pega: rode pelo nome (`scripts/run_pos_e2e_live.sh
jp5`, com a Produção de pé). O Django precisa da origem da Produção em
`CSRF_TRUSTED_ORIGINS`. Planeja o croissant da
data, então roda uma vez por seed (numa segunda passada a data já tem lote e a faixa diz
"acima do plano").

### Armadilhas medidas (16/11/2026)

- **`.venv` com `psycopg` 3.3.6 e `psycopg-binary` 3.3.5**: o `migrate` cai com
  `wait_c() got an unexpected keyword argument 'timeout'`. O script detecta e instala o
  `psycopg` da versão do binário numa pasta de cache (`~/.cache/shopman-e2e/`), na frente
  do `PYTHONPATH`, sem tocar no `.venv` compartilhado.
- **Worktree**: o `.venv` da raiz aponta para a árvore principal; o script põe a worktree
  e cada `packages/*` no `PYTHONPATH` e usa o Python da árvore principal.
- **Máquina carregada**: `npm ci` e `nuxt build` levam muitos minutos cada. Não rode build
  e vitest juntos. Os tempos limite dos gestos são de jornada (até 90 s no login e no
  vínculo, que recarregam a página inteira), não de clique.
- **Digitar antes da hidratação perde o texto**: os gestos esperam `settled` antes de
  preencher.
- **Migração com trava de produção** (`SET LOCAL statement_timeout = '30s'`, ex.:
  `shop.0053`) estourou com carga 90, mesmo com o banco vazio (17/11). O script tenta o
  `migrate` de novo até três vezes; cada migração é atômica e a nova tentativa continua de
  onde parou.
- **Processo em segundo plano por função de shell não morre no fim**: `manage runserver &`
  guarda o PID do subshell, e o Python ficava órfão na porta 8052. O script chama o
  Python direto para o `runserver` e o worker.

## Sonda: texto cortado

`copy-overflow.live.spec.ts` percorre as telas principais do PDV em **1366×768,
1280×800 e 1024×768**, com a barra lateral **compacta** e **estendida**, e mede
todo elemento com texto que não cabe na própria caixa
(`surfaces/operator-kit/tests/support/clippedText.js`):

| tipo | o que é |
|---|---|
| `ellipsis` | `text-overflow: ellipsis` cortando de fato ("Dividir co…") |
| `clip-x` / `clip-y` | overflow oculto com o conteúdo maior que a caixa (`line-clamp`) |
| `clip-parent` | o texto passa da borda de um ancestral que corta |
| `spill` | o texto sai da própria caixa ou da tela |
| `crushed` | a coluna ficou tão estreita que a frase vira uma palavra por linha |

O critério (`violatesHouseRule`) é o da casa: **aviso e título nunca se cortam,
coluna esmagada nunca passa**; o resto só passa cortado com o texto INTEIRO no
`title` (dado do usuário: nome de produto, cliente, resumo da comanda). O rótulo
fixo de botão nem chega aqui: `truncate` em texto escrito no template reprova na
varredura estática `operator-kit/tests/guardrails.copyNeverTruncates.test.ts`,
que roda em todo CI.

### Por que ao vivo, e não no mock

As telas que estouram são as **cheias**: comanda com itens, encomenda de entrega
com cliente, endereço e data, os bloqueios do pagamento, a semana de encomendas.
O `mockBackend.mjs` só sabe dizer 401. Esta sonda roda contra um PDV de verdade:
Django semeado + pos-nuxt.

### Como rodar

```bash
# 1. Django semeado (banco local à parte, para não mexer no seu)
createdb shopman_sonda
DATABASE_URL=postgres://localhost/shopman_sonda DJANGO_DEBUG=1 .venv/bin/python manage.py migrate
DATABASE_URL=postgres://localhost/shopman_sonda DJANGO_DEBUG=1 .venv/bin/python manage.py seed --profile qa
# os avisos da nota da entrega (endereço incompleto) só aparecem com um resolver
# fiscal que emita na entrega (o do alpha):
SHOPMAN_FISCAL_EMISSION_RESOLVER="shopman.shop.fiscal_resolvers.on_request_or_tax_id,shopman.shop.fiscal_resolvers.eletronic_payment,shopman.shop.fiscal_resolvers.deferred_settlement" \
DATABASE_URL=postgres://localhost/shopman_sonda DJANGO_DEBUG=1 .venv/bin/python manage.py runserver 127.0.0.1:8811

# 2. o PDV apontando para ele
cd surfaces/pos-nuxt
NUXT_DJANGO_BASE_URL=http://127.0.0.1:8811 npx nuxi dev --port 3312

# 3. a sonda (usuário com senha que abre o caixa — o superusuário do seed)
PDV_LIVE_URL=http://127.0.0.1:3312 PDV_LIVE_USER=<usuário> PDV_LIVE_PASSWORD=<senha> \
  PDV_LIVE_SHOTS=/tmp/sonda-shots PDV_LIVE_REPORT=/tmp/sonda.json \
  npm run test:live
```

Variáveis opcionais: `PDV_LIVE_RAILS` (`compact,extended`), `PDV_LIVE_CUSTOMER`
(cliente com endereço salvo; padrão do seed: Ana Ferreira), `PDV_LIVE_PRODUCTS`
(nomes separados por `|`). `PDV_LIVE_SHOTS` guarda um retrato por tela medida;
`PDV_LIVE_REPORT` guarda todos os achados (inclusive os aceitos) e os passos que
não acharam o que procuravam (`skipped`).

A sonda cria comandas e fecha uma venda de verdade no banco que você apontar.
Use um banco descartável.

## Sonda: tempo até o total

`checkout-latency.live.spec.ts` lança dez produtos numa comanda, toca em
**Pagamento** e mede o tempo até o total confirmado pelo servidor (nenhum
"Calculando…" na tela), listando cada requisição do intervalo com início e fim:
é o mapa de série × paralelo do caminho do total.

Roda contra o mesmo PDV de verdade da sonda acima. Para reproduzir o alpha,
ponha atrasos entre as peças (navegador → BFF ~150 ms de ida e volta, BFF →
Django, Django → Postgres) com qualquer proxy TCP de latência, e suba o Django
com `daphne`, como em produção.

```bash
PDV_LIVE_URL=http://127.0.0.1:3312 PDV_LIVE_USER=<usuário> PDV_LIVE_PASSWORD=<senha> \
  PDV_LIVE_ROUNDS=3 PDV_LIVE_REPORT=/tmp/total.json \
  npx playwright test -c playwright.live.config.ts checkout-latency
```

Variáveis: `PDV_LIVE_LINES` (itens por venda, padrão 10), `PDV_LIVE_TAP_MS`
(intervalo entre toques, padrão 250), `PDV_LIVE_PAUSE_MS` (do último toque ao
Pagamento, padrão 300), `PDV_LIVE_ROUNDS`.

# Jornada J4 — a grade ouve o estoque

`j4-grade-ouve-o-estoque.live.spec.ts` abre **dois dispositivos** do mesmo balcão.
A Caixa vende a última unidade de um pão no dispositivo A, em dinheiro; o
dispositivo B, sem ninguém tocar nele, precisa mostrar o tile "Esgotado" em até
5 s (aviso `stock-update` → `/sse/stock` → releitura `pos/?only=availability`).
Depois, o B ainda vende o que é feito na hora (o café): esgotar o pão não trava a
grade.

Antes de rodar, deixe UMA unidade do pão no estoque do canal do PDV (no banco
descartável da sonda), por exemplo com o `manage.py shell` do Django da pilha:

```python
from decimal import Decimal
from shopman.stockman.service import StockService  # ou o Admin do Estoque
# zere o saldo do SKU e dê entrada de 1 unidade na posição de venda
```

```bash
PDV_LIVE_URL=http://127.0.0.1:3312 PDV_LIVE_USER=<usuário> PDV_LIVE_PASSWORD=<senha> \
  PDV_LIVE_LAST_UNIT="Baguete Gergelim" PDV_LIVE_MADE_TO_ORDER="Cappuccino" \
  PDV_LIVE_SHOTS=/tmp/j4 npx playwright test -c playwright.live.config.ts j4-grade
```
