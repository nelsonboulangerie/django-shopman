# Conferir o spec antes de `doctl apps update`

> **Regra curta:** rode `make deploy-spec-drift` **antes** de qualquer
> `doctl apps update --spec`. Se a saída listar alguma chave em **SUMIRIAM**,
> não rode o update — traga a chave para o arquivo primeiro.

## A armadilha

`doctl apps update --spec` **não faz merge**. O spec que você manda *passa a
ser* o spec. Chave que existe só no painel e não no arquivo é apagada: sem
confirmação, sem aviso, sem uma linha no log. O deploy sobe verde.

Medido em **05/09/2026**: `.do/app.alpha-subdomains.yaml` tinha **73 envs** e o
app vivo tinha **95**. As 22 de diferença estavam configuradas só no painel, e
incluíam:

- **todo o e-mail** — `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_HOST_USER`,
  `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`.
  Sem elas o `EMAIL_BACKEND` cai no default `console` do `settings.py`: o
  Django "envia" imprimindo no stdout e devolvendo sucesso. **Nada falha e
  ninguém recebe nada.**
- **a emissão fiscal inteira** — `SHOPMAN_FISCAL_ADAPTER`, `FOCUS_NFE_TOKEN`.
- **o NF-e de Compras com o certificado e-CNPJ** —
  `PURCHASE_NFE_CERTIFICATE_PFX_BASE64` e sua senha. O certificado A1 é o
  arquivo que você não tem outra cópia à mão. ⚠️ Vence em **10/09/2026**.

Este PR fechou o buraco: as chaves entraram nos dois specs. Mas a armadilha
volta a armar sozinha toda vez que alguém acrescentar uma env pelo painel — que
é a coisa mais natural do mundo a se fazer às pressas.

## Como conferir

```bash
make deploy-spec-drift                                # alpha (default)
make deploy-spec-drift spec=.do/app.subdomains.yaml   # produção
```

O script (`scripts/check_do_spec_drift.py`) é **somente leitura**: chama
`doctl apps spec get`, compara com o arquivo versionado e imprime três coisas:

- **⛔ SUMIRIAM** — existem no vivo e não no arquivo. Estas apagam. É a lista
  que importa.
- **➕ nasceriam** — existem no arquivo e não no vivo. Normalmente é o que você
  quer (foi o caso do `SENTRY_DSN` e do `FOCUS_NFE_ENVIRONMENT`).
- **⚠️ divergem** — existem dos dois lados com valor/escopo/tipo diferente.

Sem `doctl` autenticado, dá para conferir com o spec já baixado:

```bash
doctl apps spec get <app-id> > /tmp/vivo.yaml
.venv/bin/python scripts/check_do_spec_drift.py --live-spec /tmp/vivo.yaml
```

> **Valor de segredo nunca é comparado nem impresso.** No spec do vivo ele vem
> cifrado (`EV[1:...]`) e no versionado não existe por política — comparar
> daria "divergente" sempre, e imprimir seria vazar.

## Como trazer uma chave do painel para o arquivo

**Segredo** — declare a chave, **sem `value`**. É o contrato do App Platform
para "o valor cifrado que já está lá permanece":

```yaml
- key: EMAIL_HOST_PASSWORD
  scope: RUN_TIME
  type: SECRET
```

⛔ **Nunca** cole o valor real, nem o `EV[1:...]` cifrado. O cifrado é
específico do app e não serve de backup — e commitá-lo é vazamento com passos
extras.

**Não-segredo** — copie chave, `scope`, `type` e `value` exatamente como o
`spec get` devolveu.

## Divergências conhecidas hoje (05/09/2026)

O drift do alpha está **limpo na lista que apaga** — nenhuma chave SUMIRIA. Mas
há **13 divergências de valor** em que o arquivo está atrás do vivo. Um
`apps update` hoje não apagaria nada, mas **reverteria** estas:

| Chave | Vivo | Versionado | Efeito de reverter |
|---|---|---|---|
| `SHOPMAN_CARD_ADAPTER` | `payment_stripe` | `payment_mock` | ⛔ cartão volta para o mock |
| `SHOPMAN_CONCIERGE_ENABLED` | `true` | `false` | concierge do WhatsApp desliga |
| `CONCIERGE_ALLOWED_SUBSCRIBERS` | 4 assinantes | vazio | piloto fechado vira aberto |
| `SHOPMAN_FISCAL_EMISSION_RESOLVER` | 3 resolvers | 2 | perde `deferred_settlement` |
| `MANYCHAT_WHATSAPP_ID_FIELD_ID` | `8932087` | vazio | ManyChat perde o campo de ID |
| `IFOOD_MERCHANT_ID` | UUID | `2512433` | iFood aponta para merchant errado |
| `AUTH_DEFAULT_DOMAIN`, `SHOPMAN_DOMAIN`, `CSRF_TRUSTED_ORIGINS`, `SHOPMAN_STOREFRONT_BASE_URL`, `SHOPMAN_PREPROD_URL`, `WHATSAPP_STOREFRONT_URL` | `menu.` | `alpha.` | o domínio **mudou** de `alpha.` para `menu.` em 01/09 e o arquivo não acompanhou |
| `SHOPMAN_STAGING_AUTOPILOT` | `false` | `true` | autopilot religa |

**Estas não foram alteradas neste PR de propósito** — são decisões de
configuração do dono (especialmente o concierge, que está desligado por env
esperando a palavra dele), não dívida técnica a ser resolvida por um agente.
Alinhar o arquivo com o vivo é um PR próprio, e a linha do domínio
`alpha.` → `menu.` provavelmente puxa junto uma revisão de
[`reference_o_corte_de_dominio_menu_e_alpha`].

## Por que isto não é gate de CI

Exige credencial da DigitalOcean, que a CI não tem — e não deve ter. É
conferência **de mão**, e o lugar dela é o minuto antes do `apps update`, não
o PR.
