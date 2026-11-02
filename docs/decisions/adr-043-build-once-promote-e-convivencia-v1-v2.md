# ADR-043 — Construir uma vez, promover o mesmo digest; V1/V2 dentro da mesma superfície

**Data:** 2026-11-02
**Status:** Aceito
**Escopo:** `.github/workflows/deploy-images.yml`, Dockerfiles, superfícies Nuxt, `operator-kit`, Watchman
**Origem:** WP-RELEASE-01 (`docs/plans/WP-RELEASE-01-versoes-de-apps-sem-quebra.md`), R0. Decisão do dono de 23/10/2026 (COORDENACAO-GO-LIVE §6): R0+R1 entram antes do go-live.

## Contexto

Hoje o push no `main` constrói as imagens e a tag móvel publicada é o deploy do alpha:
construir e lançar são o mesmo gesto. Para produção com operação real faltam três coisas:
saber qual artefato está no ar sem abrir o painel da nuvem, promover para produção o
**mesmo** artefato que passou no alpha, e trocar a experiência de um app (V1/V2) sem
quebrar a versão estável.

## Decisão

1. **Construir uma vez.** Cada componente (`web`, `storefront-nuxt`, `operator-floor`,
   `operator-office`) é construído uma vez por commit, no `deploy-images.yml`, e
   identificado por digest e tag `<tag>-<sha>`. Promoção (R2) e rollback (R3) só
   retaggeiam digests existentes; não existe `docker build` fora desse workflow para "a
   mesma" versão.
2. **A identidade é da imagem, e entra na última camada.** `SHOPMAN_BUILD_SHA`,
   `SHOPMAN_RELEASE_ID` e `SHOPMAN_RELEASE_COMPONENT` chegam como build args e viram ENV e
   LABEL OCI no fim de cada Dockerfile. Não entram no `nuxt build`: o valor muda a cada
   commit, e um build arg no estágio de cada app invalidaria os oito `nuxt build` dos
   grupos a cada push (hoje mudar o PDV reconstrói só o estágio do PDV). A tela pergunta a
   versão ao próprio servidor (`/health/release`), que é exatamente o artefato no ar.
3. **Release ID é nome de composição, não SemVer.** `AAAAMMDD-HHMM-<sha curto>`, hora do
   commit em UTC: determinístico por commit, ordenável, legível ao telefone.
4. **Main produz candidato; produção exige promoção explícita** (R2): workflow manual,
   GitHub Environment protegido, mesmo digest do alpha. Push comum nunca altera produção.
5. **V1/V2 de interface nasce dentro da superfície existente**, em rota/árvore própria,
   consumindo os mesmos contratos canônicos. Segunda surface ou segundo processo só com
   incompatibilidade técnica provada, ADR própria, custo medido e data para apagar a
   duplicação (a DO custa caro, e cada componente novo é custo fixo).
6. **Versão de UX não cria versão de regra nem de API.** Campo novo é aditivo; `/api/v2/`
   só com contrato realmente incompatível.
7. **Seleção da variante é server-side, aderente e reversível**, por coortes nomeadas
   (`off`/`internal`/`pilot`/`default`) guardadas na configuração canônica por loja
   (`RuleConfig`), com kill switch sem deploy e data de remoção obrigatória.
8. **Rollback tem três níveis distintos**: flag (sem deploy), componente (digests do
   release set anterior, sem rebuild) e dados (último recurso, ADR-015).

## Consequências

- Com a R1 no ar, o suporte e a Central respondem "qual versão está aí?" pelo
  `/health/release` e pela linha "Versão do serviço"; a sonda `release_identity` do
  Watchman confere o `main` contra o vivo.
- Componente que o deploy seletivo não reconstruiu continua servindo o commit antigo, e
  isso é correto. Quem compara vivo com `main` usa contenção (nada do componente mudou
  entre os dois), nunca igualdade; a tabela de caminhos é a do `deploy_components.py`.
- Imagem construída fora do workflow fica sem identidade e a sonda reprova: é o sinal de
  que algo foi ao ar por fora da esteira.
- V1/V2 permanente é dívida: toda flag de versão carrega `remove_after`, e a R4 faz a CI
  reprovar flag vencida.

## Alternativas descartadas

- **SemVer do monorepo.** Esconderia que os quatro componentes andam em commits diferentes.
- **Identidade no bundle do cliente (build arg no `nuxt build`).** Custaria o cache dos
  grupos de operador a cada push; e o que importa ao suporte é o servidor que respondeu.
- **Rebuild na promoção.** Produziria um artefato que nunca passou pelo alpha.
- **Segunda surface por versão.** Duplica auth, BFF, deploy e custo; vira exceção com ADR.
