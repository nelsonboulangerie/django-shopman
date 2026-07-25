# Cardápio 2027 → Seed — Plano de Tradução (aprovado com emendas, 25/07)

> Fonte: **"🍞 Cardápio 2027 — Proposta Oficial (v2.0)"** (Notion, 25/07/2026).
> Backup do estado anterior: `~/.shopman/backups/seed-pre-cardapio-2027_2026-07-25.py` + `db-pre-cardapio-2027_2026-07-25.sqlite3`.
> Decisões do Pablo (25/07): Chocolate Quente sai · Água entra a 6,00 · Goûter fica pra depois
> (regra/combo, fora do catálogo) · Campagne único **redondo** · **preço maior vence em todos os
> conflitos** · Mini Croissant sai · Fendu/Tabatière/Mini Baguete/buns continuam à venda fora do
> menu (coleção `balcao`) · Croques 24/28/30 · Despensa: lista proposta abaixo, preços a cravar.
> Fotos: itens que continuam mantêm a foto real (`nb-catalog`); novos entram com Unsplash realista.

## 1 · Bebidas

| Item | SKU | Ação | Preço | Nota |
|---|---|---|---|---|
| Espresso | `ESPRESSO` | mantém | 8,00 | |
| Coado | `COADO` | 🆕 | 12,00 | |
| Cappuccino | `CAPPUCCINO` | mantém | 12,00 | |
| Mochaccino | `MOCHACCINO` | 🆕 | 12,00 | herda o chocolate da casa |
| Chá Camille | `CHA-CAMILLE` | 🆕 | 14,00 | descrições de 1 linha a definir com Pablo |
| Chá Rouge | `CHA-ROUGE` | 🆕 | 14,00 | |
| Chá Sophie | `CHA-SOPHIE` | 🆕 | 14,00 | |
| Chá Bleu | `CHA-BLEU` | 🆕 | 14,00 | |
| Chá Gelado do dia | `CHA-GELADO-DIA` | 🆕 rotativo | 14,00 | |
| Coffee Float | `COFFEE-FLOAT` | 🆕 | 18,00 | com sorvete |
| Frappé | `FRAPPE` | 🆕 | 18,00 | café, chocolate ou frutas vermelhas |
| Cream Soda do dia | `CREAM-SODA-DIA` | 🆕 rotativo | 21,00 | torneira |
| Soda de Laranja | `SODA-LARANJA` | 🆕 | 14,00 | torneira |
| Água | `AGUA` | 🆕 | 6,00 | decisão 25/07 |
| Saem | `ESPRESSO-DUPLO` `LATTE` `CHOCOLATE-QUENTE` `CHA-EARL-GREY` `SUCO-LARANJA` | | | |

Goûter (16h–18h): **fora deste seed** — vira regra/combo (RuleConfig/Promotion) em passo próprio.

## 2 · Padaria

### Rústicos

| Item | SKU | Ação | Preço | Nota |
|---|---|---|---|---|
| Baguette de Tradition | `BAGUETE` | renomeia | 13→16 | ex-Baguete Francesa |
| Pain de Campagne | `CAMPAGNE` | funde | 22,00 | **redondo**; saem OVAL/REDONDO como SKUs |
| Passas & Castanhas | `CAMPAGNE-PASSAS` | mantém preço | **33,00** | maior vence |
| Ciabatta | `CIABATTA` | reprecifica | 14→18 | `ITALIANO-RUSTICO` sai |
| Baguete Gergelim | `BAGUETE-GERGELIM` | mantém preço | **18,00** | maior vence |
| Focaccia do dia | `FOCACCIA-DIA` | 🆕 rotativo | 18,00 | substitui 3 focaccias + 3 minis |
| Saem | `BATARD` `ITALIANO-RUSTICO` `CAMPAGNE-OVAL` `PAO-FORMA` `CHALLAH` `BRIOCHE` (Nanterre) + focaccias fixas | | | |

### Finos

| Item | SKU | Ação | Preço | Nota |
|---|---|---|---|---|
| Croissant | `CROISSANT` | renomeia | 13,00 | ex-Croissant Tradicional |
| Pain au Chocolat | `PAIN-CHOCOLAT` | mantém preço | **15,00** | maior vence |
| Folhado do dia | `FOLHADO-DIA` | 🆕 rotativo | 13,00 | rotação: Chausson/Bichon/Raisins… |
| Shokupan | `SHOKUPAN` | 🆕 | 28,00 | |
| Kuro Pan | `KURO-PAN` | 🆕 | 22,00 | |
| Melonpan | `MELON-PAN` | reprecifica | 11→12 | |
| Animalzinho | `ANIMALZINHO` | 🆕 rotativo | 10,00 | bicho do dia |
| Cornet | `CORNET` | funde | 12,00 | `CORNET-CHOCOLATE` sai; recheio do dia |
| Saem | `MINI-CROISSANT` `BRIOCHE-CHOCOLAT` `CHAUSSON` `BICHON` `PAIN-RAISINS` (fixos → rotação) | | | |

### Salgados

| Item | SKU | Ação | Preço | Nota |
|---|---|---|---|---|
| Croque Monsieur | `CROQUE-MONSIEUR` | mantém | 24,00 | |
| Croque Madame | `CROQUE-MADAME` | mantém | 28,00 | |
| Croque Complet | `CROQUE-COMPLET` | 🆕 | 30,00 | |
| Queijo-Quente | `QUEIJO-QUENTE` | 🆕 | 26,00 | no Shokupan |
| Jambon-Beurre | `JAMBON-BEURRE` | 🆕 | 18,00 | |
| Salgado do dia | `SALGADO-DIA` | 🆕 rotativo | 14,00 | deli/hotdog; reancoragem deliberada (v1.1) |
| Pain Grillé | `PAIN-GRILLE` | 🆕 | 16,00 | o pão na chapa |
| Tábua de Iguarias da Casa | `TABUA-IGUARIAS` | 🆕 | 58,00 | charcutaria, queijos, patês |
| Saem | `DELI` `HOTDOG` `QUICHE-LORRAINE` `QUICHE-LEGUMES` `TARTINE-SAUMON` `TARTINE-TOMATE` | | | |

### Doces

| Item | SKU | Ação | Preço | Nota |
|---|---|---|---|---|
| Pain Perdu | `PAIN-PERDU` | 🆕 | 18,00 | |
| Melon Iced Sando | `MELON-ICED-SANDO` | 🆕 | 22,00 | |
| Madeleine | `MADELEINE` | mantém | 6,00 | |
| Purin à la Mode | `PURIN` | 🆕 | 20,00 | |
| Tea Jelly | `TEA-JELLY` | 🆕 | 18,00 | |

### Balcão (à venda, fora do menu impresso — coleção `balcao`, nenhum feed consome)

| Item | SKU | Preço | Nota |
|---|---|---|---|
| Fendu | `FENDU` | 6,00 | decisão 25/07 |
| Tabatière | `TABATIERE` | 6,00 | |
| Mini Baguete (lanche) | `MINI-BAGUETE` | 9,00 | |
| Pão de Hambúrguer (rústico) | `PAO-HAMBURGER` | 6,00 | |
| Brioche Burger Bun (pc. 2un.) | `BRIOCHE-BURGER` | 16,00 | |
| Pão para Hot Dog (pc. 4un.) | `PAO-HOTDOG` | 28,00 | |

### Despensa — proposta (preços PLACEHOLDER, a cravar pelo Pablo)

| Item | SKU | Preço proposto |
|---|---|---|
| Mostarda da Casa (pote) | `MOSTARDA-CASA` | 18,00 |
| Bacon da Casa (peça) | `BACON-CASA` | 22,00 |
| Tapenade (pote) | `TAPENADE` | 24,00 |
| Patê de Ratatouille (pote) | `PATE-RATATOUILLE` | 24,00 |
| Cornichons (vidro) | `CORNICHONS` | 28,00 |
| Geleia St. Dalfour (mini) | `GELEIA-MINI` | 16,00 |
| Camembert | `QUEIJO-CAMEMBERT` | 38,00 |
| Queijo Pomerode (local) | `QUEIJO-POMERODE` | 32,00 |
| Café em Grão (250g) | `CAFE-GRAO` | 42,00 |
| Chá da Casa (lata p/ levar) | `CHA-LATA` | 40,00 |
| Lata Nelson (presente) | `LATA-NELSON` | 89,00 |

Seedados com `metadata.price_tbd=true` até a lista real; corrigir é trocar números numa tabela só.

## Coleções

`bebidas-quentes` · `bebidas-geladas` · `torneira` · `rusticos` · `finos` · `salgados` · `doces` · `despensa` · `balcao`

Feeds: **TV do Café** → bebidas-quentes, bebidas-geladas, torneira, doces · **TV do Salão** →
rusticos, finos, salgados · **Google/Meta** → rusticos, finos, salgados, doces. `balcao` e
`despensa` fora dos feeds (despensa pode entrar depois, é decisão de merchandising).

## Modelo dos "do dia"

1 SKU fixo por vaga; sabor/bicho do dia é operação, não SKU. Vagas: `FOCACCIA-DIA`,
`FOLHADO-DIA`, `SALGADO-DIA`, `CHA-GELADO-DIA`, `CREAM-SODA-DIA`, `ANIMALZINHO`.

## Contagem final

Menu: 42 SKUs (14 bebidas + 28 comida) · Balcão: 6 · Despensa: 11 → **59 SKUs** (eram 50).
Efeitos colaterais a cuidar no seed: pedidos históricos, receitas/produção (Craftsman),
estoque/insumos (Stockman/Buyman), favoritos e POS tabs referenciam SKUs — atualizar juntos.
