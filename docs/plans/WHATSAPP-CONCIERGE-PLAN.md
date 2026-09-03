# WHATSAPP-CONCIERGE-PLAN — Concierge de WhatsApp: pedido por conversa, com um modelo de linguagem

> Estado: **proposto (2026-09-03), código da F1 escrito, aguarda palavra do dono.**
> Supera o mecanismo do [MANYCHAT-CONVERSACIONAL-PLAN](MANYCHAT-CONVERSACIONAL-PLAN.md)
> (um flow e um endpoint por intenção): as invariantes são as mesmas (WhatsApp só via
> ManyChat, um número, o pedido nasce numa `Session` do canal `whatsapp` e passa pelo
> commit de sempre), o que muda é quem conduz a conversa. Decisão de arquitetura na
> [ADR-026](../decisions/adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md);
> configuração e operação no [guia do operador](../guides/whatsapp-concierge.md).
>
> | # | Pergunta | Recomendado (a confirmar) |
> |---|---|---|
> | 1 | Modelo | **Sonnet 5** (`CONCIERGE_MODEL`); Opus 5 é troca de env se o tom pedir |
> | 2 | Tom da abertura | copy `CONCIERGE_GREETING`, editável no Admin: casa, "assistente", uma pergunta |
> | 3 | Entrega no chat na v1 | **entrega no chat quando a geocodificação está ligada** (`GOOGLE_MAPS_API_KEY`: o endereço em texto vira coordenada e a taxa sai do motor de faixas); sem coordenada a ferramenta falha fechado e o concierge oferece retirada ou o site |
> | 4 | Teto diário por conversa | **80 turnos** (`CONCIERGE_MAX_TURNS_PER_DAY`) |
> | 5 | Fora do expediente | **responde** (o modelo sabe a agenda pelas ferramentas de slot e não promete o que não há); a encomenda para o dia seguinte é justamente o caso de uso |

## Objetivo

O cliente escreve no WhatsApp da casa como escreveria para uma pessoa ("quero 2
baguetes e um pão de chocolate pra amanhã cedo") e sai com um pedido registrado,
pago por Pix e visível no Gestor, sem sair do chat. Quando a conversa não cabe no
chat (entrega com endereço novo, troca de telefone, reclamação), o concierge
**leva para o site ou para a equipe**, nunca improvisa. É o princípio binário do
dono, "ou resolve tudo no chat, ou leva pra web e segue"
(`docs/_archive/redesign/06-spec-agentic.md:28`), com a língua livre que o
plano anterior não conseguia dar.

## O que já existe (reuso, não reescrita)

| Peça | Estado | Onde |
|---|---|---|
| WhatsApp via ManyChat: envio de texto, campos personalizados, `getInfo`, inerte em dev | no ar | `shopman/shop/adapters/notification_manychat.py`, [ADR-009](../decisions/adr-009-whatsapp-via-manychat.md) |
| Identidade do assinante → `Customer` (telefone pelo `whatsapp_phone`) | no ar | `shopman.guestman.adapters.auth.CustomerResolver.upsert_manychat_subscriber` |
| Sessão de pedido por canal, holds de estoque, quote, commit idempotente | no ar | Orderman + `shop.services.availability`, `shop.services.checkout.process` |
| Pagamento: Pix copia-e-cola e URL de checkout do cartão | no ar | `shop.services.payment.initiate` |
| Slots de retirada e regras de prazo | no ar | `shopman/storefront/services/pickup_slots.py`, `shop.services.fulfillment_window` |
| Access link (chat → site logado, sacola vai junto) | no ar | [guia](../guides/whatsapp-access-link.md), `doorman.services.access_link` |
| Fila de diretivas com worker (`process_directives --watch`) | no ar | [ADR-003](../decisions/adr-003-directives-sem-celery.md), `directive-worker` na DigitalOcean |
| Alertas do operador (`OperatorAlert`) | no ar | `shopman.backstage.services.alerts.create_alert` |
| Copy de cliente configurável | no ar | `OmotenashiCopy`, chaves `CONCIERGE_*` em `shopman/shop/omotenashi/copy.py` |
| Acompanhamento do pedido na loja | no ar | `/pedido/<ref>/` (storefront-nuxt) |
| SDK da Anthropic | dependência | `anthropic` (já usado pelo assist de texto do Gestor) |

O que é novo: `Conversation`/`ConversationMessage` (`shopman/shop/models/concierge.py`),
o service (`shopman/storefront/concierge/service.py`), o transporte
(`shopman/storefront/concierge/transport.py`), o agente e o prompt
(`shopman/storefront/concierge/agent.py`, `prompt.py`), as ferramentas
(`shopman/storefront/concierge/tools.py`), o webhook
(`shopman/storefront/concierge/webhook.py`), o handler da diretiva
`concierge.turn`, o Admin (`shopman/storefront/admin/concierge.py`), o canal `whatsapp`
no seed e o comando `bootstrap_whatsapp_channel`.

## Arquitetura

```
cliente ──texto──▶ WhatsApp ──▶ ManyChat (flow: Default Reply / keyword)
                                  │
                                  ├─ Condition: concierge_handoff == "1"?
                                  │     sim → "Pause all automations" (equipe no Live Chat)
                                  │
                                  └─ External Request  POST /api/webhooks/manychat/conversation/
                                       { subscriber_id, text, first_name, last_name }
                                       X-Api-Key: CONCIERGE_API_KEY
                                                │
                                    Django ─────┘  receive_inbound()
                                       ├─ dedupe por id da mensagem
                                       ├─ grava ConversationMessage(inbound)
                                       ├─ identifica o cliente (Guestman ↔ ManyChat getInfo)
                                       └─ enfileira Directive concierge.turn (1 por conversa)
                                       ◀── 202 em < 1 s (o ManyChat corta em 10 s)
                                                │
                              directive-worker ─┘  run_turn()
                                       ├─ junta o que o cliente mandou desde a última resposta
                                       ├─ política antes do modelo: mídia? teto do dia? handoff?
                                       ├─ agente (Anthropic SDK, system + tools em cache)
                                       │     └─ loop: tool_use → tools.py → services → tool_result
                                       ├─ persiste a transcrição (texto, tool_use, tool_result)
                                       └─ transport.send_text → ManyChat sendContent → cliente
```

O modelo nunca vê um preço que não veio de `tool_result`; as ferramentas nunca
inventam um caminho paralelo ao da loja. Um pedido do chat entra no Gestor
(coluna WhatsApp), no KDS, no fiscal e no caixa como qualquer outro.

**Canal de venda.** `Channel` ref `whatsapp`: pagamento `["pix","card"]` com
timing `at_commit` (o Pix aparece logo depois do pedido), confirmação
`auto_confirm` em 5 min, listing `whatsapp` espelhando a web. O seed liga o canal;
o banco vivo recebe pelo comando `bootstrap_whatsapp_channel`. A notificação
segue a cadeia existente (`manychat → email → sms`).

**Dados.** A sessão do chat grava `Session.data["origin_channel"] = "whatsapp"` e
`Session.data["concierge"] = {"conversation_id": ...}`
([data-schemas](../reference/data-schemas.md#concierge-de-whatsapp)). A conversa
guarda o que a casa precisa lembrar entre turnos e o modelo não pode inventar:
telefone, `session_key` da sacola, o orçamento vigente, o estado.

## Catálogo de ferramentas

Cada ferramenta é código determinístico que só chama services existentes. O
guardrail à direita é do **código**; o prompt repete, mas não é ele quem garante.

| Ferramenta | Faz | Guardrail |
|---|---|---|
| `browse_menu` | catálogo do listing `whatsapp` com preço e disponibilidade | preço e estoque só daqui; "restam N" vem do quant vivo |
| `view_cart` | a sacola atual (linhas, total) | total é o do Orderman, nunca somado pelo modelo |
| `set_item(sku, qty)` | põe/ajusta linha na sessão do canal `whatsapp` | hold de estoque via availability service; sku desconhecido é erro, não chute |
| `set_fulfillment(type, date, slot_ref, address)` | retirada/entrega, data e janela; na entrega, geocodifica o endereço e reprecifica a taxa como o checkout do site | slot inválido é recusado pelo `fulfillment_window`; endereço sem coordenada é recusado (`address_not_located`), nunca taxa chutada; fora da área vem `delivery_out_of_zone` |
| `list_pickup_slots(date)` | janelas possíveis na data | a agenda é da casa (`pickup_slots`), o modelo só lê |
| `review_order()` | o orçamento (linhas, taxas, total, prazo) + `quote_token` | o recap que o cliente confirma é este texto, não uma paráfrase |
| `place_order(quote_token, payment_method)` | commit via `checkout.process`, idempotente; `payment.initiate` | **recusa token vencido** (sacola mudou); exige confirmação explícita; Pix vai em mensagem separada |
| `order_status(order_ref)` | estado do pedido do próprio cliente | só pedidos do `customer_ref` da conversa |
| `last_order()` | último pedido, para "o de sempre?" | idem |
| `send_web_link(destination)` | access link do doorman para a loja | o link entra logado, com a sacola; TTL curto, uso único |
| `handoff_to_human(reason)` | passa para a equipe | grava estado, alerta `concierge_handoff`, liga o campo no ManyChat; o bot cala até o Admin devolver |

Guardrails de conversa que vivem no service, não nas ferramentas: dedupe de
inbound por id, uma diretiva por conversa, teto diário de turnos
(`CONCIERGE_TURN_LIMIT`), mídia respondida com copy fixa
(`CONCIERGE_MEDIA_UNSUPPORTED`), três falhas seguidas do modelo levantam
`OperatorAlert` `concierge_unavailable` e respondem `CONCIERGE_UNAVAILABLE`,
contato sem telefone conversa mas não fecha pedido (`CONCIERGE_NO_PHONE`).

## Desenho da conversa

Pesquisa comercial de 2026-09-03, resumida no que vira regra do prompt:

- **Abertura** curta, sem emoji, dizendo que é um assistente da casa e fazendo
  uma pergunta (`CONCIERGE_GREETING`). Meta exige que o cliente saiba que fala
  com automação e tenha caminho claro para uma pessoa; a casa oferece "falar com
  a equipe" sempre que perguntada e nunca nega ser assistente.
- **Uma pergunta por turno.** Opções em texto puro, no máximo 3 por mensagem
  (o WhatsApp limita 3 botões / 10 linhas de lista; como usamos texto, a régua é
  a mesma para não virar formulário).
- **Recap + "sim" explícito** antes de fechar. O recap é o `review_order()`,
  linha a linha, com total e prazo. Sem "sim", não há `place_order`.
- **Pix primeiro, cartão segundo.** 80% dos brasileiros têm o Pix como meio
  principal (CNDL/SPC, 01/2026). O código copia-e-cola vai em mensagem própria,
  sem texto em volta, para o toque-e-cola funcionar.
- **Velocidade é a alavanca número um.** 62% já abandonaram uma compra por
  WhatsApp depois de uma experiência ruim (Opinion Box, 2025). Resposta em
  segundos, sem confirmações desnecessárias, sem "só um momento".
- **Escassez só verdadeira.** "Restam 6" vem do estoque vivo via `browse_menu`;
  urgência inventada é proibida.
- **Um adicional, uma vez.** Depois do recap, uma sugestão de bom gosto (o café
  que combina, o pão que sobra pouco). Recusou, não volta.
- **"O de sempre?"** para quem já pediu (58% dos brasileiros já repetiram pedido
  por WhatsApp, Opinion Box 2026), via `last_order()`.
- **Handoff sem drama.** "Claro, alguém da equipe continua com você por aqui"
  (`CONCIERGE_HANDOFF_ACK`) e silêncio do bot até o Admin devolver.
- **Tom de casa boa:** frases curtas, calor sem exclamação em série, zero emoji
  na abertura e quase nenhum depois, sem pedidos de desculpa em cadeia, nunca
  negociar preço, nunca afirmar disponibilidade que a ferramenta não deu.
- **LGPD.** O pedido é execução de contrato; a transcrição fica guardada para
  qualidade do atendimento (e é o que o gestor lê no Admin); nada de marketing
  pela conversa sem opt-in.

## Custo

Pesquisa de 2026-09-03, preços de lista da Anthropic por MTok (entrada/saída):
Haiku 4.5 US$ 1/5, Sonnet 5 US$ 2/10, Opus 5 US$ 5/25; leitura de cache ≈ 10% do
preço de entrada. Premissas: 12 turnos por conversa, prefixo em cache ≈ 3k
tokens, ≈ 800 de entrada sem cache + ≈ 150 de saída por turno, +30% pelas idas
de ferramenta.

| Modelo | Por conversa | 300 conversas/mês | 1.000 conversas/mês | Observação |
|---|---|---|---|---|
| Sonnet 5 (default) | US$ 0,05–0,07 | US$ 15–20 | US$ 50–65 | prefixo cacheável a partir de 1.024 tokens |
| Opus 5 | ≈ 2,5× | US$ 40–50 | US$ 125–165 | troca de env |
| Haiku 4.5 | ≈ metade | US$ 8–10 | US$ 25–35 | **não cacheia** abaixo de 4.096 tokens de prefixo; com ~3k de system prompt paga entrada cheia todo turno |

WhatsApp: conversa iniciada pelo cliente e resposta em texto livre dentro das
24 h são gratuitas; ManyChat Pro ≈ US$ 39/mês (2.500 contatos ativos). Conclusão:
bem abaixo de US$ 100/mês no volume da padaria; o modelo é uma variável de
ambiente.

## Métricas

Todas legíveis a partir de `Conversation`/`ConversationMessage` e dos pedidos com
`origin_channel = "whatsapp"`; nenhuma pede tabela nova.

| Métrica | Como medir | Saudável |
|---|---|---|
| Conversa → pedido | conversas com pedido / conversas com ≥ 1 turno | > 20% |
| Tempo até a primeira resposta | `last_outbound_at - last_inbound_at` no 1º turno | < 10 s |
| Taxa de handoff | conversas que passaram por `handoff` / total | 15–30% |
| Ticket médio vs web | pedidos `whatsapp` vs `web` | ≥ web |
| Recorrência | clientes com 2+ pedidos pelo chat | cresce mês a mês |
| Recuperação de sacola | conversas com `session_key` e sem pedido que voltam e fecham | acompanhar |
| Custo por conversa | tokens × preço de lista | < US$ 0,10 |

## Fases

| Fase | Entrega | Gate |
|---|---|---|
| **F1** | Código no ar (models, service, agente, ferramentas, webhook, handler, Admin, copy, seed do canal). Canal `whatsapp` ativo no banco vivo (`bootstrap_whatsapp_channel`). `SHOPMAN_CONCIERGE_ENABLED=false`: o endpoint responde `disabled`, nada roda. | `make test`, `make admin`, deploy |
| **F2** | Flow no ManyChat (guia, passo a passo) + `SHOPMAN_CONCIERGE_ENABLED=true` em **piloto fechado** (tag `concierge-piloto` no flow + `CONCIERGE_ALLOWED_SUBSCRIBERS` na casa: ninguém fora da lista entra). Teste com o número do Pablo: pedido de retirada, Pix, handoff e volta pelo Admin. | o Pablo fecha um pedido e lê a transcrição |
| **F3** | Piloto com amigos/alpha. Uma semana medindo as métricas acima; ajuste de prompt e copy pelo Admin, sem deploy. | limiares da ADR-026 |
| **F4** | Áudio via transcrição; endereço estruturado na entrega (hoje só texto + coordenada, sem complemento/ponto de referência); resumo de conversas longas (o campo `summary` existe, a janela ainda é só por contagem); "o de sempre?" proativo na abertura para recorrentes. | pós-piloto |

## Perguntas para o Pablo

1. **Modelo:** Sonnet 5 como default, Opus 5 se o tom pedir? (custo ≈ 2,5×)
2. **Tom da abertura:** a copy `CONCIERGE_GREETING` está boa? Ela é editável no
   Admin, mas a primeira versão define o piloto.
3. **Entrega no chat na v1** está ligada quando há geocodificação; prefere deixar
   ligada, ou mandar entrega para o site no piloto? (Recomendação: ligada, com
   `GOOGLE_MAPS_API_KEY` no ambiente; o motor de taxa é o mesmo do site.)
4. **Teto diário** de 80 turnos por conversa está razoável? Ele existe para
   segurar custo em loop, não para limitar cliente.
5. **Fora do expediente:** o concierge responde à noite? (Recomendação: sim,
   com a agenda das ferramentas; encomenda para amanhã é o caso típico.)

## Como testar localmente

O único serviço que precisa ser público é o Django, para o External Request do
ManyChat alcançar o webhook. A receita de túnel Cloudflare é a mesma do access
link, seção "Testar localmente com Cloudflare Tunnel" em
[whatsapp-access-link.md](../guides/whatsapp-access-link.md); aqui só muda a URL e
as variáveis:

```env
SHOPMAN_CONCIERGE_ENABLED=true
AI_ASSIST_API_KEY=<chave da Anthropic>
CONCIERGE_API_KEY=<segredo forte>           # o X-Api-Key do External Request
MANYCHAT_API_TOKEN=<token da API ManyChat>  # para a resposta voltar
```

1. `make run` sobe o Django, o worker de diretivas e o túnel (URL em `.tunnel.log`).
2. No ManyChat, aponte o External Request para
   `https://<tunnel-django>/api/webhooks/manychat/conversation/` com o header
   `X-Api-Key`.
3. Escreva para o número da casa. A transcrição aparece em
   `/admin/shop/conversation/` a cada turno; o log do worker mostra `concierge.`.
4. Sem ManyChat: chame o webhook com `curl` (mesmo JSON) e leia a resposta na
   transcrição do Admin; o transporte fica inerte em dev e registra o envio no log.

## Referências

- [ADR-026](../decisions/adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md), [ADR-009](../decisions/adr-009-whatsapp-via-manychat.md), [ADR-003](../decisions/adr-003-directives-sem-celery.md)
- [Guia do operador](../guides/whatsapp-concierge.md)
- [MANYCHAT-CONVERSACIONAL-PLAN](MANYCHAT-CONVERSACIONAL-PLAN.md) (superado), [manychat-conversation-projection](../reference/manychat-conversation-projection.md)
- `docs/_archive/redesign/06-spec-agentic.md:28`
