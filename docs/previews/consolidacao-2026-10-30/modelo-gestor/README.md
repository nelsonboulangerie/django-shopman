# Modelo de navegação no Gestor (prévia, 31/10/2026)

Primeira prévia do modelo aprovado pelo dono em 31/10 (`../mapa/modelo.html`). Somente
prévia: nada em `surfaces/`, Core ou backend. Sem merge, sem deploy.

- **A**: `origin/main` + `gestor-compact/apply-conn-sim.mjs` (porta 4311, simulador 38920).
- **M**: A + `gestor-compact/apply-compact.mjs` (a linha do chão de 30/10) + `apply-modelo.mjs`
  (porta 4315, simulador próprio 38921 com a projeção da Central).

Só a navegação muda. A fila, o cartão e o detalhe do pedido ficam como no main. As
mudanças de função do Gestor em hiperfoco (`../gestor-hiperfoco/`) NÃO entram aqui.

## O que muda

1. **O selo abre o trocador** (o kit, vale para todo app que usar o shell): seções deste
   app agrupadas por forma (no posto, escritório, na parede), os outros apps com a
   pendência de cada um, a Central, e quem opera com "Trocar ou bloquear". Celular e tablet:
   folha de baixo. Computador: painel da esquerda, aberto pelo selo do topo da barra lateral.
2. **Sem ☰** no celular e no tablet. O selo está sempre na barra.
3. **Forma chão** (Pedidos, Saída, o pedido aberto, Rotinas): sem barra de seções embaixo.
   Na linha de cima, o selo diz o app e o lugar ("Gestor · Pedidos ▾") e a busca vira ícone
   (o termo ativo segue na faixa de baixo, como na prévia de 30/10).
4. **Forma escritório** (Histórico, Catálogo, Clientes, Canais, Postos): a barra de baixo
   mostra as seções do escritório; "Mais" abre o trocador.
5. **Computador**: a barra lateral fica como está; só o selo do topo dela abre o trocador.

## Medido (Playwright, 390×844, 820×1180, 1440×900)

Sem rolagem horizontal em nenhuma das 10 capturas (A e M). Os pares lado a lado estão no
scratchpad da sessão (`m1/cmp-*.png`), enviados ao dono.

## Limites desta prévia

- As pendências dos outros apps são fictícias (simulador). No produto vêm da mesma projeção
  da Central (`/api/v1/backstage/hub/`), que já existe.
- PDV, Cozinha e Compras abrem as prévias de 30/10 desses apps, que ainda não têm o
  trocador. Produção, Marketing e B.I. não têm prévia no ar: levam à Central.
- O cabeçalho do Catálogo no celular já está quebrado no main (selo ou ☰ empilhado sobre o
  título e as ações). Não é desta prévia; vai para a rodada do Catálogo.
- "Pedir ao gerente pelo celular" (aprovado) não está nesta prévia: é recurso de servidor.

## Reproduzir

```
node ../gestor-compact/apply-conn-sim.mjs <cópia>/surfaces/orders-nuxt
node ../gestor-compact/apply-compact.mjs <cópia>/surfaces/orders-nuxt
PREVIEW_CENTRAL=<url> PREVIEW_POS=<url> PREVIEW_KDS=<url> PREVIEW_PURCHASE=<url> \
  node apply-modelo.mjs <cópia>/surfaces/orders-nuxt
ORDERS_VISUAL_CLIENT_ONLY=1 NUXT_DJANGO_BASE_URL=http://127.0.0.1:38921 \
  NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:38921 npx nuxt build
MOCK_PORT=38921 node tests/visual/mockBackend.mjs &
NUXT_PUBLIC_OPERATOR_HUB_URL=<url da Central> PORT=4315 node .output/server/index.mjs
```

## Alternativas (31/10): aviso de pedido novo, som bloqueado e linha de cima do chão

`apply-alternativas.mjs`, depois de `apply-modelo.mjs`. O link escolhe: `?v=a|b|c`.
**O dono escolheu b (31/10): é o padrão sem parâmetro.** Escolha de prévia, não autorização
para implementar.

- **a**: como a prévia do modelo: faixa no topo ("Pedido novo. Som bloqueado." + som + Visto),
  linha de cima com moldura (Filtro, Busca, ⋮).
- **b**: o aviso vira uma pílula no polegar ("Pedido novo · H58", Ver, Visto), sem empurrar
  a fila. O som pede um toque uma vez ao abrir ("Toque para começar"): o navegador só deixa
  tocar som depois do primeiro toque, e qualquer toque já liga. Linha de cima sem moldura;
  Filtros entra no ⋮.
- **c**: sem aviso separado: a aba Entrada acende com "novo", e o som para quando você abre a
  Entrada. Muda a regra do Visto (abrir a Entrada passa a valer como Visto): pede o sim do
  dono. Som e linha de cima como em b.

No simulador (navegador sem som), o "Som bloqueado" de **a** não some depois do toque; no
aparelho some.
