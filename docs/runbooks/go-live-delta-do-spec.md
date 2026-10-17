# Go-live: o delta do spec no dia D

> A loja vira produção **no próprio app vivo `shopman-nelson`**
> (`40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`, contexto `shopman-do-app-admin`),
> **no mesmo banco** (D-029, decisão do dono B1 = 1). Não há app novo nem
> spec novo: a virada é trocar as chaves abaixo no painel do app, numa
> gravação só. Este documento é a lista inteira. A mesma lista é a tabela
> `DELTA` de `scripts/golive_spec_delta.py`, que é **a única** regra de chave
> do gate `make production-readiness target=1` (modo alvo,
> `scripts/release_readiness_target.py`): o script imprime o que colar, o gate
> diz se está pronto, e os dois leem o spec do mesmo jeito. Um teste
> (`shopman/shop/tests/test_golive_spec_delta.py`) prende tabela e documento.
>
> Sequência do dia (quem, quando, rollback de dado): [go-live-cutover.md](go-live-cutover.md).
> Segredos de produção dos provedores: [GO-LIVE-CREDENTIALS-MATRIX](../plans/GO-LIVE-CREDENTIALS-MATRIX.md).

"Hoje" é o spec vivo lido em 10/10/2026 por `doctl apps spec get` (só nomes e
valores não secretos). Segredo nunca aparece aqui: onde o dia D pede um valor
novo, quem cola é o dono, no painel, como `Encrypt`.

## Como usar

1. **Abrir a janela: guardar o spec de antes.** Fora do repositório (tem
   segredos cifrados), com sha256:

   ```bash
   doctl --context shopman-do-app-admin apps spec get 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f \
     --format yaml > ~/golive-spec-antes.yaml && shasum -a 256 ~/golive-spec-antes.yaml
   ```

2. **Ver o que falta virar** (somente leitura, nada muda no app):

   ```bash
   .venv/bin/python scripts/golive_spec_delta.py
   ```

   A saída lista cada chave como `[OK]`, `[VIRAR]`, `[SEM PROVA]` (segredo
   presente, mas sem `--baseline` não dá para saber se foi trocado) ou
   `[LIMPEZA]`, e termina com a lista pronta do que fazer no painel.

3. **O dono troca tudo no painel, numa gravação só** (Settings → App-Level
   Environment Variables → Edit; alterar todas as linhas; Save). Uma gravação
   gera um deploy só. Gravar aos poucos gera um deploy por gravação, e alguns
   desses estados intermediários sobem (ver "Por que não dá para virar pela
   metade", abaixo).

4. **Conferir depois de salvar**, com o spec de antes como prova da troca dos
   segredos:

   ```bash
   .venv/bin/python scripts/golive_spec_delta.py --baseline ~/golive-spec-antes.yaml
   ```

   Sai `0` só quando nada obrigatório falta. Depois o release job roda
   `check --deploy`, que recusa chave de teste com `SHOPMAN_ENVIRONMENT=production`.
   O gate do "depois", com as sondas, é o mesmo avaliador:
   `make production-readiness target=1 context=shopman-do-app-admin baseline=~/golive-spec-antes.yaml`.

**Ensaio do Pix real** (D-031, Efí em sandbox no app vivo, antes do dia D):
`--etapa ensaio-pix` confere só o que o ensaio pede (Pix em `payment_efi`,
`EFI_SANDBOX=true`, sem o botão "Simular pagamento", ambiente ainda `staging`).

**Ensaio geral**: rodar o passo 2 contra o vivo e contra o spec que se pretende
colar (`--live-spec <arquivo>`), para ver a lista do dia D fechar sem mexer em nada.

## A tabela

Coluna "Dia D": **colar** = o dono cola o valor do painel do provedor (nunca
vai para o repositório); **apagar** = remover a linha (ausente vale o mesmo que
`false`).

### O que vira

| Chave | Hoje (10/10) | Dia D | Por quê | Como verificar | Como voltar |
|---|---|---|---|---|---|
| `SHOPMAN_ENVIRONMENT` | `staging` | `production` | É a pergunta "esta é a loja de verdade?" (`shopman/shop/environment.py`). Liga as travas de produção (E010, E012, E015, E022, E023) e fecha `seed --flush`, `qa_scenarios`, `setup_operators`, `import_backup --apply`. | script `[OK]`; release job verde (o `check --deploy` agora cobra produção) | `staging` |
| `SHOPMAN_PIX_ADAPTER` | `shopman.shop.adapters.payment_mock` | `shopman.shop.adapters.payment_efi` | Pix de verdade. Com Efí, o release roda `efi_webhook --soft` e recadastra o webhook na Efí de produção sozinho. | script; log do release com o webhook conferido; canário de um Pix | `shopman.shop.adapters.payment_mock` (exige `SHOPMAN_ENVIRONMENT=staging` e `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` juntos) |
| `EFI_SANDBOX` | `true` | `false` | Sem isto o Pix cobra no ambiente de homologação da Efí. E022 recusa `true` em produção; E026 recusa a omissão (tem de estar escrita). | script; tela de prontidão "Efí PIX: producao" | `true` |
| `EFI_CLIENT_ID` | segredo (homologação) | **colar** o de produção | A Efí tem credenciais separadas por ambiente. | script com `--baseline` (cifrado mudou); prontidão Efí verde | colar de novo o de homologação |
| `EFI_CLIENT_SECRET` | segredo (homologação) | **colar** o de produção | Idem. | idem | idem |
| `EFI_CERTIFICATE_PEM_BASE64` | segredo (homologação) | **colar** o certificado de produção (PEM em base64) | O certificado mTLS é por ambiente. E022 olha validade e formato. | idem; prontidão mostra "Certificado válido até …" | colar de novo o de homologação |
| `EFI_PIX_KEY` | segredo | não muda (conferir que é a chave Pix da conta) | Chave Pix da conta que recebe. | script `[OK]` (presente) | não muda |
| `EFI_WEBHOOK_TOKEN` | segredo (o do ensaio) | **colar** um token novo (aleatório, 32+ caracteres) | D22/D14: o token do ensaio atravessaria para produção se ninguém trocasse. O release recadastra a URL na Efí com o token novo. | script com `--baseline`; webhook do canário Pix chega (200, não 401) | colar o anterior (a Efí é recadastrada no próximo release) |
| `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS` | `true` | **apagar** | Permissão para simulador fora de DEBUG. Em produção, simulador é erro (E003). | script | `true` |
| `SHOPMAN_EXPOSE_MOCK_CAPTURE` | `true` | **apagar** | Botão "Simular pagamento" para o cliente. Em produção é captura sem dinheiro (E015). | script; tela de Pix sem o botão | `true` |
| `SHOPMAN_MOCK_PIX_AUTO_CONFIRM` | `false` | **apagar** (ou `false`) | Confirmação automática do Pix simulado. | script | não volta (já era `false`) |
| `SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS` | `8` | **apagar** (limpeza) | Só vale com o simulador. Sem efeito em produção; sai para o spec não mentir. | script `[LIMPEZA]` | `8` |
| `STRIPE_PUBLISHABLE_KEY` | `pk_test_…` (não secreta) | **colar** `pk_live_…` | Chave publicável do modo live. E022 recusa `pk_test_` em produção. | script (prefixo `pk_live_`) | colar a `pk_test_` |
| `STRIPE_SECRET_KEY` | segredo `sk_test_` | **colar** `sk_live_…` | Cobrança de verdade. E022 recusa `sk_test_` em produção. | script com `--baseline`; release verde; canário de um cartão | colar a `sk_test_` |
| `STRIPE_WEBHOOK_SECRET` | segredo do endpoint de teste | **colar** o `whsec_` do endpoint **live** | No modo live o Stripe exige criar o endpoint de novo: `https://api.boulangerie.com.br/api/webhooks/stripe/`, com os mesmos eventos do de teste. | script com `--baseline`; o canário de cartão confirma por webhook | colar o do endpoint de teste |
| `FOCUS_NFE_ENVIRONMENT` | ausente (o settings cai em `homologacao`) | `producao` | Nota com valor fiscal. E022 recusa homologação em produção; E026 recusa a omissão. A URL (`api.focusnfe.com.br`) sai daqui. | script; prontidão "Focus NFe: producao"; NFC-e do canário consultável na SEFAZ | `homologacao` |
| `FOCUS_NFE_TOKEN` | segredo (homologação) | **colar** o token de produção | A Focus tem um token por ambiente. | script com `--baseline`; NFC-e do canário autorizada | colar o de homologação |
| `SHOPMAN_ADMIN_REQUIRE_2FA` | ausente | `true` | Admin com segundo fator. **Pré-condição**: `check_admin_2fa_ready` verde no banco do app (todo staff ativo com autenticador e recuperação). Sem ela, tranca o staff fora. | script; login no Admin pede o código | apagar |
| `SHOPMAN_GO_LIVE` | ausente | `true` | Arma a política de migração da ADR-015 dentro do contêiner (a imagem não tem `.git`, então a tag `go-live-v1` não é legível lá). | script; log do release: `migration_safety` diz "política ADR-015: ARMADA" | apagar |
| `SHOPMAN_FISCAL_EMISSION_RESOLVER` | os quatro resolvers da casa (`on_request_or_tax_id`, `eletronic_payment`, `deferred_settlement`, `on_requested_receipt`) | os mesmos quatro **e** `shopman.shop.fiscal_resolvers.intermediated_sale` no fim (acrescentar, sem tirar nada) | A venda pelo iFood sem CPF tem de sair com NFC-e presencial (decisão de 24/09, ADR-035). O pagamento dela é `external`, e nenhum dos quatro o enxerga: sem o quinto, o iFood pago online sem CPF sai sem nota. Os outros quatro seguem (E013: a política de quando emitir é decisão fiscal). | script `[OK]` (o valor contém o resolver); o primeiro iFood sem CPF concluído gera a nota presencial | tirar o `,shopman.shop.fiscal_resolvers.intermediated_sale` do fim |

### O que já está no valor de produção e não pode sair dele

O script confere estas também, para que nenhuma mexida do dia D derrube uma
delas sem acusar. Todas estão `[OK]` em 10/10.

| Chave | Hoje e dia D | Por quê (trava) | Como voltar |
|---|---|---|---|
| `DJANGO_DEBUG` | `false` | DEBUG desliga quase todas as travas de deploy. | não muda |
| `DJANGO_SECURE_SSL_REDIRECT` | `true` | Contrato de produção (`scripts/check_production_contract.py`). | não muda |
| `SHOPMAN_CARD_ADAPTER` | `shopman.shop.adapters.payment_stripe` | E003/E009. | não muda |
| `SHOPMAN_LINK_ADAPTER` | ausente (cai no do cartão, Stripe) | O link do balcão usa o mesmo Checkout do cartão. | não muda |
| `SHOPMAN_FISCAL_ADAPTER` | `shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend` | Sem ele nenhuma nota sai. | não muda |
| `FOCUS_NFE_BASE_URL` | ausente | Se existir, vence o ambiente: apontada para homologação, a nota vai para lá mesmo com `producao`. | não muda |
| `SHOPMAN_STAGING_AUTOPILOT` | `false` | E012: em produção avançaria pedido de cliente sozinho. | não muda |
| `SHOPMAN_ENABLE_CONSOLE_NOTIFICATION_ADAPTER` | ausente | Notificação para o log, não para o cliente. | não muda |
| `SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM` | ausente | Contrato de produção. | não muda |
| `GOOGLE_MAPS_API_KEY` | ausente | E023: a chave única antiga não pode existir em produção. | não muda |
| `GOOGLE_MAPS_BROWSER_API_KEY` | segredo | E023: separada da de servidor. | não muda |
| `GOOGLE_MAPS_SERVER_API_KEY` | segredo | E023. | não muda |
| `DJANGO_SECRET_KEY` | segredo | E001. | não muda |
| `DJANGO_ALLOWED_HOSTS` | `api.` e `admin.` | E002 (sem `*`). | não muda |
| `CSRF_TRUSTED_ORIGINS` | os onze hosts `https://` | Contrato de produção. | não muda |
| `DATABASE_URL` | `${postgres.shopman-staging-pool.DATABASE_URL}` | B1 = 1: o mesmo banco. O nome `staging` do cluster é só nome. | não muda |
| `REDIS_URL` | `${cache.REDIS_URL}` | E006. | não muda |
| `SHOPMAN_OPERATOR_COOKIE_DOMAIN` | `.boulangerie.com.br` | E014. | não muda |
| `DOORMAN_ACCESS_LINK_API_KEY` | segredo | E008. | não muda |
| `COMTELE_API_KEY` | segredo | Entrega do código de login (E022, `otp_delivery`). | não muda |
| `COMTELE_ROUTE` | `17` | Idem. | não muda |
| `EMAIL_HOST` | `smtp.gmail.com` | Segunda via do código de login. | não muda |
| `SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY` | segredo, nos componentes `web-operator`, `web-storefront` e `release` | E025. | não muda |

## Por que não dá para virar pela metade

- **Com `SHOPMAN_ENVIRONMENT=production`**, o `check --deploy` do release
  recusa qualquer resto de ensaio: simulador sem permissão (E003), botão de
  simular (E015), Efí em sandbox, Stripe `sk_test_`/`pk_test_` e Focus em
  homologação (E022), `EFI_SANDBOX`/`FOCUS_NFE_ENVIRONMENT` não escritas
  (E026), Maps com chave única (E023). O deploy não fica `ACTIVE`
  e o app segue no deployment anterior.
- **O contrário também não sobe**: chaves live com `SHOPMAN_ENVIRONMENT=staging`
  (ou com qualquer porta de teste aberta) eram o lado que passava calado,
  dinheiro de verdade com o botão "Simular pagamento" na tela. O
  **SHOPMAN_E027** (`check_live_provider_without_test_doors`) roda em
  **qualquer** ambiente e reprova o deploy quando há dinheiro ou nota de
  verdade (Stripe `sk_live_`/`pk_live_`; `EFI_SANDBOX=false` com o Pix em
  `payment_efi`; Focus apontada para `api.focusnfe.com.br` com o emissor
  Focus ligado) **e** alguma porta de teste aberta: `DJANGO_DEBUG=true`,
  `SHOPMAN_ENVIRONMENT` diferente de `production`,
  `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS`, `SHOPMAN_EXPOSE_MOCK_CAPTURE`,
  `SHOPMAN_MOCK_PIX_AUTO_CONFIRM`, `SHOPMAN_STAGING_AUTOPILOT` ou algum pagamento em `payment_mock` (no spec ou
  no `Shop.integrations`). A dica lista cada porta aberta e o que fazer com
  ela. O alpha de hoje (tudo de teste) e o ensaio do Pix (`EFI_SANDBOX=true`)
  não têm nada live e passam. Este script continua sendo a primeira trava
  (sai `1` enquanto `SHOPMAN_ENVIRONMENT` não for `production`), e a gravação
  única do passo 3 continua sendo a regra: o E027 recusa o estado
  intermediário, não o evita.
- **Override por componente**: o script confere cada processo Django (os dois
  `web-*`, os três workers e o `release`) com o env do componente por cima do
  do app. Um worker com `SHOPMAN_ENVIRONMENT=staging` esquecido no próprio
  componente aparece como `[VIRAR] … | só em: <componente>`.

## O que não é chave do spec (e também trava)

São dados no banco, conferidos pelo `check --deploy` ou pela prontidão, e
entram pelo plano de dados do dia D, não pelo painel:

- `Shop.integrations` com override de Pix: se o Admin apontar o Pix para o
  simulador, o settings perde e o E022 acusa `SHOP_INTEGRATIONS_payment_pix_efi`;
- catálogo de qualidade (E016, E017, E018) e Configuração > Produção (E019);
- `Shop.document` (CNPJ): sem `FOCUS_NFE_CNPJ_EMITENTE` no spec, é dele que a
  Focus tira o emitente;
- NCM em todo produto vendável publicado (a prontidão da Focus conta os que faltam);
- inscrição do 2FA de todo staff ativo (`check_admin_2fa_ready`), antes de
  `SHOPMAN_ADMIN_REQUIRE_2FA=true`.

## Avisos que o release passa a mostrar, e são esperados

- **SHOPMAN_W019** (Web Push sem VAPID): o job `release` não recebe as chaves
  VAPID, e em produção o check avisa. Os `web-*` e o `directive-worker` têm as
  três. Não bloqueia.
- **SHOPMAN_W009** (sem `MANYCHAT_WEBHOOK_SECRET`): já aparece hoje; o
  webhook de assinantes do ManyChat fica fechado. Não depende do dia D.

## Depois da virada

- O `make deploy-spec-drift` passa a acusar as chaves trocadas contra o
  `.do/app.alpha-subdomains.yaml` (o versionado ainda diz `staging`, mock e
  `homologacao`). Alinhar o arquivo ao vivo num PR de seguimento, no mesmo dia,
  sem valores de segredo.
- `.do/app.subdomains.yaml` **não** entra na virada: é modelo para um app novo,
  e os bancos que ele anexa não existem (D-029).

## Como voltar tudo

- **Por chave**, no painel: a coluna "Como voltar" acima. Os segredos de teste
  estão nos painéis dos provedores (Stripe em modo teste, Efí homologação, Focus
  homologação).
- **Tudo de uma vez**: reaplicar o spec guardado no passo 1, que preserva os
  segredos de antes cifrados. É `apps update` de arquivo, então segue a D-009:
  conferir antes com
  `.venv/bin/python scripts/check_do_spec_drift.py --context shopman-do-app-admin --spec ~/golive-spec-antes.yaml`
  (a lista "sumiriam/nasceriam" tem de ser só o delta desta página), e é a
  palavra do dono.
- **Dado**: restaurar o ponto UTC anotado na abertura e reapontar o app
  ([go-live-cutover.md](go-live-cutover.md), rollback; [backup-e-restore.md](backup-e-restore.md)).
