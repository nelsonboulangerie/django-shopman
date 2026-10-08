# WP-OPERADOR-NUXTUI-ONDAS: prompts das próximas sessões

Um prompt por app e um para cada PR de kit que ainda falta na onda 0. Cada prompt é autossuficiente: cole-o inteiro numa sessão nova. Antes de colar, confira no [plano](WP-OPERADOR-NUXTUI-ONDAS.md) (seção 9) se a frente ainda não tem dono, com `make inflight`, `gh pr list` e `git worktree list`. Frente com PR aberto **não** ganha sessão nova: escreva no PR que existe.

O bloco "REGRAS COMUNS" vale para todos e vai colado junto.

---

## REGRAS COMUNS (cole no fim de qualquer prompt abaixo)

```
REGRAS COMUNS (WP-OPERADOR-NUXTUI-ONDAS)
Leia antes: docs/plans/WP-OPERADOR-NUXTUI-ONDAS.md (o plano), o anexo de inventário do seu app em docs/plans/WP-OPERADOR-NUXTUI-ONDAS/, docs/plans/WP-GESTOR-CANON-LAUDO.md, docs/reference/omotenashi-copy.md e docs/reference/suite-vocabulary.md.

CRITÉRIO DE PRONTO
1. 100% canônico: só componente oficial do Nuxt UI, tematizado no app.config.ts do kit. Nada de :ui= por instância, HTML cru, input nativo type="date|time", classe que imita componente, valor arbitrário sem motivo escrito ou primitiva paralela.
2. Omotenashi: a tela diz o que fazer e já traz a ação.
3. Herança: o que serve a outro app sobe para o kit (PR de kit, serial), nunca é copiado.
4. Zero regressão: confira o inventário do anexo gesto a gesto DEPOIS, com arquivo:linha dos dois lados, numa tabela no PR.
5. Visto em tela: antes e depois em 390, 768, 1024, 1280 e 1440, claro e escuro, com diálogos e overlays abertos e os estados carregando, vazio, erro, offline e sessão expirada. Harness: surfaces/operator-kit/visual/capture-before-after.mjs (build de produção contra o mock, Chromium 1243).
6. CI verde do app e dos vizinhos.

DECIDIDO (não reabrir): data e hora pelos Ui*Field; ⋯ = DropdownMenu; aviso com prazo = OperatorUrgentAlert; toast = o do kit; destaque = PageCard highlight ou data-highlight; cartão com a altura do conteúdo; tabela integrada ao card; lista curta = UiNativeSelect até o dono responder a pergunta 1 do plano.

COORDENAÇÃO
- Mudança no kit é SERIAL: um PR de kit por vez, no título "(onda 0.N)". Seu app NÃO edita surfaces/operator-kit; se precisar, abra PR de kit na fila e empilhe o app sobre ele.
- Uma frente = um app = um branch = um PR por grupo de telas.
- surfaces/orders-nuxt é da sessão do Gestor.
- Mock primeiro: se o mock do app não cobre a tela, a primeira frente é gravar fixtures do seed (Django local num banco novo com nome único + seed; proxy gravador; ver tests/visual/README.md do B.I.). Mock incompleto esconde defeito (o 500 do Gestor).
- Dublê fiel ao componente real, ou mountSuspended com o Nuxt UI real.
- Trava que confere string: mude primeiro a decisão, depois a trava, com o motivo escrito no teste. Nunca afrouxe para passar.

SEGURANÇA E ESTEIRA: o CLAUDE.md inteiro vale. Worktree própria; git add só de arquivo nomeado; sem git stash; scratchpad com nome único por frente; migração nova confere colisão; contrato TS se regera pelos export_*_schema com DJANGO_DEBUG=true; teste Python na worktree com PYTHONPATH explícito; retratos e baselines só pela sessão com o browser da CI. Fora de alcance sem a palavra do Pablo: alpha, produção, reseed, apagar branch alheio, tirar PR do rascunho.

RELATÓRIO NO CHAT (elevator pitch; o Pablo não lê o MD): o que mudou; os gestos conferidos; o que expandiu e por quê; decisões dele respondíveis com 1, 2 ou sim; estado de cada PR com número; o que NÃO foi verificado, com nome e motivo. Separe sempre: implementado, testado, visto no navegador, pendente.
```

---

## Onda 0 (kit, serial)

### 0.2 Guard de slot + marcador de opt-in

```
WP-OPERADOR-NUXTUI-ONDAS · PR 0.2 do kit: guard de slot e marcador de opt-in.
Empilhe sobre o último PR de kit aberto da onda 0 (ver a seção 9 do plano).
1. Teste no operator-kit que compila (com @vue/compiler-dom, como o canonicalPilot do Gestor) cada consumidor das peças do kit nos 9 apps e compara os <template #x> passados com os <slot name> declarados pela peça. Ele teria pegado o #below (P0-2 do laudo). Hoje não há slot passado sem estar declarado: o teste nasce verde e trava o próximo.
2. Marcador de opt-in: app.config de cada app com operatorKit: { canon: boolean, toaster: "nuxt-ui" | "sonner", search: "inline" | "dialog" }; um composable useOperatorKitMode(); e data-operator-canon no <html> (useHead), para os overlays em portal herdarem o modo. Hoje o opt-in é data-suite="v3", que os 7 apps vestem e o Gestor não. A variante `suite:` só casa dentro do marcador, então portal fica de fora: o PR 0.1 contornou isso na FilterBar lendo o marcador ao montar. Generalize.
3. Trava: todo app declara o modo. O Gestor declara canon: true NO PR DELE (a sessão do Gestor), não aqui; aqui o default é o modo antigo.
Prova: vitest dos 10 projetos; captura antes/depois dos 9 apps (nada pode mudar).
```

### 0.4 Toast no kit

```
WP-OPERADOR-NUXTUI-ONDAS · PR 0.4 do kit: toast no kit.
Inventário (anexo do kit, B.2): o Gestor usa um shim local (orders-nuxt/app/utils/operatorToast.ts + plugins/operator-toast.client.ts + nuxt.config.ts:113-117) que aceita só o título. Os outros 8 montam o OperatorSonner (vue-sonner). Chamadas useSonner: Gestor 41, Produção 36, Marketing 31, Compras 25, B.I. 15, KDS 8, PDV 7 e kit 8. Cinco usam description/action: production useProductionMutationGuard.ts:219, :401, :407; purchase index.vue:669; bi index.vue:130. O shim do Gestor perde essas cinco. O OperatorUrgentAlert.vue:24 chama useToast direto e some nos apps sem UApp.
Faça: operatorToast no kit (error/success/info/warning(title, { description, action, duration })) com destino por operatorKit.toaster (PR 0.2); OperatorUrgentAlert passa a usá-lo; o Kitchen Sink demonstra os dois destinos. O Gestor troca o shim local no PR dele.
Trava: teste do shim nos dois destinos e com as 5 chamadas de dois argumentos; o falhaComSaida do PDV passa a reconhecer as duas APIs.
```

### 0.5 Live Status (só depois do "sim" do dono à pergunta 2)

```
WP-OPERADOR-NUXTUI-ONDAS · PR 0.5 do kit: Live Status volta ao contrato.
Contrato escrito: operator-kit/README.md:422, "o ponto ao vivo com a hora; fora do ao vivo o estado se escreve por extenso". A pilha trocou isso por "On HH:MM"/"Off", binário e em inglês (OperatorLiveStatus.vue:24-44), e late (Produção, Gestor) e calm (PDV, KDS, Marketing, Compras) passaram a sair verdes.
Tons: live = success, com ponto e hora; calm = neutral, com o rótulo do app ("Atualiza a cada 60 s"); late = warning; off = error ("Sem conexão"). O NuxtBadge continua.
Travas que cristalizaram o "On/Off" e mudam com o motivo escrito: orders-nuxt/tests/canonicalPilot.guardrails.test.ts:386-389, que é da sessão do Gestor (combine com ela), e operator-kit/tests/components/SuiteChrome.test.ts:608-656. O vocabulário passa a proibir "On" e "Off" visíveis.
Prova: o cabeçalho da Produção atrasada em âmbar, e os 9 apps capturados.
```

### 0.7, 0.8, 0.9, 0.10, 0.11

```
WP-OPERADOR-NUXTUI-ONDAS · PR 0.<N> do kit. Use a linha 0.<N> da tabela "Onda 0" do plano e a seção B do anexo inventario-kit-grafo.md (B.3 cabeçalho, B.9 busca, B.1 rail, B.7 hydration), que trazem arquivo:linha, consumidores e a proposta. Tudo é opt-in pelo marcador do PR 0.2. Antes de mexer no 0.11, meça com __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: true no build do e2e; sem a medida, a correção é chute.
```

---

## Onda 1: B.I. (piloto; esta sessão fez o mock e a primeira leva, ver a seção 9 do plano)

```
WP-OPERADOR-NUXTUI-ONDAS · Onda 1, B.I. (surfaces/bi-nuxt), continuação do piloto.
Estado: veja a seção 9 do plano. O mock (tests/visual, fixtures gravadas do seed) e a migração do conteúdo estão no PR do piloto. Falta o que depende do kit: o período (0.3), o cabeçalho (0.7, com dois seletores de período no desktop: o BiPeriodChip vai em #phone-actions sem md:hidden), o Live Status (0.5) e o shell (0.10: BiNav sai, entra o OperatorSuiteShell).
Inventário condensado (anexo inventario-purchase-bi.md, seção 2):
- 8 rotas: / (Sobrou ou faltou + lotes), /sales, /cash, /customers, /profiles, /explore, /forecast, /scenarios. Leitura pura; 1 POST de negócio (levar ao plano, index.vue:119-137) e CRUD de cenários salvos (explore). Sem SSE e sem poll.
- Atalhos: [ e ] mudam o dia; / leva à busca (index.vue:146-158). Deslizar entre seções no celular (BiSwipeHint).
- Gestos frágeis: o "Comparar com" e a "Coleção" (eram select invisível sobre o rótulo); "+N produtos"; abrir a linha (OverShortRow); links entre apps (OverShortDetail para a Produção e o Gestor); exportar CSV por quadro; compartilhar no celular; Apagar cenário (agora com confirmação).
- Gráficos em CSS ficam (pergunta 4 do plano).
- Trava: guardrails.test.ts:163 TYPOGRAPHY_ENFORCED inclui bi-nuxt; guardrails.appBar (BiNav na lista "migrados" até o 0.10); ledger com variantes fictícias (corrigir antes do runner visual).
Pronto: as 8 telas nas 5 larguras, claro e escuro, ⋯, período e Comparar abertos, nos cenários normal, empty e error do mock.
```

## Onda 2a: Compras

```
WP-OPERADOR-NUXTUI-ONDAS · Onda 2a, Compras (surfaces/purchase-nuxt).
Depende de: 0.2, 0.4 e 0.7 no main ou na pilha.
Inventário condensado (anexo inventario-purchase-bi.md, seção 1):
- 1 rota (pages/index.vue, 2.868 linhas) com 4 vistas por estado: Painel, Comprar, Receber e Base (4 cadastros). O atalho do PWA é ?view=receive.
- 13 POSTs, e cada um devolve a projeção inteira; approveRequest está declarado e ninguém usa. A NF entra por QR ou código de barras na câmera (@zxing), por foto ou pela chave digitada.
- Kit: UiNativeSelect 9, UiFilterChip 5, UiSheet 4, UiDialog 2, OperatorDayPicker 2, OperatorSuiteSearch 2; #below em index.vue:1332.
- Escapes: 132 controles crus (o teto do ledger), 14 input, 4 table, 47 arbitrários (17 em ReceiptExceptionFlow), 5 travessões em fallbacks de presentation/purchase.ts.
- Travas: v6-conformidade (17 it de string) e camada-visual-da-suite quebram com qualquer reescrita; mude a decisão e depois a trava.
- Sem mock e sem schema TS (723 linhas de tipos à mão).
Ordem: (1) export_purchase_schema + teste de deriva; (2) mock com estado (os POSTs devolvem a projeção) e fixtures gravadas do seed; (3) quebrar index.vue em componentes SEM mudar markup, com retrato antes e depois idênticos; (4) migrar Base → Comprar → Painel → Receber, um PR cada.
```

## Onda 2b: Marketing

```
WP-OPERADOR-NUXTUI-ONDAS · Onda 2b, Marketing (surfaces/marketing-nuxt).
Leia antes: docs/reference/marketing-surface-contract.md e rode make marketing-docs.
Depende de: 0.3 (UiDateTimeField com a hora-limite), 0.4 (31 useSonner) e 0.7 (#below em announcements/[id].vue:441).
Inventário condensado (anexo inventario-marketing-nuxt.md):
- 9 rotas + /second-control/:ref; 124 gestos; 10 famílias de diálogo; R em 5 telas, N em Campanhas.
- Kit: UiButton 82, UiDialog 8 + 5 MarketingWorkspaceDialog, UiInput 16, UiSelect 9, UiNativeSelect 4, UiCheckboxGroup 14, campos de data 8.
- Escapes: 14 :ui= (todos no UiCheckboxGroup), 18 button, 7 input, 2 select invisíveis, 1 table, 8 campos numéricos (→ NuxtInputNumber), 3 segmentados à mão, 121 arbitrários, 1 sheet simulado com max-sm:*.
- Riscos: CSP estrita (nonce; a matriz roda com bypassCSP e não prova a CSP); 7 itens de select com value "" (o P0-1 do Gestor se virarem NuxtSelect); capture="environment"; o vocabulário mensagem/publicação/entrega; a ordem do selo (digital antes do código, Enter no TOTP, segunda pessoa).
- Defeitos achados (corrija em PR próprio, antes): o "Reagendar" dos Agendados manda ?action=reschedule_announcement e o assertRecoveryAction o rejeita; no celular, Decisões e Agendados não mostram o ⋯ com "Atualizar".
- Travas: 82 baselines (só a CI regera: uma sessão só); sectionBar.test exige data-suite; harness sem runtime (tests/support/uiPrimitives.ts, 550 linhas de dublê): troque por mountSuspended.
- Decisão do dono antes: o MarketingBoard (só em /__visual_board, 12 baselines) morre? (pergunta 5).
```

## Onda 3: Central e Kitchen Sink

```
WP-OPERADOR-NUXTUI-ONDAS · Onda 3, Central (surfaces/hub-nuxt) e Kitchen Sink (surfaces/kitchensink-nuxt), duas frentes paralelas.
Depende de: 0.10 (rail canônico) e 0.11 (hydration: useSuiteRailShown fora de ClientOnly em hub app.vue:607).
Central (anexo inventario-kds-hub-kitchensink.md, seção 2): 1 tela (app.vue, 640 linhas), 24 gestos, poll de 30 s com um ponto verde "ao vivo" fixo (:286), que é mentira (vira o Live Status calm); cabeçalho à mão (:253-306) → OperatorPageHeader; mobileTiles.spec provavelmente vermelho (falta data-tile-title); selo duplicado no celular (já no main).
Kitchen Sink (seção 3): fechar as 13 contradições entre doc e código; demonstrar MONTADOS o OperatorSuiteShell, o OperatorPageHeader, o OperatorLiveStatus, o OperatorSuiteSearch e os UiDate* (o catalog.guardrails passa hoje só porque o nome aparece no léxico); o ">" literal em OperatorKitchenSink.vue:1027; dois toasters (app.vue:37 e :48); a matriz verde no Chromium da CI.
```

## Onda 4: Produção

```
WP-OPERADOR-NUXTUI-ONDAS · Onda 4, Produção (surfaces/production-nuxt).
Depende de: 0.3 (6 OperatorPeriodPicker), 0.4 (o toast de "projeção vencida" com botão Atualizar), 0.5 (o tom late) e 0.8 (a lupa que hoje pede 2 toques).
Inventário condensado (anexo inventario-production-nuxt.md):
- 14 rotas; o Letreiro (/board) fica fora do rail; sem SSE por decisão (WP-PE4), 8 polls com backoff.
- Gestos frágeis: segurar a linha 550 ms e o clique direito no tablet deitado; dois toques em 600 ms no grau do fechamento; painel encaixado no lugar de diálogo no tablet deitado; 3 numpads e o teclado físico; Alt+1..5, /, R e ?; o bloqueio de atalhos depende de [role=dialog][data-state=open] e de data-production-timer-dialog no próprio elemento do diálogo; a impressão esconde o overlay pelo nome de atributo do ui-thing.
- Kiosk: wake lock, 60 s de ociosidade e recarga em /board, virada do dia à meia-noite, timers no localStorage.
- Kit: UiButton 96, UiInput 23, UiBadge 19, UiNativeSelect 18, UiDialog 14, UiTextarea 9.
- Escapes: 90 button, 14 table, 2 role="menu" e 1 listbox à mão, 1 progressbar à mão, 74 arbitrários (30 em ProductionStageGrid.vue, 2.442 linhas).
- Travas: v6Conformity (strings), QcCloseScreen.test.ts:480-505 (13 classes), ProductionHeader.test (input[type=search]), nativeUiStubs.ts (dublês), KNOWN_INERT.
- Mock: parcial. Faltam as 5 telas de receita, os timers com estado e o timer do forno, o lote avulso, a impressão de etiqueta e os diálogos da grade. Complete antes.
Ordem: mock; fatiar ProductionStageGrid sem mudar markup; um cabeçalho só (ProductionHeader + RecipeHeader); telas de chão; telas de escritório (receitas, relatórios).
```

## Onda 5: Cozinha

```
WP-OPERADOR-NUXTUI-ONDAS · Onda 5, Cozinha (surfaces/kds-nuxt).
Depende de: 0.5 (calm), 0.8 (o / não pode cobrir a grade) e a decisão do dono (pergunta 3) sobre o aviso urgente interromper a cozinha.
Inventário condensado (anexo inventario-kds-hub-kitchensink.md, seção 1):
- 3 rotas: /, /:ref e o painel público /pickup; 41 gestos; SSE, som, fanfarra e tela sempre ligada (OperatorPwaRuntime).
- Toque: o card tem dois alvos e um intervalo antes de o Pronto aceitar toque; o botão vai para o polegar via Teleport; toque longo.
- 24 button (o teto), 28 arbitrários, 15 Ui*, 8 useSonner.
- Travas: KdsTicketCard.test crava classes (h-11/14/16, bg-primary, border-dashed); KdsTicketModal.test usa dublê de UiDialog sem runtime; a exceção do / em operator-global-shortcut-exceptions.json.
- Mock: o /pickup pede /kds/pickup/ e o mock responde /kds/cliente/; as fixtures não trazem seen (a fanfarra toca), bloqueio por pagamento, volumes nem started_by. Corrija antes.
- Os e2e do KDS e da Central não rodam na CI (surfaces-gate.yml só roda Marketing e Produção): ligue-os.
```

## Onda 6: PDV

```
WP-OPERADOR-NUXTUI-ONDAS · Onda 6, PDV (surfaces/pos-nuxt). O último, com todas as peças do kit provadas.
Inventário condensado (anexo inventario-pos-nuxt.md, com 387 disparos no anexo A):
- 13 páginas + 4 redirecionamentos; nenhuma usa os shells do kit (PosOperatorShell + PosFunctionRail); a Venda, o fim do dia e o relatório têm cabeçalho próprio.
- 381 disparos vivos (326 cliques, 25 teclas, 10 envios, 15 de ponteiro, toque e pinça, 5 de arrastar), 306 por evento de componente, 41 diálogos, folhas e popovers, 6 OperatorManagerAuth.
- 8 ouvintes de teclado próprios, com o dicionário em provideOperatorShortcuts; SSE /sse/cash, /sse/tabs e /sse/orders com poll de 60 ou 120 s; BroadcastChannel para a Tela do cliente.
- Riscos: os atalhos pausam só com [role=dialog][data-state=open] (keyboardGuard.ts:16); se a comanda virar NuxtDrawer modal, os atalhos param com ela aberta. O Esc da trava da gaveta depende de [data-drawer-manager-auth][data-state="open"] (PosDrawerLockDialog.vue:43; o PR 0.1 o devolveu). A impressão depende do Teleport, do @page e do agente local 127.0.0.1:47811. O leitor de fichas captura o teclado.
- Escapes: 156 button, 6 input, 8 table, 4 alertdialog inline, 2 radiogroup, 2 listbox, 1 folha da comanda à mão, 4 menus de ação em popover, 38 spinners à mão, vue-sonner em 21 arquivos (102 chamadas), 3 travessões visíveis.
- Locais: 55. Órfãos: PosPinPad e PosReceiptSaveOffer. Sobem ao kit: PosAddressAutocomplete, PosCodeScanner, PosTerminalHealth e PosDenominationCounter.
- Travas: cerca de 10 leem o fonte (v6Conformidade exige "Pronto</button>"; receiptPrint exige o Teleport; railPreorders; railStatusOrder; orderEditSaleScreen). O falhaComSaida só reconhece toast.error. O ledger tem teto de 157.
- Mock: parcial (só /preorders e o login). Faltam 11 telas: a Venda, /display, o caixa, o fim do dia, o relatório e todos os Ajustes. São as primeiras frentes.
```
