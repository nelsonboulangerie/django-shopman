# Laboratório sintético de integração

Copiar `manage_lab.py`, `serve_lab.py`, `settings_orders_lab.py` e `seed_e2e.py`
para `.orders-lab/` na raiz
do worktree isolado. Os scripts de crash abaixo são copiados apenas para esse ensaio.
Os bootstraps recusam outra DATABASE_URL/REDIS_URL. Usar cluster PostgreSQL próprio,
usuário/db `orders_lab`, bind local 55439, Redis próprio em 56389 sem persistência.
Não reutilizar banco, Redis ou credenciais de aplicação real. Não iniciar com `.env` de produção.

Ambiente dos scripts: DATABASE_URL=postgres://orders_lab@127.0.0.1:55439/orders_lab,
REDIS_URL=redis://127.0.0.1:56389/0, DATABASE_CONN_MAX_AGE=0, PYTHONDONTWRITEBYTECODE=1. Rodar da raiz:
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
movimentação financeira/fiscal real, equipamentos físicos ou esforço em campo.
A suíte atual contém26 cenários e verifica também acerto no livro sintético,
recibos por produto/célula/lote/feed, teclado, SSE e última leitura útil. Resultado
mais recente em `../catalog_width/catalog-overlap-final-integration.txt`.
Crashes de aceitação externa e restore de livros são ensaios separados em
`../notification_unknown/PROCESS-CRASH.md` e `../restore_lab/`; não atribuir suas
provas à suíte HTTP nem chamar fakes externos de homologação do fornecedor.

## Recuperação em outro processo

Após seed normal, executar `manage_lab.py shell < .orders-lab/phase_crash_seed.py`
com os mesmos ambientes. O **exit 17 é esperado**: o processo termina abruptamente
após commit da transição e da Directive, sem callback. Em processo novo, executar
`manage_lab.py process_directives --topic order.lifecycle_phase --limit 10`, depois
`manage_lab.py shell < .orders-lab/phase_verify.py`. Repetir worker e verificador:
deve permanecer um ticket com qty `0.5`, fase done e uma tentativa. O seed cria
estação picking sintética sem som, Session e itens de laboratório. Não representa
confirmação de trabalho físico executado, nem despacho, emissão ou mensagem real.
