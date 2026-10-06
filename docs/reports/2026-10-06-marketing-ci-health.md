# Marketing — cadeia causal das falhas recorrentes do CI (2026-10-06)

- **Frente:** `codex/supply-chain-audit`, base `origin/main` = `f650d01b2`
- **Escopo:** saúde do app Marketing + supply chain das superfícies Nuxt
- **Regra que este relatório defende:** o check de Marketing tem de significar
  Marketing. Vermelho crônico e alheio é pior que nenhum check, porque treina todo
  mundo a mergear por cima.

## Sumário

O job `Marketing — cadeia completa` acumulou quatro tipos de falha. Três não são de
Marketing:

| # | Tipo | Origem real | Correção permanente |
|---|---|---|---|
| i | drift de baseline pelo tema compartilhado do `operator-kit` | tema da layer, herdado por `extends` | contrato de tema × baselines + gate (este PR) e regeração no mesmo PR |
| ii | label/rótulo obsoleto na spec visual | cópia da tela do Marketing muda e a spec não acompanha | #1512 corrige o rótulo; regra de varredura de specs no mesmo PR |
| iii | `npm audit` do `operator-kit` rodando DENTRO do job de Marketing | toolchain Nuxt transitivo do kit, atribuído ao app errado | job `Supply chain — npm audit` (este PR) + allowlist com prazo |
| iv | retrato não assentado (races) e vermelho não obrigatório tolerado | spec e desenho de check | espera de estado assentado + relógio fixo; check deixa de carregar dívida alheia |

## Como o check estava montado

`surfaces-gate.yml`, job `marketing-complete` (nome de exibição `Marketing — cadeia
completa`), rodava em `macos-15` e encadeava, entre outros, além dos passos do
Marketing:

- `Audit operator-kit supply chain` — `npm audit --audit-level=high` **do kit**;
- `Audit Marketing supply chain` — o mesmo gate para o Marketing.

O Marketing era o único job macOS que já instalava a layer do `operator-kit`, então o
audit do kit foi pendurado ali. O efeito é medido e antigo:

- [`R1-import-recipe-versions.md`](../coordination/ROUNDS/R1-import-recipe-versions.md)
  (02/10): *"o único vermelho era 'Marketing — cadeia completa' (node-forge, D-027,
  não obrigatório)"* em um PR que só reimportava comando de receita;
- [`NIGHT-SHIFT-BRIEF-2026-09-30.md`](../plans/NIGHT-SHIFT-BRIEF-2026-09-30.md), F2:
  *"`brace-expansion` no audit do operator-kit faz o check 'Marketing — cadeia
  completa' reprovar em TODOS os PRs. Vermelho crônico que todos ignoram é pior que
  nenhum check"*;
- [`UX-M1-fila-de-decisoes.md`](../coordination/ROUNDS/UX-M1-fila-de-decisoes.md):
  *"o `npm audit` vermelho por node-forge/braces é esperado e não é desta frente"*;
- [`WP-UX-8-PHASE0-NUXT-UI-REKA-SPIKE-2026-10-05.md`](WP-UX-8-PHASE0-NUXT-UI-REKA-SPIKE-2026-10-05.md):
  *"o `npm audit --audit-level=high` passou a bloquear a cadeia completa do Marketing
  por advisories transitivos"*.

E o check **não é obrigatório**: a branch protection viva de `main` (consultada via
`gh api` em 2026-10-06) não lista `Marketing — cadeia completa` entre os 23 contextos
exigidos. Por isso a fila de merge seguia com ele vermelho — e o vermelho virava
paisagem.

## Tipo (i) — Drift de baseline pelo tema compartilhado

**Evidência.** O `operator-kit` é layer consumida por `extends`; o Marketing não tem
`app.config.ts` próprio e herda o tema do kit. O #1512 (branch
`codex/operator-kitchen-sink`) adiciona `surfaces/operator-kit/app/app.config.ts` e
ajusta `operator-theme.css`; junto, muda exatamente 4 baselines de Marketing:

- `surfaces/marketing-nuxt/tests/visual/baselines/campaign-form__weekdays-320__320x568__light.png`
- `surfaces/marketing-nuxt/tests/visual/baselines/platforms__test-receipt__768x1024__light.png`
- `surfaces/marketing-nuxt/tests/visual/baselines/settings__coupon-form__390x844__light.png`
- `surfaces/marketing-nuxt/tests/visual/baselines/settings__offer-form__1280x800__light.png`

O PR é do catálogo do kit, não do Marketing — e ainda assim o Marketing mudou de
retrato. O mesmo fenômeno aparece em escala no
[`V6-SEG-MKT-VISUAL-GATE.md`](../coordination/ROUNDS/V6-SEG-MKT-VISUAL-GATE.md) (62
falhas e 17 verdes em um PR de conformidade da suíte) e no
[`UX-M1-fila-de-decisoes.md`](../coordination/ROUNDS/UX-M1-fila-de-decisoes.md) (*"a
barra de seções mudou em todas as telas, então os retratos existentes vão divergir"*).

**Por que se repetia.** Três engrenagens sem acoplamento: (1) o tema é um só e as
baselines são por app; (2) a baseline canônica só nasce no navegador pinado da CI
(`macos-15` + Chromium do Playwright) — quem só tem Linux/local não regera; (3) não
havia gate nenhum ligando "tema mudou" a "baseline regerada". O autor do PR de tema
ficava com um vermelho que ele não sabia que era dele, e muitas vezes não podia
resolver (sem macOS), então mergeava por cima.

**Correção permanente (este PR).**

- [x] Contrato versionado
  [`operator-theme-baseline-contract.json`](../reference/operator-theme-baseline-contract.json)
  com as fontes de tema (`app/app.config.ts` + `app/assets/css/*.css`), as
  consumidoras (`marketing-nuxt`, `pos-nuxt`) e um `themeFingerprint`;
- [x] Gate
  [`check_theme_baseline_contract.py`](../../scripts/check_theme_baseline_contract.py)
  (`make theme-baselines`, no `make test-operator-ux` e no job `surface-versions`);
- [x] Processo em
  [`operator-visual-baselines.md`](../reference/operator-visual-baselines.md): PR de
  tema regera as baselines afetadas NO MESMO PR e regrava o aceite com
  `make theme-baselines-accept owner="<quem aceitou>"`;
- [ ] **O #1512 precisa regravar o aceite** depois de regenerar as 4 baselines: o
  contrato nasce com o fingerprint do `main` (sem `app.config.ts`) e o gate vai
  reprovar o #1512 até isso — de propósito.

⚠️ Nenhuma baseline foi regerada neste PR. Regenerar baseline é ato com dono e com
antes/depois revisado; o gate existe para impedir o contrário.

## Tipo (ii) — Label/rótulo obsoleto na spec visual

**Evidência.** [`marketing-matrix.spec.ts`](../../surfaces/marketing-nuxt/tests/visual/marketing-matrix.spec.ts)
linha 391 esperava o grupo acessível `"Início da oferta"`; o componente
[`MarketingOfferForm.vue`](../../surfaces/marketing-nuxt/app/components/MarketingOfferForm.vue)
linhas 283 e 290 rotula `"Período de validade"`. O `getByRole("group", { name:
"Início da oferta", exact: true })` não acha o grupo que existe e o cenário quebra
antes de qualquer pixel. O #1512 corrige essa linha.

**Por que se repetia.** A spec visual consulta a UI por **nome acessível** (decisão
certa: testa o que o operador vê), mas o nome vive escrito em dois lugares — o
componente e a spec. Renomear o rótulo no componente não alcança a spec, e o erro
aparece como falha de visual, não de contrato de texto. O mesmo padrão está descrito
no V6-SEG ("testes que ainda procuravam a anatomia anterior") e no `UX-COPY1` (copy de
Marketing ficou de fora da trava de travessão justamente por ter retrato aprovado no
macOS).

**Correção permanente.** Imediata: #1512. Estrutural, recomendada como follow-up de
Marketing: o rótulo acessível de formulário testado vira **fonte única** — a spec
importa a mesma constante que o componente usa (o repo já tem o conceito de
`suite-vocabulary`), e "quem renomeia rótulo varre as specs no mesmo PR" vira regra
explícita. Enquanto a constante não existe, a varredura no mesmo PR é a trava.

## Tipo (iii) — Audit do `operator-kit` atribuído ao Marketing

**Evidência (medida em 2026-10-06, `origin/main` `f650d01b2`).** O gate reprovava as
duas superfícies de forma quase idêntica, e quase tudo era toolchain Nuxt do kit:

- `operator-kit`: 10 pacotes high/critical bloqueados — `@nuxt/devtools`,
  `@nuxt/nitro-server`, `@nuxt/vite-builder`, `@simple-git/argv-parser`, `nuxt`,
  `sharp`, `shell-quote`, `simple-git`, `source-map-js`, `vue-sonner`;
- `marketing-nuxt`: 11 pacotes — os mesmos, mais `@modelcontextprotocol/client` e
  `seroval`, menos `sharp`;
- as folhas novas eram: `simple-git` (4 GHSAs: `GHSA-v5rq-49vh-5v5c`,
  `GHSA-x6jw-m9v5-85vh`, `GHSA-g4wm-2vf7-vfgr`, `GHSA-858h-whjf-mvg5`), `sharp`,
  `shell-quote`, `source-map-js`, `seroval` e `@modelcontextprotocol/client`.

O único fix que o `npm audit` oferecia para `simple-git` é **downgrade major para
`nuxt@3.7.4`** (`isSemVerMajor: true`). O kit não escreve `simple-git`: ele chega por
`@nuxt/devtools`. Não há `@nuxt/devtools` publicado que use a faixa corrigida — não
existe correção não-quebradora. E `simple-git` é ferramenta de dev/build, não entra no
bundle de runtime.

**Por que se repetia.** O audit do kit rodava no job do Marketing e reprovava TODOS os
PRs; a dívida é transitiva, sem fix não-quebrador; o check não é obrigatório; e a
allowlist cobria só `braces` e `node-forge`, então cada advisory novo (os quatro do
`simple-git` e o `sharp`) reacendia o vermelho. A posição do passo — dentro do job de
Marketing — é metade da causa: semântica errada gera dono errado.

**Correção permanente (este PR).**

- [x] Job dedicado `Supply chain — npm audit` em `surfaces-gate.yml`, com matriz
  `operator-kit` + `marketing-nuxt`; o audit **saiu de dentro do Marketing** e o
  Marketing voltou a rodar só o que é dele;
- [x] Os dois passos de audit foram removidos do job `marketing-complete`;
- [x] Fixes não-major aplicados: `sharp` 0.35.4 → 0.35.5 (no kit **e** no
  `storefront-nuxt`, que compartilha a versão — ver `check_surface_versions.py`),
  `shell-quote` 1.10.0 → 1.12.0, `source-map-js` 1.2.1 → 1.2.2, `seroval` 1.6.2 →
  1.6.8 (Marketing) e `@modelcontextprotocol/client` 2.0.0 → 2.3.1 (Marketing);
- [x] `simple-git` (4 GHSAs) entrou na
  [`npm-audit-allowlist.json`](../../surfaces/npm-audit-allowlist.json) com motivo
  factual e prazo curto (**2026-11-20**);
- [x] Gate verde nas DUAS superfícies, com exceções rastreadas.

### Achado do caminho: `npm audit fix` cru quebra o gate de versões

`npm audit fix` (não-force) subiu `nuxt` 4.5.2 → 4.6.0 nos dois apps e reescreveu
~2.900 linhas de lock **sem corrigir nenhuma advisory folha** (só reduziu a listagem
do `@nuxt/cli`). O `check_surface_versions.py` reprovou na hora: 8 apps irmãos
ficaram com `nuxt 4.5.2` contra `4.6.0` do kit/Marketing. A regra do projeto é a
**mesma versão em todas as superfícies**, e alinhar os 10 apps era fora do escopo.
O caminho adotado — e que fecha o gate — foi `npm update` dos transitivos específicos
+ bump explícito do pino do `sharp`, mantendo `nuxt@4.5.2`. Sem `--force` em nada.

## Tipo (iv) — Outras causas

### iv.a Retrato não assentado (races no screenshot)

O V6-SEG registra três: a busca fotografada em `Buscando…` antes do estado final (a
matriz passou de 78/79 ao esperar o estado); o `axe` medindo o primeiro frame do tema
escuro antes de a cor do rótulo `Mais` assentar; e o diálogo que fotografo o campo de
data recém-focado em vez do topo (resolvido esperando o salvamento e reposicionando o
scroll). A spec de Marketing já trata o caso geral: `page.clock.setFixedTime(VISUAL_NOW)`
congela o relógio e o comentário no arquivo explica por que `Date.now = ...` não basta.
**Permanente:** estado assentado explícito antes do retrato + relógio fixo. É o
contrato que o arquivo já documenta; manter ao adicionar cenário.

### iv.b Check não obrigatório tolerado

`Marketing — cadeia completa` não está na branch protection, então o vermelho não
bloqueia merge. Enquanto o job carregava dívida alheia, isso produziu meses de "o
único vermelho é o Marketing" (R1, T1, UX-M1, OBS0310). Com o audit fora, o vermelho
de Marketing passa a ser acionável. **Recomendação para o dono:** com a cadeia
estável, promover o job a required check — o oposto só se sustenta agora que o check
significa o app.

### iv.c Allowlist compartilhada entre apps que herdam a layer

`surfaces/npm-audit-allowlist.json` é uma lista só para apps que herdam o mesmo
toolchain. Ao mover o audit para um job de supply-chain, a exceção passa a ser
explícita e auditável: advisory do kit aparece uma vez, com prazo, em vez de tingir o
job de cada app consumidor.

## O que este PR mudou (arquivos)

| arquivo | mudança |
|---|---|
| `.github/workflows/surfaces-gate.yml` | remove os 2 audits do job de Marketing; cria o job `Supply chain — npm audit` (2 apps); adiciona o gate de tema no job `surface-versions` |
| `surfaces/npm-audit-allowlist.json` | +4 entradas `simple-git` (4 GHSAs), prazo 2026-11-20 |
| `surfaces/operator-kit/package.json` + lock | `sharp` 0.35.5 + fixes transitivos |
| `surfaces/marketing-nuxt/package-lock.json` | fixes transitivos |
| `surfaces/storefront-nuxt/package.json` + lock | `sharp` 0.35.5 (versão compartilhada) |
| `scripts/check_theme_baseline_contract.py` | gate novo |
| `docs/reference/operator-theme-baseline-contract.json` | contrato/aceite do tema |
| `docs/reference/operator-visual-baselines.md` | processo de regeração |
| `Makefile` | alvos `theme-baselines` e `theme-baselines-accept`; gate no `test-operator-ux` |
| este relatório | cadeia causal |

## O que fica de fora (com dono)

- **#1512**: regerar as 4 baselines + regravar o aceite do tema
  (`make theme-baselines-accept owner=...`); corrigir o rótulo da spec (já no PR).
- **Marketing**: fonte única do rótulo acessível de formulário (follow-up).
- **Dono**: decidir sobre tornar `Marketing — cadeia completa` required check.

## Evidência de execução (2026-10-06)

- gate antes: `check_npm_audit_gate.mjs` exit 1 nas duas superfícies;
- gate depois: exit 0 nas duas, com exceções temporárias rastreadas;
- `python scripts/check_surface_versions.py`: verde (38 pacotes compartilhados, 11
  apps);
- `python scripts/check_theme_baseline_contract.py`: verde; teste de falha forçada
  (tema alterado) reprovou como esperado e voltou ao verde após restaurar.
