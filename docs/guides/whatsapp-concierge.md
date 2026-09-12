# Concierge de WhatsApp — portão existente e contrato v2

O candidato reutiliza a automação ManyChat **Concierge (piloto)**, identificador
`content20260904134021_491685` (campo `ns` da API), e seu Keyword **#c**. A existência dessa automação
e a conta **Nelson Boulangerie** (`764222643620409`) foram confirmadas por consultas
somente leitura à API. Isso não comprova o conteúdo publicado dos nós nem a
origem de um identificador estável de mensagem.

Não criar outro flow, trocar o Default Reply ou ampliar a coorte para adaptar o
candidato. O access link existente continua com seu próprio gatilho. A entrada
conversacional mantém o endpoint e a autenticação já usados; a diferença essencial
é registrar o evento de forma durável antes de responder ao ManyChat.

## Corpo real confirmado e compatibilidade legada

Em 11/09/2026, o operador confirmou o URL
`https://api.boulangerie.com.br/api/webhooks/manychat/conversation/` e um corpo
com `subscriber_id`, `text`, `first_name` e `last_name`, sem identidade de evento.
O texto de exemplo era `#menu NB-…`; ele é preservado como texto, sem consumir
código de acesso ou promover identidade. Não substituir o corpo dinâmico pelos
valores fixos do exemplo.

C01 permite reutilizar esse corpo para leitura e encaminhamento humano. O
candidato acrescenta `CONCIERGE_LEGACY_READ_HANDOFF_ENABLED=false` por padrão.
Com opt-in autorizado, versão 2, conta, coorte e demais requisitos configurados:

- `#c cardápio`, `menu` ou `#menu NB-…` consultam o catálogo público canônico.
- `#c atendente` preserva o contexto e aciona o handoff existente.
- Texto de compra recebe orientação para consultar ou chamar a equipe, sem
  alterar sacola, revisão, pedido, pagamento, link de acesso ou consentimento.

Esse caminho é determinístico, sem modelo nem enriquecimento de identidade.
Cada recebimento guarda `event_id` e `external_id` vazios e
`input_assurance=legacy_unverified`, na mesma Conversation/Message/Directive.
O PK identifica um recebimento local; retries podem produzir recebimentos e
respostas públicas repetidos. Não há promessa de exatamente-uma-intenção.
Um batch com entrada legada permanece inteiro em leitura; nem um “confirmo”
legado já consumido vira autorização em turno posterior.

Recebimento legado não renova `last_inbound_at`: não prova nova interação no
WhatsApp. Sem janela previamente comprovada, a saída fica `not_applied` com
`window_closed`; não preencher timestamps manualmente no ambiente real. A janela
e a entrega ainda exigem homologação com ManyChat. A compatibilidade permanece
local e desativada; o URL confirmado não comprova que o candidato está publicado.

## Contrato da entrada

- Trigger existente: `#c`; o backend também reconhece `#concierge` e remove apenas
  esse prefixo inicial. `#c quero dois pães` vira `quero dois pães`.
- Endpoint: `POST /api/webhooks/manychat/conversation/` no mesmo host de API já
  configurado no flow, usando `Content-Type: application/json`.
- Header existente: `X-Api-Key`. `Authorization: Bearer` também é aceito.
  `CONCIERGE_API_KEY` continua usando `DOORMAN_ACCESS_LINK_API_KEY` como fallback.
  Não copiar nem registrar o valor da chave em documentação ou logs.
- Campo de handoff existente: `concierge_handoff`, texto `"1"` para equipe e `""`
  para retorno confirmado. A posse local contém o bot; esse campo espelha o
  roteamento no ManyChat Live Chat.

O corpo mínimo abaixo é **ilustrativo**: cada valor dinâmico deve entrar pelo
seletor real do ManyChat. Os rótulos não são nomes garantidos de variáveis:

```json
{
  "subscriber_id": "<subject selecionado no flow existente>",
  "text": "<texto desta mensagem selecionado no flow existente>",
  "event_id": "<identificador estável desta mensagem, ainda a comprovar>"
}
```

`message_id` e `external_id` também são aceitos como identidade do evento. Um
retry precisa conservar o mesmo ID e payload; duas mensagens legítimas iguais
precisam ter IDs diferentes. Não usar ID do assinante, texto+minuto, UUID gerado a
cada retry ou contador compartilhado de perfil como substituto não comprovado.
A consulta somente leitura aos campos personalizados confirmou `concierge_handoff`
como texto e não encontrou campo personalizado de ID de evento/mensagem; isso
não prova ausência de um campo sistêmico. A fonte do event ID permanece pendente
de verificação no portão existente. Sem
essa prova, a automação de mutações desse caminho fica contida.

`first_name` e `last_name` são opcionais; não são requisitos de ingresso. Telefone
ou perfil enviados no body não promovem identidade. Conta/provider/transporte
vêm da configuração confiável; não é necessário acrescentá-los ao corpo. Se
vierem, precisam corresponder à configuração. Texto vazio ou variável literal
como `{{last_input_text}}` não é substituído pela última mensagem do perfil via
`getInfo`: isso poderia processar outra mensagem e atrasar o ACK.

## Recebimento e resposta ao cliente

O ACK normal agora é **HTTP 200**, com `status` e `queued`, sem IDs internos. Ele
confirma recebimento/trabalho local, não pedido, pagamento nem entrega de uma
resposta ao aparelho. A transação grava Message e a Directive existente no tópico
versionado `concierge.turn.v2`; o worker processa o turno depois. A saída usa o
adapter ManyChat existente e revalida a janela antes do envio.

O guia antigo orientava não mapear resposta síncrona em campos; essa orientação
permanece. Se o flow real tratar status HTTP explicitamente, seu ramo deve ser
conferido para 200. Não configurar uma mensagem estática de sucesso de compra com
base no ACK.

| Resposta | Significado e recuperação |
|---|---|
| `200 queued` | Evento e trabalho aceitos; resposta posterior pelo worker. |
| `200 duplicate` | Mesmo evento/payload; consulta/reparo de trabalho sem duplicar mensagem. |
| `200 handoff` | Contexto preservado para equipe; bot contido. |
| `200 disabled` | Capacidade contida; `reason` informa versão, chave de modelo ou switch. |
| `200 not_allowed` | Subject fora da lista explícita; nenhum ingresso automático. |
| `200 legacy_read_only` | Recebimento sem ID, aceito apenas para catálogo/humano com opt-in; não autoriza compra. |
| `200 event_id_required` | Falta identidade estável e compatibilidade legada está desligada; nenhum ingresso. |
| `200 empty` | Falta texto útil deste evento. |
| `409 intent_conflict` | Mesmo ID com payload diferente; triagem, sem gerar nova intenção. |
| `401 / 503` | Autenticação ausente/incorreta ou configuração incompleta; conferir configuração sem expor segredo. |
| `400 / 413 / 415 / 429` | Corpo inválido, tamanho, MIME ou frequência; corrigir origem/política e preservar identidade do evento. |
| `500` ou timeout | Não presumir ausência de efeito; retry do mesmo ID/payload, nunca nova compra. |

A adaptação exata dos ramos de erro e do caminho humano deve ser revista no flow
existente. Esta documentação não publica nem altera a automação.

## Configuração do candidato

Além das credenciais e do switch já existentes, o contrato v2 exige configuração
explícita. O inventário de configuração não é autorização para ativação:

```env
CONCIERGE_CONTRACT_VERSION=2
CONCIERGE_ACCOUNT_ID=764222643620409
CONCIERGE_ALLOWED_SUBSCRIBERS=<somente subjects de teste explicitamente autorizados>
```

O inventário legado encontrou duas entradas de subject e duas entradas de telefone.
Conservar a autorização dos contatos de teste não significa promover telefones a
subjects: a lista v2 compara **subject ManyChat**. Resolver a correspondência pela
fonte confiável já usada; não inferir identidade a partir do telefone recebido no
body. Lista vazia contém o canal, nunca o abre a todos.

`SHOPMAN_CONCIERGE_ENABLED`, `AI_ASSIST_API_KEY` e a credencial ManyChat continuam
sendo requisitos próprios. Tokens existentes devem ser reutilizados no ambiente
autorizado, sem impressão ou cópia para fixtures. Configuração efetiva fica em
`config/settings.py`, bloco `SHOPMAN_CONCIERGE`.

Capacidades adicionais continuam desligadas até seus gates:
`CONCIERGE_IDENTITY_LINK_ENABLED`, `CONCIERGE_HUMAN_RETURN_ENABLED`,
`CONCIERGE_OUTPUT_RETRY_ENABLED` e `CONCIERGE_TRANSFER_ENABLED`. Não habilitar todas
para fazer um teste de ingresso. A rotação de entrada permite
`CONCIERGE_API_KEY_PREVIOUS` durante janela controlada; retirar a chave antiga é
operação separada no ambiente autorizado.

## Handoff, acompanhamento e recuperação

O escape textual para equipe funciona sem IA. Uma solicitação explícita recebe
ACK determinístico, sem promessa de atendimento imediato; contexto, escolhas e
refs permanecem na Conversation e nos owners canônicos. ManyChat Live Chat é a
superfície de atendimento, não uma inbox nova no Admin.

A ação de retorno no Admin exige capacidade própria e sincronização confirmada;
uma falha remota conserva a posse humana. Pedido registrado, pagamento pendente
e resultado desconhecido são estados distintos. A consulta retorna ao mesmo
pedido/recibo; não é preciso reconstruir a sacola após resposta perdida.

Saída distingue `prepared`, `executing`, `accepted`, `not_applied` e `unknown`.
`accepted` não comprova entrega. Timeout após possível efeito não admite reenvio
cego. Blocos dependentes, inclusive Pix, aguardam o bloco anterior; recuperação
explícita exige não aplicação comprovada, contexto atual e gate autorizado.

Desligar o switch contém admissão, execução, ferramentas e saídas não autorizadas.
Preservar pedidos, receipts e reconciliação; não apagar fila nem repetir histórico
como recuperação. Não realizar reseed, bootstrap de canal ou migração de produção
como parte automática da adaptação do teste.

## Verificação e limites da prova

`test_concierge_legacy_gateway.py` cobre o corpo de quatro campos, catálogo,
handoff, bloqueio de compra e confirmação, batch misto e revogação.

`test_concierge_existing_gateway.py` exercita localmente o mesmo endpoint, Keyword,
chave compartilhada de fixture e corpo mínimo; verifica replay, duas mensagens de
texto igual com IDs distintos e falta de ID sem efeitos. Credenciais são falsas e
nenhuma mensagem sai para o fornecedor. Isso prova compatibilidade técnica do
contrato proposto; não comprova a fonte do event ID na conta real.

Antes de homologar o portão existente, conferir seus nós/seletores, fonte e
estabilidade do event ID em retry, resposta 200, rota humana e janela. Registrar
artefato/hash do flow autorizado antes de eventual publicação. Não confundir:
implementação testada localmente, homologação controlada, piloto e rollout têm
provas e autorizações distintas. Reutilizar o teste existente não autoriza envio a
cliente real, publicação, deploy ou expansão.

Referências: [plano de excelência operacional](../plans/CONVERSATIONAL-SALES-OPERATIONAL-EXCELLENCE-PLAN-2026-09-11.md),
[contratos e evidências de ingresso](../../evidence/conversational/INGRESS.md),
[plano original](../plans/WHATSAPP-CONCIERGE-PLAN.md) e
[access link](whatsapp-access-link.md). O commit `d777be1cc` documenta a adoção do
Keyword `#c` em 04/09/2026, posterior à orientação histórica de Default Reply.
