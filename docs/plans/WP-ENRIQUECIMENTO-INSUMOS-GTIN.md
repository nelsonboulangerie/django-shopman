# WP — Enriquecimento de INSUMOS e compráveis por GTIN

**Estado:** planejado, não iniciado
**Pedido por:** Pablo, 05/09/2026 — *"faça o mesmo para insumos/compráveis"*
**Depende de:** o enriquecimento de produto de revenda (PR do `product_enrichment`),
que já resolve a metade de venda e estabelece o desenho a copiar.

---

## Por que existe

O produto que a casa **faz** tem receita, e a derivação já cuida dele: o
`dietary_from_recipe` une o perfil de cada insumo-folha e materializa alérgeno e
dieta no produto, com a trava certa — *não reivindica nada se um único insumo
não declarar*.

Essa trava é o que torna este WP necessário. **Ela transfere para o insumo a
responsabilidade pela verdade do rótulo do produto acabado.** Hoje o perfil do
insumo é digitado à mão em `RecipeItem.meta` (`diet` + `allergens`), e enquanto
for digitado ele tem os dois defeitos que a casa já conhece:

- **envelhece calado** — trocar a marca da manteiga não move o `meta`;
- **cala por omissão** — insumo sem `diet` derruba a derivação do produto
  inteiro, e o rótulo volta a ser o que estava lá antes.

Medido em 05/09/2026: 58 itens de receita, 47 com `diet` (81%) e **22 com
`allergens`**. As 18 receitas ativas derivam hoje porque as folhas estão
completas — mas é equilíbrio mantido à mão, não garantido.

## O que muda

Insumo comprável ganha **GTIN**, e o GTIN abre a mesma porta que abriu para a
revenda: nome, marca, foto, NCM pela Cosmos; alérgeno pelo Open Food Facts.
Aceito por gente, nunca aplicado sozinho.

O ganho é maior aqui do que na revenda, porque **um insumo alimenta muitos
produtos**: acertar a farinha acerta o rótulo de dez pães de uma vez.

## Escopo

1. **Onde mora o GTIN do insumo.** O comprável vive no Buyman
   (`Material`/`SupplierMaterialCost`) e o consumo vive em `RecipeItem.input_sku`.
   ⚠️ **Decidir primeiro se o GTIN é do material ou da oferta do fornecedor** —
   a mesma farinha comprada de dois distribuidores pode ter GTINs diferentes, e
   a resposta muda o modelo. Pende de decisão; não começar por código.
2. **Reuso do serviço.** `shop/services/product_enrichment.py` já isola
   `build_suggestion(gtin)` do que é Product. Extrair a parte de busca para
   servir os dois lados, sem duplicar o mapeamento OFF→casa nem as travas.
3. **Aceite.** Ação no Admin do material, espelhando
   `accept_enrichment` — com `permissions=` (a armadilha documentada: ação em
   lote sem isso roda para quem só tem `view`).
4. **Propagação.** Aceitar alérgeno no insumo deve **reabrir a derivação** dos
   produtos que o usam. O sinal já existe (`Recipe` `post_save` chama a
   agregação); falta disparar a partir do material.
   ⚠️ Sem isto o WP entrega metade: o dado entra e o rótulo não se move.
5. **Cobertura como número.** Um comando ou painel que diga *quantos insumos
   declaram* e *quais receitas estão a um insumo de derivar*. Dívida que não
   tem número cresce calada — foi o que este WP descobriu ao ser escrito.

## Fora de escopo

- **GTIN múltiplo por item.** Decidido em 05/09: sabor é produto próprio, e se o
  código bipado não bater o operador busca de outro jeito. Não é bloqueante.
- **Foto na vitrine vinda do OFF.** Licença CC-BY-SA exige atribuição; a foto do
  cliente continua sendo a da casa.
- **GS1.** Serve para **emitir** código próprio, não para consultar o de
  terceiro. Adesão de R$ 683 + anuidade por faixa de faturamento, e a Nelson
  revende marca alheia — resolve um problema que a casa não tem.

## Custo externo

Cosmos plano **Basic: grátis, 25 consultas/dia**. Para o volume de insumos da
casa, o catálogo inteiro sai em poucos dias sem pagar nada. Planos pagos começam
em R$ 499,99/mês (100/dia) e são assinatura mensal — se um dia precisar de um
lote grande, o padrão é assinar, enriquecer e cancelar. ⚠️ **Os termos sobre
reter o dado após o cancelamento não estão na página de preços** e precisam ser
confirmados com a Bluesoft antes de contar com isso.

## Prova esperada

- Insumo com GTIN gera sugestão `pending` e **não** altera nada sozinho.
- Aceitar no material propaga: o produto que usa aquele insumo tem o rótulo
  recalculado, e o teste mede o rótulo do produto, não o do insumo.
- Insumo sem GTIN não quebra nada — segue no caminho manual de hoje.
- A trava de "um insumo não declarado bloqueia tudo" **continua valendo**. Este
  WP facilita declarar; não afrouxa a regra.
