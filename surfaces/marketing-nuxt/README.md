# Marketing — `marketing-nuxt`

- **Proprietário operacional:** Produto/Marketing
- **Última verificação:** 2026-09-10
- **Verificado contra:** rotas e contratos do `HEAD`
- **Gate de deriva:** `make marketing-docs`

Cockpit headless do gestor de Marketing, servido no host `mkt.`. É aqui que um
fato operacional vira anúncio revisável: o operador edita, confere a consequência,
aprova, agenda, cancela e acompanha o resultado por plataforma. A superfície não
resolve audiência, autorização, consentimento, horário, oferta nem entrega; ela
renderiza as projeções e executa somente as ações oferecidas pelo Django.

O contrato completo e a lista de rotas verificadas estão em
[`docs/reference/marketing-surface-contract.md`](../../docs/reference/marketing-surface-contract.md).

## O que cada plataforma significa

- Instagram, Facebook e Google Meu Negócio são publicações públicas: um destino por
  plataforma, sem membro de público.
- WhatsApp é mensagem direta: um destino por pessoa elegível, com consentimento
  revalidado antes da tentativa.
- Mensagem direta no Instagram não é suportada. Uma futura implementação deverá ser
  outra capacidade e outro fluxo de entrega, com consentimento, limites, prontidão e
  comprovante próprios; nunca será inferida do Instagram público.

Portanto, “12 pessoas; Instagram e WhatsApp” significa uma publicação pública no
Instagram e até 12 mensagens no WhatsApp — não 12 mensagens no Instagram.

## Corte de responsabilidade

- O Nuxt é o único cockpit e o único lugar de operação de Marketing.
- O Admin/Unfold é apenas auditoria agregada para `shop.audit_marketing`; não oferece
  escrita duplicada e não expõe membros, contatos, outbox ou tentativas individuais.
- O backend é a autoridade de estado e de ações. Abrir a tela nunca publica.
- A permissão ampla legada `shop.manage_campaigns` não autoriza aprovar, publicar,
  disparar, testar nem configurar plataformas. As capacidades granulares são
  revalidadas no backend no instante de cada comando.

## Rotas da superfície

<!-- marketing-ui-routes:start -->
- `/`
- `/announcements/:id`
- `/campaigns`
- `/history`
- `/platforms`
- `/templates`
<!-- marketing-ui-routes:end -->

O histórico é um aprofundamento acessível por contexto, não uma aba primária. Links
antigos em `/campaign/announcements/:id` recebem redirecionamento para o detalhe atual.
Os probes são `/health/live` (processo/BFF) e `/health/ready` (BFF + prontidão do
Django). O BFF same-origin atende `/api/v1/**`; o SSE pessoal atende
`/sse/notifications` e apenas invalida a leitura para que o cliente refaça o fetch.

## Segurança que aparece para o operador

- Sessão válida é requisito antes do primeiro fetch protegido.
- Ações sensíveis usam versão/CAS, chave de idempotência, confirmação contextual e,
  conforme a consequência, nova autenticação, TOTP ou duplo controle.
- Resultado aceito mas não confirmado, falha parcial e resultado incerto permanecem
  distintos; repetição cega de resultado incerto é proibida.
- Contagem zero, fonte degradada, plataforma sem prontidão, fato vencido ou permissão
  revogada bloqueiam a consequência com motivo e próximo passo no mesmo contexto.
- Rascunho é isolado por operador/loja/objeto e sobrevive a reload, navegação e 401;
  conflito exige comparação, nunca sobrescrita silenciosa.
- A interface é em pt-BR. Identificadores técnicos estáveis podem permanecer em inglês
  somente em logs, payloads, código ou auditoria técnica.

## Desenvolvimento local sem efeito externo

Use Node 22 e navegue por `127.0.0.1`, nunca por `localhost`:

```bash
cd surfaces/operator-kit && npm ci
cd ../marketing-nuxt && npm ci
npm run dev
```

O app abre em `http://127.0.0.1:3006`. O ensaio completo e hermético usa banco e
cookie próprios, adapter `SIMULATION_ONLY` e porta 3008; siga
[`docs/operations/marketing-local-simulator.md`](../../docs/operations/marketing-local-simulator.md).
Ele produz comprovantes `sim_…`, mas nunca prova credencial ou entrega de um provider
real.

## Gates mecânicos

```bash
npm test
npm run lint
npm run typecheck
npm run build
MARKETING_E2E_MANAGED=1 npm run test:e2e
MARKETING_E2E_MANAGED=1 npm run test:a11y
npm run test:visual
npm run test:security
npm audit --audit-level=high
```

O job `Marketing — cadeia completa` executa essa cadeia com Node 22, `npm ci`,
Chromium e runner fixados. O contrato Django v2, o OpenAPI e o cliente TypeScript são
regenerados juntos por `python manage.py export_marketing_client`; o Runtime Gate usa
`--check` e reprova qualquer deriva.

Na raiz do repositório também existem:

- `make marketing-capacity`: pico 2× sem provider;
- `make marketing-drills`: oito falhas sintéticas e seus runbooks;
- `make marketing-diagnose`: fotografia somente leitura, sem PII;
- `make marketing-simulator`: worker local ponta a ponta sem rede.

## Estrutura atual

```text
app/
├── pages/          painel, campanhas, modelos, plataformas, histórico e anúncio
├── components/     formulários, confirmações, resultados e primitivas de UI
├── composables/    projeções, sessão, comandos, recuperação, SSE e rascunho
├── generated/      cliente TypeScript gerado do OpenAPI
├── presentation/   copy/formatação pt-BR sem política de domínio
└── types/          tipos locais de apresentação
server/
├── api/v1/[...path].ts       BFF Django
└── routes/health/*           liveness e readiness
```

O nome estável é `marketing-nuxt`; `mkt.` é configuração de deploy e não deve ser
hardcoded no app.
