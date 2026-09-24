# WP — Catálogo publicável no go-live

> Pedido do dono em 22/09/2026: *"precisamos revisar as imagens, descrições,
> coleções e tudo mais que estiver faltando. O catálogo precisa estar funcional
> e publicável em go-live!"* — e, na sequência, *"pode prosseguir. delegue para
> um WP exclusivo e dedicado"*.
>
> Este WP é o dono desta frente. A sessão que o abriu estava no limite de
> contexto; tudo que ela sabia está escrito aqui.

## Onde o catálogo está (medido no alpha em 22/09/2026)

| | |
|---|---|
| Produtos | 111 no banco · **183 linhas** na planilha de curadoria (inclui os que vão nascer) |
| Marca declarada | **103** — gravado hoje; o feed e a PDP já publicam |
| GTIN | 7 gravados (+3 quando o #966 mergear) |
| Marcados como revenda | 15 |
| **Fotos de demonstração (Unsplash)** | **59 produtos** — 13 em coleção de feed, 8 depois da curadoria |
| **Descrição longa** | **vazia nos 111** (42 deles publicados) |
| Publicados sem coleção primária | 0 ✔ |
| Preços em aberto | Coffee Cola, Queijo Vale do Testo |

> **Atualizada em 22/09 pelo ensaio:** a planilha ganhou a aba **`Pendências
> 22-09`** (o que depende dele, uma coluna amarela por linha, já com o valor de
> hoje dentro) e **8 linhas novas no fim de `Produtos`** — `BK`, `CV`, `CX`,
> `GR`, `LN`, `MT`, `QP`, `THL`, que estão no alpha e nunca tiveram linha.

A planilha de curadoria é a fonte da decisão, e está aqui:
**[Catálogo Nelson — consolidado](https://docs.google.com/spreadsheets/d/1wXoIxaYFiEn1hj2k2mEH0NrOP3b1-sTnbspakD_YhKA/edit)**
(abas `Produtos`, `Proposta SKU da casa`, `Insumos`, `Leia-me`). O dono já a
revisou duas vezes; as colunas amarelas são as dele.

## F1 — Renomear os SKUs (a fatia delicada, faça primeiro)

As três convenções estão fechadas com ele:

| Onde | Padrão | Exemplo |
|---|---|---|
| Casa | código curto, família no começo | `CAP2X`, `TRADI`, `FOAM`, `CROPQ` |
| Revenda | `TIPO-VARIANTE-MARCA-EMBALAGEM` | `GELEIA-FIGO-STDALFOUR-284` |
| Insumo | `TIPO-VARIANTE(-MARCA)` | `FARINHA-T65`, `MOSTARDA-DIJON` |

São **114 SKUs da casa e 62 de revenda**, já preenchidos na planilha. O que
torna isto delicado, e que **precisa estar no ensaio antes de gravar**:

1. **82 SKUs têm série de B.I.** (`HistoricalSaleItem` casa por SKU). Trocar
   sem `ProductAlias` quebra a série — e quebra em silêncio, que é pior.
2. **O SKU está na URL da PDP** (`/produto/<sku>`) **e no `g:id` do feed**.
   Trocar antes do go-live é barato; depois custa reindexação e redirect.
3. **O SKU está em tabela de código**: `config/management/commands/seed.py`,
   `apply_product_brands.py` (`HOUSE_SKUS`/`RESALE`), `docs/plans/sku-real-mapa.csv`,
   coleções, catálogo do iFood.
4. **Fichas apontam para SKU** (`crafting_recipe.output_sku`, `input_sku`) —
   renomear produto sem arrastar ficha deixa receita órfã.
5. O namespace é compartilhado com insumo (`shop/services/sku_namespace.py`):
   colisão é recusada, e o ensaio tem de provar que não há nenhuma.

**Forma sugerida:** um comando idempotente com ensaio por padrão e `--apply`,
no mesmo molde do `apply_product_brands` — tabela versionada, relatório do que
mudaria, alias criado junto, e recusa fechada em colisão.

### ✅ F1a — o comando e o ensaio (feito, 22/09)

`config/management/commands/apply_product_skus.py`, com ensaio por padrão
(executa e desfaz) e `--apply`. O ensaio rodou contra uma **cópia** do banco
vivo — não contra ele — e o laudo inteiro está em
[`docs/reports/2026-09-22-ensaio-rename-sku-catalogo.md`](../reports/2026-09-22-ensaio-rename-sku-catalogo.md).

Em uma linha: **os 86 pares trocam, ~16 mil linhas se mexem e 36 itens de feed
mudam de `g:id`**. Os 15 que paravam — porque uma decisão de de-para de 19/08
envelheceu quando o catálogo separou os produtos (os 12 chás Kãnfa creditados ao
`THL`, `BBB` ao pacote, `PHO` ao pacote, `CHAI_A` a produto nenhum). Isso era
curadoria, não rename — e foi resolvido em 22/09 com a palavra dele, pelo
`repoint_product_aliases`: **17.320 linhas de venda voltaram ao produto certo**.

Três coisas que o WP não previa e o ensaio achou:

1. `ProductConsumptionTag.sku` é **único**, e o alpha guarda etiqueta dos dois
   códigos (`FE` e `FENDU`): o cascade estourava a constraint no meio da
   travessia. Voltou a política por model do `rename_skus_to_real`.
2. O SKU também mora em **JSON fora do cascade** — payload de evento, snapshot
   de pedido, `content` de anúncio. História fica; estado vivo pede janela (há
   dois anúncios em `pending_review` com link para `/produto/BE`).
3. `ifood_retract_renamed_skus` lia **um mapa só**, e as levas se encadeiam
   (`BAGUETE → BF → TRADI`) e chegam a voltar (`FENDU → FE → FENDU`). Passou a
   ler os dois e a resolver a cadeia contra o catálogo vivo.

### ✅ F1b — as tabelas de código (feito, 22/09)

**846 literais** trocados: `seed.py` (742), `apply_product_brands.py` (86),
`measure_eat_in_weights.py` (10), `apply_product_measurements.py` (8), mais os
testes que liam o código antigo. O `rename_skus_to_real.py` **não** foi tocado:
é a história de um rename já executado, e reescrevê-lo falsificaria o registro
e quebraria a cadeia que o iFood segue.

Duas armadilhas que a varredura cega teria levado junto:

- **O Paraná não é o Pain aux Raisins.** Dez linhas de `state_code: "PR"` no
  seed, fora por exclusão explícita. (E o `fiscal_focusnfe.py`, que é só uma
  lista de UF, nem entrou na varredura.)
- **A herança do "M" do Yooga quebraria calada.** O `measure_eat_in_weights` dá
  à variante de metade do preço o peso do pai pela convenção `MCT` → `CT`, e o
  pai já trocou de código duas vezes: sem traduzir, as **41 variantes** cairiam
  no piso do papel sem erro nenhum. A resolução da cadeia virou função
  compartilhada (`apply_product_skus.codigo_de_hoje`), usada também pelo iFood.

E uma regra que mudou de dono: `test_seed_catalog_coerente` cobrava "SKU com
hífen é inventado pela geração automática" — verdade até 22/09, quando os com
hífen eram os nomes do cardápio 2027. Agora **o hífen é da revenda**, e o teste
cobra a forma (`TIPO-VARIANTE-MARCA-EMBALAGEM`, terminando na embalagem), com um
irmão novo que cobra os 5 caracteres da regra da casa.

### ⏳ O que falta em F1

O **`apply_product_skus --apply` no alpha**, que pede a palavra do dono. Com a
F1b no `main`, o `seed` e o banco passam a dizer a mesma coisa, que era a
pré-condição.

## F2 — Fotos: **o dono desta fatia é outro WP**

As fotos ganharam WP próprio no mesmo dia — [`WP-FOTOS-DA-CASA.md`](WP-FOTOS-DA-CASA.md),
PR #975, já no `main` — com a ilustração por coleção, a fila do que falta
ordenada pelo que mais vende e a cobrança diária. **Este WP não mexe em foto**;
o que segue são os dois fatos que a medição do rename acrescentou:

- **O acervo não tem foto real de nenhum dos 59.** `pablondrina/nb-catalog` tem
  57 fotos; as 51 que servem já estão wiradas, e o que sobra (`cca`, `cgo`,
  `coc`, `pc3`, `sa`) é de outro produto. Não há nada a "ligar": os 59 são
  sessão de fotos, não trabalho de cadastro.
- **Dos 13 no feed, 5 saem por curadoria** — `PG`, `PU`, `TJ`, `TI` (excluir) e
  `MS` (despublicar). Sobram **8**: `CCOM`, `CMA`, `CMO`, `JB`, `PPU`, `PI`,
  `PI4`, `QQ`. É a esses 8 que a marca automática da F1 daquele WP precisa
  chegar antes do go-live.

## F3 — Descrições (medido em 22/09: o campo nunca foi usado)

O WP dizia "42 publicados sem descrição longa". Medido no alpha: **`long_description`
está vazia nos 111 produtos** — 42 é só a parte que está publicada. O campo nunca
foi usado.

E a PDP **já mostra** a descrição curta, o `ingredients_text` (que inclui a
declaração de alérgenos), a dica de conservação e a tabela nutricional; o
`long_description` só rende um segundo parágrafo, e o JSON-LD e o feed caem na
curta. Então a longa não "conserta" nada: ela só vale se disser o que os outros
campos não dizem — de onde vem a farinha, quanto tempo fermenta, o que tem no
blend.

**Isso é conhecimento da casa, não derivação.** Escrever prosa em cima do que já
está declarado seria a defeito "prolixo" de
[`omotenashi-copy.md`](../reference/omotenashi-copy.md); inventar o resto seria
prometer pela casa. A pergunta está na planilha, com a proposta de eu redigir a
partir do cadastro e ele corrigir.

## F4 — O que a planilha já decidiu e ainda não foi aplicado

- **Nomes**: os que o dono corrigiu (ex.: Shokupan → Forma Artesanal,
  Animalzinho → Coelhinho de Chocolate, as latas Kãnfa de 60 g → 70 g).
- **Situação**: 7 produtos para **excluir**, 3 para **despublicar** (Mini
  Baguete fica só para a encomenda do restaurante), 1 vira **adicional**
  (Chantilly), 3 **a decidir** (os chás que esperam o WP de variação).
- **Fiscal**: 14 bebidas preparadas com NCM proposto (café 21011200, chá
  21012010, soda 22021000) — ⚠️ **marcado como proposta, a confirmar com o
  contador**, junto com os códigos tPag da NFC-e que já estavam pendentes.
- **Insumos**: 8 renomeações, a `AGUA` órfã para apagar, `TONICA-ANTARCTICA`,
  `MOSTARDA-DIJON` (Beaufor, balde 1 kg) no lugar do `MT` — que é SKU de um
  produto e está numa ficha. Detalhe em `WP-INSUMOS-SEM-FRICCAO.md`.

## O que já foi feito (não refazer)

- Marca, GTIN e marca de revenda **gravados no alpha** em 22/09; feed com
  `g:brand` nos 48 itens e PDP com `brand` no JSON-LD, conferidos no ar.
- Seis fichas com massa errada corrigidas no alpha e no seed (PR #971), com
  teste que trava a massa de cada peça.
- Compras passou a receber **mercadoria de revenda** (PR #964) e o PDV a achar
  produto pelo **código de barras** (PR #970).
- **F1a**: o comando do rename e o ensaio medido (ver acima).
- Planos irmãos: `WP-RECEITAS-DA-CASA.md`, `WP-INSUMOS-SEM-FRICCAO.md`,
  `WP-VARIACAO-E-ADICIONAL.md`, `WP-VENDA-POR-PESO.md` e — desde 22/09, dono da
  antiga F2 — `WP-FOTOS-DA-CASA.md`.

## Regras desta frente

- O oráculo do que existe é o **catálogo vivo do alpha**, nunca o `seed.py`.
- Gravar no alpha pede a palavra do dono — ele a deu para marca/GTIN/fichas em
  22/09; **o rename precisa de palavra nova, depois do ensaio**.
- Nada de completar dado que ninguém confirmou: campo sem fonte fica vazio e
  vira pergunta na planilha.
