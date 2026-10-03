# UX-COPY1: copy de operador sem travessão

- **id:** UX-COPY1
- **sessão:** reforma SUITE-UX, onda 1 (Claude, subagente em worktree próprio)
- **branch:** claude/ux-copy1-sem-travessao
- **PR:** #1428
- **estado:** pronto, na fila (auto-merge)
- **início / fim (UTC):** 2026-10-03 / 2026-10-03

## Objetivo
Regra da casa (CLAUDE.md, "Copy sem travessão"): nenhum texto visível ao operador usa travessão.
Achado real: `OperatorPushSettings.vue` ("Peça a quem cuida do sistema para ligá-lo — enquanto
isso, ..."). Varrer os 8 apps de operador + kit + router e o backend que chega à tela do operador,
reescrever cada frase, e pôr uma trava que olhe o texto visível (template e literais exibidos),
não só comentários.

## Por que escapava
Havia trava em dois cantos só: os defaults da `OmotenashiCopy`
(`shopman/shop/tests/test_omotenashi_copy_keys.py`) e o separador do `__str__`
(`test_separador_de_nome.py`). Nenhuma lia o `<template>` dos `.vue`, as `presentation/*.ts`, as
mensagens de erro das APIs, a copy de projection, o Admin ou os e-mails. A trava de vocabulário do
kit lê o arquivo inteiro, mas procura outra palavra.

## O que mudou
Cada frase reescrita lendo o sentido (ponto, vírgula, dois-pontos, parênteses; " · " onde o
travessão separava dois nomes, como já é regra no `__str__`).

| onde | linhas |
|---|---|
| bi-nuxt | 2 |
| kds-nuxt | 11 |
| pos-nuxt | 1 |
| production-nuxt | 18 |
| purchase-nuxt | 6 |
| operator-kit | 13 (+ o espelho `installGuide.ts` do Storefront, que é byte a byte o do kit, por trava) |
| hub-nuxt, orders-nuxt, operator-router | 0 (só o "—" sozinho de célula vazia) |
| shopman/shop (services, handlers, adapters, Admin, models fora do estado da migração) | 74 |
| shopman/backstage (api, services, projections, bi, Admin, admin_console) | 61 |
| packages (buyman 5, fiscalman 10, guestman 3, offerman 5, doorman 1, payman 1) | 25 |
| seed (alerta de devolução, três etiquetas de consumo do B.I.) | 4 |
| `docs/reference/suite-vocabulary.md` | a forma canônica "Sem conexão — o que está na tela..." contradizia a regra; passou a "Sem conexão. O que está na tela..." |

Do backend, 58 linhas são do Admin/Unfold (texto que o gestor lê: `help_text` de formulário,
`choices` de select, mensagens, títulos de aba). Testes que fixavam a frase antiga atualizados.

## Travas novas
- `surfaces/operator-kit/tests/guardrails.noEmDash.test.ts`: lê os apps de operador (do
  `registry.json`), o kit e o roteador (`.vue`, `.ts`, `.mjs`, `.js`, `.json`), descontando
  comentário. Passa o "—" sozinho (sinal de "sem valor" em célula) e o meia-risca de intervalo
  ("20:00–08:00"). Exceções declaradas com motivo: `marketing-nuxt/` e `OfflineBanner.vue` (ver
  abaixo) e o parser `windowTitle.ts` (regex, não texto). Tem teste da própria regra e teste que
  falha se uma exceção ficar órfã.
- `shopman/backstage/tests/test_copy_sem_travessao.py`: literais de string do servidor
  (`shopman/shop`, `shopman/backstage`, `packages`) pelo AST. Fora: docstring, argumento de
  `logger.*` (não de `messages.*`, que vai para a tela), `extend_schema`/`OpenApi*`, cabeçalho
  `// AUTO-GENERATED` de arquivo gerado, a instrução do prompt da IA que CITA a regra ("sem
  travessão (—)"), e o texto que mora no estado da migração (abaixo).

## Ficou de fora, com motivo
1. **marketing-nuxt (cerca de 22 frases) e `OfflineBanner.vue` (1)**: o Marketing tem matriz de
   retratos aprovada no macOS da CI (`Marketing — cadeia completa`, `maxDiffPixelRatio 0.001`), e
   o aviso de conexão aparece no retrato `global-error__offline`. Retrato só se regrava pela CI
   (CLAUDE.md), e o #1424 está regravando 37 deles agora. Dívida com nome: seguimento que troca a
   copy e regrava os retratos a partir do artefato `marketing-browser-gates`, depois do #1424.
   As exceções na trava do kit somem nesse seguimento.
2. **Texto no estado da migração** (`help_text`, `verbose_name`, `choices` de `TextChoices`,
   `violation_error_message` de constraint, nos models): trocar exige `AlterField` em seis apps,
   quatro do Core, e colide numeração com as frentes em voo. Provado: mudar só a mensagem da
   constraint do `buyman.MaterialConversion` já gerava `buyman.0012`. WP próprio, com migração.
3. **Nomes de produto do seed** ("Chalosofia Kãnfa — Lata 50g" e irmãos) e o hint do defeito
   "Contaminado" (vem também da migração de dados `shop.0018`): dado vivo do catálogo, curado pelo
   dono, que só muda no alpha com reseed ou migração de dados. Pergunta para o dono.
4. **Storefront** (`shopman/storefront/`, `storefront-nuxt` fora do espelho do guia): voz própria,
   frente própria. **Saída de comando** (`management/commands/`) e **log**: não chegam à tela.

## Evidência
(preenchida abaixo com a saída dos comandos)
