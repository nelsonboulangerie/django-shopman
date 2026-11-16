Lacunas confirmadas da revisão adversarial das Entregas. Conferi quatro no código e nos documentos, em HEAD 54e75d0df. Não alterei nada no repositório.

## L1. O vazamento do link da parada 1 também chega à página do pedido do cliente, e não só ao aviso de saída

O P1-1 cita só a notificação (`notification.py:919-925`). O link errado também vira botão permanente na loja.

- **Prova:**
  - `shopman/shop/projections/order_tracking.py:1348-1359`: no estado `dispatched`, a projeção cria a ação `track_courier` ("Acompanhar o entregador") com `href=_courier_tracking_url(order)`.
  - `order_tracking.py:1401-1416`: `_courier_tracking_url` lê `order.data.courier.tracking_url`, o mesmo campo que `courier.py:1131` preenche com `links[0]` em cada pedido da corrida.
  - `surfaces/storefront-nuxt/app/pages/pedido/[ref]/index.vue:768-779`: a página abre esse link em outra aba.
  - O teste existente (`shopman/storefront/tests/web/test_projections_order_tracking.py:565`) só confere que a ação existe. Não confere que o link é da parada certa.
- **Impacto:** o cliente B pode abrir a entrega do cliente A pela página dele enquanto a corrida durar. O botão só some em F/N/C (`_COURIER_ENDED_STATUSES`, `:1375`). A exposição deixa de ser uma mensagem e passa a durar a rota inteira.
- **Proposta:**
  - Incluir a projeção do acompanhamento no escopo do P1-1.
  - Ampliar o teste de 3 paradas embaralhadas: em cada pedido, o `track_courier.href` deve ser o link da própria parada ou não aparecer (falha fechada).
  - Incluir a página do pedido na prévia do P1-1.

## L2. O cliente fica sem informação entre a chamada da corrida e a coleta. O tempo real já chega à página, mas a projeção não usa o estado da corrida

- **Prova:**
  - `shopman/storefront/presentation/order_tracking.py:1334-1337`: no estado `ready_delivery` a página diz sempre "Pronto, esperando o entregador" e "Assim que ele chegar, seu pedido sai para entrega." Isso vale com ou sem corrida chamada, já aceita, ou com "ninguém aceitou", desistência ou cancelamento.
  - `shopman/shop/handlers/_sse_emitters.py:355-363`: `emit_courier_update` já publica `courier_changed` para a página do pedido (`_emit_for_order`). A projeção (`shop/projections/order_tracking.py:1313-1367`) só olha a corrida no estado `dispatched`.
  - `docs/runbooks/courier-machine-homologacao.md:89`, passo 4: o link de rastreio já existe no aceite (A). O cliente só o recebe depois do E.
  - O Concierge (`shopman/storefront/concierge/tools.py:1491,1537`) responde só com o link da loja. Ele também não sabe da corrida.
  - As seis prévias da seção 5 são todas do operador. Nenhuma mostra a tela do cliente.
- **Impacto:** é o trecho em que o cliente mais pergunta "cadê meu pedido". As correções do relatório (P0-1 desistência, P1-4 agrupado, "ninguém aceitou") mudam o que o operador vê e deixam o cliente com a mesma frase genérica.
- **Proposta:**
  - Subestados de `ready_delivery` derivados do mesmo `courier.ride_health` do P1-13, para não criar um campo paralelo. Copy na voz da concierge, sem travessão:
    - Chamada feita: "Chamamos o entregador. Avisamos quando ele aceitar."
    - Aceita: "Fulano está a caminho da loja para buscar seu pedido."
    - Demora ou desistência: "Estamos procurando um entregador. Seu pedido está pronto e guardado."
  - Prévia 7 para o dono decidir: mostrar o link da TaOn já a partir do aceite ou só depois da coleta.
  - Dependência: só depois do P1-1. Sem ele, mostrar o link mais cedo aumenta o tempo do vazamento.

## L3. Propostas que contradizem decisões do dono já registradas e não citam a decisão

Fonte: `docs/plans/DELIVERY-EXTERNAL-LOGISTICS-PLAN.md`, seção 4.

- **Decisão 3** (`:166-168`): "coleta→'saiu p/ entrega' e finalização→'entregue' automáticos, sem gate de confirmação". O P1-8 propõe que o F da corrida com retorno não confirme. O relatório põe isso em "pede a palavra do dono, item 3", mas não diz que inverte a decisão 3. Precisa ser apresentado como reversão, com o texto da decisão ao lado.
- **Decisão 4** (`:169`): "Falha de despacho: alerta + re-despacho manual (sem retry automático de corrida)". O P1-14 diz "Se falhar, o pedido volta a Aguardando ou sai sozinho". Se "sai sozinho" for uma corrida aberta automaticamente, contraria a decisão. Proposta: na falha do encaixe, o pedido volta a Aguardando com "Chamar sozinho" como botão primário e nunca abre corrida sem o toque do operador.
- **Decisão 7** (`:190-192`): a oferta "Vai junto nesta corrida?" lista entregas "prontas ou em preparo". O P1-9 trata como defeito o "fill" incluir pedido em preparo, e a regra 1 da seção 4 limita os candidatos a Pronto. Proposta: manter os pedidos em preparo na lista sem marcação, como foi decidido, e restringir só a pré-marcação.

## L4. O momento do F na corrida com retorno é contraditório entre os documentos, e o relatório "refuta" com base num lado só

- **Prova:**
  - `DELIVERY-EXTERNAL-LOGISTICS-PLAN.md:180-182` (decisão 6): "cada pedido só vira 'entregue' no `F` da corrida inteira (com retorno, depois da volta à loja)".
  - `docs/runbooks/courier-machine-homologacao.md:93`: "F (finalizou) na porta".
  - A seção 7 do relatório descarta "Estado 'back' diz 'está voltando' depois do F" porque "o runbook diz que o F é na porta". O plano diz o contrário, e nenhum dos dois foi homologado.
  - A lista de sondas da F6 não mede isso.
- **Impacto:** P1-7, P1-8, a prévia 6 (A contra B) e o estado "back" da página dependem de saber se o F chega na porta ou na loja. Decidir antes de medir pode inverter o defeito.
- **Proposta:**
  - Somar à F6 a sonda: corrida com retorno de 1 e de 2 paradas, com a hora do ER, a hora do F e a hora da volta física; o F chega na porta ou na loja?
  - Rebaixar o item refutado para "não decidido, depende da F6".
  - Na prévia 6, mostrar ao dono que hoje os dois documentos discordam.

Arquivos citados:
- /Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/gifted-hypatia-a1aaec/shopman/shop/projections/order_tracking.py
- /Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/gifted-hypatia-a1aaec/shopman/storefront/presentation/order_tracking.py
- /Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/gifted-hypatia-a1aaec/surfaces/storefront-nuxt/app/pages/pedido/[ref]/index.vue
- /Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/gifted-hypatia-a1aaec/shopman/shop/handlers/_sse_emitters.py
- /Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/gifted-hypatia-a1aaec/shopman/shop/services/courier.py
- /Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/gifted-hypatia-a1aaec/docs/plans/DELIVERY-EXTERNAL-LOGISTICS-PLAN.md
- /Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/gifted-hypatia-a1aaec/docs/runbooks/courier-machine-homologacao.md