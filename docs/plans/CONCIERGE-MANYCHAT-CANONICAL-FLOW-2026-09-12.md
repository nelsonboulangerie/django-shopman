# ManyChat como primeira connection canônica da Concierge

Decisão de direção do operador em 12/09/2026: começar com a melhor arquitetura
para um projeto pré-go-live, sem camada de compatibilidade no runtime. WhatsApp
via ManyChat é o primeiro binding real. Instagram, TikTok, Meta direta ou outro
provider devem entrar por adapter + connection, sem ramificar regras de domínio.
Este documento complementa C01/C03/C07/C08 e os gates do plano de excelência.

## Estado e proveniência

O histórico anterior permanece relevante como evidência de descoberta:

- o core v2 e uma capacidade restrita de leitura/humano chegaram a ser
  publicados no SHA `ed9a0d6dc`;
- o flow observado tinha Keyword `#c`, External Request na rota anterior e corpo
  de quatro campos (`subscriber_id`, `text`, `first_name`, `last_name`);
- o operador depois confirmou `provider_timestamp` como última interação do
  usuário no WhatsApp e o fuso UTC-03 de São Paulo;
- a correção isolada do parsing dessa janela foi validada no PR 622, base
  `cbda00f02e692fc7d1949a4e11024ace33245362`;
- a documentação pública consultada não comprovou ID imutável da mensagem para
  esse External Request.

Esses fatos descrevem o caminho de descoberta. O contrato v3 substitui a
estrutura v2 no candidato atual. A implementação técnica foi validada no SHA
`e87b9c4de04db9b48e3f02b0bf1ac6345a70c2fc`; publicação, homologação ManyChat,
piloto e rollout do desenho final não foram executados.

## Arquitetura escolhida

`Conversation` conserva a jornada lógica e os fatos comerciais. Cada endereço de
transporte é um `ConversationBinding` com
`provider + account + channel + subject + connection_key`. Mensagens de entrada e
resposta apontam para o binding causal. Cada execução de saída gera um
`OutboundAttempt` append-only, com estado e receipt próprios.

Uma única versão, `Conversation.turn_fence`, governa contexto, ferramentas,
persistência e envio. Cada entrada nova avança o fence e revoga trabalho feito
sobre contexto anterior. Não há contador, fila ou consulta paralela para
detectar correções tardias.

Provider, canal, conta e subject são strings opacas. O domínio não contém
`if whatsapp`, `if instagram` ou `if tiktok`. O registry explícito resolve a
connection pela rota confiável e instancia o adapter declarado. Limite de texto,
janela, handoff, identidade estável e delivery receipts pertencem ao adapter e
só existem quando o núcleo realmente os aplica.

ManyChat mantém trigger, roteamento técnico e atendimento humano. O Shopman
mantém Message/Conversation/Binding/Attempt/Directive, contexto, modelo,
ferramentas, autoridade comercial e receipts. Não acrescentar n8n, fila paralela,
carrinho em Custom User Field ou motor de diálogo no ManyChat.

Um contato de outro canal não é unido automaticamente por nome, telefone ou
payload. Associar um novo binding a uma conversa existente exige uma operação
explícita com `IdentityResolution` verificada contra o Customer canônico. Essa
escolha evita misturar clientes e permite preservar a mesma sacola/contexto
quando a vinculação for autorizada.

## Entrada e continuidade no ManyChat

Usar a connection `manychat-whatsapp-primary` e a rota:

```text
POST /api/webhooks/concierge/manychat-whatsapp-primary/events/
```

O External Request envia os cinco campos confirmados:

```json
{
  "subscriber_id": "<contact id dinâmico>",
  "text": "<texto desta interação>",
  "first_name": "<nome dinâmico>",
  "last_name": "<sobrenome dinâmico>",
  "provider_timestamp": "<última interação WhatsApp>"
}
```

Conta, provider e canal não vêm do corpo. A connection autenticada fixa esse
escopo. O adapter transforma `#c` sozinho em `oi`, remove `#c`/`#concierge`
quando forem prefixos e preserva os demais textos.

Keyword `#c` pode abrir o teste. Cada mensagem posterior precisa alcançar o
mesmo External Request sem novo prefixo, por configuração nativa do flow/Default
Reply restrita à coorte. Antes de alterar o Default Reply, inspecionar keywords
concorrentes, condição de humano, ordem de triggers e exclusões existentes.
Nenhuma substituição global ou expansão automática da coorte.

## Requisição, ACK e saída

O adapter autentica e normaliza o request para `InboundEvent`. A transação grava
Message e Directive antes do ACK. O worker recebe `conversation_id`, `binding_id`
e `contract_version=3`, agrupa somente entradas daquele binding sob lock/fence e
revalida autoridade antes de qualquer efeito.

O ACK HTTP 200 confirma recebimento/trabalho local. Não é resposta ao cliente nem
resultado comercial. O flow não deve mapear esse ACK para mensagem. A resposta
persistida sai por uma única via, o adapter, com estados distintos de preparação,
execução, aceitação, não aplicação, incerteza, entrega e leitura.

`provider_timestamp` representa última interação do usuário no canal. Ele é
evidência separada para a janela de resposta e nunca vira `occurred_at`, ID da
mensagem ou prova de confirmação. A janela é revalidada no momento de enviar.

## Identidade de evento e autoridade

Sem ID oficial da mensagem, cada POST autenticado é um recebimento local
at-least-once. Isso não é compatibilidade nem exceção temporária. O envelope
declara a assurance indisponível e o lote fica somente leitura por regra do
núcleo. Não descartar por hash de contato + timestamp, pois retry técnico e
repetição legítima podem ter os mesmos cinco campos.

Se surgir um ID oficial, o adapter pode preservá-lo imediatamente como candidato.
Deduplicação e autoridade só mudam depois de homologar estabilidade em retry,
unicidade para mensagens iguais e escopo de conta/canal, e então ligar
`CONCIERGE_MANYCHAT_EVENT_ID_VERIFIED`.

O hash usado para detectar conflito de um ID verificado cobre apenas a intenção
normalizada: subject, ID, tipo e texto. Mudanças em nome ou evidência de janela
não transformam replay idêntico em conflito.

Mesmo com transporte at-least-once, os efeitos comerciais continuam protegidos
por revisão vigente, inbound causal posterior, `quote_token`, locks e recibos de
mutação do Shopman. Essa proteção não transforma um evento sem assurance em
autorização para comprar; as ferramentas mutantes permanecem bloqueadas.

## Posse humana

Atendimento permanece na inbox do ManyChat. O binding espelha a sincronização do
campo `concierge_handoff`, enquanto `Conversation.state` contém o bot em todos os
bindings lógicos. Mensagens durante handoff preservam contexto. Retorno ao bot é
explícito; se qualquer binding aplicável falhar ou ficar `unknown`, a posse humana
permanece.

## Outros canais e providers

Instagram DM ou TikTok entram como novas connections com adapter próprio. Cada
adapter normaliza seu payload para os mesmos contratos e declara capacidades de
limite de texto, janela, saída, receipts e handoff. Nenhuma regra comercial ou
fila é copiada. Mídia só entra no contrato quando um adapter real e o núcleo
tiverem comportamento verificável para ela.

O gateway ManyChat atual usa credenciais globais do provider e, por isso, aceita
somente uma conta ativa por classe de adapter. Uma segunda conta falha fechada
até existir um gateway que receba credenciais por connection. APIs diretas da
Meta ou de outro provider podem implementar esse contrato sem essa restrição.

Ativação, coorte, credenciais, identidade, janela e atendimento humano são gates
separados por connection. Um fuso ou campo confirmado no WhatsApp não é
extrapolado para Instagram/TikTok. Meta direta pode coexistir como provider em
outro binding; a migração de provider exige roteamento explícito e nunca muda o
significado da conversa lógica.

## Homologação necessária

1. Registrar o grafo atual do flow, origem dos cinco campos e condição que envia
   todas as mensagens subsequentes.
2. Enviar `#c`, `#c cardápio` e mensagens rápidas com aspas/quebra de linha;
   preservar texto e ordem sem alegar dedupe inexistente.
3. Observar ACK separado da resposta do worker e `accepted` separado da entrega
   no aparelho.
4. Confirmar que ingresso sem ID consulta/orienta e não produz mutação comercial.
5. Exercitar humano, mensagem durante posse e retorno autorizado; incerteza deve
   manter o bot contido.
6. Vencer/revogar a janela antes do envio e comprovar `not_applied`, sem renovar
   a janela com dado antigo.
7. Conferir conversa, binding e attempts no Admin com resultado/próxima ação
   compreensíveis para o operador.

Homologação técnica do provider não é piloto comercial. Piloto exige coorte e
responsáveis aprovados, e rollout exige os gates G01–G07 do plano.

## Referências primárias conferidas em 12/09/2026

- [Default Reply in ManyChat](https://help.manychat.com/hc/en-us/articles/14281159586588-Default-Reply-in-Manychat)
- [Dev Tools: External Request](https://help.manychat.com/hc/en-us/articles/14281285374364-Dev-Tools-External-request)
- [System Fields](https://help.manychat.com/hc/en-us/articles/14281292522652-System-Fields)
- [Response Reference](https://help.manychat.com/hc/en-us/articles/26673580447900-Response-Reference-for-Instagram-WhatsApp-and-Telegram-Automation)
- [Understanding messaging windows](https://help.manychat.com/hc/en-us/articles/23358636027932-Understanding-messaging-windows)

A auditoria histórica da documentação pública está preservada em
`evidence/conversational/whatsapp-window/message-identity-audit.json`. Ela
comprova a lacuna nas fontes consultadas, não a impossibilidade de uma capacidade
específica da conta.
