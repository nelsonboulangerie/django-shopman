# SKU-REAL-PLAN — trocar os SKUs inventados pelos códigos que a casa usa

> **Mandato (18/08/2026):** *"os SKUs antigos são os corretos. os novos são
> inventados pela IA, nada a ver."*
>
> Os identificadores do cardápio 2027 (`CROISSANT`, `ESPRESSO`, `PAO-FRANCES`)
> nasceram de geração automática. Os códigos reais da casa são os do Yooga —
> `CT`, `MD`, `PC`, `CI` —, usados por dois anos em 353.009 linhas de venda.
>
> **Este plano NÃO desbloqueia o B.I.** O modo de consumo já funciona sem ele,
> porque passou a classificar pela **categoria** da linha. Isto aqui é sobre
> identidade do catálogo, e é uma frente própria.

---

## 1. Por que isto não é um rename

`Product.sku` é **exceção deliberada** à convenção `ref` (CLAUDE.md), e por
isso ele não está no registro do pacote `refs` — que, ironicamente, já tem
`RefBulk.cascade_rename` com auditoria, transação e `select_for_update`. A
primeira decisão do plano é justamente essa: **o SKU entra no registro de refs,
ou ganha migração própria?**

O que faz a pergunta ser séria é o alcance. Levantado no código (18/08):

### 1.1 Campos de model que guardam SKU como texto (12)

| Onde | Campo | Natureza |
|---|---|---|
| `offerman.Product` | `sku` (unique) | **a fonte** |
| `orderman.OrderItem` | `sku` | histórico de venda |
| `craftsman.WorkOrder` | `output_sku` | fornada |
| `stockman.Quant` | `sku` (indexado) | saldo vivo |
| `stockman.Batch` | `sku` | lote/validade |
| `stockman.StockAlert` | `sku` | configuração |
| `backstage.ProductConsumptionTag` | `sku` (unique) | curadoria de consumo |
| `backstage.HistoricalSaleItem` | `sku` | histórico externo |
| `backstage.ShelfOutage` | `sku` | medição de falta |
| `shop.CatalogSync` | `sku` + `channel_ref` | **espelho de canal externo (iFood)** |
| `storefront.CustomerFavorite` | `sku` | dado de cliente |
| `storefront.StockAlertSubscription` | `sku` | dado de cliente |

### 1.2 JSON que carrega SKU (não migra com `UPDATE`)

- `Session.items[].sku` — carrinho/comanda em aberto
- **`Order.snapshot`** — ⚠️ está em `Order.SEALED_FIELDS`
- `DayClosing.data.items[]` — a contagem do fechamento
- `Move.reason` — o vínculo com a fornada sai por regex

### 1.3 O que trava o caminho óbvio

**`Order.snapshot` é selado e o `Move` é ledger imutável.** Reescrevê-los para
"arrumar" o SKU destruiria a garantia que os dois existem para dar: o pedido é
o registro do que foi combinado, e o ledger é a trilha do que aconteceu. Um
pedido de março não foi feito com o SKU `CT` — foi feito com `CROISSANT`, e
essa é a verdade daquele documento.

⚠️ **E há um canal externo no meio:** `CatalogSync` espelha o que o iFood
conhece. Trocar SKU sem sincronizar lá quebra o vínculo com pedidos de fora, que
não obedecem à nossa migração.

---

## 2. Três estratégias, e a que eu recomendo

### A. Renomear tudo (UPDATE em todas as tabelas)
Simples de escrever, e **errada**: reescreve documento selado e ledger. Só seria
defensável em ambiente sem história — e a casa já tem história.

### B. Apelido (`legacy_sku` / tabela de alias), mantendo o SKU atual
Barata e reversível, mas **não entrega o pedido**: o identificador do produto
continua sendo o inventado. Vira dívida documentada em vez de resolvida.

### C. ⭐ Corte com tradução registrada — **recomendada**

O `Product.sku` passa a ser o código real. Divide-se o mundo em dois:

- **O que é estado vivo, migra:** `Quant`, `Batch`, `StockAlert`,
  `ProductConsumptionTag`, `CustomerFavorite`, `StockAlertSubscription`,
  `CatalogSync`, `WorkOrder` em aberto, `Session` em aberto.
- **O que é registro do passado, NÃO se toca:** `OrderItem`, `Order.snapshot`,
  `Move`, `DayClosing.data`, `HistoricalSaleItem`.
- **E uma tabela de tradução guarda o par** (`sku_antigo`, `sku_novo`, data,
  autor). Toda leitura que atravessa a fronteira traduz; quem lê só o presente
  ignora.

É o mesmo princípio que a casa já aplicou em outros lugares: **o passado é
coberto de forma declarada, não reescrito**. E a tradução tem dono único, em vez
de cada leitura inventando seu de-para.

---

## 3. Fases

**F0 — Medir.** Contar linhas por tabela afetada em produção antes de qualquer
coisa. O plano cita 353.009 linhas históricas; o estado vivo é o que decide o
tamanho da janela.

**F1 — O mapa.** `docs/plans/sku-real-mapa.csv` tem os 143 SKUs reais por
volume, com palpite de correspondência para 56 deles (58% das linhas). ✅ As
correspondências mostradas foram **confirmadas pelo dono (18/08)**. Faltam os
87 sem palpite — produto que saiu do cardápio ou mudou de nome.

**F2 — Decidir o mecanismo.** SKU entra no registro do `refs` (e herda
`cascade_rename`, auditoria e o Admin que já existe), ou ganha comando próprio?
Entrar no `refs` é reaproveitar o que a casa construiu; a ressalva é que o SKU
é exceção à convenção **por design**, e registrar pode confundir as duas coisas.

**F3 — Executar por produto, não em lote.** Um SKU por vez, com verificação
entre eles. Trocar 143 de uma vez transforma qualquer erro numa restauração de
banco.

**F4 — O canal externo.** Ressincronizar o catálogo do iFood e conferir
`CatalogSync` antes de considerar concluído.

---

## 4. O que NÃO fazer

- **Não reescrever `Order.snapshot` nem `Move`.** Se a conclusão for que
  precisam mudar, o plano está errado, não os models.
- **Não fazer junto com outra mudança de catálogo.** Se algo quebrar, tem de
  ficar óbvio o que foi.
- **Não confiar no palpite de nome.** Foi assim que o "Hambúrguer 100g" quase
  virou lanche. O CSV é para conferir, não para aplicar.
- **Não rodar antes do go-live formal sem decidir o corte.** Pré-go-live a casa
  zera resíduo de rename (CLAUDE.md); pós-go-live vale expand-contract
  ([ADR-015](../decisions/adr-015-backward-compat-policy-post-prod.md)). Qual
  regime vale aqui muda o plano inteiro.

---

## 5. Perguntas ao dono

1. **Antes ou depois do go-live?** É a pergunta que ordena todas as outras.
   Antes, o corte é barato e o passado é pequeno. Depois, cada pedido histórico
   vira registro que precisa de tradução.
2. **Os 87 sem correspondência:** produto extinto (não precisa de SKU novo) ou
   produto atual com nome mudado (precisa)?
3. **O sentido da troca:** o cardápio 2027 adota os códigos do Yooga, ou a casa
   aproveita para desenhar uma numeração nova e consciente? "Trocar inventado
   por real" e "trocar inventado por bem-desenhado" são projetos diferentes.
