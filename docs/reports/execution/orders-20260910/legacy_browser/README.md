# WP09 — navegador anterior contra backend novo

Browser: fonte **5a3383c9**, branch/worktree isolado
`codex/orders-old-browser-5a3383c9` / `django-shopman-orders-old-browser-5a3383c9`.
Nenhuma edição em fontes antigas; git status limpo após build/probe. Package.json e
lockfiles de orders/operator-kit são idênticos à execução; node_modules do checkout
de execução ligado no worktree antigo, sem reinstalar/alterar ambiente de terceiros.
Node22, Chromium, Nitro próprio 3006 → Django atual c935459be em 8014 → PostgreSQL
próprio 55439. Build antigo aprovado. API/credenciais/seed são só de laboratório.

Reprodução:

1. Build da fonte antiga com NUXT_DJANGO_BASE_URL e NUXT_PUBLIC_DJANGO_BASE_URL
   apontando para 127.0.0.1:8014, NUXT_APP_BASE_URL=/; iniciar seu Nitro em 3006.
2. `seed.py` pelo launcher isolado `.orders-lab/manage_lab.py shell`; cria pedido
   sintético accepted e item 0,500. Sem transporte/worker.
3. No cwd da execução: `node docs/reports/execution/orders-20260910/legacy_browser/probe.mjs`.
   O probe usa o Playwright instalado, autenticação real do laboratório e clique
   real da página antiga. Não intercepta POST nem fabrica a recusa.

**Resultado:** leitura autenticada e detalhe renderizado; botão antigo envia POST
sem intenção/revisão/ator observado, backend responde 400 intention_required.
Mensagem de atualização aparece no toast antigo (screenshot inspecionado).
Status accepted e timeline preservados. Comparação SHA-256/contagens confirma
zero alteração em nove tabelas: Order, OrderItem, OrderEvent, Directive,
IdempotencyKey, Cashman.Entry, PaymentIntent/PaymentTransaction e Stockman.Move.

Primeiro probe conferiu estado/timeline; repetido com hashes dos livros para
comprovar também ausência de efeitos indiretos. Ambas tentativas foram recusadas.
Ruff dos scripts Python aprovado. Não há migration nem versão antiga sobrescrita.

Limites: caso real de browser antigo cobre avanço; demais mutações usam seus
ensaios de contrato/permissão, não foram todas navegadas com este bundle. Worker
antigo continua incompatível com unknown (ensaio restore separado). Reload do
browser para mutar requer bundle novo; não se adicionou bypass de precondições.
Nenhum deploy, acesso a dado real ou comunicação externa foi executado.
