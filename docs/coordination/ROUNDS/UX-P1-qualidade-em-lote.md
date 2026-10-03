# UX-P1 — Produção > Qualidade em lote: um ato para os lotes sem exceção

- **id:** UX-P1
- **branch:** claude/ux-p1-qualidade-em-lote
- **PR:** #1408
- **estado final:** na fila #1408 (auto-merge ligado)
- **início / fim (UTC):** 2026-10-03 13:05 / 2026-10-03 14:00

## Objetivo
Decisão do dono (03/10): qualidade em lote. Os lotes fechados do dia sem exceção viram um cartão com a
soma e um ato só ("N lotes, nenhuma exceção · Confirmar"), com a consequência antes do gesto e a frase
de responsabilidade. Exceções à parte, uma a uma ("Confirmar assim" / "Corrigir"); o "Corrigir" pede
motivo de verdade (achado P20). Lotes não fechados ficam fora do portão, com atalho para a Expedição.

## O que mudou
- **Regra "sem exceção"** (servidor, `projections/production.py::qc_partition_is_clean`), a mais estrita:
  sem perda, markdown congelado do lote = 0, todo grupo no grau padrão e sem defeito, contagem igual ao
  que entrou no forno (`started_qty`, senão o previsto). Partição ilegível ou sem âncora = exceção.
  Contagem acima do que entrou (overshoot com motivo) também é exceção.
- **Confirmação em lote atômica**: `POST /api/v1/backstage/production/quality-review/batch/`
  (`WorkOrderQualityReviewBatchView`, capability `can_correct_qc`, a mesma do lote a lote). O serviço
  `apply_quality_review_batch` trava os lotes em ordem de pk e chama `apply_quality_review` para cada um
  dentro de uma transação: mesmo evento `quality_reviewed`, mesmo payload, mesmo ator e momento, mesma
  chave idempotente por lote. Recusa tudo se um lote mudou de revisão, é de outro dia ou tem exceção.
  A projeção oferece a ação `review_qc_batch:<sha256 de pk@rev>`, então a prova assinada prende o
  conjunto exato; um conjunto forjado é 400. Core intocado.
- **Projeção do cartão** ganha `quality_exception`, `closed_by`, `closed_at_display`,
  `typical_loss_qty` (média de perda por lote da receita nos 28 dias anteriores, só com 3+ lotes) e
  `alert_waiting_count` (fila "Me avise" de `production_ready`, via `shop/adapters/audience_sources`,
  que é o que a confirmação libera; teto, o canal ainda pode barrar; `null` quando a fila não pôde ser
  lida). Contrato regenerado (`export_production_schema`).
- **production-nuxt**: aba Qualidade vira `QualityGatePanel` (duas colunas no tablet deitado, alvos de
  48px, vocabulário "lote"): cartão do conjunto limpo (soma, chips com "Ver os N lotes", "Fechados por",
  "Ao confirmar: até N clientes avisados"), exceções com barra padrão/desconto/perda, motivo e
  referência, "Confirmados" numa aba própria. `presentation/qualityGate.ts` puro.
- **P20**: `QcCloseScreen` no modo correção pergunta o motivo (lista curta de 3 + texto livre) antes de
  salvar; o texto fabricado "Revisão do QC registrada no quiosque." morreu.
- **window.confirm**: os dois da Produção saíram (o descarte usa `useConfirm` do kit; a confirmação de
  qualidade é o próprio gesto, com a consequência escrita). A lista `DECLARED` da trava
  `guardrails.nativeConfirm.test.ts` ficou vazia.

## Prova
- `pytest shopman/backstage/tests/test_qc_quality_batch.py` → `12 passed` (regra, projeção, overshoot,
  "Me avise" e perda típica, lote limpo em conjunto com o mesmo registro do individual, replay, atomicidade
  com revisão velha, exceção recusada, outro dia recusado, dia anterior, permissão 403, conjunto forjado
  400, correção com motivo em branco 400 e motivo real gravado).
- Testes de produção do backstage (55 arquivos produc|qc|contract|schema|openapi|surface|freshness|action)
  → `1034 passed, 3 skipped`. Vocabulário + QC + notificações + audiência → `2323 passed`.
- production-nuxt `vitest run` → `Tests 389 passed`; `nuxi typecheck` 0 erros; `eslint .` 0.
- operator-kit `vitest run tests/` → `Tests 1049 passed` (vocabulário, nativeConfirm, copyNeverTruncates).
- `ruff check shopman/backstage shopman/shop/adapters/audience_sources.py` → limpo. Sem migração.

## O que ficou de fora
- "Qualidade" como item próprio do rail (nota 8 da prévia): segue como aba da Expedição. Mudar rota e rail
  é desenho de navegação da Produção, maior que esta frente.
- Retrato visual: a Produção não tem baseline da aba Qualidade; nada foi regerado.
- A busca do cabeçalho não filtra a aba Qualidade: o cartão precisa contar exatamente o conjunto que o
  ato confirma.

## Perguntas ao dono
nada
