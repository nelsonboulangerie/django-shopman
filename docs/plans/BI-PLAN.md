# BI-PLAN — B.I. cross-suite no backstage

> **Status:** 🟡 Plano proposto — aguardando iteração e OK do dono. Nada executado.
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

## 6. Superfície — decisão do dono (F5)

O backend (F1–F4) é idêntico nos dois cenários; a decisão não bloqueia nada.

**Opção A — Admin/Unfold** (default do Unfold Canonical Gate: "backstage novo nasce em
Admin/Unfold"). Páginas custom com `UnfoldModelAdminViewMixin` consumindo as projections
registradas (precedente: `operator_badge`). Custo baixo, gestor já vive no Admin, permissão
pronta. Limite: interatividade de exploração (filtros ricos, drill-down) é mais dura no Admin.

**Opção B — app Nuxt próprio** (precedente: `marketing-nuxt`/`orders-nuxt`, :3007, extends
operator-kit, `useOperatorLock("backstage.view_bi")`). Melhor para gráficos interativos e
eventual painel de parede. Custo: uma superfície nova inteira (~7–10k LOC pelos precedentes).

**Recomendação:** nascer na **Opção A** (respeita o gate, entrega valor cedo, reversível) com
graduação para B declarada como evolução — o mesmo caminho que a Central de Apps registrou.
Se o dono já sabe que quer o app próprio, pulamos direto para B sem retrabalho de backend.

Gráficos: a decisão "sem gráficos" era dos relatórios do production-nuxt, não global.
Proponho liberar gráficos no B.I. (sóbrios, neutros — cor só funcional, padrão dos apps de
operador). Confirmar no §9.

## 7. Histórico Yooga (F6, opcional — confirmar escopo)

Export existente: ~81k vendas autorizadas jul/24–jul/26, ~380k itens, consolidado no Drive
(`yooga-consolidado.xlsx`). Se entrar: tabela própria do B.I. (ex.: `HistoricalSale`,
imutável, `source="yooga"`), management command de ingestão one-shot, e as telas de vendas
ganham a série longa com a origem sempre visível (nunca misturar Yooga e Shopman numa mesma
barra sem rótulo). A inferência comer-aqui-vs-levar (regra B, âncora de bebida) já está
decidida e documentada na memória do projeto — aplicável na ingestão. Mesa/balcão do Yooga
não são confiáveis (não usar como verdade).

## 8. O que NÃO entra na v1

- Warehouse externo, Metabase/Superset/etc., Celery/broker (thresholds da ADR-003 intactos).
- Tabelas de agregação especulativas (só com gatilho medido — ADR-021 §3).
- Índices novos em packages core.
- Previsão/forecast e recomendações (o `suggest_production` existente segue como está).
- SSE/painel ao vivo.
- Migrar relatórios operacionais existentes (`report_kind`, dashboard do Admin) para o B.I.
- Comparativo automático Yooga × Shopman por SKU (mapeamento de catálogo é trabalho próprio).

## 9. Perguntas abertas ao dono

1. **Superfície:** Opção A (Admin/Unfold primeiro — recomendada) ou direto Opção B (app Nuxt)?
2. **Yooga:** a ingestão histórica (F6) entra nesta frente ou fica registrada para depois?
3. **Timer, três confirmações de semântica:** (a) pausa/`+N` não afetam a medição; (b) abrir
   o QC com timer tocando sem apertar Concluir = sem medição (run abandonado); (c) re-armar
   uma WO com run aberto = nova enfornada, a anterior não mede. Confere?
4. **Dimensão forno:** usar `position_ref` da WO quando existir (zero toque novo no kiosk),
   aceitando que fornada sem posição fica sem forno atribuído. Ou vale um toque a mais para
   declarar o forno no arm?
5. **Gráficos liberados no B.I.** (sóbrios/neutros)? A decisão "sem gráficos" segue valendo
   nos relatórios operacionais.

## 10. Fases (cada uma: um passo por commit, `make test` verde)

| Fase | Entrega | Toca |
|---|---|---|
| **F0** | ADR-021 aceita (status Proposto→Aceito) + este plano mergeados | docs |
| **F1** | `OvenRun` (model + migração backstage) + endpoints arm/conclude + sweep de abandonados no `maintenance_worker` + testes | backstage, shop (commands) |
| **F2** | production-nuxt: `startOven`/`concludeOven` disparam os POSTs (best-effort, offline-tolerante); contrato de schema atualizado | surfaces/production-nuxt |
| **F3** | B.I. produção: `projections/bi_production.py` + `api/bi.py` (tempo de forno, rendimento, perdas, qualidade; com cobertura) + permissão `view_bi` | backstage |
| **F4** | B.I. vendas/caixa/clientes (+ write-offs pós-C4) | backstage |
| **F5** | Superfície conforme decisão do §6 (páginas Unfold via `make admin`, ou scaffold do app Nuxt) | admin_console ou surfaces |
| **F6** | (opcional) ingestão Yooga | backstage |

Dependências: F1→F2→F3 é o caminho âncora; F4 é paralelo a F2/F3; F5 depende de F3 (e F4
para as telas cross-suite); F6 é independente. Rebase sobre #146/#148/#149 quando mergearem —
o F4 de write-offs só fecha pós-C4.

## Referências

- [ADR-021 (minuta) — B.I. cross-suite](../decisions/adr-021-bi-cross-suite-read-layer.md)
- [ADR-017 §8](../decisions/adr-017-quality-as-production-outcome.md) · [QC-FORNADA §7](QC-FORNADA.md) · HARDENING-PLAN §9 — a doutrina revertida
- [ADR-003 — Directives sem Celery](../decisions/adr-003-directives-sem-celery.md) · [ADR-011](../decisions/adr-011-formula-and-cashshift.md) · [ADR-012](../decisions/adr-012-headless-surface-contract.md)/[014](../decisions/adr-014-surface-data-presentation-cut.md) · [ADR-016](../decisions/adr-016-sse-first-realtime.md)
- `docs/reference/data-schemas.md` — registrar as chaves de `DayClosing.data` consumidas
- ROADMAP linha "Tempo real de forno (BI da fornada)" — a definição benzida
