# V4-HUB2: estado dos blocos da Central, ponto verde e nome curto

- **id:** V4-HUB2
- **branch:** claude/v4-hub2
- **PR:** #1461
- **estado:** PR aberto, auto-merge (onda V4, merge autorizado pelo dono)
- **início (UTC):** 2026-10-04

## Objetivo
Continuação da V4-HUB (#1454): o que a prévia v4 (`hub.jpg`) mostra nos blocos e a Central
ainda não dizia, lido das fontes reais, sem número inventado.

## O que entrou
**Backend (`projections/hub_queue.py`, `projections/hub.py`), só estado, sem item novo na fila:**
- PDV: "Caixa aberto" (`cashman.Shift` aberto; nunca valor) ou "Caixa fechado", antes das encomendas.
- Compras: "N pedidos para enviar" (marca `approved`, pede alguém) e "N pedidos a caminho"
  (marca `sent`, agrupada por `request_ref`), a mesma marca que o quadro do Compras lê.
- Marketing: "N decisões" (a fila do app, `marketing_decisions.build_decision_queue`, #1420) e
  "N campanhas ligadas". Vale para quem abre o Marketing; o item "Anúncio para decidir" na fila
  segue só para quem pode aprovar.
- B.I.: "28D: R$ 208,6 mil (−11%)", o faturamento conciliado da série diária na janela padrão do
  app contra a anterior, guardado 5 min no cache (a Central relê a cada 30 s). Nada de caixa.
- Loja: "Aberta" (horário do `Shop` e canal da loja ligado), "Aberta, pedidos online desligados"
  ou "Fechada · abre amanhã às 9h", e "N pedidos hoje" (canal da loja, sem cancelado/devolvido).
- Contrato do bloco: `status_positive` (o estado bom e sabido). Cada fonte de estado usa o mesmo
  predicado que mostra o bloco do app.
- Nome curto: `shortLabel` em `app-identity.json` ("Gestor"), espelhado em `_AppSpec.short_label`
  e travado por `test_hub_projection_identity`. A fila usa o curto; o bloco segue com o inteiro.

**Central:** ponto âmbar (pede alguém), verde (`status_positive`, sem nada pedindo; contraste
4,97:1 no claro e 6,6:1 no escuro) ou neutro; a frase sempre escrita. O gesto da fila tem 164px
fixos no tablet e no desktop, e o rótulo longo quebra em duas linhas dentro do botão.

## Fora daqui (com nome e motivo)
- "Na doca" (Compras): não há registro de chegada antes da conferência (o rascunho de recebimento
  é da sessão de quem confere). Precisa de um evento de chegada, que é decisão de produto.
- "A caminho" conta o `sent` que só se fecha na entrega depois do #1418 (aberto). Até ele entrar,
  pedido já recebido continua contando como a caminho.

## Prova visual
`scratchpad/ux/v4-hub/index.html` da sessão coordenadora, seção V4-HUB2 (+ `img/v2-*`).
