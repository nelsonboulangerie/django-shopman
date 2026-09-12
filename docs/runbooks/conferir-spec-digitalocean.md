# Conferir o spec antes de `doctl apps update`

> # ⛔ NUNCA rode `doctl apps update --spec` sem passar o drift-check antes.
>
> `make deploy-spec-drift` tem que sair **[OK]**. Se a saída listar qualquer
> coisa em **SUMIRIAM**, não rode o update: traga a coisa para o arquivo
> primeiro. Isto vale para env, **domínio** e **regra de ingress** — as três
> somem do mesmo jeito.

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
`doctl apps spec get`, compara com o arquivo versionado e imprime quatro coisas:

- **⛔ SUMIRIAM** — existem no vivo e não no arquivo. Estas apagam. É a lista
  que importa.
- **➕ nasceriam** — existem no arquivo e não no vivo.
- **⚠️ divergem** — existem dos dois lados com valor/escopo/tipo diferente.
- **✅ esperado** — diferença **declarada** no próprio script, com a razão
  junto. Não conta como drift. Ver a seção de diferenças legítimas abaixo.

Ele compara **env de app, env de serviço, domínios e regras de ingress**. As
duas últimas entraram em 08/09/2026, depois que o arquivo versionado passou uma
semana dizendo "OK" enquanto trazia `alpha.nelsonboulangerie.com.br` — domínio
morto desde o corte de 01/09 — como PRIMARY, e deixava `backup.boulangerie.com.br`
de fora. Um update teria ressuscitado o morto e apagado o vivo.

Ingress é comparado como **conjunto**, não como lista ordenada: o painel
acrescenta regra no fim e o arquivo agrupa por leitura. O que importa é quem
serve cada host, e se existe a regra catch-all.

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

## Estado hoje (08/09/2026): drift do alpha **limpo**

`make deploy-spec-drift` sai `[OK]`. As 13 divergências de valor medidas em
05/09 foram alinhadas — **todas na direção arquivo ← vivo**, porque em todas
elas o vivo é a configuração que o dono escolheu e o arquivo é que estava
velho. Um `apps update` hoje não reverte nada.

| Chave | Vivo (= agora no arquivo) | Estava no arquivo | Por que o vivo é o certo |
|---|---|---|---|
| `SHOPMAN_CARD_ADAPTER` | `payment_stripe` | `payment_mock` | o cartão está no Stripe (chave de teste); o arquivo devolveria a simulação |
| `SHOPMAN_CONCIERGE_ENABLED` | `true` | `false` | o dono abriu o piloto fechado do concierge |
| `CONCIERGE_ALLOWED_SUBSCRIBERS` | coorte explícita | vazio | no contrato v3, vazio fecha a connection; nunca significa acesso irrestrito |
| `SHOPMAN_FISCAL_EMISSION_RESOLVER` | 4 resolvers | 2 | o arquivo perdia `deferred_settlement` e `on_requested_receipt` — sem o segundo, pedir a nota impressa ou por e-mail não emitia nada |
| `MANYCHAT_WHATSAPP_ID_FIELD_ID` | `8932087` | vazio | sem o id o ManyChat não acha o campo |
| `IFOOD_MERCHANT_ID` | `f36a17d0-…` | `2512433` | o merchant do iFood é UUID; `2512433` é o número de loja do painel |
| `AUTH_DEFAULT_DOMAIN`, `SHOPMAN_DOMAIN`, `CSRF_TRUSTED_ORIGINS`, `SHOPMAN_STOREFRONT_BASE_URL`, `SHOPMAN_PREPROD_URL`, `WHATSAPP_STOREFRONT_URL` | `menu.` | `alpha.` | o corte de 01/09 matou `alpha.`; ver [[reference_o_corte_de_dominio_menu_e_alpha]] |
| `SHOPMAN_STAGING_AUTOPILOT` | `false` | `true` | o `menu.` recebe pedido de gente de verdade; o autopilot avançaria por baixo do operador |

Junto vieram duas coisas que o drift-check **não olhava** e ninguém tinha
medido: o arquivo trazia `alpha.nelsonboulangerie.com.br` como domínio PRIMARY
e não trazia `backup.boulangerie.com.br`, que estava no ar servindo o atalho do
cofre. Corrigidos, e agora o script compara domínio e ingress.

### O snapshot envelhece em minutos — e envelheceu no meio deste trabalho

O `SHOPMAN_FISCAL_EMISSION_RESOLVER` foi medido duas vezes com poucas horas de
diferença e deu valores diferentes: na primeira leitura faltava
`on_requested_receipt` (a nota pedida no comprovante não emitia), e na segunda
ele já estava lá, acrescentado pelo painel. O arquivo ficou com o valor da
**segunda** leitura.

A lição operacional é a de sempre, e ela vale mais que o caso: **`spec get`
imediatamente antes do update, nunca um arquivo salvo antes de outra
operação.** Se você mediu, foi almoçar e voltou, meça de novo.

## Diferenças legítimas — não são drift

Estas existem de propósito e estão **declaradas** em
`EXPECTED_ONLY_VERSIONED`, no `scripts/check_do_spec_drift.py`, para que o
relatório feche limpo. Um relatório que nunca fecha deixa de ser lido, e a
próxima divergência de verdade chega no meio de um ruído que todo mundo já
aprendeu a ignorar.

| Chave | Situação | Por quê |
|---|---|---|
| `FOCUS_NFE_ENVIRONMENT` | no arquivo (`homologacao`), ausente no vivo | o default do `settings.py` é o mesmo `homologacao`, então aplicar não muda comportamento. O dono decidiu **manter em homologação** por ora — a chave fica declarada para que a virada seja uma edição visível, não um efeito colateral. Ver [`ativar-focus-nfe.md`](ativar-focus-nfe.md) |
| `SENTRY_DSN` | no arquivo (`SECRET` sem valor), ausente no vivo | opt-in: sem DSN o `settings.py` não inicializa o Sentry. Ver [`ativar-sentry.md`](ativar-sentry.md) |

Ao acrescentar uma diferença legítima nova, **declare no script com a razão** —
não a tolere em silêncio. E lembre que a allowlist só vale para o lado
"nasceriam": na direção que apaga não há allowlist nenhuma.

## O template de produção (`.do/app.subdomains.yaml`)

Não existe app de produção na DigitalOcean, então **não há drift a medir** ali:
o arquivo é blueprint, com `STORE_DOMAIN` no lugar do domínio real, e
`make deploy-spec-drift spec=.do/app.subdomains.yaml` não tem app vivo contra o
que comparar.

O que se confere nele é outra coisa — se ele descreve menos do que a casa já
tem. Corrigido em 08/09: dois valores do **alpha** tinham entrado por cópia
(`SHOPMAN_BACKUP_SHEET_HOST=backup.boulangerie.com.br` e
`SHOPMAN_PRODUCT_IMAGE_BASE` apontando para o `menu.`), e o atalho do cofre não
tinha domínio nem rota apesar de a env estar declarada.

Duas diferenças em relação ao alpha **ficam de pé de propósito**:

- **`SHOPMAN_CARD_ADAPTER` continua `payment_mock`** no template. É o
  comportamento documentado ali (blueprint de verificação), e o deploy-check
  `SHOPMAN_E003` barra adapter mock em produção — trocar por Stripe sem as
  credenciais reais só trocaria um erro claro por um obscuro.
- **`CSRF_TRUSTED_ORIGINS` lista só `api.` e `admin.`**, enquanto o alpha lista
  os onze hosts. O template tem a razão escrita ao lado: o BFF mascara
  `origin=api.` para loja e apps de operador, e o admin é acessado direto.
  Copiar a lista do alpha para cá seria copiar configuração de ambiente sem
  prova de que ela é necessária.

Estas duas ficam registradas aqui para não virarem "achado" na próxima
conferência.

## Por que a comparação com o vivo não é gate de CI

Exige credencial da DigitalOcean, que a CI não tem — e não deve ter. É
conferência **de mão**, e o lugar dela é o minuto antes do `apps update`, não
o PR.

O que **é** gate de CI é a metade que não precisa saber o que está no ar:
`shopman/shop/tests/test_do_spec_hosts.py` recusa um spec que reintroduza
`alpha.`/`staging.`, que declare domínio sem rota, ou que nomeie o host do
cofre sem o domínio correspondente — e
`shopman/shop/tests/test_do_spec_drift_check.py` prova que o próprio
drift-check enxerga domínio e ingress, e que a allowlist de diferença esperada
nunca cobre a direção que apaga.
