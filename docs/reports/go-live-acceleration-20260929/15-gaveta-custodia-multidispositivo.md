# 15 — A gaveta e a custódia do dinheiro com vários dispositivos

**Pergunta do dono (operação real de padaria, um caixa físico, vários dispositivos):**
> "Hoje, a mesma sessão do PDV pode ser acessada em diferentes dispositivos, por diferentes
> operadores? Isso é bom, desde que a sincronia seja respeitada pelo sistema. Mas se a sessão
> for a mesma, a gaveta de dinheiro é uma só? Gostaria de sanar essa dúvida para que não haja
> brecha para má operação e fraudes."

**Árvore canônica:** `.dsh-worktrees/go-live-acceleration` (origin/main = `f0ffd02fd`).
Todo caminho abaixo é relativo a essa árvore. Nenhum comando git mutante foi executado; o único
arquivo escrito foi este relatório.

**Método:** leitura estática de `packages/cashman` (completo no que importa: models e services),
`shopman/backstage/{services,api,projections,station_trust.py}`, `shopman/shop/services/{pos,payment,operator_orders}.py`;
duas suítes de teste pontuais e uma sonda de runtime em sqlite de memória (nenhum `migrate`/`seed`
em banco compartilhado).

---

## 1. Resposta direta

**(a) A gaveta é uma só por quê?**

[FATO] **Por TERMINAL** — e não por sessão nem por operador. A custódia é um `Shift` com FK para
`Terminal` e uma `UniqueConstraint` que garante **um turno aberto por terminal**
(`packages/cashman/shopman/cashman/models/shift.py:48-53` e `:83-87`; docstring `:3-5`: "A custódia
é do terminal, não da pessoa"). O serviço só sabe responder "qual é o turno desta gaveta":
`open_shift_for_terminal(terminal)` (`packages/cashman/shopman/cashman/services/shifts.py:22-33`,
com a nota explícita de que **não existe** `open_shift_for(operator)`).

[FATO] O terminal, por sua vez, é **uma escolha de provisionamento do dispositivo**: a rota
`/api/v1/backstage/operator/station/` grava, no navegador daquele balcão, um cookie de estação que
carrega o `Terminal.ref` (`shopman/backstage/api/operations.py:1093-1107` chamando
`station_trust.provision`, `shopman/backstage/station_trust.py:295-366`).

[FATO] Portanto a resposta é: **a gaveta é uma só por TERMINAL, e N dispositivos podem ser
provisionados como o MESMO terminal.** Não há constraint (nem de banco, nem de serviço, nem de tela)
que impeça dois dispositivos de apontarem para `pdv-main`. Pior: o próprio código **preserva** isso
de propósito — `station_trust.provision` revoga apenas os vínculos apresentados pela requisição
atual e diz, em comentário: "os demais dispositivos do mesmo terminal continuam ativos"
(`shopman/backstage/station_trust.py:308-310`).

**(b) Com a sessão compartilhada, dois dispositivos operam a MESMA gaveta?**

[FATO] **Sim, em software, integralmente.** Se os dois dispositivos têm o mesmo `Terminal.ref`, os
dois resolvem para o mesmo `Shift` aberto, lançam no mesmo livro e veem a mesma leitura X. Provei
isso em runtime (sonda na seção 2.6): dois `TrustedDevice` de estação para o mesmo ref coexistem,
ambos os tokens verificam, `open_shift_for_terminal` devolve o mesmo turno, os dois operadores
gravam linhas no mesmo livro, e o segundo fechamento é recusado.

[INFERÊNCIA] **Em hardware, não necessariamente a mesma gaveta física.** Quem chuta a gaveta é o
**agente local na loopback de cada máquina** (`shopman/backstage/services/pos_hardware.py:28`
`DEFAULT_AGENT_URL = "http://127.0.0.1:47811"`), e o endereço + token do agente vêm do
`Terminal.metadata["hardware"]` (`pos_hardware.py:51-71` e `:140-158`) — ou seja, **o mesmo token
para os dois dispositivos**, mas cada navegador fala com o agente da SUA máquina. O payload que a
tela recebe é montado a partir do terminal, não do dispositivo (`shopman/backstage/projections/pos.py:616-617`).
Resultado possível: dois dispositivos que dividem um registro de custódia e abrem **duas gavetas
físicas diferentes**. (Que existam duas gavetas na loja é fato operacional — [NÃO VERIFICADO].)

**(c) As brechas concretas** estão na seção 4. As três principais, em uma linha cada:
1. dois dispositivos no mesmo terminal dividem a custódia sem ninguém ser avisado;
2. o livro-caixa **não registra de qual dispositivo** veio o lançamento — só de qual pessoa;
3. a trava da gaveta é verificada **pelo navegador**, não pelo servidor.

---

## 2. Fluxo passo a passo, com evidência

### 2.1 As três identidades que convivem no balcão

| Identidade | O que é | Onde vive | O que concede |
|---|---|---|---|
| **Estação** | o dispositivo | cookie HttpOnly por terminal | nada (só abre a antessala) |
| **Operador** | a pessoa | cookie de sessão Django (`request.user`) | todas as permissões |
| **Turno** | a custódia da gaveta | linha `cashman.Shift` | o lugar onde o dinheiro é lançado |

[FATO] A separação está escrita em `shopman/backstage/station_trust.py:1-27` e
`shopman/backstage/api/permissions.py:1-35`: "a ESTAÇÃO é o dispositivo… Ela responde 'de onde',
nunca 'quem pode'"; "a pessoa que se identificou por PIN ou crachá É a sessão: `request.user` é o
operador".

[FATO] O nome do cookie de estação é por terminal: `doorman_dt_station_<ref sanitizado>`
(`station_trust.py:102-112`; confirmado em runtime — `cookie names: doorman_dt_station_pdv-main`).

### 2.2 Do dispositivo até o turno

1. **Provisionamento** — quem tem `cashman.manage_operators` abre a tela no dispositivo e escolhe
   qual balcão ele é (`station_trust.py:41` `PROVISION_PERM`; tela
   `surfaces/operator-kit/app/components/OperatorStationSetup.vue:31-33`; composable
   `surfaces/operator-kit/app/composables/useStationProvision.ts:39-53`). A tela **não** mostra
   ocupação: lista todos os terminais ativos e pronto (`operations.py:1083-1091`).
   [FATO] Não existe checagem de "este terminal já tem outro dispositivo".
2. **Confiança** — grava um `TrustedDevice` com `subject_type="station"`, `subject_id=<ref>` e
   `token_hash` HMAC (`packages/doorman/shopman/doorman/models/device_trust.py:74-109`).
   [FATO] A **única** unicidade do model é `token_hash` (`:103-109`); não há `unique_together`
   nem `UniqueConstraint` em `(subject_type, subject_id)` — os índices são só de busca
   (`:132-140`).
3. **Resolução por requisição** — `station_ref(request)` devolve o ref **apenas** quando há
   exatamente um vínculo válido apresentado por aquele navegador; com dois, devolve `""` e a
   escrita falha (`station_trust.py:115-126`).
4. **Gate da mutação** — `_terminal_do_pedido(request)` é o dono único da pergunta "qual gaveta"
   nas rotas de dinheiro: o corpo **pode confirmar** a estação, nunca escolher outra
   (`shopman/backstage/api/operations.py:4632-4650`; recusa 409 `pos_station_required` /
   `pos_terminal_mismatch`). Provei por teste:
   `test_body_cannot_select_a_different_station` (`shopman/backstage/tests/test_pos_station_drawer_boundary.py:37-41`).
5. **Resolução do terminal** — `resolve_terminal` **falha fechado** na ambiguidade: com 2+ terminais
   ativos e nenhum ref, levanta `POSTerminalAmbiguous` (409) em vez de escolher
   (`shopman/backstage/services/pos.py:777-829`). Com **uma gaveta só** — o caso do dono — resolve
   sozinho e é exato (`test_uma_gaveta_resolve_sozinha`, `shopman/backstage/tests/test_onda2_dinheiro_e_terminal.py:114-120`).
6. **Turno** — `open_cash_shift` é **idempotente por gaveta**: reenviar "abrir" devolve o turno que
   já está lá, "seja quem for que apertou" (`shopman/backstage/services/pos.py:51-90`).
7. **Venda** — o servidor injeta `cash_shift_id` e `pos_terminal_ref` no payload a partir da
   estação; o navegador nunca decide a atribuição de caixa (`operations.py:520-531`), e a venda
   recusa sem turno aberto (`shopman/shop/services/pos.py:3707-3724`).

### 2.3 O turno: por terminal, nunca por pessoa

[FATO] `Shift` guarda `terminal`, `opened_by`, `opened_at`, `closed_at`, `status` — e **nenhuma
coluna de dinheiro**: nem fundo, nem contagem, nem esperado, nem diferença
(`packages/cashman/shopman/cashman/models/shift.py:17-19` e `:43-66`). A docstring explica as duas
razões: fechamento cego por construção, e "uma pergunta, um dono".

[FATO] "Quem abriu" **não é dono da custódia** — o próprio `help_text` do campo diz: "NÃO é dono da
custódia nem responde sozinho pela diferença: quem agiu está em cada Entry"
(`shift.py:54-63`).

[FATO] A consequência está escrita e é a resposta mais honesta para o dono: "quando falta dinheiro,
a nota que sumiu **não deixa lançamento**. Uma diferença no fechamento não tem um dono; tem a lista
de quem passou" (`shift.py:11-15`).

### 2.4 O livro-caixa: append-only, com dois assinantes por exceção

[FATO] `Entry` registra: `shift`, `operator` (quem agiu), `approved_by` (a segunda assinatura),
`at`, `kind`, `amount_q` assinado, `order_ref`, `payment_ref`, `parent`, `reason`, `payload`
(`packages/cashman/shopman/cashman/models/entry.py:122-174`).

[FATO] **Imutável por três guardas de app:** `Entry.save()` recusa qualquer objeto com PK
(`entry.py:239-242`), `Entry.delete()` recusa (`:244-245`), e o `EntryQuerySet` proíbe
`update()`/`delete()` em massa (`:31-38`). Correção é lançamento novo apontando para o que corrige
(`parent`).

[FATO] **O limite é dito pelo próprio código:** "a guarda vale no app. Quem tem acesso ao banco
edita o que quiser; imutabilidade real exigiria trigger no Postgres, e nem o `Move` tem"
(`entry.py:16-18`).

[FATO] Tipos que exigem segunda assinatura: `CASH_OUT` (sangria), `DRAWER_UNLOCK`, `CHANGE_SERVED`,
`COUNT_CORRECTION` (`entry.py:118-120`), validado no único escritor `ledger.record`
(`services/ledger.py:105-106`).

[FATO] O sinal mora no TIPO e o banco confere (`CheckConstraint` `cashman_entry_sign_by_kind`,
`entry.py:195-215`): sangria positiva ou abertura de gaveta com valor são impossíveis.

[FATO] **Um pedido entra UMA vez por turno, por tipo** — `UniqueConstraint` parcial em
`(shift, order_ref)` para `sale` e `cod_settled` (`entry.py:227-236`), com a justificativa de que
dois submits do mesmo fechamento dobrariam o dinheiro esperado. A tradução da colisão é
`DUPLICATE_ENTRY` (`services/ledger.py:133-141`).

### 2.5 Abertura, sangria, suprimento, ajuste, fechamento — quem pode e o que fica gravado

| Ato | Quem pode | O que fica no livro |
|---|---|---|
| Abrir turno | `cashman.operate_pos` (`operations.py:4242-4243`) | `Shift` + `float_in` na MESMA transação (`shifts.py:60-81`) |
| Sangria | operador com `operate_pos` **+ PIN/crachá de quem tem `cashman.adjust_shift`**, sempre, sem limiar (`services/pos.py:104-163`) | `cash_out` com `operator` **e** `approved_by` + motivo obrigatório no servidor (`pos.py:140-142`) |
| Suprimento | operador com `operate_pos` | `cash_in`; sem PIN, porque "só cria sobra" (`pos.py:93-101`) |
| Ajuste de contagem | gerente, pós-fechamento | `count_correction` com `parent` na contagem + motivo obrigatório (`shifts.py:127-150`) |
| Fechar turno | **só `backstage.perform_closing`** — a gerência (`services/pos.py:713-740`; `shopman/backstage/permissions.py:58`) | `count` com `amount_q = contado − esperado` e o `operator` de quem contou (`shifts.py:100-121`) |
| Abrir gaveta sem venda | `operate_pos` | `drawer_open` com motivo obrigatório (`pos.py:166-183`) |
| Destravar gaveta | operador + PIN gerencial | `drawer_unlock` com `approved_by`, `outcome` e `duration_ms` (`pos.py:364-418`) |
| Devolver dinheiro | operador + PIN gerencial | `refund` negativo, casado com `PaymentTransaction(REFUND)` do payman na mesma transação (`pos.py:421-457`; `shop/services/payment.py:1017-1074`) |
| Acerto de entrega (COD) | operador | `cod_settled` no turno aberto de quem recebeu (`shopman/backstage/services/orders.py:137-182`) |

[FATO] **Duas assinaturas são duas PESSOAS.** A autoaprovação é recusada com log de aviso, tanto no
PIN quanto no crachá: "o gerente que também opera o balcão se autorizava… isso não é aprovação, é um
passo a mais no mesmo ato" (`shopman/shop/services/pos.py:2342-2368` para PIN; `:2391-2409` para
crachá).

[FATO] Troco: o pedido (`change_requested`) tem efeito **zero** no saldo, por `CheckConstraint`
(`entry.py:200-212`); atender (`change_served`) **exige PIN gerencial** porque "a gaveta abre com
dinheiro dentro e alguém de fora do turno mexe nela" (`services/pos.py:614-643`). O estado é
dobrado do livro, não guardado em coluna (`ledger.py:242-282`). O caso "duas pessoas na mesma tela"
está previsto no tratamento do pedido já resolvido (`services/pos.py:680-700`).

### 2.6 O que acontece com DOIS dispositivos no MESMO terminal — sonda executada

Comando (sqlite de memória via `DiscoverRunner`, sem tocar em banco compartilhado; nenhum arquivo
foi criado — `git status` limpo depois):

```
PYTHONPATH=<worktree>+packages/* .venv/bin/python - <<'PY'
  ... Terminal("pdv-main"); dois TrustedDevice.create_for(STATION, "pdv-main") ...
  ... open_shift(joyce) ; record(cash_in, joyce) ; record(cash_in, fran) ...
  ... close_shift(joyce) ; close_shift(fran) ; record pós-fechamento ; update ; delete ...
PY
```

Saída (verbatim, curada):

```
devices p/ mesmo terminal: 2
verify A: True verify B: True
cookie names: doorman_dt_station_pdv-main
open_shift_for_terminal == s1: True
segunda abertura recusada: SHIFT_ALREADY_OPEN
entries no turno: [('float_in','joyce',10000), ('cash_in','joyce',1000), ('cash_in','fran',2000)]
counts no turno: 1
segundo fechamento recusado: SHIFT_NOT_OPEN
lancamento pos-fechamento recusado: SHIFT_NOT_OPEN
update recusado: Lançamentos de caixa são imutáveis...
delete recusado: Lançamentos de caixa são imutáveis...
```

Leitura da sonda:

- [FATO] **Dois dispositivos confiáveis para o mesmo terminal coexistem** (2 linhas, ambos os tokens
  válidos, mesmo nome de cookie). A tela de provisionamento não avisa; o banco não proíbe.
- [FATO] **A custódia é uma só**: o mesmo `open_shift_for_terminal` responde para os dois; a segunda
  abertura é recusada com `SHIFT_ALREADY_OPEN`.
- [FATO] **Dois operadores lançam no mesmo livro sem cerimônia** — o turno fica com `float_in` da
  Joyce e `cash_in` da Fran, cada linha com o nome de quem a fez. É o comportamento desenhado:
  `test_o_balcao_se_reveza_DENTRO_do_mesmo_turno` (`shopman/backstage/tests/test_cash_operator_identity.py:141-183`).
- [FATO] **Dois fechamentos NÃO acontecem**: o segundo é recusado com `SHIFT_NOT_OPEN` e o turno
  fica com UMA linha `count`. O `close_shift` relê o turno sob `select_for_update`
  (`services/shifts.py:101-103`).
- [FATO] **Dois sangrias, sim, acontecem** — cada uma é um ato próprio, com PIN gerencial próprio
  (não há constraint que impeça; a unicidade parcial só cobre `sale` e `cod_settled`).
- [FATO] **Lançamento depois do fechamento é recusado** (`SHIFT_NOT_OPEN`), inclusive vindo de outro
  "dispositivo": `ledger.record` relê o status do banco sob lock (`services/ledger.py:111-116` e
  `:194-199`), provado por `test_venda_em_voo_nao_entra_no_turno_fechado_por_tras`
  (`packages/cashman/shopman/cashman/tests/test_concurrency.py:49-57`).

### 2.7 Fechamento do dia: é por LOJA, não por terminal

[FATO] `perform_day_closing` cria **um** `DayClosing` por DATA — o segundo do mesmo dia é recusado
com "Fechamento de hoje já foi realizado" (`shopman/backstage/services/closing.py:26-36`). O
snapshot carrega o resumo de caixa de **todos** os turnos fechados do dia, mais a lista de turnos
que ficaram ABERTOS (`:400-455`).

[FATO] Turno esquecido aberto no fechamento gera alerta `cash_shift_open_at_closing` nomeando quem
e em qual balcão — e **não** fecha nada por conta própria (`closing.py:101-130`).

[FATO] O dinheiro de um turno entra no dia em que ele **fechou** (`closed_at__date`,
`closing.py:411-415`), com a consequência dita: turno que atravessa a meia-noite conta inteiro no
dia do fechamento (`closing.py:115-117`).

[FATO] O fechamento do dia exige `backstage.perform_closing` (`operations.py:1593`, `:1617`;
`shopman/backstage/models/closing.py:31`).

### 2.8 Divergência: limiares e alertas que existem hoje

| Alerta | Régua | Quem vê | Evidência | Agendado |
|---|---|---|---|---|
| `bi_cash_variance` (quebra acumulada **por gaveta**) | `threshold_q = 5000` (R$ 50) em `lookback_days = 7`; `severity=warning`; cooldown 24 h | operador vê mensagem SEM nome e SEM valor; detalhe só para quem tem `cashman.audit_shift` | regra semeada em `config/management/commands/seed.py:9632-9641`; cálculo em `shopman/backstage/bi/alerts.py:322-374`; `AUDIT_ONLY_METRICS` em `shopman/backstage/models/bi_alerts.py:56` e redação em `bi/alerts.py:115-118` e `:140-172` | `evaluate_bi_alerts` no `maintenance_worker` (`shopman/shop/management/commands/maintenance_worker.py:99`) |
| `cash_ledger_mismatch` | qualquer diferença entre payman (capturas − estornos em dinheiro) e o livro-caixa; `severity=error` | retaguarda | `shopman/backstage/services/financial_reconciliation.py:829-865` | `reconcile_financial_day` (`maintenance_worker.py:142`) |
| `cash_sale_after_shift_close` | venda em dinheiro que caiu depois do fechamento do turno; `critical`, com o valor fora do livro | retaguarda | `shopman/shop/services/pos.py:3604-3625` | no ato |
| `cash_shift_open_at_closing` | turno aberto no fechamento do dia | operador/gestor | `closing.py:119-130` | no ato |
| `pos_drawer_sensor_blind` / `pos_drawer_left_open` | sensor que MEDIU e parou de responder; gaveta aberta sem venda por `drawer_idle_alert_minutes` (default 3 min, editável em `Shop.defaults["pos"]`) | operador | `shopman/backstage/models/alerts.py:225-230`; `services/pos.py:186-336`; `pos_hardware.py:262-299` | no ato |

[FATO] A régua é **por gaveta, não por pessoa**, e o nome só entra quando o livro prova que uma
pessoa só lançou naquele turno (`sole_operator_key`): "Somar a quebra 'da Joyce' quando três
passaram pela gaveta seria inventar um culpado" (`bi/alerts.py:322-331` e `:360-365`).

### 2.9 Quem assina o papel

[FATO] O comprovante de sangria/suprimento é composto **do livro**, e traz turno, data, **quem
lançou** e **quem autorizou** na mesma linha, mais o motivo, o valor emoldurado e um código
(`shopman/backstage/services/receipt_escpos.py:33-91`, em especial `:63-67`).

[FATO] O código é `SG-<entry_pk>-<HMAC(SECRET_KEY)>`, com comparação em tempo constante e aceitação
das chaves antigas via `SECRET_KEY_FALLBACKS` (`shopman/backstage/services/receipt_verify.py:35-87`).
Ele **aponta** para o registro; papel inventado não tem código que resolva. O módulo diz o limite:
"não impede fotocópia… torna a fraude detectável, não impossível. Papel é papel" (`:12-13`).

[FATO] A conferência é uma página Admin com login de staff e `cashman.audit_shift`
(`shopman/backstage/admin_console/cash_receipt.py:28-31` e `:51-66`) — não é página pública, de
propósito ("a planta de um roubo").

[FATO] O que **não** existe: assinatura da PESSOA no papel. O HMAC assina o `entry_id`, não o
operador. O que amarra a pessoa é o nome impresso + a linha do livro (`Entry.operator` /
`Entry.approved_by`), não uma assinatura criptográfica do indivíduo.

---

## 3. O que impede má operação ou fraude HOJE

[FATO] Controles verificados no código, em ordem de força:

1. **Fechamento cego por construção.** A projection do PDV nunca expõe esperado nem diferença — nem
   no X, nem no Z — e isso é garantido por não chamar `balance`/`expected_before_count`/`difference`
   (`shopman/backstage/projections/cash_session.py:22-27`). A contagem vira um lançamento
   (`count.amount_q = contado − esperado`), então esperado/contado/diferença são somas provadas.
2. **Sangria exige segunda pessoa, sempre, sem limiar** e a autoaprovação é recusada no PIN e no
   crachá (`services/pos.py:104-163`; `shop/services/pos.py:2360-2363`, `:2405-2408`). O motivo da
   saída é exigência do SERVIDOR, não da tela (`services/pos.py:134-142`).
3. **Uma gaveta, um turno** — `UniqueConstraint` condicional, não `exists()` (TOCTOU)
   (`shift.py:83-87`; `shifts.py:68-73`); a mensagem de recusa é da casa, não `IntegrityError`
   (`services/pos.py:86-90`).
4. **Nada entra no livro depois da contagem.** `ledger.record` relê o turno sob `select_for_update`
   na mesma transação (`ledger.py:111-116`, `:194-199`); só `count_correction`, `note` e
   `receipt_result` são aceitos em turno fechado (`ledger.py:33`). Se a venda em voo perder a
   corrida, o dinheiro já está na gaveta — e o sistema prefere a **sobra visível** à linha tardia:
   `cash_sale_after_shift_close` é `critical` e traz o valor (`shop/services/pos.py:3604-3625`).
5. **Dinheiro não dobra.** Unicidade de `(shift, order_ref)` por tipo no banco
   (`entry.py:227-236`) + chave de idempotência por tentativa, com fingerprint de
   ator+terminal+path+payload e recusa de replay com conteúdo diferente
   (`operations.py:4125-4180`).
6. **O browser não escolhe a gaveta.** `cash_shift_id` e `pos_terminal_ref` são injetados pelo
   servidor (`operations.py:520-531`); o corpo só pode CONFIRMAR a estação (`operations.py:4632-4650`).
   Teste: `test_request_station_selects_original_drawer_and_discards_forged_shift`
   (`test_pos_station_drawer_boundary.py:28-34`).
7. **Falha fechado na ambiguidade.** 2+ gavetas sem ref ⇒ 409 `POSTerminalAmbiguous`, porque "em
   dinheiro, falha silenciosa é pior que falha ruidosa" (`services/pos.py:795-806`).
8. **Fechar o caixa é da gerência**, não de quem abriu (`services/pos.py:713-740`); provado por
   `test_quem_ABRIU_nao_fecha_por_ter_aberto` (403 `cash_close_forbidden`) e
   `test_operador_comum_nao_fecha` (`shopman/backstage/tests/test_pos_cash_close_policy.py:73-95`).
9. **Toda exceção de gaveta deixa rastro com duas assinaturas**: `drawer_open` com motivo,
   `drawer_unlock` com `approved_by`/outcome/duração, `refund` com PIN, `count_correction` com
   motivo e `parent` (`entry.py:118-120`).
10. **A tentativa de abrir a tela de PIN também é registrada** — inclusive `abandoned` e `denied`,
    porque "o operador que tenta o PIN do gerente cinco vezes por turno e desiste não aparece em
    lugar nenhum, e é exatamente ele que se quer enxergar" (`services/pos.py:337-361`).
11. **Apuração não é do balcão.** X/Z exigem `cashman.audit_shift` (`operations.py:4920-4940`);
    a tela de conferir comprovante idem (`admin_console/cash_receipt.py:31`).
12. **Identidade não é o dispositivo.** O buraco de 20/08 (balcão logado como `admin` superusuário,
    cookie valendo no domínio inteiro) está fechado: estação não concede nada
    (`station_trust.py:1-27`), totem só age em Produção e nunca com conta superusuária
    (`station_trust.py:56-83`, `:225-267`).

[FATO] Suítes executadas nesta análise (nada falhou):
- `packages/cashman/shopman/cashman/tests` → **80 passed, 1 skipped** (o skip é o teste de threads
  que exige PostgreSQL, `test_concurrency.py:34-37`).
- 8 arquivos de teste de custódia/caixa (`test_cash_operator_identity`, `test_pos_station_drawer_boundary`,
  `test_cash_audit_policy`, `test_terminal_ambiguo`, `test_pos_cash_idempotencia`,
  `test_bi_cash_difference_by_operator`, `shop/tests/test_pos_cash_ledger`,
  `shop/tests/test_cod_custody_concurrency`) → **89 passed in 55 s**.

---

## 4. Brechas concretas

### B1 — Dois dispositivos no mesmo terminal dividem a custódia, sem aviso e sem limite [FATO]
`provision` é por navegador e **preserva** os outros dispositivos do mesmo terminal
(`station_trust.py:304-312`, `:348-351`); `TrustedDevice` só tem unicidade em `token_hash`
(`device_trust.py:103-109`); a listagem de terminais da tela de provisionamento não informa
ocupação (`operations.py:1083-1091`). Sonda: **2 dispositivos, ambos válidos, mesmo cookie name**.
Consequência: o tablet e o desktop do balcão escrevem no MESMO turno. Isso é bom para sincronia
(é o desenho), mas o dono não tem hoje onde **ver** que isso está acontecendo.

### B2 — O livro-caixa não registra de qual DISPOSITIVO veio o lançamento [FATO]
`Entry` tem `operator`, `approved_by`, `shift`, `at`, `payload` — e nenhum campo de estação
(`entry.py:122-174`). Nenhum chamador de dinheiro escreve a estação no `payload`
(`services/pos.py` em `register_cash_movement`, `drawer_open`, `unlock_drawer`, `refund_cash`,
`serve_change_request`, `request_change`: nenhum inclui `station_ref`). Com dois dispositivos, o
livro responde "quem" mas **não responde "de onde"** — e é "de onde" que separa um lançamento feito
no balcão de um lançamento feito de um tablet na sala dos fundos.

### B3 — A trava da gaveta é verificada pelo NAVEGADOR, e o token do agente é o mesmo para os dois [FATO]
O servidor na DO não alcança a loopback do balcão e diz isso por escrito
(`shopman/backstage/services/pos_terminal.py:231-262`); é a **página** que sonda `/health` do
agente e chuta a gaveta. O `agent_url` + `token` vêm do `Terminal.metadata["hardware"]`
(`pos_hardware.py:51-71`, `:140-158`) e vão para o navegador de propósito
(`pos_hardware.py:203-210`) — logo, **os dois dispositivos do mesmo terminal recebem o mesmo token**.
[INFERÊNCIA] Um dispositivo com o cookie de estação daquele terminal pode abrir a gaveta física à
qual ele está ligado, sem que o servidor tenha como saber ou impedir; e dois dispositivos podem
abrir **duas gavetas** sob **um** registro de custódia. [NÃO VERIFICADO] se a loja tem, fisicamente,
mais de uma gaveta ligada a mais de um dispositivo.

### B4 — Um dispositivo pode LER o X de outra gaveta [FATO]
`POSCashReportView` passa `terminal_ref` direto do **query param**, sem validar contra a estação
(`operations.py:4942-4946`), e `build_cash_session_report` cai em `resolve_terminal(terminal_ref)`
com `strict=False` — que, vazio, escolhe o primeiro terminal ativo por `ref`
(`projections/cash_session.py:137-158`; `services/pos.py:802-806`). Diferente de TODA mutação de
caixa, que atravessa `_terminal_do_pedido`. Mitigante real: exige `cashman.audit_shift` e a
projection é cega por construção (sem esperado/diferença). Vaza, ainda assim, movimentos e
faturamento por método de outra gaveta. Com uma gaveta só, inofensivo; no dia da segunda, não.

### B5 — A sessão do operador é um cookie portador, sem vínculo com o dispositivo [FATO de ausência]
A sessão nasce no `login()` do PIN/crachá (`shopman/backstage/services/operator_session.py:1-16`,
`:53-60`), vive 7 dias de ociosidade renovável (`config/settings.py:2065`) e vale no domínio-pai
`.boulangerie.com.br` (`config/settings.py:2051-2057`; `station_trust.py:58-65`). Não há — em
lugar nenhum — verificação de que a sessão está sendo usada no MESMO dispositivo onde nasceu
(procurei por binding de sessão em `operator_session.py`, `admin_session.py`, `shop/middleware.py` e
`backstage/middleware.py`: não existe). [INFERÊNCIA] Quem copiar o cookie (perfil de navegador
sincronizado, exportação de cookie, device perdido) opera como aquela pessoa em outro dispositivo,
e cada ato sai assinado com o nome dela. O travamento por capability
(`LOCKED_CAPABILITIES_KEY`, `operator_session.py:37-40`) é **por sessão**, então travar o PDV num
dispositivo trava nos dois.

### B6 — Dois dispositivos ⇒ duas sangrias legítimas; nada detecta o padrão [FATO]
A idempotência é por `client_request_id` do cliente (`operations.py:4135-4141`), e a unicidade de
banco cobre apenas `sale`/`cod_settled` (`entry.py:227-236`). Não há limite de valor nem de
quantidade de sangrias por turno (o gate é só "PIN de gerente, em qualquer valor",
`services/pos.py:113-120`). [INFERÊNCIA] O padrão de risco — sangrias repetidas em dois dispositivos
no mesmo turno, cada uma com um PIN gerencial válido — não dispara alerta nenhum hoje: o único
alarme de dinheiro é o `bi_cash_variance` por gaveta, e ele só olha a **quebra acumulada** no
fechamento, R$ 50 em 7 dias (`seed.py:9636-9641`).

### B7 — Imutabilidade é do app, não do banco [FATO]
Dito pelo próprio pacote (`entry.py:16-18`). Um acesso direto ao Postgres edita ou apaga um
lançamento sem deixar rastro. O `CheckConstraint` de sinal continua valendo (é constraint de
banco), mas `UPDATE`/`DELETE` de linha, não.

### B8 — Falta de troco tem dono; falta de dinheiro não tem [FATO — e é decisão consciente]
"Uma diferença no fechamento não tem um dono; tem a lista de quem passou" (`shift.py:11-15`), e o
BI **recusa** nomear quem quer que a janela misture pessoas (`bi/alerts.py:360-365`). Num balcão que
se reveza várias vezes ao dia isso é o certo tecnicamente; mas o dono precisa saber que o preço é
este: **com uma gaveta e N mãos, o sistema não responde "quem"** — por desenho.

### B9 — Ainda hoje, um turno aberto "gruda" o dia seguinte [FATO]
`close_cash_shift` já registra a consequência operacional: "sem ninguém da gerência por perto, a
gaveta fica aberta e as vendas do dia seguinte caem no turno de ontem"
(`services/pos.py:726-729`). Existe alerta no fechamento do dia (`cash_shift_open_at_closing`) e a
lista de `open_shifts` no snapshot (`closing.py:444-452`), mas nada impede.

### B10 — Device é revogável, mas ninguém sabe QUAIS dispositivos um terminal tem [FATO]
`TrustedDevice.active_for(subject_type, subject_id)` e `revoke_all_for(...)` existem
(`device_trust.py:214-236`) e o Admin do doorman registra `TrustedDeviceAdmin`
(`packages/doorman/shopman/doorman/admin.py:280-290`; espelho Unfold em
`contrib/admin_unfold/admin.py:280`), com `list_filter` por `subject_type`/`is_active`. Mas não há,
na tela de Terminais do PDV, a lista "quantos dispositivos estão provisionados neste balcão". O
dado existe e ninguém o mostra — e `last_used_at` é atualizado a cada requisição
(`device_trust.py:208-212` chama `touch()` via `verify_token`), ou seja, **dois dispositivos ativos
no mesmo balcão são detectáveis hoje e não são detectados**.

---

## 5. Recomendações ordenadas

Ordenadas por (risco coberto ÷ custo). As três primeiras resolvem a pergunta do dono.

1. **Mostrar os dispositivos de cada terminal no Admin (Terminais do PDV).**
   Lista `TrustedDevice.active_for("station", terminal.ref)` com `label`/`last_used_at`/`ip`, e um
   botão "revogar este dispositivo" que já existe (`revoke_all_for` / `device.revoke()`). Sem isso,
   o dono não consegue responder "quem mais está apontando para a minha gaveta". Dados prontos,
   tela pequena, zero migração.

2. **Alertar quando um terminal ganha um segundo dispositivo confiável.**
   No `provision` (`station_trust.py:295-366`), se já existir vínculo ativo daquele ref, emitir
   `OperatorAlert` ("o balcão X agora responde em 2 dispositivos") e devolver isso na resposta da
   tela de provisionamento. Opcional: alerta periódico no `maintenance_worker` quando dois
   dispositivos do mesmo terminal têm `last_used_at` dentro da mesma janela de minutos — o dado já
   é gravado hoje.

3. **Gravar a ESTAÇÃO em cada lançamento de caixa.**
   Passar `station_ref` de `_terminal_do_pedido(request)` até `register_cash_movement`,
   `drawer_open`, `drawer_unlock`, `refund_cash`, `serve_change_request` e `request_change`, e
   escrevê-la em `Entry.payload["station_ref"]` (o schema vive em `docs/reference/data-schemas.md`,
   que precisa ser atualizado junto). **Zero migração** e resolve a pergunta "de onde veio este
   lançamento" no dia em que houver dois dispositivos. Se o dono quiser consultar em escala, aí sim
   um campo indexado — mas isso é decisão depois de ver o uso.

4. **Validar o `terminal_ref` do X/Z contra a estação (B4).**
   Trocar `request.query_params.get("terminal_ref")` por `_terminal_do_pedido(request)` em
   `operations.py:4942-4946` — ou, no máximo, aceitar o param apenas quando ele **coincidir** com a
   estação. Alinha a leitura à regra que todas as mutações já seguem.

5. **Decidir explicitamente o papel do segundo dispositivo.**
   Com UMA gaveta, as opções honestas são duas, e a escolha é do dono:
   (i) o tablet é estação do MESMO terminal — dividem a custódia, e a recomendação 1/2 passa a ser
   obrigatória para que isso seja visível; ou
   (ii) o tablet recebe OUTRO `Terminal.ref` e não opera caixa (usa KDS/Pedidos, que não têm
   gaveta). O que **não** deve continuar acontecendo é a escolha implícita: hoje ela é feita por
   quem clica "É este balcão" na tela de provisionamento, sem saber que está escolhendo dividir a
   gaveta.

6. **Vincular a sessão do operador à estação onde ela nasceu (B5), ao menos para o caixa.**
   Guardar `station_ref` no início da sessão (`operator_session.start`) e recusar mutação de caixa
   quando a estação da requisição for outra — mensagem clara: "esta sessão nasceu no balcão X".
   Custo: uma chave de sessão e uma checagem no caminho do dinheiro. Ganho: cookie copiado deixa de
   ser identidade portátil para efeito de gaveta.

7. **Trava de banco para o livro-caixa (B7).**
   `REVOKE UPDATE, DELETE` na tabela `cashman_entry` para o usuário da aplicação (ou trigger
   `BEFORE UPDATE OR DELETE`), no espírito do que o próprio pacote admite faltar
   (`entry.py:16-18`). É a diferença entre "imutável por disciplina" e "imutável".

8. **Enxugar o tempo de vida da estação/terminais inativos e o "turno que atravessa o dia" (B9).**
   Um comando de manutenção que (a) expira `TrustedDevice` de estação sem uso há N dias e (b) grita
   para o gestor todo dia enquanto houver turno aberto há mais de 24 h — o alerta já existe no
   fechamento do dia; falta a cadência diária.

9. **Nada a mudar em B8 — mas dizer isso ao dono por escrito.**
   A custódia por gaveta é decisão de 21/08/2026 e é a escolha certa para o balcão que se reveza
   (`shift.py:11-15`). Se o dono quiser que uma pessoa responda pelo dinheiro, o mecanismo é a
   contagem cega na troca de operador — que o sistema **deliberadamente não exige** porque "a loja
   não faz e não vai fazer" (`test_cash_operator_identity.py:141-151`). Reabrir isso é decisão de
   produto, não bug.

---

## 6. O que NÃO consegui verificar

1. **`shopman/backstage/services/cash.py` não existe nesta revisão.** Procurei com
   `ls shopman/backstage/services/` e `grep -rn "from shopman.cashman" shopman/`: o único arquivo
   com "cash" no nome é `shopman/backstage/services/cash_change_alerts.py` (39 linhas). O papel que
   o pedido atribui a esse arquivo é exercido por
   `shopman/backstage/services/pos.py` (mutações de caixa do PDV), `shopman/backstage/services/closing.py`
   (fechamento do dia) e `shopman/shop/services/payment.py` (payman ↔ livro). [NÃO VERIFICADO] se
   houve um `cash.py` que foi dividido; não investiguei história do arquivo (isso exigiria
   `git log`, que é leitura e seria possível, mas o pedido era sobre o estado atual).
2. **Que a loja tenha mais de uma gaveta física** (B3). Não há como saber pelo código quantas
   gavetas existem no balcão; o modelo conhece `Terminal`, não `Gaveta`.
3. **`settle_delivery_cash(tenders=...)`** — a assinatura citada no pedido não existe nesta revisão:
   é `settle_delivery_cash(order, *, operator, amount_raw, actor, change_back_raw, equipment_back, expected_revision)`
   (`shopman/backstage/services/orders.py:137-139`), e ela recebe o turno por
   `pos_service.current_shift(strict=True)` **sem** `terminal_ref` (`:155`) — o que, com uma gaveta,
   resolve exato; com duas, levanta `POSTerminalAmbiguous`. Os "tenders" vivem em
   `shopman/shop/services/payment.py` (`settle_terminal_tenders`, usado em `shop/services/pos.py:3578`)
   e nos intentos do payman; li o caminho do estorno em dinheiro (`payment.py:1017-1074`) mas **não
   li a implementação inteira de `settle_terminal_tenders`** — não afirmo detalhes dela.
4. **Testes de concorrência reais (duas conexões simultâneas).** O teste de threads do cashman é
   `skipif` em sqlite (`test_concurrency.py:34-37`) e nesta máquina não há Postgres apontado;
   rodaram a versão determinística (que é a que prova a releitura sob lock). [NÃO VERIFICADO] o
   comportamento sob `SELECT FOR UPDATE` de verdade — mas ele é coberto no CI de runtime
   (`make test-runtime`).
5. **Comportamento do BFF/Nuxt** na hora de provisionar dois dispositivos (se o cookie de estação
   é reescrito pelo proxy, se o cache do SSR atrapalha). Li o composable e a tela
   (`useStationProvision.ts`, `OperatorStationSetup.vue`) e o Django; não executei os apps Nuxt.
6. **Se há provisionamento duplicado no ambiente de produção hoje.** Não consultei banco nenhum
   (proibido `migrate`/`seed` em banco compartilhado, e não havia credencial/DB autorizado para
   leitura). A consulta que responderia isso é uma linha:
   `TrustedDevice.objects.filter(subject_type="station", is_active=True).values("subject_id").annotate(n=Count("id")).filter(n__gt=1)`.

### Comandos de reprodução

```bash
WT=/Users/pablovalentini/Dev/Claude/django-shopman/.dsh-worktrees/go-live-acceleration
PY=/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python
PP="$WT:$WT/packages/{utils,refs,offerman,stockman,craftsman,guestman,orderman,payman,doorman,buyman,fiscalman,cashman}"  # expandir em lista

# 1. cashman (80 passed, 1 skipped)
cd "$WT/packages/cashman" && PYTHONPATH="$PP" $PY -m pytest -q shopman/cashman/tests

# 2. custódia/caixa no backstage e no shop (89 passed)
cd "$WT" && PYTHONPATH="$PP" DATABASE_URL=sqlite:////tmp/golive-acc-cash.sqlite3 $PY -m pytest -q \
  shopman/backstage/tests/test_cash_operator_identity.py \
  shopman/backstage/tests/test_pos_station_drawer_boundary.py \
  shopman/backstage/tests/test_cash_audit_policy.py \
  shopman/backstage/tests/test_terminal_ambiguo.py \
  shopman/backstage/tests/test_pos_cash_idempotencia.py \
  shopman/backstage/tests/test_bi_cash_difference_by_operator.py \
  shopman/shop/tests/test_pos_cash_ledger.py \
  shopman/shop/tests/test_cod_custody_concurrency.py
```

A sonda de runtime da seção 2.6 usou `DiscoverRunner().setup_databases()` com sqlite (em memória por
padrão no runner de teste do Django) — nenhum arquivo foi criado na worktree
(`git status --porcelain` mostrou apenas as modificações pré-existentes de `docs/plans/` e
`docs/coordination/`, que não são minhas).
