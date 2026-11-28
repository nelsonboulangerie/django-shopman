# Gestor de Pedidos — plano de excelência operacional

Data: 10/09/2026. Estado: **plano auditado; implementação, piloto e rollout não executados**.

## 1. Compromisso e limite desta entrega

A régua de decisão é omotenashi: antecipar o que a pessoa precisa, eliminar memória e redigitação, conservar seu contexto quando algo a interrompe e oferecer a próxima ação **autorizada e possível**, junto ao fato que a justifica. A operação deve conseguir responder, sem investigação técnica: **o que aconteceu, o que falta, quem pode agir e como continuar**.

Esta sessão entrega exclusivamente este plano e seu prompt de execução. Não modifica serviços, componentes, contratos de produção, permissões, dados comerciais ou configurações operacionais. Os testes de diagnóstico usam banco efêmero e adaptadores de teste; não enviam mensagens, não despacham entregadores e não emitem documentos reais.

Base final auditada: **`9787bbcdfe5ccd2cbb4a2097b4d97c146e86179f`**, ref local `origin/main` resolvida nesta sessão, sem fetch nem alegação de atualização do servidor remoto. A primeira leitura usou o checkout recebido `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`; a comparação de worktrees revelou mudanças materiais. Os achados foram revalidados e os testes repetidos na base final, com os packages importados explicitamente deste worktree. O commit documental inicial foi rebaseado localmente sobre essa base; não foi integrado código sujo de terceiros. Branch documental: `codex/orders-operational-excellence-plan`. Worktree: `/Users/pablovalentini/Dev/Claude/django-shopman-orders-plan`. O checkout original e seus arquivos não rastreados foram preservados. Dependências locais foram reutilizadas por links ignorados no worktree, sem instalar ou atualizar pacotes. Este plano não pressupõe que o código continuará igual na execução.

**Não confundir três conclusões:** defeito reproduzido em fixture não prova incidência em produção; inspeção de código prova o caminho descrito, não sua frequência; meta de esforço não é ganho já observado. Esta entrega prova falhas e estabelece o experimento que deverá provar a melhoria. Declarar ganhos de campo agora seria inventar evidência.

## 2. Referências lidas e como foram usadas

Foram lidos integralmente os cinco documentos abaixo e o plano atual do PDV, seu prompt e suas evidências, identificados logo após a tabela. Os planos de Produção e Marketing estavam não rastreados no checkout original; foram tratados como entrada externa, sem copiá-los ou incorporá-los à branch.

| Referência no checkout original | SHA-256 | Rigor transferido |
| --- | --- | --- |
| `docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` | `f435f49347391b7d1bdb0e9de29a3278d14d17897bb93022b2880679014ac68d` | Integridade antes da ampliação; contratos por ação; concorrência; budgets; piloto por estação; responsabilidade sobre trabalho físico |
| `docs/plans/MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` | `de59ffaea5228aea38588fc3471049989cc86c06787640674837104ef1b94da4` | Aprovar intenção exata; não chamar timeout de falha definitiva; reconciliar antes de repetir efeito externo; preservar rascunho; evidência e gates |
| `docs/plans/POS-FIRST-CLASS-PLAN.md` | `5213cd893b842705c79dee4d59842edc44298d33813813bf8dcb3aeac95228c4` | Jornada completa, velocidade de balcão, dinheiro físico e domínio canônico |
| `docs/plans/POS-REDESIGN-PLAN.md` | `a362604f97066f65d5e691eeb48cbb642b25b7b1eb47287f1fca5027f302a14a` | Hierarquia de trabalho, teclado, interrupção e continuidade |
| `docs/reports/pdv-surface-excellence-audit-2026-05-13.md` | `8c2f9843a002f2a8690c5049c8ae5137a202d75f821a6c12f9b099170feb5241` | Inventário de ações destrutivas, impacto humano e validação antes/depois |

A fonte desses caminhos é `/Users/pablovalentini/Dev/Claude/django-shopman`. O plano mais recente do PDV foi localizado no worktree `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-pdv-plan-current-20260910` e também lido integralmente:

| Referência adicional nesse worktree | SHA-256 | Uso |
| --- | --- | --- |
| `docs/plans/PDV-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-10.md` (718 linhas) | `8963a1fcebb4666de92e2a31373abfffbcdea62adc28d7ca8518b5a2037aaab9` | Um writer por efeito; prova física separada de aceite; revisão da base atual; piloto por coorte; budgets que não removem autorização |
| `docs/plans/PDV-IRREPRESSIBLE-EXCELLENCE-PROMPT-2026-09-10.md` (91 linhas) | `91c63e048f1cd9cb3c88409c763609dad96d1b23780b190931e315f2da79371d` | Mandato técnico separado de produção e gates humanos |
| `docs/reports/PDV-EXCELLENCE-PLANNING-AUDIT-2026-09-10.md` (167 linhas) | `bff9973006e476c60955400223318231d683db132a7ce34e66bbc1c98865e00b` | Proveniência, imports do worktree, limites de SQLite/mocks e evidência de correções já existentes |

Nenhum número de testes, diagnóstico, score, status de implantação ou modelo de identidade dos documentos antigos foi promovido a fato atual. Em particular, a identidade atual é `request.user`, o estado de aceite é `accepted` e os feeds já são `Channel` com política `display`.

Contratos confrontados com o código: ADR-012 (superfícies headless), ADR-014 (dado/apresentação), ADR-016 (SSE), ADR-018 (superfície como Channel), `docs/reference/order-operational-contract.md` e `docs/reference/remote-mutation-contract.md`. O vocabulário histórico `confirmed` encontrado em texto não autoriza um estado novo. A skill `unfold-admin-canonical` foi consultada para as fronteiras administrativas; qualquer implementação que toque Admin deverá seguir a skill, seus documentos canônicos e `make admin`.

## 3. Cadeia auditada e autoridades que permanecem

O app é o hub existente de **Pedidos, Catálogo e Feeds**. A auditoria seguiu as entradas visíveis, seus composables, BFF, APIs, fachadas, serviços de domínio, modelos, sinais, workers, projeções de retorno e consumidores externos. Isso inclui efeitos acionados indiretamente por avançar, cancelar ou publicar. Não significa homologação dos serviços dos fornecedores nem auditoria universal de todos os algoritmos de cada core.

| Trecho | Código que delimita a cadeia | Autoridade e resultado a preservar |
| --- | --- | --- |
| Shell, identificação, navegação | `surfaces/orders-nuxt/app/app.vue`, `OperatorLogin.vue`, `GestorTopBar.vue`; sessão/lock/conectividade de `operator-kit`; `backstage/api/permissions.py` | Sessão da pessoa; confiança da estação não concede permissão; login já ocorre no app |
| Fila, cards, tabela, detalhe e diálogos | `pages/index.vue`, `[ref].vue`, `OrderCard.vue`, `OrderReasonDialog.vue`, `OrderCourierPanel.vue`; `useOrdersBoard`, `useOrderDetail`, `useOrderEvents`, `useNowTick`; `presentation/board.ts`, `courier.ts` | Duas zonas, encomendas, filtros, atribuição, endereço, troco, equipamentos e erros já existentes |
| Transporte HTTP/SSE | `orders-nuxt/server/api/v1/[...path].ts`, `server/routes/sse/orders.ts`; `operator-kit/server/utils/djangoProxy.ts`, `eventStream.ts`; `shop/eventstream.py`, `handlers/_sse_emitters.py` | Proxy same-origin, cookies/CSRF, `Last-Event-ID`, cancelamento de upstream, eventos após commit; push invalida leitura canônica |
| API e projeção de pedidos | `backstage/api/operations.py` (`Order*View`), `services/orders.py`, `projections/order_queue.py`, gerador/schema export de pedidos | Fachada fina; projeções tipadas; não criar outra fila persistente |
| Mutações e estado | `shop/services/operator_orders.py`, `cancellation.py`; `packages/orderman/shopman/orderman/models/order.py`, `_sequenced_event.py`, `idempotency.py` | Order, snapshot comercial selado, transições e eventos sequenciados; IdempotencyKey existente |
| Orquestração | `shop/apps.py::_connect_lifecycle_signal`, `lifecycle.py`, `directives.py`, `orderman/dispatch.py`, `management/commands/sweep_stuck_orders.py` | ChannelConfig decide timings; Directive e marcadores de fase recuperam trabalho; não criar outro workflow engine |
| Pagamento e caixa | `shop/services/payment.py`, `operator_orders.py::settle_delivery_cash`; `backstage/services/pos.py::current_shift`; Payman e `packages/cashman/shopman/cashman/services/ledger.py`, constraints de Entry | Captura/saldo/estorno no Payman; movimento físico em Cashman; cancelamento não equivale a devolução física de dinheiro |
| Estoque, cozinha e produção | `shop/services/stock.py`, `kds.py`, `handlers/preorder.py`, `production_order_sync.py`; WorkOrder, Hold, Quant e tickets dos cores | Holds e baixas canônicos; KDS por delta de line_id; encomenda não dispara antes da data; refs existentes ligam produção e pedido |
| Entrega externa | `shop/services/courier.py`, `fulfillment.py`, `handlers/courier_dispatch.py`, `courier_sync.py`, adaptadores courier e webhook | Um funil para webhook/poll; tentativa de corrida e Fulfillment existentes; não atribuir dinheiro ou custódia por inferência |
| Marketplace | `shop/services/ifood_orders.py`, `ifood_callbacks.py`, `handlers/ifood_status.py`; entrada por ingest canônico | Order externo não vira segundo pedido; callback assíncrono não significa aprovação final do fornecedor |
| Fiscal e avisos | `shop/services/fiscal.py`, `handlers/fiscal.py`, `payment_refund.py`, `payment_timeout.py`, `confirmation.py`, `services/notification.py`, `handlers/notification.py` | Resolver fiscal, consulta antes de reemitir, dedupe de avisos e estornos; consumidores atuais recebem os mesmos fatos |
| Caixa pessoal e acessos | `operator-kit/NotificationBell.vue`, `useNotifications`, `useUserNotifications`, `server/routes/sse/notifications.ts`; `backstage/api/notifications.py`, `api/sign_ins.py`, `services/sign_in_audit.py` | UserNotification pertence à pessoa; painel atual lê/marca lida e consulta acessos; não confundir com OperatorAlert da loja nem criar outro inbox |
| Link e relacionamento | `OrderResendPaymentLinkView`, `notification.resend_payment_link`, `payment.reconcile_with_gateway_if_due`, `order_queue._customer_profile/_customer_contact` | URL existente e cadência de reenvio; captura no Payman; contato/cadastro/insight no Guestman; detalhe já evita memória e busca externa |
| Fila de fornada e atributos | `services/waitlist.py`, `payment_gate.py`, `attributes.py`, `derived_provenance.py`, `product_readiness.py`; holds/quantidade/qualidade do Stockman | Fermata, materialização, confirmação e cobrança têm recuperadores atuais; dados de receita usam registry/proveniência, sem metadata paralela |
| Alertas e retomada | `backstage/api/alerts.py`, `services/alerts.py`, `shop/services/observability.py`, OperatorAlert, `useAlerts`, `AlertsBell.vue` | Alertas existentes, dedupe e referência ao pedido; reconhecer aviso não resolve sua causa |
| Catálogo | `pages/catalog.vue`, `CatalogProductPanel.vue`, `CatalogAiSuggest.vue`, `useCatalogMatrix`, `useDragReorder`, apresentação/filtros; `backstage/api/catalog.py`, `services/catalog.py`, `projections/catalog.py` | Product, ListingItem, Collection, CollectionItem; preço e publicação não ganham cópia por app |
| Projeção externa do catálogo | `shop/handlers/catalog_projection.py`, `services/catalog_sync.py`, `social_publish_rules.py`, `handlers/fiscal_gate.py` | CatalogSyncState por SKU/canal; leitura do estado atual no worker; retraction e política de publicação existentes |
| Feeds e TV | `pages/feeds.vue`, `useFeedBoard`, `backstage/api/feeds.py`, `services/feeds.py`, `projections/feeds.py`; `shop/views/product_feed.py`, `projections/menuboard.py`, resolução de preços por destino | Channel.display, coleções e pausas locais; display não vende nem tem Listing/preço próprio; saídas existentes, sem portal novo |
| Assistência de texto e cadastro | `catalog.py::ai_assist_field`, `shop/services/copy_assist.py`, painel de produto, schemas social/fiscal/nutrição | Sugestão por campo, revisão humana e aceite em rascunho; voz existente da loja; receita e override manual mantêm donos atuais |

### Soluções maduras a preservar

- Confirmação/recusa relêem Order sob lock; a transição também é serializada. D02 não significa ausência geral de proteção.
- Payman calcula captura líquida e reconhece `unknown`; Cashman bloqueia turno e deduplica venda/acerto por turno e pedido. Unicidade entre turnos ainda exige H02.
- Fiscal consulta/adota nota existente e grava sob lock. KDS reconcilia line_id; notificações têm recibos permanentes em IdempotencyKey; produção conserva vínculos/histórico e usa locks WorkOrder→Order.
- Cancelamento já tem política, permissão avançada e segunda assinatura compartilhada, preservando motivo. D03 está corrigido. O parser monetário já trata typo como erro de entrada.
- `payment_gate` é compartilhado com KDS; waitlist bloqueia fermata e recupera materialização/cobrança. Otimizar D20 deve preservar essas regras.
- SSE, polling, retomada da aba, aviso sonoro e canal pessoal já existem. O proxy protege traversal, Last-Event-ID inválido e cache privado. O som tem decisão explícita do dono: alteração exige G04.
- Contato/insight, notas distintas de cliente/cozinha, presente, endereço, troco, equipamento e encomendas já oferecem contexto. Catálogo envia somente campos alterados; atributos têm proveniência; feeds têm rotação e Admin em Channel.
- O GET do detalhe já reconcilia pagamento com gateway sob throttle. Preservar esse resgate e medir seu custo; a consulta de resultado de intenção não deve dispará-lo novamente.
- Estender `remote_mutations` e IdempotencyKey; seu uso atual não fecha sozinho atomicidade efeito/resposta nem fingerprint. Não criar infraestrutura paralela.

## 4. Evidência atual: defeitos, hipóteses e decisões

Legenda: **R** = reproduzido em execução local; **E** = confirmado pela sequência explícita do código. P0 bloqueia liberação da mutação afetada; P1 bloqueia o piloto da jornada afetada. Prioridade não é estimativa de incidência.

### 4.1 Defeitos comprovados

| ID / prioridade / prova | Achado e reprodução precisa | Consequência e correção contratual |
| --- | --- | --- |
| D01 P0 R | Dois POSTs idênticos em `api-backstage-order-advance`, pedido `accepted` de retirada/dinheiro: 200/preparing e depois 200/ready. `operator_orders.advance_order` escolhe o próximo estado a partir de cada leitura; não recebe intenção/revisão/chave | Resposta perdida pode virar ação física diferente. C02: replay da mesma intenção não avança outra etapa |
| D02 P0 R | Carregar A e B do mesmo Order; salvar nota em A; `assign_order(B,...)`; a nota some. `save_kitchen_note` e atribuição salvam `data` derivado da instância antiga | Escritores de campos distintos se apagam. C03: merge de dados frescos sob lock e conflito explícito no mesmo campo |
| D04 P0 R | Pedido delivery ready, cash/on_delivery, total 1500, troco para 2000, corrida A. `courier.apply_status(...,'E')` salva E e levanta ChangeOutRequired; replay E retorna cedo, Order continua ready | Falha parcial fica presa. C05 deve preservar fato externo e recuperar derivação; não inventar saída de troco para fazer teste passar |
| D05 P0 R | `update_product_detail(sku, {'name':'Depois','keywords':'invalido'})` levanta CatalogError após salvar name. `product.save()` precede validação da lista de keywords | Erro não significa “nada salvo”. C06: validar todo patch antes de gravar, transação local integral |
| D06 P1 R | Reordenar coleção manual B,A grava sort_order B,A; `build_catalog_matrix(ref)` devolve A,B, por `Product.order_by('name')` | Gesto aparentemente desfeito após refresh. C06: matriz e saída devem consumir a ordem canônica que afirmam editar |
| D07 P0 R | Com `SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH=True`, publicar célula individual sem classificação levanta ValidationError; `bulk_set` publica a mesma célula via QuerySet.update | Lote contorna regra existente do gate fiscal. C06 aplica o mesmo validador em célula/lote/edição global, sem regra fiscal nova |
| D08 P1 R | OrderItem qty `0.500`; `build_operator_order(...).items[0].qty` vira 0. Resumo do card também usa `int(it.qty)` | Quantidade suportada pelo core perde precisão na projeção. C01 conserva decimal e unidade. Ocorrência em catálogo real ainda não aferida |
| D09 P1 E | `[ref].vue::watch(order)`: qualquer substituição de `order` executa `notes = kitchen_note`. SSE/refresh durante edição dispara esse watcher | Rascunho não salvo é substituído. C07 conserva base, draft e seleção; atualização externa não toma posse do editor |
| D10 P1 E | `index.vue` (botão da tabela) desabilita ação de tabela só por busy, ignorando `a.disabled`; OrderCard considera ambos e não emite ação desabilitada | Mesma ação tem comportamento diferente por visualização. C01 exige mesma Action e motivo em card/tabela/detalhe |
| D11 P1 E | `order_queue._build_card`: `can_confirm = status == 'new'`; confirmação real aplica disponibilidade/pagamento. A fila não recebe pessoa/capacidades para essa decisão; o detalhe já recebe user para cancelamento, solução a preservar | Pode oferecer ação que o serviço recusará. Reutilizar guardas canônicos sem executá-las com efeitos durante GET; mudança após leitura continua sendo conflito legítimo |
| D12 P0 E | `bulk_price` aplica pct/delta ao preço corrente, percorre canais sequencialmente e reconcilia depois da escrita. Falha de `_reconcile_if_projected` comunica “Mudança aplicada, sincronização falhou” | Repetir todo o lote pode alterar preço duas vezes e afetar só parte dos canais. C02/C06 congelam escopo e valores resultantes; retomada apenas de sync pendente |
| D13 P1 E | `catalog.vue::bulk/applyBulkPrice` limpam seleção/valor após await sem testar resultado; `commitPrice` fecha antes do POST; `feeds.vue::applyEdit` fecha mesmo quando setCollections retorna False | Perda de contexto e reconstrução manual após falha. C07 mantém editor/seleção até desfecho conhecido, sem reexecutar mudanças já aplicadas |
| D14 P1 E | `feeds.vue` não consome `error`; primeira leitura falha, feeds=[], pending=false, tela diz “Nenhum feed. Crie um…”. No kit, `useNotifications.refresh/loadSignIns` também substituem erro por lista/contador vazios, e NotificationBell apresenta ausência de avisos/acessos | Induz cadastro para corrigir indisponibilidade. C08 separa vazio, sem acesso e erro, conserva última leitura válida |
| D15 P1 E | `orders.cancellation_reasons` converte IFoodCallbackError em []; `useOrderDetail.fetchCancellationReasons` também converte erro em []; não há validação autoritativa da escolha no comando de cancelamento do Gestor | Não aplicável, lista vazia e fornecedor indisponível ficam indistinguíveis. C04 preserva resultado e impede fallback silencioso de código obrigatório |
| D16 P1 E | `useNowTick` usa relógio do navegador; `confirmationRemainingLabel` o compara ao prazo absoluto; card já traz `server_now_iso`, mas não o usa para compensar relógio | Máquina adiantada/atrasada mostra prazo incorreto. C08 ancora no servidor sem permitir ao cliente decidir expiração |
| D17 P1 E | `useOrderDetail.act` retorna False com toast, sem refresh no erro; board já refaz leitura em conflito | Detalhe pode conservar estado anterior após disputa/resultado ambíguo. C02/C07 reconciliam mantendo rascunhos e explicação persistente |
| D18 P0 E | `apps.py` executa lifecycle em on_commit; DURABLE_PHASES/sweeper cobrem commit, accepted, paid, cancelled; não cobrem preparing/ready/delivered/completed. `on_preparing` cria KDS; `on_completed` emite fiscal | Crash nessa janela não tem recuperação por esse mecanismo. C05 deve cobrir efeitos devidos sem reiniciar o ciclo completo ou marcar tarefas como feitas por suposição |

D02 tem alcance além dos dois métodos reproduzidos: foram encontrados escritores de `Order.data` em courier, custódia, cancelamento fiscal, fulfillment, marcadores de lifecycle e vínculo de produção. O fato comprovado é a perda nota/atribuição; cada outra combinação deverá ter seu próprio teste de interleaving antes de receber diagnóstico de dano específico. Emissão fiscal já usa leitura bloqueada e não deve ser incluída indiscriminadamente no defeito.

D19 P1 R — O endpoint de reenvio retorna “Link reenviado ao cliente.” enquanto a Directive continua `queued` e a própria resposta diz “Enviando…”; `useOrderDetail.resendPaymentLink` repete a afirmação no toast. Além disso, `payment_link_notice` traduz toda Directive `done` como enviada, mesmo com `notification_delivery.status=skipped`. Dois ensaios herméticos confirmaram essas mensagens. C05/C08 devem ler a evidência de entrega já existente: enfileirado, aceito pelo backend, omitido por consentimento/contato e falha são diferentes; nenhum deles prova leitura pelo cliente. Preservar dedupe, cadência, URL e o resultado auditável existente.

D20 P1 R — `build_order_queue` **e** `build_two_zone_queue`, com 1/10/100 pedidos ready de retirada/dinheiro, executam respectivamente **4/13/103 consultas**, sendo **1/10/100 ao Hold**. `_build_card → _waitlist_badge → waitlist.state_for → _order_holds` consulta por pedido, mesmo sem reserva. Na fila simples, a mesma fixture na base recebida fazia 3/3/3; a comparação histórica não mediu a projeção de duas zonas. É regressão de consultas comprovada na base final, não latência de produção medida. O budget de uma leitura em batch ao Hold para 100 cards retira 99 das 100 consultas dessa dependência (99%); é ganho estrutural contratado, ainda não implementado, sem inferir redução proporcional do tempo humano ou da latência. WP07 deve resolver em batch pelo serviço canônico, preservando fermata/qualidade e o gate de pagamento; não remover o badge ou derivar “sem fila” só do JSON para reduzir consultas.

### 4.1a Achado encerrado na revalidação

**D03 — corrigido na base final, protegido por teste.** O cancelamento de completed sem transição permitida agora retorna 409 e mantém o estado, ao invés do 200 observado na base recebida. `orders.cancel_order` propaga False como OrderConflict; API e projeção usam `operator_cancel_policy`, `ADVANCED_CANCEL_PERMISSION` e aprovação compartilhada. Não reimplementar essa correção. Permanecem independentes D15 (motivos externos), H03 (interleavings) e a certeza de efeitos downstream.

### 4.2 Hipóteses abertas — não implementar diagnóstico sem confirmação

| ID | Pergunta e evidência que falta | Ensaio e decisão após resultado |
| --- | --- | --- |
| H01 | Duplicidade externa após timeout de despacho, callback iFood ou aviso: adaptação local não prova dedupe/reconciliação do fornecedor | Mock com efeito remoto aceito + resposta perdida; depois homologação autorizada de consulta por referência e semântica de retry. Sem prova, resultado desconhecido e nenhuma repetição cega |
| H02 | Acerto COD/retorno de troco duplicado entre dois turnos ou escrita em gaveta errada: fachada resolve `current_shift()` sem terminal; constraints conhecidas são por turno | PostgreSQL, dois turnos/terminais, duas conexões e objetos antigos. Identificar o turno realmente autorizado antes de escrever; política final G02 |
| H03 | Corrida timeout de confirmação/pagamento versus operador/webhook pode invalidar precondição lida antes do lock; incluir captura entre avaliação da política de cancelamento e transição, sem assumir que a segunda assinatura já fecha essa janela | Barreiras antes da transição, captura chegando em cada janela, relógio controlado. Falha reclassifica para P0; teste que passa preserva mecanismo |
| H04 | Latência, respostas fora de ordem e tempestade de refresh em payload rico | Medir endpoint real de duas zonas e detalhe, incluindo Payman, WO, deadlines, alertas e 2/10 estações. Usar D20 como baseline atual de consultas simples, sem extrapolar para latência nem todos os payloads |
| H05 | Perda de atualização em Channel.config, metadata social/fiscal e ordenação concorrente | Dois editores e callbacks com barreiras. Verificar JSON não relacionado, ordem completa e revisions; não culpar banco sem interleaving reproduzido |
| H06 | Sugestão/fetch de produto atrasado pode aparecer em outro SKU; `openDetail` não compara identidade na volta e CatalogAiSuggest observa field, não SKU | Respostas A/B invertidas, fechar/reabrir durante sugestão, confirmar comportamento real de montagem do Sheet. C07 exige proteção mesmo sem incidente em campo |
| H07 | Reconhecimento de alerta pode esconder pendência de outra função; alertas são listados sob permissão ampla e ack não resolve a causa | Fixture por persona e fonte, revisar necessidade de cada informação. Matriz de acesso/ack é G01, não acusação automática de vazamento |
| H08 | Volume real de quantidades fracionárias, estados históricos, refs de WO ausentes, COD concluído sem acerto e preços por tier | Inventário somente leitura em ambiente autorizado, anonimizado. Não converter quantidade nem ajustar estoque/dinheiro para “limpar” a amostra |

H09 — A caixa pessoal recebe `is_actionable/action_url/action_data`, mas o NotificationBell atual oferece leitura e histórico, sem ação de campanha/revogação. Isso é fronteira de produto a confirmar, não autorização para criar páginas ou botões de efeito sensível. G01 define quais famílias devem ter próxima ação ali; antes de qualquer extensão, auditar o handler canônico da família (campanha/aprovação ou revogação), preservar a confirmação exigida e coordenar o contrato com seu owner. O tratamento honesto de erro em D14 independe dessa decisão.

### 4.3 Decisões humanas necessárias

Nenhuma destas escolhas é pré-aprovada por este plano. Enquanto pendente, implementação técnica pode testar o mecanismo com fixtures, mantendo a política vigente ou o caminho novo desativado.

| Gate / responsável | Decisão concreta | O que bloqueia |
| --- | --- | --- |
| G01 Operações + Segurança/Produto | Quem pode confirmar, cancelar, assumir/liberar atendimento alheio, editar preço/lote/fiscal e reconhecer cada família de alerta; necessidade de motivo/elevação já suportada | Ativação de capacidades novas ou mudança de autoridade. Permissões atuais continuam valendo até migração aprovada |
| G02 Financeiro/Caixa + Operações | Terminal/gaveta do acerto, divergência de troco, custódia, quem resolve entrega já iniciada sem registro de saída e transição de responsabilidade | Piloto de COD, troco, equipamento e auto-courier. Nenhum lançamento sintético |
| G03 Operações + owner marketplace/courier | Cancelamento local versus pedido de cancelamento externo; códigos válidos, aprovação externa, procedimento de unknown, contato autorizado e SLA do fornecedor | Piloto da integração afetada; não alterar transições comerciais unilateralmente |
| G04 Produto/Operações | Critério de urgência e promessa ao cliente por canal, encomenda, loja fechada, assunção de atendimento e som | Mudança de prioridade/timers/automação. Usar ChannelConfig/calendário atuais até decisão |
| G05 Catálogo + responsável fiscal/nutrição | Escopo do lote, tiers, revisão de dados sensíveis e evidência para ingredientes/alérgenos; política de retenção de rascunhos em estação compartilhada com Segurança | Publicação sensível e retenção persistente. IA não inventa ingredientes nem decide classificação |
| G06 Operações + responsável técnico | Aprovar budgets, aparelhos, rede, personas, amostra e critérios do piloto após baseline WP00 | Início do piloto, não a preparação dos testes |
| G07 Responsável pelo ambiente + Operações | Alvo, janela, versão, backup, suporte de plantão, critérios de parada e autorização explícita para cada etapa em produção | Qualquer escrita, deploy, reconciliação ou envio real; este plano não concede autorização |
| G08 Operações + dados/privacidade | Em dois momentos independentes: aprovar retenção/isolamento de recibos e drafts antes de usá-los; aprovar descarte/remoção após evidência de encerramento | Retenção nova antes do piloto; contract/removal após janela de retorno |

## 5. Contratos de execução

Estes contratos são normativos. Os WPs da seção 7 indicam entrega e prova de aceite; a matriz da seção 8 especifica os ensaios; migração e rollback ficam na seção 10.

### C01 — Projeção oferece a ação; domínio decide novamente

Usar `Action` de `shop/projections/types.py` (`ref`, `kind`, `label`, `enabled`, `reason`, `href`, `method`, `payload_schema`, `idempotency`, `confirmation`) e o export gerado. Card, tabela e detalhe compartilham elegibilidade; conforme ADR-014, decisão canônica pertence a shop e apresentação específica fica na borda.

A Action informa intenção exata, estado/revisão base, consequência, inputs ausentes e bloqueio. A API revalida pessoa, recurso, turno, estado, saldo e precondições. Recuperação aponta para recurso existente e autorizado; não oferece bypass de pagamento/estoque.

Conservar quantidade decimal/unidade, dinheiro inteiro `_q` com parser único e prazo do servidor. Pagamento, produção, entrega, fiscal e sync permanecem fatos distintos, sem novo status substituto de Order.

### C02 — Uma intenção, um resultado consultável

Mutação que pode duplicar efeito ou sobrescrever versão transporta chave estável e precondição. Retry/retomada conserva a chave; nova chave corresponde a nova intenção. `advance` inclui ação-alvo e base esperada. Operação naturalmente idempotente, como marcar lida, pode conservar sua implementação se a releitura comprovar resultado e autorização, sem recibo redundante.

Estender IdempotencyKey/remote_mutations. Escopo vincula pessoa, operação e alvo; fingerprint cobre payload normalizado, base, inputs, conjunto congelado e versão contratual. Mesma chave com payload diferente conflita sem executar. Autorizar antes do replay; não expor recibo alheio.

**Efeitos locais, eventos, agendamento durável e resultado da intenção compartilham o commit.** Rede fica fora do lock; efeitos remotos usam Directive. Crash antes do commit não aplica; depois não repete efeito local; durante fornecedor mantém resultado desconhecido até reconciliação.

Resposta contém intenção, resultado, projeção/revisão atual, alterações aplicadas e pendências. Resultados possíveis: aplicado, já aplicado, não aplicado, em andamento, parcial e desconhecido — não são estados de Order. Consultar resultado não causa novo efeito; preservar separadamente o resgate de gateway já existente no detalhe.

HTTP: 200 aplicado/replay/no-op explicado; 202 aceito com acompanhamento; 400 input inválido sem escrita; 401/403 identificação/permissão; 404 alvo indisponível; 409 base/fingerprint conflitante. 5xx não prova ausência de efeito. Timeout conserva chave e consulta resultado; não recomenda repetição cega.

BFF deve encaminhar em allowlist `Idempotency-Key`, precondição e correlação, além da resposta relevante; hoje esses headers não atravessam o proxy. Preservar CSRF/cookies e identidade do servidor. Sem commit offline de ações operacionais.

Revisão: token opaco do estado canônico relevante, comparado sob lock. WP00 define campos/dependências; WP02 testa todos os writers. OrderEvent.seq sozinho não cobre nota/config/preço. Coluna monotônica no agregado existente só com necessidade demonstrada e migração mínima.

Retenção proposta: sete dias apenas para novos escopos do Gestor, mediante G08; não alterar os 24h globais do helper nem encurtar recibos permanentes. Expiração da chave não autoriza replay de base antiga ou reenvio de efeito desconhecido.

### C03 — Concorrência preserva dados e responsabilidade

Reler sob atomic/select_for_update e alterar somente campos autorizados sobre dados frescos. Mesmo campo concorrente: 409 com base/valor atual, preservando draft. Campos independentes: merge sem apagar blocos. Testar Order, produto/célula, Channel.config e ordenação separadamente.

Documentar ordem de locks compatível com os writers de Order, WorkOrder, Fulfillment, CashShift/Entry, Hold e tickets; timeout deve ser recuperável. Provar com conexões PostgreSQL independentes. Atribuição é contexto de atendimento, não lock de segurança ou permissão adicional.

### C04 — Cancelamento e suas consequências

Preservar política, permissão avançada e desafio PIN/crachá existentes. Antes de confirmar, mostrar pedido/estado, motivo, valor, efeitos em cozinha/estoque, dependência externa e destinatário da mensagem; reutilizar dados conhecidos.

Distinguir recusa, cancelamento local, solicitação externa, estorno digital, devolução física e cancelamento fiscal pelas fontes atuais. Após o comando, consultar Payman/Cashman/fiscal/Directive para informar ocorrido e pendente.

iFood deve distinguir motivos disponíveis, não aplicável e erro; revalidar código no domínio/adapter. Indisponibilidade não vira lista vazia ou código fictício. Ação impedida oferece acompanhamento/contato autorizado. Mudanças de autoridade dependem de G01 e de política externa, de G03; sem segunda verdade de cancelamento.

### C05 — Retomada de efeitos parciais

Mapear fase → efeito devido → evidência de conclusão → chave → recuperador para KDS, estoque, fulfillment/courier, fiscal, loyalty e avisos. Estender durabilidade existente onde faltar; não reiniciar todo lifecycle.

Courier preserva fato externo e tentativa/corrida; status repetido reavalia derivação pendente, inclusive em estado terminal. Evento antigo não altera corrida nova. E/F não prova troco/equipamento entregue: mostrar “coleta informada pela central; registro de saída pendente” e aplicar G02.

Após aceite remoto com resposta perdida, consultar por referência homologada antes de repetir. Sem consulta confiável, manter unknown, responsável e verificação autorizada; não prometer exactly-once externo. Preservar adoção fiscal. Para avisos, ler `notification_delivery`: enfileirado, aceito pelo backend, skipped, entregue e lido exigem evidências distintas; Directive.done não prova envio.

Recuperador usa estado fresco, idempotência, backoff, limite, alerta, dry-run e correlação. Não marcar done por inferência de status avançado. Provar crash antes/depois de enqueue, efeito e gravação do resultado.

### C06 — Cadastro e lote exatos

Preservar attributes/proveniência e flags estritas. Validar todo patch antes de save/signal: tipos, listas, decimais e schemas social/nutrição/fiscal. Lote usa os mesmos validadores de publicação e efeitos canônicos do caminho individual.

Prévia congela SKUs/canais/tiers, excluídos, alcance global/local, preços antes/depois e revisões, pelo pricing atual. Mudança de filtro, coleção smart ou preço exige recompor prévia e novo aceite; nenhum SKU entra silenciosamente.

Dentro do limite medido em WP00, escrita local é integral ou recusada integralmente. Acima dele, orientar redução do recorte. Processamento parcial de preços requer contrato por item e gate explícito. Sync remoto é independente, por destino, em CatalogSyncState/Directive: falha retoma sync, nunca reaplica pct/delta.

Collection/CollectionItem continuam donos da ordem; validar conjunto/versão e conferir matriz/saídas. Ordem global e seleção do display são distintas. Receita permanece derivada até override explícito; patch omite campos não editados. IA sugere por campo, sem publicar ou inventar ingredientes; rotulagem exige fonte e G05.

### C07 — Contexto preservado

Preservar recurso, filtros/busca, modo, zona/data, scroll/foco, draft por campo, base/revisão, seleção, diálogo e intenção pendente. SSE atualiza fatos sem sobrescrever dirty; conflito mostra diferenças sem exigir copiar/colar. Voltar do detalhe restaura a fila.

Erro permanece junto ao recurso com estado e próxima ação; toast é complementar. Editor fecha só com sucesso conhecido ou descarte explícito, sem confirmação redundante para draft vazio. Resposta assíncrona confere identidade/base: SKU A não hidrata B. Reidentificação não autoenvia; troca de pessoa não herda dados.

Reusar operator-kit, URL para recorte e estado por pessoa/recurso. Persistência após reload exige escopo, TTL, minimização e descarte aprovados em G05/G08; antes disso, limitar promessa à sessão e proteger saída. Credenciais/cartão nunca entram em drafts. Testar salvar, timeout, expiração, fechar/voltar e respostas invertidas separadamente.

### C08 — Frescor e próxima ação

Leitura expõe geração/hora do servidor e versão. Mostrar última atualização útil e falha de leitura separadas de SSE conectado. Compensar relógio local com amostra do servidor e tempo monotônico; refetch ao acordar/reconectar. Contador zerado não decide transição.

Coalescer refreshes, descartar respostas antigas e manter fallback. Se stale impede comprovar precondição, bloquear ação sensível com recuperação explícita. Conservar última leitura/draft; erro não vira zero itens.

Preservar OperatorAlert da loja, UserNotification pessoal, som/autoplay e seus escopos. Ack reconhece, não resolve. COD, custódia, fiscal e efeitos incompletos continuam encontráveis após ack/completed. Oferecer próxima ação no card/detalhe/célula ou deep-link autorizado, sem central paralela. G01 decide destinatários/autoridade; H09 exige decisão antes de ampliar ações da caixa pessoal.

## 6. Budgets de esforço e prova antes/depois

### 6.1 Unidade de medida

Vetor `E = (A, N, R, M, X, T)`: ativações deliberadas (clique/toque/atalho/submit); mudanças de página/painel; campos redigitados cujo valor o sistema já tinha; fatos que precisam ser memorizados fora da tela; trocas para outro app/suporte; tempo ativo humano. Digitar dado novo legítimo conta no tempo, não em R. Espera de fornecedor é medida separadamente. Login, segunda assinatura, confirmações e inputs físicos são registrados como parcelas separadas **e somados ao total da jornada**. Nunca removê-los, pré-confirmá-los ou esconder suas ativações para maquiar budget. Os sub-budgets da tabela começam no estado explicitado; o relatório inclui também acesso ao recurso e todas as entradas anteriores.

As contagens “antes” abaixo são **percursos estruturais do código**, não cronometragem de pessoas. `≥` é limite inferior; `?` exige medição. Depois é contrato alvo para aceite, não resultado entregue nesta sessão. Todo experimento usa mesmo pedido, permissões, dados, dispositivo e estado de rede; medidas pareadas por cenário.

### 6.2 Jornadas verificáveis

| Jornada / cenário de partida | Antes observado/derivado do código | Depois contratado e budget |
| --- | --- | --- |
| J01 Iniciar preparo de pedido elegível no card | Uma ativação; preservar esse caminho maduro. Repetição depois de resposta perdida pode marcar ready (D01) | 1 A, 0 N/R/M/X; rótulo específico e resultado visível. Nunca adicionar modal genérico ao caminho seguro |
| J02 Interromper nota com SSE | Abrir detalhe 1 A; digitar L caracteres; refresh substitui nota; retomar exige redigitar ao menos 1 campo/L caracteres e salvar (D09) | Abrir + salvar, no máximo 2 A além da entrada original, 1 N, **R=0/M=0**; evento atualiza contexto sem tocar draft. Conflito: até 2 A extras para comparar/escolher |
| J03 Dois operadores editam nota/atribuição | Duas escritas podem terminar sem erro e perder nota (D02); detecção não tem limite de esforço garantido | Campos distintos preservados; mesmo campo: 1 conflito explicado, até 2 A adicionais, R=0, M=0, X=0. Pessoa informa conscientemente nova intenção |
| J04 Resposta de avanço perdida após commit | Segundo POST avança outra etapa; operador precisa abrir/conferir histórico, custo de correção física não limitado (D01) | 0 A adicionais para consulta automática; no máximo 1 A “verificar resultado”; mesma chave, um efeito. Resultado local conhecido até budget técnico; unknown remoto não vira falha |
| J05 Cancelamento já impossível | A base final já bloqueia e explica pela capability; API devolve 409 na transição impossível. O 200 de D03 pertence só à base recebida e foi refutado na atual | Se inelegível já na leitura, 0 A inválidas e motivo visível. Se disputa: até 1 A para abrir contexto atualizado, R=0; nunca afirmar cancelamento/estorno inexistente |
| J06 Despachar COD com equipamento | App já oferece troco sugerido e equipamento; preservar. E do courier pode ficar preso após falha parcial (D04) | Após seleção do pedido, até 3 A para registrar saída, excluindo dado físico novo; R=0/M=0. Resultado parcial informa fato externo e registro faltante no mesmo detalhe; nenhum segundo despacho |
| J07 Concluir entrega e acertar dinheiro | Handoff e acerto são fatos distintos; pedido concluído pode sair da fila ativa, exigindo reencontro pelo contexto disponível | Pendência derivada continua acessível no recorte existente; até 1 A para abrir e 1 submit de acerto, mais inputs físicos necessários; R=0, sem copiar valor/ref/terminal |
| J08 Reprecificar N SKUs em canal escolhido; falha de sync | Selecionar + escolher operação/valor + aplicar; erro limpa seleção e valor (D12/D13); refazer exige N seleções ou novo recorte e redigitação ≥1 | Da seleção pronta: até 3 A (abrir, prévia, confirmar), R=0/M=0; prévia identifica todo alcance. Falha remota: até 1 A para retomar sync, **0 reaplicações de preço** |
| J09 Reordenar produto em coleção manual | Um drag grava B,A, refresh volta A,B (D06), induz novo drag | Um drag ou sequência de teclado equivalente; ordem B,A após refresh/reload/saída. 0 repetição corretiva; foco permanece no item |
| J10 Editar coleções do feed e perder resposta | Aplicar fecha editor mesmo na falha; reabrir/hidratar exige reconstruir seleção (D13) | Draft e ref preservados; consulta do resultado antes de reaplicar; até 1 A extra, R=0. Erro de GET nunca sugere criar feed (D14) |
| J11 Cancelamento externo sem lista de motivos | Falha e não aplicável viram []; risco de pedir texto/código novamente (D15) | Uma explicação persistente; 1 A para reconsultar se autorizado; motivo digitado preservado. Sem lista obrigatória, nenhuma submissão fabricada |
| J12 Voltar da interrupção/expiração de sessão | Board já consulta sessão no erro e atualiza ao voltar à aba; outros caminhos têm diferenças; persistência de draft não garantida | Reidentificar uma vez; voltar ao mesmo recurso/recorte e draft aprovado para retenção; 0 redigitação operacional, até 1 A para retomar intenção ainda não enviada. Troca de pessoa não herda draft |
| J13 Fiscal/aviso/estoque falha após estado avançar | Alguns efeitos têm Directive/alerta/sweeper maduros; preparing/completed não têm a mesma cobertura de fase (D18) | Pedido mostra fato concluído e pendência específica; até 1 A para caminho autorizado de recuperação. Nenhuma reexecução de pagamento, produção ou mensagem por botão genérico |
| J14 Reenviar link sem sair do pedido | Botão e URL existentes reduzem esforço; toast afirma enviado com fila pendente; done/skipped também vira enviado (D19) | 1 A de reenvio autorizado, 0 N/R/M/X; feedback “reenvio solicitado” e evolução pela evidência existente. Timeout consulta intenção; opt-out/sem contato não vira envio nem abre canal alternativo não autorizado |
| J15 Avançar seleção de pedidos com falha no segundo | `useOrdersBoard.actMany` usa Promise.all, mantém erro por ref, devolve contagem de falhas e faz um refresh ao final; faltam intenção estável e retomada durável de cada resultado | Preservar resultados por ref; nenhum replay das refs aplicadas. Após seleção e confirmação exigida: até 1 A para conferir/retomar somente elegíveis faltantes; R=0/M=0. Não prometer atomicidade entre pedidos com efeitos físicos independentes |

Antes/depois deve incluir: card e tabela; toque e teclado; leitor de tela nos estados de erro; dois operadores; perda de resposta antes/depois do commit; worker morto após aceite remoto; falha no segundo destino do lote; aba suspensa; relógio ±5 minutos; sessão expirada no submit; vínculo de produção indisponível; nova intenção após conflito.

### 6.3 Metas quantitativas propostas para homologação

| Indicador | Budget inicial | Como provar / limite |
| --- | --- | --- |
| Feedback local da ação | p95 ≤100 ms para estado de envio/busy, sem alegar sucesso | Medir no aparelho piloto, não em runner vazio |
| GET fila/detalhe em fixture representativa | p95 ≤500 ms backend; interação utilizável ≤1,5 s em rede piloto | 1/10/100/500 pedidos, histórico e dados ricos; registrar hardware, payload, queries e cold/warm |
| Comando estritamente local | p95 ≤800 ms para resultado conhecido; após retomada da conexão, consultar resultado em ≤2 s p95 | Excluir dependência remota do tempo local, reportá-la separadamente |
| Frescor SSE | commit→fato visível ≤2 s p95 | Medir cadeia completa; SSE aberto não basta |
| Fallback de polling | leitura útil em até 35 s enquanto rede/servidor respondem; refetch imediato ao retomar aba | Preserva os 30 s atuais mais tolerância de transporte; não reduzir arbitrariamente para mascarar push quebrado |
| Recuperação de contexto | 100% dos cenários de interrupção previstos com R=0; conflito sem perda de draft | Inclui privacidade na troca de operador e limites de retenção aprovados |
| Segurança da intenção | 0 efeitos extras em replay/concorrência nos ensaios; 0 falso sucesso; 0 escrita por persona sem permissão | Contadores e estados dos livros, não só HTTP/toast |
| Clareza operacional | ≥95% das respostas corretas a “o que ocorreu/o que falta/como continuar”; 100% nos cenários de dinheiro/cancelamento/unknown | Perguntas no instante da falha, sem explicar antes; qualquer erro crítico bloqueia |
| Esforço do conjunto J02–J15 | p50 e p95 de T não pioram; reduzir ≥30% de ativações de recuperação agregadas contra baseline; R=0 para dados já disponíveis | Não compensar regressão crítica com média de cenários fáceis; J01 não pode ganhar passos |
| Concorrência HTTP | no máximo 1 refresh ativo por recurso e 1 refresh agregado seguinte por rajada; nenhuma resposta antiga aplicada | Fake clocks + rede reordenada + traces no browser |

Metas de 500 ms/800 ms/30% são propostas técnicas a calibrar em G06; não mudar silenciosamente depois de medir. Se o equipamento torna a meta inviável, registrar baseline e aprovação do novo limite antes do piloto. P0, R=0 e ausência de falso sucesso não podem ser relaxados por desempenho.

Protocolo do piloto: 3–5 operadores representando as funções aprovadas, ou toda a equipe se menor; 10 execuções pareadas por jornada crítica por operador em ensaio controlado; alternar ordem antes/depois para reduzir aprendizagem. Registrar distribuição completa, erros, abandono, consultas ao colega, hesitação e esforço de recuperação. Para tarefas raras/perigosas, usar simulação fiel, nunca provocar falha em pedido real. Em piloto real, observar ao menos 5 turnos completos com acompanhamento, incluindo abertura, pico e fechamento. Esta amostra detecta problemas práticos, não demonstra estatisticamente ausência universal de incidentes raros.

## 7. Work packages e dependências sem ciclos

Separar três estados de entrega: **T** implementado e verificado tecnicamente; **P** piloto aprovado; **R** rollout aprovado. Um pacote T não autoriza P ou R. Trabalho técnico independente pode continuar enquanto um gate comercial está pendente, mas a mutação correspondente permanece sem ativação nova.

```text
WP00 baseline e decisões de contrato
 ├── WP01 projeções/actions e acesso
 └── WP02 intenção durável e concorrência
WP01 + WP02 ── WP03 mutações de pedidos/caixa
WP02 ───────── WP04 efeitos externos e recuperação
WP01 + WP02 ── WP05 catálogo/feeds íntegros
WP01 + WP02 ── WP06 contexto e interações
WP01 ───────── WP07 frescor/desempenho
WP03 + WP04 + WP05 + WP06 + WP07 ── WP08 retomada/observabilidade integrada
WP03 + WP04 + WP05 + WP06 + WP07 + WP08 ── WP09 hardening/migração/ensaio
WP09 + G01…G06 + retenção G08 aplicáveis + G07 do piloto ── WP10 piloto
WP10 + G07 de cada expansão ── WP11 rollout
WP11 + janela de retorno + G08 ── WP12 encerramento
```

Cada pacote entrega código/testes/contrato/evidência **na futura execução**. IDs abaixo são unidades revisáveis, não autorização para implementar nesta sessão.

G08 tem uma decisão antecipada de retenção e uma aprovação posterior de remoção; a primeira não depende de WP12. Assim, preservar contexto no piloto não cria dependência circular com o encerramento.

Os contratos C01–C08 e a matriz de testes valem integralmente para os WPs correspondentes. Cada pacote entrega implementação, testes e evidência de aceite; aplica o rollback da seção 10. A tabela de dependências acima é normativa.

### WP00 — Baseline e escopo · P0

**Dono:** liderança técnica + Operações. **Dependência:** nenhuma.

Inventariar rotas, efeitos, atores, writers, locks e consumidores; revalidar D01–D20, preservando D03 corrigido. Conferir referências por hash; medir esforço e consultas antes de alterar. Definir revisão/fingerprint, limite de lote, matriz fase/efeito e decisões G01–G08.

**Aceite:** cada escrita tem fonte canônica, política, responsável, fixture, efeito e rollback; matriz D/H/G→C→WP→teste completa. Segurança local não depende de terminar os outros planos. Sem migração operacional.

### WP01 — Actions e acesso · P0/P1

**Dono:** shop + frontend. **Dependência:** WP00. **Escopo:** C01; D08/D10/D11.

Evoluir projeções/export com elegibilidade compartilhada e resolver existente, distinguindo bloqueio, falta de permissão e desconhecido.

**Aceite:** card/tabela/detalhe não enviam ação sabidamente bloqueada; API recusa personas sem direito; quantidade/unidade mantêm precisão; export é reproduzível. Preservar reconciliação do detalhe. G01 é exigido apenas para mudar política.

### WP02 — Intenção e concorrência · P0

**Dono:** backend/core + operator-kit. **Dependência:** WP00. **Escopo:** C02/C03; D01/D02 e base de D12/D17.

Estender helper/IdempotencyKey, BFF, revisão e merge; fechar atomicidade efeito/resultado. Provar writers e consumidores existentes.

**Aceite:** matriz de concorrência/crash da seção 8 aprovada, incluindo chave ausente, payload divergente, lock timeout, falha ao salvar resposta e reidentificação. Um efeito local ou recusa comprovada; nota e atribuição coexistem. Cliente antigo não contorna o contrato seguro.

### WP03 — Pedido, cancelamento e caixa · P0

**Dono:** shop + Operações; Financeiro em G02. **Dependências:** WP01/WP02. **Escopo:** C03/C04; D15/H02/H03; regressão D03.

Aplicar resultado explícito, motivos tipados e turno/terminal autorizado; preservar livros e custódia. Deep-link ao caixa conserva ref do pedido.

**Aceite:** late capture/estorno parcial não reabrem preparo; dois turnos não duplicam acerto; turno fechado não recebe movimento. Totais conciliam Order/Payman/Entry. Cancelamento impossível continua recusado e fato remoto não inventa saída física.

### WP04 — Efeitos e recuperação · P0

**Dono:** integração + shop. **Dependência:** WP02. **Escopo:** C05; D04/D18/D19/H01/H03.

Instrumentar fases e estender recuperadores; courier repetido reavalia pendência local. Preservar dedupes existentes.

**Aceite:** falhas em cada fronteira retomam somente trabalho faltante, com alerta no esgotamento. Cobrir F sem E, E/ChangeOutRequired repetido, corrida antiga, resposta remota perdida, fiscal autorizado e worker reiniciado. Queued/skipped não aparecem como enviado.

### WP05 — Catálogo e Feeds · P0/P1

**Dono:** catálogo + frontend; G05 fiscal/nutrição. **Dependências:** WP01/WP02. **Escopo:** C06; D05/D06/D07/D12/D13/D14/H05.

Implementar validação integral, prévia exata, resultado de sync independente e leitura da ordem canônica. Corrigir erro/vazio e conferir links Admin por reverse/projeção.

**Aceite:** campo final inválido não salva parte do patch; gate individual/lote coincide; retry não reaplica preço; falha no segundo destino é rastreável. Smart collection não amplia intenção; tiers, drag/teclado e saída concordam; feed não ganha preço próprio.

### WP06 — Rascunho e retomada · P1

**Dono:** frontend/operator-kit + UX operacional. **Dependências:** WP01/WP02. **Escopo:** C07; D09/D10/D13/D17/H06.

Implementar base/draft/server e contexto por pessoa/recurso, com busy/erro por operação e proteção de resposta atrasada.

**Aceite:** J01 mantém um clique; J02/J03/J10/J12 têm R=0 no escopo aprovado. 401 conserva texto sem autoenviar; SSE conserva foco; troca de operador isola dados. Diálogo/reorder operam por teclado, touch e leitor de tela. Alvos frequentes ≥44×44 px, principal ≥48 px, com tokens compartilhados. Pós-reload depende de G05/G08.

### WP07 — Frescor e leitura · P1

**Dono:** projeções + frontend. **Dependência:** WP01. **Escopo:** C08; D16/D20/H04.

Coalescer refreshes, usar hora do servidor e eliminar consultas Hold por card pelo serviço canônico. Cache exige invalidação comprovada; paginação preserva contagens e pendências.

**Aceite:** budgets da seção 6 em hardware declarado, incluindo 500 pedidos; D20 usa no máximo um batch ao Hold, preservando waitlist. Demais queries têm budget medido. Relógio ±5 min/suspensão não antecipam ações; erro, vazio, permissão e stale são distintos.

### WP08 — Evidência e próxima ação · P1

**Dono:** shop/observabilidade + UX. **Dependências:** WP03–WP07. **Escopo:** C05/C07/C08 e seção 9.

Apresentar resultado e pendência no recurso original, ligados às fontes existentes; conservar leitura válida na falha da caixa pessoal. Não ampliar H09 sem decisão.

**Aceite:** cada falha injetada tem mensagem, responsável, ação autorizada, trace e contador; outro operador retoma sem explicação oral. Pendência monetária não some por ack/completed; interface não exige interpretar payload técnico.

### WP09 — Gates técnicos e migração · P0 de liberação

**Dono:** qualidade/release. **Dependências:** WP03–WP08. **Escopo:** seções 8–11.

Executar testes integrados e PostgreSQL, convivência de versões, migração, backup/restore e rollback. Preparar coorte/suporte sem ativá-la.

**Aceite:** P0 resolvidos ou capacidade formalmente excluída e bloqueada; P1 da coorte concluídos; hipóteses críticas comprovadas ou bloqueadas. Gates verdes, esforço de laboratório registrado e rollback ensaiado com livros/chaves intactos. Entrega T; não autoriza P/R.

### WP10 — Piloto acompanhado · validação operacional

Dono: Operações. Depende WP09 e gates aplicáveis, incluindo autorização do ambiente.

Primeiro ensaio com pedidos sintéticos; depois coorte pequena autorizada de estação/canal/personas, com suporte de plantão e supervisão dos casos sensíveis. Aplicar protocolo da seção 6, conciliar fechamento e ouvir dificuldade sem treinar a resposta da avaliação de clareza.

Aceite: 5 turnos completos sem falso sucesso, efeito repetido, perda de draft ou dinheiro sem origem; budgets atingidos por jornada; todos os pedidos pendentes com owner; Operações assina evidência. Um piloto só de leitura/retirada não autoriza courier/COD/publicação em lote. Falha retorna a WP correspondente para nova versão, preservando DAG da entrega — não é permissão para pular hardening.

### WP11 — Rollout por capacidade e coorte · implantação

Dono: release + Operações. Depende WP10 e G07 específico.

Proposta de sequência: leitura/contexto → mutações locais de pedidos → integrações/COD autorizados → catálogo/lotes/feeds. A ordem concreta respeita consumidores e tráfego real; nenhuma fase expõe mutação antes do backend seguro. Ampliar 1 estação → pequena coorte → metade → total, com ao menos um ciclo de pico/fechamento e conciliação por etapa, além dos 5 turnos do piloto. Percentuais exatos dependem do número de estações; não simular “10%” com uma estação.

Aceite: checks de liberação e budgets estáveis, sem pendência órfã, operadores orientados, evidência por coorte e autorização registrada. Capacidade não homologada permanece bloqueada. Cada expansão tem mecanismo de parada imediato e responsável nomeado.

### WP12 — Encerramento e remoção controlada

Dono: release/dados + Operações. Depende WP11, janela de retorno e G08.

Janela proposta mínima: 7 dias e dois fechamentos completos após rollout total, ampliada se ciclos reais exigirem. Remover branches temporários de compatibilidade apenas com consumidores antigos zerados e evidência de reconciliação. Reter chaves e trilhas conforme política aprovada. Não apagar arquivo/tabela porque “parece legado”.

Aceite: DoD completa; relatório de ganhos e limitações; owner de manutenção; nenhum workflow/regra/source-of-truth duplicado; pendências remanescentes explicitamente aceitas fora do escopo, sem fechar risco crítico como tarefa concluída.

## 8. Matriz de testes e gates de qualidade

| Camada | Casos obrigatórios | Evidência de aceite |
| --- | --- | --- |
| Contrato/schema | Campos novos gerados, Action consistente, decimal/centavos, erros tipados, unknown/partial, clientes antigo/novo | Export reproduzível; contratos API e teste de import boundaries sem exceção oportunista |
| Permissão | Anônimo, sem staff, staff sem permissão, persona de cada função, troca/revogação de sessão, estação travada, recurso alheio, replay de outra pessoa | Mesmo gate em GET/POST/SSE e links; zero escrita/vazamento no replay |
| Domínio | Fluxos pickup/delivery/preorder; manual/auto-confirm/auto-cancel; preparo operador/automático; pagamento externo/PIX/cartão/cash COD; conflito e cancelamento impossível | Estado, eventos, snapshot e livros corretos; nenhuma ação do frontend decide política |
| Concorrência PostgreSQL | Dois cliques/chaves; mesmo/diferente payload; nota/atribuição/fiscal/courier; confirmar/cancelar/timeout; acerto em dois turnos; lote/config/ordem simultâneos | Barreiras entre leituras/locks/commit; nenhuma perda de bloco; efeitos extras=0; conflict legível |
| Fault injection | Desconectar antes/depois do commit, matar worker antes/depois do fornecedor, falha de enqueue/result save, timeout desconhecido, falha no segundo destino, callback repetido/antigo | Resultado consultável com mesma chave; reexecução só do faltante; sem mensagem de sucesso falso |
| UI real | SSE durante draft, voltar à fila, trocar SKU enquanto fetch/IA roda, sessão expira, cancelamento do diálogo, teclado/touch/reorder, dois tabs | R=0; draft/foco/seleção preservados; pessoa nova isolada; disabled não emite request |
| E2E integral | Browser→Nitro→Django→PostgreSQL→worker→SSE→browser com fakes de rede externa | Não se satisfaz com interceptar todos os POSTs em mock; verificar estado canônico de fato |
| Fiscal/estoque/caixa | Nota já autorizada, estorno parcial, cash refund físico pendente, quantidades fracionárias, gate em lote, retorno de equipamento, pedido já completed | Reconciliar livros; consulta antes de reenvio; nenhuma compensação inventada |
| Catálogo/feeds | Patch inválido por último, bool inválido, limites/tier, coleção smart alterada, ordem persistida, publish/retract, preço no destino, GET 403/5xx | Mesma fonte em produto/célula/saída; nenhuma seleção silenciosamente ampliada |
| Performance | Cold/warm, 1/10/100/500 pedidos, catálogo/canais dimensionados, 2/10 clientes, burst SSE, payload rico, clock drift/suspend | Distribuições p50/p95, queries, bytes, memoria/CPU e trace; budgets aprovados |
| Migração/rollback | Base anterior populada, campos opcionais, worker antigo, browser antigo, chaves in_progress/unknown, scripts dry-run e restore | Leitura contínua; mutação incompatível bloqueada; dedupe e livros sobrevivem ao rollback |

Gates de comando na execução: suítes de pedidos/backstage e domínios afetados; `npm test` e `npm run typecheck` do Gestor; testes de operator-kit se transporte/sessão mudar; Playwright integral; checks de arquitetura e esquema. Quando houver Admin: `make admin` obrigatório e QA visual de permissões/templates canônicos. Quando houver migration: checks/migrações do repositório, banco vazio e banco populado, além do dry-run de dados. Executar também a suíte geral exigida pelo CI antes da entrega técnica. Não reportar lint/build/E2E como executados se não foram.

Testes novos devem capturar o comportamento observado e sua consequência, não copiar branches da implementação. Para concorrência, usar processos/conexões independentes; mocks não substituem locks. Para perda de resposta, confirmar efeito no servidor e cortar a resposta depois: simplesmente devolver 500 antes da execução não cobre D01.

## 9. Observabilidade e operação de falhas

Reusar `shop.services.observability.operational_event`, logging/Sentry e OperatorAlert. Cada comando produz correlação técnica entre request, intention, resource, actor autorizado, base_revision, resultado local, replay/conflict e refs de Directive/turno quando aplicável. Cada efeito externo registra tentativa, identificador externo se conhecido, início/fim, resposta classificada e motivo de unknown. Não logar tokens, payload integral, nota de cliente, endereço/telefone ou dados de cartão. Métricas usam labels limitados; refs ficam nos logs controlados, não em labels de alta cardinalidade.

Placar mínimo por coorte/versão: comandos aplicados/replayed/conflicted/unknown; idade do resultado pendente; efeitos devidos sem conclusão; retries por causa; ledger mismatch; draft restaurado/perdido; refresh stale/descartado; latência/frescor; erro/permissão/sessão por endpoint; tempo/ativações de recuperação. Métricas de produto podem amostrar interação sem coletar o texto digitado.

Alertas técnicos iniciais: qualquer efeito repetido, sucesso falso ou divergência monetária → parar capacidade afetada e acionar owner; efeito local sem resultado reconciliável por >2 minutos → investigar e manter indicação no recurso; pendência externa ultrapassando SLA homologado → owner de integração; fallback acima do budget com servidor acessível → responsável de disponibilidade. Limiares externos dependem de G03, não de números inventados. Ack não encerra esses critérios.

Runbook por falha: identificar intenção/recurso; consultar livro/Directive/provedor permitido; classificar aplicado/não aplicado/parcial/desconhecido; escolher recuperador existente ou ação humana autorizada; registrar evidência; devolver orientação no recurso. Nunca começar por “rode novamente” ou editar Order.data manualmente. A pessoa não precisa entender `Directive` para continuar; a equipe técnica precisa dessa referência para diagnosticar.

## 10. Migração, rollout e rollback

1. **Preparar:** inventário de versões e writers, baseline, backups testados e limites/gates. Sem escrever dados reais nesta fase documental.
2. **Expandir:** campos mínimos em estruturas existentes, leitores tolerantes e contrato versionado; índice/constraint avaliado em PostgreSQL. Proibida nova tabela de fila/recovery/order/price para conveniência de UI. Testar consumers de IdempotencyKey, inclusive checkout/reorder existentes.
3. **Habilitar servidor seguro:** atomicidade local, dedupe, revisions, validators e capacidade negociada. Cliente antigo sem intenção/precondição não executa ação sensível do caminho novo; recebe orientação de atualização sem perder draft. Não fazer dual-write para outro modelo de negócio.
4. **Migrar clientes e workers:** versão compatível antes de liberar capacidade; deploy técnico não ativa piloto. Tratar sessão/abas antigas e registrar uso residual. Manter rollout por capacidade, não apenas por flag cosmética.
5. **Reconciliar dados:** scripts existentes ampliados com dry-run, contagens e amostras; nenhuma fase antiga marcada done sem evidência; unknown não convertido em failed só por idade; não alterar status/transações para coincidir com relatório. Correções de dinheiro, estoque ou fiscal exigem ação canônica e gate adequado.
6. **Pilotar/ampliar:** WP10/WP11 e autorizações específicas. Não inferir autorização para produção de um pedido de “executar o plano”.
7. **Contrair:** apenas após WP12/G08; preservar recibos e histórico. Remover caminho de compatibilidade com busca de consumidores e testes, não mantê-lo como fonte paralela permanente.

**Parada/rollback:** um efeito repetido, perda confirmada de contexto sensível, falsa afirmação monetária/cancelamento ou violação de permissão suspende imediatamente novas mutações da capacidade/coorte. Preservar leitura, logs, drafts autorizados, chaves e directives. Reconciliar comandos em voo antes de redirecionar tráfego. Voltar ao último release seguro compatível; se a versão anterior contém o defeito P0, manter mutação suspensa em vez de restaurar insegurança. Não derrubar recursos independentes sem motivo.

**Por tipo:** UI retorna à versão compatível conservando draft; preço restaura valores exatos condicionados à versão e com nova intenção aprovada; feed reverte configuração anterior apenas sem concorrência não resolvida; dinheiro/estoque usam lançamentos compensatórios existentes com responsável; fornecedor é consultado antes de compensar/repetir; migration expandida pode permanecer durante rollback. Down migration destrutiva e limpeza de idempotência não fazem parte de resposta emergencial.

RTO técnico proposto para suspender capacidade: ≤5 minutos após detecção/acionamento; evidência de parada deve confirmar ausência de novas mutações, não apenas flag alterada. RPO para efeitos locais confirmados: zero dentro do banco íntegro; desastre de infraestrutura segue backup/RPO do ambiente, a validar em G07. Não prometer recuperação de dinheiro físico ou fornecedor em cinco minutos.

## 11. Definition of Done

### Técnica (T)

- [ ] Escopo e D/H/G atualizados no SHA executado; D03 permanece protegido; hipóteses críticas resolvidas ou capacidade bloqueada fora da coorte.
- [ ] C01–C08 e aceites WP00–WP09 comprovados pelos ensaios da seção 8, inclusive concorrência, resposta perdida e falha parcial.
- [ ] Observabilidade/runbooks disponíveis; migração, compatibilidade e rollback ensaiados; livros, chaves e trabalho de terceiros preservados.
- [ ] Evidências e limitações registradas, sem apresentar teste local como validação operacional.

### Operacional (P)

- [ ] G01–G06 aplicáveis aprovados com nomes/data/escopo; ambiente e ações reais autorizados.
- [ ] J01–J15 aplicáveis medidas antes/depois, incluindo concorrência, resposta perdida, falha parcial e retomada.
- [ ] Budgets atingidos sem esconder espera/abandono/retrabalho; R=0 para dados conhecidos; nenhuma regressão crítica compensada por média.
- [ ] Operadores sabem o ocorrido e a próxima ação; fechamento conciliado; falhas raras ensaiadas com dados sintéticos.
- [ ] Relatório assinado por Operações e owners sensíveis; T não foi anunciado como P.

### Implantação e encerramento (R)

- [ ] G07 específico por expansão; coortes estáveis, suporte e parada comprovados.
- [ ] Ganhos mantidos no pico e fechamento; nenhum resultado órfão ou regra/fonte paralela.
- [ ] Janela de rollback cumprida; G08 para retenção e remoção; compatibilidade temporária encerrada com prova.
- [ ] Entrega final responde com evidência: **o operador trabalha menos, erra menos e sabe exatamente o que aconteceu e como continuar**. Se uma dessas três dimensões falhar, a excelência operacional não está concluída.

## 12. Registro dos ensaios desta sessão

Ambiente: worktree isolado, base final `9787bbcdfe5ccd2cbb4a2097b4d97c146e86179f`; `config.settings_test`, `DATABASE_URL=''`, `REDIS_URL=''`, `PYTHONDONTWRITEBYTECODE=1`; pytest sem cache. Python 3.12.5 do venv existente; `sys.path` priorizou raiz e todos os diretórios de packages deste worktree, e as origens importadas de Orderman/Offerman foram conferidas. Node 22 selecionado por PATH para os testes finais. Nenhum provider real, PostgreSQL concorrente, operador de campo ou produção foi usado. Links ignorados reutilizam dependências; isso não equivale a instalação limpa pelo lockfile.

| Ensaio na base final | Resultado observado | Limite |
| --- | --- | --- |
| Entrada API/serviços/projeções de pedidos, catálogo, feeds e courier (11 módulos abaixo) | **221 passed, 18 subtests passed; 28,65 s** | Banco SQLite; callbacks de on_commit em TestCase não comprovam ciclo externo completo |
| Cadeia e regressões recentes (21 módulos abaixo) | **364 passed, 1 skipped; 13,51 s** | Skip: `TestConcurrentConfirmedCharge::test_two_workers_converge_on_one_intent_and_one_notice` exige PostgreSQL; nenhuma prova de locks concorrentes nesta sessão |
| Gestor Vitest após `nuxi prepare` | **12 arquivos, 221 testes passaram; 2,20 s** | Testes unitários/componentes; não E2E Django |
| Gestor `npm run typecheck` | **exit 0** | Sem build/lint/Playwright integral nesta sessão |
| operator-kit `npm test -- --reporter=dot` | **169 testes passaram em 16 arquivos; 6 arquivos Nuxt falharam na carga; exit 1** | `Cannot find module .../@nuxt/test-utils/dist/runtime/entry.mjs` pelo path da dependência ligada ao checkout original. Não classificado como defeito de produto nem como suíte integral aprovada |
| Diagnósticos temporários finais, reproduzidos também a partir do bloco do documento | **12 testes passaram; 5,48 s no ensaio e 6,02 s extraídos deste documento** | Nove defeitos R (D19 com duas provas), controle saudável D03 e segunda projeção de D20; assertions de defeito não aprovam produto |

Primeira rodada no checkout recebido: 189 + 168 testes backend e 174 frontend passaram; diagnóstico antigo passou 9/9. Esses números são **históricos**, não baseline final. Ao reexecutar os nove na base final, sete reproduções permaneceram e duas expectativas antigas falharam: D03 passou a 409, e as consultas mudaram de 3/3/3 para 4/13/103. A falha de carga do kit afeta NotificationBell, OperatorLock, useConnectivity, useOperatorSession, useRailState e useStationProvision; preparar instalação isolada pelo lockfile e repetir é gate WP00/WP09. Não houve ajuste de código para contornar o runner.

Os testes de diagnóstico foram atualizados para afirmar a realidade final; D03 virou controle saudável, D20 novo defeito demonstrado. O primeiro ensaio antigo de D04 omitiu collection=on_delivery e não reproduziu; a condição COD foi incluída explicitamente. A hipótese antiga de N+1 era refutada na base recebida e só foi confirmada, com SQL ao Hold, na base final.

Módulos de entrada, relativos à raiz:

```text
shopman/backstage/tests/test_api_orders_surface.py
shopman/backstage/tests/test_orders_service.py
shopman/backstage/tests/test_order_queue_surface.py
shopman/backstage/tests/test_orders_schema_export.py
shopman/backstage/tests/test_api_courier_change.py
shopman/backstage/tests/test_courier_backstage.py
shopman/backstage/tests/test_api_catalog_surface.py
shopman/backstage/tests/test_api_feeds.py
shopman/shop/tests/test_operator_order_contract.py
shopman/shop/tests/test_order_confirm.py
shopman/shop/tests/test_courier_service.py
```

Módulos de cadeia, relativos à raiz:

```text
shopman/shop/tests/test_lifecycle_phase_durability.py
shopman/shop/tests/test_sweep_stuck_orders.py
shopman/shop/tests/test_fiscal_handlers.py
shopman/shop/tests/test_fiscal_emission_resolver.py
shopman/shop/tests/test_fiscal_catalog_gate.py
shopman/shop/tests/test_notification_consent.py
shopman/shop/tests/test_notification_whatsapp.py
shopman/shop/tests/test_ifood_direct.py
shopman/shop/tests/test_eventstream_permissions.py
shopman/shop/tests/test_preorder_activation.py
shopman/shop/tests/test_catalog_projection_meta.py
shopman/shop/tests/test_remote_mutations.py
shopman/backstage/tests/test_api_orders_cancel_policy.py
shopman/backstage/tests/test_payment_link_resend_api.py
shopman/backstage/tests/test_production_order_sync.py
shopman/shop/tests/test_waitlist_lifecycle.py
shopman/shop/tests/test_waitlist_waits_for_payment.py
shopman/shop/tests/test_payment_gate_before_goods_leave.py
shopman/shop/tests/test_payment_timeout_gateway_check.py
shopman/shop/tests/test_payment_link_resend.py
shopman/shop/tests/test_attributes_parity.py
```

### Reprodução autocontida dos diagnósticos

Em futura execução, salvar o bloco abaixo como teste temporário **fora do código de produto**, no worktree isolado. Usar o pytest/venv do projeto, settings herméticos e sem providers reais. O resultado esperado na base final é doze testes aprovados, incluindo o controle saudável D03. Na correção, inverter as expectativas defeituosas nos testes de regressão permanentes, preservando o controle saudável.

```python
import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from shopman.orderman.models import Order
from shopman.offerman.models import Product
from shopman.shop.models import Shop
from shopman.shop.services import operator_orders, courier
from shopman.backstage.services import catalog

pytestmark = pytest.mark.django_db

@pytest.fixture(autouse=True)
def shop():
    Shop.objects.create(name="Audit local")

def order(ref="AUDIT", status="accepted", data=None):
    return Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=1500,
        data=data or {"fulfillment_type": "pickup", "payment": {"method": "cash"}},
    )

def test_repeat_advance_moves_two_stages(client):
    client.force_login(User.objects.create_superuser("audit", password="audit"))
    o = order()
    url = reverse("api-backstage-order-advance", args=[o.ref])
    for expected in ("preparing", "ready"):
        response = client.post(url, {}, content_type="application/json")
        o.refresh_from_db()
        assert (response.status_code, o.status) == (200, expected)

def test_stale_assignment_erases_note():
    a = order()
    b = Order.objects.get(pk=a.pk)
    operator_orders.save_kitchen_note(a, notes="Sem cebola")
    assert Order.objects.get(pk=a.pk).data["kitchen_note"] == "Sem cebola"
    operator_orders.assign_order(b, operator_id=1, operator_name="B", actor="B")
    a.refresh_from_db()
    assert a.data.get("kitchen_note") != "Sem cebola"

def test_cancel_completed_is_correctly_refused(client):
    client.force_login(User.objects.create_superuser("audit", password="audit"))
    o = order(status="completed")
    response = client.post(
        reverse("api-backstage-order-cancel", args=[o.ref]),
        {"reason": "cliente pediu"}, content_type="application/json",
    )
    o.refresh_from_db()
    assert response.status_code == 409 and not response.json().get("ok", False)
    assert o.status == "completed"

def test_courier_change_failure_sticks_after_retry():
    o = order(status="ready", data={
        "fulfillment_type": "delivery",
        "payment": {"method": "cash", "collection": "on_delivery", "change_for_q": 2000},
        "courier": {"id_mch": "MOCK-A", "status": "A"},
    })
    with pytest.raises(operator_orders.ChangeOutRequired):
        courier.apply_status(o, "E", source="poll")
    o.refresh_from_db()
    assert courier.get_block(o)["status"] == "E" and o.status == "ready"
    courier.apply_status(o, "E", source="poll")
    o.refresh_from_db()
    assert o.status == "ready"

def test_product_invalid_keywords_persists_name():
    p = Product.objects.create(sku="AUDIT-P", name="Antes", unit="un", base_price_q=100)
    with pytest.raises(catalog.CatalogError):
        catalog.update_product_detail(p.sku, {"name": "Depois", "keywords": "invalido"}, actor="audit")
    p.refresh_from_db()
    assert p.name == "Depois"

def test_matrix_ignores_manual_item_order():
    from shopman.offerman.models import Collection, CollectionItem
    from shopman.backstage.projections.catalog import build_catalog_matrix
    a = Product.objects.create(sku="A", name="A", base_price_q=100)
    b = Product.objects.create(sku="B", name="B", base_price_q=100)
    c = Collection.objects.create(ref="audit-c", name="C")
    CollectionItem.objects.create(collection=c, product=a, sort_order=0)
    CollectionItem.objects.create(collection=c, product=b, sort_order=1)
    catalog.reorder_collection_items(c.ref, ["B", "A"])
    assert list(c.items.order_by("sort_order").values_list("product__sku", flat=True)) == ["B", "A"]
    assert [r.sku for r in build_catalog_matrix(c.ref).rows] == ["A", "B"]

def test_bulk_bypasses_enabled_fiscal_publication_guard():
    from shopman.offerman.models import Listing, ListingItem
    from shopman.shop.models import Channel
    from django.test import override_settings
    from django.core.exceptions import ValidationError
    Channel.objects.create(ref="audit-web", name="Web")
    listing = Listing.objects.create(ref="audit-web", name="Web")
    product = Product.objects.create(sku="P", name="Produto", base_price_q=100)
    item = ListingItem.objects.create(product=product, listing=listing, price_q=100, is_published=False)
    with override_settings(SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH=True):
        with pytest.raises(ValidationError):
            catalog.set_cell(product.sku, listing.ref, is_published=True)
        catalog.bulk_set([product.sku], listing.ref, is_published=True)
    item.refresh_from_db()
    assert item.is_published is True

def test_decimal_quantity_is_truncated():
    from shopman.orderman.models import OrderItem
    from shopman.backstage.projections.order_queue import build_operator_order
    o = order()
    OrderItem.objects.create(order=o, line_id="1", sku="P", name="Pesado",
                            qty="0.500", unit_price_q=3000, line_total_q=1500)
    assert build_operator_order(o).items[0].qty == 0

def test_queue_query_growth_is_confirmed():
    from django.test.utils import CaptureQueriesContext
    from django.db import connection
    from shopman.backstage.projections.order_queue import build_order_queue
    observations = []
    for n in (1, 10, 100):
        Order.objects.all().delete()  # somente banco efêmero de teste
        for i in range(n):
            order(ref=f"A-{n}-{i}", status="ready")
        with CaptureQueriesContext(connection) as queries:
            build_order_queue()
        observations.append((n, len(queries)))
    assert observations == [(1, 4), (10, 13), (100, 103)]
    assert sum("stockman_hold" in q["sql"].lower() for q in queries) == 100

def test_resend_claims_sent_while_directive_is_queued(client):
    from shopman.orderman.models import Directive
    from shopman.shop.services import notification
    client.force_login(User.objects.create_superuser("audit-link", password="audit"))
    o = order(ref="AUDIT-LINK", data={"fulfillment_type": "pickup", "payment": {
        "method": "link", "checkout_url": "https://example.invalid/payment"}})
    response = client.post(f"/api/v1/backstage/orders/{o.ref}/resend-payment-link/",
                           {}, content_type="application/json")
    assert response.status_code == 200
    assert response.json()["detail"] == "Link reenviado ao cliente."
    assert response.json()["payment_link_notice"] == "Enviando o link ao cliente…"
    assert notification.latest_delivery(o, notification.PAYMENT_LINK_TEMPLATE).status == Directive.Status.QUEUED


def test_two_zone_board_queries_include_per_order_waitlist_read():
    from django.test.utils import CaptureQueriesContext
    from django.db import connection
    from shopman.backstage.projections.order_queue import build_two_zone_queue
    counts=[]
    for n in (1,10,100):
        Order.objects.all().delete()
        for i in range(n):
            order(ref=f"Z-{n}-{i}",status="ready")
        with CaptureQueriesContext(connection) as queries:
            build_two_zone_queue()
        holds=sum("stockman_hold" in q["sql"].lower() for q in queries)
        counts.append((n,len(queries),holds))
        assert holds == n
    print("two-zone query evidence",counts)


def test_done_skipped_notice_is_labeled_sent():
    from shopman.orderman.models import Directive
    from shopman.shop.services import notification
    from shopman.backstage.projections.order_queue import payment_link_notice
    o = order(ref="AUDIT-SKIP")
    Directive.objects.create(topic=notification.TOPIC, status="done", payload={
        "order_ref": o.ref, "template": notification.PAYMENT_LINK_TEMPLATE,
        "notification_delivery": {"status": "skipped", "reason": "customer_opt_out"},
    })
    assert payment_link_notice(o).startswith("Link enviado")
```

Para evitar importar packages do checkout original por editable install, salvar o runner abaixo em `/tmp/run_orders_plan_tests_current.py` e executar da raiz do worktree auditado:

```python
from pathlib import Path
import os, sys
root = Path.cwd()
sys.path[:0] = [str(root), *[str(p) for p in sorted((root / "packages").iterdir()) if p.is_dir()]]
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_test"
import pytest
raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", "-c", "pyproject.toml", *sys.argv[1:]]))
```

Comando: `DATABASE_URL='' REDIS_URL='' PYTHONDONTWRITEBYTECODE=1 <venv>/bin/python /tmp/run_orders_plan_tests_current.py /tmp/test_orders_plan_current.py`. Para as suites, substituir o último argumento pelos paths explícitos de cada lista acima. A preparação não autoriza executar esses DELETEs fora da fixture pytest. Não transportar `.env` real; verificar settings e adapters herméticos antes da execução.

Esta auditoria cobre as cadeias descritas por leitura de entradas, funções, diffs da base atual, contratos e testes dirigidos. Não equivale a leitura integral de todo o monorepo nem a homologação externa. As **referências de plano**, por sua vez, foram lidas integralmente. Nenhum achado depende apenas do diagnóstico de outro plano.
