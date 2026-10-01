# D14 — O token Efí do access log é de sandbox ou de produção?

- `verificado_em`: 2026-10-01T08:51Z
- `arvore`: `origin/main` = `beb9bf9737da0bc343cc64f86e423a7d26a81f17` (2026-10-01 07:46:39 +0000). Nada foi lido do checkout local (branch diferente).
- `objeto`: app DigitalOcean vivo `shopman-nelson` = `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f` (`doctl --context shopman-do-app-admin apps spec get 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`), deployment ativo `3f69fbbc-d817-403b-8b83-4c5bdb07fcea` (2026-10-01 08:13 UTC).
- `regra`: só FATO com caminho:linha ou comando+saída. Valores cifrados `EV[...]` NÃO foram decifrados e NÃO foram exibidos.

---

## Resposta direta ao dono

**(a) O token vazado é de sandbox/homologação.** Não porque o valor diga isso (ele é ilegível, `EV[...]`), mas porque **toda a instalação é de homologação** e o token só existe como valor *daqui*: `EFI_SANDBOX=true` no spec vivo, Pix no **simulador** (o adapter Efí nem está ligado) e a única vez que este ambiente falou com a Efí foi contra o host de sandbox `pix-h.api.efipay.com.br` — que chegou a recusar a autenticação com **403** em 22/09/2026. **Não existe deploy de produção**: a conta DO tem 3 apps (`shopman-nelson`, `nb-catalog-app`, `nb-site`) e nenhum é produção do Shopman.

**(b) Reutilização: SIM, por default.** Não há variável separada de produção — é **um** `EFI_WEBHOOK_TOKEN`, lido por **uma** chave de settings. O caminho do go-live é trocar `SHOPMAN_PIX_ADAPTER` para `payment_efi` e `EFI_SANDBOX=false` **no mesmo app**, então o mesmo valor atravessa para produção **a menos que alguém rotacione explicitamente**. O blueprint de produção (\`.do/app.subdomains.yaml\`) não declara nenhuma `EFI_*` — elas entram pelo painel, cifradas —, então não há nem um segundo valor preparado.

**(c) Dano hoje: zero observado, mas a porta continua aberta.** O Pix vivo é `payment_mock` (não passa dinheiro por gateway nenhum), não há cliente real, e a janela de log que li (780 linhas do service `web`) tem **0** ocorrências de `efi/pix` e **0** de `token=`. O que existe é a **capacidade**: quem tiver o token forja "Pix recebido", captura o intent no Payman e o pedido vai a `on_paid` — em staging isso é pedido marcado como pago sem dinheiro, alerta operacional para `ti@boulangerie.com.br` e sujeira de dado de teste.

**(d) Dano se o MESMO valor for para produção: dinheiro real.** Sem proxy mTLS na DO e com a allowlist de IP vazia, esse token é a **autenticação única** do endpoint de Pix. Quem lê o log forja um Pix pago para um `txid` conhecido (o próprio comprador conhece o seu) → captura + `on_paid` → mercadoria entregue, R$ 0 recebido, e **NFC-e real emitida** (o resolver vivo inclui `eletronic_payment`). Rotacionar antes de ligar a Efí de produção não é higiene: é a diferença entre um segredo queimado em log de staging e um segredo queimado no fluxo do dinheiro.

---

## 1. Toda variável Efí do spec VIVO

Comando: `doctl --context shopman-do-app-admin apps spec get 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f --format yaml | grep -n 'EFI_'` → 6 linhas.

| Variável (spec vivo) | scope | tipo | valor | papel |
|---|---|---|---|---|
| `EFI_SANDBOX` | RUN_TIME | GENERAL | `"true"` (**legível**) | escolhe o host da Efí; não é segredo |
| `EFI_CLIENT_ID` | RUN_TIME | SECRET | `EV[1:...]` cifrado | Basic auth do `/oauth/token` (cobrar) |
| `EFI_CLIENT_SECRET` | RUN_TIME | SECRET | `EV[1:...]` cifrado | idem |
| `EFI_PIX_KEY` | RUN_TIME | SECRET | `EV[1:...]` cifrado | chave Pix do recebedor |
| `EFI_WEBHOOK_TOKEN` | RUN_TIME | SECRET | `EV[1:...]` cifrado | **o `?token=` do webhook** |
| `EFI_CERTIFICATE_PEM_BASE64` | RUN_TIME | SECRET | `EV[1:...]` cifrado | mTLS cliente (`load_cert_chain`) |

[FATO] Todos os 5 segredos estão **cifrados** (`EV[...]`); o `doctl apps spec get` devolve o ciphertext, não o claro. Não decifrei e não exibi nenhum.

[FATO] **Ausentes** do spec vivo (grep `EFI_` retorna só as 6 acima): `EFI_WEBHOOK_IP_ALLOWLIST` e `EFI_MTLS_HEADER`. Consequência em `config/settings.py:1931` e `:1948`: allowlist vazia → `shopman/shop/webhooks/efi.py:261` devolve `True` sem filtrar nada; o header de mTLS nunca chega (DO App Platform serve direto). **O token é a autenticação única.**

[FATO] O que alimenta o webhook é exatamente um nome: `SHOPMAN_EFI_WEBHOOK["webhook_token"] = os.environ.get("EFI_WEBHOOK_TOKEN", "")` — `config/settings.py:1926`.

## 2. É sandbox ou produção? (não depende de ver valor)

- [FATO] Spec vivo: `EFI_SANDBOX` = `"true"`, `scope: RUN_TIME`, `type: GENERAL` — valor em claro, legível sem decifrar nada. Também `SHOPMAN_ENVIRONMENT=staging`.
- [FATO] Default no código: `config/settings.py:1910` → `os.environ.get("EFI_SANDBOX", "true")`. O default **também** é `true`.
- [FATO] **Valor efetivo = `true`** (env e default concordam). Efeito: `shopman/shop/adapters/payment_efi.py:55` → `return SANDBOX_URL if config.get("sandbox", True) else PRODUCTION_URL`, com `SANDBOX_URL = "https://pix-h.api.efipay.com.br"` (`:32`) e `PRODUCTION_URL = "https://pix.api.efipay.com.br"` (`:33`). **Toda** rota da Efí deste app (OAuth em `:126`, cobrança, cadastro de webhook) sai para o host de **homologação**.
- [FATO] Mais forte ainda: o Pix vivo nem usa a Efí. Spec vivo tem `SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_mock` e `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true`; o comentário no blueprint (`.do/app.alpha-subdomains.yaml:305-312`) registra que a troca para a Efí de testes subiu em 22/09/2026 e **a Efí recusou com 403 já no `release` (`efi_webhook`)**, voltando ao simulador. Por isso o job de release `python manage.py efi_webhook --soft` hoje **não faz nada**: `shopman/shop/management/commands/efi_webhook.py:101-103` sai com "Pix não usa a Efí neste deployment: nada a cadastrar".
- [INFERÊNCIA] Logo, as credenciais `EFI_CLIENT_ID/SECRET/CERTIFICATE` do spec são de **homologação** (o runbook manda pedir assim: `docs/runbooks/release-secrets-runbook.md:88-96`, "`EFI_CLIENT_ID=<homologacao client id>`" com `EFI_SANDBOX=true`). Não é FATO: o valor é ilegível e ninguém provou a origem no painel da Efí.
- [FATO] Não existe ambiente de produção do Shopman hoje: `doctl apps list` devolve só `shopman-nelson`, `nb-catalog-app` e `nb-site`. O blueprint de produção `.do/app.subdomains.yaml` é **template** (`name: shopman-headless`, domínios `STORE_DOMAIN` literais, `:1-25`) e não declara nenhuma variável `EFI_*`.

## 3. Qual token vai no `?token=` — e é o mesmo que cobra?

[FATO] É `EFI_WEBHOOK_TOKEN`, e é um segredo **separado** das credenciais de cobrança:

- `shopman/shop/webhooks/efi.py:332-334` — `token = request.META.get("HTTP_X_EFI_WEBHOOK_TOKEN", "")`; se vazio, `token = request.query_params.get("token", "")`.
- `shopman/shop/webhooks/efi.py:308` — esperado é `SHOPMAN_EFI_WEBHOOK["webhook_token"]`; comparado com `hmac.compare_digest` em `:340`.
- `shopman/shop/webhooks/efi.py:40` (contrato no topo do módulo) e `config/settings.py:1926` fecham o fio: header **ou** query, mesmo valor.
- Quem cobra usa **outro** caminho e **outros** segredos: `shopman/shop/adapters/payment_efi.py:120` monta `Basic base64(client_id:client_secret)` (`SHOPMAN_EFI["client_id"|"client_secret"]`, `config/settings.py:1911-1912`) contra `/oauth/token` (`:126`). **Nenhum caminho de código lê `EFI_WEBHOOK_TOKEN` para cobrar, nem `EFI_CLIENT_SECRET` para autenticar webhook.**

[FATO] O valor do `?token=` é **definido por nós**, não emitido pela Efí: o runbook diz `EFI_WEBHOOK_TOKEN=<shared secret definido para o webhook>` (`docs/runbooks/release-secrets-runbook.md:96`) e o comando o embute na URL registrada — `efi_webhook.py:48` `canonical_webhook_url(public_base, token)`; `docs/reference/commands.md:625`. **Consequência que responde a pergunta do dono:** esse segredo não tem "versão de sandbox" e "versão de produção" na Efí — ele é uma string nossa, e qual ambiente ele "vale" é decidido por **onde foi registrado** e por **onde continua configurado**.

## 4. Achado novo e urgente: a mitigação existe no repo e **não** está no spec vivo

- [FATO] `origin/main` `.do/app.alpha-subdomains.yaml:880`: `run_command: daphne -b 0.0.0.0 -p 8000 --access-log=/dev/null config.asgi:application` (com o comentário `:871-879` explicando que é vazamento de segredo, não economia de log). Introduzido em `15061ed3f1261776f110eaa6dbac5d766ad0da8b` (2026-09-05), "fix(deploy): o access log gravava o token do webhook…".
- [FATO] **Spec vivo não tem a flag:** `doctl ... apps spec get 40b86e35-… --format yaml | grep -c 'access-log'` → `0`; e o service `web` está em `run_command: daphne -b 0.0.0.0 -p 8000 config.asgi:application`.
- [FATO] Sem a flag, o pin instalado grava a query string: `daphne 4.2.3` (`pyproject.toml:38`, `daphne>=4.2,<5.0`) — `.venv/lib/python3.12/site-packages/daphne/cli.py:76-80` (verbosity `default=1`) e `:250-251` (`elif args.verbosity >= 1: access_log_stream = sys.stdout`); `daphne/http_protocol.py:276-285` loga `"path": uri` com o **request-target cru**, e `daphne/access.py:18-25` escreve `request="%(method)s %(path)s"`.
- [INFERÊNCIA] Ou seja: **hoje, cada chamada a `/api/webhooks/efi/pix/?token=<EFI_WEBHOOK_TOKEN>` ainda escreve o segredo em texto puro no log da plataforma.** O repositório corrigiu; o app vivo não recebeu a correção.
- [NÃO VERIFICADO] Se já houve chamada real com esse token: a janela de log que li (780 linhas, `doctl apps logs … web --type run`) tem `0` `efi/pix` e `0` `token=`. A janela é curta; e **deliberadamente não abri as linhas** para não reexpor o segredo. O `docs/reports/adversarial-audit-2026-09-01/01-security.md:38-52` (P0-1) chama o achado de "CONFIRMADO" pela cadeia de código, não por uma linha de log observada — e o `docs/runbooks/release-secrets-runbook.md:158-160` registra que em 19/08/2026 **não havia tráfego de webhook da Efí** no staging.

## 5. Caminho do dinheiro se o token for usado (para calibrar o dano)

- [FATO] `shopman/shop/webhooks/efi.py:210` chama `confirm_pix(txid, e2e_id, amount)` → `shopman/shop/services/pix_confirmation.py`, que localiza o intent, captura (`_capture_charge`) e despacha `dispatch(order, "on_paid")`. Não há ramo por ambiente ("dev and prod run the same transitions", `:11-16`).
- [FATO] O valor declarado no payload não é prova: a suficiência é o Payman (`pix_confirmation.py:230-245`). Isso reduz (não elimina) o dano de um payload forjado com valor errado — o atacante informa o valor certo do pedido dele.
- [FATO] Fiscal: spec vivo tem `SHOPMAN_FISCAL_ADAPTER=shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend` e o resolver inclui `eletronic_payment` (`shopman/shop/fiscal_resolvers.py:159-164`: emite quando há pagamento `pix`/`card`). Hoje isso cai em **homologação**, porque `FOCUS_NFE_ENVIRONMENT` não está no spec vivo e o default é `"homologacao"` (`config/settings.py:1801`). Em produção com o default trocado, o mesmo POST forjado vira nota fiscal real. [INFERÊNCIA no encadeamento emissão×pagamento forjado; FATO nas duas premissas de config.]

## 6. O que não consegui verificar

- [NÃO VERIFICADO] O valor claro de `EFI_WEBHOOK_TOKEN`, `EFI_CLIENT_ID`, `EFI_CLIENT_SECRET`, `EFI_PIX_KEY`, `EFI_CERTIFICATE_PEM_BASE64` — todos `EV[...]`. **Nada nesta resposta depende disso.**
- [NÃO VERIFICADO] Qual URL está cadastrada na Efí para a chave Pix, e com qual token (exigiria chamada externa com as credenciais — efeito externo, não autorizado; e o comando de release hoje nem executa, por causa do mock).
- [NÃO VERIFICADO] Se o valor que vazou é byte a byte o que está no spec hoje (não li o log).
- [NÃO VERIFICADO] Se o 403 de 22/09 foi autenticação ou escopo de webhook — o comentário do próprio spec diz "provavelmente na autenticação" (`.do/app.alpha-subdomains.yaml:308-312`).

## 7. Recomendações (ordem de custo)

1. **Devolver a flag ao spec vivo agora:** `--access-log=/dev/null` (ou `-v 0`) no service `web` — o repo já tem, o vivo não. Sem isso, rotacionar hoje só compra tempo até o próximo vazamento. **Ação de plataforma, minutos.**
2. **Rotacionar `EFI_WEBHOOK_TOKEN` como credencial vazada por desenho.** Rotacionar = recadastrar a URL na Efí (`docs/runbooks/release-secrets-runbook.md:203`); o job de release já faz isso sozinho quando o adapter efetivo é a Efí (`efi_webhook --soft`, spec vivo, job `release`).
3. **Tratar a rotação como item do checklist de corte do Pix**, não como consequência do vazamento: é o único ponto em que "sandbox" e "produção" deixam de ser coisas separadas.
4. Antes de haver tráfego real, decidir sobre mTLS (proxy na frente) ou allowlist de IP — hoje a allowlist nasce vazia de propósito e o mTLS é advisory, então o token continua sendo a única porta.
