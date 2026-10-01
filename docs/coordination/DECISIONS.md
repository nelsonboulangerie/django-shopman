# DECISIONS — ledger de decisões

> **O que é.** Registro append-only das decisões que governam o produto, com estado explícito.
> Existe porque a queixa medida em 2026-09-29 foi: *"algumas decisões ficaram perdidas
> silenciosamente no meio do caminho"*. A apuração mostrou que o padrão **não é esquecer** —
> é que **o registro não é a verdade**: dois planos mergeados continuavam marcados "não
> iniciado"; dois ADRs implementados continuavam "Proposto"; um inventário de riscos tinha
> 3 itens já corrigidos ainda marcados como abertos, e 9 abertos sem dono.
>
> **O que isto NÃO é.** Não é um segundo plano nem uma segunda matriz de go-live. Plano diz
> *como*; isto diz *o que foi decidido, por quem, quando, e se ainda vale*. Evidência de
> execução vive no código e nos relatórios; aqui fica só o ponteiro.

## Regras

1. **Append-only.** Entrada não se apaga. Decisão que mudou ganha nova entrada e a antiga vira
   `SUPERSEDIDA`, com o id da que a substituiu.
2. **Vocabulário fechado** — só estes estados:
   `DECIDIDA` · `EM_EXECUCAO` · `EXECUTADA` · `ADIADA` · `SUPERSEDIDA` · `BLOQUEADA`.
3. **`revisar_em` é obrigatório** enquanto o estado não for terminal (`EXECUTADA` ou
   `SUPERSEDIDA`). Decisão sem data de revisão é decisão que vai apodrecer em silêncio.
4. **Toda decisão tem dono nomeado.** "Ninguém" não é dono.
5. **`EXECUTADA` exige prova**: commit, PR ou comando com saída. Sem prova, o estado máximo é
   `EM_EXECUCAO`.
6. Ligado a `scripts/check_canonical_docs.py`, que **já roda no CI** (ver
   `GO-LIVE-ACCELERATION-PLAN-2026-09-29.md` §3, Onda 3).

---

## D-001 · Forma de pagamento padrão na loja online

- **Estado:** `DECIDIDA`
- **Dono:** Pablo (produto) · execução: frente F9
- **Data:** 2026-09-29 · **revisar_em:** 2026-10-31

**Decisão:** a casa prefere **Pix** como default, *se* for obrigatório ter um. Mas se *ter* um
default se provar problema real de UX, **abre-se mão dele** — Omotenashi em primeiro lugar.
Portanto: **default só quando foi dito** (preferência lembrada do cliente, ou
`payment.default_method` declarado e validado em config), **nunca por posição na lista**.

**Consequências obrigatórias:**
- Remover o fallback posicional `|| methods[0]?.ref` (`surfaces/storefront-nuxt/app/pages/finalizar.vue:744`).
- `is_default` passa a ser dinâmico (`shopman/storefront/presentation/checkout.py:445-452`).
- A forma escolhida deve ser **audível** no resumo, com troca em 1 clique sempre disponível.
- **Instrumentar** a escolha de forma de pagamento. Hoje não existe telemetria que distinga
  **escolha ativa** de **default aceito** — sem isso, não há como medir o conserto.

**Contexto do defeito:** o testador confirmou o checkout sem perceber que Pix estava marcado.
O rótulo "(padrão)" **não existe na tela** (`is_default` é calculado e nunca renderizado).
Incidente esclarecido pelo dono (corrigido em 2026-09-29): era o **alpha, com Pix no
`payment_mock`** e captura simulada ligada — não Efí de teste. Pedido aceito abertamente como
teste, **nenhuma cobrança real**, nenhum dano. O defeito de UX permanece.

**Consequência registrada:** a rodada de testes do alpha **depende** do botão de captura simulada.
Fechar a porta exige mover o adapter, não só apagar o botão: `mock_capture_allowed`
(`shopman/shop/services/payment.py:1891-1919`) só libera a captura quando o adapter efetivo do
método **é** o simulado. Caminho prescrito: **Pix → `payment_efi` com `EFI_SANDBOX=true`** +
`SHOPMAN_EXPOSE_MOCK_CAPTURE=false`. O botão fecha por construção e o alpha passa a ensaiar o
adapter real.

**Evidência:** `docs/reports/go-live-acceleration-20260929/06-checkout-pix-default.md`

---

## D-002 · Alterar pedido da loja online pelo operador

- **Estado:** `DECIDIDA`
- **Dono:** Pablo (produto) · execução: frente a definir
- **Data:** 2026-09-29 · **revisar_em:** 2026-10-31

**Decisão:** a semântica é **(i) cobrança pendente** — o operador cancela a cobrança aberta e
emite outra. Pedido **imediato também entra** (não só os com data).

**O que isso resolve, e o que ainda falta:**
- O mecanismo de edição **já existe** e não é exclusivo de encomenda: `Order` selado +
  `Order.data["adjustment"]`, um único escritor (`order_composition.record`) e um único
  caminho de leitura (`effective_items()`/`effective_total_q()`), regra em
  `shopman/shop/services/order_edit.py`, com estoque e cozinha reconciliados pelo mesmo
  caminho do `ORDER_PATCHED` do iFood.
- **Falta exposição**, não mecanismo — declarada fora de escopo em `ENCOMENDAS-PDV-PLAN.md:229`.
- **Falta capacidade nova em dois pontos:** cancelar cobrança digital hoje só tem porta pelo
  balcão (`counter_takeover`); e `order_edit` retorna antes de tocar em `payment` quando o
  valor não muda (`order_edit.py:413-414`). Trocar a **forma** (valor constante) é o caso que
  não existe.

**Evidência:** `docs/reports/go-live-acceleration-20260929/07-alterar-pedido-gestor.md`

---

## D-003 · Qual é a superfície de atendimento do cliente

- **Estado:** `DECIDIDA`
- **Dono:** Pablo (produto)
- **Data:** 2026-09-29 · **revisar_em:** 2026-12-31

**Decisão:** a **concierge é (será) o atendimento automatizado**; **hoje**, o atendimento é o
**PDV / aba Encomendas**, operado pela equipe.

**Consequências:**
- Para o caso real do WhatsApp (cliente pede troca de forma de pagamento), o caminho canônico
  **hoje** é **deep-link para o PDV/Encomendas**, não um editor novo no Gestor de Pedidos.
- O editor no Gestor nasce quando a concierge chegar — não antes.
- **Dinheiro não entra no fluxo remoto:** pedido da loja online **não oferece pagamento em
  dinheiro**; COD, troco e tratamento de dinheiro vivem na **encomenda anotada pelo operador**
  (PDV, aba Encomendas), que já tem sessão de caixa.

---

## D-004 · Sessão de PDV compartilhada entre dispositivos e custódia da gaveta

- **Estado:** `EM_EXECUCAO`
- **Dono:** Pablo (produto/operação) · apuração técnica: sessão em andamento
- **Data:** 2026-09-29 · **revisar_em:** 2026-10-15

**Pergunta registrada pelo dono (literal):**

> "Hoje, a mesma sessão do PDV pode ser acessada em diferentes dispositivos, por diferentes
> operadores, confere? Isso é bom, conforme a sincronia é respeitada pelo sistema. Mas se a
> sessão for a mesma, a gaveta de dinheiro é uma só, confere? (é o nosso caso.) Gostaria de
> sanar essa dúvida para que não haja brecha para má operação e fraudes."

**Por que está aqui e não numa conversa:** é pergunta sobre **dinheiro e responsabilização**.
A resposta precisa ficar em lugar durável, com evidência, porque a operação real é
**uma gaveta física** e **vários dispositivos**.

**APURADO em 2026-09-29.** Evidência:
`docs/reports/go-live-acceleration-20260929/14-sessao-pdv-multidispositivo.md` e
`15-gaveta-custodia-multidispositivo.md` (ambos com prova em runtime).

### Resposta

**1. Sim, a mesma sessão abre em vários dispositivos — nas duas leituras.**
Mesma **pessoa**: não existe "uma sessão por pessoa"; cada dispositivo que se identifica por
PIN/crachá abre a própria sessão Django, e as duas ficam vivas (provado: `unlock` 200 e
`GET /pos/` 200 nos dois, chaves distintas, nenhum derruba o outro). Mesmo **cookie**: a sessão é
cookie portador, **sem vínculo** com dispositivo, user-agent, IP ou estação — copiar o cookie para
outro cliente devolve 200. Em produção o cookie sai para `.boulangerie.com.br`, então vale em
`pdv.`/`gestor.`/`kds.`/`prod.` no mesmo navegador.

**2. O sistema não impede — detecta passivamente.** Sem limite de sessões, sem expulsão, sem alerta
em tempo real. Cada login vira `SignInEvent` (pessoa, método, estação, IP, UA) mais aviso in-app.

**3. A gaveta é do TERMINAL — nunca da sessão nem do operador.** A custódia é `cashman.Shift` com FK
para `Terminal` e `UniqueConstraint` de turno aberto por terminal
(`packages/cashman/.../models/shift.py:48-53`, `:83-87`). **`open_shift_for(operator)` não
existe.** Dois dispositivos provisionados como o **mesmo** balcão dividem **um** turno e **um**
livro: o segundo "abrir caixa" devolve **200 com o mesmo `shift_id`** e lança no turno do
primeiro, **sem aviso**. E isso é deliberado — `station_trust.provision` preserva os demais
vínculos do mesmo terminal (`shopman/backstage/station_trust.py:308-310`).

### O que protege (confiável hoje)

Turno único por terminal (constraint de banco) · `select_for_update` no livro e no fechamento ·
segundo fechamento recusado, lançamento pós-fechamento recusado, `update`/`delete` recusados ·
**sangria sempre com PIN/crachá gerencial e autoaprovação recusada** · fechamento só pela gerência ·
contagem cega por construção · o **corpo da requisição não escolhe a gaveta** (409 se divergir) ·
ambiguidade de terminal falha fechado · fechamento do dia é por **loja**, com alerta de turno
deixado aberto · limiar `bi_cash_variance` de R$ 50 em 7 dias **por gaveta**.

### Brechas (a preocupação de fraude tem fundamento)

- **G2 — o livro não registra o dispositivo.** O rastro responsabiliza **pessoa + terminal**, nunca
  dispositivo (`SignInEvent.station_ref` é o `Terminal.ref`, não o `TrustedDevice`). Dois tablets
  como `pdv-main` são **indistinguíveis** na trilha.
- **G8 — a falta de dinheiro não tem dono por desenho.** Uma gaveta, N mãos: o próprio código
  documenta isso, e o BI só nomeia operador quando o livro prova operador único.
- **G3/G4 — a trava da gaveta é verificada pelo navegador**, não pelo servidor; e o ociosidade que
  dispara a trava é medida no cliente. A trava por capability mora na **sessão**: cookie copiado
  herda a trava.
- **Hardware:** quem chuta a gaveta é o agente local na loopback de cada máquina
  (`pos_hardware.py:28`), com **o mesmo token** para os dois dispositivos. Dois dispositivos no
  mesmo terminal podem abrir **duas gavetas físicas diferentes** sob **um** registro de custódia.
- **B4 —** o X/Z aceita `terminal_ref` do query param sem validar contra a estação.
- **G7 —** a tela do PDV mostra "Lançado por / Editado por" a partir do campo `pos_authorship`, que
  **nenhum código escreve**. Promete responsabilização que não existe.
- **G8b —** `SHOPMAN_REQUIRE_ACTIVE_OPERATOR=true` está no spec e **nenhum código lê** (flag fantasma).

### Decisão pendente do dono

Se há **uma** gaveta física, as duas posturas coerentes são: **(a)** um dispositivo por terminal
(mais simples, casa com a gaveta única), ou **(b)** vários dispositivos no mesmo terminal **com
visibilidade** — aviso no provisionamento, "há N dispositivos neste balcão" na tela do caixa, e
dispositivo gravado no rastro. (b) é o caso real da loja.

**P0 recomendado (barato, pré-go-live):** gravar o id do `TrustedDevice` nos eventos de auditoria
(**zero migração** — o campo `data` JSON já existe e o `TrustedDevice` já está em mãos: é o que
torna auditoria de fraude verificável) · avisar no provisionamento quando o terminal já tem vínculo
ativo · mostrar "há N dispositivos neste balcão / caixa já aberto" na projeção do caixa · e remover
a flag fantasma do spec. Os dados para detectar **já existem** (`TrustedDevice.last_used_at` é
gravado a cada requisição) e ninguém usa: dois dispositivos ativos no mesmo balcão são detectáveis
**hoje**.

---

## Índice

| id | decisão | estado | revisar_em |
|---|---|---|---|
| D-001 | Forma de pagamento padrão na loja online | `DECIDIDA` | 2026-10-31 |
| D-002 | Alterar pedido da loja online pelo operador | `DECIDIDA` | 2026-10-31 |
| D-003 | Superfície de atendimento do cliente | `DECIDIDA` | 2026-12-31 |
| D-004 | Sessão de PDV multi-dispositivo e custódia da gaveta | `DECIDIDA` (resposta) + pendência do dono | 2026-10-15 |
| D-005 | Marketing/WhatsApp permanece ligado como está | `DECIDIDA` | 2026-10-31 |
| D-006 | Pix simulado permanece no alpha por ora | `ADIADA` | 2026-10-15 |
| D-007 | Postura de multi-dispositivo no mesmo balcão | `DECIDIDA` | 2026-12-31 |
| D-008 | Autoria por linha na comanda: implementar | `DECIDIDA` | 2026-12-31 |
| D-009 | Deploy na DO: só `create-deployment`, **nunca** `apps update` de arquivo | `DECIDIDA` | 2026-12-31 |
| D-010 | Cloudflare R2 para arquivos de usuário | `EM_EXECUCAO` | 2026-10-15 |
| D-011 | `DATABASE_CONN_MAX_AGE=0` no spec vivo (D21) | `DECIDIDA` (aplicada) | 2026-12-31 |
| D-012 | Receita: o padeiro pode fazer o que quiser (D11) | `DECIDIDA` | 2026-12-31 |
| D-013 | Receita: temperatura opcional, 92 etapas são rascunho, nota e "Fontes" (D19, D20, D24) | `DECIDIDA` | 2026-12-31 |
| D-014 | Recibo de envio crítico: reserva por e-mail e SMS só em evento crítico (D3) | `DECIDIDA` | 2026-10-31 |
| D-015 | Loja: forçar a versão nova, nunca durante pagamento (D9); trilho fora do `shell/` só se ninguém o exibe (D10) | `DECIDIDA` | 2026-10-31 |
| D-016 | Pix real se ENSAIA antes da virada; Efí, Stripe e Focus são as últimas a LIGAR | `DECIDIDA` | 2026-10-15 |
| D-018 | Triagem do Concierge aprovada (D32) | `EXECUTADA` | n/a |
| B-001 | Alpha SEM DEPLOY desde 29/09 21:31 UTC | `BLOQUEADA` | 2026-10-01 |

---

## D-007 · Vários dispositivos no mesmo balcão, com visibilidade

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto/operação) · **Data:** 2026-09-29 · **revisar_em:** 2026-12-31

**Decisão (D-004b):** com **uma** gaveta física e vários dispositivos, a postura é **(b) vários
dispositivos no mesmo terminal, com visibilidade** — não "um dispositivo por terminal".

**Consequências, todas no WP-2:**
1. Provisionar um segundo dispositivo no mesmo `Terminal.ref` **avisa e pede confirmação** — não
   recusa (recusar seria a postura (a)).
2. A tela do caixa mostra **"há N dispositivos neste balcão"** e **"caixa já aberto"**.
3. O dispositivo entra no rastro (é o WP-1, que não depende desta decisão, mas passa a ter um
   consumidor claro).
4. O Admin de terminais lista e permite revogar dispositivos (dados prontos, zero migração).

**Racional:** é a operação real da loja. A alternativa (a) tornaria o segundo tablet inútil e
exigiria reprovisionamento manual se um dispositivo morresse.

**Sequência definida:** CI primeiro (destravar `-n auto`), depois WP-3 → WP-1 → WP-4 → WP-2,
**uma sessão executora, sequencial**, um branch por WP.

---

## ✅ B-001 RESOLVIDO — 2026-09-30 18:21 UTC

**Deployment `3a3b0053-82c6-4a4a-b1c1-5e5e8c45718e` atingiu ACTIVE 29/29 às 18:21:28 UTC.**
O app voltou a deployar depois de **~21 horas** congelado.

**A correção:** devolver o bloco `databases` ao spec vivo (só `name` → os 6 campos), aplicado por
`doctl apps update --spec` com o spec obtido de `spec get`. **Diff: 2 linhas removidas, 12
adicionadas — e nada mais.** Segredos **intactos**: 31 de 31 idênticos, 167 envs com mesmo valor,
tipo, scope e ordem. Nenhum rollback necessário.

⚠️ **Contra a expectativa, o bloqueio anterior NÃO voltou.** O `release: DeployContainerExitNonZero`
(de 29/09 19:15–21:29) não reapareceu: `postgres`, `cache` **e** o job `release` passaram. **A causa
daquela falha anterior continua desconhecida** e resolveu sozinha — fica registrado como
**não explicado**, não como "corrigido".

**Efeito medido no cliente (home SSR, a queixa nº1):**

| | Antes (29–30/09) | Depois (steady state) |
|---|---|---|
| `/` (home) | 3,06–4,49 s | **0,65–1,18 s** |
| `/menu` | 3,79 s | **0,56–0,60 s** |
| `/sacola` | — | **0,31–0,78 s** |
| `/finalizar` | — | **0,38–0,87 s** |
| `/conta` | — | **0,42–0,71 s** |

**O que ainda NÃO está resolvido:** a rota **privada** `/api/v1/storefront/menu/` continua ~3,3 s
(`projection;dur=2718, availability;dur=1679, db;dur=613`). Ela não é cacheável por desenho (estado
de sessão). É a Onda 1 do `GO-LIVE-ACCELERATION-PLAN`: a disponibilidade calculada 4× por request,
o `home/` que constrói o catálogo inteiro, os índices ausentes. **O ganho de hoje veio de servir o
anônimo pela borda, não de o backend ter ficado rápido.**

**Método que valeu a pena registrar:** para inspecionar imagens do DOCR sem `docker` e sem o token
da API, use `doctl registry docker-config` + o intercâmbio de token em
`api.digitalocean.com/v2/registry/auth`.

---

## 🎯 B-001 · CAUSA RAIZ ENCONTRADA (2026-09-30 ~18:00 UTC)

**O `build` não falha ao puxar imagem. Ele falha ao CRIAR O BANCO.**

Passo que falha, texto exato: `deployment.progress.steps[0].steps[1].steps[8]`, nome
`build.components.postgres`, `message_base: "Creating database"`, componente `postgres`.
Em `859fccb3` falham **dois** passos: `postgres` **e** `cache`.

**A causa: o spec vivo perdeu o bloco `databases`.**

| | `databases` |
|---|---|
| Spec do repo (`.do/app.alpha-subdomains.yaml:1254-1266`) | `cluster_name`, `db_name`, `db_user`, `engine`, `production`, `version` |
| **Spec vivo hoje** | `- name: postgres` e `- name: cache` — **só isso** |

**Quando quebrou:** deployment `ded45b84`, **2026-09-29 21:47:34 UTC**, causa `app spec updated`
(`UPDATE_SPEC`), conta `pablondrina@gmail.com`. O mesmo update também **reordenou as variáveis de
ambiente** (`DJANGO_SECRET_KEY`, `STRIPE_*`, `EFI_*` mudaram de posição) — **é a explicação do
incidente em que as envs foram zeradas.** Foi um `apps update` com um spec que não era o vivo.

**Por que `restart` funciona e deploy novo não:** o deployment de sucesso (`9df9b42c`) tem
`cloned_from: c4fce115` — ele **copia** o deployment anterior, que ainda tinha o bloco completo.
Um deployment novo tenta provisionar o banco a partir do spec mutilado e falha.

**⚠️ Antes do `ded45b84` havia OUTRO bloqueio, ainda sem diagnóstico.** De 29/09 19:15 a 21:29, os
deployments falhavam com `release: DeployContainerExitNonZero` — o job `release` (migrate,
setup_groups, bootstrap) saindo com código diferente de zero. Consertar o bloco `databases` deve
trazer **esse** erro de volta. Ele é o próximo da fila.

**Correção:** devolver o bloco ao spec vivo. **Pela UI do console** (que trata os segredos), não por
`apps update` de arquivo — essa é a regra D-009, e foi um `apps update` que causou isto.

---

## B-001 · O alpha está sem deploy desde 29/09 21:31 UTC

### ✅ Descoberta decisiva (2026-09-30 17:20 UTC) — o `build` só falha quando precisa puxar imagem

| Causa do deployment | Passo `build` |
|---|---|
| `restarting app` (deployment `9df9b42c`) | **SUCCESS** — e o deployment ficou **ACTIVE** às 17:15:30 |
| `image tag X pushed` (todos os demais) | **ERROR 9/29** |

Isso isola o defeito: não é o app, não é o spec, não é o código. **É o caminho de puxar imagem
num deployment novo.**

**Verificado e descartado, um por um:** imagens íntegras (4 manifestos 200, blobs 307; método no
bloco abaixo) · não é transitório (10+ tentativas em 14 h) · não é cache de build
(`--force-rebuild` falha igual) · não é incidente global (status da DO: "All Systems Operational",
0 incidentes) · não é garbage collection travada (nenhuma ativa, nenhuma no histórico) · não é tag
ausente · não é credencial de criação (os deployments nascem `PENDING_BUILD` normalmente).

**Mudança de estado conseguida:** `doctl apps restart` tirou o app do estado *automated rollback*.
Hoje ele roda `9df9b42c` (causa "restarting app", ACTIVE, build e deploy SUCCESS) — mais saudável,
**mas com código antigo**: as rotas do PR #1285 dão 404 e a home não tem o `Server-Timing` do #1283.

**Caminho recomendado:** trocar as **tags mutáveis por digest imutável** pela **UI do console**, que
preserva os segredos. Digests já verificados:
`web` `sha256:9b9f67e3…` · `storefront` `sha256:9a8c6734…` · `operator-floor` `sha256:19cea762…` ·
`operator-office` `sha256:eed9460d…` (8 componentes no total).

⚠️ **NUNCA faça `doctl apps update --spec` com o spec obtido de `doctl apps spec get`.** Os valores
SECRET voltam **criptografados** (`EV[…]`) e o DO rejeita:
`secret env value must not be encrypted before app is created`. **É quase certamente a explicação
do incidente em que as variáveis de ambiente foram zeradas.** Para mexer no spec, use a UI do
console — que trata os segredos — ou forneça os valores em texto puro.

- **Estado:** `BLOQUEADA` · **Dono:** Pablo (credencial) · **revisar_em:** 2026-10-01

**O que está acontecendo.** O deployment **ATIVO** é `c4fce115`, criado em **2026-09-29 21:31:37 UTC**,
cuja causa registrada é `automated rollback after failed deployment of b991ce46`. Desde então,
**todo** deployment falhou:

```
2026-09-30 10:34 ERROR 9/29   09:43 ERROR 9/29   09:17 ERROR 9/29   07:32 ERROR 9/29
2026-09-30 04:05 ERROR 9/29   02:56 ERROR 9/29   02:29 ERROR 9/29   (+ CANCELED 0/29)
```

O passo que falha é **`build`**, com `InternalError: An internal error occurred. Contact support if
this persists.` — **erro da própria DigitalOcean, não do nosso código.** A imagem existe: a tag
`web` foi publicada às 10:33:58 e o deployment nasceu 9 s depois.

**Impacto medido (2026-09-30 11:25 UTC):** as rotas novas do cache de borda respondem **404** em
produção; `menu/` continua 3,37 s com `cf-cache-status: BYPASS`; home SSR 3,06–3,72 s. Os 10 PRs
mergeados hoje estão em `main` e **nenhum está no ar**. **Go-live é impossível enquanto isto durar.**

**Ação tentada em 2026-09-30 12:08–12:10 UTC — e o resultado importa:**

| Tentativa | Resultado |
|---|---|
| `doctl apps create-deployment` (contexto `shopman-do-app-admin`) | `a124f184` → **ERROR 9/29** |
| `doctl apps create-deployment --force-rebuild` | `ff76afbf` → **ERROR 9/29** |
| As 4 tags que o spec referencia existem no DOCR? | **Sim** — `web` (189 MB), `storefront` (79 MB), `operator-floor`, `operator-office` |

Ou seja: **não é transitório, não é cache de build, não é imagem ausente e não é credencial de
deploy.** O passo `build` falha de forma determinística com erro do provedor. **Escalar para o
suporte da DO** — os recursos do nosso lado estão esgotados.

⚠️ O contexto `default` do `doctl` **não tem token** (`access token is required`), e isso é
**deliberado**: um default com token ou lê mentira (se for cego a bancos) ou escreve sem querer (se
tiver escrita). **Default que falha alto é o default correto** — ele obriga a dizer o que se quer.
Quem tem escrita é o **`shopman-do-app-admin`** (era `shopman-spec-update`; renomeado em 30/09/2026
porque o nome antigo nomeava o comando perigoso — `apps update`). Use
`doctl --context shopman-do-app-admin`, e **apenas** `create-deployment` — nunca `apps update`
(ver D-009).

**⛔ Não é possível abrir o chamado programaticamente** (verificado em 2026-09-30):
`doctl` **não tem** subcomando de support/ticket (ausente da árvore de comandos), e
`GET`/`POST https://api.digitalocean.com/v2/support/tickets` devolve
`404 {"id":"not_found","message":"Your request could not be routed."}` — a DigitalOcean não expõe
criação de chamado na API pública. **O chamado tem de ser aberto no console**
(`cloud.digitalocean.com` → Support → Create ticket). Não perca tempo com a API.

### ❌ Pista das camadas — REFUTADA em 2026-09-30 12:40 UTC (não persiga isto)

**O que foi testado e como** (método reutilizável, sem `docker` e sem o token da API):
`doctl registry docker-config` (funciona mesmo quando não se consegue extrair o token da API) dá a
credencial do registry; o desafio `WWW-Authenticate` aponta para
`https://api.digitalocean.com/v2/registry/auth`; trocando ali por um token de pull e consultando a
API v2 do registry, lê-se o manifesto real e testa-se o blob.

**Resultado — as quatro imagens do spec estão íntegras:**

| Tag | Manifesto | Camadas | Soma real das camadas | Blob da 1a camada |
|---|---|---|---|---|
| `web` | 200 | 16 | 189.066.796 B | 307 (existe) |
| `storefront` | 200 | — | — | — |
| `operator-floor` | 200 | 12 | 71.400.223 B | 307 (existe) |
| `operator-office` | 200 | — | — | — |

`307` é redirect para o storage do blob: se o blob não existisse, seria `404`.

**Portanto: o `0 B` que o `doctl registry repository list-manifests` mostra em várias imagens é
artefato de relatório, não imagem quebrada.** `operator-floor` tem 71 MB de camadas, não zero.
**Não republicar nada por causa disso, e não citar o `0 B` no chamado** — mandaria o suporte atrás
de uma pista falsa. A causa do `build` falhar continua **desconhecida** e é do lado do provedor
ou do spec, não das imagens.

---

### 🔎 Hipótese original (mantida só como histórico) — camadas possivelmente ausentes

`doctl registry repository list-manifests shopman` mostra assimetria exata entre as imagens que
funcionam e as do caminho que falha:

| Imagem | Comprimido | Descomprimido |
|---|---|---|
| `web` | **189,08 MB** | 666,23 MB |
| `storefront` | **79,02 MB** | 199,40 MB |
| `operator-floor` | **0 B** | 195,94 MB |
| `operator-office` | **0 B** | 193 MB |
| (per-app: `purchase`, `production`, `hub`, `orders`, `marketing`) | **0 B** | 173–196 MB |

Manifesto com descomprimido conhecido e comprimido zerado é assinatura de camada que não subiu —
e o spec referencia **justamente** `operator-floor` e `operator-office`.

⚠️ **Não está provado.** A alternativa é que o DO reporte `0 B` para manifestos com camadas
deduplicadas (as imagens de operador compartilham base; `web`/`storefront` são únicas). O teste
decisivo seria ler o manifesto pelo registry v2 e conferir os blobs, e **não consegui extrair o
token do `doctl`** (0 caracteres em duas tentativas).

**Teste que decide, e é nosso:** republicar `operator-floor` e `operator-office` pelo
`deploy-images.yml` (`workflow_dispatch`, `components=operator-floor,operator-office`). Tamanho
normal + deploy passando ⇒ a causa é nossa e o suporte era desnecessário. `0 B` de novo ⇒ é do
registry/provedor e o chamado se sustenta.

**Chamado ao suporte da DO — conteúdo:** app `shopman-nelson` (id `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`).
Todo deployment desde 2026-09-29 21:31 UTC falha no passo `build` com
`InternalError: An internal error occurred`. Deployment ativo é `c4fce115` (automated rollback).
Reproduzido manualmente às 12:08 e 12:10 UTC (deployments `a124f184` e `ff76afbf`), inclusive com
`--force-rebuild`. As imagens DOCR referenciadas pelo spec (`shopman:web`, `shopman:storefront`,
`shopman:operator-floor`, `shopman:operator-office`) existem no registry. Pedimos investigação do
motivo do `build` falhar para este app.

---

## D-009 · Deploy na DO: só `create-deployment`, nunca `apps update` de arquivo

- **Estado:** `DECIDIDA` · **Dono:** Pablo (operação) · **Data:** 2026-09-30 · **revisar_em:** 2026-12-31

**Contexto.** O dono relatou que uma tentativa parecida com um redeploy **"acabou zerando as
variáveis de ambiente lá na DO"**. A verificação encontrou a explicação e a regra que a previne.

**A distinção que importa** (conferida em `doctl apps create-deployment --help`):
- `doctl apps create-deployment <app-id>` aceita **apenas** `--force-rebuild`, `--format`,
  `--no-header`, `--wait`. **Não há flag de spec.** Ele republica a partir do spec que já está
  **no servidor**, e por isso **não pode zerar variável de ambiente**.
- **O perigo é `doctl apps update`** (e `create-deployment --upsert`), que envia um **spec
  inteiro** e **substitui a configuração viva**. O suspeito do incidente é aplicar
  `.do/app.subdomains.yaml`, que é **blueprint, não o spec vivo** — ele tem `STORE_DOMAIN` no
  lugar do domínio real (`docs/runbooks/conferir-spec-digitalocean.md:158-163`). Aplicá-lo
  trocaria cada env por placeholder ou ausência. Já houve incidente análogo registrado em
  `.do/app.alpha-subdomains.yaml` ("`alpha.` e `staging.` estão MORTOS… já aconteceu uma vez,
  por um update feito a partir de snapshot velho").

**Regra.** Para republicar: **`create-deployment`, e só.** `apps update` a partir de arquivo exige
conferir o spec vivo na hora (`doctl apps spec get`) e diff contra o arquivo antes — nunca aplicar
o blueprint.

**Backup feito antes de qualquer tentativa:** `/tmp/shopman-live-spec-ANTES-REDEPLOY-20260930-1204.yaml`
(40.666 B, 167 chaves, 8 componentes). Contém valores SECRET: **não versionar**.

**Achado colateral — drift entre o spec vivo e o versionado:** 167 chaves no vivo contra 176 no
`.do/app.alpha-subdomains.yaml`. Faltam no vivo, ao menos:
- `SHOPMAN_BFF_PROXY_SECRET` — **de segurança**: é ele que prova ao Django que o pedido veio do BFF,
  para o IP gravado ser o do cliente. Sem ele, rate limit e auditoria por IP ficam errados.
- `FOCUS_NFE_ENVIRONMENT` — ausente, então cai no default `homologacao`.

---

## D-008 · Autoria por linha na comanda: **implementar** (opção A)

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto) · **Data:** 2026-09-29 · **revisar_em:** 2026-12-31

**Decisão:** em vez de remover da tela, **implementar** a autoria por linha.

**O defeito que isso corrige:** a tela do PDV mostra "Lançado por / Editado por" em cada linha da
comanda a partir de `Session.items[i]["meta"]["pos_authorship"]`. O campo **nunca é escrito por
ninguém** — o único código que o toca é a leitura
(`shopman/backstage/api/pos_concurrency.py:70-72`), o tipo
(`surfaces/pos-nuxt/app/types/pos.ts:584`) e a renderização
(`surfaces/pos-nuxt/app/components/PosCartPanel.vue:993-1017`). Em produção é sempre vazio. Os
testes de componente passam porque alimentam a fixture à mão
(`PosCartPanel.test.ts:523`, `:571`).

**Racional do dono:** com **uma gaveta e várias mãos**, a responsabilização por linha é o que
protege — é a mesma preocupação que originou a pergunta sobre a sessão de PDV (D-004).

**Restrições de desenho (do WP-1):** um único escritor, no ponto que já é dono da identidade da
linha (`shopman/shop/services/pos_intent.py:330-386`) — **não** no decorator `tab_command`;
`created_*` imutável e `updated_*` a cada mudança; **snapshot do nome legível no momento do ato**
(`created_label`/`updated_label`), porque renomear a pessoa depois não pode reescrever a história;
identificador estável em `created_by`; chaves documentadas em `docs/reference/data-schemas.md`
antes do uso.

---

## D-005 · Marketing/WhatsApp permanece ligado como está

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto) · **Data:** 2026-09-29 · **revisar_em:** 2026-10-31

**Decisão do dono:** *"marketing via whatsapp tem suas próprias barreiras de segurança, nada
será disparado sem querer. deixa como esta."*

**Verificado — o dono está certo:** `SHOPMAN_MARKETING_WHATSAPP_MODE=open` é **teto de
elegibilidade**, não gatilho. Nada sai sem campanha **aprovada** (`marketing_approval.py`), que
recusa por `audience_degraded` e por mínimo de audiência da loja; a serialização do ADR-009
(emenda 17/09) garante uma mensagem com flow por assinante por vez, e a ausência de cache
compartilhado derruba `canary`/`open` para falha fechado
(`shopman/shop/services/manychat_marketing_safety.py:16-29`).

**Correção de registro:** o diagnóstico inicial classificou isto como "o único risco
irreversível aberto" e recomendou desligar. **Era exagero.** Nenhuma ação pendente.

---

## D-006 · Pix simulado permanece no alpha por ora

- **Estado:** `ADIADA` · **Dono:** Pablo (produto) · **Data:** 2026-09-29 · **revisar_em:** 2026-10-15

**Decisão do dono:** *"como ainda estamos em alpha, vou manter o pix com a simulação de
pagamento mais um pouco."*

**Consequência registrada:** enquanto durar, `SHOPMAN_EXPOSE_MOCK_CAPTURE=true` +
`SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` com Pix em `payment_mock` mantêm, no ar, a
afordância de captura simulada. Isso é **aceitável em alpha e bloqueador em produção** — a
promoção para produção (K2 do caminho crítico) tem de mover o adapter para `payment_efi`.

**Prescrição preservada para quando a hora chegar** (não desligar só a flag, porque se perde a
capacidade de testar): **Pix → `payment_efi` com `EFI_SANDBOX=true`** +
`SHOPMAN_EXPOSE_MOCK_CAPTURE=false`. `mock_capture_allowed`
(`shopman/shop/services/payment.py:1891-1919`) exige que o adapter efetivo do método **seja** o
simulado, então o botão fecha **por construção** e o alpha passa a ensaiar o adapter real.

---

## D-010 · Cloudflare R2 para arquivos de usuário

- **Estado:** `EM_EXECUCAO` · **Dono:** Pablo (operação) · **Data:** 2026-10-01 · **revisar_em:** 2026-10-15

**Contexto.** O contêiner da DigitalOcean não tem disco persistente e o spec não declara volume
nem Spaces: arquivo salvo hoje some no próximo deploy, e a foto que o `/recipes/new` manda
evapora (`docs/reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md`, D6). As
opções eram DO Spaces, volume, ou só links externos (este último já entrou no #1332).

**Decisão do dono:** Cloudflare R2 (fala a API do S3) para os arquivos de usuário. Não é
componente novo na DO, e respeita a regra da casa sobre custo da conta DO.

**Consequência.**
- O código está pronto e **desligado**: `SHOPMAN_MEDIA_STORAGE` vazio ou `local` mantém o disco
  de hoje; `SHOPMAN_MEDIA_STORAGE=r2` troca `STORAGES["default"]` por `S3Storage` no endpoint
  `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`, região `auto`.
- Envs lidas: `SHOPMAN_MEDIA_STORAGE`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY` e, opcional, `R2_URL_EXPIRE_SECONDS` (padrão 3600).
- Bucket **privado**, link assinado com validade (o R2 não tem ACL por objeto); arquivo com o
  mesmo nome não sobrescreve. Ligado sem credencial, o boot cai com `ImproperlyConfigured`
  listando o que falta, nunca volta em silêncio ao disco.
- O estático segue no WhiteNoise, sem mudança.
- Ligar no alpha pede: o dono criar bucket e token (`docs/runbooks/r2-passo-a-passo-do-dono.md`),
  colar os segredos no painel da DO, e a palavra dele para pôr a flag em `r2`.

**Prova.** PR `feat/storage-r2-desligado`; `config/settings.py:581` (`"default": media_storage()`),
`config/media_storage.py:55-103`, testes em `shopman/shop/tests/test_media_storage.py`.

---

## D-011 · `DATABASE_CONN_MAX_AGE=0` no spec vivo

- **Estado:** `DECIDIDA` (aplicada) · **Dono:** Pablo (operação) · **Data:** 2026-10-01 · **revisar_em:** 2026-12-31

**Decisão do dono:** autorizou a escrita no spec vivo para o degrau 1 do D12 (pergunta D21), com
protocolo. É exceção autorizada à D-009 (que proíbe `apps update` **de arquivo**): o update foi
feito a partir do próprio spec vivo, mudando uma linha, como no D14.

**Prova.** Drift `[OK]` antes; backup do vivo; diff de uma linha (`133c133`, `"60"` → `"0"`);
`apps update` → deployment `c4f07630` ACTIVE; 42 SECRET idênticas antes e depois (chave a chave);
`/health/live/` e `/health/ready/` 200; `connect;dur` no `shell/` (n=10) 42,5 → 37,4 ms (ruído).
Arquivos versionados seguiram no PR #1334 (mergeado), e o drift voltou a `[OK]`. Os workers
recebem o mesmo 0 e reconectam por ciclo (já chamavam `close_old_connections()`).

---

## D-012 · Receita: o padeiro pode fazer o que quiser

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto) · **Data:** 2026-10-01 · **revisar_em:** 2026-12-31

**Decisão do dono (D11):** versão publicada ou substituída volta a poder ser editada e apagada por
qualquer caminho normal, inclusive em cascata. O cofre continua guardando as versões.

**Prova.** PR #1338: as recusas do #1308 saíram de
`packages/craftsman/shopman/craftsman/models/recipe_book.py`; a impressão digital do "fora de
sincronia" fica; `restoring_recipe_versions()` saiu junto (sem trava não há o que destravar), e o
backup restaura versões (`shopman/shop/tests/test_backup.py`). Emenda no ADR-027.

---

## D-013 · Receita: temperatura opcional, rascunho das massas, nota e "Fontes"

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto) · **Data:** 2026-10-01 · **revisar_em:** 2026-12-31

**Decisão do dono.** D19: o operador só lê a etapa; temperatura é campo opcional da etapa, sem
templates; anotação na versão. D20: as 92 etapas das 11 massas são rascunho do Claude, não dado
da casa. D24: rascunho pode receber nota; avaliar de novo substitui a nota do mesmo operador;
notas, critérios e fontes entram no backup; o bloco se chama "Fontes".

**Prova.** PR #1338: `temperature_celsius` em `packages/craftsman/shopman/craftsman/recipe_steps.py:36`;
aviso no topo de `docs/reference/processo-das-massas-proposta-2026-09-05.md` e trava em
`shopman/shop/tests/test_seed_sem_processo_das_massas.py`; abas `recipe_rating_criteria` e
`recipe_version_ratings` em `shopman/backstage/backup_resources.py:125` e `:159`. "Referência" já
nomeava a faixa da literatura (`FormulaLens.vue`), por isso "Fontes"; a chave interna segue
`external_references` porque `sources` colidiria com `RecipeVersion.source`.

---

## D-014 · Recibo de envio crítico

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto) · **Data:** 2026-10-01 · **revisar_em:** 2026-10-31

**Decisão do dono (D3):** e-mail e SMS podem sair sozinhos como reserva quando o WhatsApp não
confirmar, só em evento crítico, e é preciso recibo.

**Consequência.** Aceite sem identificador do provedor deixa de ser entrega; em evento crítico a
cadeia segue para o próximo canal, inclusive depois de resposta ambígua. Críticos hoje:
`payment_link_sent` e `order_accepted` (`CRITICAL_NOTIFICATION_TEMPLATES`,
`shopman/shop/services/notification.py:49`). O operador vê o recibo no detalhe do pedido do
Gestor ("Avisos ao cliente"); crítico sem comprovante abre alerta. ManyChat e Comtele não devolvem
identificador: o `Message-ID` do e-mail é hoje o único comprovante. Explicação para operador em
`docs/reference/comprovante-de-entrega.md`.

**Prova.** PR #1339.

---

## D-015 · Loja: forçar a versão nova (D9) e o trilho de sugestão no `shell/` (D10)

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto) · **Data:** 2026-10-01 · **revisar_em:** 2026-10-31

**Decisão do dono.** D9: forçar. Versão nova aplicada na navegação e, fora de checkout, pedido e
login, aviso que bloqueia a tela; nunca durante pagamento. D10: omotenashi primeiro; o trilho sai
do `shell/` só se nenhuma tela que consome o `shell/` o exibe.

**Prova.** PR #1341 (mergeado). Rotas protegidas em
`surfaces/storefront-nuxt/app/presentation/pwaRuntime.ts:53-56` (`/finalizar`, `/pedido/<ref>`,
`/entrar`, `/a`), travadas por `tests/pwaRuntime.test.ts` e `tests/components/pwaUpdatePrompt.test.ts`.
D10: o trilho **não** saiu do `shell/`, porque a `/sacola` exibe `cart.upsell` vindo do `shell/` na
primeira pintura (`app.vue:32`, `pages/sacola.vue:302`). Pela regra do dono, parou aí (D31).

---

## D-016 · Pix real se ensaia antes da virada

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto) · **Data:** 2026-10-01 · **revisar_em:** 2026-10-15

**Decisão do dono.** Efí, Stripe e Focus são as últimas chaves a **ligar**, não as últimas a
**ensaiar**. O botão público de quitar o próprio pedido (Pix simulado, D-006) não fecha hoje, mas
o ensaio do Pix real (`payment_efi` com `EFI_SANDBOX=true` + `SHOPMAN_EXPOSE_MOCK_CAPTURE=false`,
que fecha o botão por construção) tem de acontecer ANTES da virada, junto da rotação do
`EFI_WEBHOOK_TOKEN` (D22).

**Prova.** Item no `docs/runbooks/go-live-preflight.md` §4 e regra de parada no
`docs/runbooks/go-live-cutover.md` §0 (PR #1336, mergeado).

---

## D-017 · Escopo do go-live: fora só Marketing e B.I.

- **Estado:** `DECIDIDA` · **Dono:** Pablo (produto) · **Data:** 2026-10-01 · **revisar_em:** 2026-10-15

**Decisão do dono.** A proposta de corte (#1336, D28), que deixava fora entrega própria, WhatsApp
conversacional, catálogos externos e media persistente, foi **recusada**. Ficam fora do go-live só
**Marketing** e **B.I.** Entra todo o resto, explicitamente a **entrega por parceiro** (TaOn/Machine,
`shopman/shop/adapters/courier_machine.py`) e o **Concierge**, com a razão do dono: "a equipe está
defasada e a triagem das mensagens será muito útil". O Concierge é a interface conversacional da loja
online (visão no `docs/plans/WHATSAPP-CONCIERGE-PLAN.md`); a triagem é proposta na D32.

**Prova.** PR #1344: `docs/plans/GO-LIVE-SCOPE-CUT-PROPOSTA.md` (decisão com custo e dependência
externa de cada frente que voltou), `docs/plans/PRODUCT-V1-SCOPE-BACKLOG.md` (regra do go-live),
`docs/plans/WHATSAPP-CONCIERGE-PLAN.md` (visão, fases, distância, checklist para ligar).

---

## D-018 · Triagem do Concierge aprovada

- **Estado:** `EXECUTADA` · **Dono:** Pablo (produto) · **Data:** 2026-10-02

**Decisão do dono.** *"aprovo a triagem"*: a proposta da D32 (opção 1, triagem completa), sem
redesenho. Toda mensagem recebe uma das 12 intenções aprovadas em 23/09
(`shopman/storefront/concierge/intent_pilot.py`, `DEFAULT_INTENTS`) e uma urgência (agora, hoje,
pode esperar). O Concierge responde sozinho horário e entrega, como funciona a casa, produto sem
alergia, status do pedido e pedido simples (fase 1: com o link da loja). Escalam sempre para uma
pessoa: pedido de pessoa, reclamação, alergia, encomenda especial e o pedido que o chat não fecha.
Vaga, parceria e fornecedor vão para a "outra mesa", no Admin, sem acordar o balcão. O operador vê
um cartão com intenção, urgência e resumo de uma ou duas linhas no sino do Gestor de pedidos.

**Prova.** PR #1347: `shopman/storefront/concierge/triage.py` (tabela, regra local, modelo
opcional, resumo), ligado no turno em `shopman/storefront/concierge/service.py` (`run_turn`),
cartão `concierge_handoff` no público de pedidos (`shopman/backstage/models/alerts.py`,
`ORDER_TYPES`) e `concierge_other_desk` na operação geral; filtro "triagem" no Admin da conversa;
system check `SHOPMAN_W022`/`SHOPMAN_W023` e `manage.py concierge_check` (`shopman/storefront/checks.py`).
Testes em `shopman/storefront/tests/test_concierge_triage.py`. Ligar continua sendo do dono, no
painel, pela sequência do `docs/plans/WHATSAPP-CONCIERGE-PLAN.md`.

