# V4-PDV: o PDV igual à prévia v4 (último app da onda)

- **id:** V4-PDV
- **branch:** claude/v4-pdv (PR 1: casca + Venda)
- **PR:** (preenchido na abertura)
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
- Celular: a venda segue em pilha (grade e comanda embaixo); a folha da comanda é do PR 3.

## Prova visual
`scratchpad/ux/v4-pdv/index.html` da sessão coordenadora (+ `img/`).
