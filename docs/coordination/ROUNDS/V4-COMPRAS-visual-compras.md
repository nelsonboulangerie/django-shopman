# V4-COMPRAS: o app de Compras igual à v4

- **id:** V4-COMPRAS
- **branch:** claude/v4-compras
- **PR:** ver o PR do branch `claude/v4-compras`
- **estado:** PR aberto, auto-merge ligado
- **início (UTC):** 2026-10-04

## Objetivo
Onda V4 (ordem do dono, 04/10: "quero tudo igual a v4"). O Compras
(`surfaces/purchase-nuxt`) veste a camada visual da suíte (`data-suite="v3"`, rail da
suíte, cabeçalho de uma linha, barra do polegar), no modelo do Gestor (#1448/#1451), e
as telas ficam iguais às prévias: `v4/compras-validade.jpg` (recebimento por exceção no
celular) e, onde a v4 não redesenhou, as v3 `purchase-base3.html`,
`purchase-receive-phone3.html` e `purchase-receive-tablet3.html`.

## O que entrou
- **Shell:** `data-suite="v3"`; `PurchaseNav` (novo) monta `OperatorSuiteRail` (tablet
  para cima) e `OperatorSectionBar` (celular) com Painel, Comprar (ponto quando há
  reposição urgente), Receber (selo com as pendências da entrada aberta) e Base. As seções
  continuam estado, não rota (`current` + `select`). Sai o `PurchaseTopBar` e a barra do pé
  feita à mão. Avisos (sino) no pé do rail; no celular, na barra de 56px.
- **Cabeçalho de uma linha** em todas as vistas (`OperatorPageHeader` + `OperatorLiveStatus`
  com a hora da última leitura). Base: controle segmentado dos cadastros, busca com a
  tecla `/` (insumos e contagem pelo nome/SKU, custos na tabela do fornecedor) e a linha
  "Compras hoje" com Atenção e as três métricas, cada uma levando ao recorte.
- **Base › Insumos:** tabela da v3 (colunas fixas, SKU e papéis na linha de apoio, mínimo
  editável com borda cheia quando alterado, situação em etiqueta cheia), barra de ação no
  rodapé e painel docado de 372px. No celular, um cartão por insumo.
- **Receber:** documento da entrada no cabeçalho ("Alto Alegre · NF 12.884", lido da própria
  chave, `invoiceNumberLabel`); com a NF lida, o bloco de leitura recolhe numa linha
  ("Trocar NF" reabre); linhas em cartão com etiqueta cheia; conferência com "N de M
  conferidos · K pendências" e a barra; "Confirmar entrada" tracejado enquanto há
  pendência e, no celular, preso no polegar acima das seções.
- **Conferência por exceção** (`ReceiptExceptionFlow`) no desenho da v4: veredito em cartão
  verde/âmbar, "O que só você vê" com borda cheia, stepper de 56px, atalhos de validade de
  48px, linhas resolvidas em verde leve com "Trocar", "Para resolver" em destaque.
- Etiquetas de estado da linha (`receiptLineStatus.ts`) passam a `pill-*` do kit.
- **Kit:** só o teste `guardrails.appBar.test.ts` (o Compras sai da lista dos que usam
  `OperatorAppBar` e entra na dos que migraram para o rail da suíte).

## Função (não regride)
Nenhuma ação, atalho, permissão, estado ou SSE saiu. Mudaram de lugar: Atualizar (sempre à
vista no cabeçalho; no celular, na barra de 56px), Com NF/Sem NF (cabeçalho), a busca da
Base (cabeçalho, uma só), "Só os que faltam" (chip), a leitura da NF depois de lida (atrás
de "Trocar NF"). A regra do pedido de compra não mudou; o diff fica disjunto do PR #1418
exceto pelo cartão de Comprar, onde as linhas dos botões ficaram textualmente iguais.

## Evidência (saída de comando, 04/10/2026)
- `surfaces/purchase-nuxt`: `npx vitest run` → 11 arquivos, 138 testes passando (novo
  `tests/camada-visual-da-suite.test.ts`, 6); `npx nuxi typecheck` limpo; `npx eslint .` 0
  problemas.
- `surfaces/operator-kit`: `npx vitest run` → 105 arquivos, 1142 testes passando (inclui as
  travas de vocabulário, travessão, "cópia não se corta", clique nunca inerte e cabeçalho).
- Backend não foi tocado.

## Fora daqui (com nome e motivo)
- Gaveta do item encaixada ao lado da lista no tablet em pé (v3): o foco e o "Ir até lá"
  dependem da gaveta em portal; frente própria.
- Teclado numérico na tela, "Ler EAN", "Bipar cada volume", "Ler da embalagem", "Mesma
  da última entrega", recusa parcial ("Devolver só este item") e o ⋯ da conferência:
  recursos novos, não peças visuais.
- Ordenar por nome e o ⋯ do cabeçalho da Base: não existiam.

## Prova visual
`scratchpad/ux/v4-compras/index.html` da sessão coordenadora (+ `img/`): prévia | real em
desktop, tablet deitado e em pé, celular 390 e 320, claro e escuro.
