# Status — Django Shopman

> Arquitetura e capacidades existentes. Este arquivo não autoriza go-live e não
> funciona como checklist de corte. Estado operacional corrente, owners e
> bloqueios vivem na
> [matriz canônica de prontidão](plans/GO-LIVE-READINESS-PLAN.md).
>
> Última revisão estrutural: 2026-09-29. Baseline revisada:
> `ab148fbd85d50865bf107e95298b712decd9d7f4`.

## Arquitetura atual

O Django expõe APIs JSON, projections, Admin/Unfold e health checks. As
superfícies de cliente e operador são apps Nuxt 4 SSR em `surfaces/`, com BFF
Nitro e autenticação compartilhada na zona de operador.

| Superfície | Código | Papel |
|---|---|---|
| Loja | `surfaces/storefront-nuxt` | catálogo, carrinho, checkout e conta |
| Shopman Apps | `surfaces/hub-nuxt` | entrada da suíte do operador |
| PDV | `surfaces/pos-nuxt` | venda presencial e caixa |
| Cozinha | `surfaces/kds-nuxt` | preparo, picking e expedição |
| Encomendas | `surfaces/orders-nuxt` | fila, detalhe e operação de pedidos |
| Produção | `surfaces/production-nuxt` | plano, mise-en-place e fornadas |
| Marketing | `surfaces/marketing-nuxt` | campanhas, ofertas e cupons |
| B.I. | `surfaces/bi-nuxt` | leitura analítica |
| Compras | `surfaces/purchase-nuxt` | compras, recebimento e insumos |
| Layer de operador | `surfaces/operator-kit` | contratos compartilhados das superfícies |

Tempo real é SSE-first conforme a
[ADR-016](decisions/adr-016-sse-first-realtime.md), com polling como fallback.
O contrato de runtime exige PostgreSQL 16+ e Redis/Valkey compatível; detalhes
ficam em [runtime-dependencies](reference/runtime-dependencies.md).

## Capacidades construídas

Os estados abaixo descrevem código existente, não inclusão no escopo comercial
v1 nem exercício contra provedores reais.

| Capacidade | Estado do código | Limite da afirmação |
|---|---|---|
| Pedidos, estoque, produção e caixa | Construído | prontidão comercial depende da matriz canônica |
| Pagamentos EFI/PIX e Stripe | Adapters e lifecycle construídos | configuração e exercício externo são estados separados |
| Fiscal Focus NFe | NFC-e S0–S4 construído | homologação/produção e validação contábil não são inferidas |
| iFood direto | Polling, webhook e catálogo construídos | escopo v1 e homologação comercial não são inferidos |
| Machine courier | Adapter, directives, webhook e UI construídos | credenciais, homologação e escopo v1 não são inferidos |
| Marketing | Cockpit, projection/actions, outbox e ledger construídos | publicação real permanece sujeita a autorização e canário |
| Autenticação | access link, SMS fallback, passkey e device trust construídos | hardening e enrollment do ambiente são operacionais |
| Admin | Django Admin com Unfold e gates canônicos | acesso comercial continua sujeito a 2FA/ingress aprovados |

Referências de implementação: [Delivery externa](plans/DELIVERY-EXTERNAL-LOGISTICS-PLAN.md),
[iFood direto](plans/IFOOD-DIRECT-INTEGRATION-PLAN.md),
[Fiscalman](plans/FISCALMAN-PLAN.md) e
[Marketing v2](plans/MARKETING-V2-CAPABILITY-COMPOSER-2026-09-26.md).

## Migrations e compatibilidade

- O repositório contém **268 arquivos de migration** na baseline de 2026-09-29.
  Essa contagem é um inventário datado, não um objetivo nem prova do banco vivo.
- O smoke do ambiente técnico consulta `/ready/`; esse endpoint falha quando há
  migration pendente. A execução datada fica na matriz canônica.
- A tag `go-live-v1` estava ausente em 2026-09-29. Portanto a
  [ADR-015](decisions/adr-015-backward-compat-policy-post-prod.md) estava
  **inativa**; o CI registra explicitamente esse estado.
- Houve uma compactação histórica antes da baseline atual. Ela não equivale a
  um reset autorizado para o cutover futuro. Qualquer novo squash/reset é um
  evento de corte, sujeito a backup, ensaio e autorização.

## Publicação e deployment

Para a baseline auditada, o fluxo hospedado é:

1. merge autorizado em `main` dispara o workflow **Deploy Images**;
2. o workflow publica no DOCR somente os componentes alterados e produz um
   manifesto do run;
3. os componentes do app DigitalOcean têm `deploy_on_push` ativo e trocam os
   contêineres ao receber as imagens;
4. o workflow **Pre-go-live Smoke** baixa o manifesto, espera um deployment
   DigitalOcean posterior ficar `ACTIVE` e só então verifica `/ready/`, menu,
   checkout não mutante e SSR.

O fluxo acima prova deployment técnico e smoke, não aprovação comercial. Os
identificadores do último run e do deployment ficam na
[matriz canônica](plans/GO-LIVE-READINESS-PLAN.md). Operações self-hosted e
diagnóstico local permanecem em [Deploy](guides/deploy.md).

## Qualidade e testes

As contagens de aproximadamente 2.200 testes de cores e 6.500 da suíte eram uma
medição de **2026-08-13**. Elas são históricas e não devem ser apresentadas como
total corrente. A evidência atual é o resultado dos gates nomeados no commit,
não uma contagem copiada para documentação.

Gates técnicos atuais incluem Runtime, Surfaces, Omotenashi, Security,
Production Contract e Operator Groups. A lista exigida pelo branch e a
evidência do commit candidato ficam na matriz canônica.

## Autoridade documental

- Este arquivo: arquitetura e capacidade construída.
- [ROADMAP](ROADMAP.md): prioridades e direção, sem repetir estado operacional.
- [GO-LIVE-READINESS-PLAN](plans/GO-LIVE-READINESS-PLAN.md): única matriz de
  prontidão e bloqueios.
- [GO-LIVE-CREDENTIALS-MATRIX](plans/GO-LIVE-CREDENTIALS-MATRIX.md): significado
  das variáveis e maturidade das integrações, sem valores secretos.
- [Pré-flight](runbooks/go-live-preflight.md),
  [cutover](runbooks/go-live-cutover.md) e
  [rollback](runbooks/rollback-de-deploy.md): procedimentos, não cronologia.

## Compatibilidade

| Requisito | Contrato |
|---|---|
| Python | `>=3.12` |
| Django | `Django>=6.1,<6.2` |
| Node.js | `>=22` |
| Banco | PostgreSQL 16+ em ambiente compartilhado |
| Cache/realtime | Redis 7+ ou Valkey compatível |

O `pyproject.toml` é a autoridade executável para versões Python/Django; este
resumo é protegido pelo gate `make canonical-docs`.
