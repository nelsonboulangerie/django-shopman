# D4 — Motivos de rejeição de pedido: o que já existe, o que o iFood faz, e a lista proposta

**HEAD analisado:** `origin/main` = `beb9bf9737da0bc343cc64f86e423a7d26a81f17`
(atual em 01/10/2026). Toda evidência é `git show origin/main:<caminho>` — o checkout
local está em outro branch e **não** foi usado como evidência.
**Método:** leitura de código, sem execução de teste e sem nada mutante. Nada foi implementado.
**Escopo:** lista de motivos para o Gestor (orders-nuxt) recusar/cancelar pedido.

---

## 1. A lista REAL do iFood que já existe no nosso código

Existem **duas** listas distintas — e elas não são a mesma coisa. Confundir as duas é o
principal risco desta tarefa.

### 1.1 Handshake (negociação de disputa) — lista FIXA no nosso código

`shopman/shop/services/ifood_handshake.py:23-26`:

```python
REJECT_REASONS = (
    "HIGH_STORE_DEMAND", "UNKNOWN_ISSUE", "CUSTOMER_SATISFACTION", "INVENTORY_CHECK",
    "SYSTEM_ISSUE", "WRONG_ORDER", "PRODUCT_QUALITY", "LATE_DELIVERY", "CUSTOMER_REQUEST",
)
```

Rótulos em português — **único mapa pt-BR existente**, em
`surfaces/orders-nuxt/app/components/OrderIFoodNegotiations.vue:22`:

| Código (iFood) | Rótulo em português | Em `REJECT_REASONS`? |
|---|---|---|
| `HIGH_STORE_DEMAND` | Alta demanda na loja | sim |
| `UNKNOWN_ISSUE` | Problema não identificado | sim |
| `CUSTOMER_SATISFACTION` | Satisfação do cliente | sim |
| `INVENTORY_CHECK` | Conferência de estoque | sim |
| `SYSTEM_ISSUE` | Problema no sistema | sim |
| `WRONG_ORDER` | Pedido incorreto | sim |
| `PRODUCT_QUALITY` | Qualidade do produto | sim |
| `LATE_DELIVERY` | Atraso na entrega | sim |
| `CUSTOMER_REQUEST` | Solicitação do cliente | sim |
| `ORDER_DELIVERED` | Pedido entregue | **não** — só existe no mapa de rótulos; chega pelo `acceptCancellationReasons` do provedor |

[FATO] Confirmado por grep dos códigos em `origin/main`: a string `ORDER_DELIVERED` aparece
**só** em `OrderIFoodNegotiations.vue:22`, nunca em `ifood_handshake.py`.

⚠️ **Estes 9 não são "motivos para recusar um pedido"** — são os motivos que a loja declara ao
**rejeitar a solicitação de cancelamento do cliente** (disputa pós-venda). A validação que os
usa está em `ifood_handshake.py:196-199`, e a UI em `OrderIFoodNegotiations.vue:110-115`.
Não copie a semântica deles para a recusa de pedido novo.

### 1.2 Cancelamento (código obrigatório por pedido) — lista do PROVEDOR, não nossa

Não existe lista estática de códigos de cancelamento no repositório. Ela é buscada **por pedido**:

- `shopman/shop/services/ifood_callbacks.py:226-254` — `fetch_cancellation_reasons(order_id)`:
  `GET /order/v1.0/orders/{id}/cancellationReasons` → lista de `{cancelCodeId, description}`.
- `shopman/shop/services/operator_orders.py:168-180` — `cancellation_reasons(order)` normaliza
  para `[{"code": ..., "description": ...}]`; **para canal não-iFood devolve `[]`** (`:169-170`).
- `shopman/shop/services/operator_orders.py:187-192` — um código fora da lista vigente levanta
  `ValueError` ("Escolha um motivo atualmente permitido pelo iFood para este pedido.").
- `shopman/shop/services/ifood_cancellation.py:45-47` — sem código:
  "Escolha um motivo permitido pelo iFood antes de solicitar o cancelamento."
- Ponte texto→código é **config-driven** e nasce VAZIA de propósito:
  `ifood_callbacks.py:74-96` (`DEFAULT_REASON_CODES: dict[str, str] = {}`) +
  `config/settings.py:802-807` (`cancellation_default_code`, `cancellation_default_reason` =
  `"Problemas de sistema na loja"`).
- Checklist de go-live: `docs/reference/ifood-outbound-verification.md:145-147` — o código válido
  se descobre em homologação com um pedido real.

### 1.3 Onde o `operator_orders.py` entra

`shopman/shop/services/operator_orders.py` é a **fachada** (confirm/reject/cancel + leitura dos
motivos), usada pelas views do backstage (`shopman/backstage/api/operations.py:2174`). Ela não
contém lista de motivos — só a validação (`:190`) e o encaminhamento.

---

## 2. O seletor do Gestor hoje (pedidos que NÃO são iFood)

`surfaces/orders-nuxt/app/components/OrderReasonDialog.vue` — dois formatos, decididos pelo canal:

| Canal | O que aparece | Evidência |
|---|---|---|
| iFood (`marketplace`) | `<select>` com os códigos **do provedor**, carregados por pedido; a `description` escolhida é espelhada no motivo enviado | `:98-107` (select), `:56-60` (`onCodeChange`), `:95` (lista vazia) |
| Demais canais | **chips de preset** ("um toque") + `textarea` de texto livre sempre visível | `:111-123` (chips), `:124-130` (textarea) |

**Os presets não estão no componente.** Vêm do banco, via prop:

```
Shop.cancellation_presets  →  order_queue._cancellation_presets()  →  projeção
→  orders-nuxt [ref].vue:161  →  prop presets  →  chips
```

- `shopman/shop/models/shop.py:338-354` — campo `JSONField` `cancellation_presets`, `default=list`.
- `shopman/backstage/projections/order_queue.py:988-1002` — lê o singleton, descarta vazios,
  **preserva a ordem**, nunca falha a projeção.
- `shopman/backstage/projections/order_queue.py:449` (tipo), `:549` (default `()`), `:858` (wire).
- `surfaces/orders-nuxt/app/generated/ordersContract.ts:556` — `cancellation_presets: string[]`.
- `surfaces/orders-nuxt/app/pages/[ref].vue:160-161` — `presets`.

**A lista que existe hoje, de fato, são 4 itens** — os semeados
(`config/management/commands/seed.py:1366-1370`):

1. `Item indisponível no momento`
2. `Sem um dos ingredientes hoje`
3. `Problema técnico no preparo`
4. `Fora do horário de atendimento`

O `help_text` do model cita outros 3, como exemplo, não como lista real
(`shopman/shop/models/shop.py:347-352`). O teste que fixa o contrato (ordem preservada,
brancos descartados) é `shopman/backstage/tests/test_order_queue_surface.py:397-412`.

**Regras de validação do diálogo** (`:48-54`): recusar **exige** motivo; **cancelar aceita
motivo vazio** (nesse caso o cliente recebe a frase-padrão).

### 2.1 ⚠️ O texto do preset é lido pelo CLIENTE, literalmente

`shopman/shop/services/notification.py:1051-1052`:

```python
if template in {"order_cancelled", "order_rejected"}:
    return f"Motivo: {reason}." if reason else "Os detalhes estão no pedido."
```

E esse `{status_note}` entra nos templates aprovados
(`shopman/shop/migrations/0078_frases_revisadas_das_notificacoes.py:69-70` cancelado,
`:76-77` não confirmado):

> "Oi{customer_name_greeting}. Seu pedido *{ref}* foi cancelado. **{status_note}** Qualquer dúvida..."

Três consequências **duras** para qualquer lista que o dono aprove:

1. O item da lista tem **dois leitores**: o operador (chip no Gestor) e o cliente (frase na
   notificação). Não existe, hoje, "motivo só interno" para recusa — para cancelamento existe
   `order.data["cancellation_note"]` (voltado ao cliente) vs `cancellation_reason`
   (código de máquina, "nunca exibir ao cliente"): `docs/reference/data-schemas.md:212-213`,
   `shopman/shop/services/operator_orders.py:948-963`.
2. O texto entra **depois de "Motivo: "** e o ponto final é do template → **o preset não pode
   terminar em ponto** (sairia `Motivo: Item acabou..`). Os 4 atuais não terminam — [FATO].
3. É ele que aparece no WhatsApp/e-mail: tem que ser **inequívoco sozinho**, sem o contexto da tela.

---

## 3. Como o iFood organiza × como nós organizamos

| Dimensão | iFood | Nós (hoje) |
|---|---|---|
| Unidade | **código** (`cancelCodeId` / SCREAMING_SNAKE) + descrição | **frase livre** (`string`), sem código |
| Origem da lista | por pedido, do provedor (cancelamento) ou tupla fixa no código (handshake) | lista fixa local no singleton `Shop` |
| Eixos de organização | **dois**: `SCENARIOS` cruza *momento* × *ação* — `(AFTER_DELIVERY, CANCELLATION)`, `(PREPARATION_TIME, CANCELLATION)`, `(DELAY, CANCELLATION)`, `(AFTER_DELIVERY_PARTIALLY, PARTIAL_CANCELLATION)` (`shopman/shop/services/ifood_handshake.py:27-30`); a *ação* tem rótulo próprio (`CANCELLATION`→"Cancelamento", `PARTIAL_CANCELLATION`→"Cancelamento parcial", `REFUND`→"Reembolso", `OrderIFoodNegotiations.vue:42-43`) e há `timeoutAction` (`:50`) | **um** eixo só: a ordem na lista (`order_queue.py:1002` preserva a ordem) |
| Agrupamento visível | categorias do provedor (não expostas na tela; a tela é um select plano) | **nenhum** — chips em `flex-wrap`, sem header (`OrderReasonDialog.vue:111-123`) |
| Texto livre | não existe: o iFood exige um código | existe sempre, ao lado dos chips (`:124-130`) |
| Obrigatoriedade | código obrigatório | obrigatório na recusa, opcional no cancelamento (`:48-54`) |
| Voz | rótulo de sistema ("Conferência de estoque") | escrita na voz da loja, porque **vai ao cliente** (`shop.py:343-352`, `admin/shop.py:1231-1235`) |

[INFERÊNCIA] O iFood organiza por **taxonomia fechada de causa × momento**; nós organizamos por
**prateleira de frases prontas**, ordenada por frequência de uso. São propósitos diferentes: a
taxonomia do iFood serve à disputa e ao repasse financeiro; a nossa serve a dizer ao cliente, em
português claro, por que o pedido não sai. **Copiar as categorias do iFood literalmente daria
frases ruins ao cliente** ("Conferência de estoque", "Satisfação do cliente") — é exatamente o D7
(jargão) do `docs/reference/omotenashi-copy.md:253`.

**Paralelo que não deve ser confundido:** já existe uma lista de motivos em pt-BR para
*desligar canal* — `shopman/shop/services/channel_switch.py:74-76`
(`_REASONS_REMOTE`, `_REASONS_IFOOD`, `_REASONS_DISPLAY`: "Loja cheia", "Desfalque na equipe",
"Falta de produto", "Sem entregador", "Feriado", "Férias"). É outro gesto, outro lugar; ela é
citada aqui só como referência de voz e como risco de duplicação de vocabulário.

---

## 4. Lista INICIAL proposta para os pedidos internos da loja

Régua aplicada: `docs/reference/omotenashi-copy.md` — **primeiro inequívoco, depois curto**
(§1, `:51`); sem coloquialidade, sem emoji, sem "calor" (`:63-71`); o verbo nomeia o ato real
(D2, `:150`); nada de termo de dentro na tela (D7, `:253`). Cada item foi escrito para
**funcionar nos dois lugares** — chip do Gestor e frase `Motivo: … .` na notificação — porque
hoje é um campo só (§2.1).

### 4.1 Falta de produto

| # | Rótulo (texto exato do preset) | Quando usar | O cliente lê |
|---|---|---|---|
| 1 | `Item indisponível no momento` ✱ | O item acabou no balcão e não há substituto aceitável. Use **antes** de aceitar; se o pedido já foi aceito, prefira trocar o item. | "Motivo: Item indisponível no momento." |
| 2 | `Sem um dos ingredientes hoje` ✱ | A receita não sai hoje por falta de um ingrediente (a panificação do dia não rendeu). Diferente do 1: o item existe no cardápio, o dia é que não deixa. | "Motivo: Sem um dos ingredientes hoje." |

✱ já existe hoje no `seed` — mantido, porque já está na voz da casa e já está no banco.

> Use **"ingrediente"**, nunca "insumo": insumo é palavra de dentro (`CLAUDE.md`, Offerman × Stockman).

### 4.2 Pagamento

| # | Rótulo | Quando usar | O cliente lê |
|---|---|---|---|
| 3 | `Pagamento não aprovado` | O cartão/Pix foi **recusado** pelo provedor e não há outra forma combinada. Não recuse por isso sem antes oferecer o link de novo. | "Motivo: Pagamento não aprovado." |
| 4 | `Pagamento não confirmado no prazo` | O Pix venceu ou o link expirou **sem recusa** — houve silêncio, não negativa (`pix_timeout`/`payment_timeout`). É um caso diferente do 3 e o cliente precisa saber disso. | "Motivo: Pagamento não confirmado no prazo." |

### 4.3 Endereço e contato

| # | Rótulo | Quando usar | O cliente lê |
|---|---|---|---|
| 5 | `Endereço fora da nossa área de entrega` | CEP/bairro sem faixa de entrega ou fora do raio. **Ofereça retirada antes de recusar** — recusar sem oferecer é perder a venda. | "Motivo: Endereço fora da nossa área de entrega." |
| 6 | `Não conseguimos falar com você` | Telefone/endereço não confere e não houve resposta depois das tentativas; a entrega não pode sair às cegas. | "Motivo: Não conseguimos falar com você." |

⚠️ O item 6 é o único que pode soar como cobrança ao cliente. Alternativa mais neutra, se o dono
preferir: `Endereço incompleto para a entrega`. **Escolha do dono** — as duas são inequívocas.

### 4.4 Capacidade (cozinha e entrega)

| # | Rótulo | Quando usar | O cliente lê |
|---|---|---|---|
| 7 | `Alta demanda neste horário` | A fila não fecha no tempo prometido e o pedido sairia muito depois do horário ou frio. Equivale ao `HIGH_STORE_DEMAND`/„Alta demanda na loja" do iFood, na nossa voz. | "Motivo: Alta demanda neste horário." |
| 8 | `Sem entregador disponível neste horário` | Entrega própria sem ninguém na janela pedida. Espelha o "Sem entregador" que já existe em `channel_switch.py:74`. | "Motivo: Sem entregador disponível neste horário." |

### 4.5 Horário da loja

| # | Rótulo | Quando usar | O cliente lê |
|---|---|---|---|
| 9 | `Fora do horário de atendimento` ✱ | O pedido entrou com a loja fechada e não dá para produzir/entregar hoje. | "Motivo: Fora do horário de atendimento." |

### 4.6 Cliente desistiu

| # | Rótulo | Quando usar | O cliente lê |
|---|---|---|---|
| 10 | `Você pediu o cancelamento` | O próprio cliente pediu para cancelar (WhatsApp, telefone, balcão). Equivale ao `CUSTOMER_REQUEST`/"Solicitação do cliente" do iFood, virado para quem lê. | "Motivo: Você pediu o cancelamento." |

### 4.7 Pedido repetido (duplicidade)

| # | Rótulo | Quando usar | O cliente lê |
|---|---|---|---|
| 11 | `Pedido em duplicidade` | O mesmo pedido entrou duas vezes (toque duplo, ou o canal repetiu) e **este** é o excedente, que não será produzido. Diga no texto livre qual é o pedido que fica. | "Motivo: Pedido em duplicidade." |

Alternativa mais coloquial, se o dono preferir: `Pedido repetido por engano` — [INFERÊNCIA]
"duplicidade" é mais preciso e mais curto; "por engano" atribui culpa a quem pediu.

### 4.8 Outros (texto livre)

| # | Rótulo | Quando usar |
|---|---|---|
| 12 | **Outros** | Nada acima descreve o caso. O operador escreve o motivo no campo de texto. |

⚠️ **Armadilha do "Outros" — decisão do dono.** Hoje o campo é **um só**: os chips e o
`textarea` escrevem no mesmo `reason` (`OrderReasonDialog.vue:111-130`). Se "Outros" for
colocado como **preset** na lista, tocá-lo grava literalmente a palavra "Outros" e o cliente lê
"Motivo: Outros." — pior que não ter motivo. Duas saídas:

- **(recomendada, zero código)** Não colocar "Outros" na lista: o `textarea` já está sempre
  visível ao lado dos chips, então "texto livre" já é possível sem nenhum chip.
- **(exige código)** Chip "Outros" que apenas foca/limpa o texto e é bloqueado de enviar vazio —
  é mudança no `OrderReasonDialog.vue` + validação, não é configuração.

### 4.9 Lista pronta para colar (ordem = ordem na tela)

A ordem da lista **é** a ordem dos chips (`order_queue.py:1002` preserva; teste em
`test_order_queue_surface.py:412`), então ela deve ser ordenada por frequência:

```json
[
  "Item indisponível no momento",
  "Sem um dos ingredientes hoje",
  "Pagamento não aprovado",
  "Pagamento não confirmado no prazo",
  "Endereço fora da nossa área de entrega",
  "Não conseguimos falar com você",
  "Alta demanda neste horário",
  "Sem entregador disponível neste horário",
  "Fora do horário de atendimento",
  "Você pediu o cancelamento",
  "Pedido em duplicidade"
]
```

**11 itens** (dentro da faixa pedida de 8–12). Sai um item, entra outro: a lista atual tem 4 e
"Problema técnico no preparo" **não** foi mantido — [INFERÊNCIA] ele é o único dos quatro que
não passa na régua: não diz o que aconteceu nem se o pedido ainda vem (D2, `:150`), e o cliente
não sabe o que fazer com ele. Se o dono quiser preservá-lo, ele precisa dizer **qual falha**
cobre (equipamento? sistema?) — e aí vira um item específico, no lugar de um guarda-chuva.

---

## 5. Onde isso cabe — sem migração

### 5.1 O lugar já existe

`Shop.cancellation_presets` — `shopman/shop/models/shop.py:339-354`, `JSONField(default=list)`,
`blank=True`. **Aprovar esta lista não exige migração nenhuma.** É substituir 11 strings.

**RuleConfig NÃO é o lugar.** `shopman/shop/models/rules.py:24-46` guarda *classes de regra*
(`rule_path` + `params` + canais + prioridade) avaliadas pelo engine
(`shopman/shop/rules/`). Uma lista de motivos não tem regra a avaliar; usá-lo exigiria inventar
uma rule só para guardar strings.

### 5.2 Como o dono configura (Admin/Unfold)

1. Admin → **Loja** (`/admin/settings/shop/`) → grupo **"Motivos de cancelamento e recusa"**
   (`shopman/shop/admin/shop.py:2316-2325`), campo `cancellation_presets`
   (`:1193`, widget `ArrayWidget` add/remove; help em `:1229-1235`).
2. Adicionar/remover/reordenar um motivo por linha. Salvar.
3. **Efeito é imediato, sem deploy**: `Shop.save()` limpa o cache do singleton
   (`shopman/shop/models/shop.py:482-484`), e a projeção lê `Shop.load()` a cada requisição
   (`order_queue.py:995-1002`). Basta abrir o pedido no Gestor.

Para um banco novo, o mesmo conteúdo entra no `seed`
(`config/management/commands/seed.py:1366-1370`) — os dois lugares precisam ficar de acordo,
senão um deploy novo nasce com a lista velha. [INFERÊNCIA] é o único ponto de manutenção duplo.

### 5.3 Alcance (o que esta lista cobre e não cobre)

- ✅ Serve **todos os canais que não são iFood** (site, WhatsApp, balcão, encomenda): pedido de
  recusa e de cancelamento, os dois modos do diálogo.
- ❌ **Não** aparece em pedido iFood: o diálogo usa o select do provedor
  (`OrderReasonDialog.vue:98-107`) e `cancellation_reasons()` devolve `[]` fora do iFood
  (`operator_orders.py:169-170`). A lista do iFood é dele; a nossa é da casa.
- ❌ **Não** é por canal: é o singleton `Shop`, uma lista só para a loja toda. Se o dono quiser
  lista diferente por canal (ex.: esconder "fora do horário" no balcão), isso é código novo —
  poderia morar em `Channel.config` (JSONField já existente, usado em
  `channel_switch.py:228`) **sem migração**, mas exige leitura nova na projeção.

### 5.4 Se o dono quiser AGRUPAMENTO visível (cabeçalho de grupo no diálogo)

Isso **exige código**, em três pontos, sem migração:

1. `shopman/backstage/projections/order_queue.py:988-1002` — hoje devolve `tuple[str, ...]` e
   faz `str(p).strip()` em cada item; uma estrutura com grupos seria stringificada como
   `"{'grupo': ...}"` (`:1002`). Precisa devolver grupos.
2. `surfaces/orders-nuxt/app/generated/ordersContract.ts:556` — **gerado**;
   `python manage.py export_orders_schema` (`shopman/backstage/management/commands/export_orders_schema.py`).
3. `surfaces/orders-nuxt/app/components/OrderReasonDialog.vue:111-123` — os chips planos em
   `flex-wrap`.

Sem isso, a única forma de "agrupar" é a **ordem** da lista (§4.9). [INFERÊNCIA] para 11 itens,
ordenar bem resolve; agrupamento visual só se paga com a lista maior que isso.

### 5.5 Lacuna de teste (achado lateral, não bloqueia)

`shopman/shop/tests/test_admin.py:58` trata como `ArrayWidget` de lista só
`{"social_links", "kitchen_note_tags"}` — `cancellation_presets` **não** está nesse conjunto, e
não há teste de Admin fazendo round-trip do campo (o teste existente é o da projeção, com valor
mockado: `test_order_queue_surface.py:397-412`). [FATO] por grep de `cancellation_presets` em
todo o `origin/main`. **Não verifiquei** se isso é bug ou só cobertura faltando — a verificação
barata é salvar a lista no Admin e reabrir o Gestor.

---

## 6. O que NÃO foi verificado / limites

- **Nada foi executado**: sem teste, sem servidor, sem Admin. Tudo é leitura de `origin/main`.
- **A lista real de códigos de cancelamento do iFood não existe no repositório** — só existe em
  homologação/produção (`fetch_cancellation_reasons`, `ifood_callbacks.py:226-254`). O que este
  relatório chama de "lista do iFood" é (a) os 9 códigos fixos de handshake + (b) os 10 rótulos
  pt-BR do mapa do componente. Nada além disso foi inventado.
- [NÃO VERIFICADO] comportamento visual do Gestor móvel com 11 chips (`flex-wrap`, sem
  `max-height`: `OrderReasonDialog.vue:111`). Vale um olhar antes de aprovar a lista inteira.
- [NÃO VERIFICADO] se algum outro consumidor (relatório, B.I.) lê `cancellation_presets` e
  depende do texto exato. `docs/plans/BI-INSIGHTS-MAP.md:321` cita o campo, mas não li o
  consumo.
