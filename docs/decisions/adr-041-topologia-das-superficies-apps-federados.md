# ADR-041 — Topologia das superfícies: apps federados sob uma layer e uma Central

**Status:** Proposto
**Data:** 2026-10-19
**Escopo:** `surfaces/*` (registro, apps Nuxt, `operator-kit`, `operator-router`), Django headless
**Origem:** laudo adversarial de soberania, achado A10-1 (`docs/reports/core-sovereignty-adversarial-2026-10-18.md`)

## Contexto

O laudo de 18/10/2026 registrou que não há ADR de topologia: nada escrito decide se as
superfícies são **um app só**, **um shell que carrega módulos** ou **apps federados**.
A decisão existe de fato, espalhada em ADRs de recorte (ADR-012 e ADR-014, contrato
headless; ADR-016, SSE; ADR-030, dois services de deploy; ADR-038, envelope de
segurança) e no `surfaces/registry.json`. Sem ela escrita, cada frente nova pode
reabrir a pergunta, e a ADR-030 (que é sobre **deploy**, não sobre produto) passa por
resposta.

O que está no `main` em 19/10/2026:

- **11 apps registrados** em `surfaces/registry.json`: 9 de produto (`storefront`,
  `hub`, `pos`, `kds`, `orders`, `production`, `marketing`, `bi`, `purchase`), um
  interno (`kitchensink`, `kind: internal`, sem tile e sem ingress) e um público
  independente (`status`).
- Cada app é um Nuxt próprio, com subdomínio próprio (`central.`, `pdv.`, `kds.`,
  `gestor.`, `prod.`, `mkt.`, `bi.`, `compras.`, `status.`; a loja no apex) e BFF Nitro
  próprio que fala com o Django por API JSON (`/api/v1/`, `/api/v1/backstage/`).
- Os 8 apps de operador estendem a mesma layer (`surfaces/operator-kit`: BFF canônico,
  bloqueio por PIN, conectividade, telemetria, envelope de segurança opt-in, vocabulário
  e componentes) e fixam a mesma versão dela; a loja tem harness próprio.
- A **Central** (`hub`) é a home do operador e lança os outros apps por tile; a sessão
  é um cookie do Django no domínio pai, então trocar de app não pede novo login.
- No deploy, os apps de operador rodam em dois services (ADR-030), atrás de um roteador
  por `Host` sem dependências. Isso é empacotamento: cada app continua sendo build,
  rota, CSP e saúde próprios.
- Nasce superfície nova por `make new-surface`, e `scripts/check_surface_registry.py`
  reprova o que divergir do registro.

## Decisão proposta

A topologia canônica é **federada**: uma superfície de produto é um app Nuxt próprio,
com subdomínio, BFF e ciclo de build próprios, registrado em `surfaces/registry.json`.
O que é comum entre os apps de operador mora **uma vez** na layer `operator-kit`; a
navegação entre eles é a Central, não um shell que os carrega.

Consequências que valem a partir do aceite:

1. Não se cria shell, micro-frontend em runtime nem app que hospede telas de outro.
   Tela nova de um domínio entra no app daquele domínio; domínio novo de rotina vira
   app novo, por `make new-surface`.
2. Comportamento repetido em dois apps de operador sobe para o `operator-kit`, nunca é
   copiado (regra que o CLAUDE.md já aplica ao envelope de segurança).
3. Agrupar apps no mesmo contêiner (ADR-030) continua sendo decisão de custo de deploy,
   reversível, e não muda a topologia de produto.
4. Admin/Unfold não é superfície de operador: rotina diária não mora lá
   (`docs/reference/admin-surface-boundary.json`).

## Alternativas consideradas

- **App único** (uma SPA com todas as telas): um build e uma sessão, mas o PDV offline
  (ADR-013), o kiosk da Produção e a cozinha passam a carregar código e falhas uns dos
  outros, e o envelope de segurança vira um só para perfis de risco diferentes.
- **Shell com módulos**: navegação contínua, ao custo de um contrato de carregamento em
  runtime que hoje não existe e de acoplar o ciclo de deploy de todos ao do shell.

## Pergunta ao dono

Aceitar a federação como topologia canônica (status passa a **Aceito**)? A alternativa é
abrir um WP para medir o shell antes de decidir.
