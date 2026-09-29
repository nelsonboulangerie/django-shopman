# 14 — A sessão do PDV em vários dispositivos: o que o sistema permite, impede e registra

**Pergunta do dono (operação real de padaria, um caixa físico, vários dispositivos):**
> "Hoje, a mesma sessão do PDV pode ser acessada em diferentes dispositivos, por diferentes
> operadores? Isso é bom, desde que a sincronia seja respeitada pelo sistema. Mas se a sessão
> for a mesma, a gaveta de dinheiro é uma só? Gostaria de sanar essa dúvida para que não haja
> brecha para má operação e fraudes."

**Árvore canônica:** `.dsh-worktrees/go-live-acceleration` (origin/main = `f0ffd02fd`, HEAD local
`99809de07`). Todo caminho abaixo é relativo a essa árvore. Nenhum comando git mutante foi
executado; o único arquivo escrito nesta árvore foi este relatório.

**Método:** leitura estática (sessão Django, `station_trust`, `permissions`, `operator_session`,
`pos_concurrency`, `cashman`, trilhas de auditoria, superfícies Nuxt) + **duas suítes de teste
pontuais** e **duas sondas de runtime** escritas em `/tmp` (nunca na árvore), rodadas com o banco
de teste do próprio pytest (`DJANGO_SETTINGS_MODULE=config.settings_test`; `DATABASE_URL` vazio ⇒
SQLite de `config/settings.py:484-494`). Nenhum `migrate`/`seed` em banco compartilhado.

**Relação com o relatório 15.** O `15-gaveta-custodia-multidispositivo.md` (escrito na mesma
árvore, 16:14) cobre a **custódia do dinheiro** (turno, livro, sangria, fechamento cego, hardware).
Este relatório 14 cobre a **sessão de operador** — a outra metade da mesma pergunta. Onde os dois
se tocam (um dispositivo por terminal, rastro do dispositivo), há remissão explícita e nenhuma
divergência de fato: as duas leituras chegam ao mesmo resultado por caminhos independentes.

---

## 1. Resposta direta

### (a) É verdade que a mesma sessão abre em vários dispositivos?

Depende de qual "sessão" se fala, e as duas leituras são verdadeiras:

[FATO] **Mesma PESSOA em dois dispositivos: sim, e é o caso normal.** Não existe "uma sessão por
pessoa". Cada dispositivo que se identifica por PIN/crachá/senha abre a **própria sessão Django**;
as duas ficam vivas em paralelo, com chaves de sessão diferentes. Provei em runtime: dois
navegadores, o mesmo PIN, o mesmo operador → `unlock` 200 nos dois, `GET /pos/` 200 nos dois, e
**nenhum dos dois derruba o outro** (sonda 2, seção 2.5). O Django troca a chave de sessão apenas
da requisição que está autenticando (`cycle_key`), e o único código do produto que apaga sessões
alheias é o "não fui eu" do dono da conta (seção 2.8) — `grep` por `sessions.models import
Session`/`Session.objects` em código de produto só encontra `shopman/backstage/services/sign_in_audit.py:463-492`
e o fluxo de cliente do storefront.

[FATO] **O MESMO COOKIE em dois dispositivos: também sim.** A sessão é um cookie portador: não há
vínculo com dispositivo, user-agent, IP ou estação. Não existe `SESSION_ENGINE` próprio (nenhum
override em `config/settings.py`; as únicas leituras de `settings.SESSION_ENGINE` são
`shopman/shop/services/access.py:212` e um teste) e nenhum middleware compara atributo da
requisição com o que foi gravado no login: o único uso de `HTTP_USER_AGENT` em código de produto é
**gravar** (`shopman/backstage/services/sign_in_audit.py:137-139`,
`packages/doorman/shopman/doorman/services/device_trust.py:114`), nunca **conferir**. Provei
copiando o cookie para um cliente novo: `GET /pos/` 200 e a tela responde com o operador do login
(sonda 1, seção 2.4). Em produção o cookie é emitido para `.boulangerie.com.br`
(`.do/app.alpha-subdomains.yaml:248-251`, via `OperatorSessionDomainMiddleware`,
`shopman/shop/middleware.py:117-171`), então **dentro do mesmo navegador** o mesmo cookie serve
pdv./gestor./kds./prod. — o login único da zona de operador é exatamente isso.

### (b) O sistema IMPEDE isso ou apenas não detecta?

[FATO] **Não impede nada do lado da sessão.** Não há limite de sessões simultâneas, nem expulsão da
sessão anterior, nem alerta "sua conta abriu em outro lugar" em tempo real. O que existe é
**detecção passiva e a posteriori**: cada identificação vira uma linha `SignInEvent` (usuário,
método, resultado, **estação**, IP, user-agent) e um aviso in-app para o dono da conta
(`shopman/backstage/services/sign_in_audit.py:144-163` e `:356-397`), com destaque para
"estação nunca usada por esta conta", fora de horário, rajada e "acertou logo depois de errar"
(`:229-302`). Na sonda 2, os dois destraves gravaram **duas** linhas com `station_ref='pdv-main'`
e **dois** avisos para a Ana — mas só o **primeiro** veio destacado (`unknown_station`); o segundo,
no mesmo terminal, veio sem destaque nenhum.

[FATO] **O que o sistema impede é outra coisa, e impede bem:** o *dispositivo não confiável* não
opera dinheiro, e o *corpo da requisição não escolhe a gaveta*. `_terminal_do_pedido`
(`shopman/backstage/api/operations.py:4632-4650`) resolve o terminal **só** pelo cookie de estação e
recusa com 409 `pos_station_required`/`pos_terminal_mismatch`; `resolve_terminal` falha fechado na
ambiguidade com 2+ terminais ativos (`shopman/backstage/services/pos.py:795-829`); a venda recusa
sem turno aberto naquela gaveta (`operations.py:5521-5540` e `:5559-5580`). Ou seja: a fronteira
defendida é **por ESTAÇÃO**, não **por sessão**.

### (c) Se a sessão for a mesma, a gaveta é uma só?

[FATO] **A gaveta nunca é "da sessão" — é do TERMINAL.** A custódia é um `cashman.Shift` com FK para
`Terminal` e `UniqueConstraint` de um turno aberto por terminal
(`packages/cashman/shopman/cashman/models/shift.py:48-53` e `:83-87`). Consequências exatas:

- **Dois dispositivos no MESMO terminal ref → uma gaveta, um turno, um livro.** Provei: o segundo
  dispositivo "abrindo o caixa" recebe **200 com o mesmo `shift_id`** (abertura é idempotente por
  gaveta, `shopman/backstage/services/pos.py:51-90`), e registra movimento no turno do primeiro
  (`drawer-open` 200) sem nenhum bloqueio nem aviso (sonda 1, seção 2.4).
- **Dois dispositivos com terminal refs DIFERENTES → duas gavetas de software**, ainda que exista
  uma gaveta física só. Não há constraint que impeça dois navegadores de se provisionarem para o
  mesmo ref, nem que impeça refs distintos coexistirem (`station_trust.py:295-366` preserva
  deliberadamente "os demais dispositivos do mesmo terminal").

### (c′) O que sobra de rastro para responsabilizar quem fez o quê

[FATO] A responsabilização hoje é **por PESSOA + por TERMINAL**, nunca **por DISPOSITIVO**:

| Pergunta | Quem responde | Traz dispositivo? |
|---|---|---|
| Quem lançou no livro-caixa | `cashman.Entry.operator` (+ `approved_by`) `entry.py:128-147` | não (só `shift.terminal`) |
| Qual gaveta | `Entry.shift.terminal` / `Order.data.pos.terminal_ref` | terminal, não dispositivo |
| Quem mexeu na comanda | `orderman.SessionEvent.actor` `session.py:508-516` | **não** |
| Quem finalizou a venda | `actor="pos:<user>"` + `operator_username` `operations.py:4953-4962` | não |
| Quem entrou, quando, de onde | `SignInEvent` (`station_ref`, `ip_address`, `data.user_agent`) | **terminal ref**, não dispositivo |
| Qual dispositivo físico | `TrustedDevice` (user_agent, ip, label, last_used_at), no Admin | **existe, mas não se liga a nenhum ato** |

[FATO] O ponto crítico: `SignInEvent.station_ref` recebe `station_trust.station_ref(request)`
(`sign_in_audit.py:98-108`), que é o **`Terminal.ref`** — não o id do `TrustedDevice`. Dois tablets
provisionados como `pdv-main` produzem linhas **indistinguíveis** na trilha. A única diferença
possível é o `user_agent` gravado em `data`, que separa "tablet" de "desktop" mas não dois
dispositivos do mesmo modelo.

---

## 2. Fluxo passo a passo, com evidência

### 2.1 Como o operador se autentica no PDV — três portas, uma identidade

| Porta | View | Credencial | Gate |
|---|---|---|---|
| Senha no app | `OperatorLoginView` `operations.py:772-826` | usuário + senha (staff) | `AllowAny` + rate-limit 30/min por IP e 5/min por username (`:770-771`) |
| PIN / crachá | `OperatorUnlockView` `operations.py:843-925` | `operator_id`+`pin` **ou** `badge` | `IsTrustedStation` — a estação, não a sessão |
| Admin | `django.contrib.admin` `LoginView` | senha (+2FA) | fora da zona de operador (`shop/middleware.py:158-169`) |

[FATO] As três terminam em `login()` **de verdade**: quem provou a identidade **vira** a sessão, e
`request.user` é o operador (`operations.py:922` com `backend=MODEL_BACKEND` explícito;
`shopman/backstage/api/permissions.py:127-151`). Não existe "conta do dispositivo" nem "operador
ativo" guardado ao lado — esse desenho de duas identidades foi removido em 21/08/2026
(`permissions.py:1-35`, `station_trust.py:11-15`).

[FATO] `operator_session.start(request)` marca a sessão (`SESSION_MARKER`) e dá prazo de **7 dias
sem uso**, renovado no máximo 1×/dia pelo uso
(`shopman/backstage/services/operator_session.py:34-60` e `:111-127`;
`config/settings.py:2065-2066`). A sessão do Admin tem regra própria (14 dias,
`config/settings.py:2074-2075`).

### 2.2 A sessão NÃO é do dispositivo

[FATO] O cookie de sessão é **um só para a zona de operador** e é emitido no domínio-pai
(`.boulangerie.com.br`) pelo `OperatorSessionDomainMiddleware`
(`shopman/shop/middleware.py:117-171`; valor de alpha em `.do/app.alpha-subdomains.yaml:248-251`).
O middleware poupa explicitamente o host do Admin, que é host-only (`middleware.py:158-169`).

[FATO] Nada no caminho de autenticação liga a sessão ao dispositivo: não há `Session` própria do
projeto (Django default, DB-backed), não há `SESSION_COOKIE` amarrado a IP/UA, não há middleware
comparando. `grep -rn "HTTP_USER_AGENT"` em `shopman/`, `config/` e `packages/` (fora de
`__pycache__` e `/tests/`) devolve **4 ocorrências, todas de gravação ou rótulo**: 
`sign_in_audit.py:137`, `doorman/services/device_trust.py:114`, `shop/services/access.py:160`,
`shop/services/customer_sign_in.py:57`.

[INFERÊNCIA] É por isso que "sessão compartilhada" no sentido estrito (o mesmo cookie em duas
máquinas) **funciona** e **não é detectado**: nada no servidor tem como notar a troca de máquina,
porque nada foi gravado sobre a máquina quando a sessão nasceu.

### 2.3 O dispositivo TEM identidade própria — e é ela que decide a gaveta

1. **Provisionamento.** Quem tem `cashman.manage_operators` abre a tela no dispositivo e escolhe o
   balcão (`StationProvisionView`, `operations.py:1058-1115`; `PROVISION_PERM` em
   `station_trust.py:41`). A lista de terminais oferecida é "todos os ativos"
   (`operations.py:1083-1091`) — **sem mostrar ocupação e sem recusar um ref já usado por outro
   dispositivo**.
2. **Confiança.** Grava um `TrustedDevice` com `subject_type="station"`, `subject_id=<ref>` e
   `token_hash` HMAC (`packages/doorman/shopman/doorman/models/device_trust.py:74-109`), TTL de 30
   dias (`doorman/conf.py:118-125`), revogável no Admin (`doorman/contrib/admin_unfold/admin.py:280-300`).
   [FATO] A **única** unicidade é `token_hash` (`:103-109`); não existe `UniqueConstraint` em
   `(subject_type, subject_id)` — só índices de busca (`:132-140`). Dois dispositivos para o mesmo
   terminal são estado válido.
3. **Resolução por requisição.** `station_ref(request)` só devolve ref quando há **exatamente um**
   vínculo válido apresentado por aquele navegador; com dois, devolve `""`
   (`station_trust.py:115-126`) — e aí a escrita de dinheiro falha fechado.
4. **Gate do dinheiro.** `_terminal_do_pedido` (`operations.py:4632-4650`) — o corpo **confirma**,
   nunca escolhe. Coberto por teste: `test_body_cannot_select_a_different_station`
   (`shopman/backstage/tests/test_pos_station_drawer_boundary.py:37-41`, **3 passed** na minha
   execução, seção 2.10).

### 2.4 Sonda 1 — dois navegadores, a mesma pessoa, o MESMO terminal

`/tmp/dsh_probe_sessao_multidispositivo.py` (pytest + `django.test.Client`; `bind_station(client, "pdv-main")`
nos dois). Saída literal:

```
[probe] A status 200 B status 200
[probe] session_key A wuarmhyk70bbqsk7ejmrpxmf2qu4qyje
[probe] session_key B jrzai0nre3abrxwllvv7xz514rwbdaxb
[probe] mesma chave? False
[probe] A abre caixa: 200 {'ok': True, 'shift_id': 1, 'terminal_ref': 'pdv-main'}
[probe] B abre caixa no MESMO terminal: 200 {'ok': True, 'shift_id': 1, 'terminal_ref': 'pdv-main'}
[probe] B registra abertura de gaveta do turno de A: 200 {'ok': True}
[probe] pos(A).terminal_ref: pdv-main
[probe] pos(B).terminal_ref: pdv-main
[probe] A trava: 200 {'ok': True}
[probe] A depois da trava: 403
[probe] B depois da trava de A: 200
[probe] cookie de sessão copiado para outro cliente: 200
[probe] quem o servidor diz que está operando: {'id': 1, 'username': 'bia', 'name': 'bia'}
[probe] A trava: 200
[probe] A (dono do login): 403
[probe] C (só com o cookie copiado): 403
```

Leitura [FATO]: (i) duas sessões vivas do mesmo operador, sem aviso e sem exclusão mútua; (ii) **um
único turno** para os dois — o segundo "abrir caixa" devolve o do primeiro; (iii) o segundo
dispositivo **lança movimento na gaveta do primeiro** (200); (iv) **travar é por sessão**: A fica
403 e B continua 200 (a trava nova, PR #1249, seção 2.6); (v) o cliente que **só recebeu o cookie
copiado** opera normalmente (200) e **herda a trava** de A (403) — porque a trava mora na sessão,
não no dispositivo.

### 2.5 Sonda 2 — PIN real em dois dispositivos, e o que a trilha grava

`/tmp/dsh_probe2_pin_dois_dispositivos.py` (dois `Client`, `trust_station` nos dois, `PinCredential.set_for(op, "1234")`):

```
[probe2] unlock A: 200 unlock B: 200
[probe2] chave A: 681nxk1g1fczol49ocnxd012f45hcecc
[probe2] chave B: e4wcgw7mcdoee0ajdkuk9zuh3or1zbik
[probe2] A e B ainda leem o PDV: 200 200
[probe2] SignInEvent gravados: 2
   - ana pin success estacao= 'pdv-main' ip= 127.0.0.1 ua=  anomalias= ['unknown_station']
   - ana pin success estacao= 'pdv-main' ip= 127.0.0.1 ua= anomalias= None
[probe2] avisos criados para o dono da conta: 2
```

[FATO] O caminho real (PIN, não `force_login`) confirma: dois dispositivos, duas sessões, ambas
vivas. E mostra o limite do alerta: **a estação é o terminal**, então o segundo acesso "no mesmo
lugar" não é destacado; o que o destaque pega é "conta nova nesta estação", não "mais um
dispositivo nesta conta".

### 2.6 A trava da estação: o que ela é hoje (PR #1249)

[FATO] O branch `codex/p1-station-lock-20260929` **já está no main**: merge `b9ee08f43`
(2026-09-29), commit `366c13b00` "fix(backstage): scope station lock to operator capability"
(`git merge-base --is-ancestor b9ee08f43 HEAD` → sim; `git show --stat` lista
`operations.py`, `permissions.py`, `operator_session.py`, `useOperatorLock.ts`).

[FATO] O efeito: `OperatorLockView` (`operations.py:928-940`) passou a **só** gravar a capability na
sessão (`operator_session.lock_capability`, `:79-86`), e a recusa virou 403 com código
`station_locked` (`permissions.py:53` e `:113-118`), em vez de `logout()`. Comprovei em runtime:
travar em A → A 403, B 200 (sonda 1).

[FATO] **O documento do plano está desatualizado em relação ao main**:
`docs/plans/WP-LOCK-01-estacao-travada-nao-e-sessao-encerrada.md` diz "Status: Aprovado pelo dono
como WP próprio (17/09/2026), **não iniciado**" e descreve `logout()` como comportamento vigente —
o main já entregou a separação "estação travada ≠ sessão encerrada". Quem ler o plano hoje decide
com informação errada. (O WP-LOCK-01 continua valendo para o que **não** foi feito: "onde mora
'travada'" como estado por dispositivo — hoje mora na sessão, ver brecha G3.)

[FATO] A trava é **acionada pelo cliente**: o auto-lock do PDV
(`surfaces/pos-nuxt/app/composables/usePosAutoLock.ts:57-82`, ligado em
`surfaces/pos-nuxt/app/components/PosOperatorShell.vue:63-68`) chama
`POST /api/v1/backstage/operator/lock/` quando nenhum app de operador foi tocado por
`auto_lock_seconds` (default **60**, `shopman/backstage/projections/pos.py:613`, configurável por
terminal em `Terminal.metadata`), com o relógio de dispositivo compartilhado entre apps
(`surfaces/operator-kit/app/utils/deviceActivity.ts`), sem disparar com a aba oculta e sem travar
com pagamento em curso (`holdWhen`). O servidor **respeita** a trava uma vez gravada — mas o
gatilho por ociosidade vive no navegador.

### 2.7 Concorrência: o que `pos_concurrency` serializa

[FATO] `shopman/backstage/api/pos_concurrency.py:13-83` (`tab_command`): com `expected_revision`
obrigatório (422 sem ele), abre `select_for_update()` sobre as linhas de `orderman.Session` da(s)
comanda(s) envolvidas, compara a revisão e recusa com **409 `tab_revision_conflict`**
("Esta comanda mudou em outro dispositivo…"); ao sucesso devolve `revision` e `line_authors` e
emite SSE `backstage-tabs-update`.

[FATO] **O que ele serializa é a COMANDA, não o dispositivo, nem o terminal, nem o operador.** O
lock é `session_key__in=keys` sobre `channel_ref=pdv`
(`pos_concurrency.py:37-44`). Está aplicado a 6 views: `POSTabSaveView` (`operations.py:5049`),
`POSTabClearView` (`:5087`), `POSTabMoveLinesView` (`:5114`), `POSTabRenameView` (`:5147`),
`POSTabFireView` (`:5170`), `POSTabUnfireView` (`:5201`). O fechamento repete a checagem sob
lock (`shopman/shop/services/pos.py:390-397`). A tela tem o banner "A comanda mudou em outro
dispositivo" e o botão "Descartar minhas alterações e atualizar"
(`surfaces/pos-nuxt/app/pages/index.vue:992-1003`).

[FATO] Esse é o mecanismo que responde ao "desde que a sincronia seja respeitada": duas telas
podem editar a mesma comanda, mas **a segunda gravação com revisão velha é recusada**, e ninguém
sobrescreve ninguém em silêncio. Vale para comanda; **não** há CAS equivalente para dinheiro
(sangria/suprimento/fechamento) — o que existe ali é idempotência por `client_request_id`
(`CASH_IDEMPOTENCY_SCOPE`, `operations.py:4101-4180`), que protege contra replay, não contra
duas pessoas agindo.

### 2.8 "Não fui eu": o único botão que derruba sessões

[FATO] `sign_in_audit.revoke_access` (`shopman/backstage/services/sign_in_audit.py:445-520`) varre a
tabela de sessões, apaga todas as do usuário **exceto a de quem pediu**, mata o crachá e registra
um `SignInEvent` de resultado `revoked`. Só o dono da conta pode fazê-lo (`:470-472`), e o PIN
continua valendo (`:517-519`). Dois gatilhos: "não reconheço este acesso" e "perdi o crachá"
(`OperatorBadgeLostView`, `operations.py:943-1016`).

[FATO] É a única defesa ativa contra "minha sessão está aberta em algum dispositivo que não é meu".
Depende de a pessoa (i) receber o aviso e (ii) agir. O aviso aponta para `/account/sign-ins`
(`sign_in_audit.py:353`), caminho que **não existe como página** em nenhum app Nuxt
(`grep "sign-ins"` em `surfaces/` só encontra o tipo e o composable; a lista existe dentro do
sino de notificações, `surfaces/operator-kit/app/components/NotificationBell.vue:25-150`, servida por
`GET /api/v1/backstage/sign-ins/`, `shopman/backstage/api/urls.py:669`).

### 2.9 Auditoria: o que cada registro sabe (e não sabe)

[FATO] `SignInEvent` (`shopman/backstage/models/sign_in.py:84`) é o registro mais completo: usuário,
username digitado, método, resultado, `station_ref`, `ip_address` (resolvido pela direita do
XFF, `sign_in_audit.py:73-95`) e `data{user_agent, path, anomalies, reason, sessions_revoked…}`.
**`station_ref` = ref do Terminal**, não id do dispositivo (`:98-108`).

[FATO] `orderman.SessionEvent` (`packages/orderman/shopman/orderman/models/session.py:493-516`):
`session_key, seq, type, actor, payload` — **sem campo de dispositivo**. É o que grava
`line_added`/`qty_changed`/`line_removed` com o nome de quem fez
(`shopman/shop/services/pos.py:280-298`), `sale_committed`, `tab_cleared`, `tab_renamed`
(`pos.py:441`, `:1496`, `:1580`).

[FATO] `cashman.Entry` (`packages/cashman/shopman/cashman/models/entry.py:122-175`): `shift`
(→ `terminal`), `operator`, `approved_by`, `kind`, `amount_q`, `payload`, append-only. Sem
dispositivo.

[FATO] `Order.data.pos` carrega `terminal_ref` (`docs/reference/data-schemas.md:247`,
escrito em `shopman/shop/services/pos.py:2254-2256`) e `tenders[].terminal_ref`
(`data-schemas.md:1586`); `session.data.pos_operator` guarda o username
(`data-schemas.md:44`). Também sem dispositivo.

[FATO] Telemetria operacional (`shopman/backstage/api/telemetry.py:237-276`) grava `actor_id`,
operação, status, `request_id` e digests de idempotência/revisão — **nenhuma menção a estação ou
dispositivo** (`grep "station|device|terminal"` no arquivo: zero linhas).

[FATO — ausência] **Autoria por linha é um stub.** A tela do PDV mostra "Lançado por / Editado por"
(`surfaces/pos-nuxt/app/components/PosCartPanel.vue:993-1017`) a partir de `item.authorship`, e
`pos_concurrency.py:70-72` devolve `line_authors` lendo `item.meta.pos_authorship`. **Nada escreve
`pos_authorship`**: `grep -rn "pos_auth"` na árvore inteira devolve só a linha que **lê**
(`pos_concurrency.py:71`), e `build_session_ops` (`shop/services/pos.py:2114-2168`) só grava
`meta.notes`, `meta.manual_discount` e `meta.weighed.by`. Ou seja: hoje o campo chega sempre
vazio, e a única autoria por linha que sobrevive é a da **venda por peso** (`weighed.by`).
O que existe de verdade é o evento por linha no `SessionEvent` (com o `actor`, sem dispositivo).

[FATO] No balcão, a pergunta "de quem é esta linha da comanda" tem resposta pelo **evento**
(`line_added`/`qty_changed` com actor), não pelo item.

### 2.10 Testes que rodei

```
$ cd .dsh-worktrees/go-live-acceleration && PYTHONPATH=<worktree>:<packages/*> .venv/bin/python -m pytest \
    shopman/backstage/tests/test_pos_station_drawer_boundary.py -q
3 passed in 18.85s
```
(cobre: a estação da requisição escolhe a gaveta e o `cash_shift_id` forjado no corpo é descartado;
o corpo não pode escolher outra estação; estação ambígua/revogada/inativa não escolhe gaveta.)

```
$ ... pytest -c pyproject.toml -s -q /tmp/dsh_probe_sessao_multidispositivo.py
2 passed in 19.29s      # saída na seção 2.4
$ ... pytest -c pyproject.toml -s -q /tmp/dsh_probe2_pin_dois_dispositivos.py
1 passed in 15.08s      # saída na seção 2.5
```

---

## 3. O que impede má operação ou fraude HOJE

[FATO] **1. O corpo da requisição não escolhe a gaveta.** `_terminal_do_pedido`
(`operations.py:4632-4650`): ref vindo do cookie de estação; divergência com o que o corpo afirma →
409 `pos_terminal_mismatch`; sem estação → 409 `pos_station_required`. Toda mutação de dinheiro
passa por ele (abrir/fechar caixa, sangria, suprimento, gaveta, troco, devolução, `cash_shift_id`
injetado pelo servidor em `operations.py:520-531`).

[FATO] **2. Vender exige turno aberto nesta estação.** `POSReviewSaleView` (`operations.py:5521`)
e `POSCloseSaleView` (`:5559`) recusam com 409 `cash_shift_required` antes de qualquer commit.

[FATO] **3. Uma gaveta, um turno.** `UniqueConstraint` no banco
(`cashman/models/shift.py:83-87`) — impossível abrir dois caixas no mesmo terminal.

[FATO] **4. Ambiguidade falha fechado.** `resolve_terminal(..., strict=True)` levanta
`POSTerminalAmbiguous` (409) com 2+ terminais ativos e nenhum ref (`services/pos.py:795-829`).

[FATO] **5. Fechamento cego.** O terminal nunca vê esperado/diferença
(`operations.py:500-517`, que devolve só `blind_closing_amount_q`; `services/pos.py:713-750`; projeção `projections/pos.py:2025-2033`), e a
apuração exige `cashman.audit_shift` (`operations.py:4939-4947`).

[FATO] **6. Sangria exige segunda assinatura (PIN de gerente), sem limiar**
(`services/pos.py:113-152`; `Entry.APPROVAL_REQUIRED`, `entry.py:116-120`), e o livro é append-only
na aplicação (`entry.py:28-38`, `:239-247`).

[FATO] **7. Cada ato no livro leva o nome de quem fez** (`Entry.operator`) — o turno não tem dono,
o lançamento tem (`shift.py:1-15`).

[FATO] **8. Sincronia de comanda por CAS** (`pos_concurrency`, seção 2.7): a segunda tela com
revisão velha é recusada com 409 e mensagem própria.

[FATO] **9. Todo acesso é registrado e notificado** (`SignInEvent` + `UserNotification`), com
destaques; e existe o "não fui eu" que derruba as sessões da conta (seção 2.8).

[FATO] **10. Rate-limit no login de senha** (30/min por IP, 5/min por conta) e lockout de PIN
(`operations.py:770-771`; `operator_service.verify_operator_pin`).

[FATO] **11. Uma superfície autônoma (totem) só age na Produção.** A trava
`station_trust.is_production_surface` (falha fechado) existe porque o cookie de estação vale no
domínio inteiro (`station_trust.py:56-99` e `:270-292`).

---

## 4. Brechas concretas

### G1 — Dois dispositivos no mesmo terminal dividem a custódia e ninguém é avisado [FATO]
O provisionamento não checa ocupação (`operations.py:1083-1091`) e `provision` preserva
deliberadamente os outros dispositivos do mesmo terminal (`station_trust.py:308-310`). Prova em
runtime: o segundo dispositivo abre "o caixa" e recebe 200 com o **mesmo** `shift_id`, e lança
movimento no turno do primeiro (sonda 1). Nada na tela diz "este caixa já está aberto por outra
pessoa/em outro dispositivo" — o terceiro estado `terminal_occupied` foi removido de propósito
quando a custódia deixou de ser da pessoa (`projections/pos.py:2025-2033`).

### G2 — O rastro não distingue DISPOSITIVO: `station_ref` é o terminal [FATO]
`SignInEvent.station_ref` (`sign_in_audit.py:98-108`) e `Entry.shift.terminal` respondem "de qual
balcão", e dois tablets com o mesmo ref são **a mesma resposta**. O `TrustedDevice` — que tem
`user_agent`, `ip_address`, `label`, `last_used_at` — não é referenciado por nenhum evento,
lançamento ou pedido (`grep TrustedDevice` fora de testes: `station_trust`, admin do doorman e
fluxos de cliente/menuboard). **Não há como responsabilizar "o tablet do fundo"**, só "a pessoa" e
"o balcão".

### G3 — A trava de estação mora na SESSÃO, não no dispositivo [FATO]
`LOCKED_CAPABILITIES_KEY` é chave de `request.session`
(`operator_session.py:37-40`, `:79-104`). Consequências provadas na sonda 1: (i) travar em A não
trava B (cada sessão tem a sua); (ii) **quem tem o cookie** de A fica travado junto e destrava
junto — ou seja, a trava não protege contra "o mesmo cookie em outra máquina", só contra "esta
sessão continua operando". O WP-LOCK-01 lista exatamente essa pergunta em aberto ("onde mora
'travada'") e continua válido para essa parte.

### G4 — A ociosidade que dispara a trava é medida no NAVEGADOR [FATO]
`usePosAutoLock` decide no cliente e chama o POST
(`surfaces/pos-nuxt/app/composables/usePosAutoLock.ts:57-82`). Um cliente que não chame o endpoint
(deixando a aba aberta, script, cliente HTTP) **nunca trava** — a sessão segue válida por até 7
dias sem uso (`config/settings.py:2065-2066`). O servidor não tem gatilho próprio de ociosidade
para o PDV.

### G5 — Não há limite de sessões simultâneas nem expulsão [FATO de ausência]
Duas sessões da mesma pessoa coexistem indefinidamente (sondas 1 e 2). Não há "sessão única", nem
"derrubar a anterior", nem tela de "onde minha conta está aberta" (o `TrustedDevice` do
**cliente** tem isso em `shop/services/devices.py`; o do **operador** não tem).

### G6 — O alerta de "estação nova" não cobre o segundo dispositivo na MESMA estação [FATO]
A anomalia `unknown_station` pergunta "esta conta já usou esta estação?" por `station_ref`
(`sign_in_audit.py:253-264`). Como a chave é o terminal, o segundo tablet em `pdv-main` **não**
gera destaque (sonda 2: primeiro acesso destacado, segundo não).

### G7 — Autoria por linha da comanda é tela sem dado [FATO — ausência de escritor]
`pos_authorship` só é lido (`pos_concurrency.py:71`; `PosCartPanel.vue:993-1017`); nenhum caminho
grava. Quem quiser saber "quem lançou o item X" tem de ir ao `SessionEvent` (`line_added` com
`actor`) — e ali também não há dispositivo.

### G8 — Um flag de segurança fantasma no deploy [FATO]
`.do/app.alpha-subdomains.yaml:252-254` define `SHOPMAN_REQUIRE_ACTIVE_OPERATOR=true`, e **nenhum
arquivo .py/.ts do produto lê essa variável** (`grep` na árvore: só o spec e documentos). É resíduo
do modelo de "operador ativo" aposentado. Já apontado como P2-8 em
`docs/reports/adversarial-audit-2026-09-01/01-security.md:532-541`; segue no spec. Risco: quem
auditar a configuração lê "há um portão ligado" e não há.

### G9 — Documento de plano desatualizado pode induzir a decisão errada [FATO]
`docs/plans/WP-LOCK-01-…md` afirma "não iniciado" e descreve `logout()` como vigente, mas o main já
tem a trava por capability (PR #1249). Ver seção 2.6.

---

## 5. Recomendações ordenadas

**P0 — antes do go-live (barato, alto impacto, sem migração de risco)**

1. **Batizar o dispositivo no rastro.** Gravar o id do `TrustedDevice` (ou um `device_ref` curto) em
   `SignInEvent` e nos eventos de comanda, e exibir "tablet/desktop" na trilha do Admin.
   `SignInEvent` já tem `data` JSON (`sign_in_audit.py:135-152`) e `station_trust` já tem o
   `TrustedDevice` em mãos ao resolver o cookie — a mudança é ler o `pk` junto do `subject_id`
   em `_present_station_bindings` (`station_trust.py:142-167`). Isso fecha G2 e é o que torna
   qualquer auditoria de fraude verificável.
2. **Avisar quando o MESMO terminal ganha um segundo dispositivo.** No `StationProvisionView.post`
   (`operations.py:1093-1107`), listar quantos `TrustedDevice` ativos existem para aquele ref e
   pedir confirmação explícita ("o balcão pdv-main já responde em 2 dispositivos; confirmar?").
   Não precisa bloquear — precisa **não ser silencioso** (fecha G1 no que ele tem de pior).
3. **Mostrar "este caixa está aberto e há N dispositivos neste balcão" na projeção do caixa.**
   `POSCashRuntimeProjection` (`projections/pos.py:2025-2071`) hoje só diz aberto/fechado; o
   operador do segundo dispositivo merece ver que está lançando na gaveta de outro balcão.
4. **Remover `SHOPMAN_REQUIRE_ACTIVE_OPERATOR` do spec** (`.do/app.alpha-subdomains.yaml:252`) ou
   comentar por que morreu (fecha G8).

**P1 — primeira semana depois do go-live**

5. **Recusar/limitar segunda sessão ativa do mesmo operador para a MESMA superfície**, ou ao menos
   registrar e exibir "sua conta está aberta em N dispositivos" no sino (fecha G5). Como a chave de
   sessão já é varrida em `revoke_access` (`sign_in_audit.py:479-492`), o inventário existe.
6. **Ligar a leitura de linha por operador** — decidir o dono do `pos_authorship` (o
   `build_session_ops`, `shop/services/pos.py:2114-2168`, é o lugar) **ou** remover a linha da tela
   do PDV (`PosCartPanel.vue:993-1017`) para não exibir um campo que nunca vem (fecha G7 — hoje a
   tela promete um dado que o servidor não manda).
7. **Fechar o WP-LOCK-01 de verdade**: mover "travada" para estado do dispositivo
   (provável `Terminal.metadata` + registro com quem travou e quando) e fazer o servidor **impor**
   ociosidade, não só aceitar o POST do navegador (fecha G3 e G4). Decidir também a pergunta 4 do
   próprio WP ("sou outra pessoa agora" sem matar a sessão).
8. **Atualizar/carimbar o WP-LOCK-01** como parcialmente executado (fecha G9).

**P2 — estrutural**

9. **Uma sessão de caixa por terminal, com posse explícita opcional**: quando a loja tiver mais de
   um balcão, decidir se a segunda sessão no mesmo terminal entra como "apoio" (com aviso) ou é
   recusada. Hoje é "entra e ninguém vê".
10. **Rastro unificado por dispositivo**: um `device_ref` propagado nos eventos (Session/Order),
    nos `Entry` e na telemetria (`telemetry.py:258-276`), para que a resposta a "quem fez isso" não
    dependa de reconstituir IP/UA depois.

---

## 6. O que NÃO consegui verificar

- **[NÃO VERIFICADO] Comportamento em produção real.** Todas as provas de runtime foram em SQLite de
  teste (`DATABASE_URL` vazio neste ambiente). `select_for_update` é no-op em SQLite; a serialização
  de `pos_concurrency` sob Postgres concorrente real não foi exercitada aqui (o desenho de lock
  está lido no código, não medido). Rodar `make test-runtime` (Postgres + Redis) cobre isso.
- **[NÃO VERIFICADO] Quantos `TrustedDevice` de estação existem hoje no alpha, e se algum terminal
  já tem dois dispositivos.** Não consultei banco de ambiente vivo. Se houver, G1 já está ativo em
  campo; se não houver, G1 é risco de configuração.
- **[NÃO VERIFICADO] Se a loja tem (ou terá) mais de uma gaveta física.** O código suporta N
  terminais; a operação descrita pelo dono é uma gaveta. Não afirmei nada sobre o hardware.
- **[NÃO VERIFICADO] Se o token do agente local (`Terminal.metadata.hardware.device_agent.token`)
  está configurado no alpha e se o tablet alcança a loopback.** Não toquei em configuração viva.
- **[NÃO VERIFICADO] Efeito de `auto_lock_seconds` real no balcão** (se o valor configurado é 60 ou
  outro). Lido o default no código (`projections/pos.py:613`), não o dado.
- **[NÃO VERIFICADO] A Superfície de notificação `/account/sign-ins`**: confirmei que a rota não
  existe em `surfaces/*/app/pages`, mas **não** verifiquei se algum app a resolve por outro caminho
  (proxy/redirect) ou se a notificação cai em 404 na mão do operador.
- **Fora do escopo deste relatório:** a mecânica do livro-caixa (sangria, contagem cega, fechamento
  do dia, hardware da gaveta) está no `15-gaveta-custodia-multidispositivo.md`, que li por cima
  para não contradizer; não reproduzi as sondas dele.

---

## Anexo — comandos de reprodução

```bash
WT=/Users/pablovalentini/Dev/Claude/django-shopman/.dsh-worktrees/go-live-acceleration
PY=/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python
PKGS=$(ls -d $WT/packages/*/ | tr '\n' ':')

# 1. guarda da fronteira estação→gaveta
cd $WT && PYTHONPATH="$WT:$PKGS" $PY -m pytest shopman/backstage/tests/test_pos_station_drawer_boundary.py -q

# 2. sondas de sessão multi-dispositivo (arquivos em /tmp, fora da árvore)
cd $WT && PYTHONPATH="$WT:$PKGS" $PY -m pytest -c $WT/pyproject.toml -p no:cacheprovider -s -q \
  /tmp/dsh_probe_sessao_multidispositivo.py /tmp/dsh_probe2_pin_dois_dispositivos.py

# 3. o merge da trava por capability está no main?
git -C $WT merge-base --is-ancestor b9ee08f43 HEAD && echo "sim"
git -C $WT show --stat --format="%h %ad %s" --date=short 366c13b00
```
