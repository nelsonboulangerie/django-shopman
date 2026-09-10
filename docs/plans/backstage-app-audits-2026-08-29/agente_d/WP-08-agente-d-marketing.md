# WP-08-agente-d — Marketing Operacional

**Status:** pronto para implementação · **Autor:** Agente D (revisão do WP-08 do Agente G)
**Superfície:** 'surfaces/marketing-nuxt' + endpoints marketing/campaign
**Objetivo:** impedir disparo acidental, abuso de público, template errado, vazamento de cliente e divergência entre preview/aprovação/disparo — com freios servidor-side reais.

## Diferenças vs. WP original (Agente G)

**Mantidos (validados):** "Publicar agora" pode agendar (botão envia sem 'publish_now'; **zero ocorrências da flag no frontend**; toast deriva de 'publish_at' e mente — 'AnnouncementCard.vue:103-106', '[id].vue:29-36'); audiência manual diverge do planejamento de ondas ('fire_now' salva a escolha no 'trigger_context' — 'campaign.py:123-130' — e o handler usa: 'handlers/campaign.py:284-295' — mas '_queue_notify' planeja ondas pela regra salva: 'campaign.py:965'); permissão única 'shop.manage_campaigns' cobre board/approve/fire/CRUD/test ('marketing.py:57-59'); UI não preserva regras avançadas ('CampaignForm.vue:159-165' reconstrói 'audience_rules' com 4 chaves e descarta 'tags/rfm_segments/price_tiers/churn_risk_min/birthday_today/match'); preview/payload por plataforma podem divergir; PII em logs/adapters.

**Recalibrados / agravados:**
- **P1 audiência efetiva** — o aceite do WP ("o número planejado nas ondas bate com a audiência confirmada") é **contraditório com o design**: o código re-resolve a audiência na hora do envio de propósito (favoritos/alertas mudam entre aprovação e disparo — 'campaign.py:951-963'). "Bater" exige congelar (freeze) — decisão de produto. Reformulado: recibo de dry-run com hash da seleção efetiva + escolha explícita freeze vs drift registrada.
- **P1 permissão única** — mantido + achado novo: **test-send sem restrição de destino** (envia para qualquer número, um por chamada, sem vínculo com o dono — 'marketing.py:200-222' + 'campaign.py:367-411'). E 'approve' **não re-valida audiência** no momento da decisão (publica com o resumo calculado na criação — 'campaign.py:172,810-853').
- **P2 regras avançadas** — agravante: a perda é mais ampla que a omissão de tipo — o form **descarta chaves que o resolver aceita** ('audience.py:247-290').

**Novos (achados da verificação):**
- **Test-send canhão 1-por-1**: qualquer 'manage_campaigns' manda mensagem para qualquer número sem rate limit/confirmação/vínculo destino-dono.
- **'publish_at' no passado vira "publicar agora" silencioso** ('marketing.py:735-751' aceita qualquer ISO; 'campaign.py:830-831' → 'scheduled=False' → dispatch imediato).
- **Approve sem re-validação de audiência** (acima).
- Idempotência: approve imediato **já** é idempotente ('campaign.py:832-836'); fire/rewrite/test não são.

## Fronteira Natural

Marketing gera, revisa, testa, aprova, dispara ou agenda campanhas e audita resultado por plataforma. BI, Guestman, storefront, catálogo e ManyChat entram como fontes/sinks. Admin fica para configuração/auditoria, não como cockpit paralelo. **Rate limit por role**: o teto é decisão do app de Marketing; RBAC (quem tem o role) é do backstage/doorman. **Schema de audiência**: 'audience.py' é do shop e é o dono certo do vocabulário.

## Evidências (verificadas)

- 'approve' respeita 'publish_at' quando 'publish_now' ausente: 'shopman/backstage/api/marketing.py:164-172', 'shopman/shop/services/campaign.py:827-830'.
- Frontend aprova sem 'publish_now': 'AnnouncementCard.vue:103-106', 'announcements/[id].vue:29-36'; grep 'publish_now' no frontend = zero.
- 'fire_now' salva escolha no contexto: 'campaign.py:123-130'; handler usa: 'handlers/campaign.py:284-295'; ondas pela regra salva: 'campaign.py:965'.
- Tipo TS omite regras avançadas: 'surfaces/marketing-nuxt/app/types/campaign.ts:104-117'; resolver aceita: 'shopman/shop/services/audience.py:247-290'.
- Permissão única: 'shopman/backstage/api/marketing.py:57-59'.
- Test-send sem destino restrito: 'marketing.py:200-222', 'campaign.py:367-411'.
- Approve não re-valida audiência: 'campaign.py:172,810-853'.
- 'publish_at' passado → imediato: 'campaign.py:830-831'.

## Achados Priorizados

### P1 — "Publicar agora" pode agendar (e o toast mente)

Proposta:
- Botão "publicar agora" envia 'publish_now: true'; botão "agendar" envia data e texto próprio.
- Toast depende do retorno 'scheduled' do backend (nunca deriva de 'publish_at').
- 'publish_at' no passado → 400 (nunca vira publish-now silencioso).

Aceite:
- Teste cobre anúncio com 'publish_at' aprovado pelo botão "publicar agora" (dispara imediato).
- 'publish_at' no passado retorna 400 de campo.

### P1 — Audiência manual diverge do planejamento de ondas (freeze vs drift)

Proposta:
- 'fire_now', fila e handler usam a MESMA seleção efetiva (unificar 'trigger_context' ↔ '_queue_notify').
- Recibo de dry-run com hash da seleção efetiva (contagem, filtros, canais, imagem).
- **Decisão registrada**: freeze (congelar a seleção no disparo — números batem, envio pode ficar obsoleto) OU drift (re-resolver — números divergem por design). Não misturar.

Aceite:
- Se freeze: o número planejado nas ondas bate com a audiência confirmada (teste com público que muda entre aprovação e disparo).
- Se drift: o recibo registra a seleção efetiva e o planejamento é informativo.
- A escolha fica documentada neste WP antes da implementação.

### P1 — Permissão única e ausência de freio servidor-side

Proposta:
- Separar: 'view', 'edit', 'approve', 'fire', 'test_external_send', 'manage_whatsapp_template' (com 'setup_groups').
- **Test-send**: vincular o destino ao dono (apenas números autorizados do operador) OU exigir confirmação explícita + rate limit; nunca um canhão 1-por-1 sem vínculo.
- Idempotency key para fire/test/rewrite/approve (approve imediato já é idempotente — preservar).
- Rate limit por operador e teto de audiência por role/canal; confirmação por hash de audiência acima do limite.
- **Approve re-valida audiência** no momento da decisão (contagem atual, aviso se zerou/encolheu).

Aceite:
- Usuário que edita não necessariamente dispara (resolver o approve-with-edits: ou exige 'edit', ou as edições são barradas para quem não edita).
- Repetir POST com mesma chave não cria novo blast.
- Test-send para número não autorizado falha; acima do teto exige confirmação.
- Aprovar com audiência zerada mostra aviso antes de confirmar.

### P2 — UI não preserva regras de audiência aceitas pelo backend

Proposta:
- Gerar/compartilhar schema de audiência ('audience.py' é o dono do vocabulário).
- Round-trip preserva chaves desconhecidas OU bloqueia edição parcial com aviso ('CampaignForm' deixa de descartar 'tags/rfm/price_tiers/churn/birthday/match').

Aceite:
- Campanha com 'customer_refs' ou 'bought_skus' não perde regra ao salvar (teste round-trip).
- Salvamento com chaves não suportadas pelo form avisa antes de sobrescrever.

### P2 — Preview/payload por plataforma podem divergir

Proposta:
- Normalização única de conteúdo final por plataforma antes de preview, anúncio e sink externo.
- Preview mostra exatamente o payload final (snapshot comparado no teste).

Aceite:
- Snapshot compara preview aprovado vs payload final (teste).

### P2 — PII em logs e campos ManyChat amplos

Proposta:
- Mascarar/hash PII em logs de teste.
- Allowlist por evento para campos enviados ao ManyChat; limpeza explícita de campos obsoletos.

Aceite:
- Logs de teste não contêm telefone/subscriber cru (teste assert-negativo).

## Melhorias UX

1. **Modal de aprovação forte:** agora/agendado, público contado, plataformas, template, imagem e primeira onda.
2. **Dry-run anexado:** contagem, filtros, canais, imagem, hash.
3. **Comparador de blast radius:** "+312 clientes desde o preview".
4. **Linter cliente-safe:** placeholders, PII, imagem ausente, link externo, flow errado.
5. **Kill switch por campanha/plataforma:** para após N falhas/reclamações.
6. **Histórico acionável:** retestar/republicar somente falhas.

## RBAC / setup_groups

Permissões novas: 'view', 'edit', 'approve', 'fire', 'test_external_send', 'manage_whatsapp_template' (nomes a confirmar com o dono do shop). **Obrigatório atualizar 'setup_groups.py'**: hoje 'shop.manage_campaigns' é do Gerente (e dono); decidir quem dispara (aprovador), quem edita (gestor de marketing), quem testa (restrito a números autorizados). Teste de paridade obrigatório. **Atenção**: o fallback de revisores usa o mesmo codename ('campaign.py:1039-1045') — rever com a separação.

## Pré-requisitos

- Nenhum. Independente dos demais WPs.

## Testes

- 'publish_now' vs agendamento; 'publish_at' passado → 400.
- Ondas com audiência manual (freeze vs drift decidido).
- Preservação de regras avançadas (round-trip).
- Body por plataforma; URL absoluta de imagem; snapshot preview vs payload.
- Replay/idempotência (fire/test/rewrite).
- Matriz de permissões (view/edit/approve/fire/test/template) + paridade.
- Test-send: destino autorizado, rate limit, teto de audiência, hash de confirmação.
- ManyChat allowlist/limpeza; logs sem PII cru.
- Corrida de aprovação com lock (idempotência).

## Fora De Escopo

BI/atribuição financeira, CRUD de cliente/tag em massa, edição de catálogo/preço, regras de checkout/storefront, autoria completa de flows ManyChat, gestão de credenciais, CDP genérico e notificações transacionais de pedido.

## Prompt Para Agente Executor

~~~text
Execute WP-08-agente-d (Marketing Operacional).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-08-agente-d-marketing.md
- surfaces/marketing-nuxt/app/* (AnnouncementCard.vue, pages/announcements/[id].vue, types/campaign.ts, components/CampaignForm.vue)
- shopman/backstage/api/marketing.py
- shopman/backstage/projections/marketing.py
- shopman/shop/services/campaign.py (approve, fire_now, _queue_notify)
- shopman/shop/services/audience.py
- shopman/shop/handlers/campaign.py
- shopman/shop/adapters/notification_manychat.py
- shopman/shop/management/commands/setup_groups.py (RBAC)

Fases:
1. Corrigir publish_now/agendamento + publish_at passado + toast honesto.
2. Unificar audiencia efetiva (freeze vs drift decidido) + recibo dry-run com hash.
3. Permissoes finas + setup_groups; test-send com destino vinculado; idempotencia; approve re-valida audiencia.
4. Schema de audiencia e round-trip (preservar chaves avancadas).
5. Preview final por plataforma e PII-safe logs/allowlist ManyChat.

Nao mova BI, CRM ou credenciais para o app de Marketing.
~~~

