# UX-N1: "Shopman" para o operador e "Central" no lugar de "Shopman Apps"

**Estado:** pronto (03/10/2026), PR #1405
**Branch:** `claude/ux-n1-nome-central`
**Plano:** `docs/plans/SUITE-UX-FUNCTION-PLAN.md` §16 e §17

## Objetivo

Decisão do dono (03/10): diante do operador o sistema se chama **Shopman**; a home dos apps de
operador (app `surfaces/hub-nuxt`, subdomínio `central.`) passa a se chamar **Central**. A loja fica
fora. O nome da loja aparece como contexto vindo do `Shop`, nunca fixo no código.

## O que foi feito

- **Regra de renomeação:** a tag `go-live-v1` não existe (`git tag -l go-live-v1` e
  `git ls-remote --tags origin go-live-v1` vazios), então valeu "zero resíduo": nenhum
  "Shopman Apps" sobra em código, comentário, teste ou doc vivo. História intocada
  (`docs/coordination/*`, `docs/plans/completed/*`, `docs/plans/_quarantine/*`,
  `docs/reports/*` e a migração `shop.0062`).
- **Fonte do nome:** `surfaces/operator-kit/app-identity.json` (`hub.label = "Central"`,
  `article = "a"`). Daí saem manifesto, título da janela ("Nelson · Central", com a casa
  vinda do `Shop.short_name`), rail, convite de instalação e a tela da Central.
- **Gênero:** "Central" é feminino, e havia frases com "ao"/"do" fixos diante do rótulo
  ("Voltar ao …", "Você não tem acesso ao …", "Versão do …"). Nasce
  `operatorAppNamed(app, preposição)` em `operator-kit/appIdentity.ts`, que contrai o
  artigo da identidade ("à Central", "da Central"); o rail, o painel de avisos e a Central
  usam essa peça.
- **"Shopman" diante do operador:** a Central mostra a linha de marca `hubBrandLine`
  ("Shopman · Nelson", casa do `Shop`; sem casa, só "Shopman") no cabeçalho e no título do
  login dela. Nenhum nome de loja no código.
- **Trava do rótulo:** `appName.guardrails.test.ts` perdeu a exceção do hub; agora nenhum
  rótulo de app cita marca ou casa.
- **Django:** `PushSubscription.Surface.HUB`, `SERVICE_LABELS["hub"]`, descrições de
  capacidade e Admin dizem "Central"; migração `shop.0086_superficie_central` (só
  `choices`, sem mudança de esquema).
- **Fica como está (identificador/infra):** id `hub`, `hub_tile`, diretório `hub-nuxt`,
  subdomínio `central.`, envs, rotas `/api/v1/backstage/hub/`. Não havia identificador
  `shopmanApps`/`shopman_apps` em lugar nenhum.

## Evidência

- `operator-kit`: `npx vitest run` → 98 arquivos, 1049 testes passaram (inclui
  `guardrails.vocabulary`); `tests/appNamed.test.ts` novo → 2 passaram.
- `hub-nuxt`: `npx vitest run` → 26 passaram; `npx nuxi typecheck` sem erro; `eslint app tests` limpo.
- pytest: `test_hub_projection_identity` + `test_api_hub_surface` → 32 passaram;
  push/capacidade/admin/deploy + `test_vocabulario_de_tela` → 2477 passaram.
- `scripts/check_surface_registry.py` → "todos os lugares concordam"; `ruff check` limpo.

## Ficou de fora

- Renomear diretório `hub-nuxt`, id `hub`, subdomínio ou envs: é DNS/deploy, fora do escopo.
- Os e2e Playwright do hub não foram rodados aqui (sem browser da CI); nenhum deles
  afirma o texto trocado.
