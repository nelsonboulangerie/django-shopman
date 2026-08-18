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
>
> ⚠️ **REVISÃO (18/08, tarde):** a primeira versão deste plano superestimou o
> problema. O dono contestou — *"o passado não seria mudado, apenas os registros
> atuais, basicamente todos com fonte no seed"* — e a medição deu razão a ele.
> Ver §1.4. A estratégia recomendada mudou de C para **A**.

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

### 1.3 O que PARECIA travar o caminho óbvio

**`Order.snapshot` é selado e o `Move` é ledger imutável.** Reescrevê-los para
"arrumar" o SKU destruiria a garantia que os dois existem para dar: o pedido é
o registro do que foi combinado, e o ledger é a trilha do que aconteceu. Um
pedido de março não foi feito com o SKU `CT` — foi feito com `CROISSANT`, e
essa é a verdade daquele documento.

⚠️ **E há um canal externo no meio:** `CatalogSync` espelha o que o iFood
conhece. Trocar SKU sem sincronizar lá quebra o vínculo com pedidos de fora, que
não obedecem à nossa migração. **Este ponto sobrevive à revisão** — é o único
que não é descartável.

### 1.4 ⭐ A medição que derruba o parágrafo acima

Medido em produção (18/08):

| O que | Quanto | Natureza |
|---|---|---|
| Pedidos nativos | **216** (11/07 a 18/08) | seed, QA e piloto automático |
| Movimentos de estoque | **322** | 77 "Estoque inicial seed", 245 "Produção planejada: WO-…" |
| Venda real no ledger | **nenhuma** | a casa ainda não vendeu pelo Shopman |
| SKU no `HistoricalSaleItem` | `ANC`, `BA`, `BBB`, `MD`, `CT`… | **já são os códigos reais** |

Duas conclusões, e as duas mudam o plano:

1. **O passado nativo é ficção.** O `Order.snapshot` selado e o `Move` imutável
   continuam existindo como mecanismo, mas o que eles guardam hoje é dado de
   demonstração. Defender a integridade de 216 pedidos falsos não é rigor, é
   cerimônia.
2. **O passado real já está do lado certo.** O histórico do Yooga guarda os
   códigos verdadeiros. A tabela de tradução que a versão anterior propunha
   atravessava uma fronteira que **não existe**.

⚠️ **Isto vale HOJE, e é perecível.** No dia em que a casa vender pelo Shopman,
o passado nativo deixa de ser descartável e a estratégia C volta a ser a certa —
mais cara. **A janela barata é agora.**

---

## 2. Três estratégias, e a que eu recomendo

### A. ⭐ Renomear direto — **recomendada, enquanto a janela existe**

`Product.sku` recebe o código real, e as 12 tabelas acompanham com `UPDATE`. Os
216 pedidos e os 322 movimentos são de seed: podem ser migrados junto (barato) ou
simplesmente descartados num reseed do lado nativo.

Era a opção que a primeira versão deste plano descartou como "errada por
reescrever documento selado". O erro do argumento foi tratar dado de
demonstração como se fosse registro histórico. **Não há história nativa para
proteger.**

### B. Apelido (`legacy_sku` / tabela de alias)
Barata e reversível, mas **não entrega o pedido**: o identificador do produto
continua sendo o inventado. Vira dívida documentada em vez de resolvida.

### C. Corte com tradução registrada
Era a recomendação da primeira versão. **Continua correta — para depois do
go-live.** Se a troca não acontecer antes de a casa vender pelo Shopman, é para
cá que o plano volta: o estado vivo migra, o registro do passado fica, e uma
tabela guarda o par. Mais caro, e desnecessário hoje.

## 3. Fases

**F1 — O mapa.** `sku-real-mapa.csv` tem os 143 SKUs reais por volume, com
palpite para 56 deles. ✅ Correspondências **confirmadas pelo dono (18/08)**.
Faltam os 87 sem palpite (§5.2).

**F2 — Decidir o mecanismo.** SKU entra no registro do `refs` — herdando
`RefBulk.cascade_rename`, auditoria e o Admin que já existem — ou ganha comando
próprio? Entrar reaproveita o que a casa construiu; a ressalva é que o SKU é
exceção à convenção **por design**, e registrar pode confundir as duas coisas.

**F3 — Executar por produto, com ensaio.** Um comando idempotente, com
`--dry-run` que **executa e desfaz** (o padrão que o `apply_catalog_taxonomy` já
usa). Um SKU por vez, verificando entre eles.

**F4 — O canal externo.** Ressincronizar o catálogo do iFood e conferir
`CatalogSync`. É o único ponto que a revisão do §1.4 **não** tornou barato.

**F5 — O lado nativo.** Decidir entre migrar os 216 pedidos junto ou reseedar.
Migrar é honesto e barato; reseedar é mais limpo. Nenhum dos dois é urgente.

## 4. O que NÃO fazer

- **Não tratar dado de seed como se fosse história.** Foi o erro da primeira
  versão deste plano, e ele custou uma estratégia inteira. Antes de proteger um
  registro, pergunte de onde ele veio.
- **Não adiar.** A janela barata existe porque a casa ainda não vendeu pelo
  Shopman. Ela fecha sozinha, sem aviso, no primeiro pedido real.
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

1. ✅ **Antes ou depois do go-live?** Respondida pela medição do §1.4: **antes**,
   e quanto antes melhor. Depois, cada pedido real vira registro que precisa de
   tradução, e a estratégia C volta.
2. **Os 87 sem correspondência:** produto extinto (não precisa de SKU novo) ou
   produto atual com nome mudado (precisa)?
3. **O sentido da troca:** o cardápio 2027 adota os códigos do Yooga, ou a casa
   aproveita para desenhar uma numeração nova e consciente? "Trocar inventado
   por real" e "trocar inventado por bem-desenhado" são projetos diferentes.
