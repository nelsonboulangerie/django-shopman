# Orders (Gestor de pedidos) — inventário funcional

**Base congelada:** `f650d01b2` (origin/main), worktree `orders-canonical`, branch `codex/orders-canonical-shell`.
**App:** `surfaces/orders-nuxt` (Nuxt 4 SSR, `extends ../operator-kit`, porta de dev 3004).
**Fontes primárias:** `docs/plans/suite-ux-v2/funcoes/gestor.md` (engenharia reversa por função: 58 trabalhos + U05 fora do app); `docs/plans/suite-ux-v2/funcoes/cobertura.md` §Gestor (45 linhas de tela/estado/destino); `docs/reference/operator-component-ledger.json` (11 superfícies do WP-UX-13D, 45 variantes, **todas `pending`**).
**Plano de forma:** `docs/plans/SUITE-UX-FUNCTION-PLAN.md` (leis L1–L7, 7 formas, 8 gestos, ação/guardas, fronteira, dispositivo) e `docs/plans/SUITE-UX-V2-PLAN.md` (anatomia v3, navegação de 5 níveis).

> Este documento é a camada de **não-regressão** do WP-UX-13 (§8): cada ação, filtro, opção, dado, permissão, atalho, estado e recuperação precisa continuar alcançável por dispositivo. Ele **não** decide anatomia; a decisão canônica por família está no `laudo-orders-board.md`.

## 1. O app em uma página

O Gestor carrega **quatro naturezas de trabalho** no mesmo app e no mesmo dispositivo (gestor.md §leitura essencial):

1. **Despacho em tempo real** (fila: segundos, cliente esperando, de pé no passe) → `/`;
2. **Cardápio vivo** (pausar o que acabou: minutos, em plena operação) → `/catalog` e `/feeds`;
3. **Configuração de canal/vitrine** (raro, sentado, com gerente) → `/feeds`, `/channels/:ref/catalog`;
4. **Higiene de cadastro** (clientes, vínculos: dias, escritório) → `/customers`, `/workstations`.

**Permissões**

| porta | permissão | onde |
|---|---|---|
| App (trava) | `shop.manage_orders\|backstage.operate_kds` | `app/app.vue:11` (`OPERATOR_PERM`) |
| Seção Clientes | `shop.manage_customers` | `composables/useGestorSections.ts:53` |
| Seção Postos | `shop.manage_workstations` | `useGestorSections.ts` (`canManageWorkstations`) |
| Só expedição | `expeditesOnly` (sem `shop.manage_orders`) | `composables/useGestorAccess.ts` (`canManageOrders`) |

**Navegação atual:** `components/GestorNav.vue` renderiza `OperatorSuiteRail` (`place="rail"`, desktop/tablet deitado) e `OperatorSectionBar` (`place="bar"`, celular/tablet em pé). Seções: Pedidos (`/`), Saída (`/?...`, Alt2, badge), Ajustes (`/settings`), Clientes (`/customers`, condicionado), Postos (`/workstations`), Canais (`/feeds`), Catálogo (`/catalog`), Histórico (`/history`). O app já se declara piloto visual: `app/app.vue` usa `data-suite="v3"`.

**Rotas em inglês** (convenção). A mudança de `/feeds` → `/channels` proposta na v3 é WP-UX-12 (navegação), **fora** deste corte.

## 2. Superfícies (por rota)

### 2.1 `orders-board` — `/` (o primeiro corte)

- **Rota/URL:** `/`; query `?view=` (Fila/Supervisão), `?sort=`, `?columns=` (`BOARD_COLUMNS_QUERY`), `?focus=`.
- **Fontes:** `app/pages/index.vue` (1630), `components/QueueView.vue` (345), `components/OrderCard.vue` (694), `components/BoardMenu.vue` (115), `components/ChannelQueueSignal.vue`, `components/SwipeReveal.vue`; `composables/useOrdersBoard.ts`, `presentation/board.ts`, `presentation/queue.ts`.
- **Forma/posto/andar/dispositivos (plano aprovado):** FILA · Passe · Operação · parede (leitura) + tablet fixo (gesto) + desktop (supervisão em tabela/lote) + celular (dono em movimento); parede não é oferecida ao Gestor (a fila de parede é a Saída da Cozinha).
- **Trabalhos:** P01 (vigiar), P02 (perceber), P03 (aceitar), P04 (recusar), P05 (avançar), P06 (assumir/liberar), P07 (despachar), P08 (entregador voltou), P09 (maquininha devolvida), P10 (acerto), P11 (receber na retirada), P12 (DANFE), P13 (reprocessar NFC-e), P14 (negociação iFood), P15 (achar/abrir), P16 (nota da cozinha), P17 (comentar), P18 (cancelar não pago), P19 (cancelar pago), P20 (reenviar link), P21 (corrida Machine), P22 (recibos de aviso), P23 (contatar cliente), P24 (agendados), P25 (alertas), P26 (CSV/imprimir), P27 (sinal de canal), P28 (identificar-se).
- **Ações primárias do item:** Aceitar, Iniciar preparo, Marcar pronto, Entregar, Despachar/Saiu, Finalizar, Aprovar (negociação). Em lote: `Aceitar N`, `Avançar N`.
- **Ações secundárias/frequentes:** Recusar (motivo), Assumir/liberar, Comentar, Imprimir via/DANFE, Abrir detalhe, Pausar/ativar produto e canal (interruptores), "Ciente" (som), Reenviar link, Reprocessar NFC-e, Ver recibos, Contatar cliente.
- **Exceção assinada:** cancelar pedido pago (gerente, assinatura), acerto com diferença (motivo + gerente), desligar canal (motivo + gerente).
- **Filtros/recortes:** chips `Precisa de você`, `Todos`, `Atrasados`, `Entrega`, `Retirada`, `+ Canal`; busca ao digitar (`OperatorSuiteSearch`, atalho `/`); ordenação (Urgência/Chegada/…); visão Fila ↔ Supervisão; colunas por query.
- **Opções/visões:** **Fila** (itens urgentes em foco + painel `Em andamento`, `O sistema fez`, `Agora no cardápio`) e **Supervisão** (tabela densa com seleção em lote). O texto do board ainda oferece 3 colunas Entrada/Preparo/Saída na visão de quadro.
- **Informações por item:** código chamável, tempo contra a meta, cliente, canal, entrega/retirada, itens, pagamento, valor, bloqueio **com motivo** (ex.: `Pix expirado`, `gerado às… · expira às… · avança sozinho`), estado.
- **Permissões:** trava do app; `canManageOrders` esconde/expede ações; ações de dinheiro/gerente pedem assinatura.
- **Atalhos:** `/` (busca), `F` (Fila), `T` (Supervisão), `Alt 1/2` (seções), `Esc` fecha camadas; mapa completo em `scripts/check_operator_shortcuts.py`.
- **Estados:** carregando inicial/parcial (`pending`), vazio verdadeiro por zona (`zoneEmptyText`), erro recuperável (`[data-queue-error]`), erro de ação inline por card, offline/degradado (`useConnectivity`, `OfflineBanner`), SSE live/connecting/late/off (`realtime`), estação travada (403 ≠ erro de rede), denso (10 pedidos reais no seed), extremo (nomes/valores longos), ação em progresso (`usePendingAction`), sucesso, falha, repetição idempotente, desfazer (`undoHandoff`, `undoReady`).
- **Recuperações:** puxe-para-atualizar, `Tentar de novo`, reconciliação por `refresh`, desfazer handoff/pronto, reabrir, "Ciente" do aviso, refetch por SSE.
- **Evidência (capturas do estado atual, 2026-10-06):** `captures/desktop-wide__board.png`, `desktop-common__board.png`, `desktop-low__board.png`, `desktop-compact__board.png`, `tablet-landscape__board.png`, `tablet-portrait__board.png`, `mobile-standard__board.png`, `mobile-narrow__board.png`, `desktop-common__station.png`, `desktop-common__login.png`, `mobile-standard__login.png`.

### 2.2 `order-detail` — `/:ref`

- **Fontes:** `app/pages/[ref].vue` (748), `components/OperatorOrderDetail` (kit), `OrderIFoodNegotiations.vue`, `OrderCourierPanel.vue`, `OrderNotificationReceipts.vue`, `OrderReasonDialog.vue`, `CourierBackDialog.vue`, `OperatorManagerAuth`. Query `?from=history`.
- **Forma/posto/andar/dispositivos:** FILA/FOCO · Todos · Operação · celular e tablet na mão (painel no tablet, tela cheia no celular).
- **Trabalhos:** P12 DANFE, P13 NFC-e, P14 negociação iFood, P15 abrir, P16 nota da cozinha, P17 comentar, P18/P19 cancelar, P20 reenviar link, P21 corrida, P22 recibos, P23 contato.
- **Ações:** avançar, despachar, entregar, acerto, cancelar (com presets), comentar, salvar nota da cozinha (tags + texto), reimprimir via/DANFE, reprocessar NFC-e, reenviar link, cotar/chamar/cancelar corrida, unificar (cliente), responder negociação iFood, reenviar aviso.
- **Filtros/opções:** seções/abas do detalhe; nenhum filtro de lista.
- **Informações:** código, cliente/contato (relay iFood), endereço, itens, pagamento, fiscal (NFC-e/DANFE), timeline, promessa, canal, recibos de notificação.
- **Permissões:** as mesmas do app; cancelar pago e acerto exigem assinatura; editar cliente sai para o Admin (U05).
- **Atalhos:** os do detalhe do kit; `Esc` volta com contexto.
- **Estados:** carregando, não encontrado, erro, permissão negada, dado desatualizado, conflito de revisão (nota/preço), ação em progresso, sucesso, falha, desfazer.
- **Recuperações:** voltar com contexto (`?from=history`), reabrir, manter/usar versão do servidor em conflito, reprocessar.

### 2.3 `catalog` — `/catalog`

- **Fontes:** `app/pages/catalog.vue` (1178), `components/CatalogProductPanel.vue` (1108), `CatalogAiSuggest.vue`, `presentation/catalog.ts`, `presentation/catalogFilters.ts`; `services/catalog.py`. Query `?surface=&sync=`, `?sku=&tab=`.
- **Forma/posto/andar/dispositivos:** CADASTRO · Escritório · Ajustes · desktop (a pausa urgente sai para o posto/celular na fronteira proposta).
- **Trabalhos:** C01–C16 (pausar/ativar por canal e global, preço, ocultar, lote com prévia, reordenar coleções/produtos, achar/recortar, reenviar sync, editar cadastro em 5 abas, IA por campo, PIM/social, fiscal/GTIN, permitir compra, ler estado).
- **Ações:** toggle de célula, menu ⋯ da linha, editar preço na célula, barra de lote + prévia (publicação e preço), arrastar pills de coleção, reenviar sync, abrir painel do produto (salvar N campos), sugestão de IA por campo, confirmar GTIN, interruptor "Permitir compra".
- **Filtros/opções:** busca (nome/SKU/keyword); coleção; filtros por dimensão (envio, canal, publicação, venda, estoque, PIM); colunas ocultáveis (cookie por estação); deep-link `?surface=&sync=error`; abas do painel (Geral, Preço e config, Ingredientes e nutrição, Redes sociais, Fiscal).
- **Informações:** matriz produto × canal, preço base vs célula, selos de estado (Oculto, Pausado, Fora do cardápio, Esgotado, Indisponível), "Resta N", "Repõe N no lote", selo de sync.
- **Permissões:** `shop.manage_orders`; edições sensíveis com revisão/conflito.
- **Atalhos:** busca, colunas, seleção; mapa do app.
- **Estados:** carregando, vazio, erro, conflito de revisão campo a campo, prévia vencida, rascunho de ordem em conflito, sync com selo de erro, extremo (SKUs/nomes longos).
- **Recuperações:** manter meu/atual, atualizar prévia, reenviar sync, descartar rascunho com guarda (`window.confirm` hoje).

### 2.4 `channel-catalog` — `/channels/:ref/catalog`

- **Fontes:** `app/pages/channels/[ref]/catalog.vue` (122), `components/CatalogBindingReview.vue` (90), `composables/useCatalogBindings.ts`; `api/catalog_bindings.py`.
- **Forma/posto/andar/dispositivos:** CONFERÊNCIA · Escritório · Ajustes · desktop.
- **Trabalho:** K09 (revisar vínculos de catálogo do canal: importar captura iFood, ligar anúncio ↔ SKU).
- **Ações:** carregar JSON (até 20 MiB), guardar, escolher captura, escolher SKU por anúncio, confirmar vínculo.
- **Filtros/opções:** lista de anúncios, captura selecionada, revisão.
- **Informações:** anúncio da plataforma ↔ produto nosso; revisão.
- **Permissões:** `shop.manage_orders`.
- **Estados:** carregando, vazio, erro de arquivo (não UTF-8), vínculo de outra captura, revisão mudou, conflito.
- **Recuperações:** trocar inventário (com guarda), refazer vínculo, descartar seleção (com guarda).

### 2.5 `customers` — `/customers`

- **Fontes:** `app/pages/customers/index.vue` (156), `presentation/customers.ts`, `composables/useCustomers.ts`; `api/customers.py`. Permissão `shop.manage_customers`.
- **Forma/posto/andar/dispositivos:** CADASTRO · Escritório · Ajustes · desktop.
- **Trabalhos:** U01 (achar cadastro), U02 (ficha), U03 (unificar), U04 (desfazer), U05 (editar → Admin).
- **Ações:** buscar, filtrar (Todos · Possíveis duplicados · iFood · Sem telefone), paginar, abrir ficha.
- **Filtros/opções:** busca com debounce (na URL), filtros, paginação.
- **Informações:** contato, CPF, aniversário, identificadores por canal, pedidos.
- **Estados:** carregando, vazio, erro, permissão negada.
- **Recuperações:** limpar filtro, voltar.

### 2.6 `customer-detail` — `/customers/:ref`

- **Fontes:** `app/pages/customers/[ref].vue` (203), `components/CustomerMergeDialog.vue` (274).
- **Forma/posto/andar/dispositivos:** CADASTRO · Escritório · Ajustes · desktop.
- **Trabalhos:** U02, U03, U05.
- **Ações:** ler ficha, abrir candidato "Pode ser a mesma pessoa", unificar (escolher quem fica, prévia real, confirmar), editar (link Admin).
- **Filtros/opções:** candidatos, prévia de unificação.
- **Informações:** identificadores, endereços, pedidos, pontos, motivo da sugestão.
- **Estados:** carregando, vazio, conflito, permissão negada.
- **Recuperações:** voltar, refazer prévia, desfazer (24 h em `/customers/merges`).

### 2.7 `customer-merges` — `/customers/merges`

- **Fontes:** `app/pages/customers/merges.vue` (126).
- **Forma/posto/andar/dispositivos:** CADASTRO · Escritório · Ajustes · desktop.
- **Trabalho:** U04 (desfazer unificação).
- **Ações:** listar unificações com tempo restante, desfazer (avisa que pontos não voltam).
- **Informações:** par unificado, quem ficou, tempo restante.
- **Estados:** carregando, vazio, erro, janela expirada.
- **Recuperações:** confirmar com aviso; sem desfazer do desfazer.

### 2.8 `channels` — `/feeds`

- **Fontes:** `app/pages/feeds.vue` (461), `components/ChannelSwitchDialog.vue`, `ChannelHealthChecklist.vue`, `ChannelPeriodCalendar.vue`, `IFoodChannelStore.vue`, `ChannelSwitchState.vue`; `presentation/channelSwitch.ts`, `channelHealth.ts`, `ifoodStore.ts`; `api/feeds.py`. Query `?focus=`.
- **Forma/posto/andar/dispositivos:** CADASTRO (saúde) + INTERRUPTOR (toggle) · Escritório/Passe/Dono em movimento · Ajustes/Operação · desktop (saúde) e celular/tablet (toggle).
- **Trabalhos:** K01 (ligar/desligar canal com período e motivo), K02 (saúde), K03 (parear TV), K04 (coleções), K05 (rotação), K06 (automático + descanso), K07 (iFood loja), K08 (abrir/prever saída).
- **Ações:** toggle de canal, escolher período (calendário), motivo, autorizar gerente, checklist de saúde com gesto que resolve, parear TV (endereço + QR), marcar coleções, rotação, modo automático, abrir saída.
- **Filtros/opções:** por canal; `?focus=<ref>`; checklist por canal.
- **Informações:** estado do canal, iFood aberto/fechado e divergência, pendências, prévia da TV.
- **Permissões:** toggle desligar exige gerente (EXCEÇÃO ASSINADA).
- **Estados:** carregando, vazio, erro, pendência, conflito de revisão, ação em progresso.
- **Recuperações:** limpar seleção, reconsultar saúde, refazer janela.

### 2.9 `history` — `/history`

- **Fontes:** `app/pages/history.vue` (158), `composables/useOrderHistory.ts`; `api` orders/history. Query de filtros na URL.
- **Forma/posto/andar/dispositivos:** LEITURA · Escritório · Ajustes/Operação · desktop.
- **Trabalho:** localizar/entender pedidos encerrados (P26 CSV, passagem de turno).
- **Ações:** filtrar (período, canal, estado), paginar, abrir detalhe (`?from=history`), exportar.
- **Informações:** evento, pedido, estado, valores, data.
- **Estados:** carregando, vazio, erro, período extremo, paginação densa.
- **Recuperações:** voltar com contexto, limpar filtros.

### 2.10 `settings` — `/settings`

- **Fontes:** `app/pages/settings.vue` (43).
- **Forma/posto/andar/dispositivos:** CADASTRO · Escritório · Ajustes · desktop.
- **Trabalho:** operação, notificações e canais (configurações do app/loja).
- **Ações:** navegar para as seções de ajuste.
- **Estados:** vazio/estrutural.

### 2.11 `workstations` — `/workstations`

- **Fontes:** `app/pages/workstations.vue` (217). Permissão `shop.manage_workstations`.
- **Forma/posto/andar/dispositivos:** CADASTRO · Escritório · Ajustes · desktop.
- **Trabalho:** provisionar/revogar posto (K03 parear TV é o primo em Canais).
- **Ações:** listar, criar/editar, desativar (com confirmação), escolher tipo.
- **Informações:** rótulo, tipo, status, dispositivo.
- **Permissões:** `shop.manage_workstations`.
- **Estados:** carregando, vazio, erro, confirmação destrutiva.
- **Recuperações:** cancelar confirmação; sem desfazer de revogação (confirmar).

## 3. Trabalhos → superfície (não-regressão)

| trabalho | superfície atual | forma | posto | dispositivo |
|---|---|---|---|---|
| P01–P07, P12, P14, P15, P24–P27 | `/` | FILA | Passe | parede/tablet/desktop |
| P08–P11, P13, P16–P23, P28 | `/` e `/:ref` (diálogos) | CONFERÊNCIA/ANOTAR/EXCEÇÃO | Passe/Balcão/Todos | tablet/celular/desktop |
| C01–C16 | `/catalog` (+ painel) | CADASTRO | Escritório | desktop |
| K01–K08 | `/feeds` | CADASTRO/INTERRUPTOR | Escritório/Passe/Dono | desktop/celular |
| K09 | `/channels/:ref/catalog` | CONFERÊNCIA | Escritório | desktop |
| U01–U04 | `/customers*` | CADASTRO | Escritório | desktop |
| U05 | fora do app (Admin) | CONFIGURAR | Escritório | desktop |
| P26 (CSV/imprimir) | `/` (ação rara) | EMITIR | Escritório | desktop |

## 4. Gestos transversais que o app usa (FUNCTION-PLAN §3.2)

- **LOCALIZAR:** busca do board, busca de cliente/produto, `/` e atalhos; alcance ainda só "esta tela" (a busca única com escopo App/Suíte é WP-UX-11).
- **EXCEÇÃO ASSINADA:** cancelar pago, acerto com diferença, desligar canal (gerente/PIN).
- **CONFIRMAR COM PROVA:** prévia de publicação/preço em lote, revisão de conflito, prévia de unificação.
- **INTERRUPTOR:** pausar produto por canal/global, desligar canal, `Permitir compra`, switches de cardápio.
- **SELO / DESFAZER:** desfazer handoff/pronto, reabrir; entregar/despachar ainda sem desfazer (achado §11).
- **ANOTAR:** recusa, cancelamento, comentário, diferença de acerto.
- **INSTRUIR:** nota da cozinha (tags + texto → KDS).
- **AVISO:** sino de alertas, som/"Ciente", sinal de canal, recibos de notificação.
- **ACUSAR CIÊNCIA:** "Ciente" do pedido novo (hoje local ao dispositivo — L7 pede servidor).

## 5. Dispositivo (do plano aprovado, FUNCTION-PLAN §10.4)

| dispositivo | trabalho no Gestor |
|---|---|
| desktop | escritório: fila supervisionada em tabela, catálogo, canais, clientes |
| tablet | passe: fila e saída; interruptores (pausar produto, desligar canal) |
| celular | dono em movimento: push, aceitar/recusar, detalhe, interruptores, resumo fora da loja (com consentimento) |
| parede | **não oferecido** (a fila de parede é a Saída da Cozinha) |

## 6. Vermelhos e lacunas deste inventário

- **Sem runner no ledger:** nenhuma das 11 superfícies tem `runner`; `make operator-visual app=orders` não executa a matriz. O laudo capturou por script dedicado (ver `laudo-orders-board.md` §método).
- **Estados que não consegui reproduzir com o seed:** sessão expirada, permissão negada (fora do superuser), conflito de revisão em tempo real, scanner/câmera, giro de dispositivo, `forced-colors`/reduced-motion. Ficam **vermelhos** com próximo passo (não foram validados visualmente).
- **Tema escuro:** o app não declara dark-first; a matriz escura não foi capturada nesta rodada.
- **Fronteira proposta** (juntar a Saída do Gestor e a Saída da Cozinha num posto só, mover Agendados para Produção, mover avisos transacionais do Marketing para Canais) **não** foi implementada nem validada — é decisão de regra/rota (FUNCTION-PLAN §9/§13, WP-UX-12).
- **U05 / editar cliente** e **alarmes do B.I.** seguem fora do app (decisão do dono pendente).
- **Base:** este inventário é sobre `f650d01b2`; a infra nova da PR #1512 (casca, `operatorSurfaceGate`, locale, remoção de `UiToolbar`/`UiModal`, ledger/gates) **não** está nesta base. Se a #1512 mergear, refazer o rebase e revisar os pontos que ela toca.
