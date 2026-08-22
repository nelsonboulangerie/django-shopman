# Alpha tecnico pronto-para-virar

Objetivo: deixar um staging publico para testadores convidados, sem dinheiro
real obrigatorio, mas com o mesmo fluxo de negocio que sera usado no go-live. O
estado aceitavel aqui e: trocar variaveis/chaves de teste para producao e rodar
o gate de producao.

## Gate canonico

```bash
make alpha-readiness preprod_url=https://staging.exemplo.com
make smoke-gateways
make omotenashi-qa strict=1
```

`make alpha-readiness` aplica `scripts/check_release_readiness.py --profile=alpha
--strict-external`. Nesse perfil:

- Pix/card podem estar em `payment_mock`, desde que `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true`.
- Pix mockado precisa ter caminho de conclusao: `SHOPMAN_EXPOSE_MOCK_CAPTURE=true`
  ou `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true`.
- `SHOPMAN_EXPOSE_DEBUG_OTP=true`, `SHOPMAN_STAGING_AUTOPILOT=true` e o botao
  "Simular pagamento" sao warnings de alpha, nao criterio de go-live.
- Focus NFe homologacao e iFood OAuth continuam bloqueios externos se faltarem,
  porque sao as integracoes que precisam ser exercitadas antes da virada.
- Evidencia manual pendente e warning durante a janela de alpha; antes de
  producao, `manual_qa_status: passed` volta a ser obrigatorio.

## Env minimo de alpha tecnico

```env
DJANGO_DEBUG=false
SHOPMAN_ENVIRONMENT=staging
DATABASE_URL=<postgres/pool>
REDIS_URL=<redis/valkey>
SHOPMAN_PREPROD_URL=https://staging.exemplo.com

SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_mock
SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_mock
SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true
SHOPMAN_EXPOSE_MOCK_CAPTURE=true
SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true

SHOPMAN_EXPOSE_DEBUG_OTP=true
SHOPMAN_STAGING_AUTOPILOT=true
```

Para fiscal homologacao:

```env
SHOPMAN_FISCAL_ADAPTER=shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend
SHOPMAN_FISCAL_EMISSION_RESOLVER=shopman.shop.fiscal_resolvers.on_request_or_tax_id,shopman.shop.fiscal_resolvers.eletronic_payment
FOCUS_NFE_ENVIRONMENT=homologacao
FOCUS_NFE_TOKEN=<token homologacao>
FOCUS_NFE_CNPJ_EMITENTE=<cnpj ou Shop.document preenchido>
```

Para iFood real de staging:

```env
IFOOD_CLIENT_ID=<oauth client_id>
IFOOD_CLIENT_SECRET=<oauth client_secret>
IFOOD_MERCHANT_ID=<merchant uuid>
IFOOD_CANCELLATION_CODE=<codigo default opcional para fallback de cancelamento>
```

`IFOOD_WEBHOOK_TOKEN` e legado/stub. O caminho primario e o worker
`python manage.py ifood_poll --watch --interval 30`; sem OAuth ele fica ocioso.

## Roteiro minimo com testadores

- Storefront: menu -> sacola -> login -> checkout -> Pix mock -> pagamento
  simulado -> acompanhamento ate concluido.
- Pagamento: tentar Pix pendente, Pix simulado, expiracao, retry e pedido ja pago.
- Operacao: pedido aparece no gestor, KDS recebe ticket, status avanca sem
  duplicar evento, cancelamento gera trilha.
- Fiscal: emitir NFC-e em homologacao para pedido elegivel, consultar status,
  reprocessar erro e cancelar uma nota de teste.
- iFood: processar `PLACED`, repetir o mesmo evento, simular falha antes do ack,
  confirmar/ready/dispatch e cancelar com codigo valido.

## Virada para producao

Antes de qualquer venda real:

```bash
make production-readiness manual_qa=docs/reports/manual-qa.md preprod_url=https://staging.exemplo.com
```

Trocas obrigatorias:

| Area | Alpha tecnico | Producao |
|---|---|---|
| Ambiente | `SHOPMAN_ENVIRONMENT=staging` | `SHOPMAN_ENVIRONMENT=production` |
| Pix | `payment_mock` | `payment_efi` + `EFI_SANDBOX=false` |
| Cartao | `payment_mock` ou Stripe test | `payment_stripe` + `sk_live_`/`pk_live_` |
| Mock | `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` | removido/`false` |
| Botao simular | `SHOPMAN_EXPOSE_MOCK_CAPTURE=true` | removido/`false` |
| Auto-confirm Pix | `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true` | removido/`false` |
| Fiscal | Focus homologacao | Focus producao |
| OTP | debug ou sender de staging | SMS/WhatsApp real, sem debug OTP |
| Autopilot | opcional | removido/`false` |
| QA | evidencia em coleta | `manual_qa_status: passed` |

Produção nao deve depender de combinado verbal. Se algum switch de teste ficar
ligado, o gate de producao e o `manage.py check --deploy` precisam ficar
vermelhos.
