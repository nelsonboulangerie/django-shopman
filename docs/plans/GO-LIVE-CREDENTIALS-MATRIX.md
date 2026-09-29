# GO-LIVE-CREDENTIALS-MATRIX — contrato e maturidade das integrações

> Este documento registra **nomes e significado**, nunca valores. A única fonte
> de prontidão e bloqueios é a
> [matriz canônica](GO-LIVE-READINESS-PLAN.md).

- `verificado_em`: `2026-09-29T03:06:10Z`
- `ambiente_inspecionado`: spec vivo do app DigitalOcean `shopman-nelson`
- `fonte`: leitura de nomes/tipos de variáveis, código e gates; valores não foram
  lidos nem exibidos
- `owner_da_matriz`: Plataforma
- `próximo_evento`: atualizar após mudança de spec ou decisão de escopo v1

## Cinco estados diferentes

Cada integração deve avançar explicitamente por estas colunas:

1. **credencial declarada** — o nome existe no spec; não prova valor;
2. **adapter configurado** — a configuração seleciona o adapter esperado;
3. **boot gate aprovado** — o processo sobe no perfil/ambiente declarado;
4. **integração exercida em sandbox/homologação** — probe externo sanitizado;
5. **integração exercida em produção** — efeito real autorizado e reconciliado.

É proibido colapsar essas etapas em “configurado”.

## Maturidade observada

`declarada` abaixo significa apenas presença do nome no spec vivo. `código`
significa capacidade construída na baseline. O carimbo do cabeçalho vale para
todas as linhas.

| Integração | Variáveis principais | Código | Declarada no spec | Adapter no ambiente | Boot gate comercial | Sandbox/homologação | Produção | Escopo v1 | Owner / próximo evento |
|---|---|---|---|---|---|---|---|---|---|
| Django / domínio | `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SHOPMAN_DOMAIN`, `AUTH_DEFAULT_DOMAIN`, `SHOPMAN_OPERATOR_COOKIE_DOMAIN` | VERIFICADO | VERIFICADO | DESCONHECIDO | DESCONHECIDO | N/A | DESCONHECIDO | BLOQUEADO | Plataforma + Pablo / decidir domínio comercial e rodar readiness |
| PostgreSQL / Redis | `DATABASE_URL`, `REDIS_URL` | VERIFICADO | VERIFICADO | VERIFICADO pelo `/ready/` | DESCONHECIDO | N/A | DESCONHECIDO | BLOQUEADO | Plataforma / identificar ambiente comercial e backup/restore |
| Stripe | `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CAPTURE_METHOD` | VERIFICADO | VERIFICADO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | Financeiro + Plataforma / probe autorizado e reconciliação |
| EFI PIX | `EFI_CLIENT_ID`, `EFI_CLIENT_SECRET`, `EFI_CERTIFICATE_PEM_BASE64`, `EFI_PIX_KEY`, `EFI_WEBHOOK_TOKEN`, `EFI_SANDBOX` | VERIFICADO | VERIFICADO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | Financeiro + Plataforma / probe autorizado e reconciliação |
| Focus NFe | `SHOPMAN_FISCAL_ADAPTER`, `FOCUS_NFE_TOKEN`, `FOCUS_NFE_ENVIRONMENT`; emitente em `Shop.document` ou `FOCUS_NFE_CNPJ_EMITENTE` | VERIFICADO | VERIFICADO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | Fiscal + contador / homologar, validar parâmetros e decidir escopo |
| ManyChat / WhatsApp | `MANYCHAT_API_TOKEN`, `MANYCHAT_WEBHOOK_SECRET`, `MANYCHAT_OTP_FLOW_NS` e flags de Concierge | VERIFICADO | VERIFICADO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | Produto + Marketing / decidir canal v1 e provar fluxo sem envio não autorizado |
| iFood | `IFOOD_CLIENT_ID`, `IFOOD_CLIENT_SECRET`, `IFOOD_MERCHANT_ID`, `IFOOD_WEBHOOK_TOKEN`, `IFOOD_CANCELLATION_CODE` | VERIFICADO | VERIFICADO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | Operação + Produto / decidir canal v1 e anexar homologação |
| Machine courier | `SHOPMAN_COURIER_ADAPTER`, `MACHINE_API_USER`, `MACHINE_API_PASSWORD`, `MACHINE_API_KEY`, `MACHINE_WEBHOOK_TOKEN`, `MACHINE_FORMA_PAGAMENTO`, `MACHINE_CANCEL_REASON_ID` | VERIFICADO | PENDENTE | DESCONHECIDO | N/A enquanto adapter não for selecionado | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | Operação + Produto / decidir escopo antes de pedir/configurar credenciais |
| Meta / Marketing | `META_PAGE_ID`, `META_IG_USER_ID`, `META_PAGE_ACCESS_TOKEN` e flags `SHOPMAN_MARKETING_*_ENABLED` | VERIFICADO | VERIFICADO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | Marketing / decisão shadow-canário e consentimento |
| Email / SMS | `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `COMTELE_API_KEY`, `COMTELE_ROUTE` | VERIFICADO | VERIFICADO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | DESCONHECIDO | Operação / provar entrega em contato autorizado |
| Observabilidade | `SENTRY_DSN`, `SHOPMAN_ALERT_EMAIL` | VERIFICADO | VERIFICADO | DESCONHECIDO | DESCONHECIDO | N/A | DESCONHECIDO | BLOQUEADO | Plataforma + Operação / provar recebimento de alerta sintético autorizado |

## Contrato por ambiente

Enquanto o owner não aprovar nomenclatura oficial, a documentação usa apenas:

| Ambiente | Contrato |
|---|---|
| local/CI | valores sintéticos ou mocks explícitos; nunca evidência externa |
| técnico vivo de pré-go-live | serviço acessível; pode conter combinações de sandbox, homologação ou flags; cada integração exige prova própria |
| comercial | ambiente definido pelo owner, com domínio, escopo, providers e GO/NO-GO registrados |

Os rótulos históricos `alpha`, `beta`, `soft` e `oficial` não determinam tipo de
credencial até o gate humano ser resolvido.

## Regras para atualização

- Nunca colar token, senha, certificado, webhook secret, DSN ou valor de variável.
- Registrar somente nome, tipo (`SECRET`/texto), ambiente e identificador da
  evidência sanitizada.
- Não executar probe com efeito externo sem autorização contextual.
- Uma integração fora do escopo aprovado vira `N/A`; até a decisão, fica
  `DESCONHECIDO`, não “opcional”.
- O inventário completo de nomes comentados fica em [`.env.example`](../../.env.example).

## Gates de código relacionados

- `make production-contract`: contrato hermético com valores sintéticos;
- `make production-readiness`: perfil final dependente do ambiente e evidência;
- `make smoke-gateways-sandbox`: probe externo, somente com credenciais e
  autorização adequadas;
- `python manage.py check --deploy`: valida configuração de boot, não exercício
  do provider.

Passos operacionais ficam no [pré-flight](../runbooks/go-live-preflight.md); a
sequência de corte fica no [cutover](../runbooks/go-live-cutover.md).
