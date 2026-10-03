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
| **Fase 1 (go-live)** | FAQ e informação de produto; triagem com escalonamento classificado e resumido (D32 decidida; implementada, D-018); consulta de pedido do próprio cliente; o que não cabe no chat vai para a equipe ou para o site | triagem construída; identidade ligada; flow do ManyChat em toda mensagem; chave da Anthropic; ver "Como ligar" |
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
| 2a | Informação de produto | **PARCIAL** | [FATO] Nome, preço, disponibilidade viva, descrição curta, promoção e unidade (`tools.py:209-223`). Não há ingrediente nem alérgeno no payload; pergunta de alergia vai para a equipe pela regex (`handoff.py`), menos a só de glúten, que a Concierge responde com o aviso da casa (03/10/2026, `gluten.py`) | Nada |
| 2b | Informação de pedido | **PARCIAL** | [FATO] `order_status` e `last_order` existem (`tools.py:1366`, `:1419`) e estão liberados mesmo em modo só leitura (`tools.py:1964-1976`). Mas dependem de identidade: com `CONCIERGE_IDENTITY_LINK_ENABLED=false` (`.do/app.alpha-subdomains.yaml:581-584`) a identidade não é resolvida (`transport.py:229`) e a resposta é "Ainda não sei quem é o cliente." (`tools.py:1377-1378`) | `getInfo` do ManyChat para o telefone do assinante (`transport.py:570-581`) |
| 3 | Montar o pedido completo, confirmando | **PARCIAL (bloqueado pelo provedor)** | [FATO] `set_item`, `set_fulfillment`, `review_order`, `place_order` com token de orçamento e "sim" explícito existem (`tools.py:620`, `:787`, `:1028`, `:1204`). [FATO] Não rodam pelo ManyChat: o turno fica só leitura quando o ingresso não tem identificador verificado (`service.py:835-839`) e o servidor nem oferece essas ferramentas ao modelo (`tools.py:1964-1976`) | [FATO] O corpo do External Request não tem identificador de mensagem (`docs/guides/whatsapp-concierge.md:118-141`) |
| 4a | Endereço | **PARCIAL** | [FATO] Composição de endereço por texto, pin e cadastro (`shopman/storefront/concierge/address.py:120`, `:142`, `:158`, `:200`); geocodificação pela chave do Maps (`.do/app.alpha-subdomains.yaml:788-790`). Mutação: cai na mesma trava do item 3 | [FATO] Campos de pin ainda não mapeados no flow (`whatsapp-concierge.md:60`) |
| 4b | Forma de pagamento | **PARCIAL (bloqueado pelo provedor)** | [FATO] `place_order` com Pix ou cartão (`tools.py:1204`); mesma trava do item 3 | Nada específico |
| 4c | Avisos e confirmações | **PARCIAL** | [FATO] Notificações transacionais saem por ManyChat → e-mail → SMS (cadeia descrita neste plano, "Canal de venda"); recibo de envio crítico só comprova por e-mail (D27, #1339) | [FATO] Fora da janela de 24 horas só sai template aprovado (`shopman/shop/checks.py:910-913`); 27 templates com copy de referência, estado na Meta a conferir (`docs/reference/whatsapp-templates-meta.md:3-13`) |
| 5 | Triagem: responder o simples, escalar o resto classificado e resumido | **IMPLEMENTADA (02/10, D-018)**, desligada com o Concierge | [FATO] `shopman/storefront/concierge/triage.py` (tabela intenção → destino, regra local, modelo opcional, resumo); ligada no turno antes do modelo de resposta (`service.py`, `run_turn`); grava `envelope["triage"]` em cada entrada, `flags["triage"]` e `summary` na conversa; cartão `concierge_handoff` no sino do Gestor (público `orders`, `shopman/backstage/models/alerts.py`, `ORDER_TYPES`) e `concierge_other_desk` no Admin. Ver [Triagem](#triagem-decidida-em-02102026-e-implementada) | [FATO] O handoff liga o campo `concierge_handoff` no ManyChat e a equipe responde no Live Chat; retorno ao bot fechado (`CONCIERGE_HUMAN_RETURN_ENABLED=false`) |
| 6 | "O pedido de sempre" no momento certo | **INEXISTENTE** (proativo) | [FATO] Só reativo: `last_order` quando o cliente já está conversando (`tools.py:1419`). Não há regra de "quando procurar" | [FATO] Mensagem que a casa inicia é fora da janela: exige template aprovado (`checks.py:910-913`) |

**Onde o operador vê.** [FATO] Desde a D-018, o alerta `concierge_handoff` tem público
`orders` (`shopman/backstage/models/alerts.py`, `ORDER_TYPES`) e aparece no sino do Gestor de
pedidos mesmo quando a conversa não tem pedido (`shopman/backstage/services/alerts.py`, recorte
`orders`). Vaga, parceria e fornecedor geram `concierge_other_desk`, de público `operations`: ficam
no Admin (alertas e o filtro "triagem" da conversa) e não chegam ao sino.

## Triagem: DECIDIDA em 02/10/2026 e implementada

> ✅ **Decisão do dono, 02/10/2026:** *"aprovo a triagem"* (D32, opção 1;
> [D-018](../coordination/DECISIONS.md)). Implementada sem redesenho em
> `shopman/storefront/concierge/triage.py`. O vocabulário são as 12 intenções combinadas com o
> dono em 23/09 (`intent_pilot.DEFAULT_INTENTS`, dado editável no Admin para o rótulo) e as três
> urgências `now` (agora), `today` (hoje), `can_wait` (pode esperar). Nenhuma categoria nova.

**Como classifica.** A triagem roda em todo turno, antes do modelo de resposta, na mesma porta
onde rodava a regex de handoff (`service.run_turn`). Duas camadas:

1. **Regra local, sempre** (sem rede): a política de handoff de sempre
   (`handoff.classify_handoff_request`) para pessoa, reclamação, encomenda especial e alergia, e
   expressões para as outras oito intenções. Quando nada casa, a intenção é `product_question`
   com fonte `default` (o bot responde, como respondia).
2. **Modelo, quando ligado** (`CONCIERGE_TRIAGE_WITH_MODEL`, padrão ligado, com
   `AI_ASSIST_API_KEY`; modelo `CONCIERGE_TRIAGE_MODEL`, vazio = o mesmo do Concierge): propõe
   intenção, urgência e o resumo. Resposta fora das 12 intenções ou das 3 urgências é descartada;
   falha de rede vira regra local.
   **Jev no lugar do modelo** (`CONCIERGE_TRIAGE_CLASSIFIER=jev`, dono 02/10/2026, D-028): a
   intenção é a mais provável do Jev acima de 0,5, com o texto redigido; urgência e resumo ficam
   com a tabela e a regra local. Enquanto a Concierge observa, o Jev decide em sombra a cada ciclo
   do piloto (`concierge_triage_shadow` mostra onde ele e a regra discordam).

O sensível reconhecido pela regra local (pessoa, reclamação, alergia, encomenda especial) vence o
modelo. O sensível proposto pelo modelo também escala.

**Mapeamento intenção → destino** (a tabela aprovada, em `triage.ROUTES`):

| Intenção | Destino | Urgência padrão |
|---|---|---|
| `hours_delivery` (horário, endereço, retirada, entrega) | responde sozinho | hoje |
| `house_info` (como funciona a casa) | responde sozinho | pode esperar |
| `product_question` (sem alergia) | responde sozinho | hoje |
| `order_status` | responde sozinho | agora |
| `order` (pedido simples; fase 1 com o link da loja) | responde sozinho | agora |
| `human` | equipe, sino do Gestor | agora |
| `complaint` | equipe, sino do Gestor | agora |
| `allergy` | equipe, sino do Gestor | agora |
| `allergy` só de glúten (dono, 03/10/2026) | responde sozinho, com o aviso da casa | hoje |
| `special_order` | equipe, sino do Gestor | hoje |
| `order` que o chat não fecha | equipe, sino do Gestor | agora |
| `job`, `partnership`, `supplier_offer` | outra mesa (Admin, sem sino) | pode esperar |
| qualquer uma após 2 tentativas sem resposta útil | equipe, sino do Gestor | agora |

O modelo pode mudar a urgência das intenções que o bot responde e de `special_order`; nunca a das
sensíveis (sempre agora) nem a da outra mesa (sempre pode esperar).

**Glúten saiu da lista sensível (decisão do dono, 03/10/2026).** A pergunta que é SÓ de glúten
("tem algo sem glúten?", "sou celíaco, posso comer o croissant?", "o levain tem glúten?") não vai
mais para a equipe: a resposta é categórica (a casa usa farinha de trigo em tudo o que assa e não
oferece nada sem glúten, pela contaminação cruzada). A Concierge responde, sem modelo e sem busca,
com o aviso de produção compartilhada da casa (`Shop.food_safety_notice`, editável no Admin, o
mesmo texto da página de cada produto em Ingredientes e restrições) e, se a fala cita um produto do
cardápio, os alérgenos declarados dele. Uma fonte só: editar o aviso muda a loja e a Concierge
juntas. A triagem grava `intent=allergy`, `destination=answer`, `answered_by=gluten_notice`
(`shopman/storefront/concierge/gluten.py`). Regras de segurança: nada afirma "sem glúten" nem
apresenta produto como seguro (lista de alérgenos vazia não vira "não tem"); glúten junto de outra
alergia manda a mensagem INTEIRA para a equipe (responder metade daria a impressão de que a outra
metade foi respondida); alergia sem dizer a quê, as outras alergias ("tem castanha no panetone?"),
reclamação e pedido de pessoa seguem com a equipe; sem aviso cadastrado, glúten também vai para a
equipe.

**Onde a proposta não dizia, o lado seguro (escalar ou não acordar ninguém):**

- **"Pedido que o chat não fecha"** virou regra: na fase 1 (turno sem autoridade comercial), o
  segundo turno SEGUIDO com intenção `order` vai para a equipe, agora. O primeiro recebe resposta
  (o link da loja). Com autoridade comercial (fase 2), o chat fecha e não escala.
- **"2 tentativas sem resposta útil"** virou: duas falhas seguidas do modelo de resposta
  (`consecutive_failures >= 2`) vão para a equipe, agora, em vez de repetir "indisponível".
- **Outra mesa também cala o bot** (handoff no ManyChat): quem escreve não é cliente, e a resposta
  é de uma pessoa da casa.
- **Fora do expediente** nada toca ninguém: o cartão espera no sino. Não estava na proposta.

**O que o operador vê.** Um cartão por conversa escalada (`triage.alert_message`): a intenção (o
rótulo do Admin) e a urgência, o resumo de uma ou duas linhas, o nome do cliente e o último pedido
quando há, e onde responder (Live Chat do ManyChat), com o caminho da transcrição no Admin. O
resumo fica em `Conversation.summary`; a triagem da última mensagem, em `flags["triage"]`
(chaves em `docs/reference/data-schemas.md`). No Admin da conversa: coluna e filtro "triagem"
(Com a equipe, Outra mesa, Respondida pelo Concierge). O resumo do modelo e o da regra local
saem sem documento, número longo, dado financeiro e contato; endereço, alergia e pedido ficam,
porque são o que a equipe precisa ler.

**O que ficou de fora:** botão no cartão que abre a conversa no Admin (o Gestor só abre caminhos
do próprio app; o caminho vai no texto) e botão "devolver ao bot" no cartão (retorno fechado,
`CONCIERGE_HUMAN_RETURN_ENABLED=false`; a ação existe no Admin).

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

**Estado no spec versionado** (`.do/app.alpha-subdomains.yaml`). [FATO] Conferido contra o app vivo
em 02/10/2026 (`doctl --context shopman-do-app-admin apps spec get`, só leitura): os dez valores
abaixo são iguais no vivo; `AI_ASSIST_API_KEY`, `CONCIERGE_API_KEY` e `MANYCHAT_API_TOKEN` são
`SECRET` com valor cifrado no vivo (se a chave é válida: NÃO VERIFICADO); `CONCIERGE_HANDOFF_FIELD`
não está no vivo nem no arquivo e cai no padrão `concierge_handoff` (`config/settings.py:1527`).

| Variável | Valor | Linha |
|---|---|---|
| `SHOPMAN_CONCIERGE_ENABLED` | `'false'` | `:592-595` |
| `CONCIERGE_MANYCHAT_WHATSAPP_ACTIVE` | `'true'` | `:596-599` |
| `CONCIERGE_CONTRACT_VERSION` | `'3'` | `:606-609` |
| `CONCIERGE_READ_ONLY` | `'true'` | `:610-613` |
| `CONCIERGE_MANYCHAT_EVENT_ID_VERIFIED` | `'false'` | `:614-617` |
| `CONCIERGE_IDENTITY_LINK_ENABLED` | `'false'` | `:623-626` |
| `CONCIERGE_HUMAN_RETURN_ENABLED` | `'false'` | `:627-630` |
| `CONCIERGE_ALLOWED_SUBSCRIBERS` | um subject (coorte fechada) | `:645-648` |
| `CONCIERGE_OPERATION_MODE` | `observe` | `:659-662` |
| `CONCIERGE_OBSERVATION_ENABLED` / `_ALLOW_ALL_SUBJECTS` | `'true'` / `'true'` | `:663-666`, `:675-678` |

**O que muda ao ligar cada um, em ordem** ([FATO] pela leitura de
`shopman/storefront/concierge/service.py:79-98`, `:835-844` e
`webhook.py:97-129`):

0. **Conferir antes:** `manage.py concierge_check --live` no app (ver
   "Verificação"). Desligado, ele só informa o modo; ligado, lista o que falta.
1. **`CONCIERGE_OPERATION_MODE=observe` → `assist`.** É o primeiro portão: em
   `observe`, `disabled_reason()` devolve `observation_only` mesmo com o switch
   ligado (`shopman/storefront/concierge/service.py:90-91`). **Em `observe`, ligar
   `SHOPMAN_CONCIERGE_ENABLED` não muda nada**: o webhook continua respondendo
   `disabled` e nenhum turno roda. Por isso o modo vem primeiro. Desde 02/10/2026
   (dono: "ligar só para o meu contato, sem afetar nenhum cliente"), em `assist` a
   coorte (`CONCIERGE_ALLOWED_SUBSCRIBERS`) é atendida e **quem está fora dela continua
   só observado**, como em `observe` (`service._observation_policy`). A coleta do piloto
   de intenções e a sombra do Jev seguem; o atendido não é observado em dobro.
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

- [x] Triagem construída conforme a D32 decidida (D-018: classificação, resumo em
      `Conversation.summary`, cartão no sino do Gestor, outra mesa no Admin).
- [ ] `manage.py concierge_check --live` sem pendência no app (system check
      `SHOPMAN_W022`/`SHOPMAN_W023` limpo no release).
- [x] Decidir o que acontece com a observação passiva (item 1 acima): ela não acaba mais em
      `assist` para quem está fora da coorte (02/10/2026). Antes disso o dono tinha aceitado
      perdê-la (D-018), porque não havia outro jeito.
- [x] `AI_ASSIST_API_KEY` e `CONCIERGE_API_KEY` com valor no app vivo: `SECRET` com valor
      cifrado em 02/10/2026 (`apps spec get`). Se a chave da Anthropic é válida: NÃO VERIFICADO
      (só um turno de verdade prova).
- [ ] Flow do ManyChat: External Request em **toda** mensagem do assinante, não
      só no `#c`, confirmado no grafo do flow (`whatsapp-concierge.md:112-116`);
      condição `concierge_handoff == "1"` pausando a automação.
- [ ] `directive-worker` vivo (o turno roda na fila de diretivas).
- [ ] FAQ revisada **e publicada** no Admin (é a fonte das respostas do item 1). [FATO] Alpha,
      02/10/2026 (leitura pela conexão direta): 14 perguntas em `shop_faqentry`, **0 publicadas**;
      a busca só lê `is_published=True` (`shopman/storefront/presentation/public_information.py:128`,
      `:146`). Sem publicar, o Concierge não tem FAQ nenhuma. É o item `faq_initial` de
      `config/public_copy_review.py` (aval do dono, 17/09). Tela: `/admin/shop/faqentry/`.
- [ ] Copy de abertura `CONCIERGE_GREETING` e de handoff revisadas pelo dono.
- [ ] Ensaio com o número do dono na coorte fechada, pelos 10 passos de
      `whatsapp-concierge.md:212-235`.
- [ ] Rotina de contenção conhecida: desligar `SHOPMAN_CONCIERGE_ENABLED` ou
      `CONCIERGE_MANYCHAT_WHATSAPP_ACTIVE` (`whatsapp-concierge.md:242-246`).

## Verificação: o que confere o Concierge

| Comando | Onde | O que compara |
|---|---|---|
| `manage.py manychat_flows --check` | `shopman/shop/management/commands/manychat_flows.py` | Lista os flows da conta pela API (`getFlows`) e confere se cada `NotificationTemplate.whatsapp_flow_ns` configurado ainda existe no ManyChat. **Não cobre o Concierge** (e diz isso na saída) |
| system check `check_whatsapp_flow_coverage` | `shopman/shop/checks.py` (`@register(deploy=True)`) | Só campanhas de **Marketing** (fora do go-live): `SHOPMAN_W014`, `SHOPMAN_W020`. **Não cobre o Concierge** |
| system check `check_concierge_readiness` | `shopman/storefront/checks.py` (`@register(deploy=True)`) | **Cobre o Concierge** (D-018). Desligado: silêncio, o deploy de hoje passa limpo. Ligado: `SHOPMAN_W022` quando ele não vai responder (modo `observe` ou desconhecido, contrato diferente de 3, sem `AI_ASSIST_API_KEY`, sem conexão ativa, coorte vazia) e `SHOPMAN_W023` quando falta peça do ManyChat (`CONCIERGE_API_KEY`, `MANYCHAT_API_TOKEN`, campo de atendimento humano, fuso da janela). Só Warning: tudo isso já falha fechado em runtime, e um Error derrubaria o `check --deploy` do release (a lição do W020) |
| `manage.py concierge_check [--live]` | `shopman/storefront/management/commands/concierge_check.py` | O mesmo check, legível, com saída 1 quando há pendência; com `--live`, pergunta ao ManyChat (`getCustomFields`) se o campo de atendimento humano existe |

[FATO] O que nenhum comando enxerga: se o flow do ManyChat chama o External Request em **toda**
mensagem. A API do ManyChat não expõe o conteúdo do flow; essa conferência continua sendo o ensaio
manual do checklist.

**Saída real ao rodar localmente (01/10/2026, `config.settings_test`, sem banco migrado):**
com `SHOPMAN_CONCIERGE_ENABLED=true`, `CONCIERGE_OPERATION_MODE=observe` e
`CONCIERGE_CONTRACT_VERSION=3`, `manage.py concierge_check` sai com
`CommandError: 3 pendência(s) no Concierge.` e lista `SHOPMAN_W022` para o modo `observe`
("o Concierge só observa e não responde ninguém"), para a falta de `AI_ASSIST_API_KEY` e para a
falta de conexão ativa. Desligado, só informa o modo e sai com 0. **NÃO VERIFICADO no app vivo**:
o `--live` precisa do `MANYCHAT_API_TOKEN`, que só existe lá.

**Com os valores do app vivo (02/10/2026).** O comando não toca o banco (lê settings e, com
`--live`, faz um GET no ManyChat), então rodá-lo no alpha não acrescenta nada além do `--live`.
Rodado localmente com os valores não secretos do `apps spec get` e os três segredos preenchidos:
como está (`SHOPMAN_CONCIERGE_ENABLED=false`) sai 0 com "Concierge desligado [...] modo atual:
observe."; simulando o switch ligado em `observe`, sai 1 só com `SHOPMAN_W022` do modo; simulando
`assist` + switch, não sobra pendência de configuração. (O `SHOPMAN_W023` de `MANYCHAT_API_TOKEN`
que aparece localmente é do `config/settings_test.py:138`, que zera o token.) O campo
`concierge_handoff` existe no ManyChat e é textual (`"1"`/`"0"`), pela consulta só leitura de
11/09 (`docs/reports/conversational-operational-excellence-implementation-2026-09-11.md:603-608`);
o `--live` de hoje: NÃO VERIFICADO.

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
