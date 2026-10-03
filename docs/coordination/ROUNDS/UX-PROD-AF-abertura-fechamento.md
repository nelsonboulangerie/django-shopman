# UX-PROD-AF · Abertura e Fechamento (Craftsman + app de Produção)

Branch `claude/ux-prod-abertura-fechamento`, PR #1433.

Objetivo (parecer do dono, 03/10/2026): realinhar a camada pt-BR e a navegação do
fluxo `planned → started → finished`. Abas Planejamento · Preparação · Abertura ·
Fechamento · Qualidade; status Planejada · Aberta · Fechada · Cancelada; eventos
Abertura e Fechamento; quantidades planejado · previsto · realizado; indicadores
perda e aproveitamento. "Rendimento" fica reservado à ficha técnica e à massa.
Nenhum identificador do Core muda (`start`, `finish`, `started_qty`, `yield_rate`,
`STARTED_BATCH`, `action="started"`, payloads, contrato da API).

## Fonte única dos rótulos de status

Mora nos choices do modelo, `WorkOrder.Status` (Craftsman). Motivo: o Django exige
um rótulo nos choices e o Admin o mostra direto (`get_status_display`, migração de
choices); qualquer tabela em outra camada seria, por construção, uma segunda fonte.
ADR-001: o Core não conhece as superfícies, as superfícies leem o Core, e é o que a
projeção do backstage já faz (ela importa `shopman.craftsman.models`). ADR-014: o
corte proíbe copy na Projection do orquestrador (`shop/projections/`); a projeção da
Produção é apresentação do backstage e só repassa o rótulo. Quem lê:

- `shopman/backstage/projections/production.py`: `WO_STATUS_LABELS` derivado de
  `WorkOrder.Status` (antes: tabela própria com "Produzido"/"Estornado").
- Admin (`contrib/admin_unfold/admin.py`): `_work_order_status_label` lê
  `WorkOrder.Status(...).label` (antes: tabela própria com "Iniciada"/"Concluída").
- OpenAPI (`config/settings.py`, `ENUM_NAME_OVERRIDES`): caminho para
  `WorkOrder.Status` (antes: lista copiada).

Trava: `shopman/backstage/tests/test_vocabulario_abertura_fechamento.py`.

## Inventário (arquivo → antes → depois)

| Arquivo | Antes | Depois |
|---|---|---|
| `craftsman/models/work_order.py` | Status Iniciada · Concluída; "Quantidade Concluída", "Iniciada em", "Concluída em" | Aberta · Fechada; "Quantidade realizada", "Aberta em", "Fechada em" (migração `craftsman.0017`, gerada) |
| `craftsman/models/work_order_event.py` | Kind started "Iniciado", finished "Concluído" | "Abertura", "Fechamento" (demais kinds revisados, ficam) |
| `craftsman/contrib/admin_unfold/admin.py` | coluna "Produzido" (= finished), "Iniciado"; tabela própria de status; "Tempo alvo iniciado" | "Realizado", "Previsto"; status da fonte única; "Tempo máximo de lote aberto" |
| `craftsman/contrib/stockman/handlers.py` | "Produção iniciada", "Perda de rendimento: … (iniciado X, rendeu Y)", "Produção concluída" | "Abertura de lote", "Perda: … (previsto X, realizado Y)", "Fechamento de lote" |
| `backstage/projections/production.py` | `WO_STATUS_LABELS` Produzido/Concluído/Estornado; ações "Confirmar produzido", "Estornar lote", "Confirmar conclusão" | fonte única; "Confirmar abertura", "Cancelar lote", "Confirmar fechamento"; relatório ganha `started_assumed` |
| `backstage/services/production.py` | CSV "Qtd iniciada/concluída", "Rendimento (médio)", "Iniciada/Concluída em"; mensagens "estornado", "ordem iniciada", "quantidade iniciada" | "Qtd prevista/realizada", coluna "Previsto assumido", "Aproveitamento (médio)", "Aberta/Fechada em"; "cancelado", "lote aberto", "realizado acima do previsto" |
| `backstage/models/alerts.py` (choices por callable, sem migração) | "Produção com yield baixo", "… nunca iniciada", "… nunca concluída", "… concluída sem gravar os lotes" | "Lote fechado com aproveitamento baixo", "Lote planejado nunca aberto", "Lote aberto nunca fechado", "Lote fechado sem gravar a rastreabilidade" |
| `backstage/projections/alerts.py` | contexto `/expedite` | `/close` (falta de insumo, não fechado, rastreabilidade) e `/quality` (aproveitamento baixo, comunicação e proteção de qualidade) |
| `backstage/projections/hub_queue.py` (Central) | "iniciado às", "Abrir lote", `/expedite` | "aberto às", "Fechar o lote", `/close` |
| `shop/services/user_notifications.py` | `/expedite#quality` | `/quality` |
| `shop/handlers/production_alerts.py` | "fechou com yield de N%", "nunca foi iniciada/concluída", "concluiu mas os lotes não foram gravados" | "fechou com aproveitamento de N%", "nunca foi aberto/fechado", "fechou, mas a rastreabilidade não foi gravada" |
| `shop/admin/shop.py` | "Limiar de rendimento baixo" (produzido/iniciado) | "Limiar de aproveitamento baixo" (realizado ÷ previsto) |
| `config/management/commands/seed.py` | templates "Yield baixo…", "não foi iniciada" | "Aproveitamento baixo no lote…", "não foi aberto" |
| `production-nuxt` header + atalhos | Produção (Alt+3) · Expedição (Alt+4) | Abertura (Alt+3) · Fechamento (Alt+4) · Qualidade (Alt+5) |
| `production-nuxt/pages/expedite.vue` | página única com abas internas Expedição/Qualidade (QC) | `pages/close.vue` (Fechamento) + `pages/quality.vue` (Qualidade, rota própria) |
| `production-nuxt/nuxt.config.ts` | 301 `/planejamento`, `/preparacao`, `/expedicao`, `/painel` | removidos (decisão do dono, pré go-live, zero legado) |
| `ProductionStageGrid.vue` | lente `produce`, coluna "Produzido", "produzidos", "Quanto foi produzido?", "Estornar…" | lente `open`, "Previsto", "abertos", "Quanto está previsto?", "Cancelar lote…"; o "Fechar" do diálogo do lote vira "Voltar" |
| `QcCloseScreen.vue` | "N produzidos", "acima do lote iniciado" | "N previstos", "realizado acima do previsto" |
| `pages/reports.vue` | Produzido · Concluído · Rendimento, "Rendimento médio", "OPs concluídas" | Previsto · Realizado · Aproveitamento, "Aproveitamento médio", "lotes fechados"; selo **assumido** + legenda quando o lote fechou sem abertura |
| `productionContract.ts` | — | regerado (`export_production_schema`): `started_assumed` |
| docs | glossário e `suite-vocabulary.md` | entradas novas (Abertura, Fechamento, Qualidade, previsto/realizado, perda/aproveitamento) |

## Regra 3: fechamento sem abertura explícita

`_wo_started_assumed` (projeção): verdade quando o evento `started` traz
`implicit: True` ou não traz quantidade. O relatório mostra o número com o selo
**assumido** e uma legenda ("o previsto foi assumido igual ao planejado. Ninguém o
declarou."); o CSV ganha a coluna "Previsto assumido".

## Fora de escopo, deliberadamente

- Caixa (abertura/fechamento do PDV), checklists da casa, Saída/Preparo/Expedição do
  KDS e do Gestor (`orders-nuxt`, `kds-nuxt`), o posto "Expedição".
- "Rendimento" da ficha técnica (`batch_size`, `yield_quantity`), da massa
  (`yield_margin`) e o "Rendimento previsto" da etiqueta de pesagem.
- **B.I.** (`bi_explore` "Rendimento", `bi_production`) e **livro de receitas**
  (`recipe_book.build_recipe_usage`, "rendimento médio"): os dois calculam realizado
  ÷ **planejado**, não ÷ previsto. Trocar o rótulo para "aproveitamento" mentiria
  sobre a conta; trocar a conta muda o número. Pergunta ao dono.
- `CLAUDE.md` ainda cita `/expedite` e os 301 do PR #68: não foi editado por esta
  frente (precisa da palavra do dono ou da sessão coordenadora).
- Os demais kinds de evento (Planejado, Ajustado, Enfornado…) e o
  `MovementType` do caixa não mudam.

## Evidência

- Craftsman: `518 passed, 2 skipped`.
- Backstage completo: `4 failed, 8702 passed`; 3 falhas passam isoladas (concorrência
  do xdist), 1 era string fixada (`test_qc_kiosk`), corrigida; reexecução dos arquivos
  tocados e das travas: `3442 passed`.
- `makemigrations --check`: `No changes detected`. Ruff: `All checks passed!`.
- production-nuxt: vitest `426 passed` (+ trava nova), `eslint` 0, `nuxi typecheck`
  0, build e e2e Playwright (chromium desktop, tablet, mobile) `28 + 46 passed`.
- operator-kit vitest: `1121 passed` (travas de vocabulário e travessão).

## Screenshots

`docs/coordination/ROUNDS/img/ux-prod-af/`: `abertura.jpg`, `abertura-confirmar.jpg`,
`fechamento.jpg`, `fechamento-qc.jpg`, `qualidade.jpg`, `relatorio.jpg`,
`relatorio-assumido.jpg`, `atalhos.jpg`, `admin-workorders.jpg` (servidor local,
banco semeado, lote WO-2026-00025 fechado sem abertura para mostrar o selo).
