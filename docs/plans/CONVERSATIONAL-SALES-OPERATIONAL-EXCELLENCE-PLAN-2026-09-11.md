# Canal de vendas conversacional — plano de excelência operacional

Data: 11/09/2026. Estado: **plano auditado; nenhuma implementação ou ativação autorizada por este documento**. Cliente é o operador principal. Canal modelo: WhatsApp via ManyChat. Instagram DM, Messenger e outros entram pelo mesmo contrato de conversa, com capacidades próprias e gates separados.

## 1. Resultado que importa

O cliente deve decidir apenas o que falta, sem repetir dados conhecidos, reconstruir sacola ou descobrir sozinho se houve pedido/cobrança. Cada resposta preserva contexto e apresenta o resultado, a pendência e a próxima ação autorizada.

**Omotenashi é critério de correção:** resposta cordial com preço inventado, item perdido ou recuperação que exige refazer a compra falhou. Confirmações necessárias protegem o cliente; perguntas repetidas, confirmações redundantes e upsell que atrasa a solução são desperdício. Conversão, velocidade e custo de IA não compensam falha de integridade.

### Escopo

Da descoberta ao pós-compra: catálogo, disponibilidade, sacola, identidade, entrega/retirada, revisão, confirmação, pedido, pagamento, acompanhamento, interrupções, transferência ao site, atendimento humano e aviso solicitado. Auditar também os efeitos acionados em estoque, lifecycle, produção/KDS, fulfillment/courier, fiscal e notificações, preservando seus responsáveis atuais.

Reutilizar Storefront, Gestor, PDV, Produção e Marketing. Não criar checkout, CRM, inbox, painel financeiro, cadastro de consentimento, fila ou regras comerciais paralelos. Campanhas proativas, cobrança automática, recomendação sensível, transcrição de mídia e ativação de outros canais exigem escopo próprio.

Nesta sessão: somente plano e prompt. Diagnósticos temporários não alteraram produto, banco compartilhado, ManyChat ou produção.

## 2. Proveniência, método e limites da evidência

### 2.1 Isolamento

- Origem preservada: `/Users/pablovalentini/Dev/Claude/django-shopman`, branch `codex/shopman-backstage-marketing-hardening`, HEAD `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`; arquivos não rastreados de terceiros apenas lidos.
- Worktree: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-conversational-plan-20260911`; branch `codex/conversational-excellence-plan-20260911`.
- Base auditada: `1138c95eee0862630330328cf3bfe2f0b6424796`, referência **local** `origin/main` sobre a qual a branch vazia foi reposicionada antes das edições. Sem fetch; não se afirma atualidade do remoto.
- Testes: `config.settings_test`, SQLite isolado, integrações inertes/fakes e credenciais vazias. Imports de Orderman/Guestman conferidos para os packages deste worktree, apesar do runtime compartilhado.

### 2.2 Referências lidas integralmente

| Referência | Local de origem | Linhas / SHA-256 | Rigor adotado, sem importar diagnóstico |
|---|---|---|---|
| Produção, 08/09 | workspace original, `docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` | 1005 / `f435f49347391b7d1bdb0e9de29a3278d14d17897bb93022b2880679014ac68d` | fatos e autoridade antes de UI; esforço por jornada; progressão sem atalhos de integridade |
| Marketing, 08/09 | workspace original, `docs/plans/MARKETING-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` | 1743 / `de59ffaea5228aea38588fc3471049989cc86c06787640674837104ef1b94da4` | intenção revista, evidência de envio, unknown, consentimento por finalidade, IA limitada por fatos |
| Gestor de pedidos, 10/09 | `/Users/pablovalentini/Dev/Claude/django-shopman-orders-plan/docs/plans/ORDERS-OPERATIONAL-EXCELLENCE-PLAN-2026-09-10.md` | 715 / `e58d12c86515645652a847834ba5ce6cf973c6712e551427d2f5057a86bee5ab` | Action canônica, recibo consultável, falha parcial, recuperação por objeto e dono |
| PDV, 10/09 | `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-pdv-plan-current-20260910/docs/plans/PDV-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-10.md` | 718 / `8963a1fcebb4666de92e2a31373abfffbcdea62adc28d7ca8518b5a2037aaab9` | concorrência real, dinheiro/quantidade canônicos, mesma intenção após timeout, gates de campo |
| Storefront | workspace original, `docs/plans/completed/STOREFRONT-EXCELLENCE-HARDENING-PLAN.md` | 231; hash no manifesto abaixo | continuidade de sessão, conectividade, copy de recuperação, verificação integrada |

Também lidos integralmente: `docs/plans/MANYCHAT-CONVERSACIONAL-PLAN.md`, `docs/plans/WHATSAPP-CONCIERGE-PLAN.md`, `docs/decisions/adr-009-whatsapp-via-manychat.md` e `docs/decisions/adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md` e documentação de projeção conversacional/concierge disponível na base. São contexto de intenção, não prova de prontidão. A afirmação histórica de webhook não registrado não vale nesta base. Percentuais antigos de conclusão, modelos de IA, preços e contagens de testes não são metas nem evidência atual.

A skill local `unfold-admin-canonical` foi aplicada à auditoria do Admin existente. Se houver edição futura, ler playbook, política e inventário da skill; usar ModelAdmin/Unfold e executar `make admin` integral. Este plano não autoriza console customizado ou nova inbox.

### 2.3 Classificação

- **D — defeito confirmado:** execução local reproduzida ou caminho de código inequívoco. Indicar qual dos dois; reprodução não equivale a incidente de produção.
- **H — hipótese:** exposição plausível sem demonstração completa; ensaio obrigatório antes de transformá-la em diagnóstico ou correção.
- **G — decisão humana:** política, autoridade, capacidade do fornecedor ou ambiente que código não pode inventar.
- **M — solução madura a conservar:** observada no código atual e, quando indicado, protegida pelas suites executadas.

A auditoria percorreu a cadeia acionável de entrada a efeitos e retorno, incluindo writers compartilhados e fronteiras de autorização. Não executou todas as suites do monorepo, PostgreSQL, navegador real, banco de produção, gateway, WhatsApp ou conta ManyChat. Logo, não certifica operação em campo, ausência de todos os defeitos downstream ou ganhos humanos já medidos. Ganhos posteriores abaixo são contratos de aceite; a prova desta sessão é estrutural e experimental local.

## 3. Cadeia atual e propriedade dos fatos

Todos os caminhos abaixo são relativos à raiz da base auditada. Números de linha são referências nessa base, não garantias para commits futuros.

| Etapa / entrada | Código percorrido e fronteira relevante | Dono e reutilização obrigatória |
|---|---|---|
| Roteamento e ingresso | `config/urls.py`, `storefront/concierge/urls.py`, `webhook.py:116`, `service.py:150` | ingressos de conversa e de sync de assinante são distintos; conservar autenticação específica de cada integração |
| Identificação | `service.identify`, `guestman.adapters.auth.CustomerResolver`, `packages/guestman/.../contrib/manychat/{resolver,service,views}.py` | Guestman guarda cliente; Doorman determina força de identidade. Contato ManyChat não é credencial universal |
| Persistência e fila | `shop/models/concierge.py`, `service._enqueue_turn`, `handler.py`, `shop/directives.py`, dispatcher Orderman | Conversation/Message guardam contexto de interação; Directive é a fila; IdempotencyKey é recibo técnico |
| IA e ferramentas | `agent.py`, `prompt.py`, `tools.py:353–1323` | IA interpreta linguagem; servidores validam identidade, inputs, revisão, autorização e efeito |
| Catálogo e sacola | `shop/projections/catalog_context`, `tools._catalog_channel_ref`, `shop/services/{cart,sessions,availability}`, `packages/orderman/.../services/modify.py` | Offerman/Shopman resolvem preço e disponibilidade; Session é a sacola; Stockman detém reservas |
| Entrega/revisão | `tools.py:610,718`, `storefront/intents/checkout`, `storefront/services/pickup_slots`, `shop/services/{business_calendar,geocoding}`, modifiers/rules | agenda, raio/taxa, capacidade, unidade e total permanecem canônicos |
| Pedido | `tools.py:783`, `shop/services/checkout.py:37,67`, `packages/orderman/.../services/commit.py` | commit trava Session, adota pedido existente e escopa idempotência por canal/sessão; conservar |
| Pagamento | `shop/services/payment.py:75,180`, recuperação/consulta/cancelamento no mesmo serviço e adapters Payman | intent, valor capturado, expiração e refund vêm de Payman; pedido criado não significa pago |
| Ciclo e efeitos | `shop/lifecycle.py`, `production_lifecycle.py`, handlers de fase/fulfillment, serviços stock/payment/notification/fiscal/courier | lifecycle, guards de pagamento, reservas adotadas, KDS/encomenda, fases duráveis e alertas permanecem responsáveis |
| Acompanhamento | `shop/services/conversation.py`, `customer_orders.py`, tracking/payment projections, `storefront` API de conversa de pedido | reaproveitar `RemoteConversationProjection`, `Action`, ownership e política de cancelamento/recebimento/avaliação |
| Saída e avisos | `concierge/transport.py`, `shop/adapters/notification_manychat.py:157,458`, `shop/services/notification.py:78,158` | adapter traduz canal; notificação transacional existente já tem dedupe persistente e recusa reenvio incerto |
| Site e autenticação | `tools.py:955,1035`, `packages/doorman/.../services/access_link.py:200`, `storefront/api/auth.py:269,322`, `shop/services/access.py` | AccessLink com hash, validade, audience, uso único e sessão preservada; site é continuação canônica |
| Aviso solicitado | `tools.py:1077`, `storefront/services/stock_alerts.py`, receivers/notify e `shop/services/manychat_marketing_safety.py` | inscrição existente por finalidade, revogação, prazo e opt-out; não criar consentimento “do concierge” |
| Atendimento humano | `service.py:411,430`, `storefront/admin/concierge.py:224` | ManyChat Live Chat atende; Admin configura/audita e oferece ações autorizadas; nenhuma inbox nova |

Prefixo `shopman/` antecede os caminhos `shop/` e `storefront/` da tabela. Nas dependências de packages, o namespace é `packages/<pacote>/shopman/<pacote>/...`.

### 3.1 Soluções maduras a preservar

| ID | Garantia observada na base atual |
|---|---|
| M01 | Webhooks registrados, autenticação fechada sem chave fora de DEBUG e turno normalmente assíncrono por Directive futura. |
| M02 | Dedupe de diretiva viva e `remote_mutations` com fingerprint e commit conjunto de efeito local/recibo. Não criar outro barramento. |
| M03 | Commit protegido por chave e sessão consumida; testes conservam um Order mesmo com outra chave na mesma sessão. D05 é falha de recuperação do wrapper, não prova de duplicação no core. |
| M04 | Reservas/adoção de holds, gates de compromisso/pagamento, encomenda separada de trabalho imediato, fases duráveis e recuperação de intent existente. |
| M05 | Projeção conversacional derivada de pedido/pagamento, Actions e filtro de identidade. Nenhum IDOR confirmado; ampliar canal exige negativos de autorização. |
| M06 | AccessLink com lock, validade, audience, uso único e preservação de sessão; Storefront adota contexto transportado mesmo com cookie antigo. |
| M07 | Copy configurável, limites, allowlist, handoff, histórico e fallback. Corrigir continuidade e saída útil sem remover contenção de custo. |
| M08 | KDS dispara delta por `line_id` sob lock de Session; Craftsman→Stockman materializa estoque; fiscal consulta/adota nota por referência; courier bloqueia novo despacho incerto. |
| M09 | Notificações transacionais e inscrições de disponibilidade têm contratos mais fortes que o envio livre do concierge. Reutilizá-los onde cabem, sem transformar ledger de campanha em inbox. |

## 4. Achados confirmados e hipóteses

### 4.1 Defeitos confirmados

Prioridade P0 significa bloqueio do piloto do caminho afetado; não autorização para desligar produção nesta sessão. Os IDs de reprodução T-Dxx aparecem no apêndice executável.

| ID / prioridade | Evidência atual | Consequência para o cliente e aceite da correção |
|---|---|---|
| D01 P0 | `service.unanswered_inbound:260` usa ID da última REPLY/NOTE; `run_turn:293` fotografa inbound antes do modelo. T-D01 insere segunda mensagem durante a execução; ela não é processada e `pending_more=False` | “Na verdade, três” pode desaparecer da fila. Associar entrada ao turno que realmente a consumiu; nenhuma resposta/nota posterior pode reconhecer entrada não consumida |
| D02 P0 | `receive_inbound:184–206`: mensagem confirma transação antes de `_enqueue_turn`; replay retorna duplicate antes de reparar. T-D02 injeta falha na fila, repete mesmo evento e não reenfileira | cliente precisa insistir para acordar atendimento. Aceitação durável deve incluir trabalho recuperável; replay repara pendência sem duplicar mensagem |
| D03 P0 | `_send_reply:372` envia antes de persistir; bool False ainda cria REPLY; T-D03 esvazia pendência com `delivered=False`. Adapter `_api_call` distingue unknown, mas `send_text` o reduz a bool | silêncio é tratado como resposta. Persistir intenção antes da rede e distinguir preparado/aceito/não aplicado/desconhecido; não afirmar entrega ao aparelho sem evidência |
| D04 P0 | `review_order:718` emite token; `place_order:783` não exige entrada de confirmação nem prova de revisão apresentada. T-D04 cria pedido com zero mensagens do cliente | prompt é a única barreira entre orçamento e compra. Vínculo verificável entre revisão oferecida, intenção explícita e comando é obrigatório |
| D05 P0 | `place_order` limpa sessão/quote e primeiro verifica sacola; T-D05 repete token: `no_cart`, um único Order | após resposta perdida o cliente não resgata o resultado da intenção. Consultar recibo autorizado antes de exigir sacola aberta |
| D06 P0 | `set_fulfillment:610` chama `cart.set_delivery_draft` antes de retornar erros. T-D06 usa horário inválido e constata troca delivery→pickup e remoção de endereço | “não consegui alterar” contradiz estado alterado. Input inválido não escreve; pacote de entrega muda atomicamente ou informa resultado parcial explícito quando inevitável |
| D07 P1 | `set_item:473` converte int/clamp; T-D07 quantidade -1 remove item; `last_order:932` e transferência também truncam decimal | interpretação inválida vira ação válida. Usar parser/unidade canônicos; rejeitar bool, sinal indevido e perda de precisão; zero só remove quando intenção de remover for válida |
| D08 P0 | `return_to_concierge:430` salva ACTIVE e ignora False do campo ManyChat; T-D08 confirma. `mark_handoff` também ignora resultado remoto | dois lados divergem sobre quem responde. Posse local deve impedir bot imediatamente; sincronização remota tem evidência/recuperação e não é apresentada como concluída sem prova |
| D09 P0 | `run_turn:293` não revalida enabled; T-D09 desliga chave e observa modelo/resposta em trabalho pendente | chave de contenção não contém trabalho já aceito. Verificar admissão, execução, ferramentas e saída, com regra explícita para drenar efeitos já autorizados |
| D10 P1 | `order_status:887` captura erro de projeção e segue; T-D10 retorna “Não achei” para pedido existente | falha técnica induz cliente a refazer compra. Diferenciar vazio autorizado de consulta indisponível; manter contexto do pedido e próxima consulta segura |
| D11 P0 | `_external_id:140` usa texto+assinante+minuto quando não há ID; T-D11 confirma colisão de “sim” no mesmo minuto e alteração ao minuto seguinte; ID explícito é truncado em 80 | mensagens legítimas colidem, retries mudam de identidade. Exigir identidade de evento verificável para mutações; não deduplicar intenção por texto/tempo |
| D12 P0 | `_copy_cart_to_web:1035` captura falhas por item e abandona origem se qualquer item copiou. T-D12 injeta falha no segundo SKU; origem abandonada, destino incompleto e horário ausente | perda silenciosa de item e contexto. Transferência conserva itens/dados/reservas ou preserva origem inteira; nunca “sacola levada” por sucesso parcial |
| D13 P0 | `agent` permite texto livre/preâmbulos; `clean_text` é sintático. T-D13 injeta preço R$ 999,99 para item de R$ 0,90 e resposta sai intacta | valores e promessas podem ser inventados. Renderização de fatos críticos e links deve ser determinística, inclusive preâmbulos |
| D14 P1 | `handler.py:46–72` para após 5 loops e depende de nova mensagem; `run_turn` captura exceção de modelo antes do classificador do handler; inspeção estrutural | backlog pode depender de nova insistência; comentário sobre retries não prova recuperação. Criar continuação durável após limite; classificar erro no ponto em que ocorre |
| D15 P1 | `send_web_link:955` escolhe primeiro pedido recente, não recebe order_ref; retorno de pedido não cria AccessLink. Falha de mint após copiar ainda retorna `cart_carried=bool(web_key)`; inspeção | falta contrato de continuidade exata. Exigir alvo e resultado da transferência/acesso; autenticação existente pode ainda ser necessária, sem inventar vulnerabilidade |
| D16 P0 para aviso | `notify_when_available` chama `stock_alerts.subscribe` com disclosure default; serviço grava `proof_status=verified`. Tool não exige evidência de disclosure apresentado/aceito; inspeção | registro forte não prova autorização do cliente. Passar evidência real pela inscrição existente; não converter uma inferência do modelo em consentimento verificado |
| D17 P1 | `agent.history_for:100` janela de 40 exclui notas, não usa summary; `AgentOutcome.order_ref` não é salvo como continuidade. `send_text:458` corta cauda antes de enviar; inspeção | contexto necessário pode sair da janela, ação/Pix/prazo pode ser cortado. Contexto por referências e blocos essenciais indivisíveis, sem memória factual do modelo |

**Fatos estruturais que dependem de gate, não acusações adicionais:** a action Admin de devolução usa `permissions=["view"]` enquanto alteração é negada; G03 decide autoridade pretendida e WP07 separa capacidade de leitura e mutação. Lista de piloto vazia atualmente libera todos; G01/WP01 devem impedir expansão acidental. Catálogo cai silenciosamente para `web` quando listing conversacional não está disponível; H03 mede consequência comercial antes de atribuir preço incorreto.

### 4.2 Hipóteses — ensaio antes de alteração

| ID | Questão aberta | Prova requerida / destino |
|---|---|---|
| H01 | Aceite remoto seguido de resposta perdida/crash pode duplicar saída se houver retry; fornecedor fornece ID estável, consulta ou idempotência utilizável? | fake registra efeito e lança timeout; sandbox autorizada confirma capacidades. Sem recibo consultável, manter unknown e proibir repetição automática cega; WP03/G02 |
| H02 | Workers concorrentes, expiração de claim e handoff durante tool podem aplicar intenção obsoleta ou sobrescrever JSON/counters | PostgreSQL, conexões distintas, barreiras em leitura/claim/tool/commit/send e revogação. Dedupe atual é preservado, mas não substitui prova de fence; WP02/04/07 |
| H03 | Fallback de listing web, alteração de frete/promoção/agenda entre review e commit, subtotal esperado separado do total geram diferença não consentida? | fixtures com preços por canal, fee/cupom e mudança concorrente. Comparar total final completo sob lock; sem mudar regras comerciais; WP04 |
| H04 | Identificação/getInfo no ingresso estoura orçamento e lê última mensagem posterior ao evento? | stub com atraso e duas mensagens; `_API_TIMEOUT=10` no resolver compete com prazo ManyChat de 10s. A chamada síncrona é comprovada, latência de produção não; WP01 |
| H05 | Cliente do IG/Messenger sem telefone ou IDs iguais em contas diferentes pode ser associado incorretamente; source ManyChat pode promover indevidamente força de identidade ao expandir canais | matriz contas/canais/IDs colidentes e link encaminhado, teste de Doorman; não liberar adapter real até G02/G04 e WP08 |
| H06 | Avisos lifecycle e resposta de place_order duplicam a comunicação de um fato ou apresentam versões diferentes | ensaio integrado commit→intent→notification→turn, permutações de ordem; fixar proprietário de cada bloco sem desligar notificação operacional indiscriminadamente; WP03/06 |
| H07 | Webhook separado de sync marca replay por `data.id` antes do sync; payload lista não tem guard de objeto. Efeito em eventos/consentimento realmente usados nesta conta? | fixtures do contrato real assinadas; falha sync→retry, id assinante vs event_id; testar também `bool("false")` no parser de consentimento e validar tipos do payload real; confirmar uso. Correção localizada Guestman se reproduzida; não migrar autenticação do concierge para HMAC inventado; WP01/08 |
| H08 | Transferir com saldo todo reservado na origem falha por reservar novamente; carrinho web preexistente pode ser abandonado por `assign_phone_handle` | estoque exato, duas sessões, dois browsers, replay/crash. Provar conservação e definir escolha de conflito em G05; D12 já confirmado independe disso; WP05 |
| H09 | Leitura de status do tool sem `resolve_timeouts_if_due` diverge do endpoint de acompanhamento | clock vencido, worker parado, projeção antes/depois; reusar fachada canônica apropriada, documentando efeitos de reconciliação da leitura; WP06 |
| H12 | Falha entre criação de Fulfillment e gravação do marcador `fulfillment_created`, ou retomada de update após mudança de status, pode deixar registro/sync/notificação divergentes? | `services/fulfillment.py:24` e `handlers/fulfillment.py`: fault injection nos callers transacionais reais e retry, inspecionando todos os registros. Se confirmado, correção no owner compartilhado e regressão de ciclo; não criar fulfillment do concierge; WP06/09 |
| H11 | Dados de entrega/defaults salvos após compra correspondem ao pedido? `place_order` passa customer/payment/notas; `checkout._post_commit_intent` deriva fulfillment do payload, com default pickup | fixture delivery com endereço/slot na Session, inspecionar Order e CheckoutDefaults/Address após commit; corrigir passagem de contexto pela fachada existente se divergente; WP04/05 |
| H10 | A regra de histórico, limites e identidade recuperada exige perguntas repetidas no uso real | corpus e observação do cliente com interrupções, áudio, linguagem fragmentada, “o de sempre”, dois pedidos; medir esforço, não inferir latência/abandono a partir de teste unitário; WP09 |

## 5. Contratos normativos

São especificações para implementação futura. Nomes lógicos de campos abaixo não impõem tabelas novas. Cada campo deve ter dono, fonte, retenção e consumidor; eliminar qualquer duplicata do domínio.

### C01 — Entrada durável e identidade do evento

Envelope normalizado: versão de contrato, provider, conta/tenant verificados, canal de transporte, subject opaco, event_id íntegro, instante informado pelo provider, instante recebido pelo servidor, tipo de mensagem, conteúdo limitado, referência de correlação e evidência de autenticação. `channel_ref` comercial é resolvido de configuração confiável; não vem como autoridade do texto/body. Não confundir WhatsApp de transporte com regras comerciais de Channel.

Autenticar antes de persistir/consultar identidade. API key constante comparada com segurança para External Request; HMAC apenas onde a integração realmente o emite. Rotação permite janela controlada de duas chaves; não registrar segredo. Limitar tamanho/profundidade, MIME/tipo, frequência por conta/subject além do IP; IP compartilhado do provider não pode bloquear clientes arbitrariamente. Sem credencial, falhar fechado.

A transação de aceitação grava evento deduplicado e trabalho durável na Directive existente. Só confirmar aceitação após commit. Replay da mesma identidade/payload consulta resultado/repara agendamento; identidade igual com payload diferente é conflito auditável. Não truncar ID para dedupe. Ausência de event_id confiável bloqueia mutação automática desse caminho: compatibilidade legada pode encaminhar atendimento/leitura, sem declarar exatamente-uma-intenção. Não gerar ID aleatório por retry nem hash por minuto como substituto.

ACK é de recebimento, não de resposta/pedido/pagamento. Adaptar 200/202 ao contrato ManyChat homologado; docs do fornecedor limitam certos mapeamentos a 200. Payload de ACK não precisa expor IDs internos. Nenhuma busca getInfo/modelo/geocoding/gateway no trecho crítico; enriquecimento assíncrono referencia evento específico, nunca substitui silenciosamente seu texto por “última mensagem”.

### C02 — Turno, ordem e continuidade

Conversation/Message registram entradas consumidas por turno, revisão, intenção pendente, refs de sessão/pedido/recibo/revisão oferecida e resultado de saída. Persistir referências mínimas; preços, pagamento e cadastro continuam em seus owners.

Usar claim com validade/fence: fotografar contexto sob lock curto, processar fora dele e revalidar fence, identidade, posse humana, enablement e revisão antes de cada efeito/saída. Nunca manter lock durante modelo/provider. Resposta não reconhece entrada que seu turno não consumiu; confirmação atrasada não confirma outra revisão.

Após limite de loops, agendar continuação durável e justa entre conversas. Recuperar entradas órfãs/claims vencidos pela Directive existente; reinício ou virada do dia não exigem nova fala. Limite de IA oferece saída determinística ou humano.

Histórico serve à linguagem; fatos vêm de Session/Order/recibos/Actions. Resumo é descartável/versionado e não concede autorização. Retomada mostra objetivo, escolhas válidas, alterações e próxima ação, sem depender de reler quarenta mensagens.

### C03 — Saída, certeza e resposta perdida

Persistir mensagem lógica e blocos a enviar antes da chamada externa, usando Message/Directive e infraestrutura de recibos adequada. Reutilizar conceitos do envio transacional; não usar campanha como inbox. Cada bloco possui identidade estável, sequência, hash do conteúdo, intenção/fato de origem, tentativa e resultado técnico.

Estados de transporte, separados do estado do pedido: preparado, em execução, aceito pelo provider, comprovadamente não aplicado, desconhecido, entregue/lido somente se houver evento confiável. “Aceito” não vira `delivered` por conveniência. Falha parcial preserva sucesso de blocos anteriores e pendência do bloco exato. Pix, valor, prazo e CTA não podem ser cortados no meio; dividir em unidades semânticas conforme capacidades do canal, com código Pix isolado e copiável.

Timeout depois de possível efeito mantém unknown. Reconciliar por identificador consultável quando disponível; sem essa capacidade, atendimento verifica pelo procedimento G02, e o sistema não reenvia cegamente. Uma nova consulta do cliente pode produzir resposta atual sobre o **mesmo** pedido/recibo; isso não autoriza repetir compra/cobrança nem afirmar não entrega anterior. Distinguir nova resposta solicitada de retry do mesmo envio.

Revalidar janela, finalidade, consentimento quando aplicável e política do canal imediatamente antes da saída. Não presumir janela aberta porque a entrada ocorreu antes de uma fila longa. Respostas de compra e lifecycle têm proprietário por fato/revisão; reduzir ruído preservando aviso necessário e recuperação. Link/pagamento pendente nunca é anunciado como enviado apenas porque foi acrescentado a `extra_replies`.

### C04 — Ferramentas, revisão e confirmação do cliente

Ferramenta é comando sujeito à autoridade do servidor, não permissão concedida ao modelo. Validar schema em runtime, enum, limites, unidade e decimal canônicos. Separar referência de SKU/linha da frase do cliente; ambiguidade pede só a escolha faltante. Jamais converter negativo em remoção, truncar quantidade, arredondar valor pela IA ou expor stack trace em mensagem de erro.

Intenção mutante inclui ator cliente autenticado/identificado conforme capacidade, recurso, operação, payload normalizado, revision/base, chave estável e evidência da solicitação. Receipt usa `remote_mutations`/IdempotencyKey no escopo correto. Autorizar antes de replay. Mesma chave/payload/base retorna mesmo resultado; payload diferente conflita; resultado pode ser aplicado, já aplicado, não aplicado, em andamento, parcial ou desconhecido. Esses outcomes não são estados de Order.

Revisão deriva do carrinho e política correntes: linhas/unidades, totais/descontos/frete completos, entrega/retirada, data/slot/fuso, endereço necessário, pagamento e consequência da confirmação. Snapshot/identificador de revisão é ligado a sessão, cliente, base comercial, emissão/validade e conteúdo oferecido. Token interno não substitui aceite.

Commit requer confirmação explícita recebida depois da revisão oferecida e relacionada a ela. Botão/postback vinculado é preferível quando suportado; em texto, “sim” só vale com uma única confirmação pendente e sem alteração interveniente. Se a pessoa disser “sim, mas três”, aplicar revisão de quantidade e apresentar novo resumo, sem comprar. Declaração inicial completa permite montar e revisar de uma vez; não autoriza fechar sem mostrar consequência. Nunca exigir a mesma confirmação duas vezes se já há recibo.

Revalidar total final completo, identidade, estoque, agenda e base sob a fronteira transacional canônica do commit. Mudança relevante exige nova revisão com **diferença destacada**, preservando dados; se nada mudou, não pedir redigitação. Evitar copiar `_validate_preorder` para novo módulo: se a dependência atual de Shop/Storefront estiver invertida, extrair façade canônica mínima e migrar consumidores juntos.

Para operação puramente local, efeito, evento, recibo e agendamento compartilham commit. Gateway/modelo/transporte ficam fora do lock e recebem trabalho durável. Resposta perdida consulta recibo antes de procurar sacola aberta. Não envolver indiscriminadamente todo checkout existente em atomic se isso trouxer provider para dentro da transação; mapear callbacks e separar fases antes.

### C04.1 — Resultado e recuperação na fronteira conversacional

Contrato lógico mínimo da ferramenta: `ok`, `code`, `outcome`, `intent_ref`, `resource_ref`, `revision`, `facts`, `missing_inputs`, `next_action` e `pending_effects`, quando aplicáveis. Projeções existentes fornecem os fatos/Actions; o envelope acrescenta somente resultado da intenção. IDs técnicos são internos, não tarefas para o cliente memorizar. `next_action` referencia Action autorizada com alvo/precondição e motivo se bloqueada, sem aceitar URL arbitrária do modelo.

| Situação | Código/outcome contratual | Comportamento |
|---|---|---|
| Schema inválido | `invalid_input` / não aplicado | explicar campo necessário, manter escolhas; 400 na API |
| Identidade insuficiente | `identity_required` / não aplicado | acesso canônico contextual; 401/403 conforme contrato existente |
| Alvo fora do escopo | indisponível sem revelar existência | não devolver recibo/dados alheios; 404 quando aplicável |
| Base mudou | `revision_conflict` / não aplicado | diferença e nova revisão; 409, draft preservado |
| Mesma key/payload | resultado original / já aplicado | retornar recurso/pendências atuais sem novo efeito |
| Mesma key com payload diferente | `intent_conflict` / não aplicado | 409; nenhuma execução |
| Aceito ainda processando | `in_progress` | 202/ACK homologado; consulta por intenção, sem comprar novamente |
| Pedido criado, pagamento pendente | `payment_pending` / parcial | Order e Action de pagamento canônicos; não devolver erro genérico de checkout |
| Timeout com efeito possível | `outcome_unknown` / desconhecido | conservar key e pendência; consultar/reconciliar, nunca presumir não aplicado |
| Fonte de status indisponível | `projection_unavailable` | manter alvo/contexto e recuperação; não responder lista vazia como sucesso |

Códigos são vocabulário proposto da borda: mapear códigos equivalentes existentes antes de criar qualquer novo enum. HTTP 5xx não prova ausência de efeito; cliente/flow não gera nova intenção automaticamente por status. Consulta do recibo é sem efeito; reconciliação que possa chamar provider usa ação/capacidade própria e sua evidência.

### C05 — Continuidade chat ↔ site ↔ chat

Usar Session e AccessLink existentes. Alvo explícito é sessão ou pedido autorizado, não “último” por conveniência. “Abrir cardápio” não autoriza mover/destruir sacola. Se há dois pedidos plausíveis, mostrar duas escolhas curtas com contexto suficiente, sem pedir número memorizado.

Quando transferência for necessária por canais comerciais distintos, congelar origem/base, destino, todas as linhas e dados de fulfillment/notas relevantes; reprecificar pelo destino e apresentar diferenças antes da troca. Conservar reservas pelo mecanismo Stockman autorizado, sem duplicar holds nem desreservar entre etapas expondo estoque. Operação local de transferência atômica ou staging recuperável; sucesso parcial nunca abandona origem. Resolver carrinho web existente por escolha contextual aprovada em G05, não merge/abandono silencioso.

Criar link/recibo e preservar destino exato; falha do link não anuncia contexto transportado acessível. Retomar mint ou acesso da mesma operação, sem copiar de novo. Token expirado/usado em outra sessão pede somente reautenticação necessária; dados do trabalho permanecem. Token não é identificador em log nem label de métrica. Reuso com sessão viva conserva o comportamento maduro do Storefront.

### C06 — Pedido, pagamento e próxima ação

Consumir projeção conversacional canônica completa, incluindo Action, bloqueio, prazo, origem e recuperação. Não criar status `aguardando_pix` paralelo a Payman. Separar “pedido registrado”, “aguardando aceite da loja”, “pagamento pendente/capturado”, “em preparo”, “pronto”, “entrega”, “fiscal pendente” conforme fatos relevantes ao cliente.

A mesma política que habilita Action no site/Gestor revalida no comando conversacional. Avaliar cancelamento/recebimento/avaliação por essa política e identidade do cliente, nunca por permissão administrativa delegada ao bot. Se ainda não houver comando seguro no canal, oferecer link contextual autorizado ao recurso existente; não anunciar capacidade inexistente.

Pagamento falha após pedido: manter Order e intenção original, mostrar pendência e ação de obter/consultar pagamento existente. “Já paguei” consulta fonte canônica, não marca pago; screenshot não é confirmação financeira. Callback duplicado/tardio, expiração e cancelamento concorrentes entram na prova; reembolso solicitado não equivale a dinheiro devolvido.

Não transferir ao cliente a investigação de KDS/fiscal/courier. Pendência que bloqueia sua promessa deve ser explicada sem stack trace, com responsável interno e próxima atualização/ação possível; o restante fica na operação canônica.

### C07 — Atendimento humano e contenção

Escape humano por texto simples/affordance deve funcionar sem IA, inclusive em falha ou limite. Posse humana local bloqueia mutações/saídas do bot e invalida turnos em voo; campo ManyChat é espelho de roteamento, não autoridade paralela.

Distinguir solicitação registrada de equipe disponível, conforme horário/SLA G03. No Live Chat existente, fornecer objetivo, escolhas, sessão/pedido, revisão, resultado conhecido/unknown, pagamento e próximo passo; cliente não reconta o histórico.

Retorno exige capacidade explícita, recibo, contexto reconciliado e sincronização comprovada; `view` não implica essa autorização. Falha remota conserva contenção local e gera alerta acionável. Kill switch bloqueia novas intenções e saídas não autorizadas, preservando reconciliação de efeitos comprometidos e seus registros.

### C08 — Canal, identidade, consentimento e IA

Adapter declara capacidades reais: texto/postback, limites de blocos, janela, templates, mídia, evento estável, receipt/consulta, handoff e força de identidade. Núcleo recebe envelope normalizado e emite blocos/Actions; adapter faz tradução. Conta+canal+subject compõem identidade de transporte. Mesmo ID numérico em outra conta/canal não é a mesma pessoa. Não forçar telefone para navegar; compra usa requisitos canônicos e vinculação aprovada, sem cadastro falso para contornar regra.

Prontidão multicanal significa uma segunda implementação **fake**, com subject não numérico, sem telefone, sem botões e sem recibo remoto, passando pelos mesmos contratos sem `if whatsapp` no domínio. Não significa instalar/ativar IG/Messenger. `source=manychat` sozinho não deve promover força de identidade de todos os canais; ampliar Doorman somente com evidência G04.

Consentimento transacional, aviso de disponibilidade e marketing são finalidades distintas. Mostrar disclosure apropriado na escolha pertinente e relacionar aceite ao registro canônico, respeitando revogação/recheck já existentes. Pedido de produto não vira opt-in de campanha. Dados do cliente e do modelo não podem sobrescrever prova de consentimento. Sem evidência suficiente, não gravar `verified`.

Modelo não cria preço, prazo, estoque, alergênicos, promessa comercial, URL, desconto, identidade ou autorização. Fatos críticos saem de blocos determinísticos com fonte/revisão; texto de ligação tem limites e fallback seguro. Inputs, tool results, nomes e mídia são dados não confiáveis, não instruções. Exigir testes de prompt injection e chamadas diretas de tools. Sem download automático de URLs de mídia. Áudio não suportado oferece alternativa e humano, sem loop de “digite tudo de novo”; transcrição só em escopo posterior aprovado.

Não fixar fornecedor/modelo/preço a partir de plano antigo. Avaliar modelo/configuração por corpus, qualidade, latência e custo por jornada resolvida; reduzir tokens não pode apagar contexto necessário. Minimizar PII enviada ao provedor e aprovar retenção/acesso/contrato em G04.

## 6. Jornadas e budgets de esforço

### 6.1 Como medir sem fabricar ganho

Vetor por jornada: **A** = ações deliberadas do cliente (envio, toque, escolha, confirmar; um envio com vários dados é uma ação); **U** = mensagens enviadas pelo cliente; **R** = campos conhecidos solicitados novamente; **M** = fatos que precisa memorizar/copiar entre contextos; **X** = trocas de superfície; **T** = tempo ativo do cliente; **W** = espera do sistema, medida separadamente. Registrar também falhas, dúvida sobre resultado e assistência necessária. Ler um resumo exige esforço: contar tempo de leitura e extensão, não apenas cliques.

Contar autenticação/pagamento exigidos, distinguindo custo inevitável de desperdício. Abrir banco para Pix pode exigir uma troca; não escondê-la para bater meta. Não exigir banco novo nem coleta de dados duplicada. Se identidade não é suficientemente comprovada, autenticação justificada não é “redigitação evitável”.

Os “antes” abaixo são caminhos atuais possíveis e/ou defeitos reproduzidos, **não médias de campo**. Números “depois” são budgets propostos para fixture definida. WP00 mede baseline humana com o mesmo roteiro; WP09 prova comparação. Nenhum percentual de melhoria é realizado nesta sessão.

| Jornada / fixture | Antes, evidência e esforço imposto | Depois contratado | Budget após implementação |
|---|---|---|---|
| J01 Comprar pedido simples: cliente identificado, 2 unidades, retirada/slot e Pix disponíveis | tools permitem montar/revisar; número de perguntas depende do modelo, sem budget comprovado; D04 | “Quero dois pães, amanhã ao meio-dia, Pix” monta o que for válido → resumo factual completo → uma confirmação → pedido/ação de pagar | até 3 A / 3 U antes do banco, R=0, M=0, X=0; T p90≤45s; Pix copiado sem memorizar |
| J02 “O de sempre”, pedido anterior inequívoco | `last_order` existe, mas quantidade fracionária é truncada; preço/disponibilidade precisam releitura | sugerir itens anteriores como rascunho, mostrar mudanças atuais; perguntar somente escolhas ausentes; confirmar resumo | até 3 A / 3 U quando defaults continuam válidos, R=0, M=0, T p90≤45s; não refazer compra automaticamente |
| J03 Entrega com endereço conhecido e mudança apenas de horário | endereço conhecido não garante reaproveitamento; D06 pode alterar entrega apesar do erro | propor endereço resumido, validar taxa/agenda; escolher horário válido sem repetir rua/número; diferença antes de confirmar | até 2 A adicionais à J01; R=0, M=0; dado novo informado uma vez |
| J04 Pausa e retomada: fechamento do app, 40+ mensagens, nova manhã | histórico limitado, nota pode encobrir inbound; cliente pode reconstruir contexto; D01/D17 | retomar sessão/pedido por ref, mostrar escolhas mantidas e mudança de validade; somente revalidar decisão afetada | 1 A para retomar + até 1 escolha se mudou; R=0, M=0; resumo ≤1 bloco essencial e ≤1 bloco de ação |
| J05 Cliente corrige quantidade enquanto turno está processando | T-D01: segunda entrada não consumida e sem pendência; insistência adicional necessária | correção permanece pendente; revisão velha não fecha; sistema mostra quantidade atual | zero mensagens extras para “acordar”; correção conta 1 A; zero inputs perdidos; uma confirmação da revisão final |
| J06 Cliente e site editam a mesma sacola/revisão | H02/H08 ainda sem prova PostgreSQL | conflito apresenta diferença e preserva intenção; escolha entre bases quando necessário, sem sobrescrever | até 1 A de resolução + confirmação se mudou compra; R=0, M=0; nenhum item sumido |
| J07 Confirmação enviada, resposta perdida após commit | T-D05: retry retorna no_cart apesar do pedido único | recibo resgata pedido exato e seu pagamento; pode responder a “deu certo?” sem recriar | 0 A de reparo quando recuperação automática é segura; no máximo 1 U de consulta; R=0, M=0; um Order por intenção |
| J08 Pedido criado, gateway ou mensagem Pix falha | pending_setup existe, mas D03 consome inbound e bool não descreve certeza | “Pedido registrado; pagamento ainda não disponível” + ação canônica de recuperar; retomar bloco faltante quando comprovadamente seguro | até 1 A para obter/consultar meio de pagamento, nenhum novo pedido; R=0, M=0; W/unknown explícitos |
| J09 Transferir sacola ao site com falha no segundo item/link | T-D12: origem abandonada e destino sem segundo SKU/slot | operação não conclui; origem preservada; retomar mesma transferência ou permanecer no chat | X=1 no sucesso; 0 redigitação de linhas/endereço/slot; até 1 A de retomada; conservação integral |
| J10 “Quero falar com alguém”, inclusive IA fora do ar | tool existe, mas resultado remoto ignorado; D08 | solicitação determinística, bot contido, resumo entregue à equipe quando disponível; retorno informado | 1 A / 1 U; R=0, M=0; cliente não resume histórico; prazo conforme G03 |
| J11 Acompanhar, pagar ou pedir cancelamento com dois pedidos | lista de três existe, link escolhe mais recente; erro pode virar “não achei”; D10/D15 | escolher pedido pelo contexto, Action canônica explica consequência e bloqueio; consultar falha sem perder alvo | 1 A comum; até 2 A com desambiguação, mais confirmação sensível requerida; M=0 números de pedido |
| J12 Produto indisponível/aviso, cliente opt-out | inscrição canônica existe; evidência do aceite não é exigida pela tool; D16 | oferecer substituto real ou aviso com finalidade/prazo/revogação, respeitando política atual; escolha não força compra | até 2 A incluindo aceite informado; R=0 telefone já comprovado; sem campanha/inscrição implícita |
| J13 Áudio, janela expirada ou capacidade ausente | fallback textual existe; envio pode presumir janela; D17/H04 | explicar limite uma vez; oferecer humano ou caminho equivalente; preservar o que já foi identificado | até 1 A para alternativa; não prender em sequência de falhas; X≤1 se escolher site |

Regras de linguagem: um bloco responde ao pedido atual; outro só quando necessário para resumo/ação ou Pix. Oferecer poucas escolhas contextuais, sem árvore de menus numéricos como fluxo obrigatório. Não pedir CPF, cadastro, endereço ou pagamento antes de precisar deles. Sugestão comercial nunca interrompe erro, recuperação, handoff ou confirmação; dispensar permanece dispensado no contexto válido.

### 6.2 Prova de ganho

Para cada J: mesma fixture, tarefa e ponto de partida, versões antes/depois, dispositivo, rede, transcrição redigida, ações, dados repetidos, tempo ativo/espera, erros e pergunta final ao cliente: “O pedido foi feito? Está pago? O que você faria agora?”. Resposta errada sobre compromisso/pagamento é falha crítica mesmo que tarefa tenha sido rápida.

Proposta para G06: 8–12 participantes diversos, incluindo pessoas pouco habituadas a comprar por chat e pessoas que usam recursos de acessibilidade; tarefas em ordem alternada para reduzir aprendizado. Pelo menos 30 execuções completas distribuídas entre compra, retomada e recuperação; cada cenário adversarial deve aparecer também em teste automatizado, sem provocar cobrança/risco real em participante. Publicar mediana, p90, extremos e amostra por jornada; amostra pequena não autoriza alegação estatística ampla.

Critério proposto: atingir budgets absolutos; onde baseline exceder budget, reduzir ≥30% de ações evitáveis ou T controlável, sem piorar outro componente relevante; onde baseline já for curta, preservar e corrigir recuperação. R=M=0 para informação conhecida, válida e autorizada; 100% dos cenários críticos locais com resultado entendido e sem efeito indevido. Mudança de budget exige justificativa G06, nunca relaxamento de invariante financeiro/identidade/consentimento.

## 7. Work packages e dependências sem ciclos

Cada pacote inclui teste que demonstra a falha relevante, implementação mínima, verificação de consumidores, telemetria de outcome e recuperação, migração/compatibilidade quando necessária e evidência de esforço da jornada. Um pacote não depende de piloto para concluir sua implementação técnica; ativação depende dos gates.

| WP | Prioridade / depende de | Entrega e fronteira | Aceite verificável / testes |
|---|---|---|---|
| WP00 — baseline e contratos | P0 / nenhuma | congelar SHA, mapa de writers/config/copy/flows, catálogo D/H/G, fixtures e baseline de esforço; portar diagnósticos para testes de regressão que exijam comportamento correto | referências atuais conferidas; cada H tem ensaio/owner; nenhum achado antigo tratado como fato; DB/runtime de testes identificado; C01–C08 vinculados a testes |
| WP01 — ingresso confiável | P0 / WP00 | C01; mensagem+trabalho atômicos, reparo por replay, ID íntegro, enriquecimento fora do ACK; allowlist explícita e enablement no ingresso | D02/D11 corrigidos; erro antes/depois do commit/replay/out-of-order/payload conflitante; nenhuma rede no ACK; lista vazia não amplia piloto; H04/H07 decididas por prova |
| WP02 — processamento e continuidade | P0 / WP01 | C02; consumo explícito por turno, claim/fence, continuação durável, recuperação de órfãos; referências mínimas do contexto | D01/D14/D17 corrigidos na parte de contexto; burst >5 loops termina sem nova mensagem; crash/lease vencido/double worker, clock rollover; nenhuma entrada perdida ou reconhecida indevidamente |
| WP03 — saída e certeza | P0 / WP02 | C03; persist-before-send, resultado estruturado do adapter, recuperação por bloco, janela/capability recheck; coordenação com notification existente | D03 corrigido; efeito remoto+resposta perdida permanece unknown; texto/Pix não truncados; retry seguro só quando comprovado; H01/H06 documentadas; nenhum status false→delivered |
| WP04 — autoridade de tools e compra | P0 / WP02 | C04; validação runtime, revisão completa, vínculo do aceite, CAS/fingerprint/recibo; refatoração mínima do writer canônico quando necessária | D04/D05/D06/D07/D13 corrigidos; review+place no mesmo turno sem nova confirmação recusado; retry resgata resultado; H02/H03 com PostgreSQL; parsing/factual renderer red-team |
| WP05 — continuidade com Storefront | P0 / WP03, WP04 | C05; alvo exato, transferência íntegra e recuperável, acesso contextual; preservar resgate/token/sessão existentes | D12/D15 corrigidos; falha em cada item/mint/resgate/retry; cart web existente e estoque exato; sem perda de quantidade/fulfillment ou elevação de identidade; H08 resolvida |
| WP06 — pós-compra e ações | P1 / WP03, WP04 | C06; consumir projeção e Actions completas, falha distinta de vazio, pedido/pagamento exatos, recuperação de falha parcial | D10 corrigido; H09/H06 resolvidas; payment pending/captured/cancelled/refund/expired; dois pedidos; callback atrasado e timeout; J07/J08/J11 dentro de budget |
| WP07 — humano e contenção | P0 / WP02, WP03 | C07; escape sem IA, handoff com fence/recibo, capacidade Admin explícita, alerta contextual e retorno seguro | D08/D09 corrigidos; assumir durante modelo/tool/send, API de campo False/unknown; kill-switch exercitado; view-only não muta se G03 assim aprovado; make admin se houver mudança |
| WP08 — canais, identidade e consentimento | P0 / WP01, WP03, WP04 | C08; adapter de capacidades e segunda implementação fake, identidade escopada, proof de aviso na inscrição existente; sem ativar canal novo | D16 corrigido; H05/H07 decididas; IDs colidentes, sem telefone, opt-out concorrente e link encaminhado; mesma suíte de núcleo passa com 2 adapters; nenhuma nova fonte de consentimento |
| WP09 — prova integrada e facilidade | P1 / WP05, WP06, WP07, WP08 | vertical completa, carga/fault injection, acessibilidade, corpus de conversas e placar J01–J13; runbooks revisados | todos P0 fechados tecnicamente; zero invariantes violados; PostgreSQL/Redis reais isolados; browsers e sandbox conforme gates; evidência de budgets sem métricas inventadas |
| WP10 — migração e ensaio de retorno | P0 de release / WP09 | executar ensaios expand/migrate e rollback em cópia sintética, compatibilidade worker/schema/flow, relatório de pendências e autoridade | schema misto e worker antigo cercado; nada replayado a partir de transcrição; rollback mantém recibos/Orders; reconstrução de observabilidade e atendimento provada |
| WP11 — piloto assistido | operacional / WP10 + G01–G07 aplicáveis | coorte allowlist explícita, ambiente/conta autorizados, suporte e medição humana; nenhum rollout implícito | budgets/clareza e SLO aprovados, 0 violação crítica, incidentes resolvidos, revisão humana documentada; piloto reprovado retorna a atendimento seguro |
| WP12 — rollout e estabilização | operacional / WP11 + nova aprovação G07 | ampliar coorte/capacidade somente após evidência; acompanhar janela comercial e reconciliação; remover legado só em gate de descarte | SLO e esforço sustentados, recibos/unknown com owner, nenhuma expansão por lista vazia; relatório e aceite humano final |

Ordem topológica válida: **00 → 01 → 02 → {03,04} → {05,06,07,08} → 09 → 10 → 11 → 12**. Na camada intermediária, respeitar dependências exatas da tabela. Telemetria/migração não são tarefas deixadas para WP10: cada WP as entrega; WP10 prova o conjunto. Trabalho independente pode ser planejado em paralelo, mas este documento não exige subagentes.

### Critério de encerramento de cada WP

Registrar SHA/arquivos, teste antes/depois, contrato e consumidores afetados, telemetria, recuperação e jornada beneficiada. Hipótese não confirmada vira evidência de preservação, não alteração artificial. Gate humano bloqueia ativação dependente, sem impedir testes sintéticos ou trabalho independente autorizado.

## 8. Testes e evidência exigidos

### 8.1 Resultados desta auditoria

- Núcleo concierge/transporte/Admin/webhook + projeção remota + ManyChat Guestman: **127 passed em 19,17s**; nove módulos listados no apêndice.
- Suites adicionais de recibos locais, fases duráveis, checkout/cliente/preço, AccessLink, proteção de marketing, aviso de estoque, erros e checkout concorrente: **99 passed e 3 skipped**, observados no lote combinado de 18,37s. Os três skips exigem PostgreSQL (row-lock de recibo, oversell e captura concorrente); não contam como validação desses invariantes.
- Diagnósticos temporários finais: **13 passed em 17,49s**, verificando o comportamento defeituoso descrito, e não aprovando-o. Um primeiro lote acusou erro no próprio diagnóstico de transferência (`Session.status` em vez de `state`); corrigido apenas no arquivo temporário e os 13 repetidos. Não esconder esse erro como defeito do produto.
- Total de testes existentes aprovados selecionados: 226; diagnósticos distintos: 13; 3 skips existentes. Não somar reruns para inflar cobertura. Não houve teste real de delivery, carga, PostgreSQL ou medição de esforço humano.

### 8.2 Matriz adversarial mínima do candidato

| Camada | Ensaios obrigatórios | Oráculo de aceite |
|---|---|---|
| Envelope/auth | ausência/rotação de chave, HMAC onde aplicável, conta trocada, ID longo/igual com payload diferente, JSON escalar/lista, Unicode, tamanho, rate limit e evento sem ID | nenhuma mutação não autenticada; replay estável; indisponibilidade explícita; sem vazamento de payload |
| Ingresso/fila | crash antes de persistir, entre mensagem e agendamento, após commit antes do ACK; dois deliveries iguais; mensagens fora de ordem e bursts | evento aceito com caminho recuperável; dedupe não elimina fala legítima; nenhum trabalho depende de nova fala |
| Turno | entrada durante geração, nota/handoff concorrente, >5 loops, worker morto/claim vencido, dois workers e turn counter diário | associação exata de entradas; stale fence não muta/envia; recuperação justa e finita |
| Ferramentas | argumentos inválidos, bool/NaN/infinito/decimal/negativo, SKU ambíguo, remove explícito, endereço não localizado, slot inválido | validação sem escrita; unidade e dinheiro canônicos; erro explica dado faltante sem expor exceção |
| Review/commit | confirmar antes de recap, dois “sim”, “sim, mas…”, revisão trocada, fee/cupom/preço/slot/estoque mudando, payload divergente mesma key | somente intenção autorizada; total final igual à revisão aceita ou conflito; recibo estável; um pedido |
| PostgreSQL | conexões independentes com barreiras: modify/commit, confirm/edit, último estoque, callback/cancel, handoff/tool, transfer/site edit, revoke/send | invariantes de conservação, autorização e CAS; perdedor recebe conflito/estado atual; sem lost update ou deadlock sem recuperação |
| Saída/provider fake | 429/5xx, falha antes do efeito, efeito+timeout, processo morto antes/depois de persistir resultado, Pix como segundo bloco falha | unknown preservado; nenhum retry cego; blocos aceitos não reenviados; não dizer entregue sem receipt |
| Pagamento/lifecycle | commit OK+gateway fail, callback duplicado/tardio, pago após cancelamento, deadline/clock vencido, produção/fiscal/courier parcial | core preservado; pedido/pagamento/efeitos distintos; nenhuma recobrança para recuperar resposta; alertas com objeto/owner |
| Site/identity | token usado/expirado/encaminhado, browser com cookie antigo, dois carrinhos, fail segundo item/mint, novo canal sem telefone | contexto não perdido; ownership antes do receipt/link; sem promoção de confiança indevida; conservação de holds |
| Consentimento | disclosure ausente, inscrição idempotente, pedido de aviso vs campanha, opt-out antes de envio, revogação concorrente e expiração | inscrição sem prova não verified; recheck canônico; nada enviado fora da finalidade autorizada |
| IA | prompt injection em cliente/nome/produto/tool result; preço/urgência/alérgeno inventado; tool clandestina; preâmbulo antes de fatos | zero fato crítico inventado e zero efeito sem autoridade; fallback conserva contexto e escape humano |
| Canal/capabilities | WA fake + canal fake sem botões/sem telefone/sem receipt, expiração de janela enquanto em fila, mídia/links longos | sem regra de canal no domínio; degradação explícita e utilizável; nenhuma capacidade presumida |
| UX/acessibilidade | mobile 320/390px, tamanho de texto ampliado, leitor de tela, baixa conectividade, retorno do banco, webview/browser e J01–J13 | códigos/valores/prazos legíveis e copiáveis, ações nomeadas, nenhuma dependência de cor/emoji ou memória; budgets medidos |

SQLite prova lógica/fixtures e alguns interleavings injetados; **não prova locks reais**. PostgreSQL+Redis isolados são gate técnico obrigatório, com schemas/namespaces próprios e sem anexar servidor de terceiro. Tests que só verificam “contador ≥1” não provam execução única; inspecionar Orders, receipts, intents, reservas, efeitos e saídas no oráculo.

Se frontend/BFF for alterado, executar testes/typecheck/build das superfícies afetadas, encaminhamento de identidade/headers de idempotência e browser integrado sem mocks do domínio. Se Admin mudar, `make admin` integral, browser e permissões; não substituir com check scoped. Não executar checks irrelevantes só para aumentar contagem. Comandos novos precisam existir e ser validados antes de serem reportados como executados.

### 8.3 Fontes do contrato externo

ManyChat documenta timeout de **10s** para chamadas de Dev Tools e restrições de mapeamento de resposta; isso fundamenta ACK curto, mas não prova comportamento da conta específica. [Dev Tools Basics](https://help.manychat.com/hc/en-us/articles/14281252007580-Dev-Tools-Basics), consultado em 11/09/2026.

External Request permite configurar cabeçalhos/corpo e mapear resposta; não inferir daí assinatura HMAC, ID estável ou idempotência do envio. [External Request](https://help.manychat.com/hc/en-us/articles/14281285374364-Dev-Tools-External-request), consultado em 11/09/2026.

A documentação descreve janela de automação de 24h e diferenças entre WhatsApp e atendimento manual em Instagram/Messenger; fora da janela WhatsApp há regras de templates. Revalidar política/capacidade na execução e na homologação. [Messaging windows](https://help.manychat.com/hc/en-us/articles/23358636027932-Understanding-messaging-windows), atualizado em 27/08/2026, consultado em 11/09/2026. Não usar a janela manual de outro canal como autorização para bot.

## 9. Observabilidade, budgets de serviço e recuperação

Metas iniciais propostas, sujeitas a G06 e à carga medida. Medir desde a entrada do cliente até a evidência disponível; separar aceitação local, geração, provider e chegada efetiva quando mensurável.

| Indicador | Budget inicial | Ação quando violado |
|---|---|---|
| ACK durável | p95≤500ms; p99≤2s; sem dependência de rede externa | investigar saturação e reduzir admissão automática; não responder sucesso antes de commit |
| Primeira resposta útil | p95≤8s no fluxo sem gateway; aos 10s oferecer estado de andamento se canal permitir sem ruído | distinguir fila/modelo/provider; mensagem “processando” só se registrada e de fato pendente |
| Atualização após fato canônico | p95≤5s para tornar próxima ação consultável; envio medido separadamente | preservar consulta segura; alertar atraso de fila, sem produzir falso estado novo |
| Idade de entrada sem turno | alvo≤30s; alerta após limite aprovado | recuperar Directive órfã; nada de pedir ao cliente para repetir |
| Unknown de envio/efeito | 100% com owner; triagem inicial≤2min durante atendimento acordado | reconciliar evidência ou atendimento humano; nunca resolver mudando estado para sucesso |
| Contexto e integridade | zero entradas perdidas, compras/valores não autorizados, PII cruzada, opt-in falso, perda silenciosa de item | conter capacidade afetada e interromper expansão, independentemente dos percentis |
| Esforço | J01–J13 e R/M evitáveis zero | reprovar piloto do fluxo; abrir correção vinculada ao passo que impôs trabalho |
| Custo IA | tokens/custo por jornada resolvida, fallback e repetições, teto por conversa/conta aprovado | manter caminho determinístico/humano; não ocultar limite como indisponibilidade comercial |

Carga técnica inicial: 100 conversas ativas sintéticas, bursts de 10 entradas numa conversa, duas contas com subjects iguais, duas conexões por conflito, 10 mil mensagens de histórico; ampliar para pico observado×2 em G06. Números são cenários de ensaio, não capacidade certificada. Registrar queries, locks, deadlocks, memória, tamanho de payload, tempo de fila, retries e latência por estágio.

Logs/traces: correlação técnica restrita entre evento→turno→intenção→recibo→sessão/pedido→Directive→saída, versões de contrato/modelo/policy, resultado/código e fence. Métricas usam labels limitadas de canal/outcome/tipo, nunca telefone, subscriber, conteúdo, SKU arbitrário, ref de pedido ou token. Não registrar chave API, AccessLink, Pix completo, endereço nem prompts crus em telemetria geral. Transcrição existente recebe controle/retenção G04, não autorização ilimitada para novo dataset.

Alertas acionáveis nas superfícies existentes: objeto exato, último fato confirmado, incerteza, owner, próximo comando permitido, idade e link. Reconhecer alerta não resolve causa; encerramento vinculado a evidência. Para o cliente: mensagem curta com resultado e caminho. Para suporte: contexto técnico mínimo sem exigir que o cliente explique incidentes.

Runbooks obrigatórios, cada um com diagnóstico somente leitura, efeito conhecido/unknown, ações permitidas/proibidas, escalada, reconciliação e encerramento:

1. Evento aceito sem processamento: localizar receipt/Message/Directive; reparar trabalho durável, sem inserir outra entrada.
2. Saída unknown: consultar evidência do provider quando disponível; conter retry; preservar resposta lógica e pedido.
3. Pedido criado sem Pix/link: consultar Order/Payman e recuperar intent canônico; não repetir commit nem pedir novo pedido.
4. Conflito de revisão/estoque/transferência: mostrar diferença e preservar origem; nunca “corrigir” estoque para fechar conversa.
5. Handoff ou kill switch: impedir bot localmente, sincronizar campo, atribuir atendimento e retomar com fence novo.
6. Janela/credencial/provider indisponível: respeitar política do canal, comunicar caminho autorizado e manter pendências; sem fallback para outro contato não autorizado.
7. Identidade/consentimento conflitantes: bloquear só capacidade sensível, preservar navegação/rascunho e encaminhar validação canônica.
8. Rollback: conter admissão, inventariar efeitos, drenar/reconciliar e manter recibos; proibir replay em massa de transcrições.

## 10. Migração e rollback

### 10.1 Expandir, migrar, contrair

1. Inventário **somente leitura em ambiente expressamente autorizado**: conversas por estado, mensagens sem ID, entradas aparentemente pendentes, diretivas queued/running/failed, refs de sessão/pedido, bool delivered legado e handoff local/remoto. Não inferir entrega pelo bool histórico nem consentimento pela existência de texto.
2. Expandir modelos existentes com campos/índices mínimos de envelope, consumo/turno, revisão, posse e resultado. Constraints novas depois de backfill verificável. Avaliar modelo auxiliar apenas se Message/Directive/IdempotencyKey não representarem relação necessária; justificar dono/retenção e provar ausência de fonte paralela.
3. Mapper legado explicita provider/conta configurados, canal conhecido e nível de evidência. IDs históricos sem prova ficam `legacy_unverified`; delivered antigo fica evidência legada, não receipt remoto. Não fabricar confirmação de compra ou consentimento a partir de resumo/histórico.
4. Pendências ambíguas não são disparadas automaticamente. Vincular pedidos por chave/sessão/recibo existente quando inequívoco; restantes entram em reconciliação humana com motivo. Não criar pedido, pagamento, notificação ou inscrição no backfill.
5. Compatibilidade de workers: reader tolera esquema anterior; writer novo só assume coorte/versionamento explícito. Worker antigo não pode consumir tópico/envelope novo sem fence de versão. Não criar duas filas para contornar isso; usar roteamento/versionamento no mecanismo existente.
6. Flow ManyChat versionado/exportado com payload e respostas de status, rota de humano, fallback de erro e campo de handoff. Testar mensagem real em sandbox autorizada e registrar artefato/hash antes de publicação. Não mudar Default Reply global durante piloto fechado.
7. Ativar gradualmente somente depois dos gates. Remoção de campos/branches de compatibilidade e descarte de dados são outra aprovação G04/G07 após janela de retorno definida; não definir prazo legal/comercial unilateralmente.

### 10.2 Rollback operacional é contenção, não desfazer venda

Gatilhos: qualquer compra/valor não autorizado, PII cruzada, consentimento falso, perda de entrada/contexto, duplicação financeira, promessa falsa crítica ou incapacidade de operar handoff; também SLO/budgets persistentemente violados conforme G06.

Procedimento ensaiado: desabilitar novas intenções automáticas da coorte afetada; invalidar turnos por fence; bloquear saídas não autorizadas; manter consulta de recibos, reconciliação e core de pedidos/pagamentos. Encaminhar atendimento pelo caminho existente aprovado. Capturar inventário de ordens, intents, Messages e Directives em execução; confirmar estado do lado remoto antes de qualquer retry. Reverter aplicação/flow apenas para versão compatível com schema expandido; manter leitura/recuperação nova se a versão antiga não entender unknown. Se não houver binário compatível, conter e corrigir adiante, sem downgrade destrutivo.

Não apagar recibos/fila/histórico, não devolver estoque/pagamento por rollback de software, não reenviar todas as respostas. Compensação comercial usa Action/serviço canônico e autoridade própria. Cliente com pedido já feito continua recebendo estado verdadeiro e atendimento. Só retomar após teste do defeito, reconciliação de pendências, revisão humana e nova autorização de etapa.

## 11. Gates humanos e etapas de operação

O plano propõe decisões concretas; não presume aprovação. Enquanto pendentes, desenvolver mecanismos com fixtures e flags desativadas, preservando política vigente. Não parar correção técnica segura para perguntar escolha já decidida pela sessão/repositório.

| Gate / responsável a nomear | Decisão e evidência | Bloqueia |
|---|---|---|
| G01 Produto + dono do canal | coorte explícita, conta, finalidade, lista não vazia, regra de entrada/humano e escopo comercial do piloto | qualquer admissão/alteração real de flow; não bloqueia código/testes |
| G02 Integrações + dono ManyChat | event_id estável, conta/canal, ACK 200/202, limites/receipts/consulta/idempotência, janela e handoff comprovados em sandbox | envio/compra automática real se contrato insuficiente; canais novos têm gate próprio |
| G03 Atendimento + Segurança | quem assume/devolve, permissões, horários/SLA, o que dizer fora do expediente e como tratar unknown | autoridade nova e piloto humano; não inventar promessa de atendimento imediato |
| G04 Privacidade/Segurança + responsável de dados | identidade/vinculação crosschannel, força de autenticação, PII/modelo, retenção/acesso/descarte e evidência de consentimento | novos dados/uso real, promoção de confiança e remoção posterior de legado |
| G05 Produto + Operações comerciais | significado de “continuar no site”, conflito de carrinhos, exposição de diferença de canal/preço, validade comercial da revisão | ativação da transferência/política alterada; manter defaults canônicos até decisão |
| G06 Produto/UX + SRE/Operações | baseline, budgets, personas/dispositivos, amostra, carga, SLO, limite de custo e critérios de parada | início/aceite do piloto e expansão; não reduzir invariantes |
| G07 Dono do ambiente + responsável técnico/Operações | release SHA, alvo, backup, rollback, suporte, janela e autorização explícita de cada etapa | deploy, migração, envio, cobrança, reconciliação ou alteração em ambiente real; aprovação do plano não supre isso |

**Implementação técnica:** WP00–WP10, testes locais/CI/ambiente isolado, fakes e artefatos revisáveis. Conclusão técnica não é sucesso do piloto.

**Homologação controlada:** contrato de fornecedor e ponta a ponta em conta/número sandbox autorizados, sem cliente real nem pagamento real salvo autorização específica. Confirmar intake→worker→saída→ação/site e retorno; testar fluxo manual quando bot está contido. Não equivale a rollout.

**Piloto assistido:** WP11, proposta de 5–10 clientes convidados/identificados explicitamente, acompanhamento durante horário acordado, mínimo de 30 jornadas e cenários de recuperação em ambiente apropriado. Amostra/coorte finais em G01/G06. Executar por janela comercial suficiente para observar expiração/interrupção e retorno; não liberar por simples passagem de dias.

**Rollout:** WP12, ampliação proposta em coortes 10%→25%→50%→100% dos elegíveis, cada transição com relatório e nova aprovação G07; denominador, duração e volumes mínimos em G06. Se volume for pequeno, usar contagem explícita em vez de percentual enganoso. Zero P0 aberto, budgets atendidos e unknown triado antes de expandir. Instagram/Messenger não são etapas automáticas desse rollout.

## 12. Definition of Done

**Esta sessão:** plano e prompt entregues; base/referências identificadas, D/H/G separados, diagnósticos documentados e isolamento preservado. Implementação, piloto e rollout permanecem pendentes.

### Implementação técnica futura

- [ ] D P0/P1 resolvidos; retirada de achado exige evidência na nova base. Hipóteses permanecem identificadas até ensaio.
- [ ] C01–C08 aprovados pelos testes da seção 8, com consumidores reais; PostgreSQL/Redis comprovam concorrência, sem usar skips como aprovação.
- [ ] WPs00–10 encerrados pelo critério da seção 7, preservando M01–M09 e a propriedade dos fatos.
- [ ] J01–J13 verificadas nas camadas autorizadas; medições humanas ou de fornecedor pendentes são declaradas, sem alegar ganho em campo.
- [ ] Observabilidade/runbooks da seção 9 e migração/rollback da seção 10 comprovados por artefatos, SHA, comando, resultado e responsável.

### Piloto e rollout futuros

- [ ] Gates da seção 11 aprovados nominalmente para ambiente/coorte e etapa correspondentes.
- [ ] Budgets e entendimento do cliente comprovados: menos esforço/erro, resultado e próximo passo claros, sem falha crítica.
- [ ] Reconciliação encerrada ou pendência com responsável/prazo; expansão bloqueada por incidente crítico.
- [ ] Rollout e descarte de legado aprovados separadamente, com acompanhamento e rollback disponíveis.

## Apêndice A — Reprodução local e manifesto

A suite temporária abaixo afirma comportamentos defeituosos da base auditada. Ao implementar, transformar cada teste em regressão do comportamento correto; não mantê-la verde exigindo o defeito. Fixtures importadas pertencem ao SHA auditado. Nenhum contato de fixture deve receber envio real.

Comando usado para a suite diagnóstica (runtime já existente do workspace original, imports dos packages reposicionados pelo runner):

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python /tmp/conversational-audit-20260911/run.py /tmp/conversational-audit-20260911/test_diagnostics.py -rs
```

Executar a partir do worktree auditado. Os arquivos temporários não são dependência permanente do plano: seus conteúdos estão reproduzidos a seguir.

### Runner utilizado

```python
from pathlib import Path
import os,sys
root=Path.cwd()
sys.path[:0]=[str(root),*[str(p) for p in sorted((root/'packages').iterdir()) if p.is_dir()]]
os.environ['DJANGO_SETTINGS_MODULE']='config.settings_test'
os.environ['DATABASE_URL']=''
os.environ['REDIS_URL']=''
os.environ['AI_ASSIST_API_KEY']=''
os.environ['SHOPMAN_CONCIERGE_ENABLED']='false'
import shopman.orderman, shopman.guestman
print('AUDIT_IMPORTS',list(shopman.orderman.__path__),list(shopman.guestman.__path__))
import pytest
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider','-c',str(root/'pyproject.toml'),*sys.argv[1:]]))
```

### Diagnósticos T-D01–T-D13

```python
"""Diagnostic assertions of current defects, NOT acceptance of desired behavior."""
from datetime import timedelta
import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.storefront.tests.test_concierge_engine import (surface, customer, conversation, ctx, outbox, _pickup_ready, _tomorrow, SKU, CONCIERGE_SETTINGS)
from shopman.storefront.concierge import service, tools, agent
from shopman.shop.models import Conversation, ConversationMessage as Message
from shopman.orderman.models import Order, Session
pytestmark = pytest.mark.django_db

def inbound(c, text='Quero pão', ext='in-1'):
    return Message.objects.create(conversation=c,role=Message.Role.USER,kind=Message.Kind.INBOUND,text=text,content=[{'type':'text','text':text}],external_id=ext)

def test_d01_message_during_turn_is_hidden(conversation,outbox,monkeypatch):
    first=inbound(conversation)
    late=[]
    def respond(**kwargs):
        late.append(inbound(conversation,'Na verdade, três','in-2'))
        return agent.AgentOutcome(reply_text='Dois pães na sacola.')
    monkeypatch.setattr(agent,'run_agent',respond)
    result=service.run_turn(conversation.pk)
    assert result.processed_message_ids==[first.pk]
    assert late[0].pk not in result.processed_message_ids
    assert not result.pending_more and not service.unanswered_inbound(conversation)

@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS,AI_ASSIST_API_KEY='fake')
def test_d02_intake_failure_cannot_requeue_by_replay(conversation,monkeypatch):
    def fail(c): raise RuntimeError('injected enqueue failure')
    monkeypatch.setattr(service,'_enqueue_turn',fail)
    with pytest.raises(RuntimeError):
        service.receive_inbound(subscriber_id=conversation.subscriber_id,text='Olá',external_id='durable-1')
    assert conversation.messages.filter(external_id='durable-1').exists()
    assert service.receive_inbound(subscriber_id=conversation.subscriber_id,text='Olá',external_id='durable-1').reason=='duplicate'

def test_d03_failed_send_consumes_inbound(conversation,monkeypatch):
    inbound(conversation)
    monkeypatch.setattr('shopman.storefront.concierge.transport.send_text',lambda *a:False)
    message=service._send_reply(conversation,'Resposta')
    assert message.delivered is False
    assert not service.unanswered_inbound(conversation)

def test_d04_order_without_customer_confirmation(ctx):
    quote=_pickup_ready(ctx)
    assert ctx.conversation.messages.count()==0
    result=tools.place_order(ctx,quote['quote_token'],'pix')
    assert result['ok'] and Order.objects.filter(ref=result['order_ref']).exists()

def test_d05_repeat_order_loses_receipt(ctx):
    quote=_pickup_ready(ctx)
    first=tools.place_order(ctx,quote['quote_token'],'pix')
    second=tools.place_order(ctx,quote['quote_token'],'pix')
    assert first['ok'] and second['error']=='no_cart'
    assert Order.objects.count()==1

def test_d06_invalid_fulfillment_partially_writes(ctx):
    assert tools.set_item(ctx,SKU,2)['ok']
    session=Session.objects.get(session_key=ctx.conversation.session_key)
    session.data={**session.data,'fulfillment_type':'delivery','delivery_address':'Rua de Teste, 1','delivery_address_structured':{'formatted_address':'Rua de Teste, 1'}}
    session.save(update_fields=['data'])
    result=tools.set_fulfillment(ctx,'pickup',_tomorrow(),'invalid-slot','')
    session.refresh_from_db()
    assert not result['ok'] and result['error']=='validation'
    assert session.data['fulfillment_type']=='pickup'
    assert 'delivery_address' not in session.data

def test_d07_negative_quantity_removes(ctx):
    assert tools.set_item(ctx,SKU,2)['ok']
    result=tools.set_item(ctx,SKU,-1)
    assert result['ok'] and result['removed']==SKU


def test_d08_remote_handoff_failure_ignored(conversation,monkeypatch):
    conversation.state=Conversation.State.HANDOFF
    conversation.save(update_fields=['state'])
    monkeypatch.setattr('shopman.storefront.concierge.transport.set_handoff',lambda *a:False)
    assert service.return_to_concierge(conversation) is None
    conversation.refresh_from_db()
    assert conversation.state==Conversation.State.ACTIVE

@override_settings(SHOPMAN_CONCIERGE={**CONCIERGE_SETTINGS,'enabled':False})
def test_d09_worker_ignores_disabled_switch(conversation,outbox,monkeypatch):
    inbound(conversation)
    called=[]
    monkeypatch.setattr(agent,'run_agent',lambda **kw:called.append(True) or agent.AgentOutcome(reply_text='Ainda respondo'))
    assert not service.is_enabled()
    service.run_turn(conversation.pk)
    assert called==[True] and outbox.sent==['Ainda respondo']


def test_d10_projection_failure_becomes_not_found(ctx,monkeypatch):
    quote=_pickup_ready(ctx)
    order=tools.place_order(ctx,quote['quote_token'],'pix')
    def fail(*a,**kw): raise RuntimeError('projection unavailable')
    monkeypatch.setattr('shopman.shop.services.conversation.build_order_conversation',fail)
    result=tools.order_status(ctx,order['order_ref'])
    assert result['ok'] and not result['orders'] and 'Não achei' in result['message']


def test_d11_fallback_event_identity_collision_and_drift(monkeypatch):
    now=timezone.now().replace(second=10,microsecond=0)
    monkeypatch.setattr(service.timezone,'now',lambda:now)
    first=service._external_id('subscriber','sim','')
    assert first==service._external_id('subscriber','sim','')
    monkeypatch.setattr(service.timezone,'now',lambda:now+timedelta(minutes=1))
    assert first!=service._external_id('subscriber','sim','')

def test_d12_partial_web_transfer_abandons_source(ctx,monkeypatch):
    from decimal import Decimal
    from shopman.offerman.models import Product,Listing,ListingItem,Collection,CollectionItem
    from shopman.storefront.tests.test_concierge_engine import _seed_stock
    from shopman.shop.services import cart
    p=Product.objects.create(sku='SEGUNDO',name='Segundo produto',base_price_q=100,is_published=True,is_sellable=True)
    CollectionItem.objects.create(collection=Collection.objects.first(),product=p,sort_order=2)
    for listing in Listing.objects.all(): ListingItem.objects.create(listing=listing,product=p,price_q=100,is_published=True,is_sellable=True)
    _seed_stock('SEGUNDO',Decimal('10'))
    assert tools.set_item(ctx,SKU,2)['ok']
    assert tools.set_item(ctx,'SEGUNDO',2)['ok']
    assert tools.set_fulfillment(ctx,'pickup',_tomorrow(),'slot-12','')['ok']
    source=Session.objects.get(session_key=ctx.conversation.session_key)
    original=cart.add_item
    def add(**kw):
        if kw['sku']=='SEGUNDO': raise RuntimeError('injected failure for second item')
        return original(**kw)
    monkeypatch.setattr(cart,'add_item',add)
    web_key=tools._copy_cart_to_web(ctx)
    source.refresh_from_db()
    web=Session.objects.get(session_key=web_key)
    assert source.state=='abandoned' and ctx.conversation.session_key==''
    assert [i['sku'] for i in web.items]==[SKU]
    assert not web.data.get('delivery_time_slot')


def test_d13_model_unfounded_price_is_forwarded(conversation,outbox):
    from shopman.storefront.tests.test_concierge_engine import ScriptedClient,_response,_text
    inbound(conversation,'Quanto custa o pão?')
    client=ScriptedClient(_response(_text('O Pão Francês custa R$ 999,99.'),stop_reason='end_turn'))
    result=service.run_turn(conversation.pk,client=client)
    assert 'R$ 999,99' in outbox.sent[0] and not result.fallback
```

### Módulos existentes executados

Primeiro lote (127 passed):

```text
shopman/storefront/tests/test_concierge_engine.py
shopman/storefront/tests/test_concierge_handler.py
shopman/storefront/tests/test_concierge_webhook.py
shopman/storefront/tests/test_concierge_transport.py
shopman/storefront/tests/test_concierge_admin.py
shopman/shop/tests/test_remote_conversation_projection.py
packages/guestman/shopman/guestman/tests/test_manychat.py
packages/guestman/shopman/guestman/tests/test_manychat_consent_sync.py
packages/guestman/shopman/guestman/tests/test_manychat_resolver.py
```

Segundo lote (99 passed, 3 skipped; diagnósticos rodaram junto no ensaio inicial):

```text
shopman/shop/tests/test_remote_mutations.py
shopman/shop/tests/test_lifecycle_phase_durability.py
shopman/shop/tests/test_checkout_side_effects.py
shopman/shop/tests/test_checkout_customer_link.py
shopman/shop/tests/test_cart_context_pricing.py
shopman/shop/tests/test_access_link_handoff_e2e.py
shopman/shop/tests/test_manychat_marketing_safety.py
shopman/storefront/tests/test_stock_alerts.py
shopman/storefront/tests/test_concurrent_checkout.py
shopman/storefront/tests/test_checkout_error_paths.py
```

Rodados pelo mesmo runner, passando os caminhos como argumentos. O resultado combinado inicial foi `1 failed, 111 passed, 3 skipped`; a falha era do diagnóstico T-D12 e foi corrigida/reexecutada como descrito na seção 8.1.

### Manifesto complementar de leitura

| Arquivo | Linhas | SHA-256 |
|---|---:|---|
| `STOREFRONT-EXCELLENCE-HARDENING-PLAN.md` | 231 | `aacdbddbe846c7b01785492bba9e51ac55ecfbb96339a2b89eddca7f3d85d7a1` |
| `MANYCHAT-CONVERSACIONAL-PLAN.md` | 94 | `a2339ad1f941ecde89d397f54165902c1c77915e9063feb4d8c653c33d7c3501` |
| `WHATSAPP-CONCIERGE-PLAN.md` | 244 | `2feb7bda22bd63374618bc8ad542e3c8c1213b6d969264ec1184f87e66d0f2a4` |
| `adr-009-whatsapp-via-manychat.md` | 174 | `93dad01fe5706b5c9889dfa3cdc80dd354e66f16e7d5bac89f135a5bf750fc47` |
| `adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md` | 109 | `deca669184b6d2a1bc30d9583b93c29b45ac85876e9bdecaef386448ab9724db` |
| `manychat-conversation-projection.md` | 69 | `0eb6d7c1770f6fcc8b42e15ee32c21e90ec4829a777db52b6e693647aa6074f5` |
| `whatsapp-concierge.md` | 215 | `87c4e214d9aabf04d667d4329bed450eda7a9559546fe9ea6755b9cc9d430f32` |
