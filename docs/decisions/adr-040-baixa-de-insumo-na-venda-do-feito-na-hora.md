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
2. **Qual ficha:** a ficha VIGENTE do SKU cujo modo de produção é "Na hora"
   (`Recipe.production_mode`, ver "Modo de produção" abaixo). Ficha "Em lote" não baixa na
   venda (a ordem de produção já baixou); ficha arquivada não baixa nada. A constraint
   de uma ficha vigente por SKU garante que a baixa nunca escolhe entre duas. ⚠️ Até
   20/10/2026 a regra era uma marca em `Recipe.meta["made_to_order"]` numa ficha
   INATIVA; ela morreu (`shop.0104`).
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
8. **Pré-condição:** as fichas "Na hora" conferidas pelo dono (WP-RECEITAS-DA-CASA
   F1). Baixa automática em ficha errada desconta o insumo errado para sempre. O modo
   nasce no seed; no banco já semeado (o alpha) ele chega pela migração de dados
   `shop.0104_fichas_na_hora_vigentes`, que dá o modo "Na hora" às MESMAS 21 fichas pelo
   `ref` (lista única, travada contra o seed em `backstage/tests/test_ficha_feita_na_hora.py`),
   devolve a vigência às que estavam inativas só por isso (sem violar uma vigente por
   SKU: a que não pode fica arquivada e o log diz qual), limpa `made_to_order` e
   `made_to_order_marked_by` do `meta` de toda ficha e põe a coleção Doces na estação
   Lanches (o pain perdu é "Na hora"). Sem reseed. A `shop.0102` continua no histórico;
   o que ela escreveu, a `0104` apaga.

## Modo de produção (decisão do dono, 20/10/2026)

O vocabulário é o de MRP: fabricar para estoque, fabricar sob pedido, comprar.

- **Em lote** (`ProductionMode.BATCH`, o padrão): planejado, sai por ordem de produção
  (`WorkOrder`), empurra estoque, e a ordem baixa os insumos. Pão, creme, recheio,
  molho (o bechamel), o hot dog de lote.
- **Na hora** (`ProductionMode.MADE_TO_ORDER`): puxado pela venda. Nunca é planejado nem
  tem ordem de produção; o KDS o manda à estação de preparo; a venda baixa os insumos da
  ficha, um nível só. Café, chá, croque, pain perdu.
- **Revenda** é o SKU sem ficha vigente. Não é um modo.

**Onde mora.** Campo do Core, `craftsman.Recipe.production_mode` (`craftsman.0019`), e
não JSON: é estrutural, o próprio Core o consulta (o `craft.suggest` e a recusa de
ordem de produção vivem no `craftsman`), e o KDS, a venda e o planejamento o leem em lote
por SKU. Fica na ficha (o `Recipe`, cujo `ref` é o da receita do inventário), não na
versão: publicar uma versão reescreve itens e rendimento, nunca o modo.

**`is_active` é só vigente × arquivada.** O seed desligava café, chá e croque para
tirá-los do planejamento, e isso sobrepunha "arquivada" com "montada na venda" (a
ambiguidade 1 do Contexto). Agora toda ficha em uso é vigente, e quem tira o "Na hora"
do plano é o modo.

**Uma leitura, três usos.** `craftsman.services.production_modes_for_output_skus(skus)`
(sku → modo da ficha vigente; sem ficha vigente = revenda, fica de fora):

1. **Planejamento** só vê "Em lote": `craft.suggest`, a matriz e as opções do
   planejamento, a mise-en-place, a finalização rápida, os relatórios de produção, a
   sugestão por estação, a conferência de déficit a jusante, as escritas de ordem de
   produção (`shop/services/production`, `backstage/services/production`) e o "sai do
   forno" do aviso de estoque (`catalog_context.comes_out_of_the_oven`). O Core recusa
   ordem de produção de ficha "Na hora" (`CraftError("MADE_TO_ORDER_RECIPE")`).
2. **Venda** baixa só "Na hora" (`made_to_order_recipes`). Se o próprio SKU é "Em lote",
   a venda não baixa insumo: a ordem de produção já baixou, e baixar de novo seria
   contar duas vezes.
3. **KDS:** o tipo de ESTAÇÃO continua (Preparo, Separação, Saída: o trabalho que a
   estação faz). O que morreu é o KDS classificar o item sozinho ("receita ativa" era
   preparo, `get_prep_skus`). Item "Na hora" vai à estação de Preparo, e a coleção
   escolhe qual (Cafés × Lanches); item "Em lote" ou revenda é Separação, e só quando
   há o que separar (pedido remoto, encomenda). No balcão presencial (`prep_only`) ele
   nunca vira ticket. Uma estação só recebe item do tipo dela: o fallback que casava
   item de um tipo com estação de outro pela coleção morreu (ele escondia o defeito
   abaixo). Item "Na hora" sem estação de Preparo para a coleção fica sem rota e vira
   o alerta `kds_unrouted_item`.

**O defeito que isso fecha (medido contra o seed em 20/10/2026).** No balcão presencial
o café e o croque não viravam ticket (eram "picking" por terem ficha inativa, e o
`prep_only` os pulava), enquanto o pão de lote virava ticket em Encomendas (era "prep"
por ter ficha ativa, e caía no catch-all de separação). No pedido remoto o café chegava a
Cafés só pelo fallback de coleção. Agora: café e croque vão a Cafés e Lanches; pão, água
e soda não tocam o KDS no balcão.

**Como o dono muda o modo.** Produção → Ajustes → Receitas → Fichas de execução →
Editar → Operação → "Modo de produção" (também na operação da receita do inventário), ou
Admin → Fichas técnicas → a ficha → Identificação. Que estação de Preparo recebe o item é
Admin → KDS → a estação → coleções, e a coleção principal do produto no Catálogo. O
Gestor mostra, só para ler, "Feito na hora na estação Cafés" ou "Produzido em lote" no
produto, com o link para a ficha.

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
   `stock.fulfill`, com o modo de produção "Na hora" da ficha vigente e um nível de ficha.
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
- Alerta: `stock_sale_ingredient_short` (um ativo por insumo, não por pedido). O
  `stock_sale_recipe_ambiguous` morreu com a marca: a ficha vigente é uma só por SKU.
- Mudança de Core: só o argumento opcional `metadata` em `StockMovements.issue`. Medida:
  `Move.metadata` existia, mas o único jeito de o `issue` gravá-lo era nenhum, e sem ele
  o `MAKE` da venda e o da fornada são indistinguíveis no ledger (o `reason` é texto
  livre). O `receive` já aceitava `**metadata`.
- **Adicionais escolhidos no produto** (`items[].meta.options`, "+ Ovo frito"; extensão
  de 20/10/2026): a mesma directive baixa o insumo que o cadastro da opção declara
  (`consumes`, congelado na linha no momento da venda por
  `product_options.resolve_selection`): `qty do insumo × qty da opção × qty da linha`,
  na unidade-base do insumo (conversão definicional `g` → `kg` quando a grafia difere).
  Mesmo ledger (`MAKE`, `source=sale`, com `option_group`/`option_ref` no lugar de
  `recipe_ref`), mesmo alerta de falta sem travar ("o adicional Ovo frito de CQMO
  pede…"), mesma regra de cancelamento pelo preparo (o `sold_sku` é o item que levou o
  adicional, e a proporção é a do item). A marca é o próprio `consumes`: ao contrário
  da ficha, o adicional baixa mesmo quando o item não tem ficha `made_to_order` (o
  Frappé, por exemplo), porque nenhuma fornada conhece a escolha do cliente e o
  `consumes` só existe se alguém o cadastrou na aba Escolhas. Opção sem `ref` (iFood)
  não é da casa e não baixa.
- Fora daqui, de propósito: a devolução de mercadoria (`on_returned`) não devolve
  insumo, porque o item devolvido já foi preparado.

## Consequências

- Uma directive nova (`stock.consume_made_to_order` e a inversa) e um handler no
  orquestrador. Um campo novo no Core: `Recipe.production_mode` (ver "Modo de produção").
- `StockMovements.issue` aceita `metadata` opcional.
- O seed dá o modo "Na hora" às 21 fichas de montagem e bebida, todas vigentes; a irmã
  do `test_massa_de_cada_peca.py` é `backstage/tests/test_ficha_feita_na_hora.py`, que
  roda o seed e prova o roteamento do KDS no balcão e no remoto. A migração `shop.0104`
  leva o mesmo modo ao banco já semeado.
- O guardrail `INVENTORY_BACKEND` e o alerta de reposição passam a ver consumo real de
  café, chá e recheio.
