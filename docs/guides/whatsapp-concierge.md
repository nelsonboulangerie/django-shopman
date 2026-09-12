# Concierge no WhatsApp — connection ManyChat do contrato v3

O WhatsApp via ManyChat é a primeira connection real do núcleo conversacional.
ManyChat recebe a mensagem e executa o External Request; o Shopman preserva a
conversa, o contexto comercial, a fila, a autoridade e as tentativas de saída.
Regras de venda, sacola, pedido ou diálogo não são duplicadas no flow.

Este guia descreve configuração e teste. Ele não autoriza publicar o flow,
habilitar uma connection, enviar a contatos reais, iniciar piloto ou fazer
rollout.

Código e testes da implementação técnica: SHA
`e87b9c4de04db9b48e3f02b0bf1ac6345a70c2fc`. O endpoint abaixo ainda precisa ser
publicado em ambiente autorizado antes de poder ser chamado pelo flow real.

## Portão canônico

- Connection: `manychat-whatsapp-primary`.
- Endpoint relativo: `POST /api/webhooks/concierge/manychat-whatsapp-primary/events/`.
- URL no host informado pelo operador:
  `https://api.boulangerie.com.br/api/webhooks/concierge/manychat-whatsapp-primary/events/`.
- `Content-Type`: `application/json`.
- Autenticação: `X-Api-Key`. A rotação aceita temporariamente a chave anterior
  configurada; o valor nunca deve aparecer em documentação, fixture ou log.
- Keyword de entrada já usada no teste: `#c`. O adapter também reconhece
  `#concierge`.
- Campo de handoff no ManyChat: `concierge_handoff`, com `"1"` para posse humana
  e `""` para retorno confirmado.

A chave da connection vem da rota confiável. `provider`, conta, canal e adapter
vêm do registry do servidor; o corpo não escolhe nenhum deles. Essa separação
permite adicionar outra connection, inclusive Instagram ou TikTok, sem
condicionais no domínio.

## Corpo confirmado no ManyChat

O operador confirmou estes cinco campos dinâmicos e o fuso da conta
`(UTC-03:00) - Brasilia Standard Time - Sao Paulo`:

```json
{
  "subscriber_id": "<subscriber_id dinâmico>",
  "text": "<texto dinâmico desta interação>",
  "first_name": "<primeiro nome dinâmico>",
  "last_name": "<sobrenome dinâmico>",
  "provider_timestamp": "<última interação WhatsApp dinâmica>"
}
```

Os valores acima são uma amostra do contrato, não valores para fixar no flow.
Cada propriedade deve continuar ligada ao seletor dinâmico correspondente:

| Campo | Uso no contrato v3 |
|---|---|
| `subscriber_id` | Subject opaco dentro de provider + conta + canal. Não é identidade comercial universal. |
| `text` | Fotografia do texto que acionou o External Request. Não consultar o perfil depois para substituí-lo. |
| `first_name`, `last_name` | Contexto de perfil opcional. Não promovem identidade nem autorizam compra. |
| `provider_timestamp` | Última interação do usuário no WhatsApp. Serve somente como evidência da janela de resposta. |

`provider_timestamp` não é instante da mensagem atual, ID de evento, prova de
confirmação comercial ou chave de deduplicação. O adapter interpreta o valor no
fuso configurado e preserva no envelope apenas a evidência normalizada da janela.

## Keyword e texto efetivo

O prefixo é removido somente no início do texto:

- `#c` sozinho vira `oi`, para que a entrada sempre tenha conteúdo útil;
- `#c cardápio` vira `cardápio`;
- `#concierge quero dois pães` vira `quero dois pães`;
- texto sem esses prefixos é preservado;
- `#menu NB-UTGJYD` permanece texto comum e não consome código de acesso.

O primeiro `#c` consegue abrir a experiência pelo Keyword já existente. Para
uma conversa com vários turnos, cada mensagem seguinte do subject de teste deve
chegar ao mesmo External Request, sem exigir novo prefixo. Isso precisa ser
confirmado no grafo do flow/Default Reply antes da homologação; a rota do backend
não comprova sozinha essa continuidade.

## Ausência de ID de mensagem

O corpo confirmado não contém ID imutável da mensagem. O contrato v3 trata esse
caso diretamente como ingresso **at-least-once**:

1. cada POST autenticado recebe um recibo local e é persistido no mesmo modelo
   canônico de mensagem e trabalho;
2. `event_identity_assurance=unavailable` e
   `input_assurance=at_least_once` registram o limite da evidência;
3. o turno desse lote fica somente leitura por assurance, mesmo que o switch
   global `CONCIERGE_READ_ONLY` esteja desligado;
4. catálogo público, orientação e handoff permanecem disponíveis;
5. ferramentas que mutam sacola, pedido, pagamento, identidade ou transferência
   não recebem autoridade desse ingresso;
6. um retry técnico pode ser indistinguível de uma repetição legítima do cliente,
   portanto nenhum hash de contato + timestamp é usado para descartar mensagens.

Não há modo de compatibilidade paralelo. Esse é um estado normal e explícito do
contrato. Se no futuro o fornecedor expuser um ID oficial, o flow deve mapeá-lo
para o campo canônico `event_id`, mas ele só ganha assurance
`verified` quando `CONCIERGE_MANYCHAT_EVENT_ID_VERIFIED=true` após homologação de
unicidade e estabilidade em retry. Um ID recebido antes desse gate é preservado
como candidato não verificado e continua sem autorizar mutações.

## ACK e processamento

O endpoint autentica, normaliza, grava e agenda o trabalho antes de responder. O
modelo e o envio rodam depois no worker da fila `Directive`, com payload v3
contendo `conversation_id` e `binding_id`.

O ACK não é mensagem para o cliente e não comprova pedido, pagamento, aceitação
do provedor ou entrega no aparelho. Não mapear seu JSON para um campo de resposta
nem adicionar uma mensagem estática de sucesso no flow.

| HTTP / status | Significado e próxima ação |
|---|---|
| `200 queued` | Recebimento persistido e trabalho agendado. A resposta ao cliente ocorre pela saída do adapter. |
| `200 duplicate` | Mesmo evento verificado e mesmo payload; o trabalho pode ser reparado sem nova mensagem. Não se aplica ao corpo atual sem ID. |
| `200 handoff` | Contexto preservado; a conversa continua sob posse humana. |
| `200 disabled` | Núcleo contido. Verificar `reason`, contrato, switch e credencial do modelo. |
| `200 not_allowed` | Subject fora da coorte explícita. Nenhum turno automático. |
| `200 empty` | O texto dinâmico chegou vazio ou não renderizado; corrigir o campo `text`. |
| `409 intent_conflict` | ID verificado repetido com payload diferente. Triar sem inventar nova intenção. |
| `409 scope_conflict` | Binding persistido diverge da connection autenticada. Manter contido e corrigir configuração. |
| `400` | JSON/campo inválido ou texto ausente. Corrigir o mapeamento dinâmico. |
| `401` | Chave ausente ou inválida. Conferir o secret sem expô-lo. |
| `404` | Connection desconhecida ou inativa. Conferir rota e gate da connection. |
| `503` | Connection/adapter/segredo incompleto ou escopo inconsistente. Manter contido e corrigir a configuração. |
| `413` / `415` / `429` | Corpo grande, MIME incorreto ou limite de frequência. Corrigir a origem e repetir somente quando seguro. |
| `500` ou timeout | O efeito local pode ter ocorrido. Não fabricar um novo ID nem presumir ausência de persistência. |

Na saída, `prepared`, `executing`, `accepted`, `not_applied`, `unknown`,
`delivered` e `read` têm significados separados. `accepted` confirma apenas a
aceitação declarada pelo provider. Cada execução gera `OutboundAttempt`
append-only; `unknown` não admite reenvio cego.

## Configuração v3

Estado seguro para preparar um teste sem ativá-lo:

```env
CONCIERGE_CONTRACT_VERSION=3
SHOPMAN_CONCIERGE_ENABLED=false
CONCIERGE_MANYCHAT_WHATSAPP_ACTIVE=false
CONCIERGE_ACCOUNT_ID=764222643620409
CONCIERGE_ALLOWED_SUBSCRIBERS=<subscriber_id de teste>
CONCIERGE_WHATSAPP_INTERACTION_TIMEZONE=America/Sao_Paulo
CONCIERGE_MANYCHAT_EVENT_ID_VERIFIED=false
CONCIERGE_READ_ONLY=true
CONCIERGE_IDENTITY_LINK_ENABLED=false
CONCIERGE_HUMAN_RETURN_ENABLED=false
CONCIERGE_OUTPUT_RETRY_ENABLED=false
CONCIERGE_TRANSFER_ENABLED=false
```

Além disso, o ambiente precisa da chave dedicada `CONCIERGE_API_KEY`, de
`AI_ASSIST_API_KEY` e do worker canônico. A lista de subjects vazia
fecha a connection. Telefone ou nome no body não substituem essa lista.

Para uma homologação autorizada, os dois switches de admissão são independentes:

```env
SHOPMAN_CONCIERGE_ENABLED=true
CONCIERGE_MANYCHAT_WHATSAPP_ACTIVE=true
```

Ativá-los permite ingresso somente quando os demais requisitos estão válidos;
não aprova identidade, retorno humano, retry, transferência, piloto ou rollout.
Manter `CONCIERGE_READ_ONLY=true` no primeiro ensaio dá contenção adicional. O
ingresso atual sem ID já fica somente leitura por assurance mesmo sem esse flag.

## Teste prático no portão ManyChat

1. No External Request do flow de teste, trocar somente a URL para a rota v3 e
   configurar `X-Api-Key` com a chave dedicada `CONCIERGE_API_KEY` do ambiente.
2. Confirmar `Content-Type: application/json` e os cinco campos dinâmicos acima.
3. Não configurar resposta síncrona ao cliente a partir do ACK.
4. Restringir o roteamento ao subject de teste autorizado.
5. Com homologação e ambiente de teste autorizados, enviar `#c`. O registro
   normalizado deve conter texto `oi`, binding ManyChat/WhatsApp e assurance
   at-least-once.
6. Enviar `#c cardápio`. O texto persistido deve ser `cardápio`; a resposta deve
   sair pelo worker e permanecer separada do ACK.
7. Enviar duas mensagens rápidas, incluindo aspas e quebra de linha. Ambas devem
   ser preservadas; sem ID oficial, não declarar deduplicação do provider.
8. Pedir uma compra. O sistema pode orientar e consultar catálogo, mas o ingresso
   sem ID verificado não deve criar efeito comercial.
9. Pedir `atendente`. O contexto deve permanecer legível e o bot deve parar de
   competir após a posse humana.
10. Conferir o Admin: conversa lógica, bindings, transcrição, estado de cada
    tentativa e próxima ação devem ser compreensíveis sem consultar logs.

Registrar hora, subject pseudonimizado, resposta HTTP, estado da Directive,
Message/Binding/OutboundAttempt e observação no aparelho. Não registrar chave,
telefone completo, payload sensível ou conteúdo desnecessário.

O teste local/fake prova o contrato de software. A homologação ManyChat precisa
provar o flow real, continuidade entre mensagens, janela, handoff e saída no
aparelho. Piloto mede pessoas e operação numa coorte autorizada. Rollout exige os
gates do plano, alvo/release fixados, backup, janela e rollback exercitado.

## Contenção e recuperação

Para conter a capacidade, desligar primeiro
`CONCIERGE_MANYCHAT_WHATSAPP_ACTIVE` e/ou `SHOPMAN_CONCIERGE_ENABLED`. Preservar
conversas, bindings, mensagens, directives, tentativas e receipts. Conciliar
estados `executing`/`unknown`; não reenviar automaticamente nem apagar histórico.

A migração do modelo v3 é forward-only. Rollback operacional é contenção com o
schema novo preservado e correção adiante; não executar downgrade que apague
evidências. Retorno humano, retry de saída e transferência continuam fechados
até seus gates próprios.

Referências: [plano de excelência operacional](../plans/CONVERSATIONAL-SALES-OPERATIONAL-EXCELLENCE-PLAN-2026-09-11.md),
[fluxo canônico ManyChat](../plans/CONCIERGE-MANYCHAT-CANONICAL-FLOW-2026-09-12.md),
[relatório da janela](../reports/concierge-whatsapp-window-20260912.md) e
[evidências de ingresso](../../evidence/conversational/INGRESS.md).
