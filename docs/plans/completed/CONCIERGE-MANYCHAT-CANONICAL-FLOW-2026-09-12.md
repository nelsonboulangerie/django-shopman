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
`7dba54a6ac81866bd0708033d683ac47dcade30c`; publicação, homologação ManyChat,
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

TikTok, Instagram e Facebook Messenger possuem conversa direta e APIs oficiais
de mensageria empresarial. Telegram oferece conversa privada com bots pela Bot
API. A existência de uma caixa de DM não basta para ativar a Concierge: cada
connection precisa comprovar ingresso, identidade de evento, janela, saída,
receipt e tomada humana com a conta real daquele canal.

Cada integração entra como uma nova connection com adapter próprio. O adapter
normaliza o payload para os mesmos contratos e declara capacidades de limite de
texto, janela, saída, receipts e handoff. Nenhuma regra comercial, busca, fila,
FAQ ou conversa lógica é copiada. Mídia só entra no contrato quando um adapter
real e o núcleo tiverem comportamento verificável para ela.

O gateway ManyChat atual usa credenciais globais do provider e, por isso, aceita
somente uma conta ativa por classe de adapter. Uma segunda conta falha fechada
até existir um gateway que receba credenciais por connection. APIs diretas da
Meta ou de outro provider podem implementar esse contrato sem essa restrição.

Ativação, coorte, credenciais, identidade, janela e atendimento humano são gates
separados por connection. Um fuso ou campo confirmado no WhatsApp não é
extrapolado para Instagram/TikTok. Meta direta pode coexistir como provider em
outro binding; a migração de provider exige roteamento explícito e nunca muda o
significado da conversa lógica.

### Roadmap multicanal

| Ordem | Connection planejada | Entrada recomendada | Por que vem aqui | Gate específico antes de implementar/ativar |
|---|---|---|---|---|
| 1 | `manychat-instagram-primary` | Instagram profissional via ManyChat | reutiliza o portão e a inbox já conhecidos para homologar o segundo canal com o menor trabalho operacional | conta profissional conectada, payload real, ID de mensagem, janela, retorno humano e coorte de teste separados do WhatsApp |
| 2 | `manychat-messenger-primary` | Facebook Messenger via ManyChat | preserva a mesma inbox humana e acrescenta outra superfície Meta sem criar operação paralela | Facebook Page conectada, payload real, ID, PSID, janela de 24 horas, permissão e coorte próprios |
| 3 | `manychat-tiktok-primary` | TikTok Business via ManyChat | ManyChat já oferece trigger de DM e inbox; valida o canal antes do custo de uma integração direta | Business Account elegível na região, payload/ID reais, limite de dez mensagens por 48 horas, links sem clique, handoff e coorte próprios |
| 4 | `manychat-telegram-primary` | bot Telegram conectado ao ManyChat | mantém a inbox humana atual; a Bot API direta continua disponível se houver motivo para retirar o intermediário | bot criado pelo BotFather, payload/ID preservados pelo gateway, usuário inicia a conversa, retorno humano e coorte próprios |
| 5 | `webchat-storefront-primary` | widget próprio no storefront | canal sob controle integral, sem aprovação de terceiros | UX, consentimento, proteção contra abuso, sessão anônima e encaminhamento para uma inbox humana existente |
| 6 | `rcs-primary` | RCS for Business por parceiro aprovado | amplia o alcance da mensageria do aparelho e oferece rich cards/receipts | demanda comprovada, parceiro/brand verification, custo e cobertura por operadora, opt-in/opt-out, fallback e dispositivo de teste |

Instagram e Messenger diretos pela API da Meta ficam como troca de provider, não
como outros canais lógicos. Depois de homologar as connections ManyChat, versões
`meta-instagram-primary` e `meta-messenger-primary` podem coexistir desligadas,
receber tráfego de uma coorte e substituir o gateway sem alterar `Conversation`,
ferramentas ou fatos públicos. O mesmo princípio vale para migrar WhatsApp de
ManyChat para Cloud API.

TikTok direto pela Business Messaging API segue a mesma estratégia. A versão
`tiktok-business-primary` só deve ser construída quando acesso, revisão e
capabilities da conta justificarem substituir o gateway ManyChat. Data
Portability API não é transporte conversacional e não deve ser usada para isso.

O destino canônico continua sendo um adapter de protocolo, não uma dependência do
ManyChat no domínio. Telegram pode migrar depois para a Bot API direta; enquanto
o atendimento humano morar no ManyChat, manter o gateway reduz superfícies e
esforço do operador.

Não planejar agora adapters para toda rede que possui chat. Apple Messages for
Business, SMS, LINE, Zalo, marketplaces e caixas de e-mail entram somente quando
houver demanda observada, API/contrato acessível e owner operacional. Google
Business Messages não entra no roadmap. RCS é a alternativa atual do ecossistema
Google para mensageria empresarial.

### Contrato mínimo de uma nova connection

1. Preservar o ID oficial de update/mensagem e seu escopo de conta; se o provider
   não oferecer ID homologável, manter a connection somente leitura.
2. Mapear remetente e thread como identificadores opacos do provider. Nunca unir
   contatos de canais diferentes por nome, username ou telefone não verificado.
3. Separar horário do evento, evidência da janela e horário de recebimento local.
4. Declarar capabilities reais: texto, tamanho, mídia, reply window, aceitação,
   entrega, leitura e handoff. Ausência é `unsupported`, não sucesso presumido.
   Limites são medidos na unidade do provider, inclusive bytes UTF-8 e orçamento
   de mensagens por janela, antes de segmentar uma resposta.
5. Persistir Message e Directive antes do ACK e OutboundAttempt antes da rede,
   reutilizando fence, fila, busca pública, ferramentas e receipts existentes.
6. Homologar UTF-8, ordem, replay, mensagens iguais, atraso, timeout, perda de
   ACK, saída `unknown`, posse humana e retorno com uma coorte isolada.
7. Ativar primeiro somente consulta pública. Identidade e ferramentas comerciais
   exigem gates próprios e uma vinculação explícita ao Customer canônico.
8. Resolver `commercial_channel_ref` pela connection confiável quando catálogo ou
   modalidade variarem. Nunca aceitar esse escopo do webhook ou do modelo.

### Decisão de prioridade

Instagram DM é a próxima integração recomendada. Ela testa imediatamente a
promessa multicanal usando ManyChat e preserva a mesma inbox do operador.
Messenger vem em seguida pelo mesmo motivo. TikTok já fica especificado, mas seu
primeiro teste também usa ManyChat, sujeito à elegibilidade da Business Account;
o adapter direto só começa após acesso à Business Messaging API. Webchat é a
opção de maior controle e só entra quando puder encaminhar para uma inbox humana
já existente. Telegram e RCS ficam no backlog guiado por demanda; não justificam
credenciais, operação e monitoramento antes de existir uso real.

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
- [Instagram no ManyChat](https://help.manychat.com/hc/en-us/articles/14281290924444-How-to-connect-Instagram-to-Manychat)
- [Facebook Messenger no ManyChat](https://help.manychat.com/hc/en-us/articles/14281086119068-How-to-connect-Facebook-to-Manychat)
- [TikTok no ManyChat](https://help.manychat.com/hc/en-us/articles/17928990909084-How-to-connect-TikTok-to-Manychat)
- [Trigger e limites de mensagens TikTok no ManyChat](https://help.manychat.com/hc/en-us/articles/17508399106844-Set-up-your-first-TikTok-automation-in-Manychat-User-sends-a-message)
- [Instagram API oficial: Send API e requisitos de mensagens](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
- [Messenger Platform API oficial: Send API e janela](https://www.postman.com/meta/messenger-platform-api/documentation/iyp204x/messenger-platform-api)
- [TikTok API for Business: Business Messaging](https://business-api.tiktok.com/gateway/docs/index?doc_id=1739585600931842&identify_key=c0138ffadd90a955c1f0670a56fe348d1d40680b3c89461e09f78ed26785164b&language=ENGLISH)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [RCS for Business](https://developers.google.com/business-communications/rcs-business-messaging)
- [Encerramento do chat do Google Business Profile](https://support.google.com/business/answer/14919056?hl=pt)

A auditoria histórica da documentação pública está preservada em
`evidence/conversational/whatsapp-window/message-identity-audit.json`. Ela
comprova a lacuna nas fontes consultadas, não a impossibilidade de uma capacidade
específica da conta.
