# Storefront — excelência operacional centrada no cliente

Data: 10/09/2026 · Estado: plano técnico auditado; piloto e rollout não autorizados por este documento.

**O operador é o próprio cliente. A loja deve fazer o trabalho de lembrar, reconciliar e explicar; o cliente faz as escolhas.** A régua é comprar com menos esforço, menos erro e compreensão exata do que aconteceu e de como continuar. Conversão, quantidade de telas novas e cobertura de testes isoladamente não demonstram omotenashi.

Esta entrega contém somente o plano e seu prompt de execução. Não implementa produto, não altera configuração de operação, não envia mensagens e não acessa produção. As metas abaixo são propostas verificáveis, não ganhos já observados em clientes.

## 1. Base, referências e método

### 1.1 Proveniência e isolamento

Base auditada: `3b8042a94f3dababafafdda9b12b57afb51250b7`, `origin/main` disponível localmente, sem garantia de atualização remota. Branch: `codex/storefront-operational-excellence-plan-20260910`. Worktree: `/private/tmp/shopman-storefront-plan-20260910`.

O original estava em `codex/shopman-backstage-marketing-hardening`, inicialmente `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`, com arquivos de terceiros. Como `.git` era protegido, criou-se clone local independente, sem hardlinks, em `/private/tmp/shopman-storefront-plan-repo-20260910`, e worktree nele. Original preservado; nenhum acesso a produção.

### 1.2 Referências lidas integralmente

Os quatro documentos foram lidos integralmente. Servem como referência de rigor, não como prova sobre o Storefront. Identificação suficiente para localizar e conferir a edição utilizada:

| Referência | Local de leitura | SHA-256 |
|---|---|---|
| Produção, 1.005 linhas | `/Users/pablovalentini/Dev/Claude/django-shopman/docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` | `f435f49347391b7d1bdb0e9de29a3278d14d17897bb93022b2880679014ac68d` |
| Marketing, 1.743 linhas | `/Users/pablovalentini/Dev/Claude/django-shopman/docs/plans/MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` | `de59ffaea5228aea38588fc3471049989cc86c06787640674837104ef1b94da4` |
| Gestor de pedidos, 715 linhas | `/Users/pablovalentini/Dev/Claude/django-shopman-orders-plan/docs/plans/ORDERS-OPERATIONAL-EXCELLENCE-PLAN-2026-09-10.md` | `e58d12c86515645652a847834ba5ce6cf973c6712e551427d2f5057a86bee5ab` |
| PDV, 718 linhas | `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-pdv-plan-current-20260910/docs/plans/PDV-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-10.md` | `8963a1fcebb4666de92e2a31373abfffbcdea62adc28d7ca8518b5a2037aaab9` |

Princípios incorporados: evidência atual antes de diagnóstico; intenção recuperável; revisão e efeito local consistentes; desconhecido não significa fracasso; recuperação apenas dos efeitos faltantes; continuidade sem memória humana; budgets por jornada; piloto distinto de implementação; gates humanos com entradas concretas. Não se importam estação, PIN, fechamento de caixa, métricas industriais, novos ledgers ou regras comerciais desses planos para o cliente.

### 1.3 Método e limite da evidência

Inventário de rotas e consumidores; leitura dos caminhos frontend/BFF/API/Core e efeitos; suítes herméticas; falhas e interleavings determinísticos. Comentários antigos foram conferidos na implementação. A auditoria percorreu a cadeia acionada, sem certificar cada linha dos pacotes reutilizáveis. PostgreSQL concorrente, providers reais, configuração produtiva, acessibilidade assistiva e esforço humano ainda exigem validação. Reprodução em laboratório não demonstra frequência em produção.

## 2. Mapa da cadeia e fontes de verdade

Caminhos relativos à raiz auditada. `FE` abaixo significa `surfaces/storefront-nuxt/app/`; `SF` significa `shopman/storefront/`; `SHOP` significa `shopman/shop/`. Esses atalhos são apenas notação deste documento.

| Trecho | Código / autoridade |
|---|---|
| Catálogo/busca/produto | FE pages index/menu/busca/colecao/produto; SF api/surface, services/catalog/sku_state, presentation/catalog/product_detail/dietary. Offerman + disponibilidade SHOP/Stockman/Craftsman. |
| Oferta/recompra | FE oferta e useReorder; SF surface; SHOP services/offers/customer_orders. Preço/disponibilidade resolvidos no clique. |
| Sacola | FE useCartState/sacola; SF cart/services/cart_mutations; SHOP services/cart/availability/sessions. Session canônica; Stockman holds/movimentos. |
| Identidade | FE entrar/a/useShopSession/useBrowserHandoff/usePasskey; SF api/auth/identity; SHOP services/auth. Guestman, autenticação e força de identidade. |
| Checkout | FE finalizar/utils checkoutFlow/checkoutDraft/checkoutPayload; SF api/views, intents/checkout/gift, services/pickup_slots; SHOP services/checkout. Configuração/calendário/zona/preço do servidor. |
| Commit | SHOP services/sessions; packages/orderman/shopman/orderman/services/commit.py. Session bloqueada e Order selado; E03 na conferência anterior. |
| Pagamento/tracking | FE pedido/useOrderTrackingStream/useConnectivity; SF api/tracking/services/orders/presentation/order_tracking; SHOP services/payment/payment_deadline/customer_orders. Payman/gateway; GET pode reconciliar/alterar estado. |
| Execução física | SHOP lifecycle/services stock/kds/fulfillment/courier; Stockman services/holds. Holds, produção futura, gates de pagamento e despacho existentes. |
| Fiscal/pontos/notificação | SHOP services/fiscal/loyalty/notification, directives e handlers; adapters/Core. Recibos e fontes existentes; enfileirado não significa entregue. |
| Conta/privacidade | FE conta/privacy/terms; SF api/account/presentation/address_privacy; SHOP services/account. Guestman/consentimento, step-up e anonimização. |
| “Me avise” | SF models/handlers/services/stock_alerts; SHOP notifications/adapters. Subscription + fatos de estoque/fornada; E07/H04. |
| Transporte/contrato | surfaces/storefront-nuxt/server/utils djangoProxy/storefrontApiAllowlist e server/api/v1/[...path].ts; SF api/urls/serializers/actions/projections. BFF restrito, sem regras próprias. |

Nomes sem extensão indicam módulos `.py`, `.ts` ou páginas `.vue` nos diretórios acima. As suítes e achados detalham os pontos exercitados.

### 2.1 Soluções maduras: requisitos de regressão

Preservar: adição direta, fila local, feedback otimista e `summary_pending`; substitutos no contexto; preço/cupom/calendário revalidados; identidade/price tier, endereço salvo resolvido no servidor, presente, observações, troco e coleta na entrega; draft/defaults e foco no erro; `/pedido/{ref}` com pagamento integrado; reconciliação de webhook, clock do servidor e polling; autorização/máscaras/step-up; exclusão parcial explícita e anonimização das inscrições.

Manter fases duráveis `on_commit`, `on_accepted`, `on_paid`, `on_cancelled`, sweeper e deduplicação existentes. Não presumir cobertura de todas as fases. Reusar componentes, copy e fontes locais. Não adicionar OTP à compra inteira, segunda página de pagamento ou central de pendências.

## 3. Achados confirmados

`E` é comportamento demonstrado por execução ou caminho completo de código; `H` é hipótese ainda não comprovada; `D` é decisão humana. Prioridade mede consequência, não frequência observada. P0: integridade/privacidade antes de exposição; P1: continuidade essencial; P2: refinamento e fechamento de contratos. Reprodução detalhada dos diagnósticos executados no apêndice.

| ID / prioridade | Fato e prova atual | Dano para o cliente e limite da conclusão | Correção mínima / WP |
|---|---|---|---|
| E01 · P0 | `useReorder` envia `x-idempotency-key`; `djangoProxy` não repassa esse header; `remote_mutations.idempotency_key_from_request` lê `Idempotency-Key`. `OrderReorderView` usa fallback por pedido/modo, scope sem sacola. Diagnóstico: recompra, remoção de todos os itens, nova intenção com nova X-key devolve sacola antiga não vazia; GET real está vazio. | “Adicionado” sem adição, até para nova intenção legítima. O teste substitui autorização por pedido conhecido; não demonstra acesso indevido entre clientes. Checkout também manda chave no body: não imputar a ele a perda do header como causa. | Unificar transporte, identidade da intenção e escopo; replay não pode fingir snapshot atual. W01–W03. |
| E02 · P0 | `CheckoutView` verifica sacola e, após sucesso, retira `cart_session_key`. POST idêntico após 201 retorna 400 “Sua sacola está vazia.”; continua existindo um único Order. Chave de tentativa de `finalizar.vue` é recriada no setup e não vai ao rascunho. | Há idempotência no Core, mas o cliente não alcança recuperação pelo contrato de checkout quando perde a resposta. Não foi provada duplicação de Order nesse teste. | Recuperar resultado autorizado antes de exigir sacola aberta; persistir correlação mínima da tentativa. W02/W04. |
| E03 · P0 | `checkout.process_ops`: `_ensure_total_matches` ocorre antes de `sessions.commit_session`. Diagnóstico intercala PUT válido qty=2 depois dessa conferência: checkout retorna 201 e Order.total_q supera `expected_total_q` de qty=1. | O pedido pode incorporar mudança de outra aba sem reconfirmação. Prova determinística de interleaving via API, não stress PostgreSQL nem débito externo real. | Conferir revisão, fingerprint da intenção e total sob o mesmo bloqueio que sela a Session. W02/W03. |
| E04 · P1 | Oferta: `OfferItems.assembled = bool(added)`; página navega ao receber `ok=true`, antes de mostrar `skipped`; com `ok=false` define `problem`, ramo anterior ao aviso parcial. Recompra: composable ignora `skipped`/`skipped_items` e anuncia adição. | Caminhos completos de código confirmam omissão do resultado parcial. Não foi executado E2E visual da oferta nesta sessão. Cliente precisa comparar mentalmente sua intenção com a sacola. | Exibir adicionados/faltantes na própria sacola ou no passo já existente, com ação por item elegível. W05. |
| E05 · P0 | Chave global `shopman-checkout-draft`; salva estado com nome, telefone/endereço/recado; restaura por Object.assign sem scope de cliente/sacola. Logout chama `session.reset`, sem limpar esse rascunho. Parser aceita campo de tipo inválido e savedAt futuro; três testes diagnósticos passaram. | Contexto pessoal pode reaparecer em navegador compartilhado/troca de identidade. Prova de armazenamento/restauração sem isolamento; sessão ponta a ponta entre duas pessoas ainda deve ser automatizada. | Rascunho versionado, escopo autorizado opaco, expiração válida e limpeza nas fronteiras de identidade; sem perder retorno normal. W04. |
| E06 · P1 | Preferência de notificação usa toggle: duas chamadas ao serviço com mesmo canal habilitam e depois desabilitam. Não recebe estado desejado. | Replay de uma intenção inverte a escolha; perda de resposta ao desligar pode religar no retry. Demonstração no serviço, não envio real. | Escrever estado explícito, serializar intenção e retornar estado canônico; compatibilidade transitória. W06. |
| E07 · P0 | `stock_alerts._deliver` chama `SHOP/notifications.notify` diretamente. Após subscribe e revoke global WhatsApp, diagnóstico ainda chama o dispatcher uma vez e retorna sucesso simulado. Caminho de notificação de pedido já consulta revogações; este não passa por ele. | Política de consentimento fica inconsistente entre caminhos. Não se afirma entrega externa ou conclusão jurídica; precedência da inscrição específica e revogação deve ser deliberada em D03. | Aplicar política canônica de elegibilidade antes do envio, inclusive na recuperação; não criar cadastro próprio de consentimento. W06/W08. |
| E08 · P1 | `_apply_post_commit_side_effects` captura falha de `save_defaults`, só registra log. Injetar falha devolve 201 com apenas order_ref/status/next_url. UI também trata identificação/etiqueta do endereço em chamadas posteriores. | Pedido confirmado é correto; promessa de lembrar escolhas pode falhar sem resultado recuperável para a pessoa. Diagnóstico de defaults, não comprovação de perda de endereço em produção. | Separar confirmação do pedido e persistência de conveniência; dar recuperação apenas do efeito faltante. W04/W08. |

Não entram como defeito comprovado: falta geral de idempotência, ausência geral de retry, pagamento sempre quebrado, falta de rascunho, preços calculados pelo browser, fontes externas bloqueando build ou invisibilidade geral da exclusão parcial. O código atual contradiz essas generalizações.

## 4. Hipóteses e decisões que não podem virar regra por suposição

### 4.1 Hipóteses com experimento e destino

| ID | Evidência que motiva, sem extrapolar | Experimento que confirma ou refuta / destino |
|---|---|---|
| H01 | Fila de sacola é local; metadados em `cart.py` têm read/merge/save fora da mesma unidade de outras escritas. | Duas conexões PostgreSQL: quantidade × cupom × endereço × pontos; barreiras determinísticas e revisão. Não perder campos não tocados, não aplicar preço de snapshot antigo. W03; descartar correção adicional se já protegida pelo caminho real. |
| H02 | Helper remoto adquire recibo, executa efeito e grava resposta em etapas separadas; não compara fingerprint. | Matar processo após efeito antes de resposta, repetir e variar payload com mesma chave. Inventariar todos os consumidores antes de alterar helper compartilhado. W01/W02; usar IdempotencyKey existente, não segundo ledger. |
| H03 | Avaliação salva cópia de `order.data` obtida antes da execução; página agrupa POST + refresh no mesmo try. | Intercalar callback de pagamento/courier antes do save; perder refresh após POST confirmado. Verificar se apaga metadata ou anuncia falha indevida. W07; promover a E somente com prova. |
| H04 | Subscription não tem unicidade lógica; notificação faz seleção → envio → marca, com callbacks pós-commit e sem claim durável nesse serviço. | Dois workers, duplo signal, crash antes/depois do aceite remoto, subscribe concorrente. Contar recibos e efeitos reais no mock; não concluir “duas mensagens” apenas porque há duas consultas. W06/W08. |
| H05 | BFF reescreve Origin/Referer, fornece CSRF e não valida origem original nesse helper; não repassa Cache-Control/Retry-After nesse caminho. | Em ambiente isolado, testar método unsafe de origem estrangeira e same-site irmão, cookies reais/SameSite, CORS e borda; verificar cache de resposta pessoal. Ausência de checks é factual; explorabilidade e cache compartilhado são hipóteses. W01; prioridade P0 se reproduzido. |
| H06 | Campos de draft/loyalty têm parsing permissivo (`.strip`, `bool`); contrato manual TS e serializers podem divergir. | JSON malformado, string "false", enum inválido, campos extras, erro não JSON/429; exigir 4xx inteligível, ausência de escrita e preservação do formulário. W01/W03. |
| H07 | Leituras e callbacks recuperam partes da cadeia; fases e efeitos diferem em durabilidade, e pontos são assíncronos. | Worker indisponível, emissão/courier/pontos falhando, deploy após commit, duplo consumo de pontos em compras paralelas. Conferir locks/idempotência dos serviços canônicos antes de concluir dano. W08/W10; não mover saldo ao Storefront. |
| H08 | Há suporte a acessibilidade, teclado móvel e reconexão; warnings de DialogContent em testes não provam tarefa impossível. | VoiceOver/TalkBack, teclado, zoom 200%, viewport estreito, rede lenta, storage bloqueado, Maps indisponível. Verificar tarefa completa e foco; medir orçamento, não “score” isolado. W09/W10. |
| H09 | Catálogo e política pública dependem de cadastro/adapters; textos legais podem descrever decisões anteriores. | Dono valida catálogo/alergênicos, prazos, métodos, fornecedores, retenção e promessas atuais contra configuração autorizada. Sem acesso produtivo nesta sessão. D02/D03; não inventar benefício, urgência ou segurança alimentar. |

### 4.2 Decisões humanas

| ID / dono | Decisão e limite enquanto pendente |
|---|---|
| D01 · Produto/operação | Aprovar budgets §6 e copy de resultado incerto. Conversão não permite relaxar integridade/privacidade. |
| D02 · Dono/operação | Oferta parcial, soma/troca de sacola, janela e suporte. Proposta: preservar adição direta quando explicitamente rotulada; troca/SKU/pontos exigem escolha. Prazos devem ser operáveis. |
| D03 · Privacidade/marketing | Opt-out × inscrição específica, retenção e política pública. Proposta: revogação posterior silencia retries; novo opt-in precisa escolha inequívoca. Sem reinterpretar histórico ou liberar piloto de avisos antes do aceite. |
| D04 · Core/pagamento/estoque | Aprovar contrato compartilhado com diff/testes de consumidores. Sem bypass nem estado financeiro próprio. |
| D05 · Produto/pesquisa | Aprovar roteiro/amostra/acessibilidade, incluindo convidados/WhatsApp/aparelho compartilhado; fixtures sem dados reais. |
| D06 · Operação/release | Aprovar coorte/janela/limiares/plantão/rollback e reconciliação. Merge não autoriza piloto, produção ou disparos. |

Preparar propostas e provas antes de solicitar decisão; continuar trabalho independente. Não transferir decisões técnicas ao cliente.

## 5. Contratos de implementação

Extensões mínimas dos contratos atuais; nomes finais consolidados em W01, sem outro dialeto.

| Contrato | Garantias obrigatórias |
|---|---|
| C01 · Intenção e recibo | `Idempotency-Key` canônico; aceitar X-header/body legados na transição, rejeitar chaves divergentes sem efeito. Mesma intenção mantém chave após timeout/reload; nova escolha gera outra. Scope inclui principal/sessão autorizada, canal, recurso, operação e sacola alvo. Revalidar acesso no replay. Fingerprint normalizado cobre efeito/revisão, não labels ou telemetria. Mesma chave/payload recupera resultado; payload divergente retorna conflito. Reusar IdempotencyKey/Session/Order; recibo não é snapshot corrente nem credencial. Efeito local e recuperação atômicos; efeito externo exige recibo/consulta antes de retry. Não prometer exatamente-uma-vez sem garantia do provider. |
| C02 · Checkout | Conferir revisão e total sob o bloqueio que sela Session; alteração material com total igual também exige reconfirmação. Recuperar tentativa autorizada antes de exigir sacola aberta. Retornar o mesmo Order e next_url real; sem recriar sacola/pedido para resolver dúvida. Sem recibo conclusivo: andamento/indeterminado e próxima consulta na superfície existente. Persistir correlação mínima sem segredo; storage indisponível usa recuperação autorizada no servidor. Não confiar em preço, saldo, endereço salvo textual ou disponibilidade do draft. |
| C03 · Sacola e contexto | Session é única sacola. Mutações absolutas retornam revisão/projeção; merge não apaga campos concorrentes. Preservar fila; aviso de conflito junto ao item. Broadcast entre abas não substitui consistência. Draft versionado, campos validados, contexto opaco autorizado e `0 ≤ now-savedAt < TTL`. Limpar PII em logout/exclusão/troca de pessoa; preservar renovação legítima da mesma sessão. Legado sem proveniência não é atribuído a novo cliente. Retomar passo, filtros, endereço e recado válidos; nunca guardar OTP/cartão/tokens ou enviar checkout automaticamente ao reconectar. |
| C04 · Parcial e próxima ação | Distinguir confirmado, parcial, indeterminado e recusa sem efeito, sem criar estado paralelo de Order. Oferta/recompra nomeiam adicionados/faltantes/motivos e ações elegíveis; erro de infraestrutura não é indisponibilidade comercial. Zero itens não gera sucesso. Mostrar resultado no local da intenção; não substituir SKU/sacola sem escolha. Commit confirmado permanece mesmo se defaults/etiqueta falham; recuperar só conveniência faltante, sem bloquear pedido. Reusar Action/error_code/contexto/copy; Vue não calcula permissão. |
| C05 · Consentimento e identidade | Escrever estado desejado; replay não religa canal. Guestman e política D03 são autoridade; inscrição não autoriza comunicação universal. Reconsultar elegibilidade antes de envio/replay; falha de leitura silencia. Evoluir Subscription/Directive/recibos existentes para unicidade/claim/recuperação, sem outbox própria. Aviso depende de fato vendável atual; aceite remoto não prova entrega. Preservar máscaras/step-up e não revelar pedido ou PII alheios na recuperação. |
| C06 · Pagamento e efeitos | Payman/gateway/Orderman/Stockman/fulfillment continuam autoridades. Desconhecido não autoriza nova cobrança, cancelamento por não pagamento ou nova entrega. Tracking usa projeção/clock canônicos, SSE e fallback autorizado. POST confirmado não vira falha porque refresh falhou. Reparar apenas efeitos faltantes, conferindo recibos próprios de pagamento, hold, KDS, courier, fiscal, pontos, defaults e aviso. Incidente técnico vai ao gestor/OperatorAlert existente; cliente recebe consequência e próxima ação útil. |

## 6. Budgets de esforço e jornadas antes/depois

### 6.1 Medição honesta

A = ativações deliberadas de controles; T = campos digitados/redigitados; M = fatos que é preciso memorizar/transcrever para continuar; N = mudanças manuais de tela; R = intervenções manuais de recuperação. Autofill não conta como digitação. OTP obrigatório conta como campo e ação, discriminado do fluxo de aparelho confiável. Rolagem, tempo ativo, erro e pedido de ajuda são registrados separadamente; não escondê-los em “um clique”. Escolher item diferente é trabalho legítimo, refazer o mesmo dado é retrabalho.

O “antes” abaixo é walkthrough estrutural do código, ou reprodução técnica identificada. Não é média/p95 de clientes. `Sem limite garantido` significa que o caminho não fornece recuperação determinística, não que todos os clientes enfrentam esforço infinito. Teto do “depois” é critério de aceite proposto; quando o atual já é melhor, prevalece o atual. Fluxos opcionais de presente/cupom/troco são medidos separadamente, não absorvidos no happy path.

| Jornada e ponto inicial | Antes auditado | Depois contratado / budget máximo |
|---|---|---|
| J01 · Produto disponível, quantidade 1 | Adição direta com fila e feedback otimista já existente. | A≤1, T=0, M=0, N=0, R=0; nenhuma confirmação adicional. |
| J02 · Sacola pronta, cliente conhecido, retirada, defaults ainda válidos | Checkout já tem três seções: receber/quando/pagar; vários dados vêm preenchidos. Contagem humana ainda não medida. | Da sacola ao pedido: A≤3, T=0, M=0; revisar escolhas visíveis e confirmar, sem pedágios por seção completa. Pagamento externo medido à parte. |
| J03 · Sacola pronta, conhecido, entrega em endereço salvo | Quatro seções e endereço salvo resolvido pelo servidor; rascunho existente. | A≤4, T=0, M=0, N≤2 até acompanhamento. Troca de endereço explícita acrescenta só a escolha necessária. |
| J04 · Primeiro pedido, endereço novo | Identificação/endereço são necessários; não se mede baseline fictícia. | Cada campo necessário digitado uma vez; T_repetido=0, M=0. Escolher sugestão/endereço manual no mesmo passo. Nenhuma conta obrigatória nova para montar sacola. |
| J05 · Reabrir checkout da mesma pessoa após interrupção | Draft já retoma, mas não identifica contexto e perde chave de tentativa; E02/E05. | A≤1 para retomar intenção segura, T_repetido=0, M=0, R≤1. Mudança de preço/data exige só revisão do delta. |
| J06 · Logout/troca de pessoa em aparelho compartilhado | Draft global pode ressurgir; E05. | PII anterior=0. Nenhuma reconfirmação revela dado alheio. Cliente novo faz identificação necessária; não usar budget zero para suprimir proteção. |
| J07 · Confirmar pedido; resposta 201 perdida | Repetir dá sacola vazia; reconstrução/suporte sem limite garantido; E02. | Mesmo Order recuperado automaticamente; A_extra=0 na mesma página ou ≤1 ao reabrir, T_repetido=0, M=0, R≤1. Nunca “faça outro pedido”. |
| J08 · Duas abas, quantidade muda entre total e commit | Interleaving E03 confirma valor maior. | Zero commits fora da revisão confirmada; delta visível; A_extra≤1 para reconfirmar, T_repetido=0, M=0. Troca de SKU de mesmo valor também detectada. |
| J09 · Recomprar de novo depois de esvaziar sacola | Nova chave X ignorada; resposta anterior “adicionado”, sacola real vazia; E01. | A≤1 para somar itens de nova intenção; replay da mesma intenção adiciona zero vezes extras. T=0, M=0. |
| J10 · Oferta/recompra com um item faltante | Parcial pode desaparecer na navegação; cliente compara lista mentalmente; E04. | Lista de faltantes automática, M=0; seguir com presentes A_extra≤1 ou escolher substituto A_extra≤2 por item. Sem substituição automática. |
| J11 · PIX/cartão com callback perdido ou retorno antes do webhook | Recuperação já existe; não assumir que falha. | Preservar zero redigitação/segunda cobrança. Estado + próximo passo no pedido; A_extra=0 para consultar automaticamente; R≤1 só se reconexão manual necessária. |
| J12 · Pedido confirmado, defaults/etiqueta falham | 201 permanece, conveniência se perde em log; E08. | Confirmado permanece visível; salvar escolha faltante automaticamente quando seguro, ou A≤1; T_repetido=0; não reexecutar checkout. |
| J13 · Desligar WhatsApp, resposta perdida | Segundo toggle pode reverter; E06. | A≤1 original, A_extra=0 em retry; estado final desligado. Aviso antigo não passa pela revogação aprovada em D03. |
| J14 · Sem estoque/fornada futura, “me avise” | Gatilhos e copy específicos já existem; envio/recuperação H04. | Produto e motivo no contexto; A≤1 se canal já autorizado; coleta mínima se convidado. M=0. Não prometer reserva nem prazo inventado. |
| J15 · Cancelar/confirmar recebimento; POST funciona e refresh falha | Página trata POST e refresh no mesmo bloco; efeito completo a verificar H03. | Resultado da ação preservado; atualização pendente explícita; A_extra=0; nenhuma cobrança/estorno/entrega duplicada. |
| J16 · Rede volta, storage bloqueado, teclado/leitor de tela | Reconexão e componentes existem; desempenho assistivo não medido. | Sem envio financeiro automático; recuperar leitura e intenção segura, R≤1, T_repetido=0 quando sessão autoriza. Foco no próximo controle, nunca atrás de overlay. |

### 6.2 Budgets de resposta e prova de ganho

Metas iniciais em ambiente controlado, a confirmar em D01/D06: feedback local p95≤100 ms; loading/estado pendente acessível até 300 ms; resposta de mutação local p95≤1,5 s; resultado de reconciliação consultável em até 5 s **após** backend/recibo estarem disponíveis; fallback de tracking até 30 s, respeitando limites atuais. Dependência remota indisponível não recebe prazo falso: até 2 s após detecção, explicar “a confirmação ainda está em consulta” e manter a mesma tentativa.

Comparação emparelhada entre base congelada e candidata, mesmas fixtures, dispositivo/rede e roteiro, ordem contrabalançada para reduzir aprendizado. Guardar vídeos consentidos ou anotações mínimas, contagem A/T/M/N/R e tempo ativo. Nas jornadas já boas exigir não regressão; nas J07/J09/J10/J12 exigir queda de recuperação manual e transcrição a zero nos cenários controlados. No piloto, meta proposta: ≥90% completam sem ajuda; ≥90% respondem corretamente “foi pedido/pago?”, “o que faltou?” e “como continuar?”. Qualquer erro de compreensão financeira grave impede expansão mesmo com conversão maior.

Não alegar ganho percentual sem denominador, amostra e intervalo/limite da observação. Incluir abandonos e falhas, não só pedidos bem-sucedidos. Falta de evento não é sucesso. Se um budget não for viável, trazer o caminho medido e decisão explícita; não reclassificar retrabalho como “escolha do cliente”.

## 7. Work packages sem ciclos

Cada pacote entrega diff mínimo, reprodução/regressão, contratos afetados, esforço medido, observabilidade e migração/rollback aplicáveis (§9). Donos designados em G0; estimar após W00. Dependências são de artefatos, não autorização para abrir agentes.

| WP / prioridade / dono | Depende de | Entrega e aceite | Particularidade de migração/rollback |
|---|---|---|---|
| W00 · P0 · técnico | — | SHA, diferenças da base, consumidores, repros E01–E08, baseline J01–J16 e testes para H. | Só evidência/fixtures. |
| W01 · P0 · API/frontend | W00 | C01/C04 canônicos; header atravessa BFF; conflitos sem efeito; H05/H06 testadas; allowlist/traversal/cookies preservados. | Backend aceita legado primeiro; segurança não regride. |
| W02 · P0 · Core/composição | W01 | E02/E03 corrigidas: replay recupera um Order; revisão/total atômicos, inclusive mudança de mesmo total; D04. | Recibo aditivo, sem fingerprint legado inventado; preservar tentativas abertas. |
| W03 · P0 · composição/frontend | W01 | E01/H01 resolvidas; nova recompra funciona; qty/cupom/endereço/pontos não se apagam; J01 preservada. | Revisão aditiva; nunca segundo carrinho ou rollback para escrita insegura. |
| W04 · P0/P1 · frontend/conta | W02,W03 | E05/C03 e J05–J07 passam; mesma tentativa sobrevive retorno; logout limpa PII; E08 não bloqueia pedido. | Draft v2; descartar legado ambíguo sem perder sacola/pedido. |
| W05 · P1 · frontend/catálogo | W03 | E04 resolvida em componente+E2E; parcial/vazio/erro separados; J09/J10, um toque quando tudo entra. | Resultado aditivo; desativar atalho sem reaplicar oferta. |
| W06 · P0/P1 · conta/marketing | W01 | E06/E07 e H04 resolvidas sob D03; set explícito, unicidade/claim/revogação/replay/anonimização testados. | Dry-run antes de constraint; não reativar opt-out/reenvio histórico. |
| W07 · P1 · frontend/pedidos | W02 | C06/H03: refresh não apaga sucesso; ações canônicas; J11/J15, SSE/poll/foco preservados. | Campos opcionais; recuo mantém reconciliação e acesso. |
| W08 · P1 · composição/integrações | W02,W06 | E08/H02/H04/H07: recuperar só efeito faltante com mecanismos existentes; crash/retry sem duplicações. | Não presumir legado entregue; pausar novos jobs, reconciliar em curso. |
| W09 · P1/P2 · produto/frontend | W04,W05,W07 | Budgets J01–J16; H08, foco/teclado/leitor/zoom/WhatsApp/Maps manual. Tela extra só com redução medida. | Componentes atuais; copy pública depende D02/D03. |
| W10 · P0 · qualidade/domínios | W08,W09 | Matriz §8.2 em PostgreSQL/browser, consumidores, build, compatibilidade e rollback passam; pass/fail/skip explícitos. | Ensaio isolado; staging só autorizado. |
| W11 · gate · produto/operação | W10,G2 | Piloto compara esforço/compreensão, com coorte e suporte aprovados. | Flags por coorte; preservar tentativas abertas. |
| W12 · gate · release/operação | W11,G3 | Expansão só com §10/§11; incidentes reconciliados antes de conclusão operacional. | Redução ensaiada, recibos/compatibilidade mantidos. |

Ordem válida: W00,W01,W02,W03,W06,W04,W05,W07,W08,W09,W10,W11,W12. G2 lê W10; G3 lê W11. Nenhum gate exige resultado da etapa que autoriza.

## 8. Testes e observabilidade

### 8.1 Evidência executada nesta sessão

Ambiente hermético: `config.settings_test`, DATABASE_URL e REDIS_URL vazios, imports do worktree antes de pacotes editáveis do ambiente original. Sem `.env` de produção; SQLite de teste e adapters mock/fail-closed. Callbacks externos não foram exercitados contra serviços reais.

| Execução | Resultado |
|---|---|
| `pytest shopman/storefront/tests` | **1.469 passed, 3 skipped**, 79,75 s. Skips de concorrência dependentes de banco não valem como prova PostgreSQL. |
| `pytest` checkout side effects/customer link, fiscal handlers, remote mutations | **29 passed**, 4,79 s. |
| `pytest` lifecycle phase durability, reconcile payments, payment timeout gateway check, payment gate before goods leave, stock hold idempotency/integrity, notification consent, courier service, fiscal contract, commit stock gate | **113 passed**, 12,77 s. |
| `npm test -- --reporter=dot` em `surfaces/storefront-nuxt`, Node 22 | **57 arquivos / 536 testes passed**, 12,12 s. Warnings de descrição de DialogContent observados; não equivalem a auditoria assistiva. |
| `npm run typecheck` | Passou. |
| `npm run lint` | 0 erros, 5 warnings preexistentes de ordem de atributos em `WhatsappVerifyPanel.vue`. |
| Diagnósticos backend do apêndice | **7 passed**, 5,99 s. “Passed” significa que reproduziram os comportamentos atuais indesejados, não que o produto esteja corrigido. |
| Diagnósticos parser do apêndice | **3 passed**, 244 ms; escopo ausente, timestamp futuro e tipo de campo inválido. |

Os primeiros ensaios do diagnóstico de checkout foram recusados corretamente por ausência de slot/data; fixture corrigida para usar data atual e último slot válido. Não foram contabilizados como defeitos do produto. Um comando npm foi iniciado da raiz errada e refeito no frontend. Dependências foram instaladas apenas na worktree com `npm ci`; nenhum upgrade foi feito.

Não executados: browser E2E completo, build de produção, stress PostgreSQL, gateway real, teste humano, deploy, piloto. Não apresentar esses itens como aprovados por inferência das suítes acima.

### 8.2 Matriz mínima de aceite técnico futuro

| Família | Casos obrigatórios | Oráculo verificável |
|---|---|---|
| Intenção/recibo | Mesmo payload/chave; diferente payload/mesma chave; nova intenção mesma operação; dois browsers autorizados; outro principal | Efeito local uma vez por intenção; nova intenção legítima funciona; segredo/replay não concede acesso; snapshot corrente não é confundido com recibo histórico. |
| Commit | Falha antes do commit; depois do commit antes da resposta; resposta perdida com e sem cookie atualizado; reload; request concorrente; revisão muda com total igual/diferente | Exatamente um Order por intenção, valor/itens só da revisão confirmada, recuperação do mesmo ref; nenhum pedido novo para resolver dúvida. |
| Sacola/estoque | 5 compradores disputam 3 unidades; duas abas; hold vence; bundle parcial; produção menor que planejada; produto pausado; substituto some | Três unidades no máximo comprometidas, progresso dos compradores elegíveis, restantes recebem alternativa correta. Não aceitar teste em que todos falham e `count≤3` passa. Movimentos/holds reconcilam. |
| Pagamento | Webhook dup/atrasado/perdido; timeout × confirmação; autorizado sem captura; retorno Stripe; PIX expirado; dinheiro na entrega | Capturas/movimentos exatos e estados corretos; indeterminado não vira não pago; pagamento externo não é repetido. Não aceitar apenas `capture_count≥1`. |
| Parcial | Oferta 0/1/todos; recompra com itens prévios; falha no segundo item; retry depois de parte aplicada | Lista por item verdadeira; anteriores preservados; só decisão explícita troca sacola; erro técnico não se anuncia como indisponibilidade comercial. |
| Conveniência | Salvar defaults/endereço/etiqueta falha após pedido; retry perde resposta | Pedido confirmado permanece; efeito faltante recupera sem novo Order/cadastro/endereço duplicado e sem pedir os mesmos dados. |
| Identidade | Convidado, link number, device, step-up; expiração; logout/login outra pessoa; revogar aparelho; excluir parcialmente | Rotas/ações certas, PII não cruza contexto, destino seguro preservado, exclusão parcial honesta; sem ganho de privilégio via replay. |
| Avisos/consentimento | Toggle legado × novo set; revogação após enfileirar; dupla subscription/signal/worker; adapter aceita e conexão cai; anonimização | Estado desejado estável; zero envios proibidos; prova do aceite separada de entrega; retry não duplica sem reconciliação. |
| Efeitos downstream | Worker para depois de cada etapa de on_commit/on_paid/cancelled/completed; fiscal/courier/pontos falham | Só efeito faltante retomado; recibos e estados convergem; cliente sabe consequência; gestor recebe alerta existente acionável. |
| Browser/contrato | BFF real + Django; HTML 502; 429; cookie host-only; cache pessoal; origem indevida; dois tabs; storage negado; teclado/zoom/leitor | Sem vazamento, permissão ou replay indevido; sem dados perdidos por refresh; foco e próximo passo acessíveis; J01–J16 medidos. |

Testes de falha usam barreiras/transações e fault injection identificada, evitando sleeps como prova de corrida. PostgreSQL precisa conexões independentes; SQLite não valida bloqueios. Testar todos os consumidores afetados do helper/Core (inclusive outros canais) e limites de importação: superfície → composição → Core. Manter teste de contrato frontend/BFF/API, não apenas grep por strings ou assert de markup.

### 8.3 Observabilidade

Usar logs/métricas/eventos/Directive/OperatorAlert existentes, sem ledger/painel próprio. Correlação browser→BFF→API→worker; excluir cookies, OTP, telefone/endereço, presente, pagamento e chaves brutas. Dimensões limitadas: jornada/canal/versão/resultado/motivo/coorte; IDs individuais só em contexto protegido, fora de métricas de alta cardinalidade.

| Sinal | Medição / responsável |
|---|---|
| Recuperação | Tentativas committed apresentadas/recuperadas ÷ committed, separando abandono/telemetria ausente. Operação trata pendências além da janela D06. |
| Consistência | Conflitos de revisão ÷ tentativas; qualquer commit não confirmado é P0. Core investiga, sem suprimir validação. |
| Parcial | Parciais apresentados ÷ produzidos; produto verifica compreensão por roteiro, não só render. |
| Efeitos | Idade/tentativas/erro/recibo existentes; integração reconcilia e informa consequência útil. |
| Consentimento | Elegíveis/bloqueados por motivo; despacho proibido é P0, responsável marketing/privacidade. |
| Esforço | A/T_repetido/M/N/R/tempo/ajuda/abandono por jornada; produto compara à base e budgets. |
| Integridade | Conciliar Order/Payman/holds/movimentos/fiscal/fulfillment por fixtures e amostra autorizada. HTTP 200 não é prova do efeito. |

P0 interrompe exposição nova. Limiares de idade/volume e plantão precisam D06; prazos comerciais continuam na configuração canônica. Falha transitória recuperada não deve inundar cliente/plantão.

## 9. Migração, compatibilidade e rollback

1. **Expandir:** backend compatível antes do novo frontend, campos aditivos, aliases temporários e flags existentes por canal/coorte, com dono e retirada prevista. Testar versões mistas e jobs em voo. Escrita insegura antiga não fica liberada por compatibilidade: exigir atualização/reconfirmação clara.
2. **Recibos/revisões:** reaproveitar IdempotencyKey e revisão da Session; revisar consumidores/índices/retenção antes de schema. Não inventar fingerprint legado, liberar retry pela idade ou marcar entrega sem prova. Recuperar por Session/Order autorizado ou manter indeterminado.
3. **Draft/inscrições:** draft v2 estrito, sem atribuir PII legada ambígua; sacola/pedido do servidor permanecem. Dry-run de inscrições equivalentes, revogadas e já aceitas; D03 antes de saneamento/constraint. Sem opt-in ou envio retroativo automático.
4. **Ensaiar:** interrupção/repetição da migração, volume representativo sintético, locks, versões mistas e rollback. Dimensionamento produtivo requer acesso autorizado. Não restaurar snapshot sobre transações novas.
5. **Recuar:** bloquear entrada nova da coorte, preservar consulta/recuperação de tentativas abertas, pausar jobs novos afetados e reconciliar em curso. Reverter UI compatível mantendo correções de integridade/privacidade. Não apagar recibos, ressuscitar draft, reativar consentimento ou estornar/reemitir como rollback técnico.
6. **Contrair:** remover legado apenas após janela aprovada, tentativas resolvidas e evidência de consumidores, declarando lacunas de telemetria. Schema destrutivo exige release e autorização próprios.

Runbook: detectar → localizar intenção/Order autorizado → consultar fonte/recibo → conter repetição → recuperar efeito faltante → conferir projeção → fechar alerta com prova. Se provider não permite resolver efeito desconhecido, responsável humano reconcilia antes de repetir; cliente não transporta informações entre sistemas.

## 10. Gates, piloto e rollout

| Gate | Momento / entradas | Responsáveis e autorização |
|---|---|---|
| G0 · Preparação | W00: base atual, reproduções, mapa de consumidores, protocolo de privacidade e proposta de budgets | Responsável técnico/produto designam donos; D01–D04 podem ser resolvidas por pacote. Desenvolvimento independente continua. |
| G1 · Revisão técnica | W01–W09: diffs pequenos, testes por contrato, matriz de migração e decisões aplicáveis | Core/composição/frontend aprovam implementação. Não autoriza exposição, mensagens ou produção. |
| G2 · Entrada no piloto | W10 concluído; zero E P0 aberto; D02/D03/D05/D06 resolvidas; runbook/rollback testados; coorte e suporte definidos | Produto + operação + privacidade aprovam piloto delimitado. O piloto não depende de já demonstrar ganho humano nele; depende de segurança técnica e protocolo pronto. |
| G3 · Expansão | W11: resultados antes/depois, compreensão, incidentes, aderência aos budgets e reconciliação | Operação/produto autorizam cada expansão. Não usar teste técnico como substituto do aceite humano. |
| G4 · Conclusão operacional | W12: janela estabilizada, sem tentativas/efeitos sem dono, documentação e flags tratadas | Dono de operação declara rollout concluído; ganho e limites publicados no relatório. |

**Implementação técnica:** W00–W10, testes/ambientes isolados; pode terminar com piloto pendente sem declarar excelência operacional entregue. Não executar mensagens/reembolsos/cobranças reais para “provar” teste.

**Piloto proposto, sujeito a G2:** começar por tarefas simuladas com 8–12 clientes, cobrindo novos/recorrentes, dispositivo confiável/convidado, WhatsApp, acessibilidade e aparelho compartilhado. É amostra qualitativa, não inferência estatística de toda a clientela. Depois, somente se autorizado, coorte restrita em operação real com atendimento disponível e casos financeiros acompanhados; não forçar falhas de cobrança em compradores reais. Exigir pelo menos uma passagem observada de cada jornada relevante, incluindo falhas em ambiente de teste. Sem evidência suficiente, ampliar observação antes de ampliar público.

**Rollout proposto, sujeito a G3:** coorte elegível pequena → 25% → 50% → 100%, com mínimo de 48 h e 30 jornadas elegíveis por etapa como piso inicial a aprovar em D06. Pouco volume prolonga etapa; calendário não substitui evidência. Segmentação não separa uma mesma tentativa entre contratos incompatíveis. Não misturar mudança de preço/promoção para atribuir ganho ao UX.

Parada imediata: cobrança/pedido/entrega/aviso duplicado não reconciliado, valor não confirmado, PII de outra pessoa, opt-out violado, ação financeira apresentada como falha após sucesso de modo que induza repetição. Reduzir exposição e acionar runbook. Parada por degradação: orçamento essencial excedido em tarefas repetidas, aumento de ajuda/abandono ou latência fora do budget; investigar antes de expandir, sem relaxar integridade.

## 11. Definition of Done

**Técnica (G2):** E01–E08 corrigidos ou refutados na base nova com prova; nenhum P0 aberto; H com resultado/dono. C01–C06, matriz §8.2, outros consumidores afetados, browser/BFF/API, PostgreSQL, typecheck/lint/build e acessibilidade passam; skips relevantes resolvidos. J01–J16 medidos, soluções §2.1 preservadas. Migração/rollback mistos ensaiados; telemetria/runbook com dono; sem novas fontes de verdade.

**Operacional (G4):** piloto/expansão autorizados; comparação antes/depois inclui abandonos, compreensão e limites da amostra. Recuperação não exige memória/transcrição; cliente entende confirmação, parcial, indeterminado e próximo passo. Incidentes contidos/reconciliados, efeitos pendentes com dono/prazo. Documentação e retirada de flags encaminhadas. Implementação técnica concluída não equivale a rollout nem a ganho humano demonstrado.

## Apêndice A — reprodução dos diagnósticos

Diagnósticos passaram ao reproduzir defeitos; na implementação, inverter o oráculo para exigir comportamento correto. Usar fixtures sintéticas e `config.settings_test`, DATABASE_URL/REDIS_URL vazios; imports da worktree antes dos pacotes editáveis. Não importar `.env` produtivo.

Preparação backend: pytest com `django_db`, `_seed_surface` de `shopman.storefront.tests.api.test_storefront_surface`, `with_baseline` de `shopman.storefront.tests._checkout_baseline`. Para checkout válido: adicionar `PAO-FRANCES`, qty=1; nome Ana, telefone sintético `+5543999990001`, retirada, dinheiro, data local atual e `get_slots()[-1]['ref']` de `storefront.services.pickup_slots`. Usar body com `idempotency_key` fixo e `expected_total_q` resolvido por with_baseline.

| Diagnóstico executado | Procedimento e oráculo da base |
|---|---|
| Header | RequestFactory POST com `HTTP_X_IDEMPOTENCY_KEY='intention-A'`; helper `idempotency_key_from_request(..., fallback='fallback')` retorna fallback. |
| Checkout replay | POST `/api/v1/checkout/` → 201; repetir body idêntico → 400 “Sua sacola está vazia.”. Contar exatamente um Order com ref retornado. |
| Recompra nova | Criar Order completed com uma OrderItem PAO-FRANCES; mock apenas de `storefront.services.orders.get_accessible_order` retorna esse pedido. POST reorder mode=append X-key=first; PUT qty=0; POST mode=append X-key=second. Resposta diz cart.is_empty=false, GET `/api/v1/storefront/cart/` diz true. Esse mock não prova autorização. |
| Defaults parcial | Injetar RuntimeError em `shop.services.checkout.save_defaults`; checkout ainda retorna 201 e só order_ref/status/next_url, sem informar efeito faltante. |
| Toggle | Criar cliente Guestman; chamar `shop.services.account.toggle_notification_consent(ref,'whatsapp')` duas vezes. Primeira inclui canal, segunda o remove. |
| Opt-out | `stock_alerts.subscribe(..., alert_type='stock_back')`; revogar consentimento WhatsApp via ConsentService; mock `shop.notifications.notify` com NotificationResult(success=True), `_image_url` vazio. `_deliver` retorna true e chama dispatcher uma vez. Não há entrega externa real. |
| Corrida de total | Wrapper de `_ensure_total_matches` chama implementação original e depois PUT válido qty=2 antes de retornar. POST checkout conclui 201; Order.total_q > expected_total_q. Interleaving determinístico, não prova de locks PostgreSQL. |
| Parser (3 testes) | `parseCheckoutDraft` restaura nome/telefone sem scope; aceita savedAt futuro; aceita state.name como objeto. Executar em Vitest unit. |

Comandos: `pytest shopman/storefront/tests` e arquivos nomeados em §8.1 usando settings herméticos; frontend em `surfaces/storefront-nuxt`, Node 22: `npm ci`, `npm test`, `npm run typecheck`, `npm run lint`. Os scripts completos e resultados da primeira auditoria estão preservados no commit local `e0867ac9`; os procedimentos acima bastam para reconstruir as reproduções sem depender desse histórico.
