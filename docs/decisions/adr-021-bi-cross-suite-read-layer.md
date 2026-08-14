# ADR-021 — B.I. cross-suite: agregação é leitura, o ledger segue dono do fato

**Status:** Proposto (minuta — aguardando aprovação do dono)
**Data:** 2026-08-14
**Escopo:** `shopman/backstage` (módulo de B.I.: projections, services, api, models de agregado derivado), `surfaces/` (superfície de gestor), `shopman/shop` (nenhuma mudança de contrato), packages core (nenhuma mudança nesta ADR)
**Reverte parcialmente:** ADR-017 §8, `docs/plans/completed/BACKSTAGE-EXCELLENCE-HARDENING-PLAN.md` §9, `docs/plans/QC-FORNADA.md` §7

---

## Contexto

Três documentos registraram, deliberadamente, que a suite **não** tem B.I.:

- **HARDENING §9** — "App de B.I. — frente futura separada" (fora de escopo, registrar e não fazer).
- **QC-FORNADA §7** — o inventário do que existe no lugar: relatório **calculado na hora**
  (`build_production_reports`, `report_kind`), dashboard do Admin, sem Celery, sem tabela de
  agregação ou snapshot; "um app de BI é uma conversa separada — e, dado o volume de uma
  padaria, provavelmente prematura".
- **ADR-017 §8** — "Os números não vão para um B.I.": o fato vai para o ledger imutável
  (`WorkOrderEvent`), a consolidação do dia para `DayClosing.data`, e a leitura para um
  `report_kind` novo.

Essa doutrina cumpriu seu papel: impediu que o QC da fornada, o fechamento e os relatórios
nascessem acoplados a uma infraestrutura de analytics que não existia. O resultado é que hoje
a suite tem **fontes de fato duráveis e bem modeladas** em todos os domínios:

| Fonte | O que registra | Garantia |
|---|---|---|
| `craftsman.WorkOrderEvent` | ledger de produção; o `finished` carrega a partição de qualidade (ADR-017) | append-only, `seq` único por WO, `idempotency_key` |
| `craftsman.WorkOrderItem` | linhas OUTPUT/WASTE com `quality_grade_ref`, `quality_defect_ref`, `batch_ref` | indexado por grau/defeito × tempo |
| `stockman.Move` | ledger de estoque (MAKE, SELL, WASTE…) | imutável por guard (update/delete levantam) |
| `stockman.Batch` | validade + não conformidade congelada no lote | snapshot (constituição §3.3) |
| `orderman.Order`/`OrderItem` | vendas: `total_q`, timestamps por status, canal; descontos em `snapshot.pricing` e `OrderItem.meta._disc` | campos selados por `ImmutabilityError` |
| `backstage.CashShift`/`CashMovement` | caixa: abertura, contagem cega, diferença, sangria/suprimento | fechamento atômico |
| `backstage.DayClosing.data` | consolidação diária (produção, qualidade, caixa, reconciliação; write-offs após C4) | `unique(date)`, append-only na prática |
| `guestman.contrib.insights.CustomerInsight` | RFM/CRM materializado por cliente | recálculo idempotente, `calculation_version` |

Em 2026-08-14 o dono decidiu: **"Chegou a hora. O B.I. é algo cross-suite."** O pedido âncora
é a produção (tempo real de forno, rendimento, perdas, qualidade), mas o escopo declarado é a
suite inteira (vendas, caixa, clientes). A reversão é registrada aqui, formalmente — não por
baixo dos panos.

## Decisão

### 1. B.I. é uma camada de LEITURA cross-suite. Os ledgers seguem donos do fato

A ADR-011 continua valendo integralmente: **nenhum agregado de B.I. é source of truth**. Todo
número que o B.I. mostra é derivado de um ledger ou consolidação que já existe, e deve ser
**recomputável do zero** a partir deles. Se um agregado materializado divergir do ledger, o
ledger está certo por definição e o agregado é reconstruído.

Corolários:

- O B.I. **nunca escreve** em modelos dos packages core. Ele lê.
- Fato novo que o B.I. precise (ex.: tempo de forno) nasce **no dono do fato**, nunca dentro
  do B.I. — ver §4.
- `report_kind` em `build_production_reports`, o dashboard do Admin e as projections
  operacionais continuam existindo e não são migrados para o B.I. "por arrumação". O B.I.
  responde perguntas **analíticas** (tendência, comparação, série histórica); as projections
  operacionais respondem perguntas do turno ("o que está atrasado agora").

### 2. O B.I. mora no backstage, como módulo — não é um 4º app Django nem um package

Aplicando a constituição §8.3: não é core de domínio (não tem pergunta canônica própria — é
leitura das respostas dos outros), não é plugin de domínio (é cross-domínio por definição), é
**conveniência de framework** — exatamente o que o `backstage` já é para o operador. O
`backstage` já é o precedente de leitor cross-suite (o fechamento lê pedidos, estoque,
produção e caixa) e já possui models próprios (`DayClosing`, `KDSInstance`, `CashShift`).

Estrutura: `shopman/backstage/projections/bi_*.py` + `shopman/backstage/services/bi/` +
`shopman/backstage/api/bi.py` (+ models de agregado derivado quando — e só quando — a
materialização for justificada, ver §3).

Um package `shopman-bi` foi descartado pelo mesmo argumento da ADR-017 §1: precisaria
depender de todos os cores para existir, o que a ADR-001 e o `test_import_boundaries` barram.

### 3. Calcular na hora é o default; materializar exige justificativa medida

No volume da operação (~100–150 vendas/dia, 5–15 fornadas/dia), agregação on-the-fly sobre
os índices existentes responde em milissegundos. Portanto:

- **Default: computar na leitura**, como `build_production_reports` já faz.
- **Série diária histórica: ler `DayClosing.data`** — a consolidação diária já existe e já é
  o snapshot canônico do dia.
- **Materializar só com gatilho medido**, no espírito dos thresholds da ADR-003: p95 de uma
  tela de B.I. > 2s com os índices certos, ou janela de consulta que exija varrer > 12 meses
  de ledger por request. Quando materializar: tabela de agregado **derivado e recomputável**
  no backstage, recalculada por management command no ciclo do `maintenance_worker`
  (sem Celery — ADR-003 continua valendo; os thresholds dela seguem sendo o gatilho de
  migração de infraestrutura).
- **Exceção estrutural: histórico externo** (ex.: export Yooga) não tem ledger na suite,
  então só pode existir materializado — tabela própria do B.I., imutável após a ingestão,
  com a origem carimbada. Não é second source of truth: é o único registro que a suite tem
  daquele passado.

### 4. Tempo de forno vira fato de servidor — no backstage, não no core

A definição benzida pelo dono (2026-08-13, ROADMAP): **start = armar o timer do forno
(enfornou); stop = "Concluir" declarado no timer (retirou); fim de timer sem resposta e o
Confirmar do QC não medem tempo.**

O fato nasce como model do backstage (o dono do fato é a operação de produção da instância,
não o `craftsman` genérico), ligado à ordem por string ref (ADR-004). Precedente direto:
`KDSTicket` — fato operacional de superfície que o backstage já possui. Rejeitado: novos
kinds em `WorkOrderEvent` (`oven_in`/`oven_out`) — poria vocabulário de padaria num core
genérico (constituição §2.6) e exigiria migração em package core sem necessidade comprovada
(CLAUDE.md, Core é Sagrado). Se um dia outra instância precisar de etapas de processo
genéricas no craftsman, isso será uma ADR própria com 2+ consumidores reais.

O QC segue dono do fato **comercial** (partição/lote); o timer é dono do fato **temporal**.
Um não substitui o outro.

### 5. Superfície: decisão do dono (registrada quando aprovada)

O Unfold Canonical Gate faz backstage novo nascer em Admin/Unfold por padrão; POS e
Storefront são exceções explícitas. O B.I. é candidato a terceira exceção (precedente:
`marketing-nuxt` e `orders-nuxt` como apps Nuxt de gestor). A escolha — página Admin/Unfold
vs app Nuxt próprio — está aberta no `docs/plans/BI-PLAN.md` e será registrada aqui quando o
dono decidir. Qualquer que seja a superfície, ela consome Projections registradas
(ADR-012/014): dado puro no backend, copy pt-BR na presentation.

## Consequências

### Positivas

- A doutrina anti-BI é encerrada formalmente, com rastro — não corroída por exceções.
- Os ledgers construídos sob a doutrina viram o ativo: o B.I. nasce sobre fatos imutáveis e
  bem indexados, sem retrofit.
- Zero mudança em packages core nesta ADR. Zero broker novo. Zero warehouse.
- O tempo de forno deixa de morar em localStorage de um kiosk e vira fato auditável.

### Negativas

- Mais um leitor cross-suite no backstage: queries analíticas mal escritas podem pesar no
  banco transacional. Mitigação: janelas de consulta limitadas por default, e o gatilho de
  materialização do §3.
- `DayClosing.data` vira contrato de leitura do B.I. — mudanças de chave passam a ter um
  consumidor a mais (registrar em `docs/reference/data-schemas.md`).
- O timer ganha uma dependência de rede num fluxo que hoje é 100% local. Mitigação: o
  registro do fato é best-effort com retry; o countdown continua local e nunca bloqueia a
  operação.

## Invariantes

- Nenhum agregado de B.I. é source of truth; todo agregado é recomputável dos ledgers
  (exceção única: histórico externo ingerido, §3).
- O B.I. não escreve em models de packages core.
- Não existe pacote `shopman-bi`. O B.I. é módulo do backstage.
- Tempo de forno: só o par armar→Concluir mede; expiração de timer e Confirmar do QC nunca
  entram na medição.
- Materialização nova exige o gatilho medido do §3 registrado no PR que a introduz.
- Sem Celery, sem broker, sem warehouse externo — os thresholds da ADR-003 seguem sendo o
  único gatilho para revisitar isso.

## Referências

- [ADR-001 — Protocol/Adapter e fronteiras de core](adr-001-protocol-adapter.md)
- [ADR-003 — Directives sem Celery](adr-003-directives-sem-celery.md)
- [ADR-004 — String refs](adr-004-string-refs.md)
- [ADR-011 — Fórmula sem FormulaPlan (um fato, um dono)](adr-011-formula-and-cashshift.md)
- [ADR-012 — Contrato headless de superfície](adr-012-headless-surface-contract.md) · [ADR-014 — Corte data/presentation](adr-014-surface-data-presentation-cut.md)
- [ADR-017 §8 — "Os números não vão para um B.I."](adr-017-quality-as-production-outcome.md) (revertido por esta ADR)
- [Constituição Semântica](../constitution.md) — §2.5, §2.6, §8.3
- [docs/plans/BI-PLAN.md](../plans/BI-PLAN.md) — plano de execução
- [docs/plans/QC-FORNADA.md §7](../plans/QC-FORNADA.md) · HARDENING-PLAN §9 (doutrina revertida)
