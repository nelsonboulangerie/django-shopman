# WP — Ficha em gramas para SKU que se compra e se vende por unidade

> Estado: **desenho, sem código** (24/09/2026). Parte 5 da frente "comprável /
> vendável" (#1058, #1061, #1062). Parou aqui de propósito: o briefing mandava
> implementar só se coubesse limpo no protocolo do catálogo, e não cabe — mexe
> em cinco pontos do Core do Craftsman que hoje falam uma unidade só.

## O caso

A manteiga Président 200 g é **um SKU**: a casa compra o tablete, vende o
tablete no balcão e usa manteiga na massa. Desde #1058 isso é um cadastro de
compra e um de venda com o mesmo SKU e o mesmo estoque, na mesma unidade —
`un`, porque é tablete que entra pela nota e sai pelo PDV.

A ficha do croissant, porém, fala **gramas**: "250 g de manteiga". Hoje isso é
recusado na porta (`RecipeItem.clean`, `packages/craftsman/.../models/recipe.py`
~l. 350): *a unidade do ingrediente deve coincidir com a unidade do SKU
cadastrado*. A regra é certa — o ledger conta em `un`, e baixar "250" de um
estoque em tabletes seria baixar 250 tabletes.

## Por que não é um ajuste local

A ponte g → un precisa de um fator (200 g por tablete) e esse fator teria de
atravessar **toda** a cadeia que hoje assume "unidade da ficha = unidade do
estoque":

| Ponto | Onde | O que muda |
|---|---|---|
| 1. Porta da ficha | `models/recipe.py::RecipeItem.clean` | aceitar massa quando o catálogo declara conteúdo por unidade |
| 2. Protocolo do catálogo | `protocols/catalog.py::ProductInfo`/`ItemInfo` + os dois backends (Offerman, Buyman) e o composto do orquestrador | expor o conteúdo por unidade (`net_content_g`) |
| 3. BOM congelado | `services/scheduling.py::build_recipe_snapshot` | congelar o fator por item (`stock_per_recipe_unit`), para a fornada de hoje não mudar se alguém corrigir o conteúdo amanhã |
| 4. Consumo | `services/execution.py` (REQUIREMENT/CONSUMPTION) | gravar o item de consumo **na unidade do estoque** (1,25 un), com a quantidade da ficha (250 g) no `meta` |
| 5. Necessidades e guardrail | `services/queries.py::needs`, `contrib/formula`, `InventoryAvailabilityBackend` | comparar necessidade e saldo na mesma unidade |

Além disso, custo (`shop/services` de custo de ficha), alérgenos derivados e a
massa da peça (`_item_mass_in_kg`) leem a ficha: o fator entra neles também, ou
eles passam a errar calados. Cada um desses é caminho quente de produção, com
teste adversarial próprio (`test_producao_adversarial_*`). Fazer isso "de
carona" no fim de uma frente de catálogo é o jeito certo de quebrar a fornada.

## O que já existe e NÃO resolve

- `Product.unit_weight_g` é o **peso anunciado da peça assada** (piso, nunca
  mente para menos — decisão de 05/09). Não é conteúdo líquido de embalagem de
  revenda, e reaproveitá-lo misturaria duas verdades num campo.
- `buyman.MaterialConversion` é ponte **de compra** (caixa → base). A pergunta
  aqui é o contrário: da ficha para a base.

## Desenho proposto (para quando for WP próprio)

1. **Um dado, um dono.** Conteúdo líquido por unidade mora no cadastro de
   compra: `Material.metadata["net_content"] = {"quantity": "200", "unit": "g"}`
   — é dado da embalagem, que o Compras lê da nota/rótulo. Não é campo novo de
   modelo (Core é Sagrado, regra 1), e a chave entra em `data-schemas.md`.
2. **O fator é derivado, nunca digitado duas vezes**: `shopman.utils.units`
   converte a unidade da ficha para a unidade do conteúdo (definicional, tipo 1
   da ADR-024) e divide pelo conteúdo. `g` → `un` com 200 g/un dá 0,005.
3. **O protocolo ganha um campo opcional** em `ItemInfo`/`ProductInfo`
   (`net_content: tuple[Decimal, str] | None`). Backend que não sabe responde
   `None` e a porta da ficha segue recusando — falha fechada.
4. **O snapshot congela o fator** por item. `execution.py` grava o consumo na
   unidade do estoque; o `meta` do `WorkOrderItem` guarda a quantidade da
   ficha, para o relatório de produção falar gramas.
5. **Necessidades, guardrail e custo** passam a ler a quantidade já convertida
   do snapshot — um lugar só faz a conta.
6. **Peso variável fica como está**: queijo vendido por kg tem `kg` dos dois
   lados e a ficha fala `g` (mesma dimensão) — isso já funciona hoje, provado
   em `test_purchase_recebe_revenda.py::test_queijo_por_quilo_fecha_com_kg_dos_dois_lados`.

## Testes que o WP precisa trazer

- ficha "250 g de MANTEIGA-SAL-PRESIDENT-200" baixa 1,25 un no finish;
- sem `net_content`, a ficha em g continua recusada (mensagem que diz o que falta);
- corrigir o conteúdo depois do plano não muda a fornada já planejada;
- guardrail aprova/recusa pela mesma conta; custo da ficha bate com o custo do tablete.

## Enquanto isso

O caminho que já funciona: a ficha fala a unidade do estoque ("1,25 un de
manteiga") — exato, só menos natural para quem pesa. Ou o insumo da massa é
outro SKU (manteiga de 5 kg a granel, em kg), e o tablete de 200 g é só revenda.
