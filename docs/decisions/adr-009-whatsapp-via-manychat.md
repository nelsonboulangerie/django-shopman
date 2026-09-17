# ADR-009 — WhatsApp via ManyChat: vendor lock-in consciente

**Data**: 2026-04-18
**Atualizado**: 2026-09-17
**Status**: Accepted

---

## Contexto

Shopman se posiciona como "WhatsApp-first" em diversos eixos: autenticação pelo WhatsApp quando o canal permite, fallback SMS/email quando o canal não permite, notificações de pedido via WhatsApp, AccessLink (magic link) entregue por bot de WhatsApp para transição chat→web, `origin_channel="whatsapp"` roteando retornos pelo mesmo canal. É uma decisão de produto central — a experiência do cliente gira em torno do WhatsApp como superfície primária, especialmente para delivery e pré-compra.

Tecnicamente, essa integração acontece **100% via ManyChat** — plataforma SaaS terceirizada que faz a ponte entre Shopman e a Meta Cloud API (WhatsApp Business). Shopman não fala direto com a Meta. A memória de projeto `feedback_whatsapp_via_manychat.md` registra isso como norma ativa.

Esta ADR-009 documenta explicitamente a decisão para que futuros contribuidores entendam **por que** a ponte é ManyChat e **qual o risco** assumido.

## Decisão

**Toda integração WhatsApp em Shopman é mediada por ManyChat**, não pela Meta Cloud API direta. Isso inclui:

- Autenticação WhatsApp-first por AccessLink conversacional ou template WhatsApp aprovado.
- Envio de notificações transacionais (order_confirmed, order_dispatched, etc.) via ManyChat broadcast API.
- Recebimento de mensagens de cliente via ManyChat webhook → Shopman.
- Criação de AccessLink disparada por bot de ManyChat via API interna.
- Fluxos conversacionais de pré-compra (ex.: "quero fazer um pedido") são desenhados e mantidos no editor visual do ManyChat, não em código Shopman.

### Emenda de segurança para Marketing — 2026-09-09

O caminho de Marketing é **ManyChat-only**. O adapter Meta Cloud API direto não é
fallback elegível, mesmo se estiver registrado ou configurado. Uma troca ou lane
paralela de fornecedor exige revisão explícita desta ADR; não pode nascer por
detecção oportunista de credencial. O console continua disponível apenas como
transporte inerte de desenvolvimento/teste e nunca conta como readiness produtivo.

Os flows atuais do ManyChat materializam variáveis por meio de campos persistentes
do subscriber antes de chamar `sendFlow`. Não há evidência documental nem ensaio
sandbox que prove snapshot atômico/isolamento quando dois commands concorrentes
atingem o mesmo subscriber. Portanto, qualquer flow de Marketing dependente desses
campos permanece `blocked_unverified`, inclusive quando token e flow estão válidos.
Credencial não remove esse bloqueio.

O bloqueio só pode ser revisto após o ensaio externo G-H03 provar isolamento,
respostas, rate limits, `Retry-After`, efeitos de timeout, redaction e eventual
receipt/callback correlacionável. O ensaio usa target sintético/verificado, no máximo
um destinatário, e precisa de autorização específica; esta implementação local não
o executa.

Até essa prova:

- `200`/success significa apenas `accepted_unconfirmed`, nunca “entregue”;
- subscriber ID não é receipt e não pode virar um message ID fabricado;
- resposta ambígua após possível write é `unknown` e não sofre retry automático;
- o adapter bloqueia antes de resolver subscriber, gravar custom fields ou fazer
  qualquer chamada do caminho Marketing;
- readiness, aprovação e deploy check expõem o mesmo reason code reparável:
  `manychat_custom_fields_unverified`.

> A emenda de 2026-09-17, abaixo, substitui a exigência de prova externa de
> isolamento por isolamento construído do nosso lado. Os demais limites desta seção
> continuam valendo.

### Emenda de 2026-09-17 — isolamento por construção e abertura por etapas

**Decisão do dono (Pablo, 17/09):** resolver a corrida por construção, não por promessa
do fornecedor, e abrir por canário.

A prova externa de que o ManyChat "não mistura" campos entre flows concorrentes é
fraca: a corrida depende de tempo, e um ensaio que não a reproduz não prova nada. O
ponto de falha é conhecido e fica do nosso lado — a sequência "gravar N campos
persistentes → `sendFlow`" para o MESMO assinante. Então a mistura passa a ser
impossível por construção:

1. **Uma mensagem com flow por assinante por vez.** Antes de gravar qualquer campo, o
   adapter reserva o assinante no cache compartilhado
   (`cache.add("manychat:flow-busy:<subscriber_id>", ..., timeout=SETTLE)`, com
   `SETTLE = SHOPMAN_MANYCHAT_FLOW_SETTLE_SECONDS`, padrão 120 s). A reserva não é
   liberada no fim do envio: ela cobre justamente o tempo em que o flow ainda vai ler os
   campos, e expira sozinha. Vale para todo envio com flow, inclusive de pedido;
   `sendContent` não grava campo e não passa por ela.
2. **Quem não reserva não escreve nada.** O resultado é `subscriber_busy` (ou
   `flow_reservation_unavailable` quando o cache não responde): retentável, nunca
   falha final e nunca `unknown`. O "Me avise" devolve a entrega à fila e reagenda a
   directive para depois da janela sem gastar tentativa; o ledger durável devolve a
   tentativa a `PREPARED` e o destino a `queued` com `next_attempt_at ≥ SETTLE`,
   reutilizando o mesmo token; a onda legada de campanha reagenda só os refs
   ocupados; o teste sandbox responde "aguarde" sem gravar aceite.
3. **Cache compartilhado é pré-requisito.** Com LocMem/Dummy/arquivo cada processo
   reserva sozinho e a serialização não vale; o estado continua bloqueado
   (`manychat_flow_serialization_unavailable`) e o check de deploy `SHOPMAN_W021`
   explica — como **aviso**, nunca erro (lição do `SHOPMAN_W020` em 16/09).
4. **Três modos, padrão fechado** — `SHOPMAN_MARKETING_WHATSAPP_MODE`:
   - `blocked` (padrão): comportamento anterior, `manychat_custom_fields_unverified`;
   - `canary`: exige `SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS` não vazio e
     serialização ativa. Só os refs listados recebem campanha e "Me avise"; outro ref e
     assinatura anônima ficam de fora — suprimidos no claim com
     `whatsapp_canary_recipient_excluded` e recusados pelo adapter na última porta.
     A prontidão aparece como `degraded` com a contagem, nunca os refs;
   - `open`: exige serialização ativa; todo contato elegível recebe.

**O que G-H03 ainda cobria e continua como limitação conhecida:** não há receipt nem
callback correlacionável de entrega; `Retry-After` e rate limit reais do ManyChat não
foram medidos; o efeito de timeout depois de uma escrita continua ambíguo. O sistema
já trata isso de forma conservadora — `200` é `accepted_unconfirmed`, resposta ambígua
após possível escrita é `unknown` sem retry automático, e subscriber ID nunca vira
receipt. A janela de 120 s é escolha operacional, não medida: revisar com a latência
observada no canário.

## Motivação

1. **Compliance com Meta**: ManyChat é Meta Business Partner oficial, com template approval, opt-in gestão, verificação de conta, e rate limiting já resolvidos. Integração direta com Meta Cloud API exigiria equipe dedicada a gerenciar estes atritos.
2. **Editor visual de fluxos**: equipe de produto/operação pode ajustar fluxos conversacionais sem deploy Shopman — requisito funcional para padaria que itera tom/copy frequentemente.
3. **Tempo de implementação**: ManyChat webhook + API é maturo, documentado, suporta desde dia 1. Construir integração Meta equivalente é mês(es) de trabalho.
4. **Preço da fase inicial**: para volumes < 10k mensagens/mês, ManyChat é custo-efetivo e operacional.

## Limite canônico do login web

ManyChat não deve ser tratado como provedor genérico de OTP por telefone
anônimo. O endpoint `/fb/sending/sendContent` envia conteúdo para um
`subscriber_id` ManyChat já resolvido; ele não substitui conversa iniciada pelo
cliente, template aprovado pela Meta, nem permissão de importação/resolução de
contatos no ManyChat.

Para cliente que chega pela web, os caminhos canônicos são:

1. **Conversa iniciada pelo cliente no mesmo número**: o storefront abre o
   WhatsApp com mensagem pronta; a automação ManyChat chama
   `POST /api/auth/access/create/`; o Shopman devolve um AccessLink curto.
2. **Outbound sem conversa aberta**: exige template WhatsApp aprovado e suporte
   operacional do ManyChat para resolver/criar o contato antes do envio.

SMS permanece fallback, não superfície principal.

## Limite de negócio no ManyChat

A restrição "sem pricing/stock no ManyChat" não significa que o bot não possa
mostrar preço, disponibilidade, prazo, taxa ou opções de produto ao cliente.
Significa que o ManyChat não pode ser a fonte de verdade nem reimplementar
essas regras no editor visual.

O fluxo correto é:

1. ManyChat coleta intenção conversacional: itens, quantidade, fulfillment,
   endereço, janela desejada, telefone, opt-in e ação do cliente.
2. ManyChat chama um endpoint ou fluxo Shopman idempotente.
3. Shopman resolve preço, promoções, disponibilidade, holds, payment gate,
   policy do canal e próxima ação usando Orderman, Payman, Stockman,
   Guestman, Doorman, ChannelConfig, services e projections.
4. ManyChat apresenta ao cliente a projection/resposta retornada por Shopman.

O risco de colocar pricing/stock no ManyChat é operacional, não dogmático:

- preço em bot fica defasado de Offerman/pricing modifiers/cupons/loyalty;
- disponibilidade em bot ignora Stockman, holds, demanda planejada, D-1
  excluído por canal e concorrência;
- copy de promessa pode divergir do timer real de confirmação/pagamento;
- auditoria e testes ficam divididos entre repo e editor visual;
- um ajuste operacional urgente exigiria sincronizar dois motores de regra.

Portanto, continua permitido manter copy, escolhas de fluxo, botões, coleta de
dados e roteamento conversacional no ManyChat. Continua proibido manter regra
autoritativa de preço, estoque, disponibilidade, pagamento ou lifecycle de
pedido no ManyChat. Se o bot precisa responder "quanto custa?" ou "tem hoje?",
ele deve perguntar ao Shopman e renderizar a projection retornada.

Para pedidos em andamento, o contrato compacto de conversa e
`RemoteConversationProjection`, documentado em
[docs/reference/manychat-conversation-projection.md](../reference/manychat-conversation-projection.md).
Ele deriva de tracking/payment/channel policy canonicos e separa `state`
conversacional de `order_status` oficial.

## Riscos assumidos

1. **Vendor lock-in**: se ManyChat sair do mercado, mudar precificação de forma adversa, ou alterar API de forma breaking, todo o canal WhatsApp quebra.
2. **Escalabilidade**: ManyChat tem seus próprios limits. Acima de volume significativo (~50k mensagens/mês), custo pode superar integração direta com Meta.
3. **Abstração: `notification_manychat` é um adapter entre vários**, mas escrever `notification_whatsapp_cloud` (Meta direto) é trabalho não pequeno — não está prototipado, não existe ainda.
4. **AccessLink `source=MANYCHAT` é hardcoded em enums** — escalar para múltiplos provedores/bots requer refatoração em [packages/doorman/shopman/doorman/models/access_link.py](../../packages/doorman/shopman/doorman/models/access_link.py).
5. **Fluxos conversacionais são caixa-preta parcial**: auditoria de copy WhatsApp depende de acessar editor ManyChat, não está 100% versionado em código.

## Mitigações adotadas

1. **Protocol `NotificationBackend` mantido agnóstico**: embora `notification_manychat` seja implementação default para WhatsApp, o contrato permite substituir por `notification_whatsapp_cloud` no futuro sem mudar callers.
2. **Fallback por intenção/canal**: SMS/e-mail podem ser alternativas explícitas de
   autenticação ou notificações transacionais quando consentimento e contrato do caso
   permitirem. Eles não são fallback de uma onda de Marketing cuja audiência consentiu
   em WhatsApp. Para Marketing, o único transporte WhatsApp é ManyChat e a ausência ou
   insegurança dele bloqueia a lane.
3. **Webhook payload normalizado**: `AccessLink.source` aceita enum aberto; handler de webhook ManyChat pode ser replicado para outro provedor sem alterar AccessLink model.
4. **Templates de mensagem versionados em repo** (quando aplicável): o conteúdo é código Shopman (via `OmotenashiCopy` futuramente); apenas o envio é ManyChat.

## Threshold de revisão

Reavaliar a decisão quando **qualquer**:

| # | Gatilho | Ação |
|---|---------|------|
| R1 | Volume > 50k mensagens WhatsApp/mês | Comparar custo ManyChat vs Meta direct |
| R2 | ManyChat price increase > 50% em 1 ano | Prototipar `notification_whatsapp_cloud` |
| R3 | Requisito de feature específica da Meta (ex.: Click-to-WhatsApp Ads, Product Catalog) não expostos pelo ManyChat | Avaliar integração direta parcial |
| R4 | Downtime ManyChat impactando SLA > 99% | Adicionar fallback automático |
| R5 | Regulação LGPD exigindo controle mais granular sobre dados trafegados | Auditoria + possível migração |

## Consequências

**Aceitamos**:
- Dependência operacional de ManyChat para o canal principal.
- Custo recorrente ManyChat enquanto for vantajoso.
- Copy de fluxos vive parcialmente fora do repo.

**Nos comprometemos a**:
- Manter adapter abstrato (`NotificationBackend` protocol intacto).
- Versionar templates de mensagem críticos (não copy de onboarding do bot) em repo.
- Revisar decisão anualmente ou ao atingir qualquer threshold R1-R5.

**Não aceitamos**:
- Usar ManyChat como banco de dados de cliente — sempre espelhar em `guestman.Customer` / `ContactPoint`.
- Lógica autoritativa de negócio vivendo em fluxos ManyChat. O bot pode coletar intenção e mostrar preço/estoque/resumo quando esses dados vierem de Shopman; pricing, stock, availability, payment gate e lifecycle continuam em Shopman.

## Referências

- Memória: [feedback_whatsapp_via_manychat.md](.claude/memory).
- [packages/doorman/shopman/doorman/models/access_link.py](../../packages/doorman/shopman/doorman/models/access_link.py) — enum `Source`.
- [shopman/shop/adapters/notification_manychat.py](../../shopman/shop/adapters/notification_manychat.py).
- [docs/reference/manychat-conversation-projection.md](../reference/manychat-conversation-projection.md).
- [docs/reference/system-spec.md §1.7, §5.2](../reference/system-spec.md) — Doorman + WhatsApp-first UX.
