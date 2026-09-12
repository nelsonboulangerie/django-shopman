# ManyChat: fluxo canônico da Concierge

Decisão de direção solicitada pelo operador em12/09/2026: simplicidade nativa e integração canônica; manter WhatsApp como primeiro canal, preparar extensão posterior à DM Instagram. Complementa C01/C03/C07/C08 e gates do plano de excelência, não os substitui.

## Estado comprovado

- Publicado: corev2 e compatibilidade leitura/humano, SHAed9a0d6dc, coorte restrita, compra/identidade/transferência/retry/retorno contidos.
- Flow antigo: keyword#c e External Request no endpoint existente; corpo com subscriber_id/text/first_name/last_name. Não há export do grafo nem prova de continuidade após keyword.
- Operador confirmou campo dinâmico de última interação WhatsApp e fusoUTC-03SaoPaulo. CorreçãoPR622 interpreta o timestamp mediante opt-in e passou95testesPG locais. Ainda não publicada; auto-merge suspenso para consolidar desenho.
- ID estável do evento continua sem fonte comprovada. ContactID e última interação não o substituem. A fixture manychat-conversation-v2.json é contrato local, não export de flow ou prova de capacidade do fornecedor.
- read_only atual oferece catálogo/orientação/humano determinísticos; não é a experiência conversacional completa do agente. Remover read_only não torna o ingresso legado apto a compras.

## Desenho escolhido

ManyChat contém somente trigger, roteamento técnico e atendimento humano. O coreShopman conserva Message/Conversation/Directive, contexto, modelo, ferramentas, verdade comercial, ações e receipts. Não acrescentar n8n, fila paralela, carrinho em custom fields ou motor de diálogo no ManyChat.

Um flow de ingresso por canal normaliza transporte e encaminha ao mesmo núcleo; uma única implementação das regras no Shopman. WhatsApp e Instagram mantêm identidade escopada por provider+conta+canal+subject. Não unir contatos pelo nome ou exigir telefone para navegação; vinculação comercial segue gate próprio.

### Entrada e continuidade

Usar o Default Reply nativo, configurado para cada mensagem, roteando somente a coorte de teste e preservando atendimento das demais pessoas. Keyword#c pode iniciar a experiência de teste, mas cada mensagem subsequente precisa chegar ao mesmo ingresso sem exigir prefixo. Não criar loop de pergunta/Data Collection só para manter a conversa viva.

Antes de modificar Default Reply, inspecionar a automação existente, suas keywords concorrentes, condição de humano e ordem de triggers. Nenhuma substituição global ou expansão automática da coorte. O mecanismo técnico de roteamento de teste deve refletir a autorização canônica; não virar segunda política comercial.

### Requisição e resposta

External RequestHTTPSPOST no endpoint existente, autenticação existente, JSON com escaping correto para aspas/quebras de linha. Texto deve ser fotografado no disparo; não buscar getInfo para substituir a mensagem recebida. Conta e canal vinculados à configuração autenticada; IDs de contato sempre string.

Envelope lógico: versão, provider, conta, canal, subject, texto/tipo, eventID quando realmente disponível, instante do evento quando realmente disponível, última interação do canal em campo semanticamente distinto, receivedAt servidor e autenticação. Não promover lastInteraction a eventTimestamp/confirmation. O mapeamento exato deve usar campos reais do seletor/preview, sem inventar placeholders de fornecedor.

ACK200 confirma persistência/fila, sem mensagem de cliente ou resultado comercial. Worker produz e persiste blocos antes de enviar pelo adapterManyChat. Não manter requisição aberta aguardando o modelo, nem mapear ACK para campo de resposta e enviá-lo ao cliente. Uma única via de saída preserva prepared/accepted/unknown e evita resposta duplicada entreflow eworker. DynamicBlock não é o executor do turno assíncrono planejado.

### Humano

Atendimento permanece no ManyChatInbox; campo concierge_handoff espelha o estado canônico. Mensagens recebidas durante handoff preservam contexto, sem bot competindo. Retorno ao bot é explícito e condicionado à autoridade/sincronização já previstas. Inspecionar pausa nativa e fluxo de atribuição antes de mudar configuração.

### Identidade de evento: decisão ainda bloqueada

As referências consultadas descrevem ContactID/LastTextInput/LastInteraction, mas não comprovam ID estável de mensagem no ExternalRequest deste flow. Para mutações automáticas, homologar evento original e comportamento de retry/burst. Não gerar UUID a cada execução, contador mutável ou hash de texto/data como substituto.

Se a integração nativa não expuser essa evidência, registrar limitação do fornecedor e escolher conscientemente o boundary: manter leitura/orientação e confirmação comercial pelo Storefront canônico, ou avaliar contrato oficial de ingresso por evento compatível com a conexãoManyChat existente. Não ativar Meta direto em paralelo por hipótese. A escolha depende de evidência real e autorização para alteração do canal.

## Instagram depois

Reutilizar core/contratos, implementar adapterManyChatInstagram e configurar ingressoDM próprio. Não trocar apenas stringwhatsapp porinstagram na configuração atual: validar escopo de identidade, credenciais, formato de saída, janela, mídia, handoff e retomada. DefaultReplyInstagram pode excluir respostas aStories; DM é a primeira fatia proposta. Coorte e ativação separadas, explicitamente autorizadas depois. O fusoWA confirmado não é automaticamente o fusoIG; obter amostra real por canal.

## Homologação necessária

1. Export/capturas do grafo atual e configuração DefaultReply; registrar origem de cada campo.
2. Três mensagens rápidas com aspas/quebra de linha: texto exato, nenhuma perda ou repetição indevida; reexecução técnica reconhecida quando há ID.
3. Resposta real pelo worker, accepted separado de entrega observada no aparelho.
4. Humano assume, mensagem continua sendo preservada, bot para; retorno autorizado funciona.
5. Janela vence na fila e opt-in é revogado: saída contida; dado antigo não renova janela.
6. Compra fica contida enquanto evento/identidade/autoridade não forem provados; homologação de conversa não é piloto comercial.

## Referências primárias conferidas em12/09/2026

- https://help.manychat.com/hc/en-us/articles/14281159586588-Default-Reply-in-Manychat — configuração por mensagem e opçãoInstagramDMsemStories.
- https://help.manychat.com/hc/en-us/articles/14281285374364-Dev-Tools-External-request — HTTPJSON e integração externa nativa.
- https://help.manychat.com/hc/en-us/articles/14281292522652-System-Fields — ContactID, texto e última interação distintos; campos específicos por canal.
- https://help.manychat.com/hc/en-us/articles/26673580447900-Response-Reference-for-Instagram-WhatsApp-and-Telegram-Automation — formatos de saída/capacidades variam por canal.
- https://help.manychat.com/hc/en-us/articles/23358636027932-Understanding-messaging-windows — janelaAPIWhatsApp24h.

## Auditoria adicional de identidade de mensagem

O OpenAPI público Page_API consultado em12/09/2026 contém34paths, nenhum de histórico/mensagens/eventos/webhooks de ingresso. Subscriber expõe last_input_text e last_interaction, sem message_id/event_id documentado. A lista oficialSystemFields diferencia ContactID e LastInteraction, sem documentar ID de mensagem. A referência DynamicBlockWA/IG não documenta external_message_callback (a capacidade Messenger não deve ser extrapolada). Isso comprova a lacuna documental consultada, não a impossibilidade de recurso específico da conta. Evidência sanitizada: evidence/conversational/whatsapp-window/message-identity-audit.json.

Para G02, solicitar ao fornecedor/inspecionar na conta: “Na automação DefaultReply de WhatsApp e Instagram, há variável oficial ou callback que entregue o ID imutável da mensagem recebida (e timestamp daquela mensagem), preservado em retries? Qual campo/API e quais garantias para duas mensagens rápidas e reexecução do ExternalRequest? ContactID e LastInteraction não atendem essa finalidade.” Texto preparado, nenhuma mensagem enviada ao suporte.

Composição contato+timestamp permanece hipótese somente se timestamp for por evento e estável em retry, e identidade incluir conta/canal. Timestamp de última interação mutável não é promovido a ID; microssegundos não comprovam unicidade. UUID por recebimento continua sendo receipt local, não dedupe do fornecedor. O caminho de compra depende de boundary comprovado; a prova da janela e as capacidades de leitura podem evoluir independentemente.
