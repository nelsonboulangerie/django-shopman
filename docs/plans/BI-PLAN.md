# BI-PLAN — B.I. cross-suite no backstage

> **Status:** 🟢 Iterado com o dono (2026-08-14): superfície = **app Nuxt próprio**;
> Yooga **entra** (fonte externa first-class, ingestão completável); gráficos **liberados**
> ("lindões e super úteis", nunca decorativos). Pendências de semântica do timer anotadas no
> §9 para a frente de produção. Aguardando OK final para iniciar a execução (F1).
> **Mandato (Pablo, 2026-08-14):** "planejar e executar um app de B.I. no backstage…
> Chegou a hora e esse ponto do timer deve ser resolvido também. O B.I. é algo cross-suite!"
> **Reversão de doutrina:** este plano acompanha a minuta da
> [ADR-021](../decisions/adr-021-bi-cross-suite-read-layer.md), que reverte formalmente
> ADR-017 §8, HARDENING-PLAN §9 e QC-FORNADA §7 (a doutrina anti-BI).
> **Base assumida:** a fila de PRs empilhados #146 (C2 gate por canal), #148 (C3 FEFO),
> #149 (C4 write-off no fechamento) e o C6 (remoção do D-1) — as chaves
> `nonconformity_writeoffs`/`perda_vencido`/`perda_nao_conformidade` em `DayClosing.data`
> **ainda não existem no código desta branch**; chegam com esses PRs. Rebase quando mergearem.

---

## 1. O que o B.I. é — e o que ele não é

**É** a camada de leitura **analítica** cross-suite: tendência, comparação, série histórica,
distribuição. Responde "o forno 2 está queimando mais que o 1 este mês?", "qual o ticket médio
de sábado vs terça?", "quanto perdemos por `overbaked` por receita?".

**Não é** substituto das projections **operacionais** (`build_production_dashboard`,
`build_qc_kiosk`, X/Z de caixa, fila de pedidos), que respondem perguntas do turno e ficam
onde estão. Também não é um segundo dono de fato nenhum: a ADR-011 segue integral — todo
número do B.I. é derivado de ledger/consolidação existente e recomputável do zero (invariantes
na ADR-021).

## 2. Fontes de fato (inventário verificado no código)

| Fonte | Dá ao B.I. | Observações |
|---|---|---|
| `craftsman.WorkOrderEvent` | ledger de produção; `finished.payload` traz `finished_qty/planned_qty/started_qty/loss_qty` + `partition` | sem índice em `created_at`/`kind` (só `unique(work_order, seq)`) |
| `craftsman.WorkOrderItem` | linhas OUTPUT/WASTE com `quality_grade_ref/quality_defect_ref/batch_ref` | já indexado `(grade, recorded_at)` e `(defect, recorded_at)` — pronto para GROUP BY analítico |
| `craftsman.WorkOrder` | `quantity/finished/loss/yield_rate`, `started_at/finished_at`, `position_ref/operator_ref`, `target_date` | `started_qty` lê evento (N+1 em loop — evitar em agregação) |
| `stockman.Move` (+ `Quant`) | WASTE/SELL/MAKE por tempo; write-offs por prefixo de `reason` | fatia por SKU/posição exige join via `Quant` |
| `stockman.Batch` | validade + não conformidade congelada | |
| `orderman.Order`/`OrderItem` | vendas: `total_q`, timestamps por status, `channel_ref`; descontos duráveis em `snapshot.pricing` e `OrderItem.meta._disc` | `OrderItem.sku` **sem índice**; `Order` sem índice composto por data |
| `backstage.CashShift`/`CashMovement` | contagem cega, `difference_q`, sangria/suprimento/ajuste | |
| `backstage.DayClosing.data` | consolidação diária: `items`, `production_summary` (com `quality` por grau), `pending_production`, `cash_shift_summary`, `reconciliation_errors` (+ `financial_reconciliation` quando rodado; + write-offs pós-C4) | contrato de leitura do B.I. → registrar consumo em `data-schemas.md` |
| `guestman.contrib.insights.CustomerInsight` | RFM, ticket médio, canais, churn — **precedente de agregado materializado da suite** | recálculo inline síncrono em `ensure_customer`; `recalculate_all()` existe mas não tem invocador agendado |
| **(novo, F1)** `backstage.OvenRun` | tempo real de forno | o único fato novo deste plano — §4 |

## 3. Arquitetura

### 3.1 Onde mora

Módulo do **backstage** (ADR-021 §2): `projections/bi_*.py` + `services/bi/` + `api/bi.py`
sob `/api/v1/backstage/bi/`, com permissão própria (`backstage.view_bi`, no molde de
`view_production_reports`). Sem package `shopman-bi`, sem 4º app Django.

### 3.2 Ler vs materializar

**Default: calcular na leitura** (volume real: ~100–150 vendas/dia, 5–15 fornadas/dia — os
índices existentes respondem em ms). **Série diária: ler `DayClosing.data`** (a consolidação
já existe). **Materializar só com gatilho medido** (ADR-021 §3: p95 > 2s ou varredura > 12
meses/request) — e aí como tabela derivada recomputável, recalculada por management command no
ciclo do `maintenance_worker` (300s; sem Celery, ADR-003 intacta). **Exceção estrutural:**
histórico externo (Yooga, §7) só existe materializado.

Índices novos em models core (`OrderItem.sku`, `Order(created_at, channel_ref)`) **não**
entram na v1: Core é Sagrado, e o volume não os exige ainda. Se um gatilho medido aparecer,
viram migração própria com justificativa no PR.

### 3.3 Contrato de superfície

Igual ao resto do backstage (ADR-012/014): dataclasses frozen pré-formatadas, `build_*` com
kwargs, serialização por `projection_data`, permissão na view. Se a superfície for Nuxt,
contrato TypeScript gerado (`export_*_schema` + teste de drift). Copy pt-BR na presentation;
dado puro na projection.

### 3.4 Tempo real

B.I. é leitura calma: **poll em cadência calma, sem SSE** — coerente com a decisão do
production-nuxt (WP-PE4: polling deliberado). ADR-016 manda push quando o estado importa na
tela *do turno*; um gráfico de tendência não é isso. Revisitar só se nascer um "painel de
parede" ao vivo.

## 4. Timer de forno → fato de servidor (âncora, F1–F2)

### 4.1 O contrato (definição benzida, 2026-08-13)

- **start** = armar o timer (enfornou) · **stop** = "Concluir" declarado no timer (retirou).
- Fim de timer sem resposta **não mede**. Confirmar do QC **não mede** (o QC segue dono do
  fato comercial: partição/lote).

### 4.2 Estado atual (verificado)

`useOvenTimers.ts` é 100% localStorage (`producao.oven-timers`), chave = `String(order.pk)`,
sem dimensão de forno. `arm()` e `concludeOven()` (expedite.vue) geram **zero tráfego de
servidor**. Timer expirado toca 4 vezes e some no GC de 2h. `WorkOrder.started_at` é outro
momento (o start da WO, não o enfornar) — não serve de proxy.

### 4.3 Modelo: `backstage.OvenRun`

Fato operacional da instância → model do backstage (precedente: `KDSTicket`), ligado por
string ref (ADR-004). **Nenhuma mudança em craftsman** — novos kinds em `WorkOrderEvent`
poriam vocabulário de padaria no core genérico (constituição §2.6); rejeitado na ADR-021 §4.

```python
class OvenRun(models.Model):
    work_order_ref = CharField(64, db_index=True)   # WorkOrder.ref (pk não carrega semântica)
    oven_ref       = CharField(64, blank=True)      # snapshot de WorkOrder.position_ref no arm
    operator_ref   = CharField(64, blank=True)
    planned_seconds = PositiveIntegerField()        # duração armada
    armed_at       = DateTimeField()                # enfornou
    concluded_at   = DateTimeField(null=True)       # retirou (só via Concluir declarado)
    status         = open | concluded | abandoned
    metadata       = JSONField(default=dict)
```

- Partial unique: **um run aberto por `work_order_ref`**. Re-armar com run aberto marca o
  anterior `abandoned` e abre novo (nova enfornada; o anterior não mede).
- `elapsed = concluded_at - armed_at`. Pausa/retomar/`+N` do countdown são UX local e **não
  afetam a medição** (o pão continuou no forno). Só o par armar→Concluir mede.
- Sweep no `maintenance_worker`: run `open` com `armed_at` mais velho que um teto (proposta:
  reusar `ProductionConfig.alerts.default_max_started_minutes`, hoje 240) vira `abandoned`.

### 4.4 API e cliente

- `POST /api/v1/backstage/production/<wo_id>/oven/arm/` `{planned_seconds, occurred_at?}` e
  `POST .../oven/conclude/` `{occurred_at?}` — perm `backstage.operate_production`, mesmo
  gate `_ProductionActionBase` dos writes de produção.
- `occurred_at` opcional (relógio do kiosk) para tolerar fila offline; o servidor aceita
  dentro de uma janela de sanidade (não-futuro, < 24h), senão carimba hora do servidor.
- No production-nuxt: `startOven()` passa a disparar o POST de arm; `concludeOven()` o de
  conclude — **best-effort com `retryWithBackoff` (operator-kit), nunca bloqueando o
  countdown local**. O localStorage continua sendo o mecanismo do countdown/alarme (offline
  first, "quem armou, ouve"); o servidor vira o dono do **fato**.
- Abrir o QC com timer tocando sem tocar Concluir limpa o timer local e **não** conclui o
  run (vira `abandoned` no sweep) — fiel à definição: sem resposta, sem medição.

### 4.5 Honestidade da métrica

Relatório de tempo de forno sempre exibe **cobertura** (% de fornadas do período com medição
armar→Concluir completa). Métrica sem denominador declarado mente por omissão
([health não alcança tudo](../../docs/constitution.md) §2.3 aplicado a métricas).

## 5. O que medir na v1

**Produção (âncora, F3):**
- Tempo real de forno: média/p50/p90 por receita e por forno (`oven_ref`), vs `planned_seconds`; cobertura da medição.
- Rendimento (`yield_rate`) por receita × período; perda absoluta e % por receita.
- Perdas por defeito (`quality_defect_ref`) × receita × forno × operador; partição por grau
  (a preço cheio / com desconto / perda) ao longo do tempo.
- Fonte: `WorkOrderItem` (índices prontos) + `WorkOrder` + `OvenRun`; série longa via
  `DayClosing.data.production_summary`.

**Vendas (F4):** faturamento/dia (`total_q` de orders completadas), ticket médio, pedidos por
hora × dia-da-semana, top SKUs (via `OrderItem`), mix por canal (`channel_ref`), descontos
concedidos (`snapshot.pricing`).

**Caixa (F4):** `difference_q` por turno/operador/terminal (tendência de quebra de caixa),
sangrias/suprimentos, mix de meios de pagamento (`payment_method_totals` do fechamento).

**Clientes (F4):** distribuição RFM (`CustomerInsight` — já materializado), novos vs
recorrentes por semana, churn-risk. Sem recálculo novo: o B.I. só lê o que o insight já tem.

**Write-offs (pós-C4, F4):** perda por vencimento vs não conformidade, por SKU, via
`DayClosing.data` + `Move.reason`.

## 6. Superfície — decidido: app Nuxt próprio (F5)

**Decisão do dono (2026-08-14): app Nuxt próprio.** O B.I. vira a terceira exceção explícita
ao Unfold Canonical Gate (ao lado de POS e Storefront) — registrada na ADR-021 §5.

Proposta de concretização: `surfaces/bi-nuxt` (:3007), extends operator-kit, mesmo padrão de
`marketing-nuxt`/`orders-nuxt` — BFF Nitro via `proxyDjangoApi`, `useOperatorLock` com a
permissão `backstage.view_bi`, contrato TypeScript gerado (`export_bi_schema` + teste de
drift), light-first (superfície de escritório), entrada na Central de Apps (hub-nuxt).

**Gráficos: liberados** — decisão do dono: "lindões e super úteis, só onde realmente fizer
sentido, não é decorativo". Regra de aplicação: um gráfico só existe quando responde a
pergunta melhor que uma tabela (tendência, distribuição, comparação); número pontual é tile,
lista é tabela. Neutros, cor só funcional (padrão dos apps de operador). A decisão "sem
gráficos" segue valendo nos relatórios operacionais do production-nuxt.

## 7. Histórico Yooga (F6 — confirmado no escopo)

Export existente: ~81k vendas autorizadas jul/24–jul/26, ~380k itens, consolidado no Drive
(`yooga-consolidado.xlsx`).

**Fonte externa é dimensão first-class, não cidadã de segunda.** O histórico entra em
tabelas próprias do B.I. (`HistoricalSale` + `HistoricalSaleItem`), com `source="yooga"`
carimbado em cada linha. Diferenças reais em relação ao dado nativo — e como aparecem:

- **Origem sempre visível na UI**: séries longas rotulam o trecho Yooga; nunca misturar
  Yooga e Shopman numa mesma barra sem rótulo.
- **Profundidade diferente**: o Yooga não tem produção/qualidade/caixa — só vendas. As telas
  de produção começam no Shopman; as de vendas ganham dois anos de passado.
- **Semântica diferente onde o dado antigo não é confiável**: mesa/balcão do Yooga nunca
  viram verdade de canal; a inferência comer-aqui-vs-levar usa a regra B (âncora de bebida),
  já decidida e documentada na memória do projeto.
- **Fora dos ledgers**: nada do Yooga entra em `Order`, `Move`, `DayClosing` ou relatórios
  operacionais. Só o B.I. lê.

**Ingestão completável por construção** (pergunta do dono, respondida por design): a chave
natural é o id da venda no Yooga, e a ingestão é **idempotente (upsert)**. Vendas e itens são
tabelas separadas; se hoje entrar só o cabeçalho do pedido e amanhã recuperarmos os itens (ou
detalhe por venda: endereço, desconto), a segunda carga preenche/enriquece as linhas
existentes sem duplicar nada. Como os agregados do B.I. são calculados na leitura (ou
recomputáveis), completar o dado corrige os números automaticamente — sem bagunçar nada.

## 8. O que NÃO entra na v1

- Warehouse externo, Metabase/Superset/etc., Celery/broker (thresholds da ADR-003 intactos).
- Tabelas de agregação especulativas (só com gatilho medido — ADR-021 §3).
- Índices novos em packages core.
- Previsão/forecast e recomendações (o `suggest_production` existente segue como está).
- SSE/painel ao vivo.
- Migrar relatórios operacionais existentes (`report_kind`, dashboard do Admin) para o B.I.
- Comparativo automático Yooga × Shopman por SKU (mapeamento de catálogo é trabalho próprio).

## 9. Decisões do dono (2026-08-14) e pendências anotadas

**Decidido:**

1. **Superfície: app Nuxt próprio** (§6).
2. **Yooga: entra** (F6), como fonte externa first-class e ingestão completável (§7).
3. **Gráficos: liberados**, úteis e nunca decorativos (§6).

**Semântica da medição — resolvida nesta frente** (o dono liberou: o pertinente ao B.I. é
como os timers viram dados; resolver aqui o necessário para avançar, tudo bem). O decidido
abaixo governa **o fato `OvenRun` (a medição)**; a UX do kiosk é território da frente de
produção e **não muda aqui** — se ela um dia mudar o fluxo (ex.: declarar forno no arm),
ajusta-se o wiring, não o modelo:

- (a) **Pausa/`+N` não afetam a medição** — pausar congela o countdown, não o tempo físico;
  o pão continuou no forno.
- (b) **Abrir o QC com timer tocando sem apertar Concluir = sem medição** (run `abandoned`)
  — fiel à definição benzida: sem resposta declarada, sem medição.
- (c) **Re-armar uma WO com run aberto = nova enfornada**; a anterior vira `abandoned`.
- (d) **Dimensão forno**: `oven_ref` = snapshot do `position_ref` da WO no arm — zero toque
  novo às 5h; fornada sem posição fica sem forno atribuído, e o relatório declara a
  cobertura da atribuição em vez de fingir completude.

## 10. Fases (cada uma: um passo por commit, `make test` verde)

| Fase | Entrega | Toca |
|---|---|---|
| **F0** | ADR-021 aceita (status Proposto→Aceito) + este plano mergeados | docs |
| **F1** | `OvenRun` (model + migração backstage) + endpoints arm/conclude + sweep de abandonados no `maintenance_worker` + testes | backstage, shop (commands) |
| **F2** | production-nuxt: `startOven`/`concludeOven` disparam os POSTs (best-effort, offline-tolerante); contrato de schema atualizado | surfaces/production-nuxt |
| **F3** | B.I. produção: `projections/bi_production.py` + `api/bi.py` (tempo de forno, rendimento, perdas, qualidade; com cobertura) + permissão `view_bi` | backstage |
| **F4** | B.I. vendas/caixa/clientes (+ write-offs pós-C4) | backstage |
| **F5** | Superfície: scaffold de `surfaces/bi-nuxt` (:3007, extends operator-kit) + telas de produção e vendas com gráficos | surfaces/bi-nuxt, hub-nuxt |
| **F6** | Ingestão Yooga (`HistoricalSale`/`HistoricalSaleItem` + command idempotente) + série longa nas telas de vendas | backstage, surfaces/bi-nuxt |

Dependências: F1→F2→F3 é o caminho âncora; F4 é paralelo a F2/F3; F5 depende de F3 (e F4
para as telas cross-suite); F6 é independente. Rebase sobre #146/#148/#149 quando mergearem —
o F4 de write-offs só fecha pós-C4.

## Referências

- [ADR-021 (minuta) — B.I. cross-suite](../decisions/adr-021-bi-cross-suite-read-layer.md)
- [ADR-017 §8](../decisions/adr-017-quality-as-production-outcome.md) · [QC-FORNADA §7](QC-FORNADA.md) · HARDENING-PLAN §9 — a doutrina revertida
- [ADR-003 — Directives sem Celery](../decisions/adr-003-directives-sem-celery.md) · [ADR-011](../decisions/adr-011-formula-and-cashshift.md) · [ADR-012](../decisions/adr-012-headless-surface-contract.md)/[014](../decisions/adr-014-surface-data-presentation-cut.md) · [ADR-016](../decisions/adr-016-sse-first-realtime.md)
- `docs/reference/data-schemas.md` — registrar as chaves de `DayClosing.data` consumidas
- ROADMAP linha "Tempo real de forno (BI da fornada)" — a definição benzida
