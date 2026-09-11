# ADR-026 — Envelope de segurança compartilhado das surfaces de operador

**Status:** Aceito · 2026-09-09
**Escopo:** `operator-kit` e as surfaces Nuxt internas que o estendem
**Evidência de origem:** MKT-040, correção `0d39cac5f` e
[`SEC-SURF-001`](../reports/execution/operator-surface-security-followup-20260909.md)

## Contexto

As surfaces internas de operador compartilham BFF, SSE e utilitários através do
`operator-kit`. O kit já aplica CSP/cache/security às respostas BFF e SSE, mas somente o
Marketing conecta o envelope ao HTML SSR. Copiar o comportamento atual de outra surface
para o Marketing removeria controles exigidos pelo MKT-040; habilitar a CSP do Marketing
em massa também é inseguro, porque alguns consumers usam dependências runtime como
Google Maps e ViaCEP.

A CSP estrita revelou ainda uma diferença entre build e desenvolvimento: o Vite HMR
cria `<style>` no browser e não consegue aplicar o nonce gerado pelo SSR. Tratar isso
com relaxamento amplo faria o CSS voltar ao custo de enfraquecer scripts ou produção.

## Decisão

1. O envelope HTML de segurança é capability compartilhada do `operator-kit`, habilitada
   explicitamente por cada surface; middleware/plugin não deve ser copiado entre apps.
2. O Marketing é o primeiro consumer/piloto e não será enfraquecido para igualar as
   surfaces ainda não migradas.
3. Em desenvolvimento, somente `style-src-elem` pode receber a exceção necessária ao
   Vite HMR, selecionada por `import.meta.dev`. `script-src` permanece nonce-only e o
   build de produção permanece estrito.
4. A adoção nas demais surfaces é gradual e exige inventário de dependências, allowlist
   mínima por diretiva, testes do consumer e aprovação humana. Mudança no
   `operator-kit` nunca implica opt-in silencioso dos apps.
5. `unsafe-inline` para scripts, wildcard amplo e relaxamento de frame protection não
   são soluções aceitas. Exceção deve ter diretiva específica, owner, motivo e
   expiração.
6. O `storefront-nuxt` não herda esta política: por ser superfície pública/branded e
   não consumir o `operator-kit`, exige perfil e threat model próprios.
7. Esta ADR define arquitetura; não autoriza canary, deploy, staging ou produção.

## Consequências

- HTML, BFF, erros e SSE podem convergir sem duplicação e sem baixar a proteção já
  aprovada no Marketing.
- O modo dev continua visualmente fiel sem carregar a exceção para produção.
- Cada surface paga o custo explícito de provar recursos externos legítimos e seus
  testes de fluxo, em vez de receber uma CSP genérica permissiva.
- Até o fechamento de `SEC-SURF-001`, não se pode alegar equivalência global de
  segurança entre as surfaces.

## Gates e prova mínima

- Segurança aprova matriz e exceções; owner confirma dependências; QA/operador não autor
  valida fluxo real; release autoriza rollout separadamente.
- Unit/component, typecheck, lint, build, Playwright visual/security e testes dos
  consumers tocados devem passar.
- Dev deve comprovar CSS aplicado e HMR funcional, sem `unsafe-inline` em scripts;
  produção deve comprovar nonce, frame protection, HSTS, `nosniff`, referrer policy,
  COOP e permissions policy.

O inventário, ondas propostas, critérios completos e Definition of Done ficam no
registro executável [`SEC-SURF-001`](../reports/execution/operator-surface-security-followup-20260909.md).
