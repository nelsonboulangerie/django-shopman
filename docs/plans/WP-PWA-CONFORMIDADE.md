# WP-PWA — Conformidade PWA das surfaces: instalável, notificação ativa, kiosk

> Estado atual (2026-09-15): **registro histórico; não executar como brief.** A F0
> do Storefront foi entregue e publicada por [#668](https://github.com/nelsonboulangerie/django-shopman/pull/668),
> com ajustes em [#691](https://github.com/nelsonboulangerie/django-shopman/pull/691),
> [#693](https://github.com/nelsonboulangerie/django-shopman/pull/693) e
> [#694](https://github.com/nelsonboulangerie/django-shopman/pull/694). Falta a
> validação no iPhone físico da barra inferior, pull-to-refresh e teclado; essa
> prova pendente não desfaz a publicação. F1–F3 continuam futuras e exigem brief
> atualizado a partir de `main` antes de qualquer execução.
>
> Contexto da proposta (2026-09-14), a pedido do dono: nasceu na discussão dos
> agentes de operador. O aviso proativo da Anaïs ("o
> fechamento de ontem está pronto") só faz sentido se chega com a tela do celular
> desligada. Medido o estado de 14/09, a resposta era que **nenhuma surface era PWA**
> e que a casa já tem a metade difícil pronta (alerta pessoal com ciclo de vida,
> SSE por usuário, envelope de segurança que já libera worker e manifesto).
>
> Escopo do pedido do dono: "tudo que temos direito". Este WP lista tudo, decide o
> que entra e diz por quê o resto fica de fora.
>
> | # | Pergunta | Decidido / recomendado |
> |---|---|---|
> | 1 | Onde mora? | **Capability opt-in do `operator-kit`**, no mesmo modelo do envelope de segurança ([ADR-026](../decisions/adr-026-operator-surface-security-envelope.md)): nada implícito, cada app liga e declara o seu manifesto. O Storefront tem PWA própria (superfície de cliente, marca própria) |
> | 2 | Módulo ou manual? | `@vite-pwa/nuxt` (Workbox) em modo `generateSW`, com **runtime caching desligado para `/api/` e `/events/`**. Um SW por app, escopo `/` |
> | 3 | Offline? | **Só o casco**: assets imutáveis, ícones e uma tela "sem conexão" honesta. Offline-first de dados (PDV) continua sendo o WP-9+ do [POS-FIRST-CLASS-PLAN](POS-FIRST-CLASS-PLAN.md), não este |
> | 4 | Notificação ativa? | **Web Push com VAPID**, segundo canal do `UserNotification` que já existe. Nada de Firebase, OneSignal ou app nativo |
> | 5 | Quem envia? | O Django, por Directive `notification.push` no worker existente ([ADR-003](../decisions/adr-003-directives-sem-celery.md)): retry, idempotência pela `dedupe_key`, poda de assinaturas mortas |
> | 6 | Cliente recebe push? | **Não neste WP.** O canal do cliente é o WhatsApp ([ADR-009](../decisions/adr-009-whatsapp-via-manychat.md)). O Storefront fica instalável, sem push |
> | 7 | Piloto | **Storefront** (decisão do dono, 14/09): é a superfície que mais exige de PWA (marca, instalação pelo cliente, splash, fotos offline). Depois **PDV**, depois **todo o backstage**, com o Hub recebendo o Web Push primeiro. Execução: [WP-PWA-EXECUCAO.md](WP-PWA-EXECUCAO.md) |
> | 8 | Gate | `make pwa`: gate próprio da casa (o Lighthouse aposentou a categoria PWA em 2024; não há auditor externo em que se apoiar) |

## Estado medido (2026-09-14)

| Peça | Estado | Onde |
|---|---|---|
| Alerta pessoal por usuário, com ciclo de vida (criada, vista, assumida, resolvida), dedupe, escalação, retenção | ✅ no ar | `shop/models/user_notification.py`, `shop/services/user_notifications.py` |
| Entrega em tempo real com o app aberto | ✅ SSE `user-<id>` via `django_eventstream`; proxy same-origin no kit | `user_notifications.push_user_notification`, `operator-kit/server/routes/sse/notifications.ts` |
| Notificação com a aba aberta | ⚠️ só o Gestor, `new Notification()` em página; morre com a aba | `orders-nuxt/app/composables/useOrdersBoard.ts` |
| Notificação com a tela desligada | ❌ não existe: sem service worker, sem manifesto, sem assinatura de push, sem VAPID | nenhuma surface |
| Manifesto PWA | ❌ nenhuma surface | `public/` só tem `favicon.ico` e `robots.txt` |
| Meta de instalação iOS | ⚠️ parcial no Storefront (`apple-mobile-web-app-capable`, `theme-color`); Hub só `theme-color` | `nuxt.config.ts` de cada app |
| Ícones | ❌ só favicon; nenhum 192/512, nenhum maskable, nenhum apple-touch-icon | |
| Envelope de segurança compatível | ✅ `worker-src 'self' blob:` e `manifest-src 'self'` já estão na CSP; `script-src` é nonce-only e o kit injeta nonce em script sem nonce | `operator-kit/server/utils/securityHeaders.ts` |
| Kiosk | ⚠️ Produção pede fullscreen à mão no `board.vue`; sem Wake Lock em lugar nenhum (tela apaga na parede) | `production-nuxt/app/pages/board.vue:95` |
| Cache | ✅ HTML e API `private, no-store`; `/_nuxt/` e `/fonts/` imutáveis | kit |

## O que "tudo que temos direito" significa, e o que entra

| Capacidade | Entra? | Por quê |
|---|---|---|
| Instalável (manifesto completo, ícones, `start_url`, `id`, `scope`, `display`) | ✅ | é o piso: sem isso não há tela inicial, nem push no iPhone |
| Web Push (tela desligada) | ✅ | o motivo do WP |
| Badge no ícone do app (`navigator.setAppBadge`) com contagem de avisos ativos | ✅ | grátis, e é o "bolinha vermelha" que o gestor entende |
| Atalhos no manifesto (`shortcuts`) | ✅ | pressionar o ícone do Hub e ir direto em Pedidos ou Caixa |
| Wake Lock (tela não apaga) | ✅ | KDS, Produção e PDV: hoje a tela da parede apaga |
| `display: fullscreen` + `orientation` para kiosk | ✅ | KDS e Produção; tira a barra do navegador de vez |
| Atualização de versão controlada (SW novo espera; app avisa; kiosk recarrega sozinho quando ocioso) | ✅ | sem isso o operador roda versão velha por dias |
| Tela "sem conexão" honesta | ✅ | melhor do que o dinossauro do Chrome, e é onde `useConnectivity` do kit já mora |
| Splash iOS (`apple-touch-startup-image`) | ✅ | gerado junto com os ícones pelo mesmo comando |
| Cache offline de dados, Background Sync, Periodic Sync | ❌ | é o offline-first do PDV, WP próprio; um SW que guarda resposta de API por engano é vazamento de dado entre operadores |
| Push para o cliente no Storefront | ❌ | canal do cliente é o WhatsApp; fica instalável, sem push |
| Share Target, File Handling, Protocol Handlers | ❌ | sem caso de uso na casa |
| Window Controls Overlay (desktop) | ⏳ opcional no PDV | só depois de o resto estar no ar |

## Arquitetura

```
UserNotification (shop)  ── on_commit ──▶ SSE user-<id>          (app aberto: já existe)
        │
        └── Directive notification.push ──▶ pywebpush ──▶ FCM/APNs relé ──▶ SW do app ──▶ aviso na tela bloqueada
                 │                           (payload cifrado fim a fim: o relé não lê)          │
                 └── PushSubscription (shop): endpoint, p256dh, auth, user, surface, categorias   └── toque abre action_url
```

**O aviso é um ponteiro, não o fato.** O payload leva `id`, `category`, `title`, um
`body` curto e `action_url`. Ao tocar, o SW foca ou abre a surface na `action_url` e
a tela faz o fetch canônico, como já faz no evento SSE ([ADR-016](../decisions/adr-016-sse-first-realtime.md)).
Nada de valor, telefone ou endereço na tela bloqueada: categorias financeiras
mandam **só o título**.

**Uma assinatura por aparelho e surface.** `PushSubscription` liga `endpoint`
(único), chaves, `user`, `surface_ref` (hub, orders, pos…), rótulo do aparelho,
`categories` (allowlist, padrão tudo), `created_at`, `last_success_at`,
`failures`, `disabled_at`. Resposta 404/410 do relé desativa; `pushsubscriptionchange`
no SW reassina. Trocar de usuário no mesmo aparelho revoga a assinatura anterior.

**Envio pelo worker, nunca no request.** `push_user_notification` ganha a segunda
perna: enfileira `notification.push` com `dedupe_key` da notificação. O handler
resolve assinaturas ativas do usuário que aceitam a categoria, envia com `TTL`
(1 h operacional, 24 h relatório) e `Urgency` (`high` para crítico), grava
evidência por tentativa e poda o que morreu. Falha do relé é transitória; assinatura
inválida é terminal.

**Preferência do operador.** Na tela de avisos do Hub: ligar/desligar por
categoria, lista de aparelhos com "remover". O padrão é ligado para tudo que hoje
gera `UserNotification`; a regra da casa vale ("amarelo por escolha da casa é
ruído"): categoria que ninguém abre em duas semanas volta para a mesa.

**Segurança.** O SW é servido same-origin em `/sw.js` com `cache-control: no-cache`
(nunca imutável, senão a atualização não chega). O registro sai em script com
nonce, que o kit já injeta. `connect-src 'self'` segue: a assinatura de push é
do navegador, não da página. Chaves VAPID são segredo de ambiente na DO
([runbook](../runbooks/release-secrets-runbook.md)); a pública vai no
`runtimeConfig.public` do app (derivada da chave `NUXT_PUBLIC_VAPID_PUBLIC_KEY`,
ver armadilha do nome de env do Nuxt). Permissão de notificação só por toque
("Ativar avisos"), nunca no carregamento.

**Cache do SW.** Precache: assets versionados do build (`/_nuxt/*`), ícones,
fontes e o casco estático `offline.html`; **não** inclui `/` nem outra resposta de
navegação. Runtime: **nada** para `/api/`, `/events/`, `/admin/` ou HTML; somente
`/img/products/**` e `/fonts/**`, imutáveis por convenção. Navegação é sempre de
rede e, quando ela falha, recebe o fallback estático `offline.html`. Isso é
deliberado: um SW que responde API ou página viva do cache pode mostrar o estado
de ontem para o usuário de hoje.

## iPhone: o mínimo que a Apple permite, e como chegar nele

Pedido do dono: no iPhone, o ideal é "só uma confirmação". O limite é da Apple, não
nosso: o Safari não tem prompt programático de instalação, então a instalação é um
gesto manual do usuário (Compartilhar → Adicionar à Tela de Início → Adicionar), uma
única vez por aparelho. Depois disso, o resto é uma confirmação só. O WP trata isso
como requisito de UX, com critério de aceite:

| Momento | O que o sistema faz | Toques do gestor |
|---|---|---|
| Primeira visita no Safari do iPhone (não instalado) | detecta `display-mode: browser` + iOS; mostra UMA tela: "Para receber avisos, adicione à Tela de Início", com a seta apontando o botão Compartilhar do Safari e os dois passos em imagem. Botão "já adicionei" e "agora não" (não insiste no mesmo dia) | 3, uma vez na vida do aparelho |
| Primeira abertura já instalado | abre logado (cookie `.boulangerie` sobrevive à instalação); UMA pergunta: "Quer receber avisos neste iPhone?" com botão "Ativar" | 1 toque nosso + 1 confirmação do iOS |
| Depois | nada. Aviso chega com a tela apagada; toque abre direto na tela certa | 0 |

No Android o caminho é mais curto: o botão "Instalar" é nosso (`beforeinstallprompt`)
e a permissão de avisos é a mesma pergunta única.

Critério de aceite da F0/F1: gestor que nunca viu o sistema chega ao primeiro aviso
na tela bloqueada do iPhone em **menos de um minuto e sem ler manual**, medido com
uma pessoa da casa e registrado no runbook.

## Por surface

| Surface | `display` | Wake Lock | Badge | Push | Observação |
|---|---|---|---|---|---|
| hub | `standalone` | não | ✅ avisos ativos | ✅ piloto | atalhos: Pedidos, Caixa, Produção |
| orders (Gestor) | `standalone` | não | ✅ pedidos novos | ✅ | aposenta o `new Notification()` de aba |
| pos | `standalone` (`window-controls-overlay` depois) | ✅ | não | ✅ só `severity=critical` | terminal fixo; o push importa para o gerente no bolso |
| kds | `fullscreen`, `orientation: landscape` | ✅ | não | não | parede; o som já faz o papel |
| production | `fullscreen`, `orientation: landscape` | ✅ | não | ✅ para quem tem `manage_production` | kiosk Solari; `/display/` continua sem senha |
| marketing, purchase, bi | `standalone` | não | não | ✅ categorias próprias | herdam do kit; zero código específico |
| storefront | `standalone`, marca própria | não | não | ❌ | instalável; ícones e splash da marca; `theme-color` já é `#85786c` |

## Fases

Ordem decidida pelo dono em 14/09: Storefront → PDV → backstage. O detalhe
executável de cada fase está em [WP-PWA-EXECUCAO.md](WP-PWA-EXECUCAO.md).

| Fase | Entrega | Gate |
|---|---|---|
| **F0 — Storefront (piloto)** | Manifesto servido por rota Nitro a partir do `Shop` (nome, `short_name`, descrição) com cores da marca e ícones estáticos; SW de casco (`@vite-pwa/nuxt`, sem manifesto do módulo): precache do build, `offline.html` na voz da casa, fotos de produto e fontes em cache por serem imutáveis por convenção, **nada de API nem HTML**; instalação guiada (Android: botão; iOS: passo a passo); atualização controlada; ícones, favicon, apple-touch-icon e splash gerados do SVG da marca. Sem push. | `make pwa` no storefront; vitest/typecheck/lint/build/e2e verdes com node@22 |
| **F1 — capability do kit + PDV** | O que o Storefront provou vira capability opt-in do `operator-kit` (manifesto por app, SW de casco, instalação, atualização, Wake Lock, `fullscreen`); PDV liga primeiro (`standalone`, Wake Lock). | `make pwa` no pos; testes do kit; envelope de segurança intacto |
| **F2 — backstage inteiro** | hub, orders, kds, production, marketing, purchase, bi ligam conforme a tabela "Por surface"; kiosks em `fullscreen` com recarga ociosa. | `make pwa` por app; CI `surfaces-gate` verde |
| **F3 — Web Push** | `PushSubscription` em `shop/models`; VAPID; API de assinar/remover/listar; Directive `notification.push` + handler; segunda perna em `push_user_notification`; poda; preferências por categoria no Hub; SW: `push`, `notificationclick`, `pushsubscriptionchange`; badge. Hub e Gestor primeiro, depois produção e PDV crítico. | chave em [data-schemas](../reference/data-schemas.md); testes de service; prova no aparelho (Android e iPhone, tela desligada) no runbook |
| **F4 — agentes** | A Anaïs e os alertas dos agentes usam o canal como qualquer `UserNotification`. | depende do WP dos agentes |

## Gate `make pwa`

Um comando, sem serviço externo, que falha se qualquer item cair:

1. Manifesto servido same-origin com `name`, `short_name`, `id`, `start_url`,
   `scope`, `display`, `theme_color`, `background_color`, ícones 192 e 512 com
   `purpose: maskable` e `any`, `lang: pt-BR`.
2. `/sw.js` responde 200, same-origin, `cache-control: no-cache`, e o precache não
   contém caminho sob `/api/`, `/events/` ou `/admin/`.
3. CSP da página contém `worker-src 'self'` e `manifest-src 'self'`; o script de
   registro carrega nonce.
4. `apple-touch-icon`, `apple-mobile-web-app-capable` e `theme-color` no HTML.
5. Playwright (Chromium): registro do SW conclui, manifesto é lido, `offline.html`
   responde com rede cortada, `notificationclick` abre a `action_url`.
6. Backend: assinatura, envio, poda e preferências com relé falso; nenhum campo de
   valor ou PII no payload de categoria financeira.

Cada app roda o gate no seu CI ao lado dos testes de vitest, como faz hoje com o
envelope de segurança.

## Riscos e limites honestos

- **iPhone.** Só há push com o app na Tela de Início (iOS 16.4+) e permissão pedida
  por toque. O Hub precisa ensinar isso na primeira visita, sem forçar.
- **Entrega é melhor esforço.** O relé pode atrasar ou descartar. Alerta crítico
  continua com SSE, badge e som; o push é a perna a mais, não a única.
- **Permissão se corrói com ruído.** Aviso ignorado vira aviso desligado. Cada
  categoria que entra no push precisa de dono e de valor real.
- **SW velho é bug difícil.** Por isso `no-cache` no SW, versão visível na tela de
  avisos e recarga controlada.
- **Segredo VAPID.** Trocar a chave invalida todas as assinaturas: é operação com
  runbook, não deploy casual.

## Fora de escopo, com nome

Offline-first do PDV (WP-9+ do POS), push para cliente, app nativo, notificações
por WhatsApp/SMS (são canais próprios, já cobertos), Background/Periodic Sync,
Share Target.

## Referências

- [ADR-026 (envelope de segurança das surfaces)](../decisions/adr-026-operator-surface-security-envelope.md)
- [ADR-016 (SSE first)](../decisions/adr-016-sse-first-realtime.md)
- [ADR-003 (directives sem Celery)](../decisions/adr-003-directives-sem-celery.md)
- `shop/services/user_notifications.py`, `shop/models/user_notification.py`
- [POS-FIRST-CLASS-PLAN](POS-FIRST-CLASS-PLAN.md) (offline-first fica lá)
