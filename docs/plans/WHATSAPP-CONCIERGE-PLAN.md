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

> **01/10/2026:** entra no go-live (D-017). A visão do dono, as fases e a distância
> medida estão em [Visão do dono](#visão-do-dono-01102026); a tabela "Fases" mais abaixo
> é o rollout técnico (F1 a F4) e continua valendo como degraus de ligação.

## Visão do dono (01/10/2026)

> **Entra no go-live** por decisão do dono em 01/10/2026
> ([D-017](../coordination/DECISIONS.md); escopo em
> [GO-LIVE-SCOPE-CUT-PROPOSTA](GO-LIVE-SCOPE-CUT-PROPOSTA.md)). Razão dele: *"a
> equipe está defasada e a triagem das mensagens será muito útil"*.
>
> Legenda desta seção e das seguintes: **[FATO]** medido no código, no spec ou em
> saída de comando, com caminho:linha; **[INFERÊNCIA]** leitura minha;
> **NÃO VERIFICADO** quando não medi.

### VISÃO

O Concierge é a **interface conversacional da loja online**. Não é um fluxo de
pedido: é a loja inteira por conversa. O escopo, nas palavras do dono:

1. **FAQ**: horários, políticas, funcionamento.
2. **Informação e detalhe de produto e de pedido.**
3. **Montar o pedido completo**, confirmando as informações pertinentes.
4. **Endereço, forma de pagamento, avisos e confirmações.**
5. **Triagem**: responde sozinho o simples e escala o resto para uma pessoa, já
   classificado e resumido, porque a equipe está defasada.
6. **Futuro**: saber **quando** procurar a pessoa para oferecer "o pedido de
   sempre".

### FASES

| Fase | O que entra | Depende de |
|---|---|---|
| **Fase 1 (go-live)** | FAQ e informação de produto; triagem com escalonamento classificado e resumido (proposta na D32); consulta de pedido do próprio cliente; o que não cabe no chat vai para a equipe ou para o site | triagem construída; identidade ligada; flow do ManyChat em toda mensagem; chave da Anthropic; ver "Como ligar" |
| **Fase 2** | Pedido completo no chat (sacola, endereço, pagamento, recap e confirmação) | uma forma de dar autoridade de compra a um ingresso sem identificador de mensagem (ver "Limitação de frente"), ou um identificador verificado do provedor |
| **Futuro** | "O pedido de sempre" proativo, no momento certo | template aprovado na Meta (fora da janela de 24 horas); regra de quando procurar; opt-in de marketing |

[INFERÊNCIA] A divisão entre fase 1 e fase 2 não é escolha de produto minha: é
o que o contrato atual permite. Com o ingresso do ManyChat sem identificador, o
servidor não oferece ao modelo nenhuma ferramenta que altere sacola, pedido ou
pagamento (ver abaixo). Se o dono quiser o pedido completo já no go-live, a
decisão é sobre essa trava, não sobre o Concierge.

## Distância até a visão (medida em 01/10/2026)

Medido sobre `origin/main` em `1f1ff5afb`. **NOSSO** = código da casa;
**META/MANYCHAT** = depende de painel, aprovação ou capacidade de terceiro.

| # | Item do escopo | Estado | NOSSO (código) | META/MANYCHAT |
|---|---|---|---|---|
| 1 | FAQ: horários, políticas, funcionamento | **PRONTO** | [FATO] `search_storefront` busca catálogo + FAQ + horários numa porta só (`shopman/storefront/concierge/tools.py:449`); FAQ editável no Admin (`shopman/shop/models/faq.py:12`, `shopman/shop/admin/faq.py`); horários vêm de `_format_opening_hours` (`shopman/storefront/presentation/public_information.py:9`, `:32-68`, `:133`) | Nada além do flow ligado |
| 2a | Informação de produto | **PARCIAL** | [FATO] Nome, preço, disponibilidade viva, descrição curta, promoção e unidade (`tools.py:209-223`). Não há ingrediente nem alérgeno no payload; pergunta de alergia vai para a equipe pela regex (`handoff.py:36-39`) | Nada |
| 2b | Informação de pedido | **PARCIAL** | [FATO] `order_status` e `last_order` existem (`tools.py:1366`, `:1419`) e estão liberados mesmo em modo só leitura (`tools.py:1964-1976`). Mas dependem de identidade: com `CONCIERGE_IDENTITY_LINK_ENABLED=false` (`.do/app.alpha-subdomains.yaml:581-584`) a identidade não é resolvida (`transport.py:229`) e a resposta é "Ainda não sei quem é o cliente." (`tools.py:1377-1378`) | `getInfo` do ManyChat para o telefone do assinante (`transport.py:570-581`) |
| 3 | Montar o pedido completo, confirmando | **PARCIAL (bloqueado pelo provedor)** | [FATO] `set_item`, `set_fulfillment`, `review_order`, `place_order` com token de orçamento e "sim" explícito existem (`tools.py:620`, `:787`, `:1028`, `:1204`). [FATO] Não rodam pelo ManyChat: o turno fica só leitura quando o ingresso não tem identificador verificado (`service.py:835-839`) e o servidor nem oferece essas ferramentas ao modelo (`tools.py:1964-1976`) | [FATO] O corpo do External Request não tem identificador de mensagem (`docs/guides/whatsapp-concierge.md:118-141`) |
| 4a | Endereço | **PARCIAL** | [FATO] Composição de endereço por texto, pin e cadastro (`shopman/storefront/concierge/address.py:120`, `:142`, `:158`, `:200`); geocodificação pela chave do Maps (`.do/app.alpha-subdomains.yaml:788-790`). Mutação: cai na mesma trava do item 3 | [FATO] Campos de pin ainda não mapeados no flow (`whatsapp-concierge.md:60`) |
| 4b | Forma de pagamento | **PARCIAL (bloqueado pelo provedor)** | [FATO] `place_order` com Pix ou cartão (`tools.py:1204`); mesma trava do item 3 | Nada específico |
| 4c | Avisos e confirmações | **PARCIAL** | [FATO] Notificações transacionais saem por ManyChat → e-mail → SMS (cadeia descrita neste plano, "Canal de venda"); recibo de envio crítico só comprova por e-mail (D27, #1339) | [FATO] Fora da janela de 24 horas só sai template aprovado (`shopman/shop/checks.py:910-913`); 27 templates com copy de referência, estado na Meta a conferir (`docs/reference/whatsapp-templates-meta.md:3-13`) |
| 5 | Triagem: responder o simples, escalar o resto classificado e resumido | **INEXISTENTE** como o dono descreveu | [FATO] `grep -rniE "triage\|triagem" shopman packages config surfaces` só acha o quadro do Gestor de pedidos (`shopman/backstage/projections/order_queue.py:201`, `surfaces/orders-nuxt/app/pages/index.vue:29-120`), nada de mensagem. O que existe: (a) regex com 4 causas que só decide o handoff (`shopman/storefront/concierge/handoff.py:16-49`, chamada em `service.py:895-903`); (b) o modelo **não** consegue escalar: não há ferramenta de handoff no catálogo (`tools.py:1948-1960`) e o prompt manda não tentar (`prompt.py:67`); (c) o alerta ao operador é genérico, sem resumo: "Atendimento solicitado; sincronização ..." (`service.py:1302-1307`, `:1425-1437`); (d) `Conversation.summary` existe (`shopman/shop/models/concierge.py:60`) e nenhum código escreve nele; (e) o piloto de intenções tem 12 categorias definidas com o dono em 23/09 (`intent_pilot.py:58-91`) e só mede classificadores, não roteia | [FATO] O handoff liga o campo `concierge_handoff` no ManyChat e a equipe responde no Live Chat (este plano, "Arquitetura"); retorno ao bot fechado (`CONCIERGE_HUMAN_RETURN_ENABLED=false`, `.do/app.alpha-subdomains.yaml:585-588`; `service.py:1340`) |
| 6 | "O pedido de sempre" no momento certo | **INEXISTENTE** (proativo) | [FATO] Só reativo: `last_order` quando o cliente já está conversando (`tools.py:1419`). Não há regra de "quando procurar" | [FATO] Mensagem que a casa inicia é fora da janela: exige template aprovado (`checks.py:910-913`) |

**Onde o operador vê hoje.** [FATO] O alerta `concierge_handoff` tem público
`operations` (não está em `ORDER_TYPES`, `shopman/backstage/models/alerts.py:318-332`,
`:390-396`). O sino do Gestor de pedidos (`scope=orders`) só mostra alerta de
público `orders` ou preso a um pedido (`shopman/backstage/services/alerts.py:69-70`).
[INFERÊNCIA] Logo, um pedido de atendimento de quem ainda não tem pedido no chat
só aparece no Admin (`/admin/shop/conversation/<id>/change/`) e no e-mail de
alerta, não no Gestor.

## Triagem: PROPOSTA para o dono corrigir

> ⚠️ **PROPOSTA, não decisão.** Nada disto está no código. Decisão pendente:
> [D32 em PENDING-DECISIONS](../reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md#d32-concierge-a-proposta-de-triagem).
> O vocabulário reaproveita as 12 intenções que nasceram da conversa com o dono
> em 23/09 (`shopman/storefront/concierge/intent_pilot.py:58-91`), que já são dado
> editável no Admin.

**1. O que responde sozinho** (sem pessoa), sempre com a fonte canônica:

- `hours_delivery`: horário, endereço, retirada, se entrega, taxa por faixa.
- `house_info`: como funciona a casa, formas de pagamento, pet, estacionamento.
- `product_question` sem alergia: o que tem hoje, preço, disponibilidade, descrição.
- `order_status` do próprio cliente, quando a identidade está ligada.
- `order` simples: na fase 1 o Concierge orienta e manda o link da loja; na fase 2
  monta no chat.

**2. Como classifica.** Cada mensagem recebe **uma intenção principal** das 12 e
uma **urgência** (`agora`, `hoje`, `pode esperar`). A classificação roda antes do
modelo de resposta, na mesma porta onde hoje roda a regex
(`service.py:895-903`), e fica gravada na mensagem. As sensíveis (`complaint`,
`allergy`, `human`) **sempre** escalam, mesmo que o modelo saiba responder.

**3. O que escala** (para uma pessoa, com o bot calado naquela conversa):

| Intenção | Escala para | Urgência padrão |
|---|---|---|
| `human` (pediu pessoa) | atendimento | agora |
| `complaint` | atendimento (gerente) | agora |
| `allergy` | atendimento | agora |
| `special_order` (evento, volume) | encomendas | hoje |
| `order` que o chat não fecha (fase 1) | atendimento | agora |
| `job` | RH / dono | pode esperar |
| `partnership` | marketing / dono | pode esperar |
| `supplier_offer` | compras | pode esperar |
| qualquer uma após 2 tentativas sem resposta útil | atendimento | agora |

`job`, `partnership` e `supplier_offer` **não** acordam o balcão: entram numa fila
de "outra mesa", lida no dia.

**4. O que o operador vê.** Um cartão por conversa escalada, com:

- intenção e urgência (o rótulo da intenção, não o código);
- **resumo em uma ou duas linhas**, escrito pelo modelo e gravado em
  `Conversation.summary` (o campo já existe): o que a pessoa quer, o que o bot já
  respondeu, o que falta;
- nome e telefone quando a identidade está ligada; último pedido, se houver;
- um botão que abre a conversa (hoje o Admin) e outro que devolve ao bot quando o
  retorno estiver ligado.

**Onde:** no sino do Gestor de pedidos, para `human`, `complaint`, `allergy`,
`order` e `special_order` (hoje o alerta não chega lá, ver acima); no Admin e no
e-mail diário para `job`, `partnership` e `supplier_offer`.

**Perguntas para o dono corrigir:** as 12 intenções bastam? a tabela de destino
está certa (quem é "atendimento" na casa hoje)? o resumo vai no sino do Gestor ou
num app próprio? fora do expediente, o que escala espera a manhã ou toca alguém?

## Limitação de frente: ManyChat e a janela de 24 horas

[FATO] O corpo do External Request do ManyChat não traz identificador imutável
da mensagem (`docs/guides/whatsapp-concierge.md:118-141`), e o envio pelo
ManyChat não devolve identificador de mensagem entregue (D27, #1339). A Meta só
deixa sair texto livre até 24 horas depois da última interação do cliente
(`shopman/storefront/concierge/transport.py:264`, `:532-533`;
`shopman/shop/checks.py:910-913`). O que isso impede:

1. **Confirmar entrega ou leitura.** `accepted` só diz que o ManyChat aceitou;
   `delivered` e `read` não chegam (`whatsapp-concierge.md:172-175`). A casa não
   sabe se o cliente viu a resposta, o Pix ou o aviso.
2. **Deduplicar e correlacionar.** Sem identificador, um reenvio técnico do
   ManyChat é indistinguível de o cliente repetir a frase, então nada é
   descartado por suspeita (`whatsapp-concierge.md:132-134`). E não há como ligar
   uma resposta do cliente a uma mensagem específica da casa ("sim" a qual
   recap?) a não ser pela ordem na conversa.
3. **Autoridade de compra.** Pelo item 2, o contrato trata o ingresso como "pelo
   menos uma vez" e **fecha toda mutação** (sacola, pedido, pagamento,
   identidade): `service.py:835-839`, `tools.py:1964-1976`. É isto que empurra o
   pedido completo no chat para a fase 2.
4. **Mensagem livre fora da janela.** Qualquer coisa que a casa inicie (o pedido
   de sempre, um aviso depois de 24 horas, a resposta da equipe que demorou)
   exige template aprovado na Meta, submetido pelo ManyChat, com 24 a 48 horas
   de fila por rodada (`docs/reference/whatsapp-templates-meta.md:16-18`). A
   resposta automática dentro da janela é livre.
5. **Escalonamento com prazo.** [INFERÊNCIA] Se a equipe demora mais de 24
   horas para pegar uma conversa escalada, ela só consegue responder por
   template. A triagem precisa de urgência justamente para isto.

## Como ligar: estado no vivo e checklist

**Estado no spec versionado** (`.do/app.alpha-subdomains.yaml`; valor no app vivo
NÃO VERIFICADO):

| Variável | Valor | Linha |
|---|---|---|
| `SHOPMAN_CONCIERGE_ENABLED` | `'false'` | `:550-553` |
| `CONCIERGE_MANYCHAT_WHATSAPP_ACTIVE` | `'true'` | `:554-557` |
| `CONCIERGE_CONTRACT_VERSION` | `'3'` | `:564-567` |
| `CONCIERGE_READ_ONLY` | `'true'` | `:568-571` |
| `CONCIERGE_MANYCHAT_EVENT_ID_VERIFIED` | `'false'` | `:572-575` |
| `CONCIERGE_IDENTITY_LINK_ENABLED` | `'false'` | `:581-584` |
| `CONCIERGE_HUMAN_RETURN_ENABLED` | `'false'` | `:585-588` |
| `CONCIERGE_ALLOWED_SUBSCRIBERS` | um subject (coorte fechada) | `:603-606` |
| `CONCIERGE_OPERATION_MODE` | `observe` | `:617-620` |
| `CONCIERGE_OBSERVATION_ENABLED` / `_ALLOW_ALL_SUBJECTS` | `'true'` / `'true'` | `:621-624`, `:633-636` |

**O que muda ao ligar cada um, em ordem** ([FATO] pela leitura de
`shopman/storefront/concierge/service.py:79-98`, `:835-844` e
`webhook.py:97-129`):

1. **`CONCIERGE_OPERATION_MODE=observe` → `assist`.** É o primeiro portão: em
   `observe`, `disabled_reason()` devolve `observation_only` mesmo com o switch
   ligado (`service.py:89-91`). [FATO] Os modos são exclusivos: a observação
   passiva só grava com `operation_mode == "observe"` (`service.py:187-188`).
   [INFERÊNCIA] Trocar para `assist` **encerra a coleta** que alimenta o piloto de
   intenções; a amostra já guardada some no prazo de 7 dias (`:611-614`).
2. **`SHOPMAN_CONCIERGE_ENABLED=true`.** Com `assist` e a chave da Anthropic
   presente, o webhook deixa de responder `disabled` e enfileira o turno. Só os
   subjects de `CONCIERGE_ALLOWED_SUBSCRIBERS` entram (`not_allowed` para o
   resto). O bot passa a **responder** no WhatsApp.
3. **`CONCIERGE_IDENTITY_LINK_ENABLED=true`.** O assinante passa a ser
   resolvido para um `Customer` pelo telefone do ManyChat; consulta de pedido e
   "o de sempre" passam a responder.
4. **`CONCIERGE_HUMAN_RETURN_ENABLED=true`.** A equipe consegue devolver a
   conversa ao bot pelo Admin (`service.py:1340`).
5. **`CONCIERGE_READ_ONLY=false`.** [FATO] Sozinho **não muda nada** com o
   ManyChat de hoje: o turno continua limitado porque o adaptador não tem
   identificador verificado (`service.py:838-839`). Só tem efeito junto com o
   item 6.
6. **`CONCIERGE_MANYCHAT_EVENT_ID_VERIFIED=true`.** Só depois de o ManyChat
   expor um identificador e ele ser homologado (único e estável em retry). Hoje
   não há (ver "Limitação de frente").
7. **Abrir a coorte** (`CONCIERGE_ALLOWED_SUBSCRIBERS` → todos). Último passo,
   depois do piloto.

**Checklist antes de ligar (fase 1).**

- [ ] Triagem construída conforme a D32 decidida (classificação, resumo em
      `Conversation.summary`, alerta com resumo no lugar certo).
- [ ] Decidir o que acontece com a observação passiva (item 1 acima).
- [ ] `AI_ASSIST_API_KEY` e `CONCIERGE_API_KEY` com valor no app vivo
      (NÃO VERIFICADO; `.do/app.alpha-subdomains.yaml:545-547`, `:558-560`).
- [ ] Flow do ManyChat: External Request em **toda** mensagem do assinante, não
      só no `#c`, confirmado no grafo do flow (`whatsapp-concierge.md:112-116`);
      condição `concierge_handoff == "1"` pausando a automação.
- [ ] `directive-worker` vivo (o turno roda na fila de diretivas).
- [ ] FAQ revisada no Admin (é a fonte das respostas do item 1).
- [ ] Copy de abertura `CONCIERGE_GREETING` e de handoff revisadas pelo dono.
- [ ] Ensaio com o número do dono na coorte fechada, pelos 10 passos de
      `whatsapp-concierge.md:212-235`.
- [ ] Rotina de contenção conhecida: desligar `SHOPMAN_CONCIERGE_ENABLED` ou
      `CONCIERGE_MANYCHAT_WHATSAPP_ACTIVE` (`whatsapp-concierge.md:242-246`).

## Verificação: os dois comandos

| Comando | Onde | O que compara |
|---|---|---|
| `manage.py manychat_flows --check` | `shopman/shop/management/commands/manychat_flows.py:39-56`, `:84-117` | Lista os flows da conta pela API (`getFlows`) e confere se cada `NotificationTemplate.whatsapp_flow_ns` configurado ainda existe no ManyChat. Sem `MANYCHAT_API_TOKEN`, para com erro (`:61-66`) |
| system check `check_whatsapp_flow_coverage` | `shopman/shop/checks.py:906-1003` (`@register(deploy=True)`) | Se há campanha ativa de **Marketing** com WhatsApp e nenhum template ativo com flow para `announcement_published`, avisa `SHOPMAN_W014` (`:947`, `:1000`); com flow, avisa `SHOPMAN_W020` quando o modo de Marketing está em ensaio ou bloqueado (`:968`, `:986`) |

[FATO] **Nenhum dos dois cobre o Concierge.** O primeiro confere templates de
notificação; o segundo, campanhas de Marketing (que ficam fora do go-live). O
flow do Concierge (External Request, campo `concierge_handoff`) não tem
verificação automática; a conferência é o ensaio manual do checklist.

**Saída real ao rodar localmente (01/10/2026, worktree deste PR):**

- `.venv/bin/python manage.py manychat_flows --check` →
  `AssertionError: SECRET_KEY must be set in production (DJANGO_SECRET_KEY env var)`
  (`config/settings.py:2378`), exit 1.
- Com `DJANGO_SETTINGS_MODULE=config.settings_test DATABASE_URL=` →
  `ModuleNotFoundError: No module named 'shopman.utils.names'`, exit 1. Causa: o
  `.venv` carrega `packages/*` da árvore principal (editable installs), que está
  atrás do `main`; a trava de isolamento desta sessão recusou definir
  `PYTHONPATH` para apontar os pacotes para a worktree.
- O system check não foi rodado pelo mesmo motivo. Mesmo rodando, sem
  `MANYCHAT_API_TOKEN` o primeiro comando para em `manychat_flows.py:61-66`, e o
  check precisa do banco do staging para dizer algo útil. **NÃO VERIFICADO no
  staging.**

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
