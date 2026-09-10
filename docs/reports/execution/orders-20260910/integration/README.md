# Laboratório sintético de integração

Copiar estes quatro scripts para `.orders-lab/` na raiz do worktree isolado.
Os bootstraps recusam outra DATABASE_URL/REDIS_URL. Usar cluster PostgreSQL próprio,
usuário/db `orders_lab`, bind local 55439, Redis próprio em 56389 sem persistência.
Não reutilizar banco, Redis ou credenciais de aplicação real. Não iniciar com `.env` de produção.

Ambiente dos scripts: DATABASE_URL=postgres://orders_lab@127.0.0.1:55439/orders_lab,
REDIS_URL=redis://127.0.0.1:56389/0, PYTHONDONTWRITEBYTECODE=1. Rodar da raiz:
`python .orders-lab/manage_lab.py migrate --noinput`, depois
`python .orders-lab/manage_lab.py shell < .orders-lab/seed_e2e.py` e
`python .orders-lab/serve_lab.py`. Dependências do projeto e Daphne são necessárias.
A senha publicada no seed pertence exclusivamente ao usuário sintético deste banco.
Cada seed cria referências novas; não apaga histórico de ensaios anteriores.

No diretório surfaces/orders-nuxt, usar Node 22, npm ci, build com
NUXT_APP_BASE_URL=/ e NUXT_DJANGO_BASE_URL/NUXT_PUBLIC_DJANGO_BASE_URL=http://127.0.0.1:8014.
Executar `ORDERS_LAB_INTEGRATION=1 npx playwright test --config playwright.integration.config.ts`.
O harness inicia Nitro em 3004; não substitui serviços que ocupem as portas.
Manifesto, screenshots, traces e logs ficam em `.orders-lab`.

Os ensaios usam HTTP real via Nitro, Django, PostgreSQL e Redis/SSE. A interrupção
controlada descarta a resposta HTTP depois do commit. Não há worker separado nem
provedores externos neste ensaio. Não demonstra homologação, restart de worker,
resultado financeiro/fiscal, equipamentos físicos ou esforço em campo.
