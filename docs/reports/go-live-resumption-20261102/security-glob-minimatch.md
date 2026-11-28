# Correção restrita de glob e minimatch

Auditoria de 02/11/2026, com fonte `origin/main` em
`0dc8b733032cf91b4bfff4c02f65fc62ce538236`.

## Achados e escopo

A consulta autenticada do Dependabot encontrou 24 alertas moderados novos, dois
por lockfile das 12 superfícies com dependências:

- [GHSA-3g3m-2fjr-6pw4](https://github.com/isaacs/node-glob/security/advisories/GHSA-3g3m-2fjr-6pw4):
  glob pode continuar trabalho de filesystem depois do cancelamento por AbortSignal;
- [GHSA-g3hv-75wg-m249](https://github.com/isaacs/minimatch/security/advisories/GHSA-g3hv-75wg-m249):
  amplificação de padrões durante a otimização de globparts pode consumir CPU/memória.

O efeito descrito é disponibilidade quando padrões ou árvores de arquivos são
influenciados por terceiros. A auditoria não demonstrou um caminho explorável
por cliente no Shopman e não trata ausência de demonstração como prova de ausência.
Os locks classificam essas dependências como produção, portanto não se afirma
que sejam exclusivamente de desenvolvimento.

A correção de glob e do minimatch geral elimina 13 dos 24 alertas moderados
quando os locks chegarem ao main. Onze alertas moderados de minimatch permanecem
na subárvore de desenvolvimento do eslint-plugin-import-x, conforme a exceção
abaixo. Eles continuam visíveis e não foram aceitos como risco zero.

Os 12 alertas baixos de deepmerge continuam sem versão corrigida publicada.
Nenhum desses alertas foi descartado ou colocado em allowlist nesta correção.

## Por que o override não é um upgrade cego

A [issue #574](https://github.com/nelsonboulangerie/django-shopman/issues/574)
congela upgrades gerais sem análise. Este patch não integra os grupos do
Dependabot nem muda Nuxt, Vue, Unfold, Django ou os SDKs dos provedores.

O registro npm foi consultado: glob `14.0.3` e minimatch `11.0.4` eram as estáveis
mais recentes. Ambos suportam Node `18 || 20 || >=22`, incluindo o Node 22 do
build/deploy. Os overrides são idênticos em todos os 12 manifests e locks.
A resolução também atualiza path-scurry `2.0.2` para `3.0.0`, dependência de glob.
O lock da loja também passa de lru-cache 11.5.2 para 11.5.3 nessa árvore.
As remoções do lock são a deduplicação dos glob/minimatch antigos e de sua árvore,
não a remoção de bindings opcionais de plataforma.

Foram lidos os consumidores reais antes de alterar as faixas transitivas:

| Consumidor | API efetivamente usada | Prova de compatibilidade |
|---|---|---|
| archiver-utils 5.0.2 | `glob.sync(pattern, options)` | expansão de arquivos e exclusão de subdiretório pelo próprio consumidor |
| filelist 1.0.6 | `minimatch.match(files, pattern, options)` | inclusão e exclusão com FileList real |
| readdir-glob 1.1.3 | `new Minimatch(...)` | filtro assíncrono de arquivos pelo próprio consumidor |
| Nuxt/Nitro, Workbox, ESLint e formatadores | APIs modernas de glob/minimatch | builds, lint, testes das superfícies e CI completa |
| eslint-plugin-import-x 4.17.1 | import nomeado `makeRe`, removido em minimatch 11 | exceção transitiva 10.2.6 e lint real de todos os 12 apps |

`globConsumerCompatibility.test.ts` mantém os três primeiros contratos na suíte
do operator-kit. Não presume que um export existente seja prova suficiente.
A mesma suíte verifica arquivos normais, extensão diferente, subdiretório e
arquivo oculto em uma árvore temporária, removida ao terminar.

## Exceção estreita e pendência upstream

A CI detectou um consumidor que a primeira prova não cobria: a regra
`no-internal-modules` do eslint-plugin-import-x importa `makeRe`. Esse export não
existe em minimatch 11.0.1 nem 11.0.4; a versão mais recente do plugin (4.17.1)
ainda exige minimatch 9/10. Substituir tudo cegamente reprova o lint Nuxt.

Somente esse plugin recebe `minimatch: 10.2.6` como override aninhado. Não há
shim, fork, regra ESLint desativada ou mudança do audit-level. Todos os demais
consumidores resolvem minimatch 11.0.4 e glob 14.0.3.

O alcance foi conferido nos 11 locks afetados: tanto o plugin quanto seu
minimatch aninhado têm `dev: true`. A regra lê padrões `allow`/`forbid` de
`context.options[0]`, isto é, configuração de lint do repositório. Não foi
identificado caminho de entrada de cliente para esses padrões. Isso restringe
o alcance observado; não elimina o advisory nem autoriza descartá-lo.

Owner: Engenharia (`ti@boulangerie.com.br`). Rever até **09/11/2026** e quando
houver versão do plugin compatível com minimatch corrigido. A pendência está na
matriz canônica. Não foi criada allowlist nova, e os gates existentes foram
preservados.

## Evidência operacional separada de autorização comercial

A [evidência sanitizada](evidence/ci-deploy-live-20261103T005747Z.json) registra
ACTIVE, manifesto de publicação, health/ready, backups, Watchman e prontidão do
alvo. A matriz canônica recebeu somente as linhas remedidas, com carimbo próprio.

O perfil comercial continua bloqueado; segredos de produção, bootstrap atual e
ensaios físicos não foram promovidos por inferência. Confirmação de produção
física, gaveta, impressão e operação real continua humana. Nenhuma credencial,
compra, reseed, fork, restore, DNS ou configuração viva foi alterada.

A saída efetiva dos testes, builds e auditoria npm fica na PR #2093. A CI completa
continua obrigatória antes do merge.

## Verificação local da correção

- Node 22 e locks regenerados com npm 10.9.9; npm ci e lint passaram nos 12 apps, inclusive Status após a exceção estreita do plugin.
- operator-kit: 178 arquivos e 1.910 testes passaram, incluindo os três contratos dos consumidores; lint passou.
- loja: 133 arquivos e 1.140 testes passaram com dois workers. A primeira execução simultânea com outras suítes excedeu o hook de inicialização Nuxt em um arquivo (14 testes não executados); a repetição completa passou sem alterar timeout ou teste.
- Produção: 57 arquivos e 546 testes passaram; Marketing: 52 arquivos e 474 testes passaram.
- builds de loja, Produção e Marketing passaram com ambiente staging explícito e upstream HTTPS.
- npm audit dos 12 locks: zero high/critical e nenhum glob vulnerável; o kit não tem moderate. Nos outros 11 apps, permanece o advisory moderado do minimatch apenas sob eslint-plugin-import-x, além de deepmerge baixo. [Saída sanitizada](evidence/ci-deploy-security-audit-pr2093.json).
- guard de versões, governança documental/ADR e canonical docs passaram; nenhum binding de plataforma foi removido dos locks.

Esses resultados não substituem a CI da PR nem a confirmação humana das rotinas físicas.

## Falha de preview Cloudflare em 03/11/2026

Os logs autenticados do preview `9560e3fa-ab5d-4041-a0e4-46e5c3fceec8`
confirmaram falha antes do build: npm 11.12.1 recusou o lock com três
`Missing: minimatch@10.2.6`. A configuração remota selecionou Node 24.15.0,
embora o contrato do projeto seja Node 22.x. O comando e diretórios remotos
estavam corretos (`npm run generate`, raiz `surfaces/status-nuxt`, saída `dist`).

O erro foi reproduzido com npm 11.12.1 localmente; não foi atribuído apenas à
versão de Node. Seu resolvedor aplicava a exceção aninhada do plugin também
a três consumidores distintos. Overrides explícitos de minimatch 11.0.4 para
`@eslint/config-array`, `@typescript-eslint/typescript-estree` e `eslint`
preservam a exceção estritamente no plugin e tornam os locks instaláveis
com npm 10 e 11. As versões compartilhadas foram mantidas iguais nos 12 apps.
Nenhuma configuração viva, credencial, termo ou UI foi alterado.

[Prova sanitizada npm 10/11](evidence/ci-deploy-npm10-11-compat-pr2093.json):
12 instalações reais com cada npm (`--ignore-scripts`, sem dry-run), lint dos
12 apps e geração do Status passaram em Node 22. As versões já travadas não
mudaram, e o único minimatch 10 continua sob o plugin de lint.

## Revisão de 07/11/2026: correção upstream

Fonte: `origin/main` em `cda1fdbfb`. O registro npm passou a ter
eslint-plugin-import-x **4.18.0**, publicado em 06/11/2026 às 19:26Z por GitHub
Actions com atestado de proveniência SLSA. A faixa declarada virou
`minimatch: ^9.0.3 || ^10.1.2 || ^11.0.1`. O tarball foi lido antes da troca:
nenhum arquivo de `lib/` menciona `makeRe`, e `no-internal-modules` importa só
`Minimatch`, que minimatch 11 exporta.

O que mudou:

- os 12 manifests perderam o override aninhado
  `"eslint-plugin-import-x": { "minimatch": "10.2.6" }`. Os overrides gerais
  (`glob ^14.0.3`, `minimatch ^11.0.4`) continuam;
- `npm update eslint-plugin-import-x --package-lock-only` nos 11 locks que têm
  o plugin (o do operator-kit não o instala): 4.17.1 vira 4.18.0, o minimatch
  aninhado 10.2.6 sai, o plugin passa a usar o minimatch 11.0.4 da raiz e entram
  `cjs-module-lexer` 2.3.0 e `es-module-lexer` 3.0.4, ambos `dev: true`.
  Nenhum outro pacote do lock mudou.

Prova, saída de comando de 07/11/2026:

| Verificação | Resultado |
|---|---|
| `npm audit --package-lock-only` no lock do kds-nuxt do `main` | 2 moderados (`minimatch` aninhado, GHSA-g3hv-75wg-m249, e o plugin que depende dele) e 7 baixos |
| o mesmo audit nos 12 locks do branch | 0 moderados em todos, nenhuma entrada `minimatch`; restam os baixos já conhecidos (7 ou 10 por superfície) |
| `npm ls minimatch` no kds-nuxt | `eslint-plugin-import-x@4.18.0` com `minimatch@11.0.4 deduped` |
| kds-nuxt `eslint .` e `vitest run` | lint sem erro; 19 arquivos, 231 testes passando |
| storefront-nuxt `eslint .` e `vitest run` | lint sem erro; 1218 passando. Os 8 que falharam (`justPlaced`, `usePwaInstall`) quebram por `localStorage.clear` no Node 26 local, que tem Web Storage nativo; com `--no-experimental-webstorage` os 12 testes dos dois arquivos passam. A CI roda Node 22 |

A 4.18.0 também reescreve o núcleo de análise de módulos do plugin. O changelog
diz que nenhuma regra deveria mudar o que relata; o lint das duas superfícies
não trouxe relato novo, e a CI do PR roda o lint das 12.

O PR #2086 do Dependabot não resolveria este item: ele só sobe minimatch
`^10.2.5` para `^10.2.6` em subárvores e não toca no eslint-plugin-import-x.
O congelamento da issue #574 continua; esta é uma troca pontual e analisada,
não a integração do grupo.

Pendência que sobra: conferir no Dependabot, depois do merge, que os 11
alertas moderados fecharam.
