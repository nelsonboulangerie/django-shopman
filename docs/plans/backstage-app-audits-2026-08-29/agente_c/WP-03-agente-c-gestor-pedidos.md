# WP-03-agente-c — Gestor de Pedidos

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** `surfaces/orders-nuxt` + `shopman/backstage/{api,projections,services}/order*` + `shopman/shop/services/operator_orders.py`
**Objetivo:** quando a tela diz que cancelou, cancelou; quando não dá para cancelar, o botão não está lá; e um erro de digitação num campo de troco não derruba o despacho.

## Diferenças vs. WP-03 (Agente G) e WP-03-agente-d

**O P0 do Agente D é real, e foi provado executando.** `POST /orders/<ref>/cancel/` num pedido `ready`
devolveu `200 {"ok": true}` com o pedido ainda `ready`. O Agente G descreveu o problema como "o backend falha
depois" — refutado: o backend responde sucesso. Entra a leitura do Agente D.

**Refutados (não entram):**
- **"Custódia vazia registrada" e "409 quando o canal exige equipamento" (D).** Sem base: `if taken:` não
  grava nada quando a lista é vazia, e **nenhum canal exige** aparelho — o próprio código documenta que é
  oferta. Um 409 aqui inventaria regra de negócio que o dono nunca pediu. Sobra um fix de uma linha no
  frontend (P2-1).
- **"Courier é heurística local" (G e D).** Refutado: `can_quote`, `can_dispatch` e `can_cancel` já são
  projetados **e** já são tipados no frontend. Sobra tipar o espelho gerado — cosmético, não é achado.
- **"Requeue fiscal por string `failed`" (G e D).** Refutado: é enum projetado pelo servidor, e o requeue
  falha fechado com motivo.
- **"Cancelar corrida deve exigir motivo" (D).** Como escrito, **quebra a única tela que chama o endpoint** —
  ela nunca envia motivo e não coleta nenhum. Exigir no servidor primeiro deixaria o operador sem conseguir
  cancelar corrida. Se o dono quiser motivo, é trabalho de UI **antes** do 400, não um 400 solto.
- **"Não há botão ativo sem capability" como aceite do manifest (G e D).** Já é verdade no board.

**Discordo do Agente D sobre RBAC, e a direção importa:** tirar `settle_delivery_cash` do Caixa é o inverso
do certo — acertar o dinheiro da entrega **é o trabalho dele**. O que deve subir de exigência é
cancelamento, fiscal e courier. Ver P2-2.

**Ampliado:** o achado do iFood é maior do que o Agente D disse — existe uma **segunda cópia** da lógica no
board, e o código de cancelamento padrão tem default `""` nas settings, então o pedido cancela localmente e
fica **vivo no marketplace**.

**Novos:** um typo num campo de dinheiro vira 500; o Caixa vê abas que sempre respondem 403 e a tela chama
isso de falha de rede; o painel de corrida some sem aviso; o sino de alertas dá "ack" com permissão de ver.

**Nota de custo:** o "manifest de ações" não é invenção — o padrão `Action(href, method, payload_schema)` já
roda no PDV. E permissões finas são baratas porque o resolvedor de códigos **já aceita tupla**. Ver WP-00
Bloco A.

## Pré-requisitos

- **WP-00 Bloco D**: toca `shopman/backstage/api/operations.py` → **onda 2, branch único** com WP-02 e WP-05.
- **Resposta à pergunta 1** decide o desenho do P2-2 (não bloqueia o P0-1).

## Achados priorizados

### P0-1 — Cancelar pedido responde sucesso e não cancela

**Mecanismo, do clique ao efeito.**

1. Um pedido `ready` está na coluna Saída — é o estado mais comum ali. O cliente liga para desistir. O
   operador abre o detalhe e clica **Cancelar**; o botão está sempre visível, sem guarda.
2. O diálogo de motivo aceita, e o POST vai.
3. A cadeia chega em `cancellation.cancel`, que consulta `order.can_transition_to(CANCELLED)`. Em
   `DEFAULT_TRANSITIONS`, `ready`, `dispatched`, `delivered` e `completed` **não** listam `cancelled` — e o
   canal do PDV também não, exceto de `completed`. → `return False`, com um `logger.info`, **sem exceção**.
4. `cancel_order` **ignora o retorno**. A view responde `200 {"ok": true}`. O diálogo fecha, o refresh
   redesenha o mesmo pedido `ready`. Nenhum toast de erro. **Nenhum estorno. Nenhum aviso ao iFood.**

**Prova executada:**

```
STATUS HTTP: 200 BODY: {'ok': True, 'ref': 'VERIF-READY'}
ORDER STATUS APOS CANCEL: ready
```

**Prova de que é descuido, não decisão:** `reject_order` — a ação irmã, no mesmo arquivo — trava com
`select_for_update` e levanta conflito de estado → 409. O cancelamento é a **única** ação de pedido que não
confere o resultado.

**Fix mínimo — três edições pequenas:** a fachada devolve o booleano; o serviço do backstage levanta
`OrderConflict` quando for falso; a view mapeia para 409 **antes** do `except OrderError` (o conflito é
subclasse, então a ordem importa). O frontend **já** trata 409 com mensagem honesta — nada a mudar lá para o
erro aparecer.

### P1-1 — O botão Cancelar existe onde o cancelamento é impossível

A metade preventiva do P0-1: o 409 conserta a mentira, o `can_cancel` evita o gesto inútil.

A projection do pedido expõe `can_confirm`, `can_advance`, `can_settle_delivery_cash` — e **nenhum
`can_cancel`**. O detalhe renderiza o botão sem guarda, com um comentário afirmando que Cancelar "segue
sempre disponível". Não segue.

**Fix:** dois campos calculados **pela própria máquina de estados** (sem duplicar regra): `can_cancel` e um
rótulo de bloqueio nomeando o status. Depois regerar o contrato TS — o teste de drift falha sem isso.

### P1-2 — Cancelar ou recusar pedido do iFood vira texto livre quando a lista de motivos falha

Fail-open num contrato externo, com estado divergente que ninguém reconcilia. E em duas cópias.

**Mecanismo.** A busca dos motivos do iFood tem `catch` que devolve `[]` — para **qualquer** erro: rede, 401
de OAuth, iFood fora. O modo marketplace é decidido por `reasons.length > 0`, e o board tem uma **segunda
implementação** da mesma decisão. Com lista vazia, o diálogo cai no modo texto livre e aceita até motivo
vazio. O código de cancelamento vai vazio; o pedido é cancelado localmente; o callback do iFood cai no código
padrão, que tem default `""` nas settings → erro → retry → falha definitiva.

**Resultado: o pedido está cancelado na casa e vivo no iFood.** O único sinal é o alerta genérico de
"directives falharam" que o relatório alpha de 28/08 já registrou.

**Fix, em ordem de valor:**
1. Distinguir "canal sem códigos" de "não consegui buscar": o `catch` devolve `null`, e com `null` o diálogo
   **bloqueia** cancelar/recusar de pedido do iFood com mensagem própria — nunca texto livre.
2. Unificar as duas cópias: o board passa a usar o mesmo diálogo do detalhe.
3. Se o dono aceitar, configurar o código de cancelamento padrão no spec vivo, como rede de segurança.

### P1-3 — Um typo de dinheiro no Gestor vira 500

**Mecanismo, provado executando.** O parser de dinheiro é chamado **fora** do `try` em `advance_order` e em
`settle_delivery_cash`. Ele levanta `POSError`, que é **irmã** de `OrderError`, não subclasse — as views só
capturam `OrderError`, o handler de erro não converte exceção não-DRF, e o Django responde **500**.

O caminho do operador: o diálogo "Troco para o entregador" ou "Acerto dinheiro" — campo de texto livre. Digite
`12,,30` e o servidor cai. A tela mostra "Falha na ação. Tente de novo."; o log mostra stacktrace; ninguém
sabe que foi o campo.

**Prova de que é descuido:** o **mesmo arquivo**, 13 linhas abaixo, comenta explicitamente que a tela "merece
o 400 com a mensagem do pacote, não um 500" — para `CashError`. `POSError` ficou de fora.

**Fix — duas linhas:** converter `POSError` em `OrderError` nas duas funções. Melhor ainda com `field`: o
dialeto da casa aceita `field`, e a tela sabe destacar o campo.

### P2-1 — A maquininha sai no lote sem ninguém registrar que saiu

Recalibrado de P1 para P2: **o troco já está protegido pelo servidor** (409 com erro por pedido). O que escapa
é só o registro de custódia de um aparelho físico — uma maquininha sem rastro no painel de "onde está".

O filtro de lote só olha troco. Um pedido de entrega sem troco pedido, num canal que oferece maquininha, entra
no lote e avança com equipamento vazio. **Fix — uma linha:** trocar o predicado do filtro pelo que já cobre
troco **e** equipamento, e que já existe ao lado. O card já carrega as opções.

### P2-2 — Uma permissão só cobre fila, dinheiro, fiscal e courier

Recalibrado de P1 para P2: o risco é real mas **interno** — quem tem `manage_orders` é Caixa e Gerente, não é
público aberto. O que incomoda é a assimetria com o resto da casa, que já separa `audit_shift` de
`operate_pos` pela mesma razão.

A base de ações de pedido gateia igualmente: avançar pedido, **acertar dinheiro na gaveta**, **reprocessar
NFC-e**, **cancelar pedido pago** e **cancelar corrida paga**.

**Fix — a máquina já existe:** o resolvedor de códigos já aceita tupla, e o padrão já está em uso em outro
lugar do arquivo. Basta declarar por view, sem tocar na base.

⚠️ **Não tirar `settle_delivery_cash` do Caixa.** A separação certa é o inverso do que o Agente D propôs. Ver
pergunta 1.

### P2-3 — O Caixa vê abas que sempre respondem 403, e a tela chama isso de falha de rede

A barra declara as três abas numa constante fixa, sem consultar capability. Catálogo e Feeds batem em
endpoints gateados por `shop.manage_catalog`, que o Caixa **não tem**. O resultado é 403, e a tela renderiza
*"Não foi possível carregar o catálogo. Tentar de novo"* — mesma frase para permissão negada, sessão expirada
e rede caída, com um botão de retry que nunca vai funcionar.

O board já sabe distinguir esses casos. O catálogo não.

**Fix mínimo:** mensagem própria para 403 ("Seu perfil não tem acesso ao catálogo"), **sem** botão de retry. O
passo completo — projetar as abas a partir de capabilities — é o mesmo trabalho do WP-00 Bloco A e pode andar
junto.

### P2-4 — Nota de cozinha muda sem trilha

A nota chega ao ticket do KDS e altera o que a cozinha faz. É o único campo do pedido que qualquer operador
reescreve sem deixar quem e quando. Os vizinhos no mesmo arquivo — atribuir, devolver equipamento, comentar —
todos emitem evento. **Fix:** passar o ator da view e emitir o evento com antes/depois.

### P3-1 — O painel de corrida some sem aviso

O bloco de courier captura `Exception` amplo e devolve `None` com `logger.debug` (não warning). O detalhe
renderiza o painel com `v-if`. Qualquer erro dentro do bloco — inclusive cache indisponível — faz **sumir a
única tela de onde se cancela ou redespacha uma corrida paga**, sem uma linha dizendo por quê.

**Fix:** subir para `warning` e projetar o painel em estado degradado em vez de `None`. O componente já sabe
renderizar erro.

### P3-2 — Resíduo do rename `confirmed` → `accepted`

O mapa de tom no frontend tem `confirmed` (status que não existe no model desde o rename) e não tem
`accepted`. Um card aceito renderiza pill cinza em vez de azul, em três telas. E o mock do e2e ainda emite
`confirmed`, então o e2e **nunca exercita** `accepted`. Viola a convenção zero-residuals.

**Fix — uma linha em cada:** corrigir o mapa e o mock. A fonte canônica está nos tipos de projection do
`shop`; vale espelhá-la, não reinventá-la.

## Registrado, não é deste WP

O sino de alertas dá "ack" com a permissão de **ver**: o predicado é um OR de todas as personas
operacionais — Cozinha, Compras e KDS incluídos. Quem só deveria ver silencia um alerta de reconciliação
financeira. O componente é compartilhado com `production-nuxt`, então alguém precisa ser dono. Não é aqui.

**Procurado e não achado:** sem PII no SSE (só `ref`/`status`/`kind`); o BFF é proxy puro; equipamento é
normalizado e validado contra o canal. O CSV exportado leva `customer_name`, que pode ser um telefone
formatado quando o pedido não tem nome — é PII num arquivo baixado sem trilha, mas fora do peso dos itens
acima.

## RBAC / `setup_groups`

Depende da pergunta 1. Se a resposta for "cancelamento e fiscal sobem de exigência", a permissão pode ser
reusada (`shop.manage_catalog` já existe) ou nova. **Não** mexer em `settle_delivery_cash`.

⚠️ Se houver permissão nova: **PR único de permissões da onda 4** (WP-00 Bloco D3).

## Testes

1. `POST /orders/<ref>/cancel/` num pedido `ready` devolve **409** e o pedido continua `ready`. Hoje devolve
   200 (provado).
2. Cancelar de `new`, `accepted` e `preparing` continua funcionando (regressão).
3. `can_cancel` é `false` para `ready`/`dispatched`/`delivered` e `true` para os canceláveis; contrato TS
   regerado (o teste de drift já cobre).
4. Falha ao buscar motivos do iFood **bloqueia** o cancelamento de pedido do iFood; não cai em texto livre.
5. Pedido do iFood cancelado sempre carrega código de cancelamento não-vazio.
6. `change_out` malformado devolve **400** com `field`, nunca 500. Idem no acerto de entrega. Hoje é 500
   (provado).
7. Pedido de entrega num canal que oferece maquininha **não** entra no lote sem declarar o equipamento.
8. Reprocessar NFC-e exige a permissão adicional; avançar pedido não.
9. Nota de cozinha gera evento com ator e com antes/depois.
10. Falha no bloco de corrida projeta painel degradado, não `None`.
11. `confirmed` não aparece em nenhum arquivo do `orders-nuxt`; o mock do e2e emite `accepted`.

## Arquivos tocados (para a matriz de colisão)

| Arquivo | Risco | Quem mais mexe |
|---|---|---|
| `shopman/backstage/api/operations.py` (1026-1604) | **ALTO** | WP-02 e WP-05. **Onda 2, branch único.** |
| `shopman/shop/services/operator_orders.py` | MÉDIO | orquestrador |
| `shopman/backstage/services/orders.py` | BAIXO | — |
| `shopman/backstage/projections/order_queue.py` | BAIXO | — |
| `shopman/shop/management/commands/setup_groups.py` | **ALTO** | só se a pergunta 1 pedir permissão nova → **onda 4** |
| `surfaces/orders-nuxt/**` + `generated/ordersContract.ts` (regerado) | BAIXO | — |

## Fora de escopo

PDV, KDS, produção, catálogo (além da mensagem de 403). Motivo obrigatório no cancelamento de corrida.
Ownership do sino de alertas. Manifest de ações como infra — ver WP-00.

## Perguntas para o dono do produto

1. **Quem cancela um pedido já pronto?** Hoje o sistema **não deixa** ninguém (a transição não existe), mas a
   tela oferece o botão e mente. São dois desenhos diferentes: ou a transição passa a existir para quem tem
   uma permissão elevada — e aí cancelar um `ready` pago precisa decidir o que acontece com o estorno e com o
   iFood —, ou o botão simplesmente some depois de pronto. **Esta pergunta decide o WP inteiro.**
2. **Cancelamento, fiscal e courier devem exigir permissão além de `manage_orders`?** O Caixa hoje leva tudo
   junto. Reusar uma permissão existente ou criar uma nova?
3. **Vale configurar o código de cancelamento padrão do iFood?** Hoje o default é vazio, e isso transforma
   qualquer falha de motivo em pedido divergente entre a casa e o marketplace.

## Prompt para agente executor

~~~text
Execute WP-03-agente-c (Gestor de Pedidos).

⚠️ ONDA 2: toca shopman/backstage/api/operations.py, compartilhado com WP-02 e WP-05.
Branch UNICO com eles. Ver WP-00 Bloco D.

Bloqueio parcial: a pergunta 1 decide o desenho de P1-1 (botao some x permissao nova).
O P0-1 (409 em vez de 200 mentiroso) NAO depende dela — faca primeiro, em qualquer caso.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-03-agente-c-gestor-pedidos.md
- shopman/shop/services/operator_orders.py:150-156 (reject_order — o padrao CERTO), :510-534
- packages/orderman/**/order.py:63-66 (DEFAULT_TRANSITIONS)
- shopman/backstage/services/orders.py:53-55, 82-89, 135-152
- shopman/backstage/api/operations.py:1026-1250
- shopman/backstage/projections/order_queue.py:199-269, 498-504
- surfaces/orders-nuxt/app/pages/[ref].vue:217-222, index.vue:154-185
- surfaces/orders-nuxt/app/presentation/board.ts:16-26, 467-497
- docs/reports/2026-08-28-revisao-alpha-gestor-pedidos.md (o que ja foi corrigido)

Fases:
1. P0-1: escreva o teste 1 ANTES (ele deve passar hoje com 200 e falhar depois do fix).
   Tres edicoes: fachada devolve bool, servico levanta OrderConflict, view mapeia 409
   ANTES do except OrderError.
2. P1-3: converter POSError em OrderError nas duas funcoes, com field. Teste 6.
3. P1-1: can_cancel + rotulo, calculados por can_transition_to. Regerar ordersContract.ts
   com `python manage.py export_orders_schema`.
4. P1-2: catch devolve null; dialogo bloqueia iFood sem motivos; unificar as duas copias.
5. P2-1 (uma linha em board.ts), P2-4 (evento na nota), P3-1, P3-2.
6. P2-2 e P2-3 depois das respostas 1 e 2.

NAO exija motivo no cancelamento de corrida (quebra a unica tela que chama o endpoint).
NAO tire settle_delivery_cash do Caixa. NAO 409 por equipamento vazio.
~~~
