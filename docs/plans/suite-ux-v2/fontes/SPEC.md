# Prévias "depois" — especificação comum (leia inteiro antes de desenhar)

Objetivo: prévias estáticas (HTML → PNG) de como cada tela-chave dos apps de OPERADOR do
Shopman fica depois da reforma de UX/UI. Pedido do dono: padronizar experiência, aparência,
layout, controles, busca, filtros, ações e opções para a suíte parecer UM produto, atendendo
cada caso de uso. **Nenhuma funcionalidade pode regredir**: toda ação, filtro, atalho e
informação da tela atual tem que continuar existindo na prévia (visível, num menu ⋯, num
painel, ou citado na legenda como "continua em X"). Direção: EVOLUÇÃO do visual atual
(mesmos tokens, marca latão sobre papel Faubourg), não uma identidade nova.

## Ferramenta
- Diretório: `/tmp/claude-0/-home-user-django-shopman/6667231e-7b74-5246-8272-59b33d376d49/scratchpad/ux/mock`
- Escreva `src/<nome>.html`; renderize com `cd <mock> && node build.mjs <nome>` (sem `.html`).
  Gera `out/<nome>.png` (limpa, recortada no tamanho do viewport) e `out/<nome>.annotated.png`
  (com pinos e legenda). Abra o PNG com Read e itere até ficar bom (nada cortado, nada
  quebrando linha feio, nada sobreposto).
- Tailwind v4 com os tokens REAIS do operator-kit (`bg-background`, `bg-card`, `text-foreground`,
  `text-muted-foreground`, `bg-primary`, `text-primary-foreground`, `bg-secondary`, `bg-muted`,
  `bg-accent`, `border-border`, `border-input`, `bg-rail`, `text-rail-foreground`, `text-success`,
  `text-warning`, `text-info`, `text-destructive` + `/12` etc.). `h-control`/`size-control` = 44px,
  `h-action` = 48px. Fonte Instrument Sans já embutida. Tema escuro: coloque `class="dark"` no `<html>`.
- Ícones Lucide: `<i data-i="nome-do-icone" class="size-4"></i>` (sem conteúdo, nesta forma exata).
  Nomes do Lucide (ex.: search, plus, ellipsis, ellipsis-vertical, chevron-down, list-filter,
  arrow-down-up, columns-3, table-2, layout-grid, refresh-cw, download, printer, bell, keyboard,
  clock, check, x, circle-check, triangle-alert, info, store, globe, bike, message-circle, chef-hat,
  cooking-pot, package, package-check, truck, timer, calendar, banknote, credit-card, qr-code, user,
  users, croissant, wheat, flame, star, megaphone, send, chart-no-axes-combined, trending-up,
  trending-down, wallet, receipt, scan-line, file-text, scale, layers, tag, sparkles, history,
  settings-2, lock, volume-2, monitor, shopping-basket, square-kanban, clipboard-list).
- Partials: `{{> rail initials="AD" operator="Admin"}}` (rail da suíte 64px; o app ativo vem do
  `data-app` no `<body>`: pos, kds, orders, production, purchase, marketing, bi, hub) e
  `{{> global time="22:03" bell="7"}}` (busca na suíte Ctrl K + "Ao vivo hh:mm" + sino + atalhos).
- Classes tipográficas propostas (já existem no CSS): `op-display`, `op-figure`, `op-title`,
  `op-body`, `op-label`, `op-micro`, `op-eyebrow`, `tnum`.
- `<meta name="viewport-size" content="1440x900">` no `<head>` define o tamanho (use 1280x800
  para KDS e Produção-chão se fizer sentido; padrão 1440x900).

## Referência obrigatória
Copie a estrutura de `src/orders-board.html` (Gestor · Pedidos, já aprovado como padrão) e veja
`out/orders-board.annotated.png`. Ela define a ANATOMIA ÚNICA:

1. **Rail da suíte** (partial `rail`) à esquerda, 64px — troca de app; o atual aceso na cor dele.
   (Hoje o rail é por app e fica recolhido/oculto; KDS e Produção-quiosque podem escondê-lo
   em tela cheia, mas a prévia mostra com rail.)
2. **Barra de seções** (h-16, `bg-card`, borda inferior): selo do app (quadrado 32px com
   `style="background:var(--app-color)"` + ícone branco) + nome curto do app; abas de seção
   (aba ativa: `bg-secondary` + `shadow-[inset_0_-2px_0_var(--primary)]` + `font-semibold`;
   inativas `text-muted-foreground`); tecla na aba quando houver atalho (`<kbd>`); à direita,
   controles DO APP (ex. som, período global) e depois o partial `global`.
3. **Barra de trabalho** (py-2.5, borda inferior, `bg-background`): busca LOCAL desta lista à
   esquerda (label com ícone, placeholder, `<kbd>/</kbd>` ou a tecla do app), chips de filtro
   (`rounded-full`, h-control, ativo = `border-primary bg-primary/10` com check), "+ Filtro"
   tracejado para dimensões extras; à direita: Ordenar (botão com chevron), controle
   segmentado de visão (`bg-secondary p-1`, item ativo `bg-card shadow-sm`), menu ⋯ para ações
   raras, e a AÇÃO PRIMÁRIA da tela (botão `bg-primary`) por último quando existir.
4. **Conteúdo**: cards `rounded-lg border bg-card p-3.5` ou tabela padrão (cabeçalho
   `op-eyebrow text-muted-foreground` sobre `bg-muted/60`, linhas h-14 com borda, coluna de
   ações no fim com botão principal + ⋯). Seções com título `op-eyebrow` + contagem.
5. **Status**: pílula única `h-6 px-2 rounded-full bg-<tom>/12 text-<tom> op-micro font-semibold`
   com ponto `size-1.5 rounded-full bg-<tom>`; tons: info, success, warning, destructive,
   primary, neutro (`bg-muted text-muted-foreground`). Nunca cores do Tailwind cru.
6. **Estados**: vazio = caixa tracejada com ícone em círculo, título `op-title`, explicação;
   erro = `bg-destructive/8 border-destructive/30` com o que aconteceu + o que fazer + botão
   "Tentar de novo"; desatualizado = `bg-warning/10` "Sem conexão — o que está na tela é de 21:58."
7. **Ação em lote**: barra flutuante no rodapé (`bg-foreground text-background rounded-xl`)
   "N selecionados" + ações + "Limpar".
8. **Diálogos/painéis**: painel lateral direito (sheet) para detalhe/edição; diálogo central
   com título, frase de consequência, rodapé (secundário à esquerda, primário à direita).

Anotações: no fim do HTML (depois do container principal) coloque pinos
`<span class="pin" style="left:Xpx;top:Ypx">N</span>` em cima dos pontos de mudança, e depois do
container um `<div class="legend">` com `<p class="t">App · Tela <span>proposta · …</span></p>` e
itens `<div><b>N</b>texto</div>` (6 a 8 itens, frases curtas, português, SEM travessão longo
"—" no texto de UI). O container principal precisa ter `relative` e altura fixa igual ao viewport.

## Regras de copy (do repositório)
- Texto de tela em português; "dispositivo" e "maquininha", nunca "aparelho"; "lote" (não
  fornada) nos apps de operador; "Tentar de novo"; "Atualizar"; "Visto" para dar ciência.
- Sem travessão longo em texto de UI (use ponto, vírgula, dois-pontos, parênteses).
- Dados realistas do seed Nelson Boulangerie (Croissant, Baguette de Tradition, Pain au
  Chocolat, Brioche, Bichon au Citron, Shokupan, Madeleine, clientes Maria Santos, João Oliveira,
  Ana Ferreira, Café Parisiense…).

## Entregue ao final
Uma lista curta: arquivos gerados, e para cada tela o que mudou + onde ficou cada função que
existia antes (para o inventário de não-regressão). Não mexa em nada fora do diretório `mock`.
