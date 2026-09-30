# WP-POS-STATION-DEVICE-CUSTODY — caixa, terminal e dispositivo

> Aberto em 2026-09-29. **Ordens de serviço**, não plano de fundo. Cada WP abaixo é
> auto-suficiente: pode ser colado como prompt num executor, um branch por WP.
>
> **Evidência (não é preciso reler para executar):**
> `docs/reports/go-live-acceleration-20260929/14-sessao-pdv-multidispositivo.md` e
> `15-gaveta-custodia-multidispositivo.md` — ambos com prova em runtime.
> Contexto e decisão do dono: `docs/coordination/DECISIONS.md` **D-004**.

## Progresso

| Frente | Estado | Evidência |
|---|---|---|
| **Frente 0 — destravar CI** | ✅ **MERGEADA** | PR #1275 · merge `c97f56c24` em `origin/main`. Commits `8583d1f4b` (`-n auto` em `test-shop` e `test-storefront` + `uuid1`→UUID v1 fixo) e `e27ea6b47` (3 testes de log deixaram de depender da ordem). Nenhum arquivo de `.github/` tocado. |
| **WP-3 — higiene** | ✅ **NA FILA** | PR #1276 · flag fantasma confirmada (grep: nenhum consumidor) · `WP-LOCK-01` corrigido |
| **WP-1 — autoria + rastro** | ✅ **NA FILA** | PR #1278 · commit `776478628` · `pos_intent.stamp_line_authorship` (:426) como escritor único, chamado de `pos.py:2566` (`_replace_session_ops`, com 3 chamadores: `:628`, `:1428`, `:1468`). Nenhuma atribuição direta a `session.items` nos services. |
| **WP-4** | próximo | — |
| WP-2 · WP-5 · **WP-6** | pendentes | WP-6 é novo — ver abaixo |

**Ganho medido da Frente 0 na CI (PR #1275):** `test-shop` **20–30 min → 15,7 min**; gate total
**23–31 → 22,5 min**. O gate cai pouco porque `test-shop` **continua sendo o caminho crítico** — ele
termina apenas 6,8 min antes do fim. `test-storefront` fica com `-n auto` (ganho dentro do ruído;
reverter custaria um PR para ganho zero) — **se aparecer teste intermitente do storefront em
paralelo, o primeiro suspeito é essa linha**.

**Qualidade observada no WP-1 (vale preservar em quem mexer depois):** `stamp_line_authorship`
recusa **inventar** `created_*` para linha que já existia sem carimbo — não fabrica história. E
`pos.py:2171` tem o comentário "Só copia: quem escreve é `pos_intent.stamp_line_authorship`", ou
seja, o segundo caminho **defere** ao escritor único em vez de duplicar a verdade.

**Nota da Frente 0 (vale para quem for medir):** o `--collect-only -n auto` **não** serve como prova
de coleta paralela — o xdist não sobe workers nesse modo. A prova é a execução completa. E o ganho
local medido foi `test-shop` 9:16 → 5:52; em `test-storefront` o ganho ficou dentro do ruído
(1:40 → 1:30, com uma rodada de 2:08), então **esse alvo está sob observação**: se a CI não mostrar
ganho, a linha dele deve ser revertida para não pagar risco de coleta paralela por nada.

**Achado colateral:** três testes de log (`test_otp_sms_comtele.py` ×2, `test_business_hours_grita.py`)
falhavam **no ponto de partida**, isolados, em série e em paralelo — passavam só quando um teste
anterior ligava a propagação do logger. Eram verdes na CI por **ordem de execução**, não por
correção. Corrigidos com o padrão que o repo já usa; nada foi marcado `skip` ou `xfail`.

---

## Por que este conjunto existe

Uma gaveta física, vários dispositivos. A custódia é do **terminal**, e o código **preserva de
propósito** vários dispositivos no mesmo terminal (`station_trust.py:308-310`). O dinheiro está
bem guardado (turno único, livro imutável, sangria com PIN gerencial, autoaprovação recusada).
O que falta é **rastro e visibilidade**: o sistema responsabiliza *pessoa + terminal*, nunca
*dispositivo*, então dois tablets no mesmo balcão são indistinguíveis na auditoria.

## ✅ Decisão tomada — D-004b (2026-09-29)

**Postura escolhida: (b) vários dispositivos no mesmo terminal, COM VISIBILIDADE.**
Registrado em `docs/coordination/DECISIONS.md` **D-007**. Consequência: WP-2 **avisa e pede
confirmação** no segundo provisionamento (não recusa), mostra "há N dispositivos neste balcão" e
"caixa já aberto" na tela do caixa, e lista/revoga dispositivos no Admin.

**Ordem definida pelo gestor:**
```
Frente 0  destravar CI (-n auto)      ← PRIMEIRO, corta 8-16 min de cada PR seguinte
WP-3      higiene                     ← trivial, valida o loop
WP-1      rastro por dispositivo      ← aditivo, zero migração
WP-4      X/Z terminal_ref            ← cirúrgico
WP-2      visibilidade                ← tela + projeção
WP-5      trava por dispositivo       ← depois, desenho próprio
```
**Uma sessão executora, sequencial.** Um branch por WP, mergeado antes de abrir o próximo.

---

## WP-1 · Rastro por dispositivo (P0 — pode começar já)

**Objetivo.** Tornar a auditoria de fraude verificável: registrar **qual dispositivo** praticou
cada ato, não só qual pessoa e qual terminal.

**Hoje.** O rastro é pessoa + terminal. `SignInEvent.station_ref` é o `Terminal.ref`
(`shopman/backstage/sign_in_audit.py:98-108`), **não** o id do `TrustedDevice`. O mesmo vale para
`SessionEvent` (`shopman/shop/models/session.py:493-516`), `cashman.Entry` e
`Order.data.pos.terminal_ref`.

**Arquivos.** `shopman/backstage/sign_in_audit.py` · `shopman/backstage/station_trust.py`
(o `TrustedDevice` já está em mãos em `_present_station_bindings`) ·
`shopman/shop/telemetry.py:237-276` · caminhos de dinheiro que gravam `Entry.payload` ·
`docs/reference/data-schemas.md` (**obrigatório**, é o inventário de chaves em JSONField).

**Mudança.**
1. Acrescentar a identidade do `TrustedDevice` ao payload já existente. **Zero migração** — os
   campos `data`/`payload` são JSONField projetados exatamente para isto (`CLAUDE.md`, "Core é
   Sagrado", regras 1 e 2). Documentar a chave nova em `data-schemas.md` **antes** de usá-la.
2. **Autoria por linha (depende de decisão do dono — ver D-008).** A tela do PDV mostra
   "Lançado por / Editado por" (`surfaces/pos-nuxt/app/components/PosCartPanel.vue:993-1017`) a
   partir de `meta.pos_authorship`, que **nenhum código escreve** (o único hit é a leitura, em
   `shopman/backstage/api/pos_concurrency.py:71`). Se a decisão for **implementar**: gravar a
   autoria no mesmo lugar onde a concorrência da comanda já é serializada, e cobrir com teste.
   Se for **remover**: tirar da tela e apagar o campo. **Não deixe como está** — prometer
   responsabilização inexistente é pior que não mostrar.

**Fora de escopo.** Não mudar o modelo de custódia. Não criar campo em modelo do Core. Não mexer
em `operations.py`.

**Prova de pronto.**
```
login com PIN em dois clientes distintos → os dois eventos carregam device ids DIFERENTES
um lançamento de caixa carrega o device de quem o fez
(se D-008 = implementar) duas linhas lançadas por operadores diferentes mostram autores diferentes
make test-framework  (verde)
```

**Risco.** Baixo. Aditivo, sem migração. É o item que mais fecha brecha por real gasto.

---

## WP-2 · Visibilidade do multi-dispositivo (P0 — depende de D-004b)

**Objetivo.** Ninguém descobre por acidente que dois dispositivos dividem a mesma gaveta.

**Hoje.** `StationProvisionView.post` (`shopman/backstage/api/operations.py:1093-1107`) lista
todos os terminais ativos **sem mostrar ocupação**. `TrustedDevice.last_used_at` **já é gravado a
cada requisição** (`packages/doorman/.../models/device_trust.py:208-212`) e nada lê.

**Arquivos.** `operations.py:1093-1107` · `shopman/backstage/station_trust.py` ·
`shopman/backstage/projections/pos.py:2025-2071` · tela em
`surfaces/operator-kit/app/components/OperatorStationSetup.vue`.

**Mudança.**
1. No provisionamento, se o terminal já tem vínculo ativo: **avisar e exigir confirmação**
   (`confirm=true`). **Não recusar** — D-007 = postura (b), vários dispositivos com visibilidade.
   A lista de terminais (`operations.py:1083-1091`) passa a trazer ocupação por terminal.
2. Na projeção do caixa, mostrar **"há N dispositivos neste balcão"** e **"caixa já aberto"**.
3. No Admin de terminais, listar e permitir revogar dispositivos
   (`TrustedDevice.active_for("station", ref)` — **já existe**, `packages/doorman/shopman/doorman/models/device_trust.py:215`;
   dados prontos, zero migração).
4. **Tratar o 409 do WP-4 na tela do X/Z.** O front só trata 401/403 como acesso negado, então o
   409 novo (`pos_terminal_mismatch`) cai como erro genérico. É pequeno e é o mesmo assunto
   (fronteira da estação), por isso mora aqui e não num PR próprio.

**Nota sobre dimensão:** se o item 3 fizer o diff crescer demais, separe-o e relate — a frente que
importa é a visibilidade para quem está no balcão (itens 1, 2 e 4).

**Prova de pronto.** Dois provisionamentos no mesmo ref → o segundo vê o aviso; a tela do caixa
mostra N=2; revogar um derruba só ele.

**Risco.** Médio-baixo. Só tela e projeção.

---

## WP-3 · Higiene: flag fantasma, promessa vazia e plano mentiroso (P0 — pode começar já)

Três itens triviais, todos verificados, todos do mesmo padrão "o registro não é a verdade":

1. **Remover `SHOPMAN_REQUIRE_ACTIVE_OPERATOR`** do spec — está em
   `.do/app.alpha-subdomains.yaml:252` e **nenhum `.py`/`.ts` lê**. Flag de segurança fantasma:
   quem lê o spec acredita numa trava que não existe.
2. **`docs/plans/WP-LOCK-01-*.md`** diz "não iniciado" e descreve `logout()` como vigente — mas o
   PR #1249 (merge `b9ee08f43`, commit `366c13b00`) já está no `main` e a trava é capability na
   sessão. **Corrigir o estado**, conforme `CLAUDE.md`.

> **Movido para o WP-1:** o item `pos_authorship` (a tela do PDV mostra "Lançado por / Editado por"
> a partir de um campo que ninguém escreve, `PosCartPanel.vue:993-1017`; único hit é a leitura em
> `pos_concurrency.py:71`). É **responsabilização**, o mesmo assunto do WP-1 — e depende de decisão
> do dono (implementar ou tirar da tela). Mantê-lo aqui faria o WP-3, que é higiene pura, depender
> de produto.

**Prova de pronto.** `grep` não encontra a flag no spec; o plano diz o estado real.

**Risco.** Trivial. É provavelmente o melhor primeiro PR do conjunto.

---

## WP-4 · X/Z não aceita terminal do query param (P1)

**Hoje.** A rota de X/Z aceita `terminal_ref` do **query param** sem validar contra a estação
(`operations.py:4942-4946` + `shopman/backstage/projections/cash_session.py:137-158`). Exige
`cashman.audit_shift`, mas **fura a regra que todas as mutações de dinheiro seguem** — a de que o
corpo/URL não escolhe a gaveta (`_terminal_do_pedido`, `operations.py:4632-4650`).

**Mudança.** Resolver o terminal pela **estação** (como o resto faz) e usar o param, se existir,
apenas para **conferir** — divergência = 409.

**Prova de pronto.** Teste: pedir X/Z de outro terminal pela URL é recusado; o da própria estação
continua funcionando.

**Risco.** Baixo. Fecha uma exceção isolada.

---

## WP-5 · Trava por dispositivo e ociosidade no servidor (P2 — maior, decidir depois)

**Hoje.** A trava por capability mora na **sessão**, não no dispositivo: cookie copiado herda a
trava. E a ociosidade que a dispara é medida **no navegador**
(`shopman/backstage/api/permissions.py:53`, `:113-118`; `operations.py:928-940`).

**Mudança.** Trava por dispositivo + ociosidade imposta pelo servidor. Encerrar o `WP-LOCK-01`
com estado honesto.

**Por que por último.** É o único com desenho real e o único que mexe em auth. Os quatro anteriores
já entregam a auditoria e a visibilidade.

---

## WP-6 · O dispositivo no rastro do DINHEIRO (P0 — criado em 2026-09-29)

**Por que existe.** O WP-1 pôs o dispositivo na trilha de **acesso** (`sign_in_audit`) e a autoria
por linha na comanda. Mas **não** pôs o dispositivo onde o dinheiro é lançado:
`cashman.Entry.payload` e `SessionEvent`. Esses caminhos passam pelo `operations.py`, que ficou
**fora do escopo do WP-1 por decisão minha**, para não colidir com WP-2 e WP-4. A lacuna é de
planejamento, não de execução.

**Por que é o item que mais importa.** A pergunta original do dono é sobre **fraude na gaveta**.
Sem o dispositivo no lançamento do caixa, continua verdade que *dois tablets no mesmo balcão são
indistinguíveis na trilha* — e o livro responsabiliza pessoa + terminal, nunca o aparelho.

**Mudança.** Gravar a identidade do `TrustedDevice` no payload dos movimentos de caixa e dos
eventos de sessão, pelos caminhos que já existem. **Zero migração** (JSONField). Documentar as
chaves em `docs/reference/data-schemas.md` antes de usar.

**Sequência.** Depois do **WP-4**, que também mexe em `operations.py`. **Nunca em paralelo** com
WP-2 ou WP-4 — é o mesmo arquivo quente.

**Prova de pronto.** Dois lançamentos de caixa feitos de dispositivos diferentes carregam device
ids diferentes; e o mesmo lançamento continua legível para quem não tem permissão de auditoria.

---

## Como distribuir (uma frente = um branch = um PR)

| Ordem | WP | Depende de | Paralelizável | Perfil |
|---|---|---|---|---|
| 1º | **WP-3** | — | sim | trivial, bom primeiro PR |
| 2º | **WP-1** | — | sim | aditivo, zero migração |
| 3º | **WP-4** | — | sim | cirúrgico |
| 4º | **WP-2** | **D-004b** | sim | tela + projeção |
| 5º | **WP-5** | WP-2 | não | auth, desenho próprio |

**Regra de convivência (do `AGENTS.md`):** antes de abrir cada frente,
`gh pr list` + `make inflight`; um branch por WP; `git add` só com arquivo nomeado; e
**nenhum turno termina com trabalho dormente** — PR aberto ou draft.

⚠️ **`operations.py` é arquivo quente.** WP-2 e WP-4 tocam o mesmo arquivo: **não rode os dois em
paralelo** sem combinar, ou o segundo vai conflitar. WP-1 e WP-3 não tocam `operations.py` e por
isso vão primeiro.

## Prompt pronto (esqueleto para qualquer um dos WPs)

```
Leia docs/plans/WP-POS-STATION-DEVICE-CUSTODY-2026-09-29.md e execute APENAS o WP-<N>.
Abra um worktree próprio e um branch (uma frente = um branch = um PR).

Contexto de evidência (não precisa reler inteiro): docs/reports/go-live-acceleration-20260929/14-*.md
e 15-*.md.

Regras: não toque em nada fora dos arquivos listados no WP; nada de migração em modelo do Core
(JSONField existe para isto); se gravar chave nova em JSONField, documente ANTES em
docs/reference/data-schemas.md.

Entregue: a mudança, a prova de pronto do WP rodada, e o número do PR.
Não pergunte se pode commitar/abrir PR — publique e relate.
```
