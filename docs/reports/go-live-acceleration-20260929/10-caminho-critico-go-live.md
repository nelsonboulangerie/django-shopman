# 10 — Caminho crítico de go-live: o que falta, o que trava e o que pode ser cortado

> **Objetivo do dono:** "Entrar em GO-live com as principais funcionalidades no menor tempo possível."
>
> **Árvore lida:** `.dsh-worktrees/go-live-acceleration` (leitura estática; nada foi editado além deste arquivo).
> HEAD local = `f0ffd02fd` (2026-09-29T15:36Z). `origin/main` **já está em `ccf68564c`** (2026-09-29T16:12Z), 14 commits à frente — **a premissa "origin/main = f0ffd02fd" está desatualizada** (ver Achado 1).
>
> **Legenda:** [FATO] verificado no código/comando · [INFERÊNCIA] dedução · [NÃO VERIFICADO] não consegui confirmar.

---

## 1. Resumo executivo

1. **O software está pronto. O ambiente não.** O código tem 9 superfícies Nuxt, ~270 migrations, 25 deploy-checks (`SHOPMAN_E001`–`E025`) e CI de 7 gates verdes. O ambiente vivo (`shopman-nelson`) roda `SHOPMAN_ENVIRONMENT=staging`, **Pix em `payment_mock`**, Efí em sandbox, NFC-e em homologação e **botão "Simular pagamento" exposto ao público** ([FATO] `.do/app.alpha-subdomains.yaml:313-328`, R8 `:52-53`).
2. **A decisão canônica é NO-GO por gate humano, não por bug.** R8 pré-flight: 38 linhas auditadas = **13 GO / 7 NO-GO / 18 UNKNOWN**; estado final `NO-GO — BLOCKED HUMAN GATE` (`docs/reports/2026-09-29-r8-cutover-preflight.md:9,102`).
3. **A matriz canônica está congelada numa baseline 70 commits atrás** e o próprio gate `make canonical-docs` **não detecta isso** (ele não valida o SHA de `baseline_git` nem a contagem de migrations — `scripts/check_canonical_docs.py:188-226`; passa verde, verificado por execução).
4. **Existem dois registros de verdade em paralelo** — a matriz de prontidão e o *activation ledger* — e o próprio ledger proíbe isso ("Nao mantenha outro ledger em paralelo"). O ledger já está em `origin/main` (PR #1259), mas **nenhum dos 7 documentos do programa R0–R8 aponta para ele**.
5. **O caminho crítico real não é código: é credencial + prova externa + assinatura humana.** A menor cadeia tem 6 elos, dos quais **4 dependem de ação do Pablo/plataforma** (credenciais live, restore ensaiado, 2FA, GO assinado) e 2 são engenharia de horas, já com código no `main`.
6. **O maior risco da janela não é pagamento — é Marketing.** O vivo tem `SHOPMAN_MARKETING_WHATSAPP_MODE=open` e `SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED=true` preservados no spec ([FATO] commit `9d57ae346`, `.do/app.alpha-subdomains.yaml:481-489`; R8 `:70-73`). Um clique errado na janela manda WhatsApp real para cliente real. **Recomendação nº 1: cortar Marketing da janela.**
7. **O escopo v1 declarado é amplo (11 frentes) e auto-bloqueante**: `PRODUCT-V1-SCOPE-BACKLOG.md:77` diz que o go-live "só dispara com **todas** as entregues". Isso precisa ser re-cortado — a proposta está na seção 5.2.
8. **Duas "principais funcionalidades" não têm caminho curto e devem sair do v1:** iFood (homologação oficial **nunca iniciada** — `IFOOD-COMPLIANCE-2026-09-13.md:5`) e Machine courier (adapter real, **zero credencial em qualquer spec**).
9. **A boa notícia fiscal:** NF-e de entrada **já está em produção** (`PURCHASE_NFE_ENVIRONMENT=producao`), o certificado A1 foi renovado e o adapter NFC-e Focus NFe está construído. O gate fiscal do dia 1 é **1 linha de env + validação do contador**, não um projeto.
10. **Corte de esforço estimado** [INFERÊNCIA]: das 11 frentes do v1, **6 podem sair** da janela sem quebrar venda presencial, retirada ou entrega própria — e uma delas (Media persistente) tem raio de impacto de **exatamente 1 campo** (`Shop.logo`).

---

## 2. Achados

### Achado 1 — `origin/main` andou 14 commits além do SHA da tarefa, e o ledger já foi mergeado [FATO]

```
$ git rev-parse HEAD origin/main
f0ffd02fde765493d734bae93a72bb361ed28fcf      # HEAD local (branch dsh/go-live-acceleration-20260929)
ccf68564cabea19fdbe288185af448e100408992      # origin/main
$ git log -1 --format='%H %ad %s' --date=iso origin/main
ccf68564c... 2026-09-29 16:12:02 +0000 Merge pull request #1259 from nelsonboulangerie/codex/go-live-activation-ledger-20260929
$ git rev-list --count f0ffd02fd..origin/main
14
```

O delta é pequeno e **não muda a análise**: POS Encomendas UX (#1263), remarcar encomenda (#1262) e o ledger (#1259). Veio `shopman/shop/services/reschedule.py`, `shopman/shop/services/stock.py`, `surfaces/pos-nuxt/*`.

**Impacto:** qualquer auditoria que leia só o HEAD local está medindo 14 commits atrás; o *activation ledger* — que a tarefa pediu para procurar "em commits recentes" — **já é `main`**. **Confiança: alta.**

### Achado 2 — A matriz canônica de prontidão está stale e o gate não protege [FATO]

- `docs/plans/GO-LIVE-READINESS-PLAN.md:9` — `baseline_git: ab148fbd85d50865bf107e95298b712decd9d7f4`. `origin/main` hoje é `ccf68564c`: **70 commits** entre a baseline da matriz e o `f0ffd02fd`, mais 14 até `ccf68564c`.
- `docs/status.md:9` — mesma baseline `ab148fbd`; `:58` declara **268 arquivos de migration**. Medido agora: **[FATO]** `find shopman packages -path "*/migrations/*.py" ! -name "__init__.py" | wc -l` → **270** (shop 101, backstage 81, storefront 11 + outros).
- O gate roda e passa: **[FATO]** `python scripts/check_canonical_docs.py` → `canonical docs: OK` (exit 0). Ele valida *estrutura* (6 colunas, estados permitidos, owner/next-event obrigatórios em linha aberta — `scripts/check_canonical_docs.py:188-226`), **não** valida o SHA nem a contagem.

**Impacto:** a "única fonte operacional de prontidão" pode envelhecer em silêncio, e envelheceu. Todo mundo que ler a matriz hoje lê um estado de 70 commits atrás. **Confiança: alta.**

### Achado 3 — O vivo é staging com affordances de teste expostas ao público [FATO]

Do spec do app vivo (`.do/app.alpha-subdomains.yaml`, que o próprio ledger identifica como o ambiente `shopman-nelson`), e do R8 pré-flight:

| Chave | Valor | path:line |
|---|---|---|
| `SHOPMAN_ENVIRONMENT` | `staging` | `.do/app.alpha-subdomains.yaml:359-362` |
| `SHOPMAN_PIX_ADAPTER` | `shopman.shop.adapters.payment_mock` | `:313-316` |
| `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS` | `true` | `:321-324` |
| **`SHOPMAN_EXPOSE_MOCK_CAPTURE`** | **`true`** | `:325-328` |
| `SHOPMAN_CARD_ADAPTER` | `payment_stripe` (chave de teste) | `:317-320` |
| `EFI_SANDBOX` | `true` | `:337-340` |
| `FOCUS_NFE_ENVIRONMENT` | `homologacao` | `:755-761` |
| `SHOPMAN_MOCK_PIX_AUTO_CONFIRM` | `false` | `:329-332` |
| `SHOPMAN_STAGING_AUTOPILOT` | `false` | `:544-549` |

`SHOPMAN_EXPOSE_MOCK_CAPTURE=true` não é "mock interno": é **botão de quitar o próprio pedido sem pagar**, na loja pública (endpoint em `shopman/storefront/api/urls.py:182`, gate em `shopman/shop/services/payment.py:1891-1931`, UI em `surfaces/storefront-nuxt/app/components/PaymentBlock.vue:116-132`). O R8 mediu isso no vivo (`:52`: "captura mock exposta").

**Impacto:** enquanto durar, qualquer visitante fecha pedido sem dinheiro. Inaceitável no dia do corte, tolerável só no pré-live. **Confiança: alta.**

### Achado 4 — Marketing está armado no vivo: WhatsApp `open` com delivery ligado [FATO]

O commit `9d57ae346` ("preserve live envs") declarou no blueprint as chaves que existiam **somente no vivo**. Entre elas:

```yaml
# .do/app.alpha-subdomains.yaml (adicionado por 9d57ae346)
- key: SHOPMAN_MARKETING_WHATSAPP_MODE
  value: open
- key: SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED
  value: 'true'
```

E o R8 (`:70-73`): "consumers de Marketing e flags de publicação/delivery estão habilitados no vivo, WhatsApp está em modo `open` e o canário de publicação está desligado".

**Impacto:** é o maior raio de dano da janela. Vender errado = 1 pedido; **enviar errado = centenas de mensagens irreversíveis**. Marketing deve sair do escopo da janela (seção 5.2, corte C1). **Confiança: alta.**

### Achado 5 — `DOORMAN_MESSAGE_SENDER_CLASS=LogSender` no vivo: perigoso, mas **hoje inerte** [FATO]

O spec declara `DOORMAN_MESSAGE_SENDER_CLASS = shopman.doorman.senders.LogSender` (`.do/app.alpha-subdomains.yaml:387-390`). **Não é o caminho de entrega atual**, e isto importa para não produzir um falso bloqueador:

- `packages/doorman/shopman/doorman/adapter.py:174-178` — a cadeia vence; `MESSAGE_SENDER_CLASS` só é usado **se a cadeia estiver vazia**.
- `config/settings.py:1013-1016` — `DELIVERY_CHAIN` default fora de DEBUG = `sms,email`; `SHOPMAN_OTP_DELIVERY_CHAIN` **não está declarada** em nenhum spec.
- `config/settings.py:995-999` — `DELIVERY_SENDERS["sms"] = shopman.shop.adapters.otp_sms_comtele.ComteleSMSSender` (adapter real do fornecedor brasileiro).
- `packages/doorman/shopman/doorman/apps.py:26-54` — a trava de boot só dispara **quando a cadeia está vazia**; e o comentário registra textualmente que "é justamente ele [LogSender] que os dois specs da DO declaravam" e que bastava alguém esvaziar a cadeia para o código de login vazar no log.

**Impacto:** o login por telefone **não está quebrado**; está **não provado**. O bloqueador é a ausência de um SMS real recebido (seção 4), não o LogSender. Mas o LogSender é uma armadilha de uma env: se alguém esvaziar a cadeia durante um incidente com a Comtele, o boot recusa (trava correta). **Confiança: alta.**

### Achado 6 — Os defaults perigosos de dinheiro e fiscal continuam abertos no código [FATO]

| Default | Onde | Consequência |
|---|---|---|
| `EFI_SANDBOX` nasce `true` | `config/settings.py:1904` | Esquecer a env no corte: **todo Pix cobra num gateway que não recebe dinheiro** |
| `FOCUS_NFE_ENVIRONMENT` nasce `homologacao` | `config/settings.py:1795` | Nota emitida **não existe no SEFAZ** — venda ao balcão com documento inválido |

Ambos estão catalogados como **Tier 1 abertos** em `docs/plans/fallbacks-perigosos-go-live.md:30-72`, com a tabela-resumo em `:377-378` ("Trava em runtime: **nenhuma**"). O item 1 do doc cita `config/settings.py:1142` e `:1072` — **os números de linha envelheceram**; hoje são `:1904` e `:1795`.

O perfil de produção do gate (`scripts/check_release_readiness.py:377-418`) verifica explicitamente `DEBUG`, `SHOPMAN_ENVIRONMENT`, `ALLOW_MOCK_PAYMENT_ADAPTERS`, `EXPOSE_MOCK_CAPTURE`, `MOCK_PIX_AUTO_CONFIRM`, `EXPOSE_DEBUG_OTP`, `STAGING_AUTOPILOT` e adapters mock — **não verifica `EFI_SANDBOX` nem `FOCUS_NFE_ENVIRONMENT`**.

**Impacto:** são exatamente os dois "esquecimentos de 1 linha" que custam dinheiro e validade fiscal, e o gate de produção atual não os pega. **Confiança: alta.**

### Achado 7 — O `production-readiness --read-only` **já existe** no HEAD (o R8 está desatualizado neste ponto) [FATO]

O R8 (`:91-98`) diz: "O comando não possui `--read-only`… por isso o comando não foi executado contra o ambiente vivo". Isto **mudou**:

- Commit `145ff129c` "feat(readiness): modo --read-only com zero escrita garantida por mecanismo", 2026-09-29T11:38Z, **ancestral de HEAD** (verificado com `git merge-base --is-ancestor`).
- `Makefile:484` → passa `--read-only` ao script quando `read_only=1`.
- Implementação mecânica: `scripts/check_release_readiness.py:170-215` (`ReadOnlyViolation` via `execute_wrapper`), `:220-249` (`SET TRANSACTION READ ONLY`), `:817` (smoke que grava vira `SKIP`).
- O WP de cutover já documenta o alvo: `make production-readiness read_only=1` (`docs/plans/WP-COMMERCIAL-GO-LIVE-CUTOVER-2026-09-28.md:129`).

**Impacto:** um dos 5 "gates humanos mínimos" do R8 (item 4, `:114`) **já está entregue em código**. Basta rodá-lo contra o alvo. **Confiança: alta.**

### Achado 8 — O release job vivo já roda `migration_safety` (outro NO-GO do R8 fechado) [FATO]

R8 `:48`/`:82` reprovavam o release job por não rodar `migration_safety`. O relatório `docs/reports/2026-09-29-live-otp-spec-reconciliation.md:16-22` registra que o job passou a executá-lo, com evidência `migration-safety: clear`. E os dois specs versionados o contêm: `.do/app.subdomains.yaml:1245` e `.do/app.alpha-subdomains.yaml:1245-1247`.

**Impacto:** dos 7 `NO-GO` do R8, **2 estão fechados** no `main` (este e o read-only). **Confiança: alta.**

### Achado 9 — A matriz de credenciais está inteira em `DESCONHECIDO` a partir da coluna 3 [FATO]

`docs/plans/GO-LIVE-CREDENTIALS-MATRIX.md:33-45`: 11 integrações. `Código` = VERIFICADO em todas; `Declarada no spec` = VERIFICADO em 10 de 11 (Machine = PENDENTE); **`Adapter no ambiente`, `Boot gate comercial`, `Sandbox/homologação` e `Produção` = `DESCONHECIDO` em praticamente todas as células**. As três únicas linhas com `Escopo v1` declarado (Django/domínio, PostgreSQL/Redis, Observabilidade) estão **BLOQUEADO**.

O doc proíbe o atalho: "É proibido colapsar essas etapas em 'configurado'" (`:25`).

**Impacto:** nenhuma integração passou do estado 2 de 5. Não é que estejam quebradas; é que **ninguém provou**. **Confiança: alta.**

### Achado 10 — O spec de produção do repositório não declara nenhuma credencial de pagamento nem de mensageria [FATO]

`grep -E "STRIPE_|EFI_|MANYCHAT_|COMTELE_|META_|IFOOD_" .do/app.subdomains.yaml` devolve apenas: `STRIPE_CAPTURE_METHOD` (`:352`), comentário sobre o token da Efí na query (`:620`) e um comentário sobre `IFOOD_CLIENT_ID/SECRET` (`:997`). **Nada mais.** O spec `shopman-headless` declara só: VAPID, MaxMind, AI_ASSIST, CONCIERGE, SENTRY_DSN, EMAIL_HOST_PASSWORD, FOCUS_NFE_TOKEN, PURCHASE_NFE_*, GOOGLE_MAPS_*.

Além disso, o próprio spec de produção ainda traz **Pix E cartão apontando para `payment_mock`** (`.do/app.subdomains.yaml:324-331`) e `FOCUS_NFE_ENVIRONMENT: homologacao` (`:555-558`), com o comentário de bloqueio explícito em `:541-554`.

**Impacto:** o blueprint de produção **não sobe como está** — e isso é intencional (o `SHOPMAN_E003` barra de propósito, comentário em `:332-334`). Mas significa que "ir para produção" inclui **compor o spec a partir do vivo**, nunca aplicar o arquivo (R8 `:112-113`, `go-live-cutover.md:35-37`). **Confiança: alta.**

### Achado 11 — Backup é VERIFICADO; o **ensaio de restore** nunca aconteceu [FATO]

`docs/reports/2026-09-29-backup-pitr-verification.md:13-24`: PostgreSQL 16 online, **8 backups diários consecutivos**, último em `2026-09-29T00:13:26Z`, ~0,247 GB, retenção/PITR de 7 dias — tudo **VERIFICADO**. Mas `:19`: "**Ensaio recente de restore isolado — NÃO VERIFICÁVEL / NO-GO**". A matriz repete: `GO-LIVE-READINESS-PLAN.md:53` (backup VERIFICADO) × `:54` (ensaio BLOQUEADO).

**Impacto:** é o **risco mais caro e mais barato de fechar ao mesmo tempo**. Enquanto não houver restore ensaiado, um incidente no corte não tem plano B medido. Custa um fork temporário com autorização explícita de custo. **Confiança: alta.**

### Achado 12 — iFood e Machine não têm caminho curto [FATO]

- **iFood**: `docs/reports/IFOOD-COMPLIANCE-2026-09-13.md:5` — "**Nenhuma tentativa oficial foi iniciada.**" O plano é explícito: "o iFood **certifica** a integração… **Sem homologação aprovada, não roda em prod**" (`docs/plans/IFOOD-DIRECT-INTEGRATION-PLAN.md:21-22`). O código (poll, webhook, catálogo) está construído e o worker `ifood-poll-worker` existe no spec (`.do/app.subdomains.yaml:999`). R8 `:34` mantém a política: escrita no iFood **proibida**.
- **Machine courier**: `SHOPMAN_COURIER_ADAPTER` **não existe em nenhum dos dois specs** (grep em `.do/*.yaml` → vazio); só no `.env.example:277-287`, comentado. Default `None` (`config/settings.py:930`), canal default `courier="none"` (`shopman/shop/config.py:142-145`). A matriz de credenciais marca a linha inteira como `PENDENTE`.

**Impacto:** ambos são **canais aditivos** — não bloqueiam loja, balcão, retirada nem entrega própria. São os dois cortes mais fáceis e de maior retorno. **Confiança: alta.**

### Achado 13 — Media persistente é um problema de **um campo**, não de infraestrutura [FATO]

O backlog lista "Media persistente (Spaces/S3)" como must-have "imediatamente ANTES do go-live" (`PRODUCT-V1-SCOPE-BACKLOG.md:36`). Medido:

- `config/settings.py:567-574` — `STORAGES["default"] = django.core.files.storage.FileSystemStorage`; `:580` — `MEDIA_ROOT` dentro do container (efêmero).
- Grep de `ImageField`/`FileField` em `shopman/` e `packages/` (fora de testes/migrations) → **exatamente 1 resultado**: `shopman/shop/models/shop.py:168` (`Shop.logo`, `upload_to="branding/"`).
- As fotos de produto **não** passam por `MEDIA_ROOT`: moram no repo do storefront e saem por `img.nelsonboulangerie.com.br` (`docs/plans/CATALOG-IMAGES-OFF-GITHUB-PLAN.md:5-13,17-20`).
- Marketing usa hosts externos (`SHOPMAN_MARKETING_MEDIA_HOSTS`), não upload.

**Impacto:** o must-have "infra de mídia" custa, na prática, **um arquivo de logo**. Isso muda a decisão de escopo: pode ser cortado com risco ~zero (seção 5.2, corte C5). **Confiança: alta.**

### Achado 14 — O v1 declarado é auto-bloqueante e tem frentes com trabalho nomeado em aberto [FATO]

`docs/plans/PRODUCT-V1-SCOPE-BACKLOG.md:5-6`: este doc "é o **gate de escopo** do GO-LIVE-READINESS-PLAN: o go-live real só dispara quando o 'deve entrar no v1' abaixo estiver fechado". `:8`: "v1 é **amplo** — 11 frentes". `:77`: "O go-live… só dispara com **todas** as entregues."

Frentes com trabalho ainda nomeado no próprio doc: WhatsApp conversacional (~70%, falta webhook + endpoints inbound), sincronização de catálogos externos (falta homologação), media persistente (não desenvolvida), shelf life (falta decisão de lote), surface convergence, Playwright como gate.

**Impacto:** com esta regra escrita, o go-live fica refém de frentes que dependem de terceiros. **A regra precisa ser re-cortada — é a decisão de maior alavancagem deste relatório.** **Confiança: alta.**

---

### 2.A — Matriz GATE × ESTADO × EVIDÊNCIA  *(entregável 1)*

Estados: `VERIFICADO` / `PENDENTE` / `BLOQUEADO` / `DESCONHECIDO` / `N/A`, conforme `GO-LIVE-READINESS-PLAN.md:19-23`.

#### Gates técnicos

| # | Gate | Estado | Evidência | Bloqueia o corte? |
|---|---|---|---|---|
| T1 | Baseline/SHA congelado | **PENDENTE** | Matriz aponta `ab148fbd` (`:9`); `origin/main` = `ccf68564c`. Falta reauditar no SHA final | Sim |
| T2 | CI/merge queue verde | **VERIFICADO** | R8 `:44`; Runtime, Surfaces, Omotenashi, Security, Production Contract, Operator Groups, Coverage | Não |
| T3 | Imagens + manifesto | **VERIFICADO** | R8 `:45` — Deploy Images run `36521413976`, 3 digests | Não |
| T4 | Deployment ACTIVE | **VERIFICADO** | R8 `:46` — `02527053-…`, predecessor `2353933b-…` identificado | Não |
| T5 | Drift do spec vivo | **BLOQUEADO** (parcialmente resolvido) | Matriz `:48`; `2026-09-29-live-otp-spec-reconciliation.md:19-28` eliminou o **drift destrutivo**. Diferenças operacionais deliberadas continuam | Sim (parcial) |
| T6 | Release job com `migration_safety` | **VERIFICADO** [novo] | OTP-reconciliation `:16-22`; `.do/app.subdomains.yaml:1245`; `.do/app.alpha-subdomains.yaml:1245-1247` | **Não** (fechado) |
| T7 | `production-readiness --read-only` | **VERIFICADO no código** [novo] | `145ff129c`; `Makefile:484`; `scripts/check_release_readiness.py:170-249` | **Não** (fechado) |
| T8 | Banco/cache/migrations do vivo | **VERIFICADO** | Matriz `:41` — `/ready/` 200 com DB, cache, migrations, queue `ok` | Não |
| T9 | Migrations desde banco vazio | **VERIFICADO** | R8 `:81` — `check_migrations.py --json`: 3 pass / 0 fail | Não |
| T10 | Backup / PITR | **VERIFICADO** | `2026-09-29-backup-pitr-verification.md:13-18` — 8 backups, 7 dias, PG16 `nyc3` | Não |
| T11 | **Ensaio de restore** | **BLOQUEADO** | `2026-09-29-backup-pitr-verification.md:19`; matriz `:54` | **Sim — gate duro** |
| T12 | Rollback de código ensaiado | **DESCONHECIDO** | R8 `:84` — predecessor identificado, nenhum ensaio disparado | Sim |
| T13 | Credenciais reais (pagamento) | **BLOQUEADO** | Matriz `:49`; spec de produção sem Stripe/Efí (`.do/app.subdomains.yaml`, grep) | **Sim — gate duro** |
| T14 | Pix real (Efí produção) | **NÃO PRONTO** | `.do/app.alpha-subdomains.yaml:313-316` (`payment_mock`); `EFI_SANDBOX=true` `:337-340`; `config/settings.py:1904` | **Sim — gate duro** |
| T15 | Efí 403 no `efi_webhook` do release | **DESCONHECIDO** | Comentário `.do/app.alpha-subdomains.yaml:308-312` ("Voltar para a Efí só depois de o `efi_webhook` responder OK… conferidos com o Pablo") | **Sim** |
| T16 | Cartão (Stripe) produção | **NÃO PRONTO** | Código real com chave de teste (`.do/app.alpha-subdomains.yaml:394-396`); `STRIPE_CAPTURE_METHOD=manual` (`.do/app.subdomains.yaml:352`) | Sim (ou cortar — seção 5.2 C4) |
| T17 | Fiscal NFC-e produção | **NÃO PRONTO** | `FOCUS_NFE_ENVIRONMENT=homologacao` (`.do/app.alpha-subdomains.yaml:755-761`); default `config/settings.py:1795`; aviso no spec `:541-554` | **Sim — obrigação legal** |
| T18 | Fiscal NF-e entrada (Compras) | **VERIFICADO** | `PURCHASE_NFE_ENVIRONMENT=producao` (`.do/app.subdomains.yaml:563-566`; alpha `:766-769`) | Não |
| T19 | WhatsApp / SMS OTP | **PENDENTE** | Cadeia real `sms,email` (`config/settings.py:1013-1016`); Comtele real (`:996`); **falta o SMS real recebido** (`GO-LIVE-SMS-WHATSAPP-STATUS.md:33-36`) | **Sim** |
| T20 | WhatsApp transacional (templates) | **PENDENTE** | 11 templates Utility a submeter à Meta + flow namespaces (`GO-LIVE-SMS-WHATSAPP-STATUS.md:39-42`) | Depende do escopo |
| T21 | iFood | **NÃO PRONTO** | `IFOOD-COMPLIANCE-2026-09-13.md:5` ("nenhuma tentativa oficial"); `IFOOD-DIRECT-INTEGRATION-PLAN.md:21-22` | **Não, se cortado** |
| T22 | Machine courier | **NÃO PRONTO** | Ausente dos dois specs; `config/settings.py:930` = `None` | **Não, se cortado** |
| T23 | Maps / geocoding | **VERIFICADO (código)** | Google real (`shopman/shop/services/geocoding.py:24`); `SHOPMAN_E023` exige chaves browser/servidor separadas (`shopman/shop/checks.py:1255-1265`) | Não, mas remover chave legada |
| T24 | Domínio / TLS / cookies / CSRF | **PARCIAL** | R8 `:57` — `gestor.boulangerie.com.br` **sem HSTS, CSP, X-Frame-Options, Referrer-Policy**; certificados e cookie `.boulangerie.com.br` OK. `88027a6ff` ("headers de segurança do kit") é posterior ao R8 | Parcial |
| T25 | Domínio comercial aprovado | **DESCONHECIDO** | Matriz `:44`; ledger `:14-22` registra `www.nelsonboulangerie.com.br`, `api.boulangerie.com.br`, `admin.boulangerie.com.br` como hosts do vivo | Sim (decisão) |
| T26 | 2FA Admin | **DESCONHECIDO / NÃO PRONTO** | `SHOPMAN_ADMIN_REQUIRE_2FA` **não declarada** em nenhum spec; default false (`config/settings.py:2130`); R8 `:55` | Sim |
| T27 | Ingress / allowlist do Admin | **DESCONHECIDO** | WP `:143-144`; sem evidência | Sim |
| T28 | Observabilidade (Sentry + e-mail de alerta) | **DESCONHECIDO** | Declarados (`.do/app.subdomains.yaml:497`; `.do/app.alpha-subdomains.yaml:696`); **nenhum alerta sintético emitido** (R8 `:56`) | Sim |
| T29 | Webhooks (registro/replay/homologação) | **DESCONHECIDO** | R8 `:54`; fail-closed provado em teste, provider nunca chamado | Sim |
| T30 | `production-readiness` rodado no alvo | **PENDENTE** | Modo read-only existe (T7); **nunca executado no vivo** (R8 `:96-98`) | Sim |
| T31 | Kill switch global de cupom | **NÃO EXISTE** | R8 `:58`; `grep kill_switch` só acha o do Continuum (`config/settings.py:170`). Alternativa: não usar cupom no dia 1 (seção 5.2 C10) | Sim, ou cortar |
| T32 | Tag `go-live-v1` / ADR-015 | **PENDENTE** (ausente, como esperado) | Matriz `:42`; `git tag -l` vazio | Sim (é o próprio corte) |
| T33 | `SHOPMAN_GO_LIVE=true` | **NÃO DECLARADO** | Ausente dos dois specs; consumido em `shopman/shop/migration_safety.py:122` | Sim (é o próprio corte) |

#### Gates operacionais

| # | Gate | Estado | Evidência |
|---|---|---|---|
| O1 | Incident commander nomeado | **DESCONHECIDO** | R8 `:26` |
| O2 | Janela de cutover assinada | **DESCONHECIDO** | R8 `:25` |
| O3 | Critérios de aborto aceitos | **PARCIAL** (5 itens enumerados, falta aceite) | R8 `:31`; WP `:243-253` |
| O4 | Janela de rollback | **DESCONHECIDO** | R8 `:32` |
| O5 | Comunicação interna (canal/executor/observador) | **DESCONHECIDO** | R8 `:33` |
| O6 | 2FA enroll + recovery testado | **NÃO PRONTO** | WP `:137-142` |
| O7 | Alerta sintético recebido | **NÃO PRONTO** | R8 `:56` |
| O8 | **QA física mobile** (iOS Safari / Android Chrome, GPS, mapa, Pix, cartão, tracking) | **PENDENTE** | Matriz `:51`; WP `:150-161` |
| O9 | **QA física de loja** (PDV, gestor, KDS, produção, impressora, som, gaveta) | **PENDENTE** | Matriz `:52`; WP `:163-174`; `POS-HARDWARE-READINESS-HANDOFF.md:1-4` (falta instalar o agente no balcão e ver a gaveta abrir) |
| O10 | Catálogo/estoque/preço/fiscal aprovados pelos owners | **DESCONHECIDO** | R8 `:58`; `go-live-preflight.md:72-73` |
| O11 | Runbooks revisados pelo IC | **PARCIAL** | `go-live-preflight.md`, `go-live-cutover.md`, `rollback-de-deploy.md` existem e são completos; falta o "revisado por" |
| O12 | Carga proporcional | **DESCONHECIDO** | R8 `:87` |
| O13 | Indisponibilidade / fallback com rede degradada | **DESCONHECIDO** | R8 `:89` |
| O14 | Restore ensaiado com RTO/RPO | **NÃO PRONTO** | T11 |

#### Gates comerciais

| # | Gate | Estado | Evidência |
|---|---|---|---|
| C1 | Escopo v1 assinado por integração | **NO-GO** | R8 `:27` — "iFood, ManyChat/Concierge, Machine, fiscal e Marketing continuam sem inclusão/exclusão assinada" |
| C2 | Canais incluídos/excluídos | **DESCONHECIDO** | R8 `:28` |
| C3 | Teto financeiro dos canários | **DESCONHECIDO** | R8 `:29` |
| C4 | Contatos de teste autorizados | **DESCONHECIDO** | R8 `:30` |
| C5 | Nomenclatura de fases aprovada | **DESCONHECIDO** | Matriz `:45` |
| C6 | Decisão domínio técnico × comercial | **DESCONHECIDO** | Matriz `:44` |
| C7 | Copy pública aprovada | **PARCIAL** | `536cc2993` ("a copy pública só cruza o go-live com o aval do dono") + gate `production.public_copy_review` (`scripts/check_release_readiness.py:703-713`) |
| C8 | GO/NO-GO assinado | **BLOQUEADO** | Matriz `:55`; `go-live-cutover.md:24` ("Ausência de assinatura é **NO-GO**") |

**Placar:** 12 VERIFICADO · 4 PENDENTE · 6 BLOQUEADO · 10 DESCONHECIDO · 4 NÃO PRONTO/EXISTE (contagem sobre as 33+14+8 linhas) [INFERÊNCIA: contagem minha sobre a tabela].

---

### 2.B — Principais funcionalidades e estado de cada uma

"As principais funcionalidades" na leitura do próprio produto (`docs/status.md:17-28`, `surfaces/registry.json`): **loja online, PDV/balcão, KDS/cozinha, gestor de pedidos/encomendas, produção** — mais os canais de entrega e os back-offices.

| Funcionalidade | Código | Estado operacional | Evidência |
|---|---|---|---|
| **Loja online (storefront)** | 22 páginas Nuxt | **QUASE PRONTA** — SSR 200, menu 40/37, checkout anônimo 403 canônico | ledger `:148-152`; `surfaces/registry.json` |
| **Carrinho / checkout** | construído | **QUASE PRONTO** — smoke não mutante verde; falta QA em aparelho real | R8 `:88`; matriz `:51` |
| **Endereço + confirmação no mapa** | `address_map_confirmation_enabled` | **DEPLOYADO, FLAG OFF** | ledger `:188-203` (PR #1256 mergeado `3471adf64`, deploy `038abbca-…` ACTIVE 15:28:53Z, flag pública `false`) |
| **Divergência localização × endereço** | não iniciado | **NÃO PRONTO / BLOQUEADO** | ledger `:205-220` (`NOT_STARTED`, `BLOCKED_BY_PREDECESSOR`) |
| **Pix online** | adapter Efí construído | **NÃO PRONTO** — vivo em `payment_mock` | `.do/app.alpha-subdomains.yaml:313-316` |
| **Cartão online** | adapter Stripe construído | **NÃO PRONTO** — chave de teste | `.do/app.alpha-subdomains.yaml:317-320,394-396` |
| **PDV / balcão** | 7 páginas; crédito/débito liquidam **sem gateway** (maquininha física atestada pelo operador) | **PRONTO no código / PENDENTE no físico** | `docs/plans/WP-PAGAMENTO-LINK-E-TEF.md:24-26`; `POS-HARDWARE-READINESS-HANDOFF.md:1-4` |
| **KDS / cozinha** | 3 páginas | **PRONTO no código** | `surfaces/registry.json` |
| **Gestor de pedidos / Encomendas** | 10 páginas | **PRONTO no código / QA autenticado pendente** | `PRODUCT-V1-SCOPE-BACKLOG.md:30` ("Resta QA funcional autenticado") |
| **Produção / fornadas** | 12 páginas | **PRONTO no código** | `surfaces/registry.json` |
| **Availability Admin** | PR #1253 | **DEPLOYADO / SMOKE HUMANO PENDENTE** | ledger `:140-155` (deploy `9dec55ad-…` ACTIVE 14:49:46Z) |
| **Fiscal NFC-e** | S0–S4 construído | **NÃO PRONTO** — homologação | `docs/status.md:44`; `.do/app.alpha-subdomains.yaml:755-761` |
| **Fiscal NF-e entrada** | produção | **PRONTO** | `.do/app.subdomains.yaml:563-566` |
| **Login (OTP SMS)** | cadeia real | **PENDENTE de prova** | `config/settings.py:996,1013-1016`; `GO-LIVE-SMS-WHATSAPP-STATUS.md:33-36` |
| **iFood** | construído | **NÃO PRONTO** — homologação nunca iniciada | `IFOOD-COMPLIANCE-2026-09-13.md:5` |
| **Machine courier** | construído | **NÃO CONFIGURADO** | ausente dos specs; `config/settings.py:930` = `None` |
| **Marketing** | cockpit/outbox/ledger | **PERIGOSO no vivo** | `.do/app.alpha-subdomains.yaml:481-489`; R8 `:70-73` |
| **Concierge / ManyChat** | construído | **OBSERVE, allowlist VAZIA** | `9d57ae346`: `CONCIERGE_OPERATION_MODE=observe`, `CONCIERGE_OBSERVATION_ALLOW_ALL_SUBSCRIBERS=true`, `CONCIERGE_OBSERVATION_ALLOWED_SUBSCRIBERS=''` |
| **B.I.** | 8 páginas | **PRONTO no código** | `surfaces/registry.json` |
| **Compras** | 1 página | **PRONTO no código** | `surfaces/registry.json` |

---

### 2.C — Inventário de MOCKS e o que falta para virar real  *(entregável 2)*

**Legenda:** 🔴 = mock no ambiente vivo e exposto ao público · 🟠 = mock no ambiente vivo, não exposto · 🟡 = configuração de teste, inerte · 🟢 = sempre-mock aceitável (só teste).

| # | Componente | O que está hoje | path:line | O que falta para virar real |
|---|---|---|---|---|
| 1 | 🔴 **Pix (adapter)** | `SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_mock` | `.do/app.alpha-subdomains.yaml:313-316` (justificativa `:308-312`) | Trocar por `payment_efi`; `ALLOW_MOCK=false`; `EFI_SANDBOX=false`; **provar o `efi_webhook` OK** (o 403 de 22/09 é a causa da volta ao mock) |
| 2 | 🔴 **Botão "Simular pagamento"** | `SHOPMAN_EXPOSE_MOCK_CAPTURE=true` — **público** | `:325-328`; endpoint `shopman/storefront/api/urls.py:182`; gate `shopman/shop/services/payment.py:1891-1931`; UI `surfaces/storefront-nuxt/app/components/PaymentBlock.vue:116-132` | `false`. Default do código já é `False` (`config/settings.py:1687`) |
| 3 | 🟠 **Efí em sandbox** | `EFI_SANDBOX=true`; default do código também `true` | `:337-340`; `config/settings.py:1904`; efeito em `payment_efi.py:352-357` | `false` + credenciais de produção. **Sem trava em runtime** (`fallbacks-perigosos-go-live.md:377`) |
| 4 | 🟠 **NFC-e em homologação** | `FOCUS_NFE_ENVIRONMENT=homologacao`; default também | `:755-761`; `config/settings.py:1795`; `fiscal_focusnfe.py:227-228` | `producao` (**decisão do dono**, `docs/runbooks/ativar-focus-nfe.md`) + validar com o contador + avaliar `SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH` (`config/settings.py:1770`, hoje `false`) |
| 5 | 🟡 **`DOORMAN_MESSAGE_SENDER_CLASS=LogSender`** | Declarado no vivo | `:387-390`; classe `packages/doorman/shopman/doorman/senders.py:82-89` (`reveals_code=True`) | **Não é o caminho hoje** (Achado 5). Remover a env ou trocar por um sender real; a trava de boot cobre o caso de cadeia vazia (`apps.py:42-54`) |
| 6 | 🟡 **OTP de debug** | Spec versionado `false`; R8 mediu **exposto** no vivo | `:383-386`; `config/settings.py:107`; gate `shopman/storefront/api/auth.py:446-491` | Confirmar `false` **no vivo** e `SHOPMAN_DEBUG_OTP_TOKEN` ausente (sem o token, fora de DEBUG o código recusa — `auth.py:482-486`) |
| 7 | 🟠 **Cartão online (Stripe test)** | Código real, chave de teste | `:317-320,394-396`; `payment_stripe.py:102-132` | Chaves de produção + webhook assinado revalidado. **Decisão de escopo:** pode ser cortado do dia 1 (seção 5.2 C4) |
| 8 | 🟠 **Link de pagamento do balcão** | Sem `SHOPMAN_LINK_ADAPTER` — herda o adapter de cartão | `config/settings.py:1667-1672`; URL falsa do mock `payment_mock.py:187`; prontidão `shopman/backstage/services/integration_readiness.py:470-481` | Herda o destino do cartão: Stripe live, ou Stone (frente 4, pós-go-live — `WP-PAGAMENTO-LINK-E-TEF.md:3-4`) |
| 9 | 🟠 **Machine courier** | Adapter real, **não configurado**; `courier="none"` | ausente dos specs; `config/settings.py:930`; `shopman/shop/config.py:142-145` | `SHOPMAN_COURIER_ADAPTER` + `MACHINE_*` + canal `fulfillment.courier="auto"`. **Cortar do v1** (seção 5.2 C3) |
| 10 | 🟠 **Piloto automático de staging** | `SHOPMAN_STAGING_AUTOPILOT=false` | `:544-549`; `config/settings.py:1702`; `staging_autopilot.py:54-71` | Nada — já desligado. Manter |
| 11 | 🟡 **Auto-confirmação de Pix** | `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=false` | `:329-336`; `config/settings.py:1688` | Nada — já desligado |
| 12 | 🟡 **Adapter de notificação console** | Só em DEBUG ou com env proibida | `config/settings.py:1742-1743`; proibida em `scripts/check_production_contract.py:23` | Nada — ausente do vivo |
| 13 | 🟡 **`notifications.get_backend(None)` resolve para console** | Fail-open de código | `shopman/shop/notifications.py:33-37` | Frente própria (`fallbacks-perigosos-go-live.md` item 14). Não é env |
| 14 | 🟡 **E-mail com backend console** | Default console; **alpha usa SMTP real** | `config/settings.py:1167`; `.do/app.alpha-subdomains.yaml:712-716` | Nada no ambiente atual; em ambiente novo, definir `EMAIL_BACKEND` |
| 15 | 🟡 **Adapter de e-mail devolve sucesso imprimindo** | `is_available` incondicionalmente `True` | `docs/plans/fallbacks-perigosos-go-live.md:101-125` (item 4, aberto) | Frente própria. **Risco real:** `payment_requested` e `purchase_request` caem no vazio e o log diz "sent" |
| 16 | 🟢 **Continuum catalog shadow/snapshot** | `false` nos dois specs | `.do/app.subdomains.yaml:369-380`; `config/settings.py:170` | Nada |
| 17 | 🟢 `courier_mock` | Só em teste (único consumidor: `shopman/shop/tests/test_courier_service.py`) | `shopman/shop/adapters/courier_mock.py:1-24` | Nada |
| 18 | 🟢 `tests/_mocks/*_mock.py` (fiscal, accounting) | **Zero importadores** | `shopman/shop/tests/_mocks/` | Nada |
| 19 | 🟢 `marketing_delivery_console` | `SIMULATION_ONLY`; exige DEBUG + `development/test` | `shopman/shop/adapters/marketing_delivery_console.py:22,33-42` | Nada |
| 20 | 🟢 `ifood_simulation` + `inject_ifood_order` | Comando levanta erro se `not DEBUG` | `shopman/shop/management/commands/inject_ifood_order.py:23-24` | Nada. A docstring promete um botão no checkout que **não existe** (grep sem chamadores) |
| 21 | 🟢 `settings_test.py` | `ALLOW_MOCK=True`, `EXPOSE_DEBUG_OTP=True` | `config/settings_test.py:47,107-110` | Nada — legítimo, com teste da porta fechada (`test_payment_never_authorized_without_gateway.py`) |
| 22 | 🟢 Fakes das 6 superfícies | `tests/e2e/mockBackend.mjs`, `marketing/tests/visual/mock_backend.py` | `surfaces/*/tests/` | Nada |

**Trava que já existe e deve ser preservada:** `shopman/shop/adapters/payment_mock.py:95-103` (`MockGatewayNotAllowed` fora de DEBUG sem opt-in) e `shopman/shop/services/payment_provenance.py:8-24,57-60` (marca `provider_simulated`/`local_mock` e **exclui do fechamento, do livro do turno, do B.I. e da conciliação**). Essa segunda é o que garante que "Pix de mentira nunca vira receita" mesmo em homologação.

---

## 3. O que já existe e funciona (não reinventar)

1. **Cadeia de entrega comprovada:** `main → Deploy Images → deploy_on_push → deployment ACTIVE → Pre-go-live Smoke`. Smoke runs `36521633479`, `36585437565`, `36590337864` verdes; `/ready/` 200, menu 40/37, checkout anônimo 403 canônico, SSR 200 (`docs/status.md:71-81`; ledger `:148-152`, `:194-199`).
2. **25 deploy-checks nomeados** (`shopman/shop/checks.py:7-30`): `E001`–`E025`, incluindo `E003` (pagamento mock), `E009` (credencial real ausente), `E010` (OTP debug), `E015` (captura simulada), `E022` (provedor apontando para ambiente de teste), `E023` (Maps browser/server separados).
3. **Gate de perfil de produção pronto para uso:** `scripts/check_release_readiness.py:377-418` já enumera exatamente as chaves que precisam virar; `--read-only` com zero escrita **garantida por mecanismo** (`:170-249`); `Makefile:492-496` (`production-readiness`, `production-contract`).
4. **Migrations:** grafo limpo desde banco vazio (3 pass / 0 fail, R8 `:81`); `migration_safety` recusa deploy destrutivo pós-tag sem `SHOPMAN_MIGRATION_BACKUP_REF` (`shopman/shop/migration_safety.py:112-127`).
5. **Backup/PITR:** 8 backups diários, retenção 7 dias, PG16 (`2026-09-29-backup-pitr-verification.md:13-18`).
6. **Rollback runbook:** `docs/runbooks/rollback-de-deploy.md` completo, com classificação por classe de mudança (`:22-28`) e evidência mínima (`:66-74`).
7. **Fail-closed já provado em teste:** webhooks duplicados/fora de ordem (7 fixtures, R8 `:85`); reconciliação `--dry-run` sem persistir (R8 `:86`); checkout sem cobrança (R8 `:88`).
8. **Cupom × frete grátis e lote × promoção:** dois P1 do code-audit corrigidos com teste canônico (`shopman/shop/modifiers.py:1253-1262`; `test_lot_pricing.py`, `test_free_delivery_promotion.py`).
9. **Proveniência de pagamento simulado:** `payment_provenance.py` exclui mock de receita em 4 leituras.
10. **Fotos de produto fora do GitHub, em host dedicado**, com cache imutável (`docs/plans/CATALOG-IMAGES-OFF-GITHUB-PLAN.md:5-13`).
11. **Geo sem terceiro para o rótulo de cidade** (GeoLite2 local); geocoding de endereço em Google real (`shopman/shop/services/geocoding.py:24`).
12. **Gate documental** `make canonical-docs` (`.github/workflows/runtime-gate.yml:93`) — protege estruturalmente matriz e ADR-015, só não protege contra *staleness*.

---

## 4. Lacunas / riscos

| # | Lacuna | Impacto | Evidência |
|---|---|---|---|
| L1 | **Nenhuma integração passou do estado 2 de 5** da matriz de credenciais | O corte não tem prova de que Efí/Stripe/Focus/Comtele entregam | `GO-LIVE-CREDENTIALS-MATRIX.md:33-45` |
| L2 | **`efi_webhook` respondeu 403 em 22/09** e o Pix voltou ao mock por isso | Se não fechar, Pix real nasce quebrado. É o **elo mais provável de atrasar o corte** | `.do/app.alpha-subdomains.yaml:308-316` |
| L3 | **Restore nunca ensaiado** | Sem RTO/RPO medido, qualquer incidente no corte vira fé | `2026-09-29-backup-pitr-verification.md:19` |
| L4 | **Marketing armado** (`WHATSAPP_MODE=open` + delivery ligado) no vivo | Envio real irreversível para clientes reais | `9d57ae346`; `.do/app.alpha-subdomains.yaml:481-489` |
| L5 | **`SHOPMAN_EXPOSE_MOCK_CAPTURE=true` público** | Qualquer visitante quita o próprio pedido | `:325-328` |
| L6 | **Matriz canônica 70 commits stale e gate não detecta** | Decisão tomada sobre estado velho | `GO-LIVE-READINESS-PLAN.md:9`; `scripts/check_canonical_docs.py:188-226` |
| L7 | **Dois registros de verdade** (matriz × ledger); nenhum dos 7 docs do programa cita o ledger | Duas versões do estado; o ledger proíbe isso | ledger `:7`; programa R0–R8 |
| L8 | **`EFI_SANDBOX` e `FOCUS_NFE_ENVIRONMENT` sem trava em runtime e fora do gate de produção** | Esquecimento de 1 linha = dinheiro em gateway errado ou nota sem valor | `fallbacks-perigosos-go-live.md:377-378`; `scripts/check_release_readiness.py:384-401` |
| L9 | **Sem kill switch global de cupom** | Não dá para "desligar a promoção" durante a janela | R8 `:58`; grep `kill_switch` |
| L10 | **2FA do Admin desligado e sem ingress aprovado** | Admin exposto no domínio comercial | `SHOPMAN_ADMIN_REQUIRE_2FA` ausente dos specs; R8 `:55` |
| L11 | **`gestor.boulangerie.com.br` sem headers de segurança** | XSS/clickjacking na superfície do gestor | R8 `:57` (mitigado parcialmente por `88027a6ff`, posterior ao R8 — [NÃO VERIFICADO] o valor vivo) |
| L12 | **Zero QA física** (mobile e loja) | O que quebra no corte é o que só o aparelho mostra | Matriz `:51-52` |
| L13 | **Nenhum alerta sintético emitido** | Observabilidade declarada, não provada | R8 `:56` |
| L14 | **`production-readiness` nunca rodou no alvo** | O gate mais forte existe e não foi usado | R8 `:92-98` |
| L15 | **Comentário de doc desatualizado:** `fallbacks-perigosos-go-live.md:32,54` cita `config/settings.py:1142`/`:1072`; os reais são `:1904`/`:1795` | Auditor lê linha errada | verificado por grep |
| L16 | **`docs/status.md:58` declara 268 migrations; medido: 270** | Contagem canônica errada | `find … \| wc -l` |
| L17 | **`WP-ALPHA-FIX-01` diz "aberto" com o código já implementado** | Planejamento sobre dívida que não existe | `docs/plans/WP-ALPHA-FIX-01-producao-e-efi.md:7` vs `packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py:97,119` |
| L18 | **`simulate_ifood_order` sem chamador**, com docstring prometendo botão | Doc × código divergentes | `shopman/shop/services/ifood_simulation.py:4-5` |
| L19 | **Webhook Efí aceita token em query string** | Aberto por decisão documentada, com `before_send` no Sentry + rotação | `shopman/shop/webhooks/efi.py:317-334`; `config/settings.py:2291-2292` |
| L20 | **`/health` e `/ready/` sem throttle** | Amplificação; o plano de migrations já é cacheado | `shopman/shop/views/health.py` (grep `ratelimit`/`throttle` → 0) |

---

## 5. Recomendações acionáveis

### 5.1 — Caminho crítico proposto  *(entregável 3)*

**A menor sequência que destrava go-live.** Formato: `[ID] ação — owner — dependência — esforço`.

```
        +-------------------------------------------------------------+
        | K0 - DECISAO (bloqueia tudo, custo ~1 reuniao)              |
        |  Escopo v1 assinado COM OS CORTES da secao 5.2; incident     |
        |  commander; janela; teto dos canarios; contatos de teste;    |
        |  criterios de aborto; janela de rollback; canal interno.     |
        |  Owner: Pablo.  Evidencia de saida: linha no ledger.         |
        +---------------------------+---------------------------------+
                                    |
        +---------------------------v---------------------------------+
        | K1 - CREDENCIAL (dono + plataforma, elo mais lento)         |
        |  K1.1 Efi producao: resolver o 403 do efi_webhook (L2).      |
        |       SEM ISSO NAO HA PIX.                                    |
        |  K1.2 Focus NFe: token + decisao FOCUS_NFE_ENVIRONMENT=      |
        |       producao + aval do contador.                            |
        |  K1.3 Comtele: provar 1 SMS real (R$0,12).                    |
        |  K1.4 (se mantiver cartao online) chaves live do Stripe.      |
        +---------------------------+---------------------------------+
                                    |
        +---------------------------v---------------------------------+
        | K2 - FLIP DE AMBIENTE (engenharia, horas, ja tem codigo)    |
        |  Compor o spec A PARTIR DO VIVO (nunca aplicar o arquivo):    |
        |   SHOPMAN_ENVIRONMENT=production                             |
        |   SHOPMAN_PIX_ADAPTER=payment_efi                            |
        |   EFI_SANDBOX=false                                          |
        |   FOCUS_NFE_ENVIRONMENT=producao                             |
        |   remover SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS                |
        |   remover SHOPMAN_EXPOSE_MOCK_CAPTURE                        |
        |   SHOPMAN_MARKETING_WHATSAPP_MODE=blocked                    |
        |   SHOPMAN_MARKETING_*_CONSUMER_ENABLED=false                 |
        |   (opcional) SHOPMAN_ADMIN_REQUIRE_2FA=true                  |
        |  Gate de saida: manage.py check --deploy LIMPO.              |
        +---------------------------+---------------------------------+
                                    |
        +---------------------------v---------------------------------+
        | K3 - PROVA TECNICA (engenharia + plataforma, ~1 dia)        |
        |  K3.1 make production-readiness read_only=1 no alvo, verde   |
        |  K3.2 Restore ensaiado em fork descartavel (conexao DIRETA,  |
        |       NUNCA o pool), RTO/RPO registrados                     |
        |  K3.3 Rollback de codigo ensaiado (predecessor ja conhecido) |
        |  K3.4 Alerta sintetico recebido                              |
        +---------------------------+---------------------------------+
                                    |
        +---------------------------v---------------------------------+
        | K4 - PROVA EXTERNA (operacao, ~1 dia, humano no aparelho)   |
        |  K4.1 Canario de UM: Pix de valor baixo + NFC-e + estorno,   |
        |       autorizados um a um                                    |
        |  K4.2 QA mobile (iOS Safari + Android Chrome)                |
        |  K4.3 QA fisica de loja (impressora, som, gaveta, PDV, KDS)  |
        +---------------------------+---------------------------------+
                                    |
        +---------------------------v---------------------------------+
        | K5 - CORTE                                                    |
        |  tag go-live-v1 (anotada, no SHA congelado) ->                |
        |  SHOPMAN_GO_LIVE=true -> deploy -> smoke -> canario de um -> |
        |  janela de observacao -> decisao de expansao                  |
        +--------------------------------------------------------------+
```

**Propriedades do caminho:**

- **Gargalo real = K1 (credencial) e K4 (humano no aparelho).** K2 e K3 são engenharia com código já no `main`: `--read-only` existe (`145ff129c`), `migration_safety` está no release job, os checks `E003/E009/E010/E015/E022` já reprovam o perfil errado.
- **K1.1 (Efí 403) é o único elo que pode virar projeto.** Está sem diagnóstico desde 22/09 (`.do/app.alpha-subdomains.yaml:308-312`). Tratá-lo como o item de maior risco técnico e atacá-lo **primeiro**, ainda durante K0.
- **Paralelizável:** K1.2/K1.3/K1.4 não dependem de K1.1; K3.2 (restore) não depende de K1; K4.3 (QA física) pode começar antes do flip, com o ambiente atual, para impressora/gaveta/som, porque o que é físico não depende de credencial.
- **Corte antecipado possível ("go-live parcial")** [INFERÊNCIA]: com K1.2 (fiscal) + K1.3 (login) fechados e sem K1.1, é possível subir com **Pix desabilitado**, deixando online só **balcão (crédito/débito na maquininha, que já liquida sem gateway)** + **retirada com pagamento no balcão**. Não é o objetivo do dono, mas é a rede de segurança se a Efí não fechar, e vale ser decidido em K0, não em K4.

**Sequência mínima absoluta (a "menor cadeia"):**
`K0 -> K1.1 -> K2 -> K3.1 -> K4.1 -> K5`.
Seis elos, dos quais **só K2 é engenharia nova**; os outros cinco são decisão, credencial, prova e assinatura.

---

### 5.2 — Proposta de corte de escopo  *(entregável 4)*

> **Regra que precisa ser revogada primeiro:** `PRODUCT-V1-SCOPE-BACKLOG.md:77` ("o go-live só dispara com **todas** as entregues"). Com 11 frentes, 2 dependendo de terceiros, essa regra **garante atraso**. Proposta: **v1 = o que o cliente final usa no dia 1**; o resto vira v1.1 com data.

#### CORTAR (adiar pós-go-live, risco ~zero)

| # | Corte | Justificativa com evidência | Risco de cortar |
|---|---|---|---|
| **C1** | **Marketing: publicação e delivery** | Vivo em `WHATSAPP_MODE=open` + `DELIVERY_ENABLED=true`, `ALLOW_ALL_SUBSCRIBERS`, allowlist vazia. Publicação real é irreversível e de maior blast radius da janela. O canário de publicação já está desligado no vivo (R8 `:70-73`) | Nenhum para venda. Manter o cockpit **em leitura** e ligar publicação depois da janela |
| **C2** | **iFood** | Homologação **nunca iniciada** (`IFOOD-COMPLIANCE-2026-09-13.md:5`); certificação externa é obrigatória (`IFOOD-DIRECT-INTEGRATION-PLAN.md:21-22`); R8 mantém escrita proibida (`:34`). Canal **aditivo** | Nenhum — a loja própria cobre. Desligar `ifood-poll-worker` (`.do/app.subdomains.yaml:999`) ou mantê-lo ocioso |
| **C3** | **Machine courier / delivery externo** | Nenhuma credencial em nenhum spec; canal default `courier="none"` (`shopman/shop/config.py:142-145`). Entrega própria cobre | Nenhum. Manter entrega própria |
| **C4** | **Cartão online (Stripe live)** — *opcional, se o tempo apertar* | Código real, só falta chave live. **Mas** o balcão já liquida crédito/débito **sem gateway** (`WP-PAGAMENTO-LINK-E-TEF.md:24-26`) | Perde conversão online. **Só cortar se K1 estourar**; senão manter, porque é troca de chave |
| **C5** | **Media persistente (Spaces/S3)** | Raio de impacto = **1 campo** (`Shop.logo`, `shopman/shop/models/shop.py:168`); fotos de produto já moram no repo do storefront com host dedicado (`CATALOG-IMAGES-OFF-GITHUB-PLAN.md:5-13`) | Perder o logo num redeploy. Mitigação: manter o logo versionado no repo (mesmo padrão das fotos) ou re-subir. **Corta um must-have inteiro por ~1h de trabalho** |
| **C6** | **ManyChat conversacional / pedido inbound** | ~70% pronto e sem webhook (`PRODUCT-V1-SCOPE-BACKLOG.md:34`); Concierge em `observe` com allowlist vazia; OTP nunca passa por ManyChat (`GO-LIVE-SMS-WHATSAPP-STATUS.md:42`) | Nenhum — vender continua pela loja, balcão e WhatsApp humano |
| **C7** | **Sincronização de catálogos externos (Google/Meta feeds)** | Falta homologação externa (`PRODUCT-V1-SCOPE-BACKLOG.md:35`) | Nenhum para venda direta |
| **C8** | **B.I. (`bi-nuxt`)** | Leitura analítica; não participa de nenhuma transação | Nenhum. Ligar depois com dados reais |
| **C9** | **Compras (`purchase-nuxt`)** | 1 página, back-office, NF-e de entrada **já em produção** e independente da venda | Nenhum para o cliente |
| **C10** | **Cupons e promoções no dia 1** | Não existe kill switch global de cupom (R8 `:58`). **Não usar cupom no dia 1 dispensa construir um** | Nenhum — vender sem promoção é o normal da operação |
| **C11** | **Teleporte de endereço, customer rating, troca de telefone** | Já eram pós-v1 declarados (`PRODUCT-V1-SCOPE-BACKLOG.md:42-49`) | Nenhum |
| **C12** | **`SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH`** | Default `false` (`config/settings.py:1770`) | Nenhum — ligar depois da classificação fiscal estar completa |
| **C13** | **Playwright como gate obrigatório amplo** | Já roda parcialmente no CI (`surfaces-gate.yml`, `orders-isolated-capacity.yml`) | Nenhum — não bloquear o corte por cobertura de E2E |

**Economia do corte:** 13 frentes saem da janela; **C5, C10 e C11 zeram trabalho** (não são "adiar", são "não fazer"); C1, C2, C3 e C6 são **desligamentos de configuração**, não desenvolvimento.

#### NÃO CORTAR (must-have do dia 1)

| Item | Por quê |
|---|---|
| **Pix real (Efí produção)** | É o meio de pagamento online da casa; uma boulangerie brasileira sem Pix não vende online |
| **Fiscal NFC-e em produção** | Obrigação legal. O spec é explícito: nota em homologação **não existe no SEFAZ** (`.do/app.alpha-subdomains.yaml:541-554`) |
| **Login real (SMS Comtele + e-mail)** | Sem entrega, nenhum cliente entra. **Não é o LogSender**: é provar a entrega (Achado 5) |
| **`SHOPMAN_EXPOSE_MOCK_CAPTURE=false`** | Uma linha. Sem isso, qualquer visitante quita o próprio pedido |
| **PDV/balcão + KDS + Gestor + Produção** | É a operação física |
| **Impressão, gaveta, som** | Sem isso o balcão para |
| **2FA do Admin + ingress restrito** | Admin no domínio comercial; custa horas |
| **Restore ensaiado** | É a única saída de emergência |
| **Alerta sintético** | Sem isso o incidente não avisa |
| **QA física mobile + loja** | É onde mora o defeito que o CI não vê |

#### RE-CORTAR A REGRA, não só a lista

- Substituir `PRODUCT-V1-SCOPE-BACKLOG.md:77` por: *"o go-live dispara quando as frentes NÚCLEO estiverem entregues e as demais tiverem data de v1.1 assinada"*.
- Registrar cada corte como `N/A` na matriz de credenciais (`GO-LIVE-CREDENTIALS-MATRIX.md:66-67` já prevê: "Uma integração fora do escopo aprovado vira `N/A`; até a decisão, fica `DESCONHECIDO`, não 'opcional'").
- Registrar cada corte como linha `N/A` no **activation ledger**, que é hoje o único artefato com o formato certo para isso.

---

### 5.3 — Recomendações ordenadas por impacto / esforço

| Ordem | Ação | Impacto | Esforço | Owner |
|---|---|---|---|---|
| 1 | **Re-cutar o escopo v1 com os 13 cortes da seção 5.2 e assinar** | Destrava tudo; hoje o v1 é auto-bloqueante | 1 reunião | Pablo |
| 2 | **`SHOPMAN_EXPOSE_MOCK_CAPTURE=false` no vivo** | Fecha um botão público de fraude | minutos | Plataforma |
| 3 | **`SHOPMAN_MARKETING_WHATSAPP_MODE=blocked` + consumers `false` no vivo** | Elimina o maior risco irreversível da janela | minutos | Pablo + Plataforma |
| 4 | **Atacar o 403 do `efi_webhook`** | É o elo que pode virar projeto; hoje bloqueia todo Pix real | horas a dias | Pablo + Efí |
| 5 | **Rodar `make production-readiness read_only=1` no alvo e anexar a saída** | O gate mais forte já existe e nunca foi usado | horas | Engenharia |
| 6 | **Adicionar `EFI_SANDBOX` e `FOCUS_NFE_ENVIRONMENT` ao gate de produção** (`scripts/check_release_readiness.py:377-418` + `SHOPMAN_E022`) | Fecha os dois "esquecimentos de 1 linha" que o gate não pega | horas | Engenharia |
| 7 | **Autorizar e executar o restore ensaiado** (fork, conexão direta) | Único gate de recuperação aberto | horas + custo do fork | Pablo + Plataforma |
| 8 | **Provar 1 SMS real pela Comtele** | Fecha o login | minutos + R$0,12 | Engenharia |
| 9 | **Fechar `FOCUS_NFE_ENVIRONMENT=producao` com o contador** | Obrigação legal | horas | Pablo + contador |
| 10 | **Enroll de 2FA + ingress restrito no `admin.`** | Admin comercial | horas | Pablo + Plataforma |
| 11 | **Compor o spec a partir do vivo com os flips de K2** e rodar `check --deploy` | Materializa o corte | horas | Plataforma |
| 12 | **Fazer o gate `canonical-docs` validar `baseline_git` contra `origin/main`** | Impede recorrência do Achado 2 | horas | Engenharia |
| 13 | **Unificar matriz × ledger** (o ledger vira a única fonte; a matriz vira procedimento) | Elimina L7; o próprio ledger proíbe dois | horas | Engenharia |
| 14 | **Atualizar `docs/status.md` (268 -> 270) e o comentário de linhas do `fallbacks-perigosos`** | Evita auditor lendo linha errada | minutos | Engenharia |
| 15 | **QA física de loja (impressora/gaveta/som)**, pode começar antes do flip | Não depende de credencial | 1 dia | Pablo + Operação |
| 16 | **Alerta sintético** | Prova observabilidade | minutos | Plataforma |
| 17 | **Corrigir `is_available` do adapter de e-mail** (`fallbacks-perigosos-go-live.md:101-125`) | Hoje o canal que carrega o link de pagamento falha em silêncio | horas | Engenharia |
| 18 | **Header de segurança em `gestor.`** | R8 `:57`; parcialmente endereçado por `88027a6ff` | horas | Engenharia |

---

## 6. Perguntas abertas / o que não consegui verificar

1. **Qual é o valor REAL do spec vivo hoje?** Todo o diagnóstico de mocks vem do arquivo versionado (`.do/app.alpha-subdomains.yaml`) e do R8 (medido às 04:45Z). Entre 04:45Z e agora o spec foi recomposto (OTP reconciliation, 09:10-09:19Z). **Não tenho `doctl`** e não rodei `check_do_spec_drift.py`. [NÃO VERIFICADO]
2. **O `efi_webhook` responde OK hoje?** O 403 de 22/09 é a causa declarada da volta ao mock, e não há registro de resolução posterior. [NÃO VERIFICADO]
3. **`COMTELE_API_KEY` / `COMTELE_ROUTE` no vivo têm valor válido?** Estão declarados no blueprint (`:419-424`); o doc de status exigia a renomeação do secret no DO. Não há prova de que foi feita. [NÃO VERIFICADO]
4. **O vivo usa mesmo `SHOPMAN_ENVIRONMENT=staging`?** R8 mediu isso às 04:45Z; a recomposição de 09:19Z não menciona essa chave. [INFERÊNCIA: continua staging]
5. **Os headers de segurança em `gestor.` foram corrigidos?** `88027a6ff` ("Pedidos (gestor.) com os headers de segurança do kit") é posterior ao R8, mas não confirmei o valor em produção. [NÃO VERIFICADO]
6. **Estado atual dos 5 PRs dormentes** (#1120, #1119, #1116, #1148, #722) e dos 4 drafts de snapshot (#1220-#1223). Não rodei `gh`. O `main` já está em `\@nuxt/kit` 3.21.11 (`surfaces/operator-kit/package.json:33`), o que sugere supersessão do #722 por outra via. [INFERÊNCIA]
7. **R1, R2, R3, R4, R5 do programa de recuperação não têm relatório de execução.** Entrega comprovada por commit no `main`, estado final não declarado. [FATO: ausência]
8. **Se o cutover trocar o cluster Postgres**, backup/PITR precisam ser reverificados no cluster final (`2026-09-29-backup-pitr-verification.md:26-28`). Não sei se o cutover troca. [NÃO VERIFICADO]
9. **Teto financeiro dos canários e contatos de teste** — não existem em nenhum documento; são decisões do dono. [NÃO VERIFICADO]
10. **`SHOPMAN_ALERT_EMAIL` tem destinatário válido no vivo?** Declarado como env; valor não lido (correto). [NÃO VERIFICADO]
11. **A carga proporcional** nunca foi exercida contra o vivo (R8 `:87`). [NÃO VERIFICADO]
12. **Este relatório leu código até `f0ffd02fd`.** `origin/main` está 14 commits à frente; o delta é POS Encomendas + `reschedule.py` + `stock.py` + o ledger, e **não** altera nenhuma conclusão aqui, mas uma auditoria do SHA final precisa ser refeita.

---

### Anexo — Comandos reproduzíveis (todos somente leitura)

```bash
WT=/Users/pablovalentini/Dev/Claude/django-shopman/.dsh-worktrees/go-live-acceleration
cd $WT

# Achado 1 - HEAD vs origin/main
git rev-parse HEAD origin/main
git rev-list --count f0ffd02fd..origin/main

# Achado 2 - contagem real de migrations (docs/status.md:58 diz 268)
find shopman packages -path "*/migrations/*.py" ! -name "__init__.py" | wc -l

# Achado 2 - o gate canonico passa mesmo com a matriz stale
/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python scripts/check_canonical_docs.py

# Achado 5 - a cadeia de entrega vence o MESSAGE_SENDER_CLASS
grep -n "MESSAGE_SENDER_CLASS\|DELIVERY_CHAIN\|DELIVERY_SENDERS" config/settings.py
sed -n '170,180p;288,299p' packages/doorman/shopman/doorman/adapter.py

# Achado 7 - o modo read-only existe e e mecanico
git merge-base --is-ancestor 145ff129c HEAD && echo "read-only esta em HEAD"
grep -n "read_only\|READ ONLY" scripts/check_release_readiness.py | head

# Achado 13 - media persistente e 1 campo
grep -rn "ImageField\|FileField" --include=*.py shopman/ packages/ | grep -v "/tests/\|migrations/"

# Ledger de ativacao (ja em origin/main)
git show origin/main:docs/runbooks/GO-LIVE-ACTIVATION-LEDGER-2026-09-29.md | head -60
```


