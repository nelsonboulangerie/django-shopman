# WP-03-agente-c — Gestor de Pedidos

**Status:** P0-1 e P1-1 **IMPLEMENTADOS** (29/08) · resto pronto para implementação · **Autor:** Agente C

> ✅ **Implementado nesta branch:** o falso-sucesso do cancelamento (P0-1) e as três camadas do
> cancelamento pelo operador (P1-1), com 10 testes novos. Detalhe no fim do arquivo.
> ⬜ **Pendente:** P1-2 (iFood), P1-3 (typo → 500), P2-1 a P2-4, P3-1, P3-2.
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
- ~~Resposta à pergunta 1~~ — **respondida (29/08): cancelar pedido pronto é de gerente ou dono.** O desenho
  está no P1-1 abaixo, com uma armadilha que a resposta expõe (o snapshot selado) e uma sub-decisão que
  sobrou.

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

### P1-1 — A régua do canal não deixa cancelar pedido pronto, e isso é lacuna

**Decisão do dono (29/08):** cancelar pedido pronto é de **gerente ou dono**. O Caixa não.

> ⚠️ **Correção de uma análise anterior minha.** Numa primeira leitura eu propus uma "transição de exceção"
> validada em código, contornando a máquina de estados, com o argumento de que mudar a config do canal não
> alcançaria pedidos já criados. **Estava errado em três níveis**, e o registro fica porque a proposta chegou
> a ser escrita:
>
> 1. **Cancelar nunca feriu a imutabilidade do pedido.** `SEALED_FIELDS` é
>    `["ref", "channel_ref", "session_key", "snapshot", "total_q", "currency"]`. **`status` não está lá** — é
>    mutável por desenho, porque é o ciclo de vida. O que é selado é a *régua* (snapshot), o *preço* e a
>    *identidade*. Eu confundi "a régua é imutável" com "cancelar fere a imutabilidade".
> 2. **O problema que a exceção resolvia não existe.** Pedido antigo não pegar a régua nova é irrelevante em
>    alpha (reseed resolve) e, em produção, seria o comportamento **correto**: cada pedido carrega a regra sob
>    a qual nasceu. É o ponto inteiro do snapshot, não um defeito dele.
> 3. **A exceção criaria duas fontes para a mesma pergunta** — parte da régua no snapshot, parte numa lista em
>    código. É exatamente o modo de falha que o `setup_groups.py` documenta em voz alta ("duas fontes para a
>    mesma pergunta, e a pior das duas ganhava").

**O achado que fecha o caso: a régua do canal do PDV é internamente incoerente.**

| de | pode cancelar? |
|---|---|
| `new` | ✅ |
| `accepted` | ✅ |
| `preparing` | ✅ |
| **`ready`** | ❌ |
| `completed` | ✅ |

Dá para cancelar **antes** (na cozinha) e **depois** (entregue e fechado), mas **não no meio** — justamente no
estado em que o pão está pronto no balcão e ninguém pegou, que é quando o cliente liga para desistir. Não há
ADR, comentário ou documento justificando. **É lacuna, não decisão.**

Isso reenquadra o trabalho: não é "abrir uma exceção na máquina de estados". É **consertar uma régua que não
fecha**.

**O desenho — e a casa já usa as três camadas; só não usa a do meio para o operador.**

| Camada | Pergunta | Onde vive hoje |
|---|---|---|
| **Régua** | esta transição é estruturalmente possível **para este pedido**? | `snapshot.lifecycle.transitions`, assado no nascimento — imutável e auditável |
| **Política** | é **permitido agora**, cruzando os ciclos de pedido, pagamento e fulfillment? | ✅ existe para o **cliente** (`payment_service.can_cancel`) · ❌ **não existe para o operador** |
| **Autorização** | **este ator** pode? | RBAC, mais segunda assinatura (PIN) nas exceções auditadas |

**Os três ciclos são mesmo separados** — confirmado no código. `payment_service.can_cancel` cruza duas
dimensões independentes:

```python
if order.status not in _CANCELLABLE_STATUSES:      # {"new", "accepted"} — ciclo do PEDIDO
    return False
status = (get_payment_status(order) or "").lower()  # ciclo do PAGAMENTO, via intent do payman
if status in _UNCERTAIN_STATUSES or has_sufficient_captured_payment(order):
    return False
```

E o fulfillment é o terceiro (`dispatched`, `delivered`, courier, equipamento). O docstring é explícito sobre
por que o gate de pagamento existe: *"Estados incertos bloqueiam cancelamento para não cancelar um pedido que
pode já estar pago."*

**O cliente para em `accepted`** — nem chega em `preparing`, e nem depende da régua do canal. A régua do canal
governa o **operador**.

**A lacuna real, então, não é a régua — é a política do operador.** `cancellation.cancel` é o ponto de entrada
único dos três caminhos (cliente, operador, timeout) e **só consulta a máquina de estados**. O gate de
pagamento mora uma camada acima, e **só no caminho do cliente**. Consequência: hoje o operador cancela um
pedido **pago** e nada no caminho pergunta pelo dinheiro.

**E a casa já resolveu esse caso uma vez, no PDV.** O `completed → cancelled` da régua não é descuido — o
comentário em `cancellation.cancel` explica que o canal do PDV o declara de propósito ("a venda de balcão
fecha no commit, e o desfazer da janela precisa passar"), e o endpoint correspondente
(`POSCancelRecentSaleView`) exige **PIN de gerente**, com o comentário: *"Cancelar venda fechada é exceção
auditada: sempre sob PIN de gerente."* A terceira camada existe e funciona — só não foi estendida ao Gestor
de Pedidos.

**Fix, agora em três peças pequenas e cada uma na sua camada:**

1. **Régua** — `"cancelled"` entra em `ready` no `lifecycle.transitions` do canal, no seed. Uma linha. A régua
   passa a fechar (hoje ela cancela antes e depois, mas não no meio). Zero core, zero migration.
   ⚠️ **Colide com o [#391](https://github.com/nelsonboulangerie/django-shopman/pull/391)**, que também toca
   `seed.py` — ver README §5.
2. **Política** — uma `can_operator_cancel(order)` análoga à do cliente, cruzando pedido × pagamento ×
   fulfillment, no `shop`. É o que falta, e é o coração deste achado: cancelar pedido **pago** deve exigir
   decisão explícita sobre o dinheiro, não passar batido.
3. **Autorização** — permissão para os estados avançados; e, para pedido pago, a **segunda assinatura** que o
   PDV já usa. Reusar `validate_manager_override`, que já aceita crachá ou usuário+PIN e já recusa
   autoassinatura.

E `can_cancel` na projection passa a ser régua **E** política **E** permissão — uma pergunta só para a tela,
respondida pelo servidor.

**Decidido pelo dono (29/08):** `dispatched` e `delivered` **não** ganham `cancelled` — depois que o motoboy
saiu, o certo é `RETURNED`, que já existe e já está na régua. Cancelar e devolver são fatos diferentes, e
misturá-los estragaria o B.I. depois.

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

**Uma permissão nova, confirmada pela decisão do dono:** cancelar pedido em estado avançado é de gerente e
dono. Concedê-la ao **Gerente** basta — quem é dono entra em "Gerente" **e** em "Dono" (o `setup_groups`
documenta isso: "Dono" é portão de dinheiro, não persona completa), e superusuário tem tudo por definição.
O **Caixa não recebe**, que é exatamente o recorte pedido.

Migration nova em `shop` (permissão custom no `Meta` de `Shop`) → começa em **`shop 0024`** (ver README §5).
E entrada nova no teste de paridade, senão o CI reprova por permissão que ninguém tem.

⚠️ A **régua** (a transição no canal) não é permissão e **não** vai neste PR: é uma linha no seed, e vai junto
com o código do P1-1. Só a permissão vai para o PR único da onda 4.

**Não** mexer em `settle_delivery_cash` — acertar o dinheiro da entrega é o trabalho do Caixa.

⚠️ **PR único de permissões da onda 4** (WP-00 Bloco D3).

## Testes

1. **Caixa** cancelando pedido `ready` recebe **403**, e o pedido continua `ready`. Hoje recebe 200 com
   `{"ok": true}` e nada acontece (provado).
2. **Gerente** cancelando pedido `ready` recebe **200 e o pedido fica `cancelled`** — num pedido criado
   **depois** da régua nova, que é o contrato do snapshot: cada pedido carrega a regra sob a qual nasceu.
3. Qualquer perfil cancelando um status fora da exceção (`completed`, `cancelled`) recebe **409**, nunca 200
   mentiroso.
6. Cancelar de `new`, `accepted` e `preparing` continua funcionando para o Caixa (regressão — não subir a
   régua do cancelamento normal sem querer).
7. `can_cancel` é `true` para o Gerente num pedido `ready` e `false` para o Caixa no mesmo pedido — **o mesmo
   pedido, dois perfis, dois valores**. É a prova de que o servidor decide a capacidade e a UI não recalcula.
   Contrato TS regerado (o teste de drift já cobre).
6. Falha ao buscar motivos do iFood **bloqueia** o cancelamento de pedido do iFood; não cai em texto livre.
7. Pedido do iFood cancelado sempre carrega código de cancelamento não-vazio.
8. `change_out` malformado devolve **400** com `field`, nunca 500. Idem no acerto de entrega. Hoje é 500
   (provado).
9. Pedido de entrega num canal que oferece maquininha **não** entra no lote sem declarar o equipamento.
10. Reprocessar NFC-e exige a permissão adicional; avançar pedido não.
11. Nota de cozinha gera evento com ator e com antes/depois.
12. Falha no bloco de corrida projeta painel degradado, não `None`.
13. `confirmed` não aparece em nenhum arquivo do `orders-nuxt`; o mock do e2e emite `accepted`.

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

1. ~~Quem cancela um pedido já pronto?~~ **RESPONDIDO (29/08): gerente ou dono.** Sobraram duas
   sub-decisões, ambas pequenas e nenhuma bloqueia começar:
   **(a)** a régua ganha `cancelled` também em `dispatched` e `delivered`, ou só em `ready`? Proponho só
   `ready` — depois que o motoboy saiu, o certo é `RETURNED`, que já existe e já está na régua.
   **(b)** cancelar um pedido **pronto e pago**: o estorno é automático ou o gerente decide caso a caso? Hoje
   o cancelamento comum já dispara o fluxo de estorno; para a exceção, automático pode surpreender. Precisa da
   sua palavra antes de o executor escrever o aceite.
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
6. P1-2: catch devolve null; dialogo bloqueia iFood sem motivos; unificar as duas copias.
7. P2-1 (uma linha em board.ts), P2-4 (evento na nota), P3-1, P3-2.
8. P2-2 e P2-3 depois das respostas 1 e 2.

NAO exija motivo no cancelamento de corrida (quebra a unica tela que chama o endpoint).
NAO tire settle_delivery_cash do Caixa. NAO 409 por equipamento vazio.
~~~

---

## Registro de implementação — 29/08/2026

**Feito, com teste:**

| Camada | Arquivo | O quê |
|---|---|---|
| Régua | `config/management/commands/seed.py` | `cancelled` entra em `ready` no `lifecycle.transitions` do canal. A régua passa a fechar. |
| Política | `shopman/shop/services/cancellation.py` | `operator_cancel_policy()` + `OperatorCancelPolicy` + `ADVANCED_CANCEL_STATUSES` + `ADVANCED_CANCEL_PERMISSION`. É a camada que não existia. |
| Autorização | `shopman/backstage/api/operations.py` | `OrderCancelView` cruza as três; 409 para régua, 403 para permissão, 422 para assinatura pendente. |
| Falso-sucesso | `operator_orders.py`, `backstage/services/orders.py` | a fachada devolve o booleano e a fronteira levanta `OrderConflict`. |
| Permissão | `shop/models/shop.py` + migration `0024` + `setup_groups.py` + teste de paridade | `shop.cancel_advanced_order`, concedida ao **Gerente**. |
| Contrato | `projections/order_queue.py` + `ordersContract.ts` (regerado) | `can_cancel`, `cancel_requires_approval`, `cancel_block_label`. |
| Tela | `surfaces/orders-nuxt/app/pages/[ref].vue` | o botão passa a obedecer `can_cancel`; quando não dá, a tela **diz por quê**. |

**Testes:** `shopman/backstage/tests/test_api_orders_cancel_policy.py`, 10 casos — 409 em vez do 200
mentiroso, Caixa barrado em `ready`, Gerente cancelando, a esteira normal como regressão, pedido pago
exigindo segunda assinatura, leitura de pagamento falhando **fechado**, e a capability diferindo por perfil
no mesmo pedido.

**Duas decisões tomadas durante a implementação:**

1. **422, não 403, para assinatura pendente.** O `PosIntentError` já tem `status = 422` e o PDV já responde
   assim no seu próprio desafio de gerente. Inventar 403 aqui daria dois dialetos para o mesmo diálogo de
   aprovação. Seguir a casa.
2. **A constante da permissão mora na política**, não na view nem na projection. As duas precisam concordar
   sobre quem pode, e duas cópias da mesma string concordam só até alguém editar uma delas — que é o modo de
   falha que este próprio WP critica em outros lugares.

**Não validado localmente:** o typecheck e o vitest de `orders-nuxt` — a worktree não tem `node_modules`.
O gate de superfícies do CI cobre, e o risco real (o `.vue` lendo campo que não existe no contrato) está
fechado pelo contrato regerado.
