# HANDOFF — Convergência das superfícies operadoras ao canon do operator-kit

## Missão (o que é o trabalho, de verdade)
Fazer cada app operador (`surfaces/*-nuxt`) **SER composto pelos mesmos componentes/anatomias canônicos** que o `surfaces/operator-kit` define e que o catálogo `surfaces/kitchensink-nuxt` (`:3009`) renderiza. Não é "deixar parecido", não é "trocar de cor": é o app **usar os componentes canônicos** — mesma composição, mesmo espaçamento, mesmo alinhamento, mesma hierarquia. Onde o app precisa de algo que o kit não tem, **o kit cresce** (vira cânone, documentado) — nunca um componente/variant local.

Começar pelo **Gestor (orders)**; depois replicar nos demais apps.

## Regra do dono
"O canônico cobre; o app cede. Se o app não puder ceder sem regressão, o canônico cresce — virando cânone, com prova; nunca virando fork local."
- Aparência herdada do canon: espaçamento, alinhamento, hierarquia, tipografia, cantos, alturas de controle (desktop = default Nuxt UI; toque 44/48 **só** no `@media (pointer: coarse)`), claro+escuro.
- **O rail dourado é DELIBERADO (marca) e NÃO é o problema.** Não mexer na cor do rail. O problema é **composição e desalinhamento**.

## Referência (a régua)
- `surfaces/kitchensink-nuxt` (`:3009`) — o catálogo canônico: seções **Anatomias, Fundamentos, Componentes, Receitas, Estados, Matriz**. É a régua renderizada.
- `surfaces/operator-kit` — a fonte dos componentes/anatomias compartilhados.
- Docs: `docs/reference/operator-kitchen-sink.md`, `docs/reference/operator-component-ledger.json`, `docs/guides/operator-surface-ux.md`, e `docs/plans/suite-ux-v2/orders/` (inventário, laudo, `auditoria-visual.md`, `header-fronteira.md`, `checklist-revisao-design.md`).

## O problema atual (por que o dono diz "parece que nada mudou")
As telas do Gestor **não são compostas pelos componentes canônicos**: há markup/composição local, desalinhamentos (spacing, altura, âncora, ritmo), e componentes que deveriam ser os do kit e não são. O app **parece** com o catálogo, mas **não é** o catálogo.

## Trabalho
1. Enumerar as superfícies do Gestor no ledger e, para cada tela/estado, comparar **componente por componente** com o catálogo (`:3009`).
2. **Substituir a composição local pela canônica do kit.** Se faltar um componente/anatomia no kit, **criá-lo no kit** (categoria 2, documentado) e usá-lo — nunca um variant local.
3. Corrigir **alinhamento** de verdade: escala de espaçamento, larguras, âncoras, alturas, ritmo vertical, hierarquia. Medir, não "no olho".
4. **Side-by-side catálogo | app** antes/depois, desktop e mobile, claro e escuro.
5. Replicar nas outras superfícies do Gestor e, depois, nos outros apps.

## Ambiente (comandos)
- Node: `export PATH=/opt/homebrew/opt/node@22/bin:$PATH`.
- Worktree do trabalho: `~/.codex/worktrees/orders-canonical/django-shopman`, branch `codex/orders-canonical-shell`, **PR #1516**. Nunca escrever no checkout principal.
- Dev do app: em `surfaces/orders-nuxt`, `NUXT_DJANGO_BASE_URL=http://127.0.0.1:8001 node node_modules/.bin/nuxt dev --host 127.0.0.1 --port 3004` (`:3004`; login admin/admin; PIN 1234 quando pedir).
- Catálogo (régua): `:3009` (admin/admin). Django orders `:8001`; Django kitchensink `:8000`.
- Gates: `python3 scripts/run_operator_visual.py --app orders --route /` (claro+escuro, todos os viewports), `python scripts/check_operator_component_ledger.py`, `nuxi typecheck`, `npm run lint`, `npm test`, `make test-operator-ux`.
- Contrato de tema × baselines: `scripts/check_theme_baseline_contract.py`; se mudar tema do kit, regerar as baselines das consumidoras (Marketing/POS) e `make theme-baselines-accept owner="..."` — ver `docs/reference/operator-visual-baselines.md`.

## Regras
- Nunca escrever no checkout principal (chão compartilhado) — só no worktree.
- Sem mudança de rota/regra/permissão/backend. Sem allowlist nos gates.
- Commit por arquivo nomeado; push (atualiza o PR #1516).
- **Evidência sempre**: side-by-side e medições. **Não declarar "pronto"** — o dono compara com o catálogo.
- Decisão de produto/gosto: **registrar**, não inventar.

## Estado atual do branch (o que já existe)
- Casca canônica (`DashboardGroup/Sidebar/Panel/Navbar/Toolbar`), `OperatorOfficeShell`, locale pt-BR.
- Header canônico (`OperatorCanonicalHeader` no kit), rail (`OperatorSuiteRailMenu/TabBar`), card `NuxtCard`, A1 `Banner`+`Slideover`, A3, purga de `op-*`, uma altura de controle, regra de toque compartilhada.
- Matriz visual **90/90** (claro+escuro). Catálogo mobile como lista. CTA do banner AA (11.3/12.05).
- Auditoria de **66 telas** em `docs/plans/suite-ux-v2/orders/auditoria-visual.md`.

## Pendências conhecidas
- **Convergência item a item ao catálogo (o foco).**
- Ajustes/Postos: título × conteúdo estreito.
- Densidade do card "Bloqueado" no mobile; contraste **não-texto** do `border` (token do kit, WCAG 1.4.11).
