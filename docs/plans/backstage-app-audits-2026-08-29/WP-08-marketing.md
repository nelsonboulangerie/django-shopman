# WP-08 - Marketing Operacional

**Status:** pronto para implementacao  
**Superficie:** `surfaces/marketing-nuxt` + endpoints marketing/campaign  
**Objetivo:** impedir disparo acidental, abuso de publico, template errado, vazamento de cliente e divergencia entre preview/aprovacao/disparo.

## Fronteira Natural

Marketing gera, revisa, testa, aprova, dispara ou agenda campanhas e audita resultado por plataforma. BI, Guestman, storefront, catalogo e ManyChat entram como fontes/sinks. Admin fica para configuracao/auditoria, nao como cockpit paralelo.

## Evidencias Principais

- `approve` respeita `publish_at` quando `publish_now` nao vem: `shopman/backstage/api/marketing.py:164`, `shopman/shop/services/campaign.py:827`.
- Frontend aprova sem `publish_now`: `surfaces/marketing-nuxt/app/components/AnnouncementCard.vue:103`, `surfaces/marketing-nuxt/app/pages/announcements/[id].vue:29`.
- `fire_now` salva audiencia escolhida: `shopman/shop/services/campaign.py:123`.
- Handler usa audiencia do contexto: `shopman/shop/handlers/campaign.py:284`.
- `_queue_notify` calcula ondas pela regra salva: `shopman/shop/services/campaign.py:965`.
- Tipo TS omite regras avancadas: `surfaces/marketing-nuxt/app/types/campaign.ts:104`.
- Resolver aceita regras avancadas: `shopman/shop/services/audience.py:195`.
- Permissao unica `shop.manage_campaigns`: `shopman/backstage/api/marketing.py:57`.

## Achados Priorizados

### P1 - “Publicar agora” pode agendar

Botao de UI sugere publicar, mas backend pode agendar se `publish_now` ausente e `publish_at` existir.

Proposta:

- Botao “publicar agora” envia `publish_now: true`.
- Botao “agendar” envia data e texto proprio.
- Toast depende do retorno `scheduled`.

Aceite:

- Teste cobre anuncio com `publish_at` aprovado por botao publicar agora.

### P1 - Audiencia manual diverge do planejamento de ondas

Selecao efetiva e regra salva podem divergir.

Proposta:

- `fire_now`, fila e handler usam a mesma selecao efetiva.
- Guardar recibo de dry-run com hash da audiencia.

Aceite:

- O numero planejado nas ondas bate com a audiencia confirmada.

### P1 - Permissao unica e ausencia de freio servidor-side

`shop.manage_campaigns` cobre editar, aprovar, disparar, testar e configurar; `AudienceCountView` e preflight opcional.

Proposta:

- Separar `view`, `edit`, `approve`, `fire`, `test_external_send`, `manage_whatsapp_template`.
- Idempotency key para fire/test/rewrite/approve.
- Rate limit por operador e teto de audiencia por role/canal.
- Confirmacao por hash de audiencia para disparo acima do limite.

Aceite:

- Usuario que edita nao necessariamente dispara.
- Repetir POST com mesma chave nao cria novo blast.

### P2 - UI nao preserva regras de audiencia aceitas pelo backend

Form reconstrui `audience_rules` parcialmente e pode descartar chaves avancadas.

Proposta:

- Gerar/compartilhar schema de audiencia.
- Round-trip preserva chaves desconhecidas ou bloqueia edicao parcial com aviso.

Aceite:

- Campanha com `customer_refs` ou `bought_skus` nao perde regra ao salvar.

### P2 - Preview/payload por plataforma podem divergir

Body especifico por plataforma pode ser sobrescrito; URL de imagem e normalizada em um caminho e crua em outro.

Proposta:

- Normalizacao unica de conteudo final por plataforma antes de preview, anuncio e sink externo.
- Preview mostra exatamente payload final.

Aceite:

- Snapshot compara preview aprovado vs payload final.

### P2 - PII em logs e campos ManyChat amplos

Test send loga destinatario/subscriber; adapter envia quase todo scalar do contexto.

Proposta:

- Mascarar/hash PII em logs.
- Allowlist por evento para campos enviados ao ManyChat.
- Limpeza explicita de campos obsoletos.

Aceite:

- Logs de teste nao contem telefone/subscriber cru.

## Melhorias UX

1. **Modal de aprovacao forte:** agora/agendado, publico contado, plataformas, template, imagem e primeira onda.
2. **Dry-run anexado:** contagem, filtros, canais, imagem, hash.
3. **Comparador de blast radius:** “+312 clientes desde o preview”.
4. **Linter cliente-safe:** placeholders, PII, imagem ausente, link externo, flow errado.
5. **Kill switch por campanha/plataforma:** para apos N falhas/reclamacoes.
6. **Historico acionavel:** retestar/republicar somente falhas.

## Testes

- `publish_now`.
- Ondas com audiencia manual.
- Preservacao de regras avancadas.
- Body por plataforma.
- URL absoluta de imagem.
- Replay/idempotencia.
- Matriz de permissoes.
- ManyChat allowlist/limpeza.
- Confirmacao por hash de audiencia.
- Corrida de aprovacao com lock.

## Fora De Escopo

BI/atribuicao financeira, CRUD de cliente/tag em massa, edicao de catalogo/preco, regras de checkout/storefront, autoria completa de flows ManyChat, gestao de credenciais, CDP generico e notificacoes transacionais de pedido.

## Prompt Para Agente Executor

```text
Execute WP-08 Marketing Operacional.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/WP-08-marketing.md
- surfaces/marketing-nuxt/app/*
- shopman/backstage/api/marketing.py
- shopman/backstage/projections/marketing.py
- shopman/shop/services/campaign.py
- shopman/shop/services/audience.py
- shopman/shop/handlers/campaign.py
- shopman/shop/adapters/notification_manychat.py

Fases:
1. Corrigir publish_now/agendamento.
2. Unificar audiencia efetiva e recibo dry-run.
3. Permissoes finas + idempotencia/rate/blast radius.
4. Schema de audiencia e round-trip.
5. Preview final por plataforma e PII-safe logs.

Nao mova BI, CRM ou credenciais para o app de Marketing.
```

