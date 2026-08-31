# PDV — "Quando" e "Dividir"

Duas features de balcão, e uma terceira que só apareceu quando fomos olhar: a
promessa de horário do pedido não tinha quem a guardasse.

## O pedido

1. **Pedido com data futura no PDV, para entrega E para retirada.** A casa recebe
   muito pedido remoto (WhatsApp, telefone) e o operador registra em nome do
   cliente. Hoje ou daqui a três dias, para retirar ou para entregar. É caso
   comum, não exceção — tem que ser cidadão de primeira classe.
2. **Dividir a conta no pagamento.** Em 2, 3, 4 pessoas, sem o operador fazer
   conta de cabeça com o cliente na frente.
3. **(descoberto)** Garantir que nenhum horário incompatível com os produtos do
   pedido possa ser escolhido — nem pelo operador, nem pelo cliente na loja.
   *"Se tem baguete de tradição no pedido, mas ela só sai depois do meio-dia, não
   tem como poder escolher o slot das 9h."*

## O que já existe (e por que não basta)

| peça | onde | alcance |
| --- | --- | --- |
| `pickup_slots` "A partir das 09h/12h/15h" | `storefront/services/pickup_slots.py` | **só a loja, só retirada** |
| prontidão por SKU (mediana das WorkOrders) | mesmo arquivo, `get_typical_ready_times` | histórico apenas |
| janelas de meia hora do expediente | `shop/services/business_calendar.delivery_slots_for` | **só entrega, sem prontidão** |
| encomenda com data futura | `shop/handlers/preorder.py` + `lifecycle` | pronto, dirigido por `delivery_date` |
| pagamento dividido por valor | `payment_tenders` (`mixed`) | pronto, mas exige conta de cabeça |
| dividir comanda por itens | `move_lines` modo `split` | outro gesto, outro propósito |

### Os três buracos

- **`shopman/shop/services/pos.py:3012`** — no commit, se `fulfillment_type != "delivery"`
  o pedido **perde** `delivery_date` e `delivery_time_slot`. Retirada agendada é
  literalmente impossível hoje no PDV. É o eixo errado: *quando* é fato do
  PEDIDO, não da entrega.
- **`shopman/shop/services/pos.py:_delivery_review_context`** — devolve `(None, ())`
  para retirada. A tela não tem o que oferecer porque o servidor não responde.
- **`storefront/intents/checkout.py:_validate_slot`** — `if fulfillment_type != "pickup": return {}`.
  **Entrega não passa por prontidão nenhuma**, nem na loja. E no PDV não passa
  nos dois modos. A baguete das 12h pode ser prometida para as 9h por três
  caminhos diferentes.

### E a prontidão sai só do histórico

`get_typical_ready_times` lê a mediana das WorkOrders terminadas nos últimos 30
dias. Produto sem fornada no período → **nenhuma restrição**. Para uma promessa
ao cliente isso é falhar ABERTO: o dado que falta libera o horário em vez de
fechá-lo. A casa sabe que a baguete de tradição sai depois do meio-dia; ela
precisa de porta para DIZER isso.

---

## WP-1 — `ready_from`: a hora de sair da fornada vira declaração

`Product.metadata["ready_from"]` = `"HH:MM"`, declarado pela casa.

Segue o precedente do irmão `made_to_order` (commit `cd85ba6ec`) e de
`allows_next_day_sale`: metadata do Product, zero migração no Core.

- Switch/campo no Admin/Unfold (aba Configuração, ao lado dos dois irmãos).
- Round-trip no catálogo do Gestor (`backstage/services/catalog.py`).
- `seed`: a baguete de tradição e os pães de fornada tardia nascem declarados.
- Registro em `docs/reference/data-schemas.md`.

**Resolução:** declarado **manda**; histórico **preenche a lacuna**; quando os
dois existem, vence o mais tarde — a declaração é piso, não teto (uma fornada que
atrasou sistematicamente não pode ser desmentida por um número no cadastro).

## WP-2 — a prontidão vira serviço do orquestrador

`shopman/shop/services/product_readiness.py` — "a que horas cada SKU fica pronto",
declarado + histórico. Puro, sem opinião sobre slot.

Sobe para `shop/` porque **backstage não pode importar storefront** (regra de
dependência). `storefront/services/pickup_slots.py` continua dono do vocabulário
grosso da loja ("A partir das") e passa a delegar a prontidão.

## WP-3 — nenhuma janela incompatível é oferecida, em nenhuma superfície

`shopman/shop/services/fulfillment_window.py` — anota as janelas de meia hora do
`business_calendar` com `enabled` / `reason`, dado o carrinho e a data.

- PDV: `review_sale` anota; `close_sale` **recusa**.
- A razão é dita em português de balcão: *"Baguette de Tradition sai às 12:00.
  Escolha 12:00 às 12:30 ou mais tarde."*

**Calibração descoberta na execução — dois eixos, e só um fecha a porta.**
A primeira versão recusava também a janela fora da grade do dia, e isso quebrou
um teste do backstage de um jeito revelador: uma loja com `opening_hours` em
branco tem grade vazia, e passaria a **recusar toda venda com horário**. Pior, a
dona no balcão às 18h05 não conseguiria agendar a retirada de amanhã.

- **Prontidão fecha.** É a única promessa que a casa não pode cumprir.
- **Expediente não fecha.** A grade diz o que se OFERECE (`annotate`), não o que
  se aceita. Agenda do balcão é da casa.

> **Loja, entrega:** o storefront não oferece janela de horário para entrega (só
> data), então não há promessa de hora a guardar ali. Ficou intocado de propósito
> — mexer no `_validate_slot` da loja na véspera do go-live seria risco sem ganho
> visível. Anotado como pergunta.

## WP-4 — "Quando" é fato do pedido

**Servidor**
- `_delivery_review_context` → `_schedule_review_context`: responde para retirada
  também.
- O commit para de descartar `delivery_date`/`delivery_time_slot` na retirada.
- Datas ofertadas saem de `business_calendar.available_dates` (pula fechado e
  feriado) com o teto de `max_preorder_days`.

**Tela**
- Terceiro botão na barra de contexto, irmão de Cliente e Recebimento:
  **"Para hoje"** por padrão; clicou, abre data + janela.
- O bloco de data sai de dentro do formulário de entrega.
- Janela incompatível aparece desabilitada, com o motivo.

> Chaves persistidas seguem `delivery_date` / `delivery_time_slot`. Renomear
> agora atinge loja, gestor, fechamento, B.I. e acompanhamento na véspera do
> go-live. Fica anotado como pergunta para o Pablo.

## WP-5 — dividir a conta

O trilho de tenders já existe e não regride. O que falta é o gesto que evita a
conta de cabeça: **"Dividir"** → em quantas pessoas → N linhas iguais, com o
resto dos centavos na primeira. Cada linha recebe sua forma de pagamento.

Odoo faz isso com pagamentos parciais sucessivos; a diferença é só quem faz a
divisão. Aqui faz o sistema.

---

## Ordem

1 → 2 → 3 → 4 → 5. Um commit por WP, na mesma branch: os WPs 3, 4 e 5 tocam os
mesmos arquivos (`projections/pos.py`, `usePosSale.ts`, `PosPaymentWorkspace.vue`)
e PRs paralelos virariam criss-cross na fila de merge.
