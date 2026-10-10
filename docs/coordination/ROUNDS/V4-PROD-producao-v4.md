# V4-PROD: a Produção igual à prévia v4

- **id:** V4-PROD
- **branch:** claude/v4-prod
- **PR:** #1459
- **estado:** na fila (auto-merge)
- **início (UTC):** 2026-10-04

## Objetivo
Onda V4 (ordem do dono, 04/10: "quero tudo igual à v4"). O app de Produção
(`surfaces/production-nuxt`) veste a camada visual da suíte (`data-suite="v3"`), no
modelo do Gestor (#1448/#1451), com as prévias `plano-porque.jpg` e
`producao-qualidade.jpg` como fonte da verdade e as telas v3 de produção onde a v4 não
redesenhou. Vocabulário do #1433 intacto (Planejamento · Preparação · Abertura ·
Fechamento · Qualidade; previsto/realizado).

## O que entrou
**Shell:** `ProductionNav` (rail da suíte + barra do polegar) no lugar do `OperatorRail`
com as abas no cabeçalho. Rail: as cinco etapas com a tecla impressa (Alt1 a Alt5, só com
ponteiro fino), Timers (selo de ativos, ponto quando toca), e no pé Receitas, Relatórios
(com as mesmas sondas de acesso) e o Letreiro; Alertas no pé. Celular: as cinco etapas na
barra do polegar ("Plano" e "Preparo" como rótulo curto, nome cheio para leitor de tela),
Timers e o sino na barra de 56px, Receitas/Relatórios/Letreiro no ⋯.

**Cabeçalho (`ProductionHeader`, agora `OperatorPageHeader`):** uma linha com título, ao
vivo com a hora da última leitura ("Sem atualizar" por extenso quando a leitura falha),
busca com "/", "N de M planejados/abertos" com a barra, o dia e o ⋯ (Atualizar R,
Abrir timers, Atalhos ?). Teclas Alt+1 a Alt+5, "/", R e "?" seguem no mesmo lugar do
código. `RecipeHeader` também virou o cabeçalho da suíte.

**Planejamento (prévia `plano-porque4.html`):** recortes Todos · A planejar · Com
ressalva · Planejados · Base; linha de 62 px com nome + SKU + encomendas, sugestão
(número + no máximo um sinal + "Por quê"), stepper na linha e "Planejar N" (uma
primária com o número); mudou o número, "você mudou de X · voltar". "+N produtos sem
ressalva" vira conjunto (Ver um a um, Planejar os N como sugerido, um plano por produto,
para na primeira recusa). Os que não têm sugestão para o dia também viram conjunto
(planejar à mão, um toque para abrir). Planejados viram uma linha de estado; Corrigir,
Planejar novo lote e Ver encomendas no menu de cada produto. O diálogo de planejar
continua para ajustar um lote planejado, somar um lote novo e a volta da recusa.

**Abertura:** tabela com Situação (A confirmar / Aberto), Planejado, Previsto e Ação;
recortes Todos · A confirmar · Abertos. **Fechamento:** cartões de lote em duas colunas,
o próximo com borda, o timer e "N un. Finalizar"; o dia no cabeçalho e o lote avulso no
⋯. **Qualidade (prévia `producao-qualidade4.html`):** "Para confirmar | Confirmados" na
linha do título, o dia no cabeçalho, selo de lotes à espera no rail, cartões na tipografia
da suíte. **Preparação, Timers, Relatórios, Receitas:** cabeçalho e tipografia da suíte.
**Letreiro:** caráter Solari mantido, com os tokens escuros da suíte e a Instrument Sans.

**Kit (aditivo):** `OperatorSuiteRail` ganha `print-shortcuts` e `dense-labels`;
`RailSection` ganha `printShortcut`/`dense`; `OperatorSection.shortLabel` (barra do
polegar). Duas correções de acessibilidade que a matriz AA da Produção pegou e valem para
todos os migrados: o selo do app no celular (`OperatorPageHeader`) tem alvo de 44 px (o
desenho segue com 36) e as iniciais do operador no rail passam a fundo escuro (contraste
3,7 → acima de 4,5).

## Fora daqui (com nome e motivo)
- "6 un. para 08:30" (hora da encomenda no chip): a projeção do quadro só tem a
  quantidade comprometida, não a hora do compromisso. O chip mostra "6 un.".
- Ocasião e clima no cabeçalho do Planejamento ("Sábado comum, previsão 24 °C"): a
  projeção do quadro não entrega o `DayContext` do dia planejado.
- "Planejado 15:12" (a hora do plano): os planejados não trazem a hora do plano na
  projeção; a linha diz "Planejados".
- Achado de dado: no início de uma estação (`production.suggestion.seasons`) a sugestão
  some por semanas, porque a janela de 28 dias fica toda na estação anterior e o filtro de
  meses a descarta. Nas capturas o banco local usou uma estação única. Decisão de regra.

## Evidência
Ver o corpo do PR (saídas de comando) e a página de comparação
`scratchpad/ux/v4-prod/index.html` da sessão coordenadora.
