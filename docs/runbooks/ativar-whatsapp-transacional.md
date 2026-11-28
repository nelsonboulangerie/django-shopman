# Runbook — Ativar WhatsApp transacional (notificações de pedido)

> Liga as notificações de pedido por WhatsApp. **A engenharia está 100% pré-ligada**:
> eventos já disparam, adapters registrados, fallback texto→SMS→email funcionando.

> ⛔ **O passo 3 deste runbook mudou duas vezes; o texto abaixo foi corrigido em 21/11/2026.**
> O campo "flow do WhatsApp" é **somente leitura no Admin**
> (`NotificationTemplateAdmin.readonly_fields`), e o único gravador do `whatsapp_flow_ns` é
> `marketing_platform_configuration.configure_whatsapp_flow`. Em 25/09 ele só aceitava o
> anúncio de Marketing; hoje aceita qualquer evento de `WHATSAPP_EVENT_LABELS`, pela tela
> Marketing → Configurações → Plataformas → WhatsApp → "Avisos automáticos", sem deploy.
> Ver "Onde se configura".

> **Este runbook não liga Marketing.** Pedido/OTP/estoque são notificações
> transacionais; campanhas usam outro ledger, outro catálogo de fluxo, consentimento de
> Marketing e o cockpit `marketing-nuxt`. Não copie fallback, template ou readiness
> deste caminho para campanha. Ver
> [`marketing-surface-contract.md`](../reference/marketing-surface-contract.md).

## Como o sistema decide o canal

`ChannelConfig.notifications`: backend primário `manychat` (WhatsApp) → fallback `sms` →
`email`. Cada evento de pedido chama `notify(event, recipient, context)`. O adapter ManyChat:
1. usa o **flow** configurado para o evento, se houver → dispara `/sending/sendFlow`;
2. senão, envia a **mensagem de texto** (campo `body` do template) → `/sending/sendContent`.

## Onde se configura

Cada evento é um `NotificationTemplate`. Campos:
- **mensagem** (`body`) — texto enviado quando não há flow (fallback dentro da janela 24h).
  Continua editável no Admin.
- **flow do WhatsApp (ManyChat)** (`whatsapp_flow_ns`) — namespace do flow
  (ex.: `content20250401120000_123456`). **Preenchido → dispara o flow aprovado.**

Precedência (`notification_manychat.send`): o `whatsapp_flow_ns` do registro vence o
`settings.MANYCHAT_FLOW_MAP`, que fica como fallback de bootstrap.

**Há dois caminhos para gravar o `whatsapp_flow_ns`, e nenhum é mais o Admin:**

| Caminho | Cobre | Custo |
|---|---|---|
| Marketing → Plataformas (`WhatsAppTemplateView`), seção "Avisos automáticos" | todo evento de `WHATSAPP_EVENT_LABELS` (o anúncio e os transacionais) | nenhum; vale na hora, com o flow revalidado no catálogo vivo, CAS, confirmação, TOTP e auditoria |
| `MANYCHAT_FLOW_MAP` em `config/settings.py` | só os mapeamentos antigos; evento novo não entra aqui (ADR-042) | um PR e um deploy (~6 min) |

⚠️ **O Admin não grava este campo.** `NotificationTemplateAdmin` o traz em
`readonly_fields` e o form o marca `disabled`, apontando para Marketing → Plataformas.
O caminho de cada evento é a tela de Marketing. O `MANYCHAT_FLOW_MAP` do `settings.py`
fica só para os mapeamentos antigos: configuração nova de loja não entra por `settings`
(ADR-042, trava `scripts/check_tenant_config.py`).

## Passos (Pablo)

0. **Criar os campos personalizados no ManyChat** (tipo Texto), senão a variável do
   template aprovado sai em branco e nada falha. Lista na seção "Campos personalizados no
   ManyChat" do doc dos templates.
1. **Submeter os templates à Meta**, copiando de
   [`docs/reference/whatsapp-templates-meta.md`](../reference/whatsapp-templates-meta.md).
   **Tudo Utility ou Marketing — não há Authentication**, porque o ManyChat não tem essa
   categoria; o OTP vai por SMS (ver abaixo). Aguardar aprovação (~24-48h).
2. **Criar um Flow no ManyChat** para cada template aprovado e copiar o **namespace**.
3. **Mapear evento → namespace** pela tela de Marketing (Configurações → Plataformas →
   WhatsApp → "Avisos automáticos"): escolher a mensagem e o modelo aprovado da lista.
4. **Conferir**: `manage.py manychat_flows --check` confronta cada namespace configurado
   com os que existem de fato na conta. Flow apagado é envio que falha destinatário por
   destinatário, sem aviso.

Mapeie só os eventos que quiser; os demais caem no texto — que a Meta só entrega dentro da
janela de 24h (`HTTP 400 code 3011` fora dela).

Essa prontidão vale somente para notificações transacionais. No Marketing, ausência de
adapter, flow ativo verificado ou prova fresca deixa WhatsApp bloqueado/indisponível;
não há fallback escondido para SMS, email ou Meta Cloud direto.

## Eventos

`order_received`, `order_accepted`, `order_rejected`, `order_preparing`,
`order_ready_pickup`, `order_ready_delivery`, `order_dispatched`, `order_delivered`,
`order_cancelled`, `preorder_reminder`, `payment_requested`, `payment_link_sent`,
`payment_confirmed`, `payment_reminder`, `payment_failed`,
`waitlist_available`, `waitlist_released`, `stock_arrived`, `purchase_request`.

> ⚠️ Esta lista dizia `order_confirmed`, **que o código nunca emitiu** — o evento é
> `order_accepted`. O mapa conferido chave a chave contra
> `notification_manychat.MESSAGE_TEMPLATES` mora no doc dos templates; esta lista é o
> resumo dele, não uma segunda fonte.

> OTP (login) **não** vai por WhatsApp (ManyChat não tem categoria Authentication) — vai
> por SMS (Comtele).

## Alternativa — Meta Cloud API direto

Adapter `notification_whatsapp` (spike, inerte até `WHATSAPP_PHONE_NUMBER_ID` +
`WHATSAPP_ACCESS_TOKEN`). Decisão ManyChat-vs-direto:
[`WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN`](../plans/completed/WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md).
