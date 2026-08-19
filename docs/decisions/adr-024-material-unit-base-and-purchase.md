# ADR-024 — Unidade do insumo: base para receita e estoque, unidade de compra para custo

**Status:** Proposto (rascunho para decisão do dono, 2026-08-19)
**Data:** 2026-08-19
**Escopo (se aceito):** `packages/buyman` (`Material.unit`, `SupplierMaterialCost` ganha unidade de compra + fator); `shopman/shop` (custo por unidade-base derivado); `config/management/commands/seed.py` (tabela de unidades); Fase 2 do [BUYMAN-PROCUREMENT-PLAN](../plans/BUYMAN-PROCUREMENT-PLAN.md) (`PurchaseOrder`)
**Não muda nada hoje:** esta ADR **não** vem com implementação nem com migração. O campo só muda **depois** que o dono responder a pergunta do fim.
**Origem:** auditoria do Buyman (2026-08-18), achado B2

---

## Contexto

`Material.unit` (`packages/buyman/shopman/buyman/models/material.py:28`) alimenta
duas mecânicas com pressões opostas, e por isso serve mal às duas.

**1. A receita exige igualdade estrita.** `RecipeItem.clean()`
(`packages/craftsman/shopman/craftsman/models/recipe.py:231`) recusa unidade
diferente da do SKU no catálogo — *"a unidade do ingrediente deve coincidir com a
unidade do SKU cadastrado"*. **Não há conversão, por design.** Insumo em `kg`
obriga toda ficha técnica a falar em kg (0,5 kg, nunca 500 g).

**2. O custo é centavo inteiro por essa mesma unidade.** `SupplierMaterialCost.cost_q`
é "custo por unidade do insumo, em centavos" (ADR-002). Insumo em `g` torna
custos sub-centavo **irrepresentáveis**: canela a R$ 45,00/kg são 4,5
centavos/g — arredonda para 4 ou 5, erro de ~11% multiplicado por cada grama
custeado.

Escolher a unidade fina quebra o custo; escolher a grossa quebra a ergonomia da
ficha técnica. O seed já vive o dilema em silêncio
(`config/management/commands/seed.py`): farinhas, sal e açúcar em `kg` (custo
representável, receita fracionária); **CANELA e ALECRIM em `g`** (receita
ergonômica, custo condenado ao arredondamento).

E o silêncio é literal: o seed cria os `RecipeItem` por `objects.create()`, que
**não chama `clean()`**. Resultado hoje, no banco de desenvolvimento: o `Material`
CANELA está em `g` e o `RecipeItem` de canela está em `kg` com quantidade
`0.060` — as duas unidades já discordam, e nada gritou. O guarda existe; ele só
não é chamado no caminho que popula os dados.

Falta o eixo que o item master clássico tem exatamente para isso: **unidade de
compra + fator de conversão**. Ninguém compra grama de farinha: compra-se saco de
25 kg, e é *nesse* nível que o custo do fornecedor existe no mundo real. A Fase 2
(`PurchaseOrder`/recebimento) vai precisar da unidade de compra de qualquer
forma — a linha do pedido é "3 sacos", não "75 kg". Decidir agora evita migrar
dados de custo duas vezes.

## Decisão proposta

1. **`Material.unit` é a unidade-base**, e só isso: a unidade em que a receita
   escreve e o estoque conta. Uma por insumo, sem conversão, exatamente como
   `RecipeItem.clean()` já exige.
2. **O custo ganha o eixo de compra.** `SupplierMaterialCost` passa a guardar:
   - `purchase_unit` — a unidade em que o fornecedor vende (saco, caixa, kg, l);
   - `purchase_factor` — quantas unidades-base cabem em uma unidade de compra
     (decimal; 1 saco = 25 kg);
   - `cost_q` — centavos **por unidade de compra** (ADR-002 intacto: o que se
     guarda em dinheiro continua inteiro em centavos, e agora é o número que
     está na nota do fornecedor).
3. **Custo por unidade-base é derivado, não guardado**: `cost_q / purchase_factor`
   calculado em `Decimal`, arredondado **só na ponta**, quando vira dinheiro de
   verdade (custo de uma fornada, custo de um produto). Assim a canela a
   R$ 45,00/kg é exata, e o erro de 11% desaparece com o arredondamento
   intermediário que o causava.
4. **A unidade-base do insumo passa a ser escolhida pela receita**, não pelo
   custo — porque o custo deixou de depender dela. Na prática: CANELA e ALECRIM
   podem seguir em `g`, com custo lançado por kg comprado.
5. **A Fase 2 herda o eixo pronto**: a linha do `PurchaseOrder` fala em unidade
   de compra e o recebimento converte para base ao emitir o `Move` de entrada.

## Consequências

**Positivas**

- Os dois senhores param de brigar: receita manda na unidade-base, fornecedor
  manda na unidade de compra.
- O custo passa a ser lançado como está na nota fiscal — menos conta de cabeça
  no cadastro, menos erro de digitação.
- Fase 2 nasce sem migração de custo.

**Negativas / custos**

- Duas colunas novas em `SupplierMaterialCost` e uma migração no Buyman (barato
  hoje: a tabela é master data pequena, pré-go-live).
- O cadastro de custo ganha dois campos — mais fricção na tela de quem digita.
- Fator errado é erro silencioso e caro (custo 25× menor). Pede validação
  (`purchase_factor > 0`) e um alerta de ordem de grandeza na tela.

## Alternativas consideradas

- **Guardar custo em milésimos de centavo** (mudar a granularidade de `cost_q`):
  resolve a representação e não resolve a Fase 2 — continua faltando "saco de
  25 kg" para a linha do pedido de compra. E rompe ADR-002 sem ganhar o eixo.
- **Regra de cadastro "insumo sempre na unidade grossa" (kg/l)**: zero código —
  é a alternativa B da pergunta abaixo. Custa fichas técnicas em 0,060 kg e
  ainda deixa a Fase 2 sem unidade de compra.
- **Conversão automática de unidade na receita** (g↔kg): rejeitada por design
  no Craftsman, e não é o problema — o problema é o custo, não a ficha.

## Pergunta ao dono (responda A ou B)

> A unidade do insumo deve passar a ter **dois eixos** (A: `unit` é a
> unidade-base da receita e do estoque; o custo é lançado por unidade de compra
> com fator de conversão, como já vem na nota do fornecedor), ou continuamos com
> **um eixo só** (B: `unit` serve receita, estoque e custo, e a regra vira
> "cadastre todo insumo na unidade grossa — kg/l", com fichas técnicas em
> 0,060 kg e a unidade de compra adiada para a Fase 2)?

## Referências

- Auditoria do Buyman (2026-08-18), achado B2
- [ADR-002](adr-002-centavos.md) — dinheiro é inteiro em centavos
- [ADR-023](adr-023-cost-live-and-frozen.md) — que custo é esse que a unidade expressa
- [BUYMAN-PROCUREMENT-PLAN](../plans/BUYMAN-PROCUREMENT-PLAN.md) — Fases 2–4
- `packages/craftsman/shopman/craftsman/models/recipe.py` (`RecipeItem.clean`), `packages/buyman/shopman/buyman/models/cost.py`
