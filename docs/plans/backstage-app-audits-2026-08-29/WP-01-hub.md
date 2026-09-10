# WP-01 - Hub / Central De Apps

**Status:** pronto para implementacao  
**Superficie:** `surfaces/hub-nuxt` + `api/v1/backstage/hub/`  
**Objetivo:** transformar o Hub na casa segura do operador: abre o app certo, mostra bloqueios reais, evita tile morto e orienta para o maior gargalo sem virar mini app operacional.

## Fronteira Natural

O Hub deve autenticar/reconciliar sessao, mostrar o que o operador pode abrir, indicar a proxima acao certa e explicar indisponibilidade. Ele nao vende, nao opera KDS, nao planeja producao, nao recebe NF, nao dispara campanha e nao executa BI.

Contratos naturais:

- Entrada: sessao de operador, estacao confiavel, permissoes, URLs configuradas, resumo operacional.
- Saida: tiles, deep links seguros, status por app, CTA de gargalo.
- Donos externos: POS decide dinheiro; KDS decide estacao/ticket; Producao decide WO; Compras decide recebimento; BI decide analise; Marketing decide campanha; Admin decide configuracao.

## Evidencias Principais

- Projection estreita: `shopman/backstage/projections/hub.py:51`, `:63`.
- Hub API usa `IsBackstageOperator`: `shopman/backstage/api/hub.py:18`.
- Tela trata qualquer erro como login: `surfaces/hub-nuxt/app/app.vue:40`.
- Tipo de tile aceita `launch | external`: `surfaces/hub-nuxt/app/types/hub.ts:12`.
- Mock e2e ainda usa `kind: "config"`: `surfaces/hub-nuxt/tests/e2e/mockBackend.mjs:15`.
- `SHOPMAN_PURCHASE_BASE_URL` entra nas URLs: `config/settings.py:1256`, `:1303`.
- Check de dominio operacional omite Purchase: `shopman/shop/checks.py:401`.

## Achados Priorizados

### P1 - Tile Producao usa permissao diferente da superficie real

O Hub decide visibilidade por `can_access_production`, enquanto o app e a API usam `backstage.operate_production`.

Proposta:

- Criar campo canonico `can_operate_production` no contexto/projection do Hub.
- Se houver persona de relatorio, criar tile separado: `Producao - relatorios`.
- Adicionar guardrail: todo tile `launch` declara `required_permission` igual ao `OPERATOR_PERM` do app destino.

Aceite:

- Usuario com `view_production_reports` e sem `operate_production` nao ve tile operacional de Producao.
- Usuario com `operate_production` ve tile e abre sem 403.

### P1 - Erro de fetch vira login falso

`needsLogin = Boolean(error.value) || sessionExpired.value` mistura 401, 403, `station_locked`, 5xx e erro de rede.

Proposta:

- Usar utilitarios de `operator-kit` para classificar erro.
- 401: sessao expirada.
- 403 `station_locked`: tela de PIN.
- 403 comum: sem permissao.
- 5xx/rede: indisponibilidade com retry.

Aceite:

- Teste Vue cobre 401, 403, 403 `station_locked`, 500 e network error.
- Tela nunca pede senha quando o problema e API indisponivel.

### P1 - URLs de tiles sao repassadas sem validacao de host/esquema

`_surface_urls()` mescla settings e `build_operator_hub` devolve URL diretamente.

Proposta:

- Validar URLs de `launch` fora de DEBUG: `https`, host sob `SHOPMAN_OPERATOR_COOKIE_DOMAIN`, sem `javascript:`, sem localhost.
- Permitir URL externa somente quando `kind="external"`.
- Incluir Hub e Purchase no check de dominio/cookie operacional.

Aceite:

- `javascript:` e `http://localhost` fora de DEBUG falham no check.
- Purchase entra na matriz de host/cookie.

### P2 - Projection nao carrega estado operacional

Hoje `OperatorHubProjection` tem apenas `operator_name` e `tiles`. Isso força a UI a ser um launcher cego.

Proposta:

- Adicionar `station`, `session`, `tile.status`, `tile.badge`, `tile.blocked_reason`, `tile.stale_at`, `tile.primary_action`.
- Manter tudo resumido: sem listas de pedidos, sem ledger, sem detalhe de campanha.

Aceite:

- Tile pode renderizar `ok`, `blocked`, `offline`, `stale`, `missing_url`, `forbidden`.
- Empty state diferencia falta de permissao de configuracao incompleta.

## Melhorias UX

1. **Leve-me ao gargalo:** CTA no topo calculado no backend, por exemplo pedidos atrasados, caixa fechado, insumo critico ou producao parada.
2. **Tiles com motivo:** tile nao desaparece silenciosamente quando houver valor operacional em explicar o bloqueio.
3. **Recentes por estacao:** primeiro tile pode ser ultimo app usado naquela estacao.
4. **Teclado total:** `1-9` abre tile, `/` busca, `Enter` abre, `Esc` volta.
5. **Handoff contextual:** deep link seguro `?from=hub&focus=late_orders`, sem o Hub conhecer CRUD interno.

## Testes

- Python: tile Producao segue permissao operacional real.
- Python: validator de URL de superficie.
- Python: check inclui Purchase e Hub no dominio operacional.
- Vue: classificacao de erro.
- Vue/e2e: fixture tipada rejeita `kind` desconhecido.
- A11y: foco inicial, teclado numerico, retorno ao Hub.

## Fora De Escopo

Venda, pagamento, gaveta, fechamento de caixa, preparo KDS, expedir pedido, planejamento de fornada, QC, recebimento de NF, criacao de campanha, BI interativo, CRUD Admin e loja do cliente.

## Prompt Para Agente Executor

```text
Execute WP-01 Hub / Central de Apps.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/WP-01-hub.md
- surfaces/hub-nuxt/app/*
- shopman/backstage/projections/hub.py
- shopman/backstage/api/hub.py
- shopman/backstage/api/permissions.py
- surfaces/operator-kit/app/utils/httpError.ts

Implemente em fases pequenas:
1. Corrigir contrato de permissao do tile Producao e adicionar guardrail de tile vs OPERATOR_PERM.
2. Classificar erros do Hub sem transformar 403/5xx em login falso.
3. Validar URLs de tiles e incluir Purchase/Hub nos checks de dominio operacional.
4. Ampliar projection com status minimo de tile.
5. Adicionar testes Python/Vue.

Nao implemente CRUD de nenhum app destino. O Hub aponta, resume e protege a entrada.
```

