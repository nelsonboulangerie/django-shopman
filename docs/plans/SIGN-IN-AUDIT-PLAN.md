# Plano — Trilha de acesso e aviso de login (Gerente/Admin)

Data: 2026-08-29
Status: **Completo nesta branch** (log, destaque, aviso, sino, "não fui eu", "perdi meu crachá"). O dono respondeu as quatro decisões
em 29/08/2026 e a política abaixo já é o que o código faz. Sem pendência.
Pedido de origem: *"sistema de notificação para Gerente/Admin sempre saber quando sua conta for logada,
seja por senha, crachá ou PIN. Serve também como um log ativo. Evita que alguém use um crachá esquecido."*

---

## 0. A pergunta que ele fez primeiro: "já temos estrutura para isso?"

**Metade. E é a metade que menos dói.**

| Peça | Existe? | Onde |
| --- | --- | --- |
| Entrega de aviso à PESSOA (não à tela) | ✅ pronta e em uso | `shopman/shop/models/user_notification.py`, canal SSE `user-<id>` |
| Push em tempo real | ✅ pronto | `shopman/shop/services/campaign.py:1049` `push_user_notification()` |
| API de caixa pessoal (listar/ler/agir) | ✅ pronta | `shopman/backstage/api/notifications.py` |
| Consumo na tela | ⚠️ só no **marketing-nuxt** | `surfaces/marketing-nuxt/app/composables/useUserNotifications.ts` |
| Alerta operacional da LOJA | ✅ pronto | `shopman/backstage/models/alerts.py` (`OperatorAlert`, 30+ tipos) |
| **Registro de quem entrou** | ❌ **NÃO EXISTE** | — |
| Sinal de login ligado a algo | ❌ **NÃO EXISTE** | `user_logged_in`/`user_login_failed` não têm nenhum receiver no repo |
| Tela para consultar acessos | ❌ **NÃO EXISTE** | — |

Ou seja: o **carteiro existe e funciona**; o **fato a ser entregue nunca foi produzido**.
Hoje um crachá esquecido destrava o PDV e o único vestígio é `PinCredential.last_verified_at`
mudando em silêncio — um carimbo que sobrescreve o anterior, não uma trilha.

### Os seis caminhos de autenticação, mapeados

| # | Caminho | Onde abre a sessão | Quem usa | No escopo? |
| --- | --- | --- | --- | --- |
| 1 | Senha do Admin Django | `django.contrib.auth.views.LoginView` (`/admin/login/`) | gerente/admin | **sim** |
| 2 | Senha no app de operador | `shopman/backstage/api/operations.py:478` (`OperatorLoginView`) | gerente/operador com dispositivo próprio | **sim** |
| 3 | **PIN** | `shopman/backstage/api/operations.py:551` (`OperatorUnlockView`) | balcão | **sim** |
| 4 | **Crachá** (código de barras) | mesma view, ramo `badge` | balcão | **sim** |
| 5 | OTP / link de acesso / passkey / dispositivo confiável | `packages/doorman/.../services/verification.py:317`, `access_link.py:251`, `shopman/shop/services/auth.py:201,291` | **cliente** | não (fora do pedido) |
| 6 | Confiança de ESTAÇÃO (cookie) | `shopman/backstage/station_trust.py` | dispositivo | **não é login** — não concede nada, só faz a tela de identificação aparecer |

Duas coisas importam nesse mapa:

- **Os quatro caminhos do escopo terminam todos em `django.contrib.auth.login()`.** Isso dá um
  ponto de origem único e à prova de esquecimento: `user_logged_in`. Um caminho de login novo que
  alguém escreva amanhã já nasce coberto.
- **2FA (TOTP) existe no Admin** (`shopman/backstage/middleware_2fa.py`), mas está **desligado por
  padrão** (`SHOPMAN_ADMIN_REQUIRE_2FA`), e nenhuma env o liga nos specs. Vale registrar aqui
  porque muda a leitura de risco da senha do Admin.

### O que os canais de aviso realmente fazem hoje (a verdade, não o mapa de módulos)

| Canal | Envia de verdade? |
| --- | --- |
| SSE in-app (`user-<id>`) | ✅ **sim**, funcionando |
| ManyChat (WhatsApp) | ⚠️ HTTP real, mas o template de negócio está fora da janela de 24h — não serve para aviso não solicitado |
| SMS (Comtele) | ⚠️ HTTP real, credencial no spec, mas com erro 500 em aberto |
| E-mail | ❌ **NÃO ENVIA.** `EMAIL_BACKEND` cai no backend de console (`config/settings.py:799`) e nenhum spec `.do/*.yaml` define `EMAIL_*`. Pior: o adapter devolve `True` (sucesso falso) e **encerra a cadeia de fallback** (`shopman/shop/adapters/notification_email.py:238`) |
| WhatsApp direto (Meta) | ❌ código morto — nunca registrado no registry |

**Isto é decisivo para o desenho:** um aviso por e-mail seria exatamente o pior resultado
possível — silencioso e reportado como entregue.

---

## 1. Avaliação da ideia — "que tal?"

**A ideia está certa, e por um motivo mais forte do que ele disse.** O crachá é a única credencial
da casa que se pode *perder no chão*: é posse pura, 48 bits de token impresso, sem segundo fator, e
`resolve_by_badge` deliberadamente **não** está acoplado ao lockout do PIN (não há força bruta a
conter, mas também não há atrito nenhum para quem achou o crachá). A emissão já deixa rastro no
`LogEntry` do Admin (`shopman/backstage/admin/operators.py:31`), e o comentário lá é honesto sobre o
buraco: *a trilha detecta, não impede*. Este trabalho é a outra metade dessa frase — hoje a trilha
existe para a **emissão** do crachá e não existe para o **uso** dele.

**Onde a ideia falha na prática, e como o desenho responde:**

1. **Fadiga de alerta mata a feature em uma semana.** O gerente entra 3-6 vezes por dia. Se toda
   entrada vira aviso, ele para de ler, e aí o aviso que importava chega numa caixa que ninguém
   abre. → §5 (o corte), e o corte é configurável.
2. **Aviso sem ação é ansiedade, não segurança.** "Alguém entrou com seu crachá" sem um botão de
   "não fui eu" transfere o problema sem dar ferramenta. → §6.
3. **O aviso não pode depender da tela que ele não está olhando.** Se chega só no PDV, o gerente em
   casa não vê. → §4: canal pessoal, não canal de superfície. Mas o SSE só entrega para quem está
   com *alguma* superfície aberta — a limitação é real e está declarada em §4.
4. **Log que ninguém lê é custo de armazenamento.** → §3: tela no Admin, retenção explícita, e o
   log só existe para quem opera (staff), não para os milhares de logins de cliente.
5. **O aviso vira o vetor.** Um aviso que chega por WhatsApp com "clique aqui para bloquear" é um
   phishing pronto. → §6: a ação mora dentro da superfície autenticada, nunca num link do aviso.

**Um efeito colateral que vale mais que o alerta:** o log responde perguntas que hoje não têm onde
ser respondidas — *quem estava no balcão às 14h20 quando o desconto saiu?*, *este operador ainda
usa o sistema ou a conta pode ser desativada?*, *a estação X foi usada fora do horário?*.

---

## 2. O evento canônico — um só ponto de origem

**Um fato: "uma sessão de operador foi autenticada".** Nunca três caminhos paralelos para senha,
PIN e crachá.

```
django.contrib.auth.login()  ──emite──▶  user_logged_in  ──▶  receiver do backstage
                                                                     │
   OperatorUnlockView (PIN/crachá recusado) ──chama──▶  record()  ◀───┘
                                                          │
                                                          ▼
                                                    SignInEvent (uma linha)
```

- **Sucesso vem do signal do Django**, não das views. É o que garante cobertura: senha do Admin,
  senha do app, PIN e crachá passam todos por `login()`, e um caminho novo entra sozinho.
- **O método é marcado pelo chamador**, num atributo de request lido pelo receiver
  (`request.shopman_sign_in_method`). Sem marcador, o método é inferido do backend de
  autenticação. Duas linhas nas views existentes, nenhuma lógica duplicada.
- **A falha de PIN/crachá não tem signal equivalente no Django** (não passa por `authenticate()`),
  então ela é registrada explicitamente na única view que a produz, chamando **a mesma função**
  `record()`. Um escritor, uma função — não é caminho paralelo.
- **Regra de escopo: só `is_staff`.** Login de cliente (OTP, passkey, link) não entra. É o pedido,
  é o volume certo, e evita transformar a trilha num banco de PII de cliente.

### Por que um model novo, e não `Session.data`/`Order.data`

A regra "Core é sagrado" proíbe **campo novo em model do Core** (`packages/*`) para dado contextual.
Aqui não há model do Core a estender: `PinCredential` guarda uma credencial (um carimbo que
sobrescreve), `TrustedDevice` guarda um dispositivo, `LogEntry` guarda mudança de objeto no Admin,
e `OperatorAlert` é a fila de exceções da loja, não uma trilha (`acknowledged` some da fila).
Nenhum deles é "uma linha por entrada, para sempre". O model vive em `shopman/backstage/`, que é a
casa do que é do operador, e não toca `packages/*`.

---

## 3. O log

**`shopman/backstage/models/sign_in.py` → `SignInEvent`** (tabela append-only, nunca editada).

Queryable de verdade (é por isso que se filtra):

| Campo | Por quê é coluna |
| --- | --- |
| `user` (FK, `SET_NULL`) | "os acessos do fulano" |
| `username` | sobrevive à exclusão da conta — o log não pode sumir com ela |
| `method` | senha / PIN / crachá / OTP / desconhecido — o corte de §5 pergunta isto |
| `outcome` | `success` / `failed` |
| `station_ref` | de que balcão. **É o eixo central do corte**: "dispositivo desconhecido" |
| `ip_address` | de onde |
| `created_at` | quando (índice — toda consulta é por tempo) |
| `notified` | se este evento já gerou aviso — impede aviso duplicado no retry |

Em JSON (`data`, `JSONField`) — contexto, nunca filtro: `user_agent`, `surface`, `path`, `reason`.
As chaves estão registradas em [`docs/reference/data-schemas.md`](../reference/data-schemas.md).

**Retenção: 180 dias.** Longo o bastante para uma investigação de "mês passado", curto o bastante
para a tabela nunca virar problema (a ordem de grandeza é ~50 linhas/dia). A varredura entra no
`maintenance_worker` existente, sem cron novo. Prazo configurável por setting.

### O caminho do gerente até o log, hoje

**Clique a clique:** abrir `https://admin.boulangerie.com.br/admin/` → login → menu lateral →
**Auditoria** → **Acessos de operador**. Filtros por método, resultado, estação e data; busca por
usuário; coluna **"atenção"** mostrando o que fez cada linha ser destacada.

**A permissão já alcança — provado, não deduzido.** Com `setup_groups` rodado: o grupo `Gerente`
tem `backstage.view_signinevent` e `GET /admin/backstage/signinevent/` responde **200**; o grupo
`Caixa` **não** tem, e a mesma URL responde **403**. O balconista não lê a trilha da loja.

⚠️ **Mas isso é o Admin, em `admin.boulangerie.com.br` — outro domínio e outro app.** O gerente
que vive no Hub não vai lá "sempre que quiser": vai quando lembra. Por isso o log da PRÓPRIA
conta também mora no sino, dentro do app em que a pessoa já está.

**O backend da lista in-app já existe:** `GET /api/v1/backstage/sign-ins/` devolve os acessos da
**própria** conta (filtrado por `request.user`, sem parâmetro que mude isso), já com
`anomalies`/`highlight`/`anomaly_labels` prontos para a tela. A notificação aponta para
`/account/sign-ins` — quando a página existir, os avisos antigos já levam a ela.

**E o log da própria conta mora no sino**, na layer `operator-kit` — mesma lista, com o
suspeito realçado. O `/account/sign-ins` continua sem existir: o painel abre o log ali
mesmo, e mandar a pessoa para o Admin noutro domínio não seria "conferir sempre que
quiser". A página de conta só mudaria a casa, não o comportamento.

**A tela do Admin: `SignInEventAdmin`, ModelAdmin/Unfold somente leitura**, no grupo **Auditoria** do menu,
ao lado de "Alertas do operador". Sem `add`, sem `change`, sem `delete` — o Admin é CRUD/config e
consulta, não opera, e uma trilha que se pode apagar pela tela não é trilha. Filtros: método,
resultado, estação, período. Busca: usuário. Não é página custom, é o ModelAdmin canônico — nenhum
waiver do gate necessário.

---

## 4. A notificação — decidido: in-app, todo mundo, sobre a própria conta

**Canal: `UserNotification` + push SSE no canal `user-<id>`.** É o único canal que
comprovadamente entrega hoje, é endereçado à pessoa e não à tela, já tem API de leitura, e não
inventa infraestrutura. O push sai no `transaction.on_commit`; chega em ~1s.

**Modo de entrega: contador discreto e lista consultável.** Nada de modal, som, ou o que roube
foco de quem está atendendo. "Tudo" com pop-up é insuportável em uma semana; "tudo" com um
contador é confortável.

**Destinatário: cada um sobre a própria conta.** Todo staff é avisado dos acessos à conta dele.
Ninguém recebe aviso do login alheio. A API `/api/v1/backstage/sign-ins/` filtra por
`request.user` sem parâmetro que mude isso, e há teste provando que query string não vaza — um
balconista que lesse a trilha da loja saberia quem estava no balcão a cada hora do mês.

**Falhar visível, nunca em silêncio.** ⚠️ **E-mail está proibido como canal aqui**: `EMAIL_BACKEND`
cai no backend de console e o adapter devolve `True` sem enviar. Num aviso de segurança isso é o
pior resultado possível — silencioso e reportado como entregue. WhatsApp fica para depois; nada
nesta fase depende dele.

---

## 5. O ruído — decidido: avisa TUDO, destaca o suspeito

**Palavra do dono: "acho que tudo".** Todo login vira aviso; nenhum é suprimido. O que era o
"corte" virou **destaque**: o subconjunto suspeito chega realçado na mesma lista, não separado
num silo. O gerente varre e o olho para no que é anômalo, sem que nada tenha sido escondido dele.

Isso muda o custo de errar o critério: um falso negativo passa a ser **"não destacou"** em vez de
**"não avisou"** — o primeiro é recuperável na lista, o segundo nunca aconteceu.

Sinais de destaque (todos ligados por padrão):

| Código | Gatilho |
| --- | --- |
| `badge` | crachá — a credencial de posse pura, a que o pedido nomeia |
| `unknown_station` | estação que **aquela conta** nunca usou: credencial certa, lugar errado |
| `outside_hours` | fora do expediente configurado (sem grade configurada, nada é "fora") |
| `burst` | N acessos em janela curta (default 4 em 10 min) |
| `after_failure` | acerto até 15 min depois de uma recusa |
| `failure` | qualquer recusa — o sinal mais barato que existe |

Configurável via **`RuleConfig`** com ref `sign_in_highlight`
(`shopman/shop/rules/security.py::SignInHighlightRule`). Sem linha de `RuleConfig`, valem os
defaults: a feature funciona configurada em zero lugares.

⚠️ **Chave desconhecida nos `params` NÃO carrega a configuração** — regra da casa. Aqui ela cai
nos **defaults**, alto e claro no log, e não em "destaque desligado": como esta regra só governa
realce, "não rodar" seria parar de sinalizar anomalia em silêncio, que é exatamente a falha que o
trabalho existe para evitar. Os defaults são o piso seguro; a configuração quebrada é a ignorada.

---

## 6. A ação "não fui eu" — decidido: sim, derruba

**Palavra do dono: "'Não fui eu' é algo grave... Se foi consentido, jamais apelaria para 'não fui
eu'."** O raciocínio está certo: ninguém aperta esse botão por engano de consentimento.

Implementado em `POST /api/v1/backstage/notifications/<pk>/action/` com `action: "not_me"`.

**Três cuidados que não se negociam:**

1. **A ação nunca vive num link.** Ela mora dentro da superfície já autenticada, onde há sessão,
   `request.user` provado e dono conferido. Se um dia o aviso sair por WhatsApp ou e-mail, a
   mensagem só pode dizer *"abra o app"* — um botão "clique aqui para bloquear" dentro de uma
   mensagem é phishing pronto, e seria a nossa própria comunicação treinando o operador a clicar
   nele. Está escrito no docstring de `revoke_sessions` e de `NotificationActionView` para
   ninguém desfazer por conveniência.
2. **Confirmação explícita.** Sem `confirm: true` a API responde **409** descrevendo o estrago —
   inclusive que uma venda em curso naquele terminal cai — em vez de causá-lo.
3. **A revogação vira linha no log** (`outcome=revoked`, com `requested_by`, `sessions_revoked`,
   `revoked_sign_in_event_id`) e é ela própria notificável, chegando aos outros dispositivos.

**O que a revogação alcança** (decisão do dono, 29/08/2026 — o crachá cai junto):

| Alvo | Alcança? |
| --- | --- |
| Sessões Django da conta em outros dispositivos | ✅ apagadas |
| **Crachá** | ✅ **invalidado** (`clear_badge()`) |
| Verificação 2FA daquelas sessões | ✅ mora na sessão, morre junto |
| **PIN** | ↩️ **de pé, de propósito.** PIN é conhecimento, não se acha no chão. Ninguém para de trabalhar |
| Sessão de quem pediu | 🔒 preservada — quem aperta o botão acabou de se autenticar |
| Confiança de estação (`TrustedDevice`) | ↩️ intocada, e é o certo: o cookie é do balcão, não da pessoa |
| Bridge token / AccessLink / Passkey | n/a — todos são de **cliente** (`customer_id`), não autenticam operador |

**Medido, antes e depois.** Mesmo roteiro (atacante acha o crachá → entra → vítima aperta
"não fui eu"), mesma máquina:

| | Antes | Depois |
| --- | --- | --- |
| Sessão do atacante | 403 | 403 |
| **Mesmo crachá, ~0,01 s depois** | **200 — entrou de novo** | **403 — porta fechada** |
| PIN da vítima | 200 | 200 |
| Aviso a quem reemite | — | "Crachá de ana foi invalidado" |

### "Perdi meu crachá" — mesmo efeito, sem gatilho

`POST /api/v1/backstage/operator/badge/lost/`, exige `confirm` e o **PIN**. Quem perde o
crachá às 6h não espera o ladrão usar.

**Fica na trava** (`OperatorLock`, layer `operator-kit`) — pré-login, que é onde a pessoa
está. Gate de estação, não de sessão: **provar o PIN é a autorização**, mesmo contrato da
troca de PIN. PIN errado conta para o lockout e vira linha (`badge_lost_invalid`), porque
errar aqui é tentar matar o crachá de alguém. A confirmação vem antes do PIN, para um
cliente que esqueceu a flag não queimar tentativa de quem não pediu nada.

A tela É a confirmação: diz que o crachá para agora, que o PIN continua valendo e que o
gerente emite outro — e só então pede o PIN. O leitor de crachá fica desligado ali (quem
está nessa tela não tem o crachá).

**Quem é avisado:** o dono (a linha no log) e quem tem `cashman.manage_operators` — grupo
**Gerente** —, porque são eles que reemitem. Não é o log alheio: é um pedido operacional
("o fulano precisa de crachá novo") para quem já administra credencial no Admin.

O botão fica no rodapé da identificação, ao lado de "Trocar meu PIN": discreto, mas texto
legível e não um menu — quem perdeu o crachá precisa achar sozinho.

## 7. Fases

- **F1 — evento + log + tela.** ✅ implementada.
- **F2 — destaque + aviso.** ✅ implementada: regra `RuleConfig` `sign_in_highlight`,
  `UserNotification` categoria `sign_in`, push SSE, API `/sign-ins/` da própria conta.
- **F2b — o sino.** ✅ implementado na layer `operator-kit`: uma implementação, oito apps.
  Contador discreto, painel com a caixa e o log da própria conta. Não interrompe — nada
  aparece até alguém clicar.
- **F3 — ação "não fui eu".** ✅ implementada: sessões **e** crachá, com confirmação.
- **F4 — "Perdi meu crachá".** ✅ completo: endpoint + botão na trava, nos sete apps.
- **Fora de escopo, mas anotado:** ligar `SHOPMAN_ADMIN_REQUIRE_2FA` fecha o caminho da senha do
  Admin muito melhor do que qualquer aviso. É decisão dele, e é barata.

---

## 8. Decidido em 29/08/2026 — e a única pergunta que restou

| # | Pergunta | Resposta do dono |
| --- | --- | --- |
| 1 | O corte do ruído | **"acho que tudo"** → avisa tudo, destaca o suspeito (§5) |
| 2 | Canal | **in-app primeiro**, com o log sempre à mão (§4) |
| 3 | Quem recebe | **cada um sobre a própria conta** (§4) |
| 4 | "Não fui eu" derruba a sessão | **sim** (§6) |

### ✅ Fechada: bloquear a credencial junto?

**Sim, o crachá.** Implementado. O PIN fica de pé, então ninguém para de trabalhar, e o
gerente reemite sozinho (`manage_operators` está no grupo Gerente).

### ✅ Fechada: onde fica o botão "Perdi meu crachá"?

Na trava (`OperatorLock`), provando o PIN. Componente da layer `operator-kit`, então os
sete apps de operador herdam de uma vez.

### Nenhuma pergunta aberta.
