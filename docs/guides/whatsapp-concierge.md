# Concierge de WhatsApp (ManyChat + modelo de linguagem)

Guia de configuração e operação do concierge: o assistente que atende o WhatsApp
da casa e fecha pedidos por conversa. Um flow só no ManyChat, um webhook, a
resposta volta pela API. Arquitetura e decisões no
[WHATSAPP-CONCIERGE-PLAN](../plans/WHATSAPP-CONCIERGE-PLAN.md) e na
[ADR-026](../decisions/adr-026-concierge-lingua-do-modelo-dinheiro-do-codigo.md);
o login por WhatsApp continua sendo o [access link](whatsapp-access-link.md), e os
dois flows convivem no mesmo número.

## A ideia

O cliente escreve como escreveria para uma pessoa. O ManyChat manda o texto para
a casa e **não espera resposta**: a casa responde `202` na hora, processa o turno
no worker de diretivas (modelo + ferramentas que só chamam services) e devolve a
resposta pela API do ManyChat, dentro da janela de 24 h que o cliente acabou de
abrir. O modelo escolhe as palavras; preço, estoque, prazo e Pix vêm do Shopman.

Quando o cliente pede uma pessoa, o concierge liga um campo no assinante
(`concierge_handoff = "1"`), o flow para de chamar a casa e pausa as automações:
a equipe atende no Live Chat do ManyChat. Devolver a conversa ao bot é uma ação
no Admin.

## Fluxo

```
1. Cliente escreve no WhatsApp da casa
2. ManyChat (flow) → Condition: concierge_handoff == "1"?
     sim → Pause all automations (equipe no Live Chat); fim
     não → External Request POST /api/webhooks/manychat/conversation/
             { subscriber_id, text, first_name, last_name }   X-Api-Key
           ← 202 em < 1 s
3. Django grava a mensagem, identifica o cliente e enfileira concierge.turn
4. directive-worker roda o turno (modelo + ferramentas) e envia a resposta
   pela API do ManyChat (sendContent, texto livre)
5. Cliente recebe a resposta; o pedido, quando fechado, aparece no Gestor
   (coluna WhatsApp) e no acompanhamento /pedido/<ref>/ da loja
```

## Variáveis de ambiente

```env
# Liga o concierge. false = o webhook responde "disabled" e nada roda (kill switch).
SHOPMAN_CONCIERGE_ENABLED=true

# Credencial da Anthropic (a mesma do assist de texto do Gestor).
AI_ASSIST_API_KEY=<chave>

# Chave que o External Request apresenta no header X-Api-Key. Sem ela, fora de
# DEBUG, o endpoint falha FECHADO. Default: DOORMAN_ACCESS_LINK_API_KEY.
CONCIERGE_API_KEY=<segredo forte>

# API do ManyChat (já usada pelas notificações): é por ela que a resposta volta.
MANYCHAT_API_TOKEN=<token>

# Opcionais (defaults no config/settings.py, bloco SHOPMAN_CONCIERGE)
CONCIERGE_MODEL=claude-sonnet-5          # claude-opus-5 é troca de env
CONCIERGE_EFFORT=low
CONCIERGE_MAX_TURNS_PER_DAY=80           # teto por conversa, por dia
CONCIERGE_HANDOFF_FIELD=concierge_handoff  # nome do campo personalizado no ManyChat
CONCIERGE_CHANNEL_REF=whatsapp           # Channel.ref dos pedidos do chat
```

Lista completa: `config/settings.py`, bloco `SHOPMAN_CONCIERGE`.

## O canal de venda no banco vivo

Os pedidos do chat nascem no `Channel` ref `whatsapp` (Pix e cartão a
`at_commit`, confirmação automática em 5 min, listing `whatsapp` espelhando a
web). O seed já o cria; no banco vivo, sem reseed:

```bash
.venv/bin/python manage.py bootstrap_whatsapp_channel
```

Idempotente: cria o canal e o listing se faltarem, ativa se estiverem inativos,
não toca no que já existe. Ver [commands.md](../reference/commands.md#bootstrap_whatsapp_channel).

## Configuração do flow no ManyChat

Os mesmos cuidados do access link valem aqui, e dois deles mordem: em contato de
WhatsApp o campo sistêmico `phone` é **nulo** (o telefone é `whatsapp_phone`; a
casa o busca pelo `getInfo`, você não precisa mandar), e **variável digitada à
mão não renderiza**: toda variável entra pelo seletor do ManyChat.

1. **Campo personalizado** (Settings → Fields → User Fields): crie
   `concierge_handoff`, tipo **Text**. O nome tem de ser o mesmo de
   `CONCIERGE_HANDOFF_FIELD` (default `concierge_handoff`). Não crie como
   booleano: a casa grava `"1"` e `""`.

2. **Trigger.** Uma automação `Shopman - Concierge` com o trigger **Default
   Reply** do WhatsApp (toda mensagem que não casa com outro keyword). Se
   preferir abrir devagar, use um **Keyword** (`pedir`, `cardápio`) e migre para
   Default Reply na F3. O `#menu` do access link continua com o flow dele; os
   dois convivem porque o keyword ganha do Default Reply.

3. **Condition** (primeiro nó): `concierge_handoff` **is equal to** `1`.
   - **Sim** → ação **Pause all automations** (o tempo que a casa usar; 24 h
     serve) e, se quiser, "Mark conversation as open" + assign para a equipe.
     Nada mais: a mensagem fica na transcrição da casa, o bot não responde.
   - **Não** → segue para o External Request.

4. **External Request** (Dev Tools, plano Pro):
   - Method: `POST`
   - URL: `https://api.<seu-domínio>/api/webhooks/manychat/conversation/`
   - Header: `X-Api-Key: <CONCIERGE_API_KEY>`
   - Body (JSON), cada valor escolhido **pelo seletor de variáveis**:
     ```json
     {
       "subscriber_id": "{{Subscriber ID}}",
       "text": "{{Last Text Input}}",
       "first_name": "{{First Name}}",
       "last_name": "{{Last Name}}"
     }
     ```
   - **Não mapeie a resposta** em campo nenhum. O corpo é `{"status": "queued"}`
     (ou `duplicate`, `handoff`, `disabled`) e o código é `202`. A resposta ao
     cliente chega depois, pela API. Mapear resposta síncrona foi o que entregava
     a resposta do turno anterior quando a casa demorava.
   - Teste com o botão **Test request** do ManyChat: espere `202`. `401` é chave;
     `400` é corpo sem `subscriber_id`; `200` com `status: "empty"` é texto vazio
     (a variável não veio e o `getInfo` também não trouxe nada).

5. **Depois do External Request:** nada. Sem mensagem de "aguarde", sem
   typing. O worker responde em segundos.

6. **Devolver ao bot.** No Admin, em **Conversas do concierge** (`/admin/shop/conversation/`), filtre
   por estado "Com a equipe", selecione e rode a ação **Devolver ao concierge**.
   A casa limpa o campo `concierge_handoff` no ManyChat e o bot volta a
   responder na próxima mensagem. Se a automação ainda estiver pausada no
   ManyChat, ela retoma sozinha ao fim do prazo da pausa, ou o atendente
   despausa no Live Chat.

## O que o cliente vive

- Abertura curta, sem emoji, dizendo que é um assistente da casa e fazendo uma
  pergunta (copy `CONCIERGE_GREETING`, editável no Admin).
- Uma pergunta por vez, opções em texto (até 3).
- Recap do pedido linha a linha, com total e prazo, e um "sim" explícito antes
  de fechar. Sem "sim", não há pedido.
- Pix em mensagem separada (só o código, para copiar e colar); cartão como link.
- Confirmação com o número do pedido e o link de acompanhamento na loja.
- "Falar com a equipe" sempre disponível; áudio e imagem recebem uma resposta
  fixa pedindo texto (`CONCIERGE_MEDIA_UNSUPPORTED`).

## Como ler as transcrições

`/admin/shop/conversation/`. A lista mostra cliente, estado (Ativa / Com a
equipe / Encerrada), última mensagem, turnos do dia, motivo do handoff e tokens
(entrada / saída / cache). Busca por telefone, nome ou id do assinante.

No detalhe, a aba **Transcrição** lista tudo em ordem: mensagem do cliente,
chamada de ferramenta (nome e argumentos), resultado (primeiros 200
caracteres), resposta enviada ("não entregue" quando o ManyChat recusou) e notas
da casa (handoff, volta ao bot). A aba **Pedido em andamento** mostra a sacola e
o orçamento vigente; **Consumo**, os contadores.

Nada se edita ali. A única ação é devolver ao concierge.

## Kill switch

`SHOPMAN_CONCIERGE_ENABLED=false` e redeploy: o webhook responde `202` com
`disabled`, nenhuma diretiva é enfileirada, o modelo não é chamado. O flow do
ManyChat pode ficar como está; para o cliente não ficar sem resposta, ligue no
ManyChat uma mensagem fixa depois do External Request enquanto o concierge
estiver desligado (a copy `CONCIERGE_UNAVAILABLE` serve de modelo).

Sem chave da Anthropic (`AI_ASSIST_API_KEY` vazia) o efeito é o mesmo: o
concierge se considera desligado.

## Diagnóstico

| Sintoma | Onde olhar | Causa provável |
|---|---|---|
| Cliente escreve e nada volta | log do `directive-worker`, filtre `concierge.` | worker parado; diretiva `concierge.turn` com falha (veja `Directive` no Admin); transporte inerte (`MANYCHAT_API_TOKEN` vazio) |
| External Request devolve `401` | painel do ManyChat, Test request | `X-Api-Key` diferente de `CONCIERGE_API_KEY` (ou do fallback `DOORMAN_ACCESS_LINK_API_KEY`) |
| External Request devolve `202` com `disabled` | idem | `SHOPMAN_CONCIERGE_ENABLED=false` ou `AI_ASSIST_API_KEY` vazia |
| Resposta registrada como "não entregue"; log do adapter com erro `3011` | transcrição no Admin + log | janela de 24 h fechada ou canal do assinante não é WhatsApp (contato do Instagram) |
| Handoff nunca volta ao bot | Admin mostra "Ativa" mas o ManyChat segue pausado | nome do campo no ManyChat difere de `CONCIERGE_HANDOFF_FIELD`; ou a automação ainda está dentro do prazo de "Pause all automations" |
| Concierge responde a copy de "fora do ar" | `OperatorAlert` `concierge_unavailable` | três falhas seguidas do modelo nessa conversa: chave inválida, modelo indisponível, `CONCIERGE_MODEL` com nome errado |
| Cliente não consegue fechar pedido, recebe `CONCIERGE_NO_PHONE` | detalhe da conversa, campo telefone vazio | contato sem `whatsapp_phone` (veio pelo Instagram); peça para entrar pelo site |
| Mesmo cliente recebe resposta duplicada | transcrição: duas inbound iguais no mesmo minuto | reenvio do ManyChat sem id de mensagem; o dedupe por hash cobre o mesmo minuto, fora dele é insistência real |

## Testes

```bash
make test-framework   # service, agente (cliente fake), ferramentas, webhook, admin
```

Admin: `shopman/shop/tests/test_concierge_admin.py`. Receita de teste local com
túnel: seção "Como testar localmente" do
[plano](../plans/WHATSAPP-CONCIERGE-PLAN.md#como-testar-localmente).
