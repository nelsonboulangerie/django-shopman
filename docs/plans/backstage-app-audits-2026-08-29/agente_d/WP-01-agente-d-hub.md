# WP-01-agente-d — Hub / Central De Apps

**Status:** pronto para implementação · **Autor:** Agente D (revisão do WP-01 do Agente G)
**Superfície:** 'surfaces/hub-nuxt' + 'api/v1/backstage/hub/'
**Objetivo:** o Hub abre o app certo para quem pode abri-lo, sem login falso, sem link morto e sem virar mini app operacional.

## Diferenças vs. WP original (Agente G)

**Mantidos (validados na verificação):** erro de fetch vira login falso ('needsLogin = Boolean(error.value) || sessionExpired' — 'app.vue:41'); drift do mock e2e ('kind: "config"' — 'mockBackend.mjs:15'); 'SHOPMAN_PURCHASE_BASE_URL' fora do check de domínio ('checks.py:401-408'); projection sem estado operacional.

**Recalibrados:**
- **P1 tile Produção** — o WP dizia "usuário abre e dá 403"; a verdade é o **inverso**: quem tem só 'backstage.operate_production' (persona de chão) **não vê o tile**, porque o hub usa 'can_access_production' ('hub.py:85'), que exige 'shop.manage_production' ou colunas finas ('permissions.py:32-41'). E 'can_operate_production' **já existe** ('permissions.py:93-102') — a correção é trocar o predicado no registry, não "criar campo canônico" como o WP propôs. Nos grupos seedados (Cozinha/Gerente) as duas perms coexistem, então o bug fica mascarado — precisa de teste com grant customizado.
- **P1 validação de URLs** — rebaixado para **P2 (config-drift)**: as URLs vêm de 'settings.SHOPMAN_SURFACE_URLS', não de payload de cliente; o risco é config errada no deploy, não ataque. O problema real: 'SHOPMAN_SURFACE_URLS' não passa por nenhum check de host/esquema nem aparece em 'check_operator_cookie_domain'.
- **P2 projection com 'tile.status/blocked/forbidden'** — **removido como proposto**: renderizar 'forbidden'/'missing_url' contradiz o contrato "tiles já vêm FILTRADOS: se está na lista, o operador pode abrir" ('hub.ts:2-3') e vaza nomes de superfície para quem não pode abri-las. Substituído por contrato de **motivo de ausência no empty-state** (§UX).
- **"Leve-me ao gargalo"** — rebaixado para **P3/backlog**: exige leitura de orderman/cashman/buyman/craftsman (fronteira que o próprio WP declara como externa). O Hub não agrega estado operacional; cada app expõe seu próprio summary (ver §Fronteira).

**Novos (achados da verificação):**
- Spec e2e 'hub.spec.ts:21-23' também stale: afirma 'href="/admin/shop/shop/"' e 'target="_blank"' (contrato pré-cutover); com 'kind:"config"' no mock, 'tileTarget' devolve '_self' → a asserção falha. O par mock+spec está congelado junto — corrigir os dois, não só o mock.
- Zero cobertura de teste para o grant customizado de Produção ('test_api_hub_surface.py' só cobre superuser/manage_orders/filtro de URL).
- **Criar 'SHOPMAN_HUB_BASE_URL'** (não existe setting do host da Central) antes de incluir o Hub no check de domínio — gap que o WP não declarou.

## Fronteira Natural

O Hub autentica/reconcilia sessão, mostra o que o operador pode abrir e explica indisponibilidade. **Não** vende, não opera KDS, não planeja produção, não recebe NF, não dispara campanha, não executa BI e **não agrega estado operacional de outros apps** (gargalos/blocked_reason por app são responsabilidade do app dono, via summary próprio).

Contratos naturais: entrada = sessão de operador + permissões + URLs configuradas; saída = tiles 'launch|external' + empty-state com motivo. Donos externos: POS decide dinheiro; KDS decide estação; Produção decide WO; Compras decide recebimento; BI decide análise; Marketing decide campanha; Admin decide configuração.

## Evidências (verificadas)

- 'needsLogin = Boolean(error.value) || sessionExpired.value': 'surfaces/hub-nuxt/app/app.vue:41'.
- Registry usa 'can_access_production' para o tile Produção: 'shopman/backstage/projections/hub.py:85'.
- 'can_operate_production' já existe: 'shopman/backstage/permissions.py:93'.
- Superfície Produção e API usam 'backstage.operate_production': 'surfaces/production-nuxt/app/app.vue:10', 'shopman/backstage/api/operations.py:714'.
- Projection só tem 'operator_name' + 'tiles' (ref/label/description/icon/url/kind): 'hub.py:51-66'.
- Tipo tile 'launch|external' só existe no TS (lado Python não valida): 'surfaces/hub-nuxt/app/types/hub.ts:13'.
- Mock e2e com 'kind: "config"' e spec com href antigo: 'tests/e2e/mockBackend.mjs:15', 'tests/e2e/hub.spec.ts:21-23'.
- 'check_operator_cookie_domain' omite Purchase **e** Hub: 'shopman/shop/checks.py:401-408'; 'SHOPMAN_PURCHASE_BASE_URL' em 'config/settings.py:1258,1303'.
- operator-kit já tem 'httpError'/'isTransientError'/'isUnauthenticatedError'/'isStationLockedError'/'httpErrorCode': 'surfaces/operator-kit/app/utils/httpError.ts:18-83'.

## Achados Priorizados

### P1 — Tile Produção usa permissão diferente da superfície real (direção: tile escondido)

Quem tem 'backstage.operate_production' (gate do app) não vê o tile; quem tem colunas finas sem 'operate_production' vê um tile que abre 403 na API.

Proposta:
- Trocar o predicado no registry: '_AppSpec("production", ..., can_operate_production)' em 'hub.py:85' (substituir 'can_access_production').
- Guardrail: todo tile 'launch' declara 'required_permission' igual ao 'OPERATOR_PERM' da superfície destino (um teste de paridade hub↔app).
- Teste novo: usuário com **só** 'backstage.operate_production' vê o tile; usuário com 'view_production_reports' sem 'operate_production' não vê tile operacional.

Aceite:
- Usuário com 'backstage.operate_production' vê o tile Produção e abre sem 403.
- Usuário com 'view_production_reports' e sem 'operate_production' não vê tile operacional (persona de relatório fica fora deste WP).
- Teste Python cobre o grant customizado (hoje invisível à CI).

### P1 — Erro de fetch vira login falso

'needsLogin' mistura 401, 403, 'station_locked', 5xx e erro de rede. Os utilitários do operator-kit já existem e o hub não os usa.

Proposta:
- 401 → re-gate de sessão (manter 'useOperatorSession').
- 403 'station_locked' → tela de PIN (via 'isStationLockedError').
- 403 comum → estado "sem permissão" com retry da lista.
- 5xx/rede → estado "indisponível" com retry ('isTransientError' + 'onReconnect' que já existe).

Aceite:
- Teste Vue cobre 401, 403, 403 'station_locked', 500 e network error.
- A tela nunca pede senha quando o problema é API indisponível ou falta de permissão.

### P2 — URLs de superfície sem validação de config e fora do check de domínio

Proposta:
- Validar 'SHOPMAN_SURFACE_URLS' em 'manage.py check --deploy': 'https', host sob 'SHOPMAN_OPERATOR_COOKIE_DOMAIN', sem 'javascript:', sem localhost (fora de DEBUG).
- Incluir 'SHOPMAN_PURCHASE_BASE_URL' no dict de 'checks.py:401' (1 linha).
- **Criar 'SHOPMAN_HUB_BASE_URL'** em settings + incluí-lo no check (sem a config, o aceite "Hub no check" é impossível).
- URL externa permitida somente quando 'kind="external"'.

Aceite:
- 'manage.py check --deploy' falha com 'javascript:'/localhost em produção.
- Purchase e Hub entram na matriz de host/cookie.

### P2 — Projection não explica ausência (contrato de motivo, não de estado por app)

Em vez de 'tile.status/blocked_reason' (que vazaria superfícies que o operador não pode abrir), a projection ganha um **empty-state com motivo** quando a grade é vazia: "nenhum app configurado" (URLs ausentes) vs "nenhum app liberado" (permissões) — distinguível sem expor nomes.

Aceite:
- Grade vazia por falta de permissão não mostra mensagem de "configuração quebrada" e vice-versa.
- 'HubTileProjection' não ganha campos de estado por app (contrato travado por 'test_api_hub_surface.py:92').

## Melhorias UX (após os P1)

1. **Recentes por estação:** primeiro tile = último app usado na estação (requer track de uso — P3, dado novo).
2. **Teclado total:** '1-9' abre tile, '/' busca, 'Enter' abre, 'Esc' volta (só depois do P1, para não abrir app sem permissão).
3. **Handoff contextual:** deep link seguro '?from=hub&focus=<app-scoped-ref>' — o Hub repassa, não interpreta.
4. **Resumo por app (backlog):** cada superfície expõe um endpoint '/summary' mínimo; o Hub apenas lista os resumos recebidos. Não é feature do Hub.

## RBAC / setup_groups

Este WP não cria permissão nova (usa 'can_operate_production', já existente). Sem ação em 'setup_groups.py'.

## Pré-requisitos

- Nenhum. Independente dos demais WPs.

## Testes

- Python: paridade tile↔'OPERATOR_PERM' (hub vs app).
- Python: grant customizado 'backstage.operate_production' → tile visível.
- Python: validator de 'SHOPMAN_SURFACE_URLS' no check --deploy; Purchase/Hub no domínio operacional.
- Vue: classificação de erro (401/403/locked/5xx/rede).
- Vue/e2e: mock+spec corrigidos juntos (href/target do tile Loja = storefront apex, 'external'); fixture tipada rejeita 'kind' desconhecido.
- A11y: foco inicial, teclado numérico, retorno ao Hub.

## Fora De Escopo

Venda, pagamento, gaveta, fechamento, preparo KDS, expedir pedido, planejamento, QC, recebimento, campanha, BI interativo, CRUD Admin, loja do cliente, e **qualquer agregação de estado operacional cross-app** (gargalos/blocked_reason por app).

## Prompt Para Agente Executor

~~~text
Execute WP-01-agente-d (Hub / Central de Apps).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-01-agente-d-hub.md
- surfaces/hub-nuxt/app/* (app.vue, types/hub.ts, presentation/hub.ts, tests/e2e/*)
- shopman/backstage/projections/hub.py
- shopman/backstage/api/hub.py
- shopman/backstage/permissions.py (can_operate_production)
- surfaces/operator-kit/app/utils/httpError.ts
- shopman/shop/checks.py (check_operator_cookie_domain)
- config/settings.py (SHOPMAN_SURFACE_URLS, SHOPMAN_PURCHASE_BASE_URL)

Fases:
1. Trocar o predicado do tile Producao para can_operate_production + guardrail de paridade tile↔OPERATOR_PERM + teste de grant customizado.
2. Classificar erros do Hub com o operator-kit (nunca 403/5xx/rede vira login).
3. Validar SHOPMAN_SURFACE_URLS no check --deploy; criar SHOPMAN_HUB_BASE_URL; incluir Purchase e Hub no check de dominio.
4. Empty-state com motivo (sem campos de estado por app na projection).
5. Corrigir mock+spec e2e juntos; testes Python/Vue.

Nao implemente CRUD de nenhum app destino e nao agregue estado operacional de outros apps.
~~~

