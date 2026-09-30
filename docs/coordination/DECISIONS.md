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

## B-001 · O alpha está sem deploy desde 29/09 21:31 UTC

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

**Ação:** `doctl apps create-deployment 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f` (token com escrita).
Se falhar igual, tentar com `--force-rebuild`; persistindo, abrir chamado no suporte da DO —
o erro é do provedor e persiste há mais de 12 h.

⚠️ O token de `doctl` disponível para agentes é **somente-leitura** (`403 You are not authorized`
em `create-deployment`). A ação exige credencial do dono.

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
