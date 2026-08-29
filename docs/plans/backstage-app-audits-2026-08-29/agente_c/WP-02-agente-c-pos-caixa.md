# WP-02-agente-c — PDV / Caixa

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** `surfaces/pos-nuxt` + `shopman/backstage/{api,projections,services}/pos*` + `shopman/shop/services/pos*`
**Objetivo:** o terminal que a tela mostra é o terminal em que o dinheiro é lançado; o que o operador declara é o que o livro registra; e nada de dinheiro entra duas vezes porque o wi-fi caiu.

> ⚠️ **Este WP contém o achado mais grave dos nove, e ele pode já estar no ar.**
> Ver P0-1 e a pergunta 1 — a resposta decide se isto é WP ou hotfix.

## Diferenças vs. WP-02 (Agente G) e WP-02-agente-d

**Agravado, com prova executada:** o Agente D identificou o mecanismo dos dois resolvers de terminal e
**inverteu o exemplo** — o caso que ele cita (`totem-01` depois de `pdv-main` em ordem alfabética) não
quebra. O caso que quebra é qualquer ref **antes** de `pdv-main`: `balcao-2`, `caixa-02`, `atendimento`. E o
efeito é maior do que ambos descreveram: não é "operar no caixa errado", é **o PDV parar de vender** com uma
mensagem que mente sobre o motivo.

**Confirmado com prova:** abrir caixa com `-10` cria o turno com **zero lançamentos** — nem o `FLOAT_IN` — e
a contagem cega do dia inteiro parte de um esperado envenenado.

**Refutados / descartados (não entram):**
- **"Pagamento digitado pode desaparecer" (G, P1).** O mecanismo existe, o dano não se materializa: o botão
  Finalizar só habilita com o total da *review* coberto, e o excedente não-dinheiro já é avisado nos dois
  lados. O que sobra — cartão não dá troco — é o comportamento correto. Vira item de teste (fuzz de tender),
  não de implementação.
- **"Implementar dedupe de `fire_tab` por `client_request_id`" (G, P2).** Refutado: quebraria o disparo
  progressivo por curso. A idempotência real é do ledger do KDS, por `line_id`, sob `select_for_update`. O
  Agente D acertou; a correção é ajustar a **declaração**, não o comportamento.
- **"Sem estação vinculada, o PDV não abre estado mutável" como aceite do P0 (D).** Contradiz
  `Terminal.default()`, que é decisão de produto explícita e comentada ("loja com um só balcão não deve
  precisar cadastrar terminal"). É **fase 2**, separável — não pré-requisito do conserto.
- **"Review e close divergem" como achado próprio (D).** Toda recusa do close tem aviso correspondente na
  review, com o mesmo `code`. É escalada preview→commit, e o código estável é justamente o que deixa a tela
  bloquear antes. O que falta é o **teste** que trava isso, não uma refatoração.
- **"O desconto valida A e persiste B" (D).** Formulação errada. O defeito real é pior e está no P2-1.
- **"Permissão única gateando riscos diferentes"** (pauta comum dos dois). Refutado aqui: o gate único é a
  porta; o risco é regateado por PIN, `perform_closing` e `audit_shift`.
- **"Manifest de actions gerado" como bloco de infra (G).** Custo desproporcional: nada valida
  `payload_schema` em runtime e todos os hrefs conferem hoje. Reduzir ao que paga — corrigir os três schemas
  errados e **um** teste que resolve cada `href` contra a URLconf. Ver também WP-00 Bloco A, que mostra que o
  manifesto já existe e o trabalho é honrá-lo.

**Novos:** `approved_by` de desconto gravado sem verificação nenhuma; movimento de caixa sem idempotência;
`serveChangeRequest` com URL hardcoded.

**Procurado e não achado** (registro pelo valor do negativo): sem PII no SSE do caixa; o browser **não**
consegue escolher o turno da venda; sem parsing frouxo no intent da venda (chave desconhecida é recusada);
sem duplicação de venda por duplo clique — a venda já é idempotente.

## Pré-requisitos

⚠️ **Sobreposição em voo (29/08):** o [PR #396](https://github.com/nelsonboulangerie/django-shopman/pull/396)
(sessão `confident-pasteur-6cf01c`) reescreve o fluxo da gaveta — a trava passa a ser **dura**, o PDV para
até o sensor dizer que fechou. Isso toca `drawer_open` e `drawer_unlock`, que são **duas das oito ações de
dinheiro** do WP-00 Bloco A, e traz dois tipos de alerta novos em `backstage/models/alerts.py`
(migration `backstage 0038`). O #396 está **empilhado no #395** — mergear o #395 primeiro. **Aplicar o Bloco A
sobre o fluxo novo, depois do merge**, não sobre o de hoje. Migrations deste WP começam em `backstage 0039`.

⚠️ E o mesmo PR mexe em `OperatorLock.vue` e `useOperatorLock.ts` na `operator-kit`. **Falar com aquela
sessão antes de escrever qualquer coisa sobre login, PIN ou crachá de operador** — é retrabalho garantido.

- **WP-00 Bloco A** (idempotência das ações de dinheiro): o P1-2 deste WP é a primeira aplicação concreta dele.
- **WP-00 Bloco D**: toca `shopman/backstage/api/operations.py` → **onda 2, branch único** com WP-03 e WP-05.
- **Resposta à pergunta 1** decide se o P0-1 sai antes de tudo, como hotfix.

## Achados priorizados

### P0-1 — Dois resolvers de terminal: um segundo terminal cadastrado no Admin paralisa o PDV

**Mecanismo, do clique ao efeito.**

1. A gerente tem `add_terminal`/`change_terminal` e cadastra o segundo aparelho em Equipamentos com ref
   `balcao-2` — qualquer coisa que venha antes de `pdv-main` em ordem alfabética.
2. A projection resolve o terminal por `Terminal.default()` → **`pdv-main`**. A tela diz `pdv-main`.
3. O operador abre o caixa. A tela manda o ref que ela mostra → o turno abre em `pdv-main`. A projection
   recarrega e mostra **caixa aberto**. Tudo parece bem.
4. Daqui em diante, **toda** mutação que não carrega ref resolve por
   `Terminal.objects.filter(is_active=True).order_by("ref").first()` → **`balcao-2`**, que não tem turno:
   - sangria, suprimento, abertura de gaveta, destrave, pedido de troco, atender/cancelar troco e devolução
     em dinheiro → `"Caixa não aberto."`;
   - review e close da venda → **409 `cash_shift_required`**: **não se vende mais nada**;
   - fechar o caixa não manda ref → "Caixa não aberto": o turno aberto **não pode ser fechado pela tela**.
5. O operador lê "Abra o caixa antes de finalizar" numa tela que mostra o caixa aberto. **Não há saída pela UI.**

**Por que passou.** Todo teste do caixa roda com **um** terminal — um deles chega a afirmar
`shift.terminal == Terminal.default()`, o que só é verdade no mundo de uma gaveta. O comentário em
`current_shift` já previu o problema ("quem chama precisa passar o ref"), e o único chamador que obedeceu foi
o comprovante.

**Fix mínimo — um resolver só.** Promover `_terminal` a público (`resolve_terminal`) em
`backstage/services/pos.py` e trocar, em `projections/pos.py:454-457`:

```python
        terminal = resolve_terminal("")
```

Projection e mutação passam a concordar sempre. O endurecimento proposto pelo Agente D — falhar fechado com
409 quando há dois ou mais terminais ativos e nenhuma estação vinculada — é a **fase 2**, correta e
separável.

### P1-1 — "Abrir caixa" com valor negativo abre com R$ 0 em silêncio

A assimetria é gritante: o fechamento **recusa** negativo, e o próprio `parse_money_to_q` tem docstring
dizendo que devolver zero silencioso num fechamento cego transformaria um erro de digitação numa diferença
gigante sem aviso. A abertura faz exatamente isso.

**Mecanismo.** O operador digita `-10`. O parser devolve `-1000`; um `max(0, …)` em
`backstage/services/pos.py:65` devolve `0`; o turno abre sem lançar `FLOAT_IN` nenhum, e o guard do cashman
(`float_q < 0`) nunca vê o sinal. **Provado:** turno criado, livro vazio. O operador acha que declarou o
fundo; a contagem cega no fim do dia acusa o fundo real como diferença sem explicação.

**Fix mínimo — uma linha:** remover o `max(0, …)`. O `CashError("INVALID_AMOUNT")` do pacote já vira
`POSError` no `except` logo abaixo e a view devolve 400 com `field: opening_amount`. Vazio continua valendo
zero.

### P1-2 — Movimento de caixa não tem idempotência: uma resposta perdida vira sangria em dobro

Primeira aplicação concreta do WP-00 Bloco A, e o item de dinheiro mais provável de acontecer num dia normal.

**Mecanismo.** A view de movimento não aceita nem consome `client_request_id`, e a ação declara honestamente
`idempotency="none"`. O front tem só uma trava de reentrância local e **não** faz retry automático. Numa
resposta perdida — wi-fi da padaria, proxy, tablet dormindo — o fetch estoura, a tela diz "Falha ao registrar
movimento" e o operador aperta de novo com o mesmo corpo, inclusive o mesmo `manager_approval`, que revalida
e passa. Duas linhas de R$ 100 no livro; o esperado cai R$ 200 por R$ 100 que saíram; a contagem cega fecha
com sobra de R$ 100 e ninguém consegue explicar. Vale igual para o acerto de conta, que é **entrada** de
dinheiro, sem PIN e sem chave.

**Fix mínimo:** aceitar `client_request_id` nas duas views e reusar o `IdempotencyKey` que a venda já usa,
com escopo `cash-movement:<shift_id>`; declarar `idempotency="client_request_id"` nas duas ações.

### P2-1 — `approved_by` de desconto é gravado sem verificação nenhuma

**Mecanismo.** O validador de aprovação gerencial **retorna cedo** quando não há motivos que exijam desafio —
desconto abaixo do teto, sem override de preço: nada é verificado. Mas a construção das operações da sessão
lê `manager_approval.username` do payload **incondicionalmente** e carimba `price_approved_by`,
`line_discount.approved_by` e `manual_discount.approved_by`. O parser do intent aceita
`{"username": "joyce", "pin": ""}`. Um payload montado à mão — ou uma tela com o campo de gerente preenchido e
o PIN limpo — grava no pedido que a Joyce aprovou um desconto que ela nunca viu.

Quando a aprovação **é** exigida, o nome persistido coincide com o verificado, e por isso o defeito é
invisível nos testes atuais.

**Fix mínimo — uma linha:** no ramo em que não há motivos, zerar `payload["manager_approval"]` (assinatura só
existe quando houve desafio). **Fix estrutural:** o validador devolve o `User` verificado e a construção usa
esse nome em vez de ler o payload — o mesmo remédio que o cancelamento de venda recente já aplicou, e que a
docstring do override descreve como lição aprendida.

### P2-2 — Aprovação gerencial: dois parsers, e o crachá morre na porta

O override de caixa aceita **crachá ou usuário+PIN**, recusa autoassinatura nas duas portas e devolve o
usuário verificado. O validador de desconto aceita **apenas** usuário+PIN e não devolve nada. E o parser do
intent copia só `username` e `pin`: mesmo que a tela mandasse crachá, ele morreria na porta. Resultado: o
gerente com o crachá no pescoço autoriza uma sangria encostando o crachá, e precisa digitar usuário e PIN
para liberar um desconto. É atrito no balcão — e atrito é o que faz o time deixar de chamar o gerente.

**Fix:** o validador de desconto delega ao de override quando há motivos; o parser do intent preserva o
crachá. Duas mudanças pequenas, um parser só. **Dono: o orquestrador.**

### P2-3 — Fechamento do dia: quantidade ilegível vira 0 em silêncio

O operador digita `1O` (letra O) ou `2,5` na sobra de um SKU. O parser devolve `0`, o fluxo toma o caminho
"nada sobrou", nenhum write-off acontece, e o snapshot grava zero. A divergência aparece depois na
conciliação como venda fantasma, sem ninguém saber de onde veio. É o mesmo defeito que `parse_money_to_q` foi
escrito para **não** cometer.

**Fix:** levantar `ValueError("Quantidade inválida em <sku>.")`; a view já traduz para 400.
⚠️ Se houver WP de fechamento do dia, este achado migra para lá — é uma linha, sem dependência.

### P2-4 — Três declarações erradas no contrato de ações

`request_change` declara `{"required": ["kind"], "optional": ["amount","note"]}` — e `kind` **não existe em
lugar nenhum**: é resíduo de um tipo que o próprio docstring conta que foi removido. O endpoint lê
`amount`/`denominations`/`note` e exige `amount > 0`. `close_cash_shift` não declara `terminal_ref`, que o
endpoint lê. `fire_tab` promete `idempotency="client_request_id"` e a proteção real é o ledger.

**Fix:** três linhas na projection (`fire_tab` passa a declarar `idempotency="ledger"`, com nota apontando o
`line_id`) e **um teste** que percorre as ações e resolve cada `href` contra a URLconf. Isso pega a próxima
divergência sem construir infraestrutura nova.

### P3-1 — `serveChangeRequest` é a única mutação do PDV com URL hardcoded

Monta o path na mão sem passar pelo helper de href, apesar de a ação existir na projection. Não quebra hoje —
o path bate. É o ponto que a varredura do P2-4 deve cobrir junto.

## RBAC / `setup_groups`

**Nenhuma mudança.** O Caixa segue com `cashman.operate_pos` + `shop.manage_orders`; o PIN de gerente reusa
`cashman.adjust_shift`, que o Gerente já tem; fechar caixa reusa `backstage.perform_closing`; o X/Z reusa
`cashman.audit_shift`, que **só o Dono** tem — e o comentário do arquivo explica por que o Gerente não entra
ali. Confirmo a seção RBAC do Agente D.

## Testes

| # | Aceite | Prova |
|---|---|---|
| 1 | Com dois terminais ativos, o terminal da projection é o mesmo do turno. | Backend: cria os dois, abre turno pelo fluxo da UI, assert de paridade. |
| 2 | Com dois terminais ativos, sangria/gaveta/troco/refund não dizem "Caixa não aberto" com turno aberto. | Backend, um assert por mutação. |
| 3 | Com dois terminais ativos, o close da venda **não** devolve 409 `cash_shift_required`. | API, assert-negativo. |
| 4 | Turno aberto por um terminal pode ser fechado pela mesma tela sem passar ref. | API. |
| 5 | `opening_amount="-10"` devolve 400 com `field == "opening_amount"` e **nenhum** turno é criado. | API; espelha o teste que já existe para o fechamento. |
| 6 | `opening_amount=""` continua abrindo com zero. | Backend (regressão). |
| 7 | Cada `href` das ações resolve contra a URLconf, e cada chave `required` é lida pela view. | Contrato, varrendo as 25 ações. |
| 8 | `request_change` declara `required:["amount"]` e `optional` com `denominations`. | Assert na projection. |
| 9 | `fire_tab` **não** declara `client_request_id`; duplo disparo do mesmo curso não duplica ticket. | Projection + teste de fire existente. |
| 10 | Venda com desconto abaixo do teto e `manager_approval` com PIN vazio fecha **sem** gravar `approved_by`. | Assert-negativo de payload. |
| 11 | Todo `code` de erro do close tem warning correspondente na review, para o mesmo payload. | Paridade parametrizada (cash/pix/card/misto/conta/parcial/excedente). |
| 12 | Duplo movimento com o mesmo `client_request_id` cria **uma** entrada no livro. | API. |
| 13 | Quantidade ilegível no fechamento devolve 400 e não grava o fechamento. | API. |
| 14 | O canal SSE do caixa continua sem PII. | Assert-negativo (a fixture já existe). |

## Arquivos tocados (para a matriz de colisão)

| Arquivo | Risco | Quem mais mexe |
|---|---|---|
| `shopman/backstage/api/operations.py` | **ALTO** | WP-03 e WP-05 no mesmo arquivo. **Onda 2, branch único.** Faixas deste WP: `214-232`, `1850-2350`, `2244-2260`. |
| `shopman/shop/services/pos.py` (3.423 linhas) | **ALTO** | Dono é o orquestrador. Faixas: `1375-1420`, `1550-1560`, `1661-1695`. |
| `shopman/backstage/projections/pos.py` | MÉDIO | Faixas: `440-460`, `940-1235`. Colide com WP de catálogo/vitrine. |
| `shopman/backstage/services/pos.py` | BAIXO | — |
| `shopman/shop/services/pos_intent.py` | MÉDIO | orquestrador |
| `shopman/backstage/services/closing.py` | MÉDIO | migrar P2-3 se houver WP de fechamento |
| `surfaces/pos-nuxt/app/composables/usePosCashSession.ts` | BAIXO | exclusivo do PDV |

**Não tocar:** `packages/cashman/**`. O guard de fundo negativo já está certo — só precisa parar de ser
contornado.

## Fora de escopo

Produção, KDS, pedidos, marketing. Cadastro de Terminal no Admin (é do WP-09) — mas é **a porta que dispara o
P0-1**, então o conserto do P0-1 é pré-requisito de qualquer trabalho de multi-terminal. Estação confiável e
vínculo terminal↔estação: fase 2, depende da pergunta 2.

## Perguntas para o dono do produto

1. **O alpha tem mais de um `Terminal` ativo hoje?** O seed só cria `pdv-main`, mas a gerente pode cadastrar
   outro pelo Admin. Se já houver um segundo com ref anterior a `pdv-main` em ordem alfabética, **o PDV já
   está quebrado em produção** e o P0-1 vira hotfix, não WP. É uma consulta de um comando ao banco do alpha.
2. **Quando houver balcão e totem, o terminal vem da estação confiável ou de uma escolha explícita do
   operador na antessala?** A fase 2 muda de desenho conforme a resposta.
3. **Fundo de troco negativo deve ser 400 ou 0 com aviso?** Proponho 400, para espelhar o fechamento. Mas se
   o balcão usa "-" como atalho de alguma coisa hoje, quero saber antes de trocar um zero silencioso por uma
   parede na abertura do dia.

## Prompt para agente executor

~~~text
Execute WP-02-agente-c (PDV / Caixa).

⚠️ ANTES DE TUDO: responda a pergunta 1 (o alpha tem 2+ Terminal ativos?). Se tiver, o
P0-1 sai como HOTFIX isolado, hoje, fora deste WP e fora da onda.

⚠️ ONDA 2: toca shopman/backstage/api/operations.py, compartilhado com WP-03 e WP-05.
Branch UNICO com eles. Ver WP-00 Bloco D.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-02-agente-c-pos-caixa.md
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-00-agente-c-transversal.md (Bloco A)
- shopman/backstage/services/pos.py (_terminal :506, abertura :65, _open_shift_or_raise :638)
- shopman/backstage/projections/pos.py:440-460 e _pos_actions :938-1240
- shopman/backstage/api/operations.py:214-232, 1850-2350
- shopman/shop/services/pos.py:270-530 (o claim de idempotencia a reusar), 1375-1420, 1661-1754
- shopman/shop/services/pos_intent.py:392-399
- packages/cashman/**/shifts.py:57-76 — LER, nao alterar

Fases:
1. P0-1: um resolver so. Escreva os testes 1-4 ANTES; eles devem falhar com dois terminais.
2. P1-1: tirar o max(0,...) da abertura + testes 5 e 6.
3. P1-2: client_request_id no movimento e no acerto de conta, reusando o claim da venda.
4. P2-1: zerar manager_approval quando nao houve desafio + teste 10.
5. P2-4 + P3-1: tres declaracoes na projection + o teste 7 que resolve href contra a URLconf.
6. P2-2 (parser unico de aprovacao) e P2-3 (quantidade ilegivel) — precisam do dono do shop.
7. Teste 11 (paridade review<->close) — trava a divergencia sem refatorar.

NAO implemente dedupe de fire_tab por client_request_id (quebra o fire por curso).
NAO construa gerador de manifest. NAO toque packages/cashman.
NAO exija estacao vinculada como pre-requisito do P0-1 — isso e fase 2.
~~~
