# ADR-040 — Baixa de insumo na venda do item feito na hora

**Data:** 2026-10-19 (proposta) · 2026-10-20 (aceita pelo dono)

**Status:** Aceito
**Escopo:** Orquestrador (`shopman/shop`), Stockman (ledger), Craftsman (ficha)
**Plano:** [WP-BAIXA-DE-INSUMO-NA-VENDA](../plans/WP-BAIXA-DE-INSUMO-NA-VENDA.md) (fatia F1)

## Contexto

### O problema, medido no `main` em 19/10/2026

O que se faz quando o cliente pede (café, chá, croque, sanduíche montado) tem ficha
técnica, mas a ficha nasce **inativa** (`Recipe.is_active=False`): ela dá custo, insumo e
rótulo, e fica fora do plano de forno (`craft.suggest` considera toda ficha ativa). O seed
cria **22** fichas assim (`config/management/commands/seed.py`, seções 2b de montagem e
de bebida); o alpha tinha 23 em 23/09.

Quando esses itens são vendidos, **nenhum insumo sai do estoque**:

- O único escritor de consumo de insumo é `craftsman/contrib/stockman/handlers.py`
  (`_consume_materials`), que lê as linhas `CONSUMPTION` de uma `WorkOrder` finalizada e
  escreve `StockMovements.issue(kind=MAKE)`. Venda não gera `WorkOrder`.
- Na venda, o orquestrador só mexe no **próprio SKU vendido**: `services/stock.fulfill`
  baixa a reserva com `kind=SELL` (`adapters/stock.fulfill_hold`). O espresso (`SP`) não
  tem ledger, então entra como marcador `is_tracked=False` (`untracked_hold_entry`) e nada
  acontece.
- Os demais `StockMovements.issue` do `shop`/`backstage` são abrir embalagem
  (`package_opening`, chamado pela fornada) e perda de fim de dia (`closing`, `WASTE`).
  Nenhum parte de uma venda.

Consequência, já descrita no plano: os insumos que só existem em ficha inativa
(`CAFE-GRAO`, `PRESUNTO-CASA`, `QUEIJO-GRUYERE`, os chás da Kãnfa…) entram pela compra
(`BUY`) e nunca saem. O saldo mente para cima, o alerta de reposição em cima dele é
ficção, o guardrail `INVENTORY_BACKEND` valida contra um número que não desce, e a
margem do feito na hora (P6 do B.I.) não fecha.

### Duas ambiguidades que o código já carrega

1. **`is_active=False` quer dizer duas coisas.** "Ficha de montagem, consumida na venda"
   e "ficha desligada, não use". Baixar insumo por toda ficha inativa ligaria também as
   desligadas.
2. **A unicidade só vale para ficha ativa** (`craft_recipe_active_output_uq`). Pode haver
   duas fichas inativas para o mesmo `output_sku`, e a baixa teria de escolher uma em
   silêncio.

### O que o ledger já garante

- O ledger indexa por **SKU** (`Quant.sku`); a ficha fala SKU e unidade do insumo, e o
  porteiro de unidade (`RecipeItem.clean`) já vale.
- A perna de saída de uma transformação é `kind=MAKE`; a produção já a escreve, com a
  política "presente antes de futuro, vitrine por último" (`consumable_quants`).
- `Move.metadata` (JSON) existe, mas `StockMovements.issue` não o aceita: hoje a única
  forma de dizer "desceu por venda" seria o texto do `reason`.
- A lição do `InventoryProtocol` morto: um segundo caminho de escrita que não escrevia
  nada, sem ninguém perceber. Escritor único, e falha que grita.

## Opções

### A. Signal na venda (síncrono, junto do `SELL`)

Um receiver no orquestrador escuta a confirmação de estoque do pedido (o ponto em que
`stock.fulfill` roda, em `on_paid`/`on_accepted`) e escreve os `MAKE` na mesma transação.

- **A favor:** saldo em tempo real; nenhum componente novo.
- **Contra:** a venda passa a depender do ledger de insumo. Se o `issue` falha, ou a
  venda cai (pior que o erro que evita: recusar café porque o sistema acha que acabou o
  gruyère) ou o erro é engolido (o silêncio que criou o problema). Signal é para anunciar
  sem esperar retorno (ADR-001); aqui queremos garantia de execução, e signal não tem
  retry.

### B. Directive disparada na venda (assíncrona, idempotente)

No mesmo ponto em que o `SELL` acontece, o orquestrador cria uma `Directive`
(`stock.consume_made_to_order`, chave de idempotência = `order.ref`). O handler lê as
linhas efetivas do pedido, acha a ficha "feita na hora" de cada SKU e escreve os `MAKE`.
Cancelamento depois da baixa cria a directive inversa.

- **A favor:** é o caso que a ADR-003 reserva para Directive (comando assíncrono,
  confiável, com retry e idempotência). A venda nunca espera nem cai pelo insumo. Falha
  aparece como directive com erro e alerta, não some. Saldo quase em tempo real (o
  worker roda continuamente).
- **Contra:** mais uma directive para manter; o saldo fica atrás da venda por segundos.

### C. No fechamento do dia (em lote)

O `DayClosing` soma o que foi vendido de cada SKU feito na hora no dia, explode a ficha e
escreve os `MAKE` de uma vez.

- **A favor:** tolerante a cancelamento e correção dentro do dia; é como muita casa faz;
  um lugar só, já com tela de conferência.
- **Contra:** o saldo de insumo fica errado o dia inteiro, e é durante o dia que o
  guardrail de disponibilidade e o alerta de reposição olham para ele. Se o fechamento
  não acontece, nada desce, e esse é exatamente o modo de falha silencioso que este ADR
  existe para matar. Venda fora do dia (encomenda, ajuste depois do fechamento) precisa
  de regra própria.

## Decisão

**Opção B**, decidida pelo dono em 20/10/2026, com estas regras:

1. **Gatilho:** o mesmo ponto em que o pedido baixa o próprio estoque
   (`services/stock.fulfill`, ou seja, `on_paid`/`on_accepted` conforme o canal). Pedido
   de teste (`is_test_order`) não baixa, como já não baixa o `SELL`.
2. **Qual ficha:** só a ficha marcada como feita na hora, por marca **explícita** em
   `Recipe.meta["made_to_order"] = true` (JSON, sem migração; chave registrada em
   `docs/reference/data-schemas.md` no PR de implementação). Ficha inativa sem a marca é
   ficha desligada e não baixa. Duas fichas marcadas para o mesmo SKU: a directive falha
   gritando (alerta), não escolhe.
3. **Um nível só.** A baixa desconta os itens da ficha como publicados, nunca desce até a
   folha. O `MOLHO-BECHAMEL` do croque sai como `MOLHO-BECHAMEL`, que a fornada dele já
   pôs no estoque com `MAKE`; a farinha do bechamel já saiu na fornada. Sem dupla
   contagem.
4. **Ledger:** `StockMovements.issue(kind=MAKE)`, mesma política de `consumable_quants`
   (presente antes de futuro, vitrine por último), `reason="Consumo de venda: <ref>"` e
   `metadata={"source": "sale", "order_ref": ...}`. Para isso o `issue` ganha o argumento
   opcional `metadata` (mudança mínima no Core, necessidade medida: a F3 precisa separar
   "desceu por venda" de "desceu na fornada" dentro do mesmo `MAKE`). O SKU vendido não
   ganha `MAKE` de entrada nem `SELL` de saída quando não tem ledger: não se inventa
   estoque de espresso.
5. **Falta de insumo não trava a venda**, mas fica registrada: baixa o que existe, e o
   que faltou vira `OperatorAlert` (mesmo desenho do `production_stock_shortfall`).
6. **Cancelamento: o que decide é o preparo, não o pagamento** (dono, 20/10/2026, palavra
   por palavra: *"cafés preparados, croques preparados, não voltam pro estoque, é perda
   mesmo. Não é antes ou depois de pago que define, é antes ou depois de preparado. Se
   pagou e cancelou antes de fazer/preparar, aí sim volta para o estoque."*).
   - **Antes de preparado:** o insumo volta (`RETURN`, no mesmo saldo de onde saiu).
   - **Depois de preparado:** perda. O par `RETURN` + `WASTE` no mesmo saldo: o número
     fica onde a venda o deixou e a saída deixa de ser consumo de venda para ser perda
     (`WASTE` é o movimento de perda que o Stockman já usa, o mesmo do fechamento).
   - **"Preparado" é o ticket do KDS**, o único fato que o sistema registra sobre o
     preparo do item: o item está num ticket que a estação **iniciou** (`started_at`) ou
     **concluiu** (`completed_at`/`status="done"`). Iniciado já conta, porque começar a
     fazer já gasta o insumo (o café moído não volta para o pacote). O cancelamento
     fecha o ticket aberto, mas guarda o `started_at`, então a leitura vale depois dele.
   - **Item sem ticket** (balcão que tira o café sem KDS, item que nenhuma estação
     recebe): não há fato que diga "não foi feito", e a regra é a conservadora para o
     estoque: conta como preparado, vira perda. Devolver sem prova inflaria o saldo, que
     é o defeito que este ADR existe para matar.
   - Cancelamento parcial (2 cafés, 1 feito): proporção por item; a parte devolvida
     arredonda para baixo (na dúvida de um grama, é perda).
   - Por directive (`stock.settle_made_to_order_cancellation`), agendada no
     `on_cancelled` só quando a venda agendou baixa. Se o cancelamento chega antes de o
     worker baixar, a própria baixa vê o pedido cancelado e acerta na mesma passada.
7. **Nada retroage.** O saldo de hoje foi contado à mão; o histórico do Yooga e do alpha
   fica como está.
8. **Pré-condição:** as fichas marcadas como feitas na hora conferidas pelo dono
   (WP-RECEITAS-DA-CASA F1). Baixa automática em ficha errada desconta o insumo errado
   para sempre. A marca nasce no seed; num banco já semeado (o alpha), ela só chega com
   reseed ou marcada à mão na ficha (Admin), e as duas coisas pedem a palavra do dono.
   Sem a marca, nada baixa: o código entra no ar inerte.

## Impacto no ledger

| | Hoje | Com a recomendação |
|---|---|---|
| Venda de `SP` (sem ledger) | nada | `MAKE −7 g` em `CAFE-GRAO` (exemplo), `metadata.source=sale` |
| Venda de croque | `SELL` do croque, se rastreado | idem + `MAKE` de `PRESUNTO-CASA`, `QUEIJO-GRUYERE`, `MOLHO-BECHAMEL` |
| Fornada de bechamel | `MAKE +` bechamel, `MAKE −` insumos dele | sem mudança |
| Cancelamento pós-baixa | `RETURN` do produto | idem + `RETURN` dos insumos |
| Escritores de `MAKE` | `craftsman/contrib/stockman` (fornada), `package_opening` | os mesmos + um handler de directive, escritor único da venda |

Leitura do `MAKE` por origem: fornada = `reason` "Consumo de produção"; venda =
`metadata.source == "sale"`. O Compras (F3) e a margem do B.I. (F4) leem daí.

## Decisões do dono (20/10/2026)

1. **Gatilho: a venda** (opção B), pela directive idempotente por pedido no ponto do
   `stock.fulfill`, com a marca explícita `Recipe.meta.made_to_order` e um nível de ficha.
   Falta de insumo não trava a venda: vira alerta. Nada retroage.
2. **Cancelamento: antes de preparado devolve, depois de preparado é perda** (regra 6).

## Implementação

- `shop/services/made_to_order.py`: `schedule_consumption` (chamada por
  `stock.fulfill`), `consume`, `schedule_cancellation_settlement` (chamada pelo
  `on_cancelled`), `settle_cancellation`. Handlers em `shop/handlers/made_to_order.py`.
- Idempotência em três camadas: recibo permanente das directives
  (`create_persistently_deduped`, uma vez na vida do pedido), efeito numa transação só
  e, como guarda final, o próprio ledger (`Move.metadata.source` = `sale`/`sale_cancel`
  com o `order_ref`). O `Order.data["made_to_order_consumption"]` é rastro, não guarda.
- Alertas: `stock_sale_ingredient_short` (um ativo por insumo, não por pedido) e
  `stock_sale_recipe_ambiguous`.
- Mudança de Core: só o argumento opcional `metadata` em `StockMovements.issue`. Medida:
  `Move.metadata` existia, mas o único jeito de o `issue` gravá-lo era nenhum, e sem ele
  o `MAKE` da venda e o da fornada são indistinguíveis no ledger (o `reason` é texto
  livre). O `receive` já aceitava `**metadata`.
- Fora daqui, de propósito: o insumo dos **adicionais** escolhidos no produto
  (`meta["options"]`, "+ Ovo frito") ainda não baixa; a devolução de mercadoria
  (`on_returned`) não devolve insumo, porque o item devolvido já foi preparado.

## Consequências

- Uma directive nova (`stock.consume_made_to_order` e a inversa) e um handler no
  orquestrador; nenhuma mudança de modelo.
- `StockMovements.issue` aceita `metadata` opcional.
- O seed marca `made_to_order` nas 21 fichas de montagem e bebida; a irmã do
  `test_massa_de_cada_peca.py` é `backstage/tests/test_ficha_feita_na_hora.py`.
- O guardrail `INVENTORY_BACKEND` e o alerta de reposição passam a ver consumo real de
  café, chá e recheio.
