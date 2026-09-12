# iFood: preparação e evidências de homologação

## Estado atual verificado

- Aplicativo salvo: **Nelson Boulangerie - Shopman**; slug **nelson-boulangerie-shopman**; ID `d852f581-9b04-44ed-83e8-fce81d2669f4`. Events habilitado com autorização explícita de Pablo. Não foram criados apps duplicados ou novas credenciais.
- Chrome conectado e autenticado. O assistente de homologação reconhece o aplicativo e exige **Order + Events**. Módulos opcionais aparecem como futuros ou orientados a suporte. Preparação selecionou loja de teste e Polling; **nenhuma tentativa oficial iniciada**.
- Domínio público confirmado: `https://menu.nelsonboulangerie.com.br`. O backend continua em `https://api.boulangerie.com.br`; domínio da vitrine não equivale à rota de eventos.
- Worktree de release: `django-shopman-ifood-release-20260912`, branch `codex/ifood-release-20260912`, criada de `origin/main` **160f0c5ad**. A worktree inicial estava antiga e não será usada para deploy.
- Correções implementadas, ainda não publicadas: isolamento de merchant, CAN antes de PLC, conclusão remota conservadora, solicitação de cancelamento pendente até CAN, pagamento por evidência e resumo operacional de pagamento/troco.
- Última rodada integrada local: **198 testes + 18 subtests passaram**, incluindo iFood e contratos/projeções operacionais. Frontend: **309 testes passaram**. Testes complementares e revisão ainda em execução.
- Pendências para homologação: publicar versão validada; confirmar isolamento de efeitos reais dos pedidos de teste; gerar pedidos oficiais e coletar evidências; verificar estabilidade do polling que apresentou 403 intermitente; alinhar webhook antigo ainda habilitado com URL sem DNS.
- **Não está comprovada prontidão de homologação.** Elegibilidade do aplicativo no portal não substitui os testes práticos. Nenhum pedido oficial foi gerado nesta sessão.

As seções abaixo preservam a investigação anterior e suas correções históricas. Quando houver divergência temporal, prevalece o estado verificado acima.


Consulta e verificação: 12/09/2026. Base auditada: `b589e22c5`. Branch `codex/ifood-homologation-20260912`, worktree isolada. Sessões Marketing e Conversacional avisadas; Conversacional confirmou ausência de sobreposição. Nenhum deploy, alteração de configuração remota, pedido ou chamado foi criado nesta verificação. Na continuação, foram feitas duas consultas de polling sem ACK no próprio container, depois de confirmar que o aplicativo só autoriza a loja de teste. Segredos não constam deste relatório.

## Decisão

**Ainda não está pronto para uma tentativa oficial de homologação.** Podemos preparar e executar os testes com a loja de teste após fechar os bloqueios abaixo. O domínio correto está ativo; isso não certifica o recebimento e o ciclo de pedidos.

## Evidências obtidas agora

| Verificação | Resultado | Limite da evidência |
|---|---|---|
| `https://menu.nelsonboulangerie.com.br/` | HTTPS válido, HTTP 200 | Storefront; não é a origem Django |
| `/api/webhooks/ifood/events/` no domínio menu | HEAD 404 | Não cadastrar essa URL como webhook |
| `https://api.boulangerie.com.br/api/webhooks/ifood/events/` | GET 405; POST `{}` sem assinatura 401 `invalid_signature` | Prova rota e rejeição; não prova entrega assinada/KEEPALIVE |
| OAuth com credenciais locais existentes | HTTP 200; expiresIn 21599 | Sem imprimir token; não valida credenciais do container |
| Consulta merchant local | HTTP 200, “Teste - Nelson Boulangerie” | Merchant `f36a17d0-e10b-4fdd-a16d-c8ffd866e59b` |
| Status da loja de teste | available=true, state=OK, is-connected=OK | Não prova ingestão/ACK nem identifica qual consumidor a mantém conectada |
| DigitalOcean app shopman-nelson | deployment ACTIVE `812eaf0b-77b8-42b5-a307-3704d50f4c57` | Implantação por imagem; API não informou SHA do código |
| Workers implantados | directive-worker e ifood-poll-worker, 1 instância cada; polling configurado 30s | Presença no deployment não prova saúde |
| Últimas 100 linhas do poll worker | 21 avisos HTTP 403 Access Denied e 79 resumos com polled=0; intervalo 22:06:16–22:45:24 UTC | Resumo vazio após erro não significa consulta bem-sucedida. Causa do 403 ainda não determinada |
| Suíte iFood e projeção catálogo isolada | **89 passed in 6.35s** | Mocks/testes locais; não comprovam E2E publicado |

O ambiente publicado tem variáveis iFood presentes e segredos marcados SECRET. Valores criptografados presentes não provam validade. Os valores das credenciais não foram comparados nem expostos; posteriormente, OAuth e consulta de merchant no próprio container retornaram 200. Não foi aberto segundo loop consumidor nem enviado ACK manual. As duas consultas pontuais de diagnóstico no container retornaram 204.

## Bloqueios e correções necessárias

1. **P0 operacional — polling publicado recebe 403 intermitente.** Verificar em execução do próprio container: contrato/URL, cabeçalhos (inclusive User-Agent), autorização do merchant e resposta sanitizada. Separar recusa WAF (HTML Access Denied observado) de recusa OAuth/escopo JSON. Registrar timestamp UTC, endpoint, HTTP e identificador da resposta, sem Authorization. Não trocar credenciais nem relaxar validação por tentativa. Se persistir, abrir suporte iFood com esses dados. A autenticação local 200 não elimina falha de rede/origem ou configuração no servidor.
2. **P1 — reconciliação incompleta:** a primeira base local não tinha o tratamento CAN; a imagem publicada já o possui (commit `6009deb85`, hash do arquivo confirmado no container). Esse código foi preservado na worktree. CFM/CON ainda não são reconciliados; CAN anterior a PLC também requer teste porque pedido desconhecido é ACKado. Não reconstruir o tratamento CAN existente. O teste `test_process_events_ignores_non_placed_codes` ainda exige ignorar CONFIRMED.
3. **P1 — cancelamento definitivo antes da decisão remota:** `services/cancellation.py:63`, `services/operator_orders.py:534` e `handlers/ifood_status.py:68`. Solicitar cancelamento deve preservar estado pendente até decisão do iFood; rejeição/falha precisa ser visível. Validar estoque/financeiro sem efeito duplicado.
4. **P1 — pagamento na entrega:** `services/ifood_ingest.py:113` marca todo pagamento external/paid. Integrar pending/prepaid, cartão e troco ao contrato operacional que a UI usa (`backstage/projections/order_queue.py:687`). Não basta preservar JSON bruto em data.ifood.
5. **P1 para isolamento — fallback removia filtro de merchant:** correção implementada e testada nesta branch: HTTP 400 não expande escopo; merchantId explicitamente divergente não é ingerido nem ACKado. Mantida compatibilidade com eventos sem merchantId. Ainda não implantada.
6. **P2 — entrega e agendamento:** mapper extrai complemento, referência, CEP, horário e responsável logístico, mas `ifood_ingest.py:105` não os preserva no contrato consumido pela UI. Validar entrega própria/iFood e agendamento com pedidos reais.
7. **Webhook, se escolhido:** além da assinatura, implementar/validar KEEPALIVE, respostas de presença e durabilidade. A view atual retorna 200 mesmo quando processamento registra failed. Evitar registrar o webhook enquanto esse caminho não cumprir seu contrato. Polling é a opção já implantada para o primeiro ciclo.

Esses achados são da base local auditada; a equivalência exata do código da imagem publicada ainda precisa ser comprovada. Não aplicar correção ampla de lifecycle sem os testes de concorrência e efeitos operacionais.

## Documentação oficial atual e divergências

- [Política de homologação por categoria](https://developer.ifood.com.br/en-US/docs/getting-started/homologation/categories): Order + Events FOOD podem usar homologação automática; outros módulos seguem processo próprio/chamado.
- [Wizard de Events](https://developer.ifood.com.br/en-US/docs/guides/modules/events/homologation): Homologação → Nova homologação; selecionar app, loja e Polling OU Webhook; conectividade, confirmar, cancelar, despachar e concluir. Limite publicado de uma tentativa por app a cada quatro horas. Fallback webhook/polling é testado manualmente.
- [Checklist Order](https://developer.ifood.com.br/pt-BR/docs/guides/modules/order/homologation/): conta profissional/CNPJ, app funcional, loja de teste; cenários de pagamento, cupom, retirada/entrega e agendamento. Essa página ainda descreve sessão por chamado e reteste em 15 dias; conferir elegibilidade no portal, priorizando política de categoria e wizard para Order/Events FOOD.
- [OAuth centralizado](https://developer.ifood.com.br/en-US/docs/guides/modules/authentication/centralized/): reutilizar token conforme expiresIn.
- [Polling Events](https://developer.ifood.com.br/en-US/docs/guides/modules/events/polling-overview): referência atual publica `/events/v1.0/events:polling` e `/events/v1.0/events/acknowledgment`. O projeto usa rotas no módulo `/order/v1.0/` verificadas historicamente; não migrar apenas por texto divergente. Validar contrato e escopos atuais em teste.
- [Webhook FOOD](https://developer.ifood.com.br/en-US/docs/food/guides/modules/events/webhook-overview), [assinatura](https://developer.ifood.com.br/en-US/docs/food/guides/modules/events/webhook-signature), [presença](https://developer.ifood.com.br/en-US/docs/guides/modules/events/webhook-presence): HMAC SHA256 do corpo bruto com client secret; rejeição de assinatura inválida; KEEPALIVE 202. Webhook não exige ACK separado; polling exige.
- [Workflow FOOD](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/workflow): operações POST, inclusive startPreparation/readyToPickup/dispatch. Algumas páginas antigas divergem nos verbos e rotas; conferir API reference e resposta real antes de mudanças.
- [Merchant](https://developer.ifood.com.br/en-US/docs/food/guides/modules/merchant/homologacao): se solicitado, homologar também status, horários e interrupções.
- [Gerar pedido de teste](https://developer.ifood.com.br/pt-BR/docs/getting-started/first-steps/generate-test-order).
- [Solicitar acesso a lojas](https://developer.ifood.com.br/pt-BR/docs/getting-started/first-steps/request-access).

Algumas aberturas diretas da documentação retornam 403 para ferramentas automatizadas; a consulta utilizou conteúdo oficial indexado. Confirmar no portal o fluxo disponibilizado para a conta do usuário. Não confundir esse bloqueio da documentação com o 403 independente observado no worker.

## Sequência prática com Pablo

### 1. Preparar o portal sem iniciar tentativa

Em Meus Apps, identificar o aplicativo **de teste FOOD centralizado**, seus módulos/escopos e a loja Teste - Nelson Boulangerie. Confirmar conta profissional/CNPJ e quais módulos serão solicitados. Domínio público do aplicativo: `https://menu.nelsonboulangerie.com.br`. Gestor operacional: `https://gestor.boulangerie.com.br`. Para o primeiro roteiro, selecionar Polling, após restaurar a saúde do worker. Não gerar pedidos novos enquanto 403 e efeitos operacionais estiverem pendentes.

### 2. Preparar ambiente e validar recebimento

Confirmar que apenas o consumidor designado usa a loja de teste, que não há merchants reais no escopo e que as integrações de impressão, entregador, fiscal e mensagens não executarão efeitos reais para os pedidos de teste. O campo isTest preservado não prova isolamento desses efeitos. Validar SKU existente no catálogo: testes históricos auto-gerados usavam SKUs aleatórios e acionavam rejeição automática; revalidar antes da demonstração.

Depois das correções, gerar **um** pedido em Testes → Gerar pedido de teste. Registrar ID/hora; acompanhar PLC → persistência → ACK → pedido visível no Gestor. Confirmar no Gestor, conferir callback e evento no iFood. A API aceitar 202 é evidência parcial: observar a transição efetiva. Não rodar ifood_poll local simultaneamente ao publicado.

### 3. Matriz mínima de evidências

| Caso | Evidência esperada | Estado atual |
|---|---|---|
| Delivery próprio imediato, online | Receber, confirmar, preparar, despachar; conclusão remota refletida | Pendente |
| Delivery iFood | Pronto para coleta e logística corretos | Pendente |
| Takeout imediato/agendado | Horários e estados coerentes nos dois sistemas | Pendente |
| Dinheiro/cartão na entrega | Cobrança pendente, troco/bandeira visíveis | Bloqueio de ingestão identificado |
| Cupom iFood/loja e combo | Totais e responsabilidade corretos, opções completas | Pendente E2E |
| Recusa antes da confirmação | Motivos oficiais, cancelamento efetivo refletido | Pendente |
| Cancelamento pós-confirmação aceito/negado | Solicitação pendente; estado final conforme decisão | Bloqueio identificado |
| Cancelamento/conclusão externos | Atualizar local sem eco, liberar recursos uma vez | CAN existe na imagem; desordem e conclusão continuam pendentes |
| Evento duplicado/desordenado | Sem pedido/estoque/callback duplicado | Pendente E2E |
| Falha temporária e retorno | Sem perda, ACK após persistência e retry observável | Pendente E2E |

Guardar apenas IDs técnicos, timestamps, resultado esperado/observado, status HTTP e capturas necessárias sem dados pessoais. Associar evidências a deployment e base testados.

### 4. Homologação oficial

Com todos os critérios elegíveis verdes, acessar Homologação → Nova homologação, escolher app/loja de teste e Polling; seguir cada cenário do wizard. Registrar resultado/protocolo. Se a opção não existir, ou incluir Catalog/Merchant, consultar a política do módulo e abrir chamado pertinente. Não considerar aprovação de Order/Events como aprovação automática do catálogo.

### 5. Após aprovação

Seguir orientação do portal para app de produção e módulos homologados. Solicitar permissão à loja real; responsável aprova no Portal do Parceiro. Validar credenciais/merchant e executar piloto controlado, mantendo responsáveis disponíveis. Não substituir merchant de teste pela loja real antes dessa autorização.

## Minuta de suporte técnico — não enviada

Assunto: HTTP 403 Access Denied no polling — aplicativo de teste FOOD

Estamos preparando homologação da integração Django Shopman. OAuth e consulta de merchant executados localmente em 12/09/2026 retornaram 200. No worker publicado em DigitalOcean, região nyc, o polling registra HTML “Access Denied” com HTTP 403. Amostra: 12/09/2026 22:06–22:45 UTC. Solicitamos orientação sobre bloqueio de origem e confirmação do endpoint/escopos de Events adequados para o aplicativo. Informaremos no chamado privado clientId, merchantId, endpoint exato e request ID, quando capturado. Não enviaremos client secret ou access token.

Essa minuta não substitui diagnóstico no container e não é um pedido de homologação.

## Continuação autônoma — sessão de portal e container

- Portal aberto no navegador visível do Codex, tela de login pronta para senha/CAPTCHA do usuário; inspeção de apps aguarda autenticação.
- Console do ifood-poll-worker: OAuth 200; merchant 200; lista de merchants autorizados contém somente Teste - Nelson Boulangerie.
- Ambas rotas `/order/v1.0/events:polling` e `/events/v1.0/events:polling` responderam 204 às 22:52:46 UTC. Request IDs: `536ed43c-5a53-4c52-aa71-ed37b765a49b` e `6aacd9c4-e512-4764-8ec8-944b73d16d75`. Nenhum evento foi consumido/ACKado por essas consultas. Isso comprova conectividade naquele instante, não resolve a intermitência histórica.
- SHA256 ifood_events.py publicado: `c962c30ee652dde57d50f4e045b757b62a760d2bb99575ef6f57f193d262fc42`, igual ao arquivo de `6009deb85`. Auth publicado igual à base auditada. Portanto, o diagnóstico original de ausência de CAN era válido apenas para a branch antiga; foi corrigido acima.
- Correção merchant + implementação CAN já publicada preservada na worktree; **98 testes passaram em 36.07s**, Ruff dos arquivos de implementação/novo teste e diff --check verdes. Sem deploy; não substituir imagem completa com esta branch antiga sem integração na base de release vigente.

## Portal autenticado — constatações verificadas

- Perfil Profissional confirmado na Home. Wizard disponível: conectividade, receber/confirmar, cancelar, despachar e validar pedidos, com capturas de tela e estimativa de dez minutos. Apenas telas de preparação foram abertas; nenhuma tentativa foi submetida.
- Wizard de seleção informou “Nenhum aplicativo em desenvolvimento encontrado”. A lista de apps carregou depois, mas alterna com erros de carregamento da conta/lista. Portanto, o resultado vazio não deve ser tratado como prova definitiva de inexistência de app elegível.
- Aplicativo `NB Teste (C)` é centralizado, categoria TEST, ID `662ff49d-64d0-47be-bee3-d405e577a810`. Order, Events e Merchant estão habilitados (além dos demais módulos fixos de teste). Permissão ativa somente para Teste - Nelson Boulangerie.
- **Webhook do app de teste ativo com URL obsoleta**: `https://api.staging.nelsonboulangerie.com.br/api/webhooks/ifood/`. O hostname falhou em resolução DNS nesta máquina. A rota também é a legada normalizada, não a rota assinada `/ifood/events/`. Categorias FOOD e GROCERY; presença por merchant desativada. Nenhuma configuração alterada no portal.
- App `nb-manychat-webhook` (ID `d852f581-9b04-44ed-83e8-fce81d2669f4`) é centralizado, categoria **PDV**, em desenvolvimento. Order e Merchant ativos; **Events desmarcado** e editável. Portal orienta abrir ticket. Antes de criar app duplicado, verificar alinhamento de escopo e elegibilidade desse app. Habilitar Events amplia acesso do app e requer confirmação específica no momento de salvar; nenhuma permissão foi modificada.
- Existe também `Nelson Boulangerie - Catálogo` em desenvolvimento e aplicativo de teste distribuído. Não foram alterados.
- Fluxo de cadastro de app foi apenas inspecionado: Centralizado → categorias (PDV, Catálogo etc.); há aceite de responsabilidade/termos. **Não aceitamos termos, não continuamos além desse aceite e não criamos credenciais.**
- Portal tem falhas intermitentes reais de UI: “Estamos com problemas para carregar os dados da sua conta”, erro da lista e, ocasionalmente, “este app não existe” para app anteriormente lido. Console mostra erros de execução React/JavaScript. Não inferir que o app foi excluído. Recarregar/retentar recuperou acesso parcialmente, mas a instabilidade voltou. Solicitada preferência do usuário por tentar Chrome.
- Correção CAN anterior a PLC implementada: pedido desconhecido libera claim para retry e não ACKa cancelamento; redelivery cancela quando PLC tiver sido persistido. Testes cobrem ordem invertida no mesmo lote e entre lotes, evento órfão e replay. **101 testes passaram em 8.59s** na suíte iFood + projeção catálogo; código ainda não publicado.

## Preflight operacional no container às 23:30 UTC

Leitura somente, sem mudar configurações: canal iFood com confirmação manual (timeout 5 minutos), pagamento externo, notificações backend console, courier none, prep_start auto. Há dois pedidos iFood históricos, ambos terminais, nenhum aberto. O resolver fiscal efetivo combina solicitação explícita, pagamento eletrônico, pagamento diferido e recibo solicitado; método external não é eletrônico nesse resolver. Não foi exibido dado pessoal ou segredo.

Ainda há efeitos de estoque e KDS compartilhados: reserva desde ingestão e possível baixa/ticket ao aceitar. A flag is_test não constitui isolamento. Para ensaio completo, usar banco/instância isolados ou inventário e execução de teste explicitamente separados; não assumir que o nome da loja de teste elimina os efeitos locais.

Validação adicional: 76 testes de projeção/fila e 13 subtests; frontend typecheck aprovado. ESLint dos arquivos envolvidos sem erros; lint global da superfície apresenta 11 erros anteriores de no-dynamic-delete em arquivos não modificados. Não foram alterados lockfiles ou dependências declaradas.
