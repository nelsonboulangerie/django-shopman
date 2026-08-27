# Release secrets runbook

Este runbook fecha os bloqueios externos reportados por
`scripts/check_release_readiness.py`. Nao cole segredos em chat, issue, PR ou
arquivo versionado. Preencha-os direto no ambiente de staging/producao.

## 1. Onde colocar

Na DigitalOcean App Platform, coloque segredos como app-level environment
variables com `Encrypt` ligado. Variaveis dinamicas como `${APP_URL}` podem ser
`GENERAL`; chaves, tokens, certificados e webhooks devem ser `SECRET`.

Variaveis que desbloqueiam o readiness local:

```env
SHOPMAN_PREPROD_URL=https://staging.example.com
SHOPMAN_MANUAL_QA_EVIDENCE=/path/to/manual-qa.md
```

Use `docs/runbooks/manual-qa-evidence-template.md` como base. O arquivo so
passa no readiness quando a primeira linha estiver marcada como
`manual_qa_status: passed`.

## 2. Contato publico da loja

O storefront usa `Shop.phone` e `Shop.social_links` para projetar
`home.public_config.whatsapp_url`. Configure com o comando idempotente:

```bash
python manage.py configure_shop_contact \
  --phone 554333231997 \
  --email nelson@boulangerie.com.br
```

Ou use variaveis de ambiente e rode o mesmo comando sem argumentos:

```env
SHOPMAN_SHOP_PHONE=554333231997
SHOPMAN_SHOP_EMAIL=nelson@boulangerie.com.br
SHOPMAN_SHOP_WHATSAPP=https://wa.me/554333231997
```

```bash
python manage.py configure_shop_contact
```

Valide:

```bash
curl -s "$SHOPMAN_PREPROD_URL/api/v1/storefront/home/" \
  | python -m json.tool \
  | rg 'whatsapp_url|phone_display'
```

## 3. Core secrets

Obrigatorias para staging/producao fora de `DEBUG`:

```env
DJANGO_SECRET_KEY=<strong random secret>
DOORMAN_ACCESS_LINK_API_KEY=<strong random server-to-server key>
```

Use `python - <<'PY'` localmente para gerar valores quando o provedor nao gerar:

```bash
python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

## 4. EFI Pix

Obtenha na Conta Efi:

```env
EFI_SANDBOX=true
EFI_CLIENT_ID=<homologacao client id>
EFI_CLIENT_SECRET=<homologacao client secret>
EFI_CERTIFICATE_PATH=/app/secrets/efi-homologacao.p12
EFI_PIX_KEY=<chave pix de homologacao/producao>
EFI_WEBHOOK_TOKEN=<shared secret definido para o webhook>
EFI_MTLS_HEADER=HTTP_X_SSL_CLIENT_VERIFY
```

⚠️ **O `EFI_WEBHOOK_TOKEN` viaja NA URL do webhook**, porque a Efí não envia
cabeçalho customizado (os mecanismos dela são mTLS, allowlist de IP e hash no
fim da URL registrada). Cadastre a URL já com a query:

```
https://api.<dominio>/api/webhooks/efi/pix/?token=<EFI_WEBHOOK_TOKEN>
```

O header `X-Efi-Webhook-Token` continua aceito, para dev local e para um proxy
futuro que consiga injetá-lo.

⚠️ **A verificar no primeiro cadastro: a Efí acrescenta `/pix` ao fim da URL
registrada.** A doc de webhooks dela documenta o parâmetro `ignorar=` justamente
para suprimir esse append (exemplo oficial:
`https://seu_dominio.com.br/webhook?hmac=xyz&ignorar=`). Como a nossa URL já
termina em `/pix/`, o append pode entregar num caminho que não existe — e o
sintoma seria "a Efí não notifica", sem erro do nosso lado. Confirme o caminho
efetivamente chamado no primeiro webhook real; se o append acontecer, a saída é
registrar a URL com `&ignorar=` no fim. Consultado em 19/08/2026 em
[dev.efipay.com.br/docs/api-pix/webhooks](https://dev.efipay.com.br/docs/api-pix/webhooks/).

### Allowlist de IP — pesquisada em 19/08/2026, recomendação: **não ligar**

A terceira camada da Efí, a allowlist de IP, existe no view e é **opt-in**:
`EFI_WEBHOOK_IP_ALLOWLIST=<CIDRs ou IPs separados por vírgula>`. Vazia (default)
não filtra nada — configuração ausente não pode ser o motivo de a loja parar de
receber pagamento.

**A Efí publica endereço, mas não publica uma faixa em que se possa confiar.**
As duas fontes oficiais discordam entre si:

| Fonte | O que publica | Data |
|---|---|---|
| [Webhooks — API Pix](https://dev.efipay.com.br/docs/api-pix/webhooks/) (doc corrente) | **um** endereço: `34.193.116.226`. Sem CIDR, sem lista. | atualizada em 02/06/2026 |
| [Central de Ajuda — "Quais endereços de IP a Efí utiliza?"](https://sejaefi.com.br/central-de-ajuda/api/quais-enderecos-de-ip-gerencianet-utiliza) | **28** endereços `/32` sob o título "Callbacks" | corpo do artigo datado de **13/02/2017** |

As duas são consistentes no que se sobrepõe (o `34.193.116.226` da doc corrente
está na lista de 28), mas isso não resolve o problema: são **elastic IPs da AWS**
(`34.19x.*` e `52.67.*`), a lista completa tem oito anos, e nenhuma das páginas
promete estabilidade. Uma allowlist montada sobre isso não falha com aviso —
falha com 401 em todo webhook de pagamento, silenciosamente, no dia em que a Efí
trocar um EIP. **Allowlist errada é pior que allowlist ausente**, e esta tem
prazo de validade desconhecido.

⚠️ **Armadilha da Central de Ajuda:** a mesma página tem um segundo bloco,
"Envio de e-mails", com faixas largas (`54.240.0.0/18` é Amazon SES,
`199.255.192.0/22`, `199.127.232.0/22`, `177.66.7.0/24`). Copiar a página inteira
para a allowlist do webhook abriria ~16 mil endereços da SES a troco de nada. Se
um dia ligar, use **só** o bloco "Callbacks".

⚠️ **Segunda armadilha, nossa:** o IP que o app lê é o último salto do
`X-Forwarded-For`, e na DO App Platform esse salto pode ser da própria plataforma,
não da Efí. Antes de ligar qualquer coisa, é preciso **primeiro observar** —
recusa loga o IP visto, e um webhook real precisa ter chegado para haver o que
observar. Em 19/08/2026 não havia tráfego de webhook da Efí nos logs do staging,
ou seja: hoje não temos nem a medição que autorizaria a decisão.

**O que sobra de mitigação real, e é o que está no ar:**

1. o **token na URL** (`?token=`), que é o mecanismo que a Efí de fato oferece —
   a doc dela chama de hash/HMAC e recomenda usar junto com o IP, nunca em vez de;
2. o **strip da query string no Sentry** (`_strip_query_string` em
   `config/settings.py`, travado por
   `shopman/shop/tests/test_sentry_query_scrubbing.py`), sem o qual o token
   vazaria em texto puro em todo evento de erro;
3. a **rotação** do `EFI_WEBHOOK_TOKEN` tratada como credencial vazada por
   desenho (rotacionar = recadastrar a URL na Efí).

**O que faria diferença de verdade** — e é decisão de infraestrutura, não de
código: um **proxy mTLS na frente** do app. É o mecanismo canônico da Efí (por
norma do Banco Central: chave pública da Efí no servidor, handshake em duas
requisições, TLS 1.2+), é criptográfico em vez de topológico, e não quebra quando
a AWS troca um IP. O view já sabe consumi-lo: `EFI_MTLS_HEADER`
(`X-SSL-Client-Verify: SUCCESS`) existe e é lido. Falta o proxy, que a DO App
Platform servindo direto não nos dá. A Efí publica até um exemplo de nginx
(`github.com/efipay/mtls-webhook`).

**Se um dia ligar mesmo assim**, o valor documentado hoje seria só o da doc
corrente, e o procedimento é ligar em **staging** primeiro e observar antes de
tocar em produção:

```
EFI_WEBHOOK_IP_ALLOWLIST=34.193.116.226/32
```

Reconfira o valor na doc da Efí na hora de ligar — este runbook registra o que
ela dizia em 19/08/2026, e é exatamente esse o dado que envelhece.

### Consequências de o token ser a autenticação única

Sem a allowlist configurada e sem proxy mTLS na frente (DO App Platform
direto), esse token é a autenticação **única** do endpoint — e ele fica gravado
no access log do provedor por desenho. Duas consequências que NÃO são higiene
opcional:

1. o `before_send` do Sentry (`config/settings.py`) corta a query string de
   `request.url`; sem ele todo evento de erro carregava o segredo em texto puro
   (`send_default_pii=False` não remove query string);
2. rotacionar o `EFI_WEBHOOK_TOKEN` significa **recadastrar a URL na Efí**, já
   que o segredo é parte dela.

O certificado precisa existir no filesystem do container no caminho de
`EFI_CERTIFICATE_PATH`. Se o provedor de deploy nao monta arquivo secreto,
converta isso em etapa de build/runtime segura antes de habilitar `payment_efi`.
Nao commite `.p12`, `.pem` ou dumps base64 do certificado.

## 5. Stripe

Para sandbox, use chaves de test mode:

```env
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CAPTURE_METHOD=manual
```

O `STRIPE_WEBHOOK_SECRET` e por endpoint e por ambiente. Nao reutilize o segredo
de endpoint live no endpoint test, nem o segredo impresso pelo Stripe CLI em
staging.

## 6. iFood

Para o contrato atual do Shopman:

```env
IFOOD_WEBHOOK_TOKEN=<shared token usado pelo endpoint legacy/local>
IFOOD_MERCHANT_ID=<merchant id de staging/producao>
```

Se a integracao migrar para o formato novo do Developer Portal com assinatura
`X-IFood-Signature`, alinhe o adapter antes de marcar o smoke como provado.

## 7. ManyChat e AccessLink

```env
MANYCHAT_API_TOKEN=<token outbound da API ManyChat>
MANYCHAT_WEBHOOK_SECRET=<segredo HMAC inbound>
MANYCHAT_OTP_FLOW_NS=<flow namespace do OTP, quando aplicavel>
MANYCHAT_SUBSCRIBER_RESOLVER=shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.resolve
MANYCHAT_WHATSAPP_ID_FIELD_ID=<id do campo espelho WhatsApp ID no ManyChat>
DOORMAN_ACCESS_LINK_API_KEY=<mesmo segredo core acima>
```

Nao confunda:

- `MANYCHAT_API_TOKEN`: autentica chamadas Shopman -> ManyChat.
- `MANYCHAT_WEBHOOK_SECRET`: valida chamadas ManyChat -> Shopman.
- `MANYCHAT_WHATSAPP_ID_FIELD_ID`: permite resolver subscriber por `WhatsApp ID`, sem depender do campo sistêmico `phone`.
- `DOORMAN_ACCESS_LINK_API_KEY`: autentica criacao server-to-server de access links.

## 8. Ativar gateways reais

Enquanto credenciais reais nao estiverem prontas, mantenha staging tecnico em
mock explicito:

```env
SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_mock
SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_mock
SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true
SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true
```

Depois que EFI/Stripe estiverem completos:

```env
SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_efi
SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_stripe
SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=false
```

## 9. Validar

Sem falhar por bloqueios externos:

```bash
python scripts/check_release_readiness.py
```

Falhando se qualquer credencial/evidencia externa ainda faltar:

```bash
python scripts/check_release_readiness.py --strict-external
```

Com argumentos diretos:

```bash
python scripts/check_release_readiness.py \
  --strict-external \
  --preprod-url "$SHOPMAN_PREPROD_URL" \
  --manual-qa-evidence "$SHOPMAN_MANUAL_QA_EVIDENCE"
```

Resultado esperado antes de trafego real: nenhum `failed` e nenhum
`blocked_external`. Se `manychat.ordering_webhook` aparecer como
`blocked_by_implementation`, o contrato ainda nao esta provado para pedidos
conversacionais inbound; use ManyChat apenas para OTP/access-link ate esse
smoke ser implementado.
