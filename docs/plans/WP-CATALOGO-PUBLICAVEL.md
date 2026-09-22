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
| **Fotos de demonstração (Unsplash)** | **59 produtos** — 13 deles no feed do Google |
| **Publicados sem descrição longa** | **42** |
| Publicados sem coleção primária | 0 ✔ |
| Preços em aberto | Coffee Cola, Queijo Vale do Testo |

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

Em uma linha: **72 dos 87 pares trocam, 15.786 linhas se mexem, 36 itens de feed
mudam de `g:id`, e 15 pares param** — porque uma decisão de de-para de 19/08
envelheceu quando o catálogo separou os produtos (os 12 chás Kãnfa creditados ao
`THL`, `BBB` ao pacote, `PHO` ao pacote, `CHAI_A` a produto nenhum). Isso é
curadoria, não rename: o conserto é no Gestor, e o comando é idempotente.

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

### ⏳ F1b — as tabelas de código (falta)

671 literais no `seed.py`, 72 no `apply_product_brands.py`, 23 no
`rename_skus_to_real.py`, 10 no `measure_eat_in_weights.py`, 8 no
`apply_product_measurements.py`. **Fica para depois da palavra dele sobre a
tabela**: reescrever 671 literais contra um de-para que ele ainda pode editar é
retrabalho garantido. E precisa estar commitado **antes** do `--apply`, senão o
próximo `seed` nasce discordando do alpha.

## F2 — Fotos

59 produtos com foto de demonstração (Unsplash), 13 deles no feed do Google.
Foto de banco de imagem no feed é risco de reprovação no Merchant Center e,
pior, é promessa que a vitrine não honra. As fotos reais moram em
`img.nelsonboulangerie.com.br` (ver [[project_fotos_de_produto_moram_na_loja]]).

## F3 — Descrições

42 publicados sem descrição longa. A PDP e o JSON-LD usam a curta como
fallback, então ninguém "quebra" — só empobrece. Vale a régua de copy da casa
(`docs/reference/omotenashi-copy.md`): primeiro inequívoco, depois curto.

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
  `WP-VARIACAO-E-ADICIONAL.md`, `WP-VENDA-POR-PESO.md`.

## Regras desta frente

- O oráculo do que existe é o **catálogo vivo do alpha**, nunca o `seed.py`.
- Gravar no alpha pede a palavra do dono — ele a deu para marca/GTIN/fichas em
  22/09; **o rename precisa de palavra nova, depois do ensaio**.
- Nada de completar dado que ninguém confirmou: campo sem fonte fica vazio e
  vira pergunta na planilha.
