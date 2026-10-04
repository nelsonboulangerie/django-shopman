# V5-SUG: a sugestão de produção não some no começo de estação

- **id:** V5-SUG
- **branch:** claude/v5-sugestao-estacao
- **estado:** PR aberto, auto-merge ligado
- **início (UTC):** 2026-10-04

## Problema (achado do PR #1459)
No começo de uma estação (`production.suggestion.seasons`; outubro abre a "hot"), a janela de 28
dias do histórico ainda está toda na estação anterior. O filtro por meses descartava esses dias, a
ficha ficava sem amostra e a sugestão sumia por semanas.

## Decisão do dono
Enquanto a estação nova não tiver histórico suficiente, usar o histórico da estação anterior até
juntar dados novos.

## O que entrou
- `ProductionConfig.Suggestion.season_min_samples` (default `3`, `0` desliga): "suficiente" é ter
  pelo menos N dias-amostra da estação corrente na janela. Mesmo lugar dos outros parâmetros da
  sugestão (`Shop.defaults["production"]["suggestion"]`), documentado em `data-schemas.md`.
- `suggest_for()` (orquestrador, `shop/services/production.py`): a ficha abaixo do mínimo é
  recalculada com os meses da estação anterior (`previous_season_for`); a troca só vale se a
  anterior tiver mais amostra. O `basis` marca `season_fallback`, `season` (anterior),
  `current_season` e `current_season_samples`. Craftsman intocado.
- Projeção do quadro: `season_fallback` + `current_season_label`. Produção (Nuxt), "Por quê":
  "Baseado na estação amena, ainda sem histórico da estação quente".

## Fora
- Campo no Admin para `season_min_samples`: ajustável por `Shop.defaults`, sem formulário próprio.
