# SUITE-UX-V2-PLAN: oito apps, um produto

**Proposta de 03/10/2026, para validação do dono antes de qualquer código.**
Escopo decidido por ele na mesma conversa: **só os apps de operador** (PDV, Cozinha, Gestor,
Produção, Compras, Marketing, B.I. e Shopman Apps). **A Loja e o Admin/Unfold ficam de fora.**
Direção visual: **evolução** do que existe (mesmos tokens, latão sobre papel Faubourg), com
espaço para ideias novas, que estão separadas no §6 para ele aceitar ou recusar uma a uma.

Regra que vale para o plano inteiro: **nenhuma funcionalidade regride.** Toda ação, filtro,
atalho, informação e estado que existe hoje continua existindo; a reforma só muda o lugar e
a forma. O §5 diz como isso é garantido por mecanismo, não por cuidado.

Este plano **continua** o [SUITE-UX-PLAN](SUITE-UX-PLAN.md) (22/09/2026), não o substitui. O
diagnóstico de lá segue válido; o WP-UX-1 está entregue e os WP-UX-3, 4 e 7 estão em
execução. O que este documento acrescenta: a medição de hoje, a proposta visual com prévias,
os padrões por intenção (busca, filtro, ação, opção…) e a trava de não-regressão.

As prévias estão em [`suite-ux-v2/`](suite-ux-v2/): `comparar-*.jpg` põem lado a lado a captura
real do app rodando com o seed ("Hoje") e a proposta; `depois-*.annotated.jpg` são as propostas
com pinos numerados e legenda. As propostas foram montadas com os tokens reais do `operator-kit`
(`operator-theme.css`), a fonte Instrument Sans e os ícones Lucide. ⚠️ Nas capturas reais as fotos de produto e os ícones PWA aparecem
quebrados porque o ambiente de captura não tem as imagens do catálogo nem os ícones gerados;
não é defeito da tela.

---

## 1. O que a medição de 03/10 encontrou

Quatro varreduras independentes (kit, PDV/Cozinha/Produção, Gestor/Hub/Compras,
B.I./Marketing) mais as capturas das telas. O resumo:

| tema | hoje |
|---|---|
| Cópias de primitivas | 7 árvores `components/Ui/` (~270 arquivos), Dialog e Sheet com 3 variantes cada; o kit depende em silêncio da cópia do app hospedeiro (`OperatorReasonDialog` usa o `UiDialog` de quem o monta) |
| Botão | Gestor: 146 `<button>` à mão e 0 `UiButton`; Compras: 67; B.I.: botões de 36 px |
| Cabeçalho | 7 cabeçalhos diferentes; `OperatorAppBar` cobre 5 apps; PDV, Cozinha, Produção e Hub montam o seu |
| Barra de trabalho | `UiToolbar` e `UiFilterChip` só no Gestor; busca em 4 implementações; `type="search"` cru em 5 apps; B.I. e Hub sem busca |
| Controle segmentado | não existe peça: ~46 `aria-pressed` fazendo o papel, com 3 estilos de "ativo" (contorno, cheio, sombra) |
| Menu ⋯ / popover | à mão no Gestor (ordenar, sino de alertas) e no B.I. (Explorar), sem Esc nem foco |
| Overlays à mão | ~11 `fixed inset-0` sem trap de foco nem scroll-lock; "Close" em inglês no Dialog de 3 apps |
| Estados | nenhuma peça de vazio, esqueleto ou campo no operador; ~114 "Nenhum…" literais; "Carregando…" em texto em 4 apps |
| Status | 6 mapas de cor em 3 vocabulários; paleta crua do Tailwind (Gestor 28, Marketing 29, Produção 13 hex) |
| Sino | 4 implementações (duas com o mesmo nome `AlertsBell.vue`, arquivos diferentes) |
| Tipografia | a escala `display/figure/title/body/label/micro` continua só como comentário em `operator-base.css` |
| Tempo real | SSE no PDV, Cozinha, Gestor e Marketing; Produção só em poll; B.I. e Compras sem nada; 3 jeitos de mostrar "ao vivo" |
| Navegação | Compras guarda seção e aba em `useState` (sem URL, sem voltar); o período do B.I. não vai para a URL |

O inventário funcional completo de cada tela (cada ação, filtro, atalho e estado) está no
apêndice A. Ele é a lista que a trava de não-regressão confere.

---

## 2. A proposta em uma frase

**O operador aprende a suíte uma vez.** Toda tela é montada com as mesmas quatro faixas e as
mesmas peças; o que muda de um app para outro é o trabalho, não o jeito de fazê-lo.

![Anatomia](suite-ux-v2/depois-gestor-pedidos.annotated.jpg)

### 2.1 A anatomia (cinco faixas, sempre na mesma ordem)

```
┌──────┬─────────────────────────────────────────────────────────────────────┐
│ RAIL │ BARRA DE SEÇÕES   selo do app · seções · controles do app · GLOBAL   │ quem sou, onde estou
│ da   ├─────────────────────────────────────────────────────────────────────┤
│ suíte│ BARRA DE TRABALHO busca local · filtros · ordem · visão · ⋯ · AÇÃO   │ o que estou olhando
│      ├─────────────────────────────────────────────────────────────────────┤
│ apps │ CONTEÚDO          cards · tabela · quadro · painel lateral           │ o trabalho
│ op.  ├─────────────────────────────────────────────────────────────────────┤
│ lock │ RODAPÉ            barra de lote · ação fixa · MoreBelow              │ o próximo passo
└──────┴─────────────────────────────────────────────────────────────────────┘
```

1. **Rail da suíte** (`OperatorRail`, evoluído): troca de app com os oito ícones, o atual aceso
   na cor de identidade dele (`app-identity.json`), ponto de atenção no ícone de quem precisa de
   você; embaixo, tema, bloquear e o operador. A navegação **dentro** do app sai do rail e vai
   para a barra de seções (hoje PDV, Cozinha, Produção e Compras usam o rail para isso).
2. **Barra de seções** (`OperatorAppBar`, já entregue): selo do app + seções com contagem e tecla
   na própria aba. À direita, os controles **do app** (som da Cozinha e do Gestor, período do
   B.I., saúde do terminal do PDV) e a **faixa global**, igual em todo app: busca na suíte
   (Ctrl K), "Ao vivo hh:mm" (substitui as faixas "Última leitura útil"), um sino só, atalhos.
3. **Barra de trabalho** (`UiToolbar`): busca **desta lista** à esquerda com a tecla ensinada,
   filtros como chips com contagem, "+ Filtro" para dimensões extras (`FilterBar`); à direita,
   ordenar, controle segmentado de visão, menu ⋯ e, por último, a ação primária da tela.
   Uma segunda linha opcional serve para recortes da lista (coleções do Catálogo, abas da Base
   do Compras).
4. **Conteúdo**: cards, tabela ou quadro, com as mesmas peças. Detalhe e edição em painel
   lateral (`UiSheet`); decisão em diálogo (`UiDialog`).
5. **Rodapé**: barra de lote flutuante quando há seleção; ação fixa quando a tela tem um
   próximo passo que não pode sumir (Pagamento no PDV, Salvar mínimos no Compras); `MoreBelow`.

Um app pode não ter uma faixa; nenhum app inventa uma sexta. Telas de parede e quiosque
(Painel de retirada, Letreiro, Tela do cliente) escondem rail e barras em tela cheia, como hoje.

### 2.2 Perfis de dispositivo (a mesma peça, ajustada ao uso)

| perfil | apps | o que muda |
|---|---|---|
| **Balcão, teclado primeiro** | PDV | tecla impressa em todo controle que tem atalho; foco nunca se perde; ação principal 48 px |
| **Parede/cozinha** | Cozinha, Painel de retirada | tema escuro por padrão, tipografia maior, alvos de 56 px, nada que dependa de hover |
| **Chão/tablet** | Produção, Compras (recebimento) | 44 px mínimo, teclado numérico na tela, painel de baixo (sheet) em vez de lateral no retrato |
| **Escritório** | Gestor, Marketing, B.I., Compras (base) | mesma régua de 44 px (o kit não tem modo denso, de propósito); mais colunas, não controles menores |

---

## 3. Padrões por intenção (um jeito canônico para cada coisa)

| intenção | padrão único | peça | hoje |
|---|---|---|---|
| **Buscar nesta lista** | campo na barra de trabalho, à esquerda, com a tecla impressa (`/`; `F3` no PDV); Esc limpa; o termo vai para a URL | `UiSearchInput` | 4 implementações, 5 apps com `type="search"` cru |
| **Buscar na suíte** | Ctrl K de qualquer tela: pedidos, produtos, clientes, insumos, telas e ações; cada resultado abre no app certo | `OperatorCommandPalette` (nova, §6) | não existe |
| **Filtrar** | chips com contagem para os 3 a 6 recortes mais usados; "+ Filtro" para o resto; filtro aplicado aparece como chip removível "Dimensão: valor ✕" e "Limpar filtros"; tudo na URL | `UiFilterChip`, `FilterBar` | chips em 1 app; selects soltos; checkbox como filtro |
| **Recortar a lista** (abas da mesma lista) | segunda linha da barra de trabalho | `UiSegmentedControl` (nova) | 3 estilos de aba |
| **Trocar visão** (quadro/tabela, grade/lista, densidade) | controle segmentado à direita da barra de trabalho; preferência por dispositivo | `UiSegmentedControl` | popover no PDV, botão-ciclo na Cozinha, botões no Gestor |
| **Ordenar** | botão "↕ Critério ▾" que abre menu de rádio | `UiMenu` (nova) | menu à mão sem Esc |
| **Período** | dia ou intervalo, sempre com o seletor do kit; na barra de seções quando vale para o app inteiro (B.I.), na de trabalho quando vale para a lista | `OperatorDayPicker`, `OperatorPeriodPicker` | select nativo na Cozinha |
| **Ação primária** | uma por tela, botão cheio, último à direita da barra de trabalho ou fixo no rodapé; no card, o botão largo de baixo | `UiButton` | ~86 estilos de botão |
| **Ação secundária frequente** | botão de contorno visível | `UiButton variant=outline` | — |
| **Ação rara** (exportar, imprimir, atualizar, apagar) | menu ⋯ da tela ou da linha, com a mesma tecla de antes; destrutiva por último, em vermelho, com confirmação | `UiMenu` | espalhadas na barra (o Gestor tem 10 botões nela) |
| **Ação em lote** | seleção por checkbox; barra flutuante "N selecionados · ações · Limpar"; revisão antes de confirmar quando muda preço ou publicação | `UiBulkBar` (nova, a partir da do Catálogo) | só o Catálogo tem barra; aceitar em lote sem confirmação |
| **Opções do item** | menu ⋯ na linha ou no card; detalhe no painel lateral | `UiMenu`, `UiSheet` | popover em um lugar, botão solto em outro |
| **Confirmar** | diálogo com título-pergunta, frase de consequência e o verbo do ato no botão ("Recusar pedido", nunca "OK"); desfazer (toast) quando o ato é reversível | `UiDialog`, `OperatorReasonDialog`, toast com Desfazer | 5 jeitos (modal, dois passos dentro do modal, inline fixo, `window.confirm`, nenhum) |
| **Status** | pílula de tom: info, em andamento, sucesso, alerta, erro, neutro; mapa único estado → tom/rótulo/ícone | `presentation/status.ts` | 6 mapas, 3 vocabulários |
| **Vazio** | ícone, título que nomeia o espaço, explicação, gesto quando houver | `UiEmpty` (nova) | ~114 literais |
| **Carregando** | esqueleto no formato do conteúdo | `UiSkeleton` (nova) | "Carregando…" em texto |
| **Erro** | o que aconteceu + o que continua valendo + o que fazer + "Tentar de novo" | `UiAlert` | 3 a 4 variantes por app |
| **Desatualizado** | "Sem conexão. O que está na tela é de 21:58." + Atualizar | `UiAlert tone=warning` + `onReconnect` | só 2 apps reconciliam ao voltar |
| **Ao vivo** | ponto + hora da última leitura na faixa global | `OperatorLiveStatus` (nova) | faixa de texto, ponto solto, nada |
| **Avisos** | um sino, com abas Alertas e Avisos | `NotificationBell` | 4 sinos |
| **Atalhos** | botão de teclado na faixa global e tecla `?`; ajuda lista as teclas da tela atual | `OperatorShortcutsHelp` (nova, a partir das 2 que existem) | só PDV e Produção têm ajuda |
| **Campo de formulário** | rótulo, obrigatório, dica, erro com `aria-describedby` | `UiField` (nova) | 8 dialetos |
| **Número de painel** | rótulo, número, delta em pílula de tom | `UiStatTile` (a partir do `StatTile` do B.I.) | 2 desenhos |
| **Tipografia** | 6 papéis com nome | `op-display`, `op-figure`, `op-title`, `op-body`, `op-label`, `op-micro` (+ `op-eyebrow`) | 2.287 combinações à mão |

![Kit](suite-ux-v2/depois-kit.jpg)

---

## 4. As telas-chave, antes e depois

Uma por app, como o dono pediu. Cada uma tem a captura de hoje, a proposta anotada e o de-para
de funções no apêndice A.

### 4.1 Gestor · Pedidos

![Gestor · Pedidos](suite-ux-v2/comparar-gestor-pedidos.jpg)

Proposta anotada: [`depois-gestor-pedidos.annotated.jpg`](suite-ux-v2/depois-gestor-pedidos.annotated.jpg) · inventário: apêndice A.1.

### 4.2 Gestor · Catálogo

![Gestor · Catálogo](suite-ux-v2/comparar-gestor-catalogo.jpg)

Proposta anotada: [`depois-gestor-catalogo.annotated.jpg`](suite-ux-v2/depois-gestor-catalogo.annotated.jpg) · inventário: apêndice A.2.

### 4.3 PDV · Venda

![PDV · Venda](suite-ux-v2/comparar-pdv-venda.jpg)

Proposta anotada: [`depois-pdv-venda.annotated.jpg`](suite-ux-v2/depois-pdv-venda.annotated.jpg) · inventário: apêndice A.3.

### 4.4 Cozinha · Estação de preparo (tema escuro)

![Cozinha · Estação de preparo (tema escuro)](suite-ux-v2/comparar-cozinha-estacao.jpg)

Proposta anotada: [`depois-cozinha-estacao.annotated.jpg`](suite-ux-v2/depois-cozinha-estacao.annotated.jpg) · inventário: apêndice A.4.

### 4.5 Produção · Produção do dia

![Produção · Produção do dia](suite-ux-v2/comparar-producao-dia.jpg)

Proposta anotada: [`depois-producao-dia.annotated.jpg`](suite-ux-v2/depois-producao-dia.annotated.jpg) · inventário: apêndice A.5.

### 4.6 Compras · Base › Insumos

![Compras · Base › Insumos](suite-ux-v2/comparar-compras-base.jpg)

Proposta anotada: [`depois-compras-base.annotated.jpg`](suite-ux-v2/depois-compras-base.annotated.jpg) · inventário: apêndice A.6.

### 4.7 Marketing · Campanhas

![Marketing · Campanhas](suite-ux-v2/comparar-marketing-campanhas.jpg)

Proposta anotada: [`depois-marketing-campanhas.annotated.jpg`](suite-ux-v2/depois-marketing-campanhas.annotated.jpg) · inventário: apêndice A.7.

### 4.8 B.I. · Vendas

![B.I. · Vendas](suite-ux-v2/comparar-bi-vendas.jpg)

Proposta anotada: [`depois-bi-vendas.annotated.jpg`](suite-ux-v2/depois-bi-vendas.annotated.jpg) · inventário: apêndice A.8.

### 4.9 Shopman Apps (início com estado)

![Shopman Apps (início com estado)](suite-ux-v2/comparar-hub.jpg)

Proposta anotada: [`depois-hub.annotated.jpg`](suite-ux-v2/depois-hub.annotated.jpg) · inventário: apêndice A.9.


---

## 5. A trava de não-regressão

"Nenhuma funcionalidade pode regredir" vira quatro mecanismos, todos rodando no CI.

1. **Inventário funcional como contrato.** Cada tela ganha um arquivo
   `surfaces/<app>/tests/inventory/<tela>.inventory.ts` com a lista fechada do que ela oferece:
   ações (com rótulo e tecla), filtros, visões, estados, canais de tempo real, permissões. O
   apêndice A é o rascunho desses arquivos. Um teste de componente monta a tela com dados de
   exemplo e confere que cada item está acessível por papel e nome (`getByRole`), inclusive os
   que moraram para dentro de um menu ⋯ (o teste abre o menu). Item que sai do inventário só
   sai com a decisão escrita no PR.
2. **Regra de PR "mover, nunca remover".** Todo PR da reforma traz a tabela "função antes →
   onde ficou" da tela que mexeu. Sem a tabela, o PR não entra na fila.
3. **Os testes que já existem continuam passando sem afrouxar**: unitários de `presentation/`,
   e2e com mock, sondas ao vivo do PDV (`test:live`, texto cortado), `guardrails.*` do kit,
   vocabulário e cópia. Os seletores dos e2e passam a ser por papel e nome, que sobrevivem à
   troca de markup.
4. **Retrato antes/depois por tela** com o Playwright visual que já existe (`test:visual`).
   Regra do repositório: só regera baseline quem tem o Chromium da CI, numa sessão só.

E duas travas novas de forma, para a deriva não voltar:

- `guardrails.primitives.test.ts`: recusa `<button>`, `<input type="search">`, `fixed inset-0`,
  `aria-pressed` e `role="tablist"` escritos à mão fora do kit, com lista de exceções que só
  encolhe (o mesmo modelo do `guardrails.pendingAction`).
- `guardrails.palette.test.ts`: recusa `text|bg|border-(red|amber|green|…)-\d00` e hex em
  template e em `presentation/`, aceitando só tokens.

---

## 6. Ideias além da evolução (o dono decide uma a uma)

As cinco abaixo não são necessárias para padronizar; são o que faria a suíte parecer um
produto só. Todas aparecem nas prévias para ele julgar vendo.

1. **Rail como trocador de apps.** Hoje o rail é por app e volta ao Hub por uma porta só. A
   proposta põe os oito apps no rail de todos, com o atual aceso e ponto de atenção.
   Consequência: a navegação interna do PDV, Cozinha, Produção e Compras sai do rail e vai
   para a barra de seções.
2. **Busca da suíte (Ctrl K).** Uma busca que acha pedido, cliente, produto, insumo, lote e
   tela, e abre no app certo com contexto. Começa lendo os endpoints de busca que já existem
   (pedidos, clientes, catálogo); não precisa de backend novo na primeira versão.
3. **Um sino só, com duas abas** (Alertas operacionais e Avisos pessoais), no lugar dos quatro.
4. **"Ao vivo" na faixa global** em todo app, no lugar das faixas "Última leitura útil",
   com o mesmo texto de desatualizado em todo lugar.
5. **Hub com estado** (já aprovado em 22/09, ainda não feito): cada tile diz o que espera por
   você e leva ao lugar exato; uma faixa "Precisa de você" junta o que é urgente nos oito apps.

---

## 7. Work packages

Mesma numeração do SUITE-UX-PLAN, para não duplicar frente. Cada WP é um PR (ou um por app
quando o diff passar de ~800 linhas), com o inventário da tela e a tabela "antes → onde ficou".

| WP | o quê | depende de | risco |
|---|---|---|---|
| **WP-UX-5** tipografia e status | `op-*` viram CSS de verdade; `presentation/status.ts` no kit; trava de paleta | — | baixo |
| **WP-UX-8** primitivas no kit | `UiButton`, `UiDialog`, `UiSheet`, `UiPopover`, `UiInput`, `UiTextarea`, `UiBadge` passam a ser do kit (uma cópia só); apagar as 7 árvores `Ui/`; "Fechar" em português; os ~11 overlays à mão migram | — | médio (mexe em tudo, mas é mecânico) |
| **WP-UX-6** campo, vazio, carregando | `UiField`, `UiEmpty`, `UiSkeleton`, `UiAlert` padrão de erro/desatualizado | WP-UX-8 | baixo |
| **WP-UX-2** barra de trabalho | `UiToolbar` + `UiSearchInput` + `UiFilterChip` + `FilterBar` + `UiSegmentedControl` (novo) + `UiMenu` (novo) + `UiBulkBar` (novo); estado na URL (Compras e B.I. incluídos) | WP-UX-8 | médio |
| **WP-UX-9** cabeçalhos ricos | PDV, Cozinha, Produção e Hub sobre o `OperatorAppBar`, com os slots de cada um | WP-UX-2 | **alto**: é onde mora o risco de regressão; retrato antes/depois obrigatório |
| **WP-UX-10** faixa global e rail da suíte *(novo, §6.1, 6.3, 6.4)* | `OperatorLiveStatus`, um `NotificationBell`, `OperatorShortcutsHelp`; rail com os oito apps | WP-UX-9, decisão do dono | médio |
| **WP-UX-11** busca da suíte *(novo, §6.2)* | `OperatorCommandPalette` lendo as buscas existentes | WP-UX-10, decisão do dono | médio |
| **WP-UX-7** (2ª metade) Hub com estado | projeção de estado por app no `hub.py`; tiles com deep link | WP-UX-10 | baixo |

Ordem dentro de cada WP: **kit primeiro, depois um app piloto, depois os outros.** Piloto
sugerido: **Gestor** (já usa `UiToolbar`, `UiFilterChip`, `FilterBar`, `ColumnPicker`; é o mais
perto do padrão e o que mais ganha com a limpeza de 146 botões à mão). PDV por último, porque é
o de maior risco operacional (balcão com cliente esperando) e o que mais depende de teclado.

---

## 8. O que é decisão do dono

1. **Aprovar a anatomia e os padrões** (§2 e §3), olhando as prévias.
2. **As cinco ideias do §6**, uma a uma. Se ele recusar o rail-trocador (§6.1), o rail fica
   como está e só a barra de seções se padroniza.
3. **Ordem e piloto** (§7): Gestor como piloto, PDV por último.

Nada aqui muda dado, URL de cliente nem regra de negócio; a reforma é só da camada de tela.

---

## Apêndice A: inventário funcional das telas-chave

Rascunho dos arquivos `*.inventory.ts` do §5. Cada linha: função de hoje → onde fica na proposta.
"⋯" é o menu de mais ações da tela; "faixa global" é a busca na suíte + Ao vivo + sino + atalhos.

### A.1 Gestor · Pedidos (`orders-nuxt/app/pages/index.vue`)

| hoje | proposta |
|---|---|
| Abas Pedidos · Catálogo · Clientes (com permissão) · Canais (ponto de atenção) | barra de seções, igual; contagem de pedidos na aba |
| Busca código/cliente/item, tecla `/` | barra de trabalho, `UiSearchInput` com `/` |
| Chips de canal com contagem e "Todos" | barra de trabalho, iguais |
| Chips Entrega / Retirada (alternam) | chip "Entrega/retirada" que abre as duas opções com contagem (FilterBar) |
| Ordenar Chegada / Urgência / Mais recentes (menu à mão), tecla `s` | botão Ordenar com `UiMenu`; `s` mantido |
| Quadro/Tabela (à mão), tecla `v` | `UiSegmentedControl`; `v` mantido |
| Exportar CSV, Imprimir, Atualizar (`r`) | ⋯ com as mesmas teclas |
| Ponto "Ao vivo" + faixa "Última leitura útil" | "Ao vivo hh:mm" da faixa global; desatualizado vira aviso padrão |
| Som (3 estados, inclusive bloqueado) e "Ciente" | controles do app na barra de seções |
| Sino de alertas (`AlertsBell`) + sino do kit | um sino só, abas Alertas e Avisos |
| Esc limpa filtros; tecla qualquer reconhece o som | mantidos |
| Card: selecionar, Atender/liberar, tempo, código, canal, cliente, itens, status, pagamento, total, progresso da OP, endereço, troco, maquininha na rua, prazo de confirmação | card padrão com os mesmos campos; status em pílula de tom |
| Card: Aceitar, Avançar/rótulo, Recusar, Acertar entrega, Receber na retirada, Maquininha voltou, Entregador voltou; bloqueio com motivo | botão largo do card (ação principal) + ⋯ do card para as demais; bloqueio tracejado com motivo, igual |
| Card: reimprimir DANFE, link NFC-e não autorizada, negociação iFood | ⋯ do card |
| Lote: Aceitar N, Avançar N, Limpar | `UiBulkBar` |
| Diálogos Recusar (motivos iFood / texto), Acertar dinheiro, Despacho, Entregador voltou | `UiDialog`/`OperatorReasonDialog`, mesmo conteúdo |
| Vazio por coluna, vazio por filtro com "Limpar filtros", erro | `UiEmpty` e `UiAlert` |
| URL guarda filtros; volta do detalhe restaura rolagem e foco | mantido |

### A.2 Gestor · Catálogo (`orders-nuxt/app/pages/catalog.vue`)

| hoje | proposta |
|---|---|
| Busca produto/SKU | `UiSearchInput` com `/` (tecla nova) |
| FilterBar (envio, canal, publicação, venda, estoque, PIM; pré-preenchida por `?surface=&sync=`) | "+ Filtro"; filtro aplicado como chip removível + "Limpar filtros" |
| ColumnPicker (cookie) | "Colunas", igual |
| Chips de coleção com contagem, arrastar para reordenar (ponteiro e setas), ✦ inteligente | segunda linha da barra de trabalho (recortes), mesmas funções |
| Contagens "131 produtos · 4 canais · 4 feeds", Atualizar | contagem do recorte à direita; Atualizar no ⋯ |
| Linha: seleção, foto (lightbox), nome, status, esgotado/pouco estoque, reenviar, SKU, preço, coleção, alça de arrastar | linha padrão com os mesmos itens; status em pílula de tom |
| ⋯ da linha: Editar detalhes, Pausar/Ativar em todos, Ocultar/Exibir, Dados para redes sociais, Reenviar | `UiMenu` da linha, mesmos itens |
| Célula: switch por canal, auditoria da pausa, popover de preço (Enter/Esc, conflito), ponto de sincronização | iguais |
| Lote: superfície, Pausar, Ativar, Preço… (Definir/Ajustar %/Ajustar R$, Revisar→Confirmar), Ocultar, Exibir, prévia de publicação | `UiBulkBar`, mesmas ações e revisão |
| Painel do produto (5 abas, Permitir compra, sugestão por IA, conflito, rodapé "N campos alterados") e `?sku=&tab=` | `UiSheet` com `UiSegmentedControl` nas abas; deep link mantido |
| Esqueleto, erro com retry, vazios, guarda de saída com rascunho | peças padrão; guarda mantida |

### A.3 PDV · Venda (`pos-nuxt/app/pages/index.vue`, `PosProductGrid`, `PosCartPanel`)

| hoje | proposta |
|---|---|
| Rail: Comandas, Sessão de caixa/Abrir caixa, Encomendas (badge), Tela do cliente, Atualizar, saúde do terminal | abas Comandas (F2) · Encomendas · Caixa; "Tela do cliente" e "PDV-01" (saúde: agente, impressora, gaveta, fiscal) como controles do app; Atualizar no popover do terminal |
| Voltar, Balcão/Encomendas, renomear comanda, Cliente F6, Recebimento F7, Quando F8, Liberar comanda (confirmação), PIX aguardando | barra de trabalho da venda, mesmas teclas; Recebimento e Quando só em Encomendas, como hoje |
| Atalhos (?), Últimas vendas | botão de atalhos da faixa global; Últimas vendas na barra de seções |
| Não salvo / descartar e atualizar; edição de pedido com descartar; alerta de fechamento | mantidos, em `UiAlert` padrão |
| Busca F3 (Enter adiciona, Esc sai; letra digitada começa a busca) | campo de 48 px com a dica "Enter adiciona · Esc sai" |
| Densidade Compacta/Padrão/Ampla (popover) | `UiSegmentedControl` visível |
| Chips de coleção | `UiFilterChip`, com a cor da coleção |
| Tiles, esgotado, sem foto, grupo com variantes, pesados, opções | iguais; esgotado em pílula neutra |
| Carrinho: Selecionar Alt+S, linhas, −/+, Remover (confirma + desfazer), detalhes, cartão da cozinha, desfazer envio, teclado de linha (Qtd, Desc %, Desc R$, Obs.), motivo de desconto | iguais |
| Total parcial, Enviar à cozinha F9, Transferir F10, Pagamento F4 / Salvar alterações | iguais; Pagamento como ação primária fixa |
| Todas as teclas globais e bloqueio de teclas sob diálogo/lock; leitor de ticket | mantidos (`utils/keyboardGuard.ts`) |
| Pagamento, resultado, Últimas vendas, sessão, fechamento, encomendas | fora desta prévia; seguem a mesma anatomia no WP-UX-9 |

### A.4 Cozinha · Estação (`kds-nuxt/app/pages/[ref].vue`)

| hoje | proposta |
|---|---|
| Eyebrow Preparo/Saída + nome; lista de estações em página própria | selo + nome; abas "‹ Estações" · Preparo · Saída com contagem |
| Relógio, dia de serviço (select) | barra de seções; dia com o seletor do kit |
| Contadores, busca, densidade, som (bloqueado), Visto, recuperar concluídos (Reabrir), Painel de retirada | contadores e densidade na barra de trabalho; som, Reabrir e Painel como controles do app (48 px); Visto vira aviso de pedido novo com botão grande |
| — | chips Todos · Retirada · Entrega · Atrasados (novos, opcionais) |
| Faixa "A fazer", cancelado com "Recebi o cancelamento", grade por urgência | iguais |
| Ticket: tempo, atraso, itens, sem estoque, Iniciar → Finalizar → Desfazer (5 s), prévia de data futura, bloqueio | iguais, botão de 56 px; status em pílula de tom |
| Toque no ticket abre o detalhe | mantido |
| Saída: Pronto por estação, Entregar/Despachar, ver itens, volumes | na aba Saída, mesma anatomia |
| Vazio "Tudo em dia" + "Ligar o som", busca vazia, erro com e sem dados (âmbar cru) | peças padrão em token |
| SSE + poll 15 s, bipe | mantidos; "Ao vivo" na faixa global |

### A.5 Produção · Produção do dia (`production-nuxt/app/pages/index.vue`, `ProductionStageGrid`)

| hoje | proposta |
|---|---|
| Etapas Planejamento/Preparação/Produção/Expedição, Alt+1…4 | abas da barra de seções com a tecla |
| "5 PRODUZIDOS" + barra 33% | figura de progresso à direita da barra de trabalho |
| Busca `/` | `UiSearchInput` |
| Timers (badge, pulsa) | controle do app na barra de seções; também no ⋯ |
| Sino de alertas próprio | sino da faixa global |
| Atualizar R, Atalhos ? | ⋯ e botão de atalhos |
| Dia (‹ › e seletor), "Todas as bases" | `OperatorPeriodPicker`; chip "Base: todas ▾" |
| — | chips Todos · A confirmar · Produzidos (novos) |
| Chip de unidades comprometidas → diálogo | "N un. encomendadas", abre o mesmo diálogo; também no ⋯ da linha |
| Produzido ✓ → diálogo com Estornar… | valor + "Ver lançamento"; ⋯ da linha com Corrigir e Estornar… |
| "Confirmar ›" → "Quanto foi produzido?" (lote, stepper, Enter, falta de insumo) | botão Confirmar, mesmo diálogo |
| Desatualizado (chip âmbar), vazio com CTA, busca vazia | aviso padrão e `UiEmpty` |

### A.6 Compras · Base › Insumos (`purchase-nuxt/app/pages/index.vue`)

| hoje | proposta |
|---|---|
| Painel/Comprar/Receber/Base em `useState` (sem URL) | abas com URL própria (`/base/insumos`) |
| Abas Insumos/Fornecedores/Custos/Contagem à mão | `UiSegmentedControl` na barra de trabalho |
| Busca crua, checkbox "Atenção" | `UiSearchInput` com `/`; chip "Atenção 120" |
| Pílulas 0 reposições / 120 sem preferencial / 0 estimados | faixa de resumo clicável sob a barra de trabalho |
| Tabela: SKU, insumo (tipo, receitas, chips), estoque, cobertura, mínimo editável, custo-base, status | tabela padrão; lista de receitas por extenso passa para o painel (a linha mostra a contagem) |
| Rodapé Limpar / Salvar mínimos | barra de ação fixa "N mínimos alterados · Limpar · Salvar mínimos" |
| Detalhe: avisos, Permitir revenda → preço → Colocar à venda, "Quando aberto, vira" (form), receitas | painel lateral fixo, mesmas funções |
| Fornecedores, Custos, Contagem (modal à mão de divergências) | mesma anatomia; o modal vira `UiDialog` |
| Sem SSE nem poll; Atualizar só na faixa de status | Atualizar no ⋯; "Ao vivo"/desatualizado na faixa global (WP-UX-10) |

### A.7 Marketing · Campanhas (`marketing-nuxt/app/pages/campaigns.vue`)

| hoje | proposta |
|---|---|
| Seções Hoje · Campanhas · Ofertas e cupons · Plataformas; sino próprio | barra de seções do kit; sino da faixa global |
| Cartão "Encontrar uma campanha": Buscar (debounce, `?q`), Situação, Plataforma, Limpar filtros | barra de trabalho: busca com `/` (mesmo debounce e `?q`), chips Todas/Ligadas/Desligadas com contagem, chip "Plataforma ▾", Limpar filtros |
| "Modelos", "Histórico completo" | ⋯ (com Atualizar e Atalhos) |
| "Nova campanha" | ação primária no fim da barra de trabalho |
| Linha: switch (com permissão e ocupado), linha abre edição, Preparar disparo, Automática, motivo de bloqueio, gatilho → destinos, público, agenda, desempenho | tabela padrão com colunas Campanha, Gatilho, Destinos, Público, Situação, Ações; bloqueio tracejado com motivo |
| Paginação 12/página | rodapé padrão de paginação |
| Faixa "criada" e destaque da linha; vazio, sem resultado, desatualizado; esqueleto; erro | peças padrão |
| Diálogos de edição, disparo e confirmação forte (senha/TOTP) | inalterados |
| Fonte própria, `rounded-xl`, títulos com eyebrow | Instrument Sans e `op-*`, como os outros apps |

### A.8 B.I. · Vendas (`bi-nuxt/app/pages/sales.vue`)

| hoje | proposta |
|---|---|
| 8 seções; período (presets dia → máx + intervalo, ‹ ›) compartilhado entre páginas, fora da URL | barra de seções; período como controle do app e na URL |
| Comparação implícita "vs período anterior" | "Comparar com: período anterior ▾" na barra de trabalho (explícita) |
| — | chips de canal, ⋯ com Exportar CSV, Copiar link do recorte, Atualizar, Fontes dos números (novos) |
| 4 KPIs com delta | `UiStatTile` padrão, delta em pílula de tom e o valor anterior escrito |
| Faturamento por dia (barras, traço do período anterior, pico, histórico Yooga em tom claro, legenda) | cartão de gráfico padrão; cores `--chart-*` |
| Nota de fontes em conflito | ⋯ "Fontes dos números" (ou linha de rodapé no cartão, se o dono preferir à vista) |
| Pedidos por hora, por dia da semana, por canal, top produtos | cartões padrão; canais pelo nome ("PDV", não "pdv") |
| "Carregando…" em texto; "Tentar de novo" de 36 px | `UiSkeleton`; botão de 44 px |

### A.9 Shopman Apps (`hub-nuxt/app/app.vue`)

| hoje | proposta |
|---|---|
| Cabeçalho à mão com "Olá, Admin" | barra de seções com selo, saudação, dia e loja |
| — | busca da suíte larga (ideia §6.2) |
| 8 tiles com ícone, nome e descrição; abre instalado ou no navegador | tile com cor do app, estado, número-chave e deep link; ícone diz se abre instalado ou no navegador |
| — | faixa "Precisa de você" com o urgente dos 8 apps (ideia §6.5, aprovada) |
| Avisos neste dispositivo; versão | cartões de rodapé, mesmo conteúdo |
| Login, bloqueios (estação, sem permissão, indisponível), nenhum app liberado, offline | inalterados; tiles seguem a permissão do operador |

### O que as prévias não desenham (e continua igual)

Diálogos internos (Quanto foi produzido?, Estornar, Recusar com motivos do iFood, Acertar
dinheiro, Despacho, confirmação forte do Marketing), as telas de Pagamento, Resultado, Sessão e
Fechamento do PDV, a Saída da Cozinha, Expedição/Planejamento/Receitas da Produção, Receber e
Comprar do Compras e as outras sete páginas do B.I. Elas entram na mesma anatomia nos WPs, e
o inventário de cada uma é escrito no PR que mexer nela, antes do código.
