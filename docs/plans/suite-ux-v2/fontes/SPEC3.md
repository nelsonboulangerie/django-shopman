# Prévias v3 — o que mudou depois do retorno do dono (leia SPEC.md antes; este arquivo prevalece)

Mesmo diretório/ferramenta (`node build.mjs <nome>`), mesmas regras de copy, pinos e legenda.
Referências v3 obrigatórias: `src/orders-board3.html` (+ `out/orders-board3.annotated.png`) e
`src/orders-search3.html`. NÃO edite arquivos `_*.html` compartilhados nem `_shared.css`
(outros agentes usam); se precisar de CSS próprio, ponha um `<style>` no seu HTML.

## Retorno do dono que motivou a v3
1. PDV: a v2 "perdeu" espaço vertical, sobretudo na área de itens do pedido.
2. Rail como trocador de apps tira o espaço das seções. → **As seções do app voltam para o
   rail**; o trocador vira **um botão** (o selo do app no topo do rail abre os 8 apps + Shopman
   Apps). Assim a barra de seções do topo some e sobra altura.
3. Dois campos de busca confundem. → **Uma busca só, uma tecla só** (`/`, e Ctrl K abre a
   mesma): filtra a tela ao digitar e oferece "Esta tela | App | Toda a suíte" no dropdown.
4. Um sino só: aprovado (vai para o pé do rail, "Avisos").
5. "Ao vivo" ocupava espaço demais → vira **ponto + hora** ao lado do título; só cresce quando
   desatualiza.
6. Shopman Apps com estado: aprovado na função, mas a aparência anterior (mais limpa) era melhor.
7. **Dispositivos**: cada app tem de ser finamente lapidado para o dispositivo em que é usado —
   teclado e tela grande no desktop; tela média, giro e toque no tablet; tela pequena, giro,
   toque, câmera, localização etc. no celular. "Ajuste de breakpoint e rearranjo de colunas é o
   mínimo do mínimo." O sistema deve entender ONDE o operador está e oferecer o máximo de
   recursos. Omotenashi-first (mobile-first embutido). Apps de campo (Compras, Produção) DEVEM
   ser plenamente úteis no celular.

## Anatomia v3 — desktop (teclado + tela grande)
- **Rail 76px** (`bg-rail`): partial `{{> rail3top app="Nome" icon="lucide"}}` (selo = trocador),
  depois as seções do app como `<a class="rail-item [on]"><i data-i="icone"></i>Nome<span class="badge">N</span></a>`
  (ou `<span class="attn"></span>` para ponto de atenção; `<kbd>F2</kbd>` opcional dentro), e no fim
  `{{> rail3bottom bell="7" initials="AD" operator="Admin"}}` (Avisos, Atalhos, Bloquear, operador).
- **Cabeçalho único** (`bg-card`, borda inferior): linha 1 = título da tela (`op-display !text-[22px]`)
  + `<span class="live-dot"></span>hh:mm` em `op-micro` + busca única
  `{{> search3 w="w-[22rem]" placeholder="…"}}` + controles da tela à direita (ordenar, visão,
  ⋯, ação primária por último). Linha 2 (só se a tela tiver filtros) = chips `h-10`.
- Telas com contexto próprio (venda do PDV) podem fundir as linhas.
- Teclas impressas em todo controle que tem atalho (desktop).

## Anatomia por dispositivo
### Tablet (toque, giro; 1180x820 deitado / 820x1180 em pé)
- Rail compacto (mesmo rail v3) ou, em pé, barra inferior de seções.
- Alvos de 48px (ação principal 56px); nada depende de hover; teclas impressas somem (sem
  teclado físico); pressão longa = menu de contexto; arrastar onde fizer sentido.
- Deitado: divisão lista + detalhe lado a lado. Em pé: lista inteira + detalhe em painel de baixo.
- Teclado numérico na tela onde há número (quantidade, valor, contagem).
- Tela acesa (wake lock) em estação fixa; giro travado quando o app pede (já existe no kit).

### Celular (toque com o polegar, giro, câmera, localização, vibração, push; 390x844)
- **Barra superior 56px**: selo do app (toque = trocar de app), título, ponto ao vivo, ícone de
  busca (abre a busca única em tela cheia com o alcance), sino.
- **Barra inferior de seções** (64px + área segura) com até 4 seções + "Mais".
- **Ação principal no alcance do polegar**: botão largo fixo acima da barra inferior.
- Listas em cards; deslizar o card para ações rápidas; puxar para atualizar.
- Filtros: linha de chips rolável + botão "Filtros" que abre painel de baixo (bottom sheet).
- Detalhe e formulário em painel de baixo ou tela cheia com "Concluir" no rodapé.
- **Recursos do aparelho do operador** (a palavra na UI é "dispositivo", nunca "aparelho"):
  câmera (ler código de barras/QR/chave de NF, EAN do insumo, etiqueta de lote, foto de nota em
  papel), vibração (confirmação e alerta), push (já existe), localização quando faz sentido
  (ex.: o Gestor sabe se o operador está na loja ou fora e mostra "resumo e decisões" fora),
  compartilhar (enviar comprovante/relatório), NFC do crachá para desbloquear (Android),
  lanterna no leitor.
- Um tema escuro opcional para chão de produção/forno, se ajudar.

### Moldura das prévias de dispositivo
Use `<div class="device"><div class="screen" style="width:390px;height:844px">…</div></div>`
(celular) ou `<div class="device tablet"><div class="screen" style="width:1180px;height:820px">…</div></div>`.
Canvas: ponha 2 ou 3 celulares lado a lado num `<body>` de fundo `#e9dfd6` (ou `bg-secondary`),
com título curto acima de cada um (`op-title`), e `viewport-size` do tamanho do conjunto
(ex.: 1320x1000 para 3 celulares). O container principal (com `relative`) tem a altura do
viewport; a legenda vem depois. Desenhe uma barra de status simples (hora 22:03, sinal, bateria)
e a área segura de baixo. Celular: fonte mínima 13px, alvos ≥ 48px.

## "Onde o operador está" (o motor de contexto proposto, para citar nas legendas)
`useOperatorContext()` no kit: classe de dispositivo (ponteiro fino/grosso, hover, tamanho,
giro), modo de entrada do momento (teclado → mostra teclas; toque → esconde e aumenta alvos),
estação provisionada (dispositivo fixo do balcão/cozinha) × dispositivo pessoal, local (na loja
× fora, com consentimento), conexão, hora do turno. Cada tela declara o que muda em cada caso.
