# V4-MKT: o Marketing na camada visual da suíte (onda v4)

- **id:** V4-MKT
- **branch:** claude/v4-mkt
- **PR:** (preenchido no PR)
- **estado:** PR aberto, auto-merge ligado
- **início (UTC):** 2026-10-04

## Objetivo
Ordem do dono (04/10): "tudo igual à v4". O Marketing veste a camada visual da suíte do
kit (UX-KIT-V1/V2, modelo: Gestor) e a prévia `docs/plans/suite-ux-v2/v4/marketing-decisoes.jpg`
(fila de decisões por prazo e o selo). Função não regride; o envelope de segurança do kit
(ADR-026), de que o Marketing é piloto, fica como está.

## O que entrou
**Shell:** `data-suite="v3"`; `MarketingNav` monta o `OperatorSuiteRail` (OPERAÇÃO:
Decisões com o selo âmbar, Agendados, Enviados; Ajustes no pé) e a `OperatorSectionBar`
no celular. `CampaignTopBar` e `MarketingSectionBar` saíram. `--app-color` no `<html>`.

**Cabeçalho:** `MarketingPageHeader` sobre o `OperatorPageHeader` em todas as telas
(Decisões, Agendados, Enviados, Campanhas, Modelos, Plataformas, o workspace de Ajustes,
o anúncio e o painel da matriz visual). Em toda tela de Ajustes, a segunda linha
(`MarketingSettingsNav`: Campanhas, Modelos, Ofertas e cupons, Plataformas) mora na linha
de recortes com o chip da suíte. No celular a barra de 56px leva o sino (ponto âmbar) e o
menu do operador; "ao vivo" com a hora nas telas de fila.

**Fila (`MarketingDecisionQueue`):** cartão da v4 (14px, miniatura de 60px no tom do app ou
a plataforma que falhou, título de 16px, destino de 13px, motivo na faixa vermelha, prazo
como hora em negrito + tom, "Revisar" de 48px cheio só no mais urgente, que tem a borda na
cor da ação), linha automática com o brilho, "+N agendados hoje" com o número forte.
Agendados no mesmo cartão, sem destaque.

**Selo (`MarketingCommandConfirmationDialog`):** folha que sobe do pé no celular, carimbo
na cor do app, destinos um por linha com a grandeza à direita (`sealRows`) e a frase do
que volta e do que não volta (`sealConsequence`). O mesmo desafio de antes.

**Caixa pessoal:** `MarketingInboxLive`, um só no shell, em qualquer largura (SSE, poll,
"visto", a instância `live` da fila). O sino virou só link.

**Kit (aditivo):** `OperatorPhoneMenu`, peça nova: o menu do operador no celular (tema,
giro, Bloquear). Sem ela o celular perdia o que o `OperatorRail` clássico mostrava em
qualquer largura; o a11y do Marketing troca o tema em 320px. Guarda do cabeçalho: o
Marketing passa da lista "convertidos" para "migrados".

## Função (não regride)
Mudaram de lugar: as seções (rail/polegar), a linha de Ajustes (linha de recortes), o
"Voltar às decisões" (o voltar do cabeçalho), o link "Modelos" da página de Campanhas
(chip de Ajustes logo abaixo), tema/giro/Bloquear no celular (menu das iniciais),
Atualizar do workspace e de Enviados no celular (ícone na barra de 56px), Atualizar da
fila (linha do título). Testes que fixavam o lugar antigo foram reescritos; nenhum
teste de comportamento afrouxou.

## Evidência (saída de comando, 04/10/2026)
- `surfaces/marketing-nuxt`: `npx vitest run` → 54 arquivos, 445 testes passando;
  `npx nuxi typecheck` limpo; `npx eslint .` limpo; `npm run test:security` 13/13;
  `npm run build` completo.
- `surfaces/operator-kit`: `npx vitest run` → 105 arquivos, 1145 testes passando; eslint limpo.
- Playwright local (Chromium 1194 desta máquina, backend hermético): e2e 8/8; a11y 3/3
  (com as credenciais sintéticas do CI).
- `python scripts/check_marketing_docs.py` → "Marketing docs match HEAD".

## Fora daqui (com nome e motivo)
- Digital do dispositivo e pedido à segunda pessoa por push no selo: função nova (UX-M1).
- Foto na miniatura da fila: a projeção não leva imagem; é mudança de contrato.
- Lupa da prévia: o Marketing não tem busca (busca da suíte é recurso novo).
- Baselines visuais (`tests/visual/baselines`): quase todos os retratos mudam; só a CI
  grava (artefato `marketing-browser-gates`).

## Prova visual
`scratchpad/ux/v4-mkt/index.html` da sessão coordenadora (+ `img/`).
