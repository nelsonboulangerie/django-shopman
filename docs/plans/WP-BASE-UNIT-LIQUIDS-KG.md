# WP-BASE-UNIT-LIQUIDS-KG — os líquidos que a casa PESA passam a contar em kg

> Aberto em 2026-09-03, a pedido do dono. Aplica a [ADR-024](../decisions/adr-024-material-unit-base-and-purchase.md)
> aos insumos líquidos da Nelson. Não muda doutrina nem código de conversão:
> muda **cadastro**, e move a ponte do lugar errado para o certo.
> Continuação prática do [UNIT-CONVERSION-PLAN](UNIT-CONVERSION-PLAN.md) (fases 0-6 concluídas).

## O problema em uma frase

Água, leite, azeite e creme de leite estão cadastrados em **litro**, mas a padaria os
**pesa** na bancada. A R1 da ADR-024 diz que a unidade-base é a do *momento da verdade*
— "se o insumo é pesado, `kg`" — então hoje a base está no eixo errado, e o preço disso
é uma ponte de densidade dentro da **produção diária**: a receita fala em grama, a ficha
tem de virar litro ao publicar, e a tela de pesagem mostra `3,4 L (3502 g)` porque nenhum
dos dois números sozinho serve ao padeiro.

## A decisão

Trocar a unidade-base desses quatro insumos para `kg`. A ponte de densidade sai da
produção e vai para o **recebimento**, que é o lado que a ADR-024 R2 foi desenhada para
converter: a nota fala "12 L de leite", uma `MaterialConversion` declarada leva para kg,
e o número carrega o `≈` até a tela (R3).

| | Hoje (base litro) | Depois (base kg) |
|---|---|---|
| Receita e pesagem | grama | grama |
| Ficha, livro e custo | litro | kg |
| Ponte de densidade | ao publicar a ficha, todo dia | ao lançar a nota, toda semana |
| Tela de mise en place | `3,4 L (3502 g)` | `3,502 kg` |

A precisão é a mesma nos dois desenhos (a densidade é a mesma constante). O que muda é
**onde a ponte fica** e **quantos leitores precisam dela**: hoje, oito leitores da ficha
(separação, pesagem, guardrail de falta, sugestão de compra, custo, nutrição, expansão de
BOM e a baixa) só funcionam porque a ficha já foi convertida. Depois, nenhum precisa.

### Os quatro insumos e a densidade declarada

A densidade já está em `INGREDIENT_PROFILES` (`Material.metadata["density_g_per_ml"]`).
Nada é inventado aqui; a R4 manda **recusar** quem não a tiver declarada.

| SKU | Densidade (g/ml) | 1 L vale |
|---|---|---|
| `AGUA-FILTRADA` | 1,00 | 1,000 kg |
| `LEITE` | 1,03 | 1,030 kg |
| `AZEITE` | 0,91 | 0,910 kg |
| `CREME-DE-LEITE` | 1,01 | 1,010 kg |

## ⛔ O que NÃO muda

- **Nenhuma linha da física** (`shopman.utils.units`) e nenhuma regra da ADR-024.
- **`RecipeItem.clean`** continua exigindo a unidade do cadastro. É ele que torna a troca
  segura: se algo escapar, a ficha recusa em vez de gravar número mudo.
- **A ponte de densidade em `publish_version`** (`_in_catalog_unit`) **fica no código** e
  vira dormente sozinha: grama e kg são a mesma dimensão, então ela deixa de ser chamada.
  Ela continua servindo a qualquer insumo que um dia seja cadastrado em volume.
- **`seed --flush`** não entra nesta frente. O banco vivo é migrado por comando explícito.

## Frentes

### A · Seed (`config/management/commands/seed.py`)

1. `material_attrs`: os quatro SKUs passam de `("l", …)` para `("kg", …)`. A validade não muda.
2. `recipes_data`: cada linha desses SKUs é **multiplicada pela densidade** (a água não
   muda de número; leite, azeite e creme mudam). Preservar a física é obrigatório: manter o
   número e trocar o rótulo seria mudar a fórmula em 3% em silêncio, exatamente o que a R3 proíbe.
3. Semear uma `MaterialConversion` por insumo: `label="litro"`, `kind=APPROXIMATE`,
   `to_base_factor=<densidade>`, `supplier=None`. Sem ela a primeira nota em litro trava (R4).
4. **Invariante de prova:** a massa total de cada ficha é a MESMA antes e depois. Hoje o
   `_item_mass_in_kg` já converte o volume pela densidade; escrever o resultado dessa conta
   no cadastro não pode mover a balança.

### B · Comando `convert_material_base_unit` (banco vivo)

Genérico, não sabe o nome de nenhum insumo da Nelson. Dry-run por padrão (padrão do
`refresh_seed_dates`), transação única, idempotente (insumo já na unidade alvo é pulado).

```bash
python manage.py convert_material_base_unit LEITE AZEITE --to kg
python manage.py convert_material_base_unit LEITE AZEITE --to kg --apply
```

Converte, na mesma transação: `Material.unit`; `Quant`, `Move` e `Hold` do stockman;
`RecipeItem` (quantidade **e** unidade); o `_recipe_snapshot` das WorkOrders **abertas**;
`SupplierMaterialCost.cost_q` (que é dinheiro **por unidade-base**, então divide); e cria a
`MaterialConversion` da unidade antiga, para a nota seguinte não travar. Fecha varrendo o
banco por qualquer outro modelo que guarde quantidade daquele SKU e **relata o que não tocou**.

Sem densidade declarada, recusa nomeando o que cadastrar (R4). História de WorkOrder
concluída **não** é reescrita: ela contou no que contava.

### C · Docs e integração

`commands.md`, nota no `UNIT-CONVERSION-PLAN`, e QA no banco semeado (publicar uma receita
com líquido e conferir ficha, mise en place e baixa).

## ⚠️ A armadilha: o cofre reverte a base em silêncio

`export_backup`/`import_backup` levam **`materials`** (com a unidade), **`recipe_items`**
(quantidade **e** unidade) e **`supplier_material_costs`** (dinheiro por unidade-base).
Não levam estoque.

Logo, **uma planilha do cofre exportada ANTES desta mudança, reimportada DEPOIS, escreve
litro por cima de kg** — e como ela reverte o cadastro *e* a ficha na mesma passada, os
dois voltam a concordar entre si e nada grita. O saldo do estoque, que o cofre não toca,
é que fica 3% errado, calado.

**Regra operacional:** assim que esta frente entrar no ar, **re-exportar o cofre** e
descartar as planilhas anteriores. Os XLSX que já estão no Sheets são pré-mudança.

## Efeito colateral esperado (e desejado)

A tela de separação anota a linha pela conversão declarada de menor fator
(`_counting_conversions`, `backstage/projections/production.py`). Com a ponte "litro"
declarada, o leite passa a aparecer como `3,502 kg · ≈ 3,4 litros`, exatamente como o ovo
aparece como `≈ 6 ovos`. É informação para quem despeja de caixa de 1 L, não ruído.
A água não ganha a ponte (não entra por nota), então não ganha anotação.

## Fora deste WP

Outros insumos em volume que a casa venha a cadastrar; a decisão de comprar leite por kg
em vez de litro (é do fornecedor, não do sistema).
