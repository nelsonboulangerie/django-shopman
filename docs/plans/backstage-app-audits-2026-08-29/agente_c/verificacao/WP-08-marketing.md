# Verificação WP-08 — Marketing

Base verificada: worktree `coordenar-sessoes-deploys-b9cdac`, HEAD `9469c92a2` (descendente do main de 29/08).
Todos os `arquivo:linha` abaixo foram abertos e lidos na função inteira. Onde a linha citada pelos
agentes G/D mudou, registro a linha ATUAL.

## A. Superfície real (o que existe hoje)

### Backend — API (todas com o MESMO gate `shop.manage_campaigns`, `shopman/backstage/api/marketing.py:57-59`)

| Rota (`/api/v1/backstage/`) | View | O que faz |
|---|---|---|
| `marketing/` | `CampaignBoardView` | painel: pendentes, recentes, placar do dia, **`reach_limits`**, `ai_assist_available` |
| `marketing/history/` | `CampaignHistoryView` | tudo que saiu (limit 100/máx 300) |
| `marketing/options/` | `CampaignOptionsView` | vocabulário do formulário (gatilhos, plataformas, tags, tiers, RFM, ofertas) |
| `marketing/platforms/` | `PlatformsView` | prontidão de entrega de TODA plataforma (`services/delivery_readiness.py`) |
| `marketing/preview/` | `PreviewView` | render do corpo pelo mesmo resolvedor do envio; **sem PII** |
| `marketing/audience/count/` | `AudienceCountView` | conta o público **só números** (`projections/marketing.py:292`) |
| `marketing/rules/` + `rules/<pk>/` | `CampaignListView`/`CampaignDetailView` | CRUD de campanha |
| `marketing/rules/<pk>/fire/` | `CampaignFireView` (`marketing.py:418-478`) | **dispara agora**, público opcional deste disparo |
| `marketing/announcements/<pk>/` | `AnnouncementDetailView` | ler/editar antes de aprovar |
| `.../approve/` | `AnnouncementApproveView` (`marketing.py:147-185`) | **publica ou agenda** |
| `.../reject/` · `.../rewrite/` | reject / sugestão IA | — |
| `marketing/templates/` + `<pk>/` | CRUD de `AnnouncementTemplate` | — |
| `marketing/whatsapp-template/` | `WhatsAppTemplateView` | escolhe o flow ManyChat do evento `announcement_published` |
| `marketing/whatsapp-template/test/` | `WhatsAppTestSendView` (`marketing.py:188-222`) | **manda 1 mensagem real para 1 número digitado** |

### Backend — serviços / handlers
- `shopman/shop/services/campaign.py` — `evaluate`, `fire_now` (85-147), `_create_announcement` (150-183), `approve` (810-853), `dispatch` (920-936), `_queue_notify` (948-988), `arm_scheduled` (1070-1112), `create_for_occurrence` (1126-1157), `dispatch_due` (1160-1179), `send_test` (367-428).
- `shopman/shop/services/audience.py` — resolvedor único. `resolve()` (195), `waves()` (123-174), **`select_wave()` (339-350) — sem nenhum chamador no repositório**.
- `shopman/shop/handlers/campaign.py` — `AnnouncementNotifyHandler` (263-309) e `_send_to` (347-423) = o envio real; `CampaignOccurrenceHandler` (230-260) = ocasião agendada.
- `shopman/shop/services/campaign_identity.py` — cunha um **AccessLink pessoal por destinatário** (login do cliente) e o coloca no `action_url` da mensagem.
- `shopman/shop/services/campaign_schedule.py` — `preferred_hours` (adia) × `once`/`recurring` (dispara).
- `shopman/shop/adapters/notification_manychat.py` — único transporte real de WhatsApp; `_push_custom_fields` (288) grava contexto no perfil do assinante; `_FIELD_DENYLIST` (282).
- `shopman/shop/adapters/_external.py` — trava `inert()`: inerte em `seed` (sempre) e em `DEBUG` sem opt-in.
- `shopman/backstage/projections/marketing.py` — board, história, contagem de público, `_reach_limits` (467).
- `shopman/shop/management/commands/setup_groups.py:153` — `manage_campaigns` só no grupo **Gerente** (o Dono soma por herança do mesmo bloco).

### Frontend (`surfaces/marketing-nuxt`)
`pages/index.vue` (painel), `campaigns.vue` (regras + disparo), `announcements/[id].vue`, `history.vue`, `platforms.vue`, `templates.vue`; componentes `AnnouncementCard.vue`, `CampaignForm.vue`, `FireCampaignPanel.vue`, `AnnouncementPreview.vue`; composables `useCampaignBoard/useCampaigns/useAudienceCount/useWhatsAppTemplate`. BFF: `server/api/v1/[...path].ts` → `proxyDjangoApi` da operator-kit.

### O disparo real está ligado hoje?
**Condicionalmente, e não consigo confirmar o ambiente alpha a partir do código.** O que o código
determina:
- O único transporte de WhatsApp registrado em produção é `manychat` (`config/settings.py:1039-1044`; `console` só entra com `DEBUG` ou `SHOPMAN_ENABLE_CONSOLE_NOTIFICATION_ADAPTER`).
- `manychat.is_available()` (`notification_manychat.py:323`) devolve `True` **só se `MANYCHAT_API_TOKEN` estiver setado**.
- Sem token, `_whatsapp_backend()` devolve `None` e `_send_to` retorna `(0, N)` — **falha fechada**, ninguém recebe, o painel mostra "0 enviados, N falharam". Correto.
- Com token e `DEBUG=False`, o envio é **real e imediato**, sem trava adicional. `inert()` não protege staging/produção por desenho (`_external.py:44`).
- As plataformas de **publicação** (Instagram/Facebook/Google Business) não têm adapter: `_posting_adapter` devolve `None` e o anúncio vira `pending_manual`. Nada sai por ali hoje.

Conclusão prática: **o único canal com blast radius real é o WhatsApp/ManyChat, e ele acende com uma
variável de ambiente.** Trate todo achado de WhatsApp como "ligado" para efeito de prioridade.

### O que os WPs não mencionaram (fatos, não achados)
1. **Existe um caminho de disparo 100% autônomo**: `arm_scheduled` → Directive `campaign.occur` → `create_for_occurrence` → `_create_announcement`; com `requires_approval=False` ele chama `dispatch()` direto (`campaign.py:181-182`), sem humano. É deduplicado por `occurrence_key` (unique parcial, `models/campaign.py:348-352`) e o formulário avisa em amarelo ao desligar a revisão (`CampaignForm.vue:411-413`). É o maior blast radius do app e nenhum dos dois WPs o cita.
2. **Já existem freios servidor-side parciais** que D chamou de ausentes: `reach_limits` no board (`projections/marketing.py:456, 467-514`) e a contagem ao vivo no painel de disparo (`FireCampaignPanel.vue:311-361`).
3. `AudienceCountView` e `build_announcement` devolvem **apenas contagens** — nenhum destinatário, telefone ou ref sai pela API de marketing. Verificado.

---

## B. Evidências dos WPs, veredito uma a uma

| # | Afirmação (G/D) | Arquivo:linha ATUAL | Veredito | Nota |
|---|---|---|---|---|
| 1 | `approve` respeita `publish_at` quando `publish_now` não vem (G:13, D:28) | `marketing.py:172`; `campaign.py:828-830` | **CONFIRMADO** | `respect_schedule=not _as_bool(publish_now)`; sem a flag, `publish_at = announcement.publish_at`, e `scheduled=True` se futuro. |
| 2 | Frontend aprova sem `publish_now`; zero ocorrências da flag (G:14, D:29) | `AnnouncementCard.vue:103-106` (`publishNow`) e `108-111` (`schedule`) | **CONFIRMADO E AGRAVADO** | `grep publish_now` em `surfaces/` **e** em `shopman/` (fora da própria leitura) = **zero**. A flag não tem produtor nenhum no repositório — nem teste. É parâmetro morto. |
| 3 | Toast deriva de `publish_at` e mente (D:9) | `useCampaignBoard.ts:36`; `announcements/[id].vue:35-36` | **CONFIRMADO E AGRAVADO** | Mente nos **dois** sentidos: sem `publish_at` diz "publicado" quando agendou; com `publish_at` no passado diz "agendado" quando publicou já. A resposta traz `scheduled` (`marketing.py:183`) e ninguém a lê. |
| 4 | `publish_at` no passado vira publish-now silencioso (D novo) | `marketing.py:735-751` (aceita qualquer ISO); `campaign.py:830` | **CONFIRMADO** | `scheduled = publish_at is not None and publish_at > now` → passado é `False` → `dispatch()` imediato (`851-852`). Sem teste cobrindo (só o de data-lixo, `test_api_marketing_surface.py:464`). |
| 5 | `fire_now` salva a audiência escolhida no contexto (G:15, D:30) | `campaign.py:123-130` | **CONFIRMADO** | Muda o `rule` **em memória** (129) e grava no `payload` (130) que vira `trigger_context`. |
| 6 | Handler usa a audiência do contexto (G:16, D:30) | `handlers/campaign.py:284-295` | **CONFIRMADO** | `chosen = context.get("audience_rules")` vence a regra salva. |
| 7 | `_queue_notify` planeja ondas pela regra salva → diverge (G:38, D:50) | `campaign.py:965` | **PARCIAL — impacto muito menor do que os dois afirmam** | Divergência real, mas **o conjunto de destinatários nunca fica errado por causa dela**: o handler re-resolve e mapeia por chave, e as chaves `vip`/`general`/`all` sempre cobrem todo mundo. O que diverge é a **estrutura das ondas** (split VIP, atraso) e o **número planejado**. A exceção grave é a onda `nome@hora` — ver C-3. |
| 8 | Permissão única `shop.manage_campaigns` cobre tudo (G:51, D:32) | `marketing.py:57-59`; `setup_groups.py:153` | **CONFIRMADO, gravidade recalibrada** | É verdade que uma permissão só cobre ler/editar/aprovar/disparar/testar/configurar template. Mas ela está **só no grupo Gerente**, não em Caixa nem Cozinha. Não é "qualquer operador dispara". |
| 9 | Test-send sem restrição de destino (D novo, "a") | `marketing.py:200-222`; `campaign.py:367-428` | **CONFIRMADO E AGRAVADO** | Além de destino livre, o serviço aceita **`body` arbitrário** (`campaign.py:399`) — a API manda texto livre para número livre. A UI não expõe `body` (`useWhatsAppTemplate.ts:53`), mas a API sim. Sem throttle para autenticado (só `AnonRateThrottle`, `settings.py:832-837`). |
| 10 | `approve` não re-valida audiência (D novo, "b") | `campaign.py:810-853`; card lê `announcement.audience` em `AnnouncementCard.vue:82, 234` | **CONFIRMADO** | O número que o gestor lê é o de `_create_announcement` (`campaign.py:157, 172`), calculado na criação; o envio re-resolve em `handlers/campaign.py:295`. |
| 11 | `CampaignForm` descarta chaves de audiência (D novo, "d") | `CampaignForm.vue:159-165` | **CONFIRMADO** | Reconstrói com 4 chaves e sempre envia `audience_rules`, então PATCH apaga: `match`, `tags`, `rfm_segments`, `price_tiers`, `churn_risk_min`, `birthday_today`, `customer_refs`, `bought_skus`, `bought_collections`, `preferred_hour_window_hours` (10 chaves). |
| 12 | "Tipo TS omite regras avançadas" (G:18, D:31, citando `types/campaign.ts:104`) | `types/campaign.ts:104-117` | **REFUTADO** | O tipo `AudienceRules` HOJE declara `match`, `price_tiers`, `tags`, `rfm_segments`, `churn_risk_min`, `birthday_today`. A perda **não está no tipo**, está no `submit()` do form. A evidência citada não sustenta a afirmação. |
| 13 | "Resolver aceita regras avançadas: `audience.py:195` / `:247-290`" (G:19, D:31) | `audience.py:195` (`resolve`) e `247-283` (blocos por chave) | **CONFIRMADO** (linha ligeiramente deslocada: o último bloco é `282-283`, não `290`) | — |
| 14 | Body por plataforma pode ser sobrescrito (G:80) | `campaign.py:611` | **CONFIRMADO no código, IRRELEVANTE na prática** | `out[platform] = {**variant, "body": content["body"]}` sobrescreve mesmo. Mas `platform_content` **não tem leitor**: só é escrito (`campaign.py:170, 881`) e exibido no Admin. Nenhum sender o consome. |
| 15 | Imagem normalizada num caminho e crua no outro (G:82) | `campaign.py:797-804` (`_image_url`, cru) × `774-794` (`product_image_url`, absoluto) | **CONFIRMADO, sem consumidor vivo** | `content["image_url"]` só seria usado por um adapter de posting, que não existe. O caminho que chega ao ManyChat usa `product_image_url` (variáveis), que absolutiza. |
| 16 | "Adapter envia quase todo scalar do contexto" ao ManyChat (G:96) | `notification_manychat.py:282-286` (`_FIELD_DENYLIST`) e `288-315` | **PARCIAL** | Existe denylist e ela bloqueia `phone`, `customer_ref`, `customer_uuid`, `sku`, `session_key`, `subscriber_id`, `recipient`, `hold_ids`. Não é "quase todo scalar". Mas é denylist, não allowlist — e deixa passar o item perigoso que ninguém viu (ver D-1). |
| 17 | "Test send loga destinatário/subscriber" (G:96, D) | `marketing.py:212-215` | **CONFIRMADO, e menor do que o problema real** | Loga `recipient` cru em INFO. O vazamento maior é no caminho de **produção**: `notifications.py:68-69` loga `recipient[:20]` para **cada destinatário de cada onda** — telefone BR inteiro cabe em 20 chars. |
| 18 | "Approve imediato já é idempotente" (D:20) | `campaign.py:832-836` | **CONFIRMADO** | `PUBLISHED`/`PUBLISHING` e `APPROVED` sem `publish_at` retornam sem refazer. |
| 19 | "fire/test/rewrite não são idempotentes" (D:20) | `campaign.py:138`; `models/campaign.py:348-352` | **CONFIRMADO** | `fire_now` cria com `occurrence_key=""`, que o unique parcial não cobre. Dois POSTs = dois anúncios = dois blasts. Só o `busy` do cliente (`campaigns.vue:56-58`) segura. |
| 20 | "Rate limit por operador ausente" (G:59, D:68) | `config/settings.py:832-837` | **CONFIRMADO** | `DEFAULT_THROTTLE_CLASSES` só tem `AnonRateThrottle`. Nenhum endpoint de marketing usa `django_ratelimit` (que o backstage já usa em `operations.py:427-430`). |
| 21 | "Fallback de revisores usa o mesmo codename" (D:116) | `campaign.py:1039-1045` | **CONFIRMADO** | `Q(user_permissions__codename="manage_campaigns") \| Q(groups__permissions__codename=...)`. Separar a permissão quebra este fallback. |
| 22 | Main já corrigiu algo disto? | `git log -6` nos 5 arquivos citados | **NÃO** | Último toque em `api/marketing.py` = `5f0919e94` (match/contagem); em `campaign.py` = `a4c64b474`. Nenhum commit recente mexe em `publish_now`, ondas, test-send ou no form. |

---

## C. Achados confirmados, com gravidade recalibrada

### C-1 — "Publicar agora" agenda, "agendar no passado" publica, e o toast mente nos dois casos · **P1**
**Risco × esforço:** risco moderado (a mensagem sai na hora errada, ou o gestor acredita que agendou
e ela já saiu — irreversível), esforço trivial (duas linhas no front, uma no back).

**Mecanismo, do clique ao efeito:**
1. Uma campanha com `schedule = {"type": "preferred_hours", ...}` (configurável só pelo Admin — o
   form não gera esse tipo, `CampaignForm.vue:110-127`) faz o anúncio nascer com `publish_at` na
   próxima abertura de janela (`campaign.py:163` → `campaign_schedule.next_publish_at`).
2. O gestor clica **"Publicar agora"**. `publishNow()` (`AnnouncementCard.vue:103-106`) emite os
   edits **sem `publish_now`**.
3. `approve` recebe `respect_schedule=True` (`marketing.py:172`), reintroduz o `publish_at` do
   anúncio (`campaign.py:828-829`), calcula `scheduled=True` e **não despacha**.
4. `useCampaignBoard.ts:36` olha `edits.publish_at` (ausente) e mostra **"Anúncio publicado."**
   O gestor sai da tela achando que publicou.
5. O espelho: no botão **"Agendar"**, uma data no passado passa por `_publish_at` (`marketing.py:735-751`,
   que só valida formato), vira `scheduled=False` e **dispara imediatamente** — com o toast dizendo
   "Anúncio agendado."

**Fix mínimo:**
- `AnnouncementCard.vue:105` → `emit("approve", props.announcement.pk, { ...edits(), publish_now: true });`
- `useCampaignBoard.ts:36` e `announcements/[id].vue:35-36` → decidir o texto pelo `scheduled` da
  resposta (`marketing.py:183`), nunca pelo corpo enviado.
- `marketing.py`, em `_publish_at`, depois da linha 750: recusar passado —
  `if parsed <= timezone.now(): return None, {"detail": "Essa hora já passou.", "field": "publish_at"}`

### C-2 — `CampaignForm` apaga 10 chaves de audiência ao salvar · **P1**
**Risco × esforço:** risco alto na direção que importa (uma edição de nome de campanha destrói o
recorte e, no caso de `match: "all"`, **alarga** o público), esforço baixo.

**Mecanismo:** o gestor abre "Editar" numa campanha configurada no Admin com
`{"tags": ["corredores"], "rfm_segments": ["champion"], "match": "all"}`, muda só o nome e salva.
`submit()` (`CampaignForm.vue:145-167`) monta `audience_rules` do zero com 4 chaves
(159-165) e o PATCH sobrescreve o JSON inteiro (`marketing.py:635-640` grava o dict como veio).
Perdem-se `match`, `tags`, `rfm_segments`, `price_tiers`, `churn_risk_min`, `birthday_today`,
`customer_refs`, `bought_skus`, `bought_collections`, `preferred_hour_window_hours`. Com
`favorites`+`alerts`+`bought` ligados, perder `match: "all"` troca interseção por união
(`audience.py:285-287`) — **mais gente do que o gestor pediu**, sem aviso.

**Fix mínimo (uma linha, e é a certa):** preservar o que não se edita —
`CampaignForm.vue:159` → `audience_rules: { ...(props.rule?.audience_rules ?? {}), favorites: ..., alerts: ..., ... }`,
com as chaves opcionais apagadas explicitamente quando desligadas (`bought_within_days: undefined` não
basta em JSON; usar `delete` ou montar o objeto). O aviso na tela ("esta campanha tem regras que este
formulário não edita") é UX desejável, não pré-requisito do fix.

### C-3 — A onda de hora habitual é planejada, despachada, e **entregue a ninguém**, reportada como enviada · **P1**
**Risco × esforço:** risco alto de confiança (o painel afirma entrega que não houve), esforço de uma
linha. Latente hoje (nenhuma UI escreve `preferred_hour_window_hours`; só o Admin, e a chave é
oferecida no `help_text` do próprio model, `models/campaign.py:157`).

**Mecanismo:**
1. `audience.waves()` produz ondas com chave `f"{name}@{hour}"` (`audience.py:172`) para quem tem
   `CustomerInsight.preferred_hour` e a regra tem `preferred_hour_window_hours > 0`.
2. `_queue_notify` cria uma Directive por onda, com essa chave (`campaign.py:971-987`).
3. `AnnouncementNotifyHandler` resolve os destinatários por um dicionário fixo de três chaves:
   `{"vip":…, "general":…, "all":…}.get(wave, ())` (`handlers/campaign.py:297-301`). `general@14`
   cai no default `()`.
4. `_send_to` recebe zero destinatários; `_record_wave` grava `sent=0, failed=0` e, por
   `handlers/campaign.py:509`, o status vira **`"sent"`** ("onda vazia não é falha").
5. `_settle` fecha o anúncio como `PUBLISHED`. Ninguém daquela onda recebeu, e nada indica isso.

A função que resolveria — `audience.select_wave(rules, wave_key, sku=sku)` (`audience.py:339-350`) —
existe, está descrita como o contrato de despacho no docstring do `_queue_notify`
(`campaign.py:958-960`) e **não tem um único chamador no repositório**. É código morto que a
documentação afirma estar em uso.

**Fix mínimo (uma linha):** em `handlers/campaign.py`, trocar o dicionário das linhas 297-301 por
`recipients = audience_service.select_wave(rules, wave, sku=sku)`.

### C-4 — Test-send é um canhão de texto livre para número livre · **P1**
**Risco × esforço:** risco alto (mensagem arbitrária saindo do WhatsApp Business da padaria para
qualquer número, e com efeito colateral no perfil de clientes reais), esforço baixo.

**Mecanismo:**
1. `POST marketing/whatsapp-template/test/` com `{"recipient": "<qualquer número>", "body": "<qualquer texto>"}`.
2. `marketing.py:200-208` só faz `str()` dos campos; `send_test` (`campaign.py:384-389`) recusa
   apenas vazio e lista (vírgula/espaço). Nenhuma validação de formato, nenhum vínculo com o
   operador, nenhum consentimento, nenhum throttle.
3. O `body` do chamador vira a mensagem (`campaign.py:399-401`) e sai pelo transporte real.
4. **Efeito colateral que ninguém viu:** se houver flow configurado, `send()` chama
   `_push_custom_fields` (`notification_manychat.py:253`) e **grava o contexto do teste como campos
   personalizados do assinante**. Testar contra o número de um cliente real sobrescreve
   `customer_name`, `product_name`, `action_url` etc. no perfil dele — e a próxima mensagem legítima
   renderiza com os valores do teste.

**Fix mínimo:** (a) remover `body` do contrato do endpoint — a UI já não o manda
(`useWhatsAppTemplate.ts:53`), então é dívida sem consumidor; (b) `django_ratelimit` no
`WhatsAppTestSendView`, no mesmo padrão de `backstage/api/operations.py:427-430`
(`ratelimit(key="user", rate="5/m", method="POST", block=True)`). O vínculo destino↔dono que D
propõe é bem-vindo mas depende de dado que não existe hoje (o `User` do operador não tem telefone
declarado) — não colocar no aceite.

### C-5 — Dois cliques em "Disparar agora" mandam duas vezes · **P2**
**Risco × esforço:** risco real mas contido (o front desabilita o botão), esforço médio.

**Mecanismo:** `fire_now` cria o anúncio com `occurrence_key=""` (`campaign.py:138`), e o unique
parcial só cobre chave não vazia (`models/campaign.py:348-352`). Duas requisições = dois
`Announcement` = dois conjuntos de Directives com dedupe_keys distintos (`announcement:<pk1>:wa:all`
e `announcement:<pk2>:wa:all`) = duas mensagens por pessoa. A única barreira é o `busy`
client-side (`campaigns.vue:56-58`), que não sobrevive a um retry de rede, a duas abas ou a um curl.

**Fix mínimo:** aceitar um `Idempotency-Key` no `CampaignFireView` e usá-lo como `occurrence_key`
(o unique parcial do banco já resolve o resto — não precisa de tabela nova).

### C-6 — Uma permissão para editar, aprovar, disparar e testar · **P2** (G e D dizem P1)
**Recalibração:** `manage_campaigns` está **só no grupo Gerente** (`setup_groups.py:150-153`); Caixa e
Cozinha não a têm. O cenário "qualquer operador dispara para a base" não existe. O que existe é
ausência de segregação de funções **dentro** de uma persona de gestão — em uma padaria com um ou
dois gerentes, isso é higiene, não bloqueador. Além disso a separação tem custo escondido: o
fallback de revisores (`campaign.py:1039-1045`) casa por codename e quebraria.

**Fix mínimo se for feito:** separar apenas `fire`/`test_external_send` de `manage_campaigns`
(as duas ações irreversíveis), manter o resto sob a permissão atual, e ajustar
`_reviewers` para o codename de leitura/aprovação.

### C-7 — PII de destinatário em log INFO, no caminho de produção · **P2**
`notifications.py:68-69` loga `"Notification sent: %s -> %s..." % (event, recipient[:20])` para
**cada** destinatário de cada onda; um telefone brasileiro em E.164 tem 13 caracteres e cabe
inteiro. `marketing.py:212-215` faz o mesmo no test-send. Não é vazamento externo, mas é telefone de
cliente em log agregado, retido por quem gerencia o app.
**Fix mínimo:** mascarar na origem — `recipient[:4] + "…" + recipient[-2:]` nas duas linhas.
⚠️ `notifications.py` é do `shop` e serve todos os canais transacionais: o fix vale, o arquivo não é
deste WP (ver seção G).

---

## D. Achados NOVOS (que G e D perderam)

### D-1 — O token de login do cliente é gravado no perfil dele no ManyChat · **P1**
**Risco × esforço:** risco alto e específico (acesso à conta de cliente por terceiro), esforço de
uma linha.

**Mecanismo, do clique ao efeito:**
1. Gestor aprova um anúncio com WhatsApp entre as plataformas.
2. `_send_to` cunha, **por destinatário**, um `AccessLink` de login e o coloca em `action_url`
   (`handlers/campaign.py:397-401` → `campaign_identity.personal_link`, `campaign_identity.py:60-82`).
   O token vale até 24 h (`campaign_identity.py:44, 85-95`) e cria sessão de cliente identificado
   por número (`storefront/api/auth.py:138-153`).
3. `notify()` repassa o contexto intacto ao adapter (`notifications.py:66`).
4. Havendo flow configurado — que é exatamente a configuração que o app oferece em
   `marketing/whatsapp-template/` —, `send()` chama `_push_custom_fields`
   (`notification_manychat.py:253`), que grava **todo scalar não-denylistado** como campo
   personalizado do assinante (`notification_manychat.py:288-315`).
5. `action_url` **não está na `_FIELD_DENYLIST`** (`notification_manychat.py:282-286`). O token de
   login do cliente passa a viver, em texto claro, no perfil dele dentro de uma ferramenta SaaS de
   marketing — legível por qualquer pessoa com acesso à conta ManyChat, e utilizável enquanto o
   cliente não clicar (o link é de uso único, `AccessLink.is_valid`, `packages/doorman/shopman/doorman/models/access_link.py:147-149`).

**Fix mínimo (uma linha):** `notification_manychat.py:282-286` → acrescentar `"action_url"` ao
`_FIELD_DENYLIST`. O flow do ManyChat que precisar do link deve receber o link **comum**, não o
pessoal; se o botão do template precisar do link pessoal, ele tem de vir pelo `flow_token` (que
já é enviado, `notification_manychat.py:257`) e não como campo persistido no perfil.

### D-2 — Regra de audiência com número mal formado devolve 500 em vez de erro de campo, e mata a campanha em silêncio · **P2**
**Mecanismo:** `audience.resolve` faz `int()` sem guarda em três chaves —
`bought_within_days` (`audience.py:242`), `preferred_hour_window_hours` (`290`) e
`vip_first_minutes` (`292`). `_rule_fields` (`marketing.py:635-640`) aceita qualquer dict como
`audience_rules`, sem validar tipos das chaves. Consequências:
- `POST marketing/audience/count/` com `{"audience_rules": {"bought_within_days": "muitos"}}` →
  `ValueError` não tratado → a API devolve **500** (o `exception_handler` de `api_errors.py:57`
  devolve `None` para exceções não-DRF). Não vaza stacktrace com `DEBUG=False`, mas o gestor vê o
  erro genérico sem `field`.
- Mesmo payload em `rules/<pk>/fire/` → 500 (o `except` só pega `CampaignError`, `marketing.py:467`).
- Pior: salvo na campanha, `evaluate()` engole a exceção por regra (`campaign.py:76-81`) e a campanha
  **nunca mais dispara**, sem nada na tela dizer isso.

**Direção da falha:** verifiquei especificamente o caso que o briefing teme — filtro que morre e vira
"todo mundo". **Não existe.** `resolve()` parte de conjunto vazio (`audience.py:224`), cada
resolvedor falho devolve `[]` (`audience.py:387-388, 495-497, 527-529, 546-548, 569-571, 592-594`),
o consentimento falha fechado (`audience.py:686-687`) e `int()` explode antes de somar ninguém. A
única frouxidão que **alarga** é `match` desconhecido → união (`audience.py:320-323`), e ela é
deliberada, logada, e visível na contagem antes do envio.

**Fix mínimo:** validar as três chaves numéricas em `_rule_fields` e em `AudienceCountView`/`CampaignFireView`,
devolvendo `{"detail": …, "field": "audience_rules"}`. Alternativa mais barata e igualmente correta:
tornar as três leituras tolerantes em `audience.py` (helper `_as_int(value, default=0)` que loga e
devolve o default) — mas aí a campanha salva com lixo passa a rodar com o default, o que é pior para
`bought_within_days`. Prefira a validação na porta.

### D-3 — `platform_content` e `content["image_url"]` são configuração sem leitor · **P2 (dívida, não risco)**
`AnnouncementTemplate.platform_variants[<plataforma>]["body"]` é lido só para saber "esta plataforma
diverge" e imediatamente sobrescrito pelo corpo genérico (`campaign.py:611`). O `platform_content`
resultante é gravado (`campaign.py:170, 881`) e **nenhum consumidor o lê** — grep em `shopman/` e
`surfaces/` só encontra escrita, o Admin e um assert de teste. Idem `content["image_url"]`, cujo
único consumidor seria um adapter de posting inexistente. Não é risco de blast; é o gestor
configurando um campo que não faz nada. Deve ser **apagado ou implementado**, não "unificado com o
preview".

---

## E. Achados a DESCARTAR

1. **"Tipo TS omite regras avançadas" (G, evidência `types/campaign.ts:104`; D repete).**
   Refutado pelo código: `AudienceRules` (`types/campaign.ts:104-117`) já declara `match`, `tags`,
   `rfm_segments`, `price_tiers`, `churn_risk_min`, `birthday_today`. Manter a evidência errada faz
   o executor gastar tempo no arquivo errado. O achado real é C-2, no `submit()` do form.

2. **"Gerar/compartilhar schema de audiência" (G:72, D:80).**
   Custo desproporcional. O vocabulário é fechado, plano e documentado em três lugares
   (`audience.py:204-216`, `models/campaign.py:150-158`, `types/campaign.ts:104-117`), e a ADR-020 §7
   proíbe expressamente a árvore booleana que justificaria um gerador. A perda de chaves se resolve
   com um spread (C-2).

3. **"Preview/payload por plataforma podem divergir" + "snapshot preview vs payload final" (G:80-91, D:87-94).**
   Descartar como P2 de preview: não há payload por plataforma consumido por ninguém (D-3). O que
   sobra é a dívida D-3, com outro fix (apagar ou implementar). O aceite "snapshot compara preview
   aprovado vs payload final" não é verificável hoje porque o "payload final por plataforma" não
   existe.

4. **Aceite "o número planejado nas ondas bate com a audiência confirmada" (G:49).**
   D já apontou que contradiz o desenho (`campaign.py:16-18, 951-963`: a audiência é
   deliberadamente re-resolvida no envio). Confirmo: é decisão documentada e correta —
   favoritos e assinaturas de "me avise" crescem entre a aprovação e o disparo, e congelar
   desperdiçaria justamente quem entrou na fila. **Não entra como aceite.** O que entra é C-3 (a
   onda que não entrega) e um aviso de contagem no momento da aprovação.

5. **"Kill switch por campanha/plataforma" e "comparador de blast radius +312 desde o preview" (G:111-113, D idem).**
   Fora de proporção para uma padaria com um forno e ~dezenas de destinatários por onda; e o
   comparador depende do freeze que ninguém decidiu. Deixar em ideias, não em escopo.

6. **"Allowlist por evento para campos do ManyChat" (G:100, D:100).**
   A denylist existe e cobre os identificadores (`notification_manychat.py:282-286`). Trocar por
   allowlist por evento é reescrita de um mecanismo que funciona; o buraco real é uma chave faltando
   nela (D-1), e o fix é acrescentá-la.

7. **"Separar seis permissões" como P1 (G:57, D:65).**
   Recalibrado para C-6/P2 e reduzido a duas permissões. Seis codenames novos exigem migração de
   `Permission`, atualização de `setup_groups.py`, conserto de `_reviewers` e teste de paridade — e
   protegem contra um cenário (operador de balcão disparando) que o RBAC atual já impede.

---

## F. Aceites verificáveis

Todos checáveis contra o código/teste de hoje. Nenhum depende de infra inexistente nem da decisão
freeze × drift.

1. **`publish_now` sai da UI e chega ao backend.**
   Prova: `grep -r "publish_now" surfaces/marketing-nuxt/app` retorna ao menos `AnnouncementCard.vue`;
   e teste em `shopman/backstage/tests/test_api_marketing_surface.py` que cria anúncio com
   `publish_at` futuro (via `schedule` `preferred_hours`), aprova com `{"publish_now": true}` e
   afirma `response.json()["scheduled"] is False` + `status == PUBLISHING/PUBLISHED`.

2. **`publish_at` no passado é 400 de campo.**
   Prova: teste irmão do `test_garbage_date_is_refused_before_anything_is_published`
   (`test_api_marketing_surface.py:464`), com `timezone.now() - timedelta(hours=1)`, afirmando
   `status_code == 400` e `json()["field"] == "publish_at"` e `status` ainda `PENDING_REVIEW`.

3. **O toast segue o `scheduled` da resposta.**
   Prova: teste vitest em `surfaces/marketing-nuxt/tests/` que faz o `$fetch` devolver
   `{scheduled: true}` sem `publish_at` no corpo enviado e afirma a mensagem "Anúncio agendado.".

4. **Round-trip do formulário não perde regra.**
   Prova: teste vitest em `tests/components/CampaignForm.test.ts` que monta `props.rule` com
   `audience_rules: {favorites: true, tags: ["corredores"], match: "all"}`, submete sem tocar em
   nada e afirma que o payload emitido ainda contém `tags` e `match`.

5. **A onda de hora habitual entrega.**
   Prova: teste em `shopman/shop/tests/` que resolve uma audiência com
   `{"favorites": true, "preferred_hour_window_hours": 4}` e um destinatário com
   `preferred_hour` no futuro próximo, roda `_queue_notify` + `AnnouncementNotifyHandler.handle` com
   a directive de chave `all@<hora>` e afirma `sent == 1`. Hoje esse teste falha com `sent == 0`.

6. **Onda que não alcançou ninguém não se reporta como "sent" quando havia gente planejada.**
   Prova: o mesmo teste, afirmando que `platform_results["whatsapp"]["status"] != "sent"` quando
   `waves_expected` prometia destinatários e nenhum foi resolvido.

7. **`action_url` não vira campo personalizado no ManyChat.**
   Prova: teste que chama `notification_manychat._push_custom_fields` (com `_api_call`
   monkeypatchado) com `{"action_url": "https://…?t=abc", "product_name": "Pão"}` e afirma que
   nenhuma chamada teve `field_name == "action_url"`.

8. **Test-send recusa texto arbitrário e é limitado por operador.**
   Prova: teste em `test_api_marketing_surface.py` (classe `TestWhatsAppTestSend`, já existe a
   partir da linha 781) afirmando que `body` no payload não altera a mensagem enviada; e que a 6ª
   chamada em um minuto devolve 429.

9. **Regra de audiência com número inválido é 400 de campo, nunca 500.**
   Prova: teste `POST marketing/audience/count/` com `{"audience_rules": {"bought_within_days": "muitos"}}`
   afirmando `status_code == 400` e `json()["field"] == "audience_rules"`. Mesmo teste para `fire/`.

10. **Dois `fire` com a mesma chave de idempotência criam um anúncio só.**
    Prova: teste que posta duas vezes em `rules/<pk>/fire/` com o mesmo `Idempotency-Key` e afirma
    `Announcement.objects.filter(rule=rule).count() == 1`.

11. **Log de campanha não contém telefone inteiro.**
    Prova: teste com `caplog` sobre uma onda de 1 destinatário afirmando que o telefone completo não
    aparece em nenhum registro (assert negativo).

12. **A tela do disparo continua contando antes de enviar.**
    Prova (regressão, não trabalho novo): `FireCampaignPanel.test.ts` já cobre; manter verde.

---

## G. Fronteiras e colisões

### Arquivos que este WP precisa tocar (lista exata)

**Backend — deste WP:**
- `shopman/backstage/api/marketing.py` — `_publish_at` (recusar passado), `WhatsAppTestSendView` (remover `body`, throttle, mascarar log), `CampaignFireView` (idempotency key), validação numérica de `audience_rules` em `_rule_fields` e `AudienceCountView`.
- `shopman/shop/handlers/campaign.py` — `AnnouncementNotifyHandler.handle` linhas 297-301 (`select_wave`), `_record_wave` (status honesto para onda planejada e vazia).
- `shopman/shop/services/campaign.py` — `send_test` (deixar de aceitar `body` arbitrário); opcionalmente `fire_now` (`occurrence_key` de idempotência); `_platform_content`/`_image_url` se D-3 for resolvido apagando.
- `shopman/shop/adapters/notification_manychat.py` — **uma linha**: `action_url` na `_FIELD_DENYLIST` (linha 282-286).
- `shopman/backstage/tests/test_api_marketing_surface.py`, `shopman/shop/tests/test_campaign.py`, `shopman/shop/tests/test_audience.py` — testes.

**Frontend — deste WP:**
- `surfaces/marketing-nuxt/app/components/AnnouncementCard.vue` (linha 105: `publish_now: true`)
- `surfaces/marketing-nuxt/app/composables/useCampaignBoard.ts` (linha 36: ler `scheduled`)
- `surfaces/marketing-nuxt/app/pages/announcements/[id].vue` (linhas 33-37: ler `scheduled`)
- `surfaces/marketing-nuxt/app/components/CampaignForm.vue` (linha 159: preservar chaves)
- `surfaces/marketing-nuxt/app/types/campaign.ts` (acrescentar `customer_refs`, `bought_skus`, `bought_collections`, `preferred_hour_window_hours` — o resto já está)
- `surfaces/marketing-nuxt/tests/components/{AnnouncementCard,CampaignForm}.test.ts`

**Risco de colisão alto** com qualquer WP que toque `shopman/shop/handlers/campaign.py` (é também
onde vive o receiver de `production_changed`, que WPs de Produção podem tocar) e
`shopman/shop/adapters/notification_manychat.py` (compartilhado com pedidos, estoque e compras —
alterar só a constante `_FIELD_DENYLIST` mantém o hunk mínimo).

### Permissões novas e impacto em `setup_groups.py`
Li `shopman/shop/management/commands/setup_groups.py`. Estado atual: `manage_campaigns` aparece
**uma vez**, em `"Gerente"` (linha 153), com comentário explicando que sem ela o app fica
inalcançável; o `"Dono"` soma por composição (linhas 220-232). O comando também tem um teste de
paridade de contagem (comentário na linha 257 sobre "Gerente: 157" divergindo do banco), então
qualquer permissão nova exige acertar esse número.

Proposta reduzida (ver C-6): **duas** permissões novas, não seis —
`shop.fire_campaign` e `shop.test_external_send` — ambas no `"Gerente"` num primeiro momento, para o
comportamento não mudar no deploy; a separação de pessoas vira config depois. **Obrigatório junto:**
`shopman/shop/services/campaign.py:1039-1045` (`_reviewers`) continua casando por
`manage_campaigns` — que passa a ser a permissão de *ler e aprovar*, o que é o comportamento certo,
mas precisa de teste explícito.

### O que pertence a outro app / outro dono
- **`shopman/shop/notifications.py:68-69`** (telefone em log INFO): é do `shop` e afeta todos os
  canais transacionais, não só campanha. C-7 deve virar item de um WP de notificações/observabilidade,
  ou ser explicitamente doado a este WP com o hunk mínimo de duas linhas.
- **Consentimento e PII de cliente**: `guestman` (`ConsentService`, `CustomerInsight`, `CustomerTag`).
  Este WP consome, nunca escreve. `audience.py` fica no `shop` e continua sendo o dono do vocabulário.
- **`campaign_identity.py` / `AccessLink`**: a política de token pessoal é `doorman` + `storefront`.
  Este WP só mexe no que o **adapter de marketing persiste** (D-1), não na cunhagem.
- **RBAC (quem tem o papel)**: `backstage`/`doorman`. Este WP declara as permissões; a atribuição a
  pessoas é do deployment.
- **Adapters de posting (Instagram/Facebook/Google)**: não existem. Fora de escopo, e todo aceite que
  dependa deles é invencível hoje.

---

## H. Perguntas abertas para o dono do produto

1. **O `MANYCHAT_API_TOKEN` está setado no alpha hoje?** É a única chave entre "campanha é um
   ensaio" e "campanha alcança clientes reais", e ela decide se C-1/C-4/D-1 são P1 ou P2. Não
   consigo responder lendo código.

2. **O test-send deve poder mandar texto livre, ou só o template?** Hoje a API aceita `body`
   arbitrário para número arbitrário e a tela não usa esse campo. Se a resposta for "só o template",
   o fix é apagar o parâmetro; se for "texto livre também", precisa de confirmação explícita na tela
   e do teto por operador, e o WP fica maior.

3. **`preferred_hour_window_hours` deve continuar sendo oferecido?** O `help_text` do model o anuncia
   e nenhuma tela o escreve; hoje ligá-lo faz a mensagem não chegar (C-3). Consertar o handler é uma
   linha; expor o controle numa tela é trabalho de produto. Consertar sempre — expor, só se você
   quiser a onda por hora habitual de fato.
