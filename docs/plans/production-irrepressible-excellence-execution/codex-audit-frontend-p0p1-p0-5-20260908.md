# Execução WP-P0.5 — agente `audit_frontend_p0p1`

- Data: 2026-09-08
- Worktree: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-production-irrepressible-20260908`
- Branch: `codex/production-irrepressible-excellence-20260908`
- SHA no início da implementação: `d003be80dd9edd0ee37a13e8aee5cd1040eaee8d`
- Escopo serializado pelo orquestrador: `surfaces/operator-kit`, `surfaces/production-nuxt`,
  `surfaces/Dockerfile.surface`, `scripts/run_omotenashi_browser_ci.sh` e documentação
  diretamente relacionada ao WP-P0.5.
- Exclusões: backend Django, migrations, contrato gerado de Produção e log consolidado.
- Integração: edição coordenada no worktree compartilhado; nenhum commit por instrução do
  orquestrador. Mudanças paralelas preexistentes foram preservadas.

## Estado inicial

- A rota Nuxt `/menuboard` era pública e consumia `/api/v1/storefront/menu/` sem gate.
- O layer de operador não instalava headers HTTP defensivos nem cache privado uniforme.
- O upstream Django tinha fallback local inclusive em build de produção e a validação runtime
  não rejeitava HTTP remoto.
- D4 continua aberto: faltam refs reais das TVs, credenciais e janela de troca. Este WP não
  inventa redirect nem board ref.

## Registro

### Decisões implementadas

- `/menuboard` foi removido do router Nuxt; o shell não possui mais bypass público e o mock
  recusa qualquer chamada a `/storefront/`.
- Não há redirect enquanto D4 não fornecer a `ref` real de cada TV. O Django protegido por
  credencial/SSE permanece o único owner canônico.
- A política de headers vive no `operator-kit`, com opt-in por app para não quebrar silenciosamente
  conexões cross-origin de outros consumidores do layer. O Produção ativa a política.
- Documentos e BFF recebem CSP, bloqueio de frame/object, `nosniff`, referrer/permissões mínimas,
  `private, no-store` e `Vary: Cookie`; `Vary` do Django e cookies são preservados. HSTS é emitido
  somente quando Nitro recebe HTTPS.
- Build e boot do Produção exigem ambiente explícito e upstream HTTPS remoto. E2E local exige
  simultaneamente `SHOPMAN_ENVIRONMENT=test` e `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1`.
- A imagem genérica compila com `https://django-upstream.invalid`, origem reservada e não roteável,
  somente na camada de build. Ela não vira `ENV`; o plugin repete a validação no boot.

### Arquivos do agente

- Borda compartilhada: `surfaces/operator-kit/server/{middleware/operator-security.ts,
  plugins/upstream-guard.ts,utils/operatorSecurity.ts,utils/djangoBaseUrl.ts,utils/djangoProxy.ts}`.
- Consumo/corte: `surfaces/production-nuxt/{nuxt.config.ts,app/app.vue,
  app/pages/menuboard.vue,public/robots.txt}`.
- Integração: `surfaces/Dockerfile.surface`, `scripts/run_omotenashi_browser_ci.sh`.
- Testes: `surfaces/operator-kit/tests/{djangoProxy.test.ts,operatorSecurity.test.ts}` e
  `surfaces/production-nuxt/tests/{securityConfig.test.ts,e2e/guards.spec.ts,e2e/mockBackend.mjs}`.
- Documentação: READMEs do kit/Produção/E2E e ADR-018.

### Verificação

- `operator-kit`: projeto unitário, 12 arquivos/140 testes aprovados.
- `production-nuxt`: typecheck e lint aprovados; 21 arquivos/114 testes aprovados.
- Guard focal de integração: 3 testes aprovados; `bash -n scripts/run_omotenashi_browser_ci.sh`
  aprovado.
- Playwright: 6 testes aprovados, incluindo 404 sem storefront e headers/cache/cookie/`Vary` reais
  no servidor Nitro compilado.
- Build com ambiente/HTTPS explícitos aprovado. Build sem ambiente e boot sem ambiente terminam
  com exit 1 antes de servir tráfego.
- `npm test` completo do `operator-kit`: os 140 testes node passaram, mas cinco suítes Nuxt não
  chegaram a coletar porque o runtime resolveu `/@fs/.../django-shopman/.../node_modules` no checkout
  principal em vez do worktree. Não houve falha de asserção do WP; permanece dívida do harness.

### Riscos/gates restantes

- D4 aberto: refs/credenciais das TVs e janela de cutover dependem de decisão humana.
- Scanner no host real e comportamento do edge (`X-Forwarded-Proto`, HSTS e cache intermediário)
  não podem ser validados neste worktree.
- A receita Docker recebeu guard estático, mas a imagem não foi construída localmente porque o
  executável `docker` não está instalado neste host.
- CSP ainda precisa de nonce em WP futuro para retirar `script-src 'unsafe-inline'`, exigido hoje
  pelo payload inline de hidratação do Nuxt; `unsafe-eval` e origens externas permanecem fechados.

## Complemento WP-P0.2 — 2026-09-09

- Após a regeneração do schema, foi criado um guard único para as oito mutations de domínio da
  Produção: plan, start, advance-step, void, finish, quick-finish, oven arm e oven conclude.
- O guard falha fechado antes de criar a tentativa quando offline ou quando `generated_at`,
  `source_revision`, `fresh_until` e `contract_version` estão ausentes/inválidos/vencidos. Datas
  ambíguas ou impossíveis não são coercidas; a versão deve ser um inteiro positivo.
- Cada request autorizado envia `projection_generated_at`, `source_revision`, `fresh_until` e
  `contract_version` do mesmo snapshot. Após a integração com o backend, o schema foi regenerado
  pelo comando canônico e os quatro campos passaram a fazer parte dos tipos de request gerados.
- Recusas `stale_projection` locais e remotas preservam os dados/tela, nunca repetem escrita e
  oferecem a ação `refresh` rotulada conforme o envelope do servidor.
- Validação: 5 arquivos/30 testes focais e 23 arquivos/124 testes Vitest completos aprovados;
  typecheck aprovado com o opt-in explícito de upstream de teste; lint dos arquivos de Produção
  alterados e build Nuxt/Nitro com ambiente de produção explícito aprovados. O `operator-kit` não
  possui configuração ESLint própria para validar isoladamente a extensão do harness.

## Revalidação integrada — agente raiz, 2026-09-09

- `production-nuxt`: 23 arquivos/130 testes, typecheck, lint e build aprovados.
- `operator-kit`: o link externo de `node_modules` foi substituído por instalação local no
  worktree; 17 arquivos/177 testes aprovados, eliminando a limitação do harness registrada acima.
- Playwright no servidor Nitro compilado: 6/6 aprovados.
- `export_production_schema --check`: aprovado depois da regeneração do client.
