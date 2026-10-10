# V4-PDV: o PDV igual à prévia v4 (último app da onda)

- **id:** V4-PDV
- **branch:** claude/v4-pdv (PR 1), claude/v4-pdv-fim-do-dia (PR 2), claude/v4-pdv-tablet (PR 3)
- **PR:** #1462 (casca + Venda), #1463 (Fim do dia), PR 3 (tablet) em seguida
- **estado:** PR aberto, auto-merge (onda V4, merge autorizado pelo dono)
- **início (UTC):** 2026-10-04

## Objetivo
Onda V4 ("quero tudo igual à v4"): o PDV (`surfaces/pos-nuxt`) veste a camada visual da
suíte (`data-suite="v3"`, UX-KIT-V1/V2) e fica igual às prévias
`docs/plans/suite-ux-v2/v4/pos-sale.jpg`, `pos-tablet.jpg`, `pos-tablet-fluxo.jpg`,
`fim-do-dia.jpg` e `salao-mesas.jpg`, sem regredir nenhuma função do balcão.

Dividido em PRs sequenciais para caber numa revisão:
1. **casca + Venda (este PR)**: rail da suíte, barra de contexto, grade, comanda (COMPOSIÇÃO).
2. **Fim do dia**: o corredor de 3 passos com a conferência cega (`fim-do-dia.jpg`).
3. **tablet e Salão**: a folha da comanda no tablet e Ajustes › Salão.

## O que entrou (PR 1)
**Casca:** `data-suite="v3"` no shell de operador (a tela do cliente fica fora: é do cliente).
`PosFunctionRail` passa a montar o `OperatorSuiteRail` do kit com as seções da prévia
(Comandas F2 com o selo das em uso, Encomendas com o selo das de hoje, Caixa com o ponto
quando o turno está fechado, Tela do cliente) e, no pé, Terminal (saúde + Atualizar no mesmo
painel), Avisos (sino do kit, novo no PDV), Atalhos, Bloquear e o operador. No celular, as
mesmas seções na barra do polegar (`place="bar"`), lidas do estado que o rail publica (uma
leitura das Encomendas por tela). As seções são puras (`presentation/sections.ts`).

**Venda (`pos-sale.jpg`):** barra de contexto de 56px (voltar, Balcão | Encomendas
segmentado, a comanda com o lápis, Cliente F6, Recebimento F7, Quando F8 tracejado enquanto
"Agora", o ao vivo do kit, Últimas vendas e "Liberar comanda" com texto). Busca da suíte
(borda primária em foco, "Enter adiciona", F3 e /), densidade segmentada à vista, coleções em
chips de 32px com o ponto na cor da coleção. Tile da prévia (faixa de 92px na cor da coleção,
ícone, SKU, nome e preço; "Esgotado" em pílula ao lado do preço; foto que falha volta ao
desenho da coleção). Comanda: cabeçalho com "N itens · em M linhas", Selecionar (Alt S) e
Enviar à cozinha (F9, com a contagem); linhas qtd × nome × total, com o fato numa linha só
(observação, preço com desconto, peso, cozinha com a hora do envio); editor da linha sob
demanda colado no pé (Editando X · R$ cada, − n +, Remover Del, Fechar Esc, Desconto e
Observação); dica do teclado físico; Pagamento F4 numa faixa só com o total dentro. Modo
seleção: o cabeçalho vira a barra do lote, com Transferir (F10) levando as linhas marcadas
para o diálogo, Desconto e Remover.

**Sessão de caixa e Encomendas:** cabeçalho de uma linha do kit (`OperatorPageHeader`).

**Kit (aditivo, só camada da suíte):** `RailSection` sem o `px-0.5` e sem quebrar palavra no
meio (a prévia `.rail-item` tem 64px sem respiro: "Encomendas" virava "Encomenda / s").

## O que entrou (PR 2: Fim do dia, `fim-do-dia.jpg`)
`/session/closing` vira o corredor da v4: cabeçalho "Fim do dia" (selo, ao vivo, terminal,
Sair), os três passos no topo com estado e nunca valor (1 Fechar caixa, 2 Contar a vitrine,
3 Fechar o dia). Passo 1: estado da gaveta pela Projection do terminal e a porta "Fechar
caixa", que abre direto a contagem cega da Sessão de caixa (`/session?close=1`). Passo 2: a
CONFERÊNCIA cega por produto (vazia, Enter avança, dica do item que falta), com o selo preso
ao pé que ecoa o contado ("Contei N peças · Revisar e fechar o dia"). Passo 3: caixa (estado,
"Fechamento às cegas: valores só na auditoria"), vitrine em PEÇAS (ficam para amanhã, viram
perda, lote misto) calculadas só do que se contou e da classificação do lote, produção
(automático), **"Explicar o dia estranho"** para cada episódio que o sistema notou
(`pending_episodes`, chips do catálogo `OperationEpisodeKind`, "Não houve nada", detalhe
livre) gravado pela rota que já existia (`closing/episodes/<id>/`), e o selo "Fechar o dia"
com a consequência escrita embaixo. Sem R$ em nenhum passo.

## O que entrou (PR 3: tablet, `pos-tablet.jpg`)
Abaixo do desktop (< 1024px: tablet em pé e celular) a comanda vira a **folha de baixo**:
fechada, o resumo ("N itens · R$ total" e o fato da cozinha) e o **Pagamento na zona do
polegar**; puxada (alça, resumo ou chevron), o cabeçalho com Selecionar e Enviar à cozinha,
as linhas, o editor e o numérico (no toque, só ao tocar a linha), com o fundo escurecido
que recolhe ao tocar. A grade ganha a tela inteira (4 colunas no tablet em pé). No celular a
folha fica acima da barra do polegar. Em dispositivo de toque as teclas impressas somem
(SPEC4 §7; o atalho segue valendo). Desktop e tablet deitado (≥ 1024px) seguem com a coluna.

**Ajustes › Salão (`salao-mesas.jpg`): não entrou, e o que falta é dado.** O cadastro do
salão já existe no Admin (`backstage.SeatingSpot`: rótulo, tipo, área, lugares, "conta na
capacidade oficial", existe desde/até) e o B.I. já mede a lotação com ele
(`services/room.py`). Para o editor visual faltam: (1) **posição e forma** da mesa na
planta (x, y, giro, redonda/quadrada/comprida/banqueta), que não existem no model; (2) uma
**API** de leitura/gravação para o PDV (hoje só o Admin escreve) com a regra de tempo
(`active_from`/`active_until`: mudar vale de hoje em diante) e permissão de gestor; (3) o
andar **Ajustes** no rail do PDV (item do pé, como na prévia) com Terminal, Impressoras,
Maquininhas, Salão, Envio à cozinha e Atalhos de venda. Os itens (1) e (2) pedem migração
no app `backstage` (não é Core) e a decisão de quem pode mexer no salão.

## Função (não regride)
Todas as teclas seguem (F2 a F10, ?, Alt S, Esc, setas, Del, 0 a 9). O que mudou de lugar:
Atalhos e Terminal foram para o pé do rail (no celular, Atalhos fica na barra de contexto);
Atualizar mora no painel do Terminal (um toque a mais, ao lado da saúde); Transferir saiu do
pé da comanda para o modo seleção (F10 continua em toda a venda); o numérico da tela aparece
no desconto e nos dispositivos de toque (no balcão, o teclado físico digita a quantidade);
o unitário "R$ cada" aparece no editor e nas linhas com desconto ou peso. Novos gestos de
teclado da prévia: Esc fecha o editor, Del pede a remoção da linha ativa, ↑↓ trocam a linha
do editor. Desconto com PIN do gerente, edição de encomenda, NFC-e, PIX pendente, gaveta,
cancelamento, tela do cliente e SSE intactos.

## Fora daqui (com nome e motivo)
- "vai à cozinha" nas linhas novas: a linha não diz se tem preparo (sem campo de estação no
  `POSCartItem`); hoje o estado aparece só depois do envio.
- Interruptor "envio automático por estação": não existe dado nem serviço (decisão do dono
  §5.1, desligado por padrão).
- "Mesa 6" como nome da comanda: a comanda tem só a referência (`#1007`).
- Atalho impresso no item do rail ("F2" sob Comandas): o `RailSection` anuncia a tecla, não a
  imprime (o rail é estreito).
- Tablet da prévia sem rail (seções numa barra embaixo: Comandas, Encomendas, Retirada, Fim
  do dia, Mais): o PDV mantém o rail da suíte do tablet para cima, como os outros apps.
- Fluxo do tablet como segundo posto (PIX/Maquininha na folha, "Dinheiro: enviar ao caixa",
  "Ler código" pela câmera): o posto Atendimento existe (#1429), mas não há serviço que
  mande a cobrança em dinheiro do tablet para a fila do Caixa; a folha cobra pelo mesmo
  Pagamento de sempre. Abrir gaveta pelo tablet fica para a frente do relay (decisão do dono).
- Fim do dia, passo 1 dentro do corredor (contador de cédulas em tela cheia com o numérico):
  a contagem cega da gaveta segue no diálogo da Sessão de caixa (mesmo contador por cédula);
  o corredor leva até ele.
- "Caixa conferido · dentro da tolerância": não existe veredito de tolerância no servidor
  (o fechamento da gaveta não devolve nada ao operador, de propósito). O passo 3 diz só
  "Caixa fechado · contagem cega registrada". Falta decidir a tolerância (decisão do dono).
- Gráfico por hora "hoje × sábado típico" no dia estranho: o episódio traz só o sinal em
  texto; não há série por hora projetada para o fechamento.

## Prova visual
`scratchpad/ux/v4-pdv/index.html` da sessão coordenadora (+ `img/`).
