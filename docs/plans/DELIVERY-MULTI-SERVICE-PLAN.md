# DELIVERY-MULTI-SERVICE-PLAN: escolher o serviço da corrida e entregadores próprios

> **Compromisso:** DEV-2026-030 (fala do dono, 16/11/2026). **Estado:** desenho DECIDIDO
> pelo dono em 16/11/2026 (respostas no §9); execução pela esteira, frente a frente (§7).
> **Base medida:** `origin/main` em `ed7cf13c1` (16/11/2026, depois do #2492).
> **Apoia-se em:** revisão das Entregas, DEV-2026-026, referência no PR draft #2484
> (frentes F1a a F10). Este plano não reabre nenhuma delas: diz onde se encaixa.

A fala do dono, literal:

> "O sistema de entrega precisa estar pronto para aceitar escolher facilmente para QUAL
> serviço envia aquela entrega/rota. Poderemos configurar outras APIs de serviços de
> terceiros, bem como (caso de uso real desde já) direcionar entregas para entregadores
> próprios. Para isso, eventualmente teremos que expor algo que o entregador possa se
> basear, desde valores negociados, como rotas, observações, etc."

Meta da revisão, que vale aqui igual: **chamar uma corrida, juntar corridas e escolher quem
leva custam o mesmo gesto.** O caminho comum não ganha toque nenhum.

---

## 1. Estado medido

**Resumo:** a costura existe, mas é só um seletor de módulo. Não há contrato tipado, há uma
implementação real (a TaOn), e o serviço, os handlers, as projeções e a tela falam o
vocabulário da TaOn direto: letra de status, `id_mch`, chaves do corpo da Machine e o nome
"TaOn" na copy.

### 1.1 O adapter é trocável? Por deployment, sim; por corrida, não

| Fato | Prova |
|---|---|
| `get_adapter("courier")` resolve `Shop.integrations["courier"]` → settings → padrão | `shopman/shop/adapters/__init__.py:139`, `:150-171` |
| A chave é UM caminho de módulo, não um dicionário por método: uma loja tem um serviço só | `adapters/__init__.py:34` (`"courier": "SHOPMAN_COURIER_ADAPTER"`), `config/settings.py:1136` |
| "SE despacha" mora no canal; "QUEM" mora no adapter | `shopman/shop/config.py:199-203` (`fulfillment.courier = "none" \| "auto"`) |
| **Não há Protocol de entrega.** O contrato é duck typing das funções do módulo | `shopman/shop/protocols.py` (94 linhas, nenhuma classe de entrega) |
| Implementações: `courier_machine.py` (526 linhas, a única borda HTTP) e `courier_mock.py` (175 linhas, só teste, importa as constantes e os DTOs da Machine) | `courier_mock.py:15-21`; única referência fora de teste: `privacy_inventory.py:138` |
| O check de credencial só reconhece a Machine pelo nome do caminho | `shopman/shop/checks.py:331-348` |
| O bloco grava `provider="machine"`, e ninguém lê | `shopman/shop/handlers/courier_dispatch.py:204`; `surfaces/orders-nuxt/app/types/orders.ts:42-48` declara e a tela não usa |

**Leitura pelo ADR-001:** hoje há UMA implementação real (o mock é teste). Com o entregador
próprio passam a ser **duas reais**, e o Protocol deixa de ser "para o futuro": é o momento
que o ADR-001 pede.

### 1.2 O que está preso à TaOn

| Camada | Preso à TaOn | Prova |
|---|---|---|
| Serviço (`services/courier.py`, 1.620 linhas) | Importa `CANCELLABLE_STATUSES`, `TERMINAL_STATUSES`, `CourierError` da Machine | `courier.py:29-33` |
| | Corpo da Machine montado no serviço (`forma_pagamento`, `partida`, `paradas[*_parada, id_externo]`, `retorno`) | `courier.py:248`, `:293` (`build_machine_payload`), lê `SHOPMAN_MACHINE` em `:312` |
| | Letras A/E/F/N/C decidem o destino do pedido | `courier.py:999` (`apply_status`), `:1015-1047`; `_STATUS_RANK` `:1337` |
| | `id_mch` é a identidade da corrida (companheiros, arquivo, despacho pendente) | `courier.py:84`, `:493`, `:503`, `:969` |
| | Motivo de cancelamento é o `motivo_id` da Machine | `courier.py:853` (`cancel_ride`, `reason_id`) |
| | Link de rastreio casado pelas chaves da Machine (`id_externo`, `numero_pedido`, `parada_id`, `link_rastreio`) | `courier.py:1141` (`link_for_order`) |
| | Copy com "TaOn" | `courier.py:658`, `:1298`, `:1304`, `:1484-1485` |
| | Docstring da regra antiga ("a casa não tem entregador próprio") | `courier.py:136-140` |
| Handlers | `courier.dispatch` chama `build_machine_payload` e grava `provider="machine", id_mch, status="D"` | `handlers/courier_dispatch.py:75`, `:105`, `:118`, `:204` |
| | `courier.cancel` e `courier.sync` usam as constantes da Machine | `handlers/courier_cancel.py:12`, `:40`, `:51`; `handlers/courier_sync.py:35`, `:70-71` |
| Webhook (`webhooks/machine.py`) | Inteiro da TaOn (token, `Signature-V2`, letras, AP/ER/L/R, busca por `data__courier__id_mch`). Genérico só o funil (`apply_status`, `record_arrival`) | `machine.py:14-16`, `:69`, `:134`, `:144`, `:173`, `:199-224` |
| Projeção Entregas | Letras D/G/P/U/A/S/F, importa `CANCELLABLE_STATUSES` da Machine | `backstage/projections/deliveries.py:193`, `:196`, `:213`, `:223` |
| Projeção da fila | Rótulo por letra, nome da central lido de `SHOPMAN_MACHINE["company_name"]`, "Sem resposta da TaOn", `provider or "machine"` | `backstage/projections/order_queue.py:1425`, `:1449`, `:1477`, `:1533-1535`, `:3481`, `:3564` |
| Outras réguas de letra | Encomendas, página do cliente, B.I. | `preorders.py:613`; `shop/projections/order_tracking.py:1375`; `bi_delivery_cost.py:105`, `:134` (dedupe por `id_mch`); `bi_delivery_timing.py:198-199` |
| API | `courier-cancel` recebe `reason_id` da Machine; cotação com "TaOn" na recusa | `backstage/api/operations.py:4453`, `:4667` |
| Tela (orders-nuxt) | A letra crua dirige passos e tom; "TaOn" escrito em 13 arquivos (33 vezes) | `presentation/courier.ts:1-62`; `OrderCourierPanel.vue:423`, `:450`; `CourierRideDetail.vue:70`, `:144`; `CourierRideMenu.vue:128`; `pages/deliveries.vue:177`, `:207`, `:257`, `:343`; `presentation/board.ts:1549`; `composables/useOrderDetail.ts:356` |
| Aviso ao cliente | Variante do ManyChat com rastreio exige `SHOPMAN_MACHINE["tracking_link_base"]` | `adapters/notification_manychat.py:464-530` |
| Configuração | `SHOPMAN_MACHINE` (11 chaves `MACHINE_*` por env), congelado na baseline do ADR-042 | `config/settings.py:1111-1135`; `scripts/tenant-config-baseline.json` |

Contagem: "TaOn" aparece 86 vezes em 19 arquivos Python fora de teste (cerca de 20 são copy
de tela) e 33 vezes em 13 arquivos do Gestor. Testes que dependem disso: 13 arquivos de
backend com nome de corrida (216 testes) e 54 testes no front.

### 1.3 O que já é genérico e se reaproveita inteiro

- **A custódia.** Troco no livro do caixa (`courier_out`/`courier_in`), maquininha em
  `DeliveryDevice.current_order` e `Order.data["dispatch"]`
  (`operator_orders.py:644`, `:1003`, `:1130`, `:1165`, `:1246`;
  `backstage/models/delivery_device.py:7-21`). Não depende de quem leva.
- **O despacho sem API já existe.** "Despachar" e "Entregador voltou" do Gestor
  (`operator_orders.advance_order` `:412`, `courier_returned` `:976`) são hoje o caminho de
  quem não chama a TaOn. Falta só dizer QUEM levou, o valor e o que ele recebe.
- **A rota, o grupo e a letra.** `_route` (`courier.py:271`), `next_ride_number`
  (`:617`), `MAX_RIDE_STOPS = 4` (`:639`, regra da casa, não da API), `request_group_dispatch`
  (`:663`).
- **A cobrança na porta e a observação.** `door_charge` e `door_charge_note`
  (`courier.py:132`, `:155`) são régua de dinheiro, não de API.
- **A via do entregador impressa.** `receipt_escpos.courier_ticket` (`:866`), com as vias
  Identificada e Anônima decididas por `delivery_ownership` (`order_helpers.py:59-107`). O
  entregador próprio é "house": a via dele é a Identificada, sem mudar regra. Falta o botão
  (#2406).
- **O tempo real.** SSE `courier_changed` já chega à página do pedido
  (`handlers/_sse_emitters.py:355-363`).
- **O custo no B.I.** `bi_delivery_cost.py` já soma o custo de corrida contra o frete
  (`:95`, `:157`); só deduplica por `id_mch`.

---

## 2. Desenho: um contrato, três implementações

### 2.1 Serviço de entrega é cadastro, não env

Modelo novo no orquestrador (`shopman/shop/models/delivery.py`, ao lado de `DeliveryZone`;
o Core não muda):

**`DeliveryService`** (Admin: Pedido e entrega › Serviços de entrega)

| Campo | O que é |
|---|---|
| `ref` | identificador estável (`taon`, `casa`) |
| `name` | o nome que o OPERADOR vê ("TaOn", "Entregadores da casa"). Nunca vai ao cliente |
| `kind` | qual implementação: `machine`, `own_fleet` (lista fechada no código; não é caminho livre) |
| `active` | liga e desliga sem apagar |
| `position` | ordem de exibição no sheet |
| `config` | JSON da implementação (base da API, forma de pagamento, motivo padrão…), validado pela implementação |
| `secret` | credencial cifrada por `shop/secret_box.py` (o mesmo de `ai_connection.py`), nunca em env |

| `is_default` | o serviço que vem marcado no sheet (decisão do dono, 16/11: configurável no Admin, hoje a TaOn). Um só por loja (restrição no banco) |

O serviço padrão é o registro marcado no Admin, e é ele também que o despacho automático
(`fulfillment.courier = "auto"`) usa. Os entregadores da casa livres aparecem como opção no
mesmo sheet, sem vir marcados.

**ADR-042:** a TaOn de hoje continua lendo `SHOPMAN_MACHINE` (baseline congelada, só pode
diminuir). Ao criar o registro `taon`, a frente M1 move as leituras para o `config` e o
`secret` do registro, e a baseline **diminui**. Serviço novo nasce só no banco. Nenhuma
chave `SHOPMAN_*` nova.

### 2.2 O contrato (`DeliveryServiceBackend`, em `shop/protocols.py`)

Cada implementação declara o que sabe fazer, e a tela só mostra o que o serviço escolhido sabe:

```python
@dataclass(frozen=True)
class DeliveryCapabilities:
    quote: bool             # cota antes de chamar (TaOn: API; casa: tabela de valores)
    multi_stop: int         # quantas paradas numa corrida (0 = uma só); teto da casa vale por cima
    cancel_reasons: bool    # cancelar pede motivo da tabela do serviço
    customer_tracking: bool # entrega um link de rastreio por parada para o cliente
    push_status: bool       # avisa sozinho (webhook); sem isso o estado vem de quem leva ou do operador
    door_charge: bool       # leva cobrança na porta, troco e maquininha
    needs_return: bool      # a cobrança na porta exige corrida com volta (TaOn: `retorno`)
    boost: bool             # aceita "Aumentar a oferta" (TaOn v2, depois da F6)
    attach: bool            # encaixa pedido em corrida viva (TaOn v2, depois da F6)
    assign: bool            # o operador escolhe a pessoa (casa: sim; TaOn: a central distribui)
```

| Operação | TaOn (`machine`) | Entregador da casa (`own_fleet`) | Outra API |
|---|---|---|---|
| `capabilities()` | quote, multi_stop 4, cancel_reasons, customer_tracking, push_status, door_charge, needs_return | quote (tabela), multi_stop 4, door_charge, assign | o que ela declarar |
| `quote(ride)` | `GET /estimarSolicitacao` | tabela de valores (instantâneo, sem rede) | a API dela |
| `open(ride)` → `ride_ref` | `POST /abrirSolicitacao` (o corpo da Machine sai do serviço e vem para cá) | grava a corrida, gera o link do entregador | a API dela |
| `read(ride_ref)` → `RideReading` | `read_ride` de hoje, traduzido | lê o próprio banco (eventos do link e do operador) | a API dela |
| `cancel(ride_ref, reason)` | `POST /cancelar` com o motivo por fase (F1a) | revoga o link e avisa o entregador | a API dela |
| `stop_links(ride_ref)` | `obterLinkRastreio` casado por parada (F2a) | nenhum (`customer_tracking = False`) | a API dela |
| `parse_event(request)` | o webhook de hoje (`/api/webhooks/machine/`) | os toques no link do entregador (endpoint interno) | o webhook dela |

**Vocabulário neutro de estado.** O funil (`apply_status`) passa a falar estados da casa, e
a letra da TaOn vira tradução dentro do adapter:

| Estado neutro | TaOn | Casa |
|---|---|---|
| `searching` | D, G, P | (não existe: a casa escolhe a pessoa) |
| `grouped` | U | (não existe) |
| `reassigning` | T, C com `will_reopen` (F1b) | o operador trocou o entregador |
| `assigned` | A | o operador mandou para a pessoa |
| `at_store` | S, AP antes do E | (opcional) "Cheguei à loja" |
| `on_route` | E | "Saí da loja" (ou o Despachar do Gestor) |
| `stop_done` | ER com `stop_id` (F2b) | "Entreguei" na parada |
| `stop_failed` | (F2b, ENT-05) | "Não consegui entregar" na parada |
| `done` | F | última parada entregue (sem volta) ou "Voltei à loja" conferido |
| `not_served` | N | (não existe) |
| `cancelled` | C | o operador cancelou |

O bloco `Order.data["courier"]` ganha `service` (o `ref` do `DeliveryService`), `ride_ref`
(neutro) e `state` (neutro), e guarda a letra crua em `provider_status` para auditoria. O
`id_mch` some por rename completo (pré go-live não há tag `go-live-v1`, então vale "zero
resíduo"; os pedidos já gravados migram por migração de dados, sem alias).

### 2.3 O que a tela mostra, por capacidade

- Sem `quote`: a linha de cotação some; nunca "R$ 0,00".
- Sem `customer_tracking`: o cliente não tem botão de acompanhar; vê o nome e a hora (§4.5).
- Sem `push_status`: a Saída mostra os gestos de quem avança ("Saiu", "Entregue") e o
  aviso de dado parado não existe (não há o que esperar de terceiro).
- Sem `cancel_reasons`: cancelar é um toque e uma confirmação, sem os três motivos da F1a.
- Sem `boost`/`attach`: o chip não aparece (igual ao que a F9 já prevê até a homologação).
- O nome do serviço vem do cadastro: a copy do operador diz "TaOn" porque o registro se
  chama TaOn, e diria outro nome sem mudar código. Ao cliente, nunca.

---

## 3. O gesto do operador: escolher quem leva no mesmo toque de chamar

O ponto de encaixe é o `CourierCallSheet` e o `courier.ride_plan` que a F5 constrói
(prévia 1 da revisão, decisão A). Proposta, vista na prévia M1 deste plano:

1. **Uma linha "Quem leva" no topo do sheet**, com os serviços ativos em chips. Um já vem
   marcado (a sugestão). Trocar é UM toque no chip. O caminho comum continua com dois toques
   (abrir o sheet, chamar), sozinho ou junto.
2. **Cada chip diz o que importa para decidir:** o valor da corrida inteira (a TaOn pela
   cotação, a casa pela tabela) e o estado ("Diego · livre", "Rui · volta 12h50", "TaOn · cota
   R$ 11,00 · 18 min"). Sem cotação, o chip diz "Sem cotação agora" e nunca vem marcado por
   preço.
3. **Regra de sugestão (DECIDIDA, dono 16/11):** vem marcado o serviço padrão do Admin
   (hoje a TaOn). Os entregadores da casa livres e na escala aparecem como opção, a um toque.
   Sem regra de "mais barato" e sem "casa primeiro".
4. **A cotação "juntas contra separadas" é do serviço marcado**, nas duas linhas já
   decididas (✔ na mais barata, a linha dela em destaque). Trocar o chip recalcula.
5. **Na casa, a pessoa é parte do chip:** "Diego", "Rui"; não há um segundo passo "escolher
   entregador". Com mais de 3 pessoas livres, o último chip vira "Outro da casa" (lista).
6. **O botão diz o que acontece:** "Chamar TaOn para A47 e C03" ou "Enviar para Diego: A47 e
   C03". "Chamar só A47" segue ao lado, como na prévia 1.
7. **O que o serviço não sabe fazer some do sheet:** a TaOn não mostra pessoa; a casa não
   mostra "procura entregador".

**Proposta para a coordenação da revisão (formato do `ride_plan`, F5):** cada corrida do
plano carrega, desde o primeiro PR da F5, as chaves

```jsonc
"service": "taon",                    // a sugestão para esta corrida
"service_reason": "own_busy",         // por que esta (own_free, own_busy, cheapest, house_default)
"service_options": [                  // os serviços ativos, na ordem do cadastro
  {"service": "casa", "courier": "diego", "label": "Diego", "state": "free", "back_at": null,
   "quote": {"value_q": 1200, "minutes": null, "km": 7.4}, "refusal": null},
  {"service": "taon", "courier": null, "label": "TaOn", "state": "available",
   "quote": {"value_q": 1100, "minutes": 18, "km": 7.4}, "refusal": null}
]
```

Com UM serviço só (hoje), a F5 entrega a lista com a TaOn e o sheet esconde a linha "Quem
leva". Assim a F5 não espera este plano, e este plano não reescreve a F5.

---

## 4. Entregador próprio, de ponta a ponta

### 4.1 Quem são (cadastro)

**`Courier`** (Admin: Pedido e entrega › Entregadores; também editável no Gestor, Entregas ›
Entregadores): `ref`, `name`, `phone` (WhatsApp), `vehicle` ("Moto prata · ABC1D23"),
`active`, `service` (o `DeliveryService` `own_fleet` ao qual pertence). Sem CPF, sem chave
Pix no sistema (o pagamento é fora dele, §4.8).

**Quem está hoje:** uma linha "Entregadores de hoje" no topo da seção Entregas, com um chip
por pessoa ativa (toque liga e desliga a escala do dia). Só quem está na escala aparece no
sheet. Sem escala marcada, a casa não sugere ninguém da casa.

### 4.2 Como recebem a corrida

O que o entregador precisa para se basear, numa tela de celular (prévia M3):

- a **letra e a cor** da corrida (a mesma da Saída e da sacola);
- as **paradas na ordem real** da rota (`_route`, a mesma enviada à TaOn), cada uma com
  endereço, complemento, referência, instruções do cliente e o **primeiro nome**;
- **"Abrir no mapa"** por parada e a rota inteira (link do Google Maps/Waze, sem integração);
- **o que cobrar** em cada parada: valor, forma e troco ("Cobrar R$ 58,00 em dinheiro ·
  troco para R$ 100,00"), a mesma régua do `door_charge_note`;
- **o que leva da loja:** sacolas por pedido, troco total da gaveta, maquininha (nome e cor);
- **o valor da corrida** que ele recebe ("Você recebe R$ 14,00 por esta corrida");
- **observações** da casa para esta corrida (campo livre no sheet, opcional).

Por qual meio, recomendado: **link** (página pública com token) enviado pelo **WhatsApp do
dispositivo do operador** num toque (abre o WhatsApp com o texto pronto; zero integração nova),
mais a **via impressa** com o mesmo conteúdo e um QR do link (#2406, já desenhada:
`courier_ticket` Identificada). O envio automático pelo WhatsApp da loja (modelo novo na Meta)
fica para depois (#2508).

### 4.3 Como o estado avança sem API

Recomendado: **o entregador toca no link**, e o operador pode fazer o mesmo no Gestor
(quem chegar primeiro vale; o mesmo funil `apply_status`, fonte `courier_link` ou
`operator:<nome>`):

| Toque do entregador | Efeito |
|---|---|
| "Saí da loja" | `on_route`: pedido(s) DISPATCHED, aviso "saiu" ao cliente (igual ao E) |
| "Entreguei" (por parada) | `stop_done`: só aquele pedido DELIVERED, aviso ao cliente |
| "Não consegui entregar" (por parada) | `stop_failed`: alerta no Gestor, o pedido volta com a sacola (fluxo da F2b) |
| "Voltei à loja" | fecha a ida; o acerto de dinheiro e maquininha continua no Gestor (§4.7) |

Sem o link (sem celular, sem bateria), o Gestor tem os mesmos gestos no cartão da Saída. O
"Despachar" de hoje passa a ser o "Saiu" da corrida da casa.

### 4.4 Dado pessoal exposto ao entregador: o mínimo, com prazo

- Primeiro nome, endereço e instruções. **Sem CPF, sem e-mail, sem itens com preço** (só as
  sacolas). Telefone só como botão "Ligar para o cliente" enquanto a parada está aberta.
- O link é um token aleatório de 32 bytes por corrida, **vale até a corrida fechar, mais 2 h**,
  e morre no cancelamento ou na troca de entregador. Depois disso: "Esta corrida terminou."
- `noindex`, `no-store`, sem cookie, sem analytics. Cada abertura do link grava `opened_at`.
- Registro no inventário de privacidade (`privacy_inventory.py`).

### 4.5 O que o cliente vê

Sem link de terceiro, a página do pedido mostra o fato útil de cada estado, na voz já
decidida na prévia 7 da revisão (sem "corrida", sem "TaOn", sem emoji): "Diego está a caminho.
Deve chegar por volta de 12h45." A hora vem da cotação/rota (km e tempo da tabela) e da hora
da saída. Sem botão "Acompanhar o entregador" (`customer_tracking = False`). Posição ao vivo
pelo celular do entregador fica para depois (#2509), se o dono quiser.

### 4.5.1 Localização do entregador da casa (pergunta 6, alternativa 2)

Na prática, a única fonte é o celular do entregador. Três caminhos, do mais leve ao mais pesado:

1. **Pela página do link (recomendado, frente da #2509).** Depois de "Saí da loja", a página
   pede a permissão de localização do navegador e manda a posição a cada 15 s enquanto
   estiver aberta. A posição entra no mesmo cache e no mesmo mapa das Entregas que já
   desenham o entregador da TaOn, e, para o cliente, só na parada dele, com a idade visível
   ("Posição de há 20 s"). **Limite honesto:** navegador não manda posição com a tela
   apagada nem com outro app na frente (Waze, Maps); no iPhone isso é regra do sistema. Com
   o celular no suporte e a nossa página na tela, funciona; navegando pelo Waze, a posição
   congela e a tela diz "Última posição há 4 min".
2. **Localização em tempo real do próprio WhatsApp**, compartilhada com o número da loja.
   Zero desenvolvimento, mas só a casa vê (no WhatsApp, fora do Gestor) e o cliente não.
3. **App nativo** com localização em segundo plano. Resolve o limite do caminho 1, mas é
   um app para publicar e manter. Só se o caminho 1 provar que os buracos atrapalham.

**E instalada como PWA?** Ajuda, mas não resolve o segundo plano. Instalado na tela de
início, o link vira um ícone que abre direto, mantém a tela acesa durante a corrida (Screen
Wake Lock) e recebe aviso de corrida nova (push; no iPhone, só com o app instalado). Mas nem
no iPhone nem no Android um PWA recebe posição em segundo plano: com o Waze na frente, a
posição congela do mesmo jeito. O que contorna isso sem app nativo é a nossa página ser o
mapa da corrida: a rota desenhada, a próxima parada em destaque e "Abrir no Waze" só como
opção. Quem navega pela nossa página manda posição o tempo todo.

**Quando entra (decidido por mim, a pedido do dono, 16/11):** logo depois da M2, como frente
própria (M2b, #2509), na mesma página: PWA instalável, tela acesa, mapa da corrida e posição
para a casa (mapa das Entregas) e para o cliente (só a parada dele, com a idade visível).

Até lá, a casa acompanha a corrida pelos toques do entregador ("Saí", "Entreguei A47"), com
a hora prevista refeita a cada parada, e o cliente vê nome e hora (decisão 6 = 1).

### 4.6 Cancelar

Antes da saída: um toque e uma confirmação no Gestor; o link do entregador passa a dizer
"Corrida cancelada pela loja. Não precisa vir." e o troco e a maquininha voltam pelo mesmo
`return_partner_custody` de hoje. Depois da saída: não se cancela a corrida, trata-se a
parada (volta com a sacola, F2b).

### 4.7 Fechar a volta (dinheiro e maquininha)

Igual à TaOn com retorno: "Entregador voltou" abre o `CourierBackDialog` (generalizado na
F4a), confere troco e maquininha, fecha a saída. Nada novo no livro do caixa.

### 4.8 Custo e acerto

- O valor da corrida da casa é gravado na chamada (`estimate.value_q`, da tabela) e vira
  `final_value_q` no fecho (com o que o operador ajustar, ex.: parada extra).
- O B.I. (`bi_delivery_cost.py`) passa a deduplicar por `ride_ref` e a separar por serviço:
  "TaOn R$ 210,00 · Entregadores da casa R$ 96,00", contra o frete pago pelos clientes. Os
  tempos (#2467) entram com a mesma chave.
- **Acerto do dia** (recomendado): o Gestor soma "A pagar a Diego hoje: R$ 56,00 (4
  corridas)"; o pagamento em si é por fora (Pix do dono). Pagar pela gaveta seria lançamento
  novo no livro do caixa: alternativa na pergunta 5.

---

## 5. Valores negociados

**`CourierRate`** (Admin: Pedido e entrega › Valores dos entregadores), recomendado:

- **Tabela da casa por distância da rota**, igual para todos: "até 3 km R$ 8,00 · até 6 km
  R$ 12,00 · até 10 km R$ 16,00", **mais R$ 3,00 por parada extra** e **mais R$ 2,00 com
  volta** (cobrança na porta ou maquininha). Os números são exemplo; o dono preenche.
- **Exceção por entregador** quando combinado ("Diego: R$ 10,00 fixo por corrida").
- Distância da rota é a mesma que a TaOn cotaria (loja → paradas → volta), calculada por
  `_route` com as coordenadas que o pedido já tem.

Onde aparece:
- **Ao operador, antes do toque:** no chip ("Diego · R$ 12,00") e na cotação juntas contra
  separadas do serviço marcado.
- **Ao entregador:** no link e na via impressa ("Você recebe R$ 14,00 por esta corrida").
- **No fecho e no B.I.:** como custo da corrida.

---

## 6. Reversões e conflitos com decisões escritas

| Onde está escrito | Texto antigo | Passa a valer (dono, 16/11/2026) |
|---|---|---|
| `docs/reference/cenarios-de-pedido.md:23` | "Não existe entregador da casa: toda entrega dos canais próprios sai pela **TaOn**, inclusive a cobrada na porta" | Entregador próprio é caso de uso real desde já; cada corrida vai para o serviço escolhido (TaOn, entregador da casa, outra API) |
| `shopman/shop/services/courier.py:138` (docstring) | "A casa não tem entregador próprio (decisão do dono, 13/10/2026): toda cobrança na porta sai com a corrida" | A cobrança na porta sai com quem levar, pela mesma régua |
| `shopman/shop/services/operator_orders.py:430-431` (docstring) | "A casa não tem entregador próprio (decisão do dono, 13/10/2026)" | Idem |
| `DELIVERY-EXTERNAL-LOGISTICS-PLAN.md:16`, `:155-157` | Teleporte é "fallback manual (API fora / entrega própria)"; "permanece como fallback de contingência (API fora do ar, corrida não atendida com entrega própria)" | A entrega própria deixa de ser contingência: é serviço de primeira classe, com link, rota e valor. O teleporte segue só como cópia de dados para serviço sem integração |
| `DELIVERY-EXTERNAL-LOGISTICS-PLAN.md:40-42` | "`get_adapter("courier")` ← `Shop.integrations["courier"]` > `SHOPMAN_COURIER_ADAPTER`… Config diz SE; adapter diz QUEM" | "QUEM" deixa de ser um por loja: é escolhido por corrida entre os `DeliveryService` ativos; o canal diz SE e qual é o padrão |
| `DELIVERY-EXTERNAL-LOGISTICS-PLAN.md:55-56` (go-live, passo 2) | "Ligar: `SHOPMAN_COURIER_ADAPTER=…courier_machine`" | Ligar = registro `taon` ativo no Admin; o env sai na M1 |
| `docs/reference/data-schemas.md:394-399` | "Corrida de entrega via logística externa (Machine/Gaudium)… Status usa a letra crua da Machine" | Estado neutro (`state`) mais a letra crua em `provider_status` |
| `docs/plans/suite-ux-v2/funcoes/gestor.md:39`, `:299` | P21 "Gatilho: sem entregador próprio" | Gatilho: entrega da casa, qualquer serviço |
| Memória da coordenação, 13/10/2026 | "nunca presuma entregador próprio em copy, via impressa ou fluxo" | Já marcada como revertida |

**Decisões do plano antigo que continuam valendo, e onde este desenho as respeita:**

- Decisão 2 (preço ao cliente = faixas/zonas; custo é interno): o valor do entregador da casa
  também é custo interno. O frete do cliente não muda com o serviço.
- Decisão 3 (coleta → "saiu", fim → "entregue", automáticos): na casa, o "Saí" e o
  "Entreguei" do link são os fatos equivalentes; sem gate de confirmação do cliente.
- Decisão 4 (falha de despacho = alerta + re-despacho manual): a troca de serviço depois de
  uma falha é **um toque do operador** ("Chamar com Diego"), nunca automática.
- Decisões 5 a 7 (retorno por pedido, corrida de várias paradas, custódia da corrida
  conjunta): valem para qualquer serviço com `door_charge`; `needs_return` vira capacidade
  (a casa não precisa pedir "volta" a ninguém, mas o valor com volta entra na tabela).

**Alinhamento, sem conflito:** a via do entregador (`courier_ticket_variant`,
`order_helpers.py:117`) já trata o entregador da casa como "house" e imprime a Identificada.

---

## 7. Plano em frentes (uma frente = um branch = um PR)

| Frente | Entrega no ar | Depende de | Pode começar |
|---|---|---|---|
| **M0. Cadastro** | Modelos `DeliveryService` (com `is_default`), `Courier`, `CourierRate` + Admin + a régua pura do valor da corrida da casa (`delivery_rates.ride_value`) + migração de dados com os registros "TaOn" (padrão) e "Entregadores da casa". Nada muda para o operador; o dono já pode cadastrar entregadores e a tabela | nada (não toca os arquivos em voo) | **já** |
| **M1. Núcleo neutro e contrato** (#2524) | `DeliveryServiceBackend`/`DeliveryCapabilities` em `protocols.py` (nascem com a TaOn conformada; o entregador da casa é a segunda implementação, na M2, como pede o ADR-001); estado neutro, `ride_ref`, `service` no bloco; a letra da TaOn e o corpo da Machine descem para `courier_machine.py`; `get_adapter` por serviço; nome do serviço vindo do cadastro; `SHOPMAN_MACHINE` vira `config`/`secret` do registro (baseline do ADR-042 diminui); migração de dados dos pedidos com `id_mch`. Tela idêntica | F1a, F1b, F2a, F3, F4a, F4b mergeados (todos mexem em `courier.py`, handlers e projeções) | depois da F4b |
| **M2. Entregador da casa** (#2525) | `courier_own_fleet.py`; página do entregador por link (token, prazo); toques "Saí", "Entreguei", "Não consegui", "Voltei"; enviar pelo WhatsApp do dispositivo; via impressa com QR (fecha #2406) | M0, M1 | depois da M1 |
| **M2b. Localização do entregador da casa** | A página do link como PWA instalável (tela acesa, aviso de corrida nova), mapa da corrida e posição ao vivo para a casa e para o cliente da parada, com idade visível (§4.5.1) | M2 | logo depois da M2 (#2509) |
| **M3. Quem leva no sheet** (#2526) | Linha "Quem leva" no `CourierCallSheet`, regra de sugestão, cotação por serviço, "Entregadores de hoje"; cartão da Saída da corrida da casa (forma E, com letra e o nome da pessoa) | F5, M2 | depois da F5 e da M2 |
| **M4. Cliente e B.I.** (#2527) | Página do pedido da corrida da casa (nome + hora, sem link); custo por serviço e acerto do dia; tempos com `ride_ref` (#2467) | M1, M2; prévia 7 da revisão implementada | depois da M2 |
| **M5. Segunda API de terceiro** | Implementação nova do contrato | o dono nomear o serviço | #2507 |

Notas de coordenação:
- Nenhuma frente M edita `courier.py`, handlers, webhook, `deliveries.py`, `operations.py`
  (endpoint `courier-ride`), `deliveries.vue` ou `Courier*.vue` antes dos PRs da revisão
  entrarem. A M0 cria arquivos novos e mexe só em `models/`, Admin, migração e docs.
- A M1 é o único refactor grande; pede uma janela em que as frentes F da revisão não estejam
  com PR aberto nos mesmos arquivos. Proposta: entra logo depois da F4b, antes da F5, e a F5
  já nasce sobre o núcleo neutro. Se a F5 vier antes, a M1 adapta a F5.
- Pedido à coordenação: reservar `service`, `service_reason` e `service_options` no
  `ride_plan` desde o primeiro PR da F5 (§3).

---

## 8. Prévias locais (não vão ao ar)

No Gestor (`surfaces/orders-nuxt`), páginas `/preview-multisservico/1` a `3`, dados fictícios,
num branch próprio (`claude/entregas-multisservico-previas`, PR draft que NÃO se mergeia, no
molde do #2484). Lá o `app.vue` ganha um desvio só de desenvolvimento (`import.meta.dev`) para
as prévias abrirem sem backend; esse desvio nunca chega ao `main`.

1. **Chamar entregador, com "Quem leva".** Lado a lado: (A) chips de serviço no topo do sheet,
   um marcado, troca em um toque [recomendada]; (B) o sheet de hoje e a escolha do serviço
   como segundo passo depois de "Chamar". Estados: ninguém da casa livre, TaOn sem cotação.
2. **A corrida da casa na Saída**, forma E com letra, ao lado de uma corrida da TaOn, nas duas
   partes "A coletar" e "Saiu para entrega", com os gestos que a casa precisa.
3. **O que o entregador recebe** (celular, 375 px): (A) a página do link [recomendada]; (B) só
   a via impressa. E o que o cliente vê na corrida da casa.

Comando para abrir: ver o corpo do PR.

---

## 9. Decisões do dono (16/11/2026)

| # | Pergunta | Resposta |
|---|---|---|
| 1 | Quem vem marcado | **Padrão configurável no Admin: TaOn. Opcional: entregador da casa livre.** (nem "casa primeiro" nem "mais barato") |
| 2 | Como o entregador recebe | **1**: link no WhatsApp num toque + via impressa com QR |
| 3 | Quem avança o estado | **1**: o entregador pelo link, com o operador podendo marcar |
| 4 | Valor negociado | **1**: tabela da casa por distância + parada extra + volta, com exceção por entregador |
| 5 | Pagamento do entregador | **1**: o sistema soma "a pagar hoje"; pagamento por fora |
| 6 | O que o cliente vê | **1** agora (nome e hora); a **2** (posição ao vivo) interessa: abordagem no §4.5.1, frente na #2509 |

Ele também perguntou se haverá UI para o entregador: sim, é a página do link (prévia M3),
aberta no navegador do celular, sem instalar nada.

### Perguntas como foram feitas

1. **Quem vem marcado:** (1) entregador da casa livre primeiro, TaOn quando ninguém da casa
   está livre [recomendo]; (2) sempre o mais barato entre os que cotaram.
2. **Como o entregador recebe:** (1) link no WhatsApp, enviado num toque do dispositivo do
   operador, mais a via impressa com QR [recomendo]; (2) só a via impressa.
3. **Quem avança o estado:** (1) o entregador pelo link ("Saí", "Entreguei"), com o operador
   podendo marcar no Gestor [recomendo]; (2) só o operador no Gestor.
4. **Valor negociado:** (1) tabela da casa por distância + parada extra + volta, com exceção
   por entregador [recomendo]; (2) valor fixo por corrida, por entregador.
5. **Pagamento do entregador:** (1) o sistema soma "a pagar hoje" e o pagamento é por fora
   [recomendo]; (2) paga pela gaveta, lançado no livro do caixa.
6. **O cliente da corrida da casa vê:** (1) nome e hora estimada, sem mapa [recomendo]; (2)
   posição ao vivo pelo celular do entregador (frente própria, pede permissão de localização).
