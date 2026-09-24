# WP — Ficha em gramas para SKU que se compra e se vende por unidade

> Estado: **implementado** (24/09/2026) pelo modelo do dono — abrir a embalagem.
> Código: `shopman/shop/services/package_opening.py`. Testes:
> `shopman/shop/tests/test_abrir_a_embalagem.py`.

## O caso e a decisão do dono

A manteiga Président 200 g é comprada e vendida por unidade (`un`), e a ficha do
croissant fala gramas. O dono deu o modelo (24/09):

> "na produção é consumido em gramas. De alguma forma, o estoque deve saber que
> aquela unidade não está mais disponível para revenda, mas aquela quantidade,
> dentro da validade, em tese, sim."

Ou seja: **abrir a embalagem**.

## O desenho que ficou — sem mexer no Core

O primeiro desenho (fator g → un atravessando a ficha) exigia cinco mudanças no
Core do Craftsman. O modelo do dono dispensa todas, porque o aberto é **outra
coisa** — e, portanto, outro SKU:

| Peça | Onde | O que é |
|---|---|---|
| Embalagem | `Material` `MANTEIGA-SAL-PRESIDENT-200` (`un`), com `metadata.opens_into = {sku, quantity, shelf_life_days?}` | o tablete que se compra e se vende |
| Aberto | `Material` `MANTEIGA-COM-SAL` (`kg`), sem cadastro de venda | o insumo que a ficha usa |
| Ficha | `RecipeItem(input_sku="MANTEIGA-COM-SAL", unit="kg")` | a mesma regra de unidade de sempre, sem exceção |
| Abrir | `package_opening.open_package` | 1 un sai da embalagem (`MAKE`) e o conteúdo entra no aberto (`MAKE`), no mesmo lugar, com lote próprio se há validade depois de aberta |

- **Quando abre:** no fechamento da fornada (`shop/services/production.finish_work_order`),
  antes do consumo, e só o que falta: uma embalagem por vez, até o aberto cobrir a
  quantidade BRUTA da ficha congelada. Fornada já fechada (replay) não abre.
- **FEFO:** o consumo já tira do quant mais antigo primeiro, então o aberto que
  sobrou é usado antes do recém-aberto.
- **Revenda nunca vende o aberto:** o aberto não tem cadastro de venda.
- **Vitrine nunca é aberta:** só embalagem fora de posição vendável (a mesma régua do
  consumo, #1062).
- **Guardrail:** `InventoryAvailabilityBackend` conta o aberto + o que as embalagens
  fechadas (fora da vitrine) ainda podem virar.
- **Reposição:** a saída da embalagem é `MAKE` com delta negativo — entra no consumo
  médio que o Compras usa para sugerir o pedido do tablete.

## Cenário do dono (teste)

Manteiga 200 g, fichas de 50, 100 e 80 g: a 1ª abre um tablete (sobra 150 g); a
2ª usa o aberto (sobra 50 g); a 3ª abre o 2º só quando o aberto não basta (sobra
170 g). Depósito: 3 → 2 → 2 → 1. Vitrine intacta.

## Fica para depois

- Tela para declarar `opens_into` no Compras (hoje é metadado do cadastro de compra).
- Abrir à mão (o chef abriu o tablete fora de uma fornada): é o mesmo `open_package`,
  falta só o gesto.
