# SEC-SURF-001 — Convergência do envelope de segurança das surfaces Nuxt

**Status:** registrado; implementação transversal deliberadamente adiada
**Prioridade:** P1 de hardening antes de piloto público ou tráfego real
**Origem:** MKT-040, [ADR-026](../../decisions/adr-026-operator-surface-security-envelope.md)
e correção local `0d39cac5f` (2026-09-09)
**Owners requeridos:** Segurança + owners das surfaces + QA
**Autorização atual:** somente documentação e implementação local do Marketing; nenhum
deploy, staging, produção ou rollout para outras surfaces está autorizado.

## Achado confirmado no código

As oito surfaces internas `bi-nuxt`, `hub-nuxt`, `kds-nuxt`, `marketing-nuxt`,
`orders-nuxt`, `pos-nuxt`, `production-nuxt` e `purchase-nuxt` estendem o
`operator-kit`.

O kit já aplica o envelope CSP/cache/security nas respostas BFF e SSE. Porém, somente o
Marketing conecta esse mesmo envelope ao HTML SSR por middleware + hook de render. Nas
demais surfaces, a página raiz ainda não tem a mesma garantia de CSP, frame protection,
HSTS, `nosniff`, referrer policy, COOP e permissions policy.

Essa assimetria explica também por que o CSS do `production-nuxt` funcionava em
desenvolvimento enquanto o Marketing apareceu sem estilo: a CSP estrita do Marketing
bloqueava os `<style>` dinâmicos criados pelo Vite HMR. O commit `0d39cac5f` corrigiu o
perfil compartilhado para permitir somente `style-src-elem 'unsafe-inline'` no branch
compile-time de desenvolvimento; `script-src` permanece nonce-only e o build de
produção permanece estrito.

## Decisão registrada

1. O Marketing permanece como piloto do envelope estrito; sua segurança não será
   reduzida para imitar a ausência atual de CSP global nas demais surfaces.
2. O comportamento genérico deve viver no `operator-kit` como perfil/módulo opt-in.
   Cada surface deve apenas habilitar o perfil e declarar dependências externas
   estritamente necessárias; não haverá cópia de middleware/plugin por app.
3. Nenhuma surface será habilitada em massa. Cada consumer passa por inventário de
   recursos externos, testes de desenvolvimento e produção, matriz de headers e revisão
   visual antes da adoção.
4. O `storefront-nuxt` fica fora deste item: é superfície pública/branded, não estende o
   `operator-kit` e usa imagens, Maps, WhatsApp e fontes externas. Ele exige threat model
   e perfil CSP próprios.
5. Exceção CSP só pode ser específica por diretiva, com owner, motivo e expiração.
   `unsafe-inline` para scripts, wildcard amplo e relaxamento de `frame-ancestors` não
   são soluções aceitas.

## Dependências que impedem rollout cego

- `pos-nuxt` carrega Google Maps em runtime e consulta ViaCEP;
- várias surfaces usam `@nuxt/fonts`, cujo comportamento de build e assets servidos
  deve ser comprovado por consumer;
- links/imagens remotos e integrações futuras precisam de allowlists mínimas por
  diretiva (`connect-src`, `img-src`, `font-src`, `script-src`), nunca de uma abertura
  global;
- a correção do HMR deve continuar restrita a `import.meta.dev`, sem atravessar o bundle
  de produção.

## Sequência proposta

1. **MKT-049 — contrato e CI:** transformar o envelope em opt-in canônico do
   `operator-kit`; criar matriz executável HTML/BFF/error/SSE e testes de consumer. Não
   habilitar outras surfaces como efeito colateral.
2. **MKT-050 — documentação:** publicar a capability e configuração no README do
   `operator-kit`, mapa de surfaces e roadmap; referenciar este ID e manter exceções
   visíveis.
3. **Onda A — consumers sem dependência runtime conhecida:** auditar e habilitar
   `production-nuxt`, `orders-nuxt`, `kds-nuxt`, `hub-nuxt` e `bi-nuxt`, um por vez.
4. **Onda B — consumers com integrações adicionais:** auditar e habilitar
   `purchase-nuxt` e `pos-nuxt`, com allowlists específicas e testes de Maps/ViaCEP.
5. **Storefront:** abrir item separado, com threat model de superfície pública e sem
   herdar implicitamente o perfil de operador.

As ondas A/B constituem trabalho transversal sucessor; não serão embutidas
silenciosamente no plano de Marketing nem executadas antes dos gates abaixo.

## Gates humanos

- **G-SEC-S01 — Segurança:** aprovar a matriz de diretivas/headers e qualquer exceção
  com owner e expiração.
- **G-SEC-S02 — owner da surface:** confirmar as dependências externas legítimas e que
  falhar fechado não inviabiliza a operação.
- **G-SEC-S03 — QA/operador não autor:** validar login, navegação, dados, SSE, dark/light,
  refresh e HMR em cada consumer no ambiente autorizado.
- **G-SEC-S04 — release:** autorizar separadamente canary/deploy/rollback. Este registro
  não concede essa autorização.

## Critérios de aceite executáveis

- perfil global implementado uma vez no `operator-kit`, opt-in explícito por surface;
- HTML SSR, assets, BFF, erros e SSE passam a matriz aprovada de security/cache headers;
- desenvolvimento apresenta CSS aplicado (`document.styleSheets` e estilo computado),
  HMR funcional e zero `unsafe-inline` em `script-src`;
- build de produção não contém a exceção de style do desenvolvimento e mantém nonce,
  frame protection, HSTS, `nosniff`, referrer policy, COOP e permissions policy;
- dependências externas permitidas somente nas diretivas e hosts comprovadamente
  necessários; host não allowlisted falha fechado;
- unit, component, typecheck, lint, build, Playwright visual/security e testes do
  `operator-kit` passam para cada consumer tocado;
- nenhum teste requer credencial real, destinatário, escrita externa ou produção;
- rollback remove somente o opt-in da surface, preservando BFF/SSE e sem reduzir a
  política das surfaces já aprovadas.

## Definition of Done deste follow-up

O item só pode ser encerrado quando todas as sete surfaces de operador restantes
adotarem o perfil ou tiverem exceção documentada, aprovada, com owner e expiração; o
Marketing continuar verde em dev e produção; a documentação central refletir o estado
real; e as evidências por consumer estiverem anexadas ao commit/ambiente testado.

Até lá, a formulação honesta é: **o Marketing possui envelope HTML endurecido; o
`operator-kit` protege BFF/SSE compartilhados; equivalência global entre surfaces ainda
é dívida viva registrada em `SEC-SURF-001`.**
