# SEC-SURF-001 — Convergência do envelope de segurança das surfaces Nuxt

**Status:** em execução por consumer; ver "Estado por consumer"
**Prioridade:** P1 de hardening antes de piloto público ou tráfego real
**Origem:** MKT-040, [ADR-026](../../decisions/adr-026-operator-surface-security-envelope.md)
e correção local `0d39cac5f` (2026-09-09)
**Owners requeridos:** Segurança + owners das surfaces + QA
**Autorização atual:** somente documentação e implementação local do Marketing; nenhum
deploy, staging, produção ou rollout para outras surfaces está autorizado.

## Estado por consumer (29/09/2026)

| Surface | Envelope do kit (`operatorSecurityHeaders`) | Exceções de CSP (`operatorCspAllow`) | Situação |
| --- | --- | --- | --- |
| `marketing-nuxt` | envelope próprio, mais estrito (nonce) | não usa o do kit | piloto |
| `production-nuxt` | ligado | nenhuma | onda A concluída |
| `orders-nuxt` | ligado | `img-src https:` (foto do produto) e `connect-src` loopback (agente do dispositivo), por decisão do dono em 29/09/2026 | onda A com exceções declaradas |
| `kds-nuxt` | ligado | nenhuma | onda A concluída |
| `bi-nuxt` | ligado | nenhuma | onda A concluída |
| `hub-nuxt` | ligado | `img-src https:` (ícone de cada app na origem dele), decisão do dono em 29/09/2026 | onda A com exceção declarada |
| `pos-nuxt` | ligado | `script-src https://maps.googleapis.com` e `connect-src https://maps.googleapis.com https://places.googleapis.com` (autocompletar de endereço, Google Maps), `connect-src https://viacep.com.br` (endereço pelo CEP), `img-src https:` (foto do produto) e `connect-src` loopback (agente do dispositivo), por decisão do dono em 29/09/2026; `Permissions-Policy` de base (o PDV não usa geolocalização) | onda B com exceções declaradas |
| `purchase-nuxt` | ligado | nenhuma; `Permissions-Policy` com `camera=(self)` (leitura da NF pela câmera), por decisão do dono em 29/09/2026 | onda B com exceção declarada |
| `storefront-nuxt` | fora do kit | fora do kit | item separado |

**Cozinha e B.I.** O inventário de `app/`, `server/` e `nuxt.config.ts` não achou
recurso fora da própria origem: o SSE, o BFF, o manifesto e as fontes são servidos pelo
próprio app, e o bipe da Cozinha é Web Audio gerado no navegador, sem arquivo. No
Chromium headless, com o build de produção, as rotas `/`, `/<ref>` e `/pickup` (Cozinha)
e as oito rotas do B.I. carregaram sem nenhuma violação; `fetch("https://example.com/")`
foi recusado por `connect-src` nas duas, como controle negativo.

**Shopman Apps.** Cada tile mostra o ícone do app buscado na origem DELE
(`tileIconUrl`: `https://pdv.<zona>/pwa/pwa-192x192.png`, `https://kds.<zona>/…`),
e o Shopman Apps mora em `central.<zona>`. Com o envelope ligado num build de teste, a
política de base recusou esses ícones (`img-src 'self' data: blob:`) e o tile caiu no
Lucide de reserva. Não quebra a tela, mas tira o ícone real, que é função escrita no código. O dono escolheu, em 29/09/2026, a mesma regra do Pedidos: `img-src https:`, declarada no `nuxt.config` do app com o motivo.

**PDV e Compras (onda B).** O kit passou a aceitar `script-src` por app, mais estreito
que as outras diretivas: só host `https://` explícito ou curinga de subdomínio sobre
domínio fixo (`https://*.googleapis.com`), nunca `https:`, loopback, `*` ou `'unsafe-*'`.
O curinga de subdomínio passou a valer também em `img-src`, `connect-src`, `font-src` e
`media-src`, e a `Permissions-Policy` ganhou exceção por app
(`runtimeConfig.operatorPermissionsAllow`), só para recurso da lista de base e só com
`self`. No PDV, o inventário achou quatro recursos fora da origem: a Maps JS API
(bootstrap e pedaços da biblioteca Places, todos em `maps.googleapis.com`, mais o
`gen_204?csp_test=true` da própria API), as sugestões e os detalhes do endereço
(`places.googleapis.com`, Places API New), o ViaCEP e o agente do balcão; nenhuma
chamada a `navigator.geolocation`. No Chromium headless, com o build de produção, a
carga completa do Maps (bootstrap com `language`/`region`, `importLibrary("places")` e
`fetchAutocompleteSuggestions`, que chegou ao Google e voltou "API key not valid" pela
chave fictícia) não gerou violação; `/`, `/session`, `/preorders` e `/display` também
não. O Maps só de autocompletar não pediu `font-src`, `style-src` externo, `worker-src`,
`frame-src` nem `'unsafe-eval'`, por isso nenhum deles abriu. Script de
`example.com` e de `maps.gstatic.com` foram recusados por `script-src-elem`, e
`fetch("https://example.com/")` por `connect-src`, como controle negativo. No Compras,
o leitor de código (@zxing) vem do próprio bundle e a foto da nota vira `blob:`: a CSP
fica a de base. Com câmera fictícia, `getUserMedia({ video: true })` abriu no Compras e
foi recusado no PDV (`NotAllowedError`, `camera=()`); sem câmera, os dois respondem
`NotFoundError`.

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
