# UX-KIT-V2: o Gestor igual à prévia v4

- **id:** UX-KIT-V2
- **branch:** claude/ux-kit-v2-gestor-v4
- **PR:** #1451 (draft, sem auto-merge: o dono aprova as capturas)
- **estado:** esperando o dono (capturas prévia | real)
- **início (UTC):** 2026-10-04

## Objetivo
Continuação do UX-KIT-V1 (#1448). Ordem do dono (04/10): o Gestor fica visualmente IGUAL
à prévia v4, peça por peça (cartão, etiquetas, grade da Saída, cabeçalho de uma linha,
faixas recolhidas com resumo, rail com Ajustes, tablet e celular). Função não regride.

## O que entrou
**Cartão (`OrderCard.vue`, desenho de `gestor-colunas4.html` e `gestor-fila4.html`):** código
grande (`op-code`), nome · canal, selo do estado no canto (Novo, Próximo, Bloqueado ou o
estado; quando o selo diz outra coisa, o estado segue escrito na linha do tempo), tempo em
palavras ou o prazo ("aceita/cancela sozinho em m:ss"), etiquetas cheias com ícone (um estilo
só: Retirada/Entrega, N itens, agendado, fila de espera, presente, observação, quem atende),
um traço por estação com a frase ("1 de 2 prontos · falta Encomendas"; o "Pronto de X" da
estação sem tela e o papel perdido seguem no cartão), "Pronto · automático · desfazer",
bloqueio escrito com cadeado e botão tracejado listrado, pagamento e total acima do botão,
botão largo com o verbo e o nome ("Entregar a Ana", "Despachar M09"; o rótulo do servidor
fica no `title`), "Aguardando Café" no lugar do botão enquanto a Cozinha trabalha, e o
cartão entregue no lugar, riscado, com o anel do tempo e "Desfazer N s". A caixa de seleção
e o "Atender" saíram da vista: ⋯ do cartão (Atender/Liberar, Selecionar vários, Voltar
para…, Abrir o pedido) e toque longo.

**Quadro (`pages/index.vue`, `BoardMenu.vue`):** cabeçalho de UMA linha (título, ao vivo,
busca, som, ordenar, alternador Quadro/Tabela com a tecla, ⋯); Ciente só enquanto há pedido
novo; Atualizar, exportar, imprimir, seleção em lote e a última leitura útil no ⋯ (que fica
aberto ao atualizar). Recortes: Todos | Entrega, Retirada, "+ Canal" (seletor; o canal
escolhido vira chip cheio com ×). Seleção em lote é modo, com barra (Aceitar N, Avançar N,
Marcar todos, Limpar, Concluir; Esc sai). Tablet em pé e posto Saída: ordenar, visão e som
entram no ⋯ para a linha não quebrar. Celular: "Filtros" no começo dos recortes abre o
painel pelo pé.

**Posto Saída:** "Posto Saída · este dispositivo" quando o dispositivo é posto, busca de 15
rem, Visão: Saída e Mostrar as 3 colunas; a coluna larga vira grade de altura igual em duas
linhas que enchem a tela, com os recortes do fluxo na cabeça e "lembrada neste posto"; o
excedente vira "+N prontos esperando (códigos)", que abre todos.

**Faixas recolhidas (`QueueColumnStrip`, kit, atrás de `suite:`):** a `.strip` da v4 (56 px,
círculo de contagem, nome em pé de 16 px, ponto, anel e sino quando há novidade) e a frase
da urgência (`summary`: "aceita sozinho em 1:10"; atraso fala primeiro).

**Rail (`OperatorSuiteRail` + `OperatorSection.group/foot`, kit):** dois andares. OPERAÇÃO:
Pedidos (`?columns=all`, selo de novos) e Saída (`?columns=expedition`, selo da Saída; no
celular abre a aba). Ajustes no pé, com o ponto de canal desligado, e a página `/settings`
(Histórico, Catálogo, Clientes, Canais, Postos, cada um a um toque; Clientes e Postos com a
mesma permissão de antes). O item Ajustes acende em qualquer uma dessas telas.

**Copy:** "Marcar como retirado" e "Marcar como entregue" com minúscula, nas duas fontes do
servidor (`order_queue.NEXT_ACTION_LABELS` e `operator_orders`).

## Função (não regride)
Nenhuma ação, atalho, permissão ou estado saiu. Mudaram de lugar: Atualizar, exportar,
imprimir e a última leitura útil (⋯ do quadro), Atender e a seleção (⋯ do cartão e modo),
Histórico/Catálogo/Clientes/Canais/Postos (Ajustes), ordenar e visão no tablet em pé e no
posto Saída (⋯). Atalhos r, v, s, /, Esc e 1/2/3 intactos (Esc agora fecha o painel aberto
antes de limpar os recortes). Testes que fixavam a posição antiga foram reescritos para o
lugar novo (alvos de toque, Atualizar no e2e de negociação, freshness da fila no teste de
integração, seções do rail); nenhum teste de comportamento afrouxou.

## Evidência (saída de comando, 04/10/2026)
- `surfaces/orders-nuxt`: `npx vitest run` → 55 arquivos, 585 testes passando (novo
  `tests/cardV4.test.ts`, 18); `npx nuxi typecheck` limpo; `npx eslint .` 0 erros (2 avisos
  antigos de `catalog.vue`).
- `surfaces/operator-kit`: `npx vitest run` → 105 arquivos, 1142 testes passando (inclui as
  travas de vocabulário, travessão, "cópia não se corta" e a escala tipográfica; `op-code` e
  `op-action` entraram como papéis da camada da suíte, sem ampliar a allowlist).
- Python: `pytest test_order_queue_surface.py test_saida_com_maquininha.py
  test_api_notifications.py` → 105 passando; `test_vocabulario_de_tela.py` → 2260 passando;
  `ruff` limpo.
- e2e do Gestor (Playwright, Chromium desta máquina, mock backend): 8 de 9 passam. O
  `ifood.spec.ts` falha pelo mesmo motivo de antes no `main` (procura no cartão o resumo de
  operação do iFood, que mora no detalhe desde antes do V1). O `tests/integration` precisa do
  laboratório Django e não rodou aqui.

## Fora daqui (com nome e motivo)
- A FILA "Precisa de você" da v4 desktop (lista por urgência + coluna "Em andamento / O
  sistema fez / Agora no cardápio"): o Gestor segue com o quadro de três colunas. Faltam
  dados: a classificação "espera um fato humano" no servidor, a meta de tempo por etapa
  (só o pedido novo tem prazo), a linha do tempo dos automáticos dos últimos 15 min (hoje o
  desfazer é por pedido) e o estado do cardápio e do iFood na mesma leitura.
- "N volumes" (a projeção tem `items_count`, não volumes) e "pronto há N min" (não há a hora
  do pronto; o tempo é desde a chegada).
- "Atalhos" no rail (não existe painel de atalhos; as teclas estão nos títulos e impressas
  no desktop). Busca da suíte inteira e detalhe em duas colunas: exceções aceitas.
- "Em Preparo" com P maiúsculo vem do `OmotenashiCopy` (`ORDER_STATUS_PREPARING`), que
  também fala com o cliente; não mexi.

## Prova visual
`scratchpad/ux/kit-v2/index.html` da sessão coordenadora (+ `img/`): posto Saída 1180×820
(claro, escuro, 1024 com a faixa do excedente), desktop 1440×900 (claro, escuro, ⋯, modo de
seleção), Ajustes, tablet em pé 820×1180, celular 390×844 (Entrada, Saída, Filtros, escuro)
e 320×568.
