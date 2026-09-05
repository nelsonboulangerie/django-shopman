# Verificação cética dos 17 "P0" de UX (04-storefront-ux · 05-operator-ux)

Encargo: reauditar os 5 P0 de `04-storefront-ux.md` e os 12 P0 de `05-operator-ux.md`
contra **uma única régua** — a mesma usada pelo auditor de dinheiro/lifecycle, que
fechou com **zero P0**. Leitura estática, read-only, nenhum teste executado.

Régua aplicada:

- **P0** — bloqueia go-live: perde dinheiro, corrompe dado, fura segurança, ou torna uma
  tarefa diária central **impossível sem contorno**.
- **P1** — tarefa central degradada, confusa, ou exige um contorno que o operador/cliente
  precisa descobrir sozinho.
- **P2** — polimento, inconsistência, caso de borda.

Feio, jargão e falta de estado vazio **não são P0**. Dado velho apresentado como vivo
**pode** ser P0 quando agir sobre ele custa dinheiro ou comida — julgado caso a caso.

---

## Tabela de verdicts

| # | Claim (curto) | Superfície | Verdict | Severidade corrigida | Evidência |
|---|---|---|---|---|---|
| S1 | Home vendida com 7 fotos Unsplash de outra padaria | storefront | OVERSTATED | **P1** | `surfaces/storefront-nuxt/app/components/HomeHeroThing.vue:36-39` + `app/pages/index.vue:65,314,341` — fato confirmado. Não perde dinheiro, não corrompe dado, não fura segurança. Licença Unsplash **permite** uso comercial. `config/settings.py:1580` libera `img-src https:` — não há bloqueio de CSP. |
| S2 | "Loja fechada agora" calculado e jogado fora pela tela | storefront | **DUPLICATE** | **P1** | Gêmeo literal: `02-storefront-contract.md:329-336` **P1-12**, mesmo arquivo, mesma linha (`app/pages/index.vue:43`), mesma conclusão — e classificado **P1** lá. Ver §S2 abaixo para o que mais o auditor perdeu. |
| S3 | Barra de resumo do checkout coberta pela bottom-nav | storefront | OVERSTATED · NEEDS-BROWSER | **P2** | Fato do CSS confirmado (`app/pages/finalizar.vue:1851` e `app/components/AppBottomNav.vue:29`, ambos `fixed inset-x-0 bottom-0 z-40`; nav depois no DOM em `app/app.vue:78,80`). **Consequência errada** — ver §S3. |
| S4 | `debug_otp_code` impresso na tela = sequestro de conta | storefront | **REFUTED** | **P2** | `shopman/storefront/api/auth.py:431-446` falha fechado em três camadas; sem `SHOPMAN_DEBUG_OTP_TOKEN` (ausente de **todos** os `.do/*.yaml`) o `SHOPMAN_EXPOSE_DEBUG_OTP='true'` do alpha é **inerte**. `01-security.md:811-815` já verificou e absolveu. |
| S5 | Privacidade/Termos sem aval do dono | storefront | **CONFIRMED** | **P0** | `app/pages/privacy.vue:10-11` e `app/pages/terms.vue:8-15` — o próprio código declara o bloqueio. Linkadas do rodapé de toda tela; art. 9º LGPD + Decreto 7.962/2013. Único P0 sobrevivente dos 17. |
| O1 | Gerente assina sangria sem ver o valor | pos-nuxt | OVERSTATED | **P1** | `app/presentation/managerAuth.ts:41-64` e `app/components/PosManagerAuthDialog.vue:103-104` — só `title`+`reason`, confirmado. Mas ver §O1: o modal é deliberadamente sobreposto à tela onde o valor foi digitado (`PosManagerAuthDialog.vue:96`), e a brevidade da copy é **decisão registrada do dono** (`managerAuth.ts:33-38`). |
| O2 | Falha de insumo ao INICIAR não mostra nada | production-nuxt | **REFUTED** | **P2** | `ProductionStockShortError` é levantado **só** em `apply_finish` (`shopman/backstage/services/production.py:433`); `ProductionOrderShortError` só no guardrail de **plan** (`:691`). `apply_start` (`:213-239`) não levanta nenhum dos dois. `parseShortage` (`surfaces/production-nuxt/app/presentation/production.ts:267-277`) só reconhece esses dois códigos → em `start`/`advance-step` o `post()` **sempre** cai no `useSonner.error` (`useProductionBoard.ts:55`). O ramo faltante é código morto. |
| O3 | Quiosque não vira o dia | production-nuxt | OVERSTATED | **P1** | `ProductionStageGrid.vue:72-73` e `pages/mise-en-place.vue:16-19` são constantes — fato confirmado. Mitigações não vistas: a data completa aparece **duas vezes** na tela (`ProductionStageGrid.vue:466-468` e no diálogo de planejar, `:692`), e `defaultPlanningDate` (`useProductionBoard.ts:16-20`) já aponta para **amanhã** depois do meio-dia — ou seja, a tela deixada ligada de tarde amanhece no dia **certo**. |
| O4 | Menuboard NUNCA se atualiza | production-nuxt | OVERSTATED | **P1** | `pages/menuboard.vue:27-30` — `useFetch` sem poll/SSE, confirmado. Mas `:1-8` declara a página **demo** ("Quando o menuboard virar produto, este demo converge para o plano do catalog hub"). Preço não muda no dia; o que congela é o `ESGOTADO`. |
| O5 | Um blip mata o menuboard de forma permanente | production-nuxt | **REFUTED** (e gêmeo do O4) | **P2** | Contradiz o próprio O4: **não existe refetch**, logo `error` só pode ser setado no fetch inicial — quando `pages` está vazio de qualquer jeito. O `v-else-if="error"` (`menuboard.vue:143`) **nunca** troca um cardápio já pintado. Sobra a copy falsa ("reconectando…" sem reconexão), que é o mesmo defeito do O4. |
| O6 | Timer do forno não toca depois de recarga | production-nuxt | OVERSTATED | **P1** | `useOvenTimers.ts:33-50` (`load`) não chama `unlockAudio()`; `chime()` faz `if (!audio) return` (`:88`) e `audio` só nasce em `arm()` (`:119`) — fato confirmado. Mas `:1-4` declara o timer **auxiliar**, com o guardrail real de esquecimento no sino de alertas, e `expedite.vue:612-614` (`.qc-ringing`) mantém o sinal visual. |
| O7 | Alarme depende da aba em primeiro plano | production-nuxt | **NEEDS-BROWSER** · gêmeo do O12 | **P2** | Throttling de `setInterval` em aba oculta e sono do aparelho não se lêem do fonte. O próprio texto do achado diz "combina com o P0 do wakeLock" — é o mesmo fato contado duas vezes. |
| O8 | `accepted` perde a cor de status | orders-nuxt | OVERSTATED | **P2** | `app/presentation/board.ts:16-26` tem `confirmed` e não tem `accepted`; o canônico é `accepted` (`packages/orderman/shopman/orderman/models/order.py:37`) — fato confirmado, resíduo real de rename. Mas `OrderCard.vue:175-176` renderiza `card.status_label` **dentro** do badge: o operador lê a palavra certa; só o tom fica neutro. Cosmético. |
| O9 | Disparar campanha sem confirmação | marketing-nuxt | OVERSTATED | **P2** | `FireCampaignPanel.vue:376-384` não tem passo de confirmação — fato. Mas já é o clique terminal de um fluxo deliberado: sheet dedicado (`pages/campaigns.vue:246-266`), texto e público escolhidos à mão, contagem de pessoas ao vivo com `aria-live` (`:311-361`), e botão travado durante o envio (`:378`). |
| O10 | Retentativa duplica o disparo da campanha | marketing-nuxt | **DUPLICATE** | **P1** | Gêmeo: `03-backstage-contract.md:526-535` **P1-19**, mesmo endpoint, mesma causa, e o contract auditor já registrou que "the client double-click guard is correct". Classificado **P1** lá. |
| O11 | Confirmar entrada duplica estoque e custo | purchase-nuxt | **REFUTED** | **—** | O auditor leu a **view** (`shopman/backstage/api/purchase.py:72`) e parou. A view delega para `purchase_service.confirm_receipt`, que envolve a escrita em `run_idempotent_mutation(scope=RECEIPT_IDEMPOTENCY_SCOPE, key=source_ref)` (`shopman/backstage/services/purchase.py:195-198`), trata `RemoteMutationInProgress` (`:199-204`) e responde "Esta nota já entrou em X por Y" no replay (`:206-214`, `_receipt_already_received_message` `:219-227`). `source_ref` é determinístico nos dois modos (chave da NF, ou hash de fornecedor+nota+linhas em `_manual_source_ref` `:1306-1325`). |
| O12 | Nenhuma superfície pede `wakeLock` | operator-kit | **NEEDS-BROWSER** | **P2** | Zero ocorrências confirmadas em `surfaces/`. Mas "todos apagam pela política do sistema" é **suposição sobre configuração de aparelho**, não fato do código: TV e tablet de quiosque se configuram no SO, e nenhum `wakeLock` de browser controla um televisor. Melhoria real, não defeito. |

**Contagem:** CONFIRMED 1 · OVERSTATED 8 · REFUTED 4 · DUPLICATE 3 · NEEDS-BROWSER 1.

---

## O que cada auditor errou (por claim rebaixada)

### S1 — Unsplash
O fato está certo e vale corrigir. Três coisas empurraram a severidade para cima
indevidamente: (a) a licença Unsplash **autoriza** uso comercial, então o argumento
jurídico não existe; (b) `config/settings.py:1580` já libera `img-src https:` — não há
bloqueio de CSP a descobrir; (c) o comentário imediatamente acima do bloco citado
(`HomeHeroThing.vue:32-35`) declara que é o **conjunto neutro de referência**, pareado com
o hero Django para comparação de composição — o código sabe que é provisório. Constrange
a marca; não bloqueia go-live pela régua do dinheiro.

### S2 — "Loja fechada"
Duplicata de `02-storefront-contract.md` P1-12, e o contract auditor calibrou melhor.
Além disso, dois fatos derrubam a narrativa do "só descobre no checkout":

- O hero **já muda** quando a loja está fechada: `HomeHeroThing.vue:130,167` trocam o CTA
  por `closedCtaLabel` (`index.vue:196` → "Montar pedido") quando `statusOpen` é falso.
- O checkout **nunca oferece dia fechado**: `closed_dates_json`, `closed_weekdays`,
  `datepickerDisabledDates` e `preorder_hint` (`app/pages/finalizar.vue:377-397,976`;
  `shopman/storefront/presentation/checkout.py:135-241`). Loja fechada é fluxo de
  **encomenda**, não beco sem saída.

O defeito real — o notice global montado pelo servidor e nunca renderizado — permanece, e
é P1.

### S3 — Barra do checkout sob a bottom-nav
O CSS confirma a colisão abaixo de 768px. A **consequência** está errada nos dois pontos:

- *"o cliente não vê o total correndo"* — o total aparece no fluxo, em corpo grande, no
  rodapé do passo de confirmação: `finalizar.vue:1610-1611` ("Total do pedido" +
  `grand_total_display`), e de novo no rodapé do sheet de revisão (`:1732`).
- *"não alcança o botão que abre o recibo"* — o botão "Resumo" (`:1859`) abre o sheet
  `receiptOpen` (`:1748-1765`), que é um **visualizador**. O caminho de envio é outro:
  "Revisar pedido" no fluxo (`:1637`, `continueFromPayment`) → sheet `confirmOpen`
  (`:1648`) → `submitCheckout` (`:1740`). Nada do caminho de pagamento passa pela barra
  coberta.

Ou seja: uma barra de conveniência redundante fica invisível no telefone. É P2, e a
geometria exata (altura vs. `pb-24`) só se confirma renderizando.

### S4 — OTP de debug
Refutado por leitura do backend. `_debug_otp_allowed` (`shopman/storefront/api/auth.py:431-446`)
exige, fora de `DEBUG`: a flag **e** um segredo configurado **e** o header
`X-Shopman-Debug-Otp` batendo por `secrets.compare_digest`. `SHOPMAN_DEBUG_OTP_TOKEN` não
aparece em nenhum `.do/*.yaml` — só em `config/settings.py:101` e nos testes. Portanto o
`SHOPMAN_EXPOSE_DEBUG_OTP='true'` de `.do/app.alpha-subdomains.yaml:281-283` não emite
código nenhum, e `.do/app.subdomains.yaml:330-333` já nasce `"false"`. O agente de
segurança chegou à mesma conclusão (`01-security.md:811-815`). O que sobra é o render em
`entrar.vue:576-613`, que só pinta o que o servidor mandar — defesa em profundidade, P2.
**A entrada da memória do projeto que marca isto como bloqueador está desatualizada.**

### O1 — Assinatura cega da sangria
O fato é real e a correção proposta (prop `detail` com o valor) é boa. Mas dois pontos
foram omitidos: o diálogo é explicitamente desenhado como **modal com a operação visível
atrás** (`PosManagerAuthDialog.vue:93-97` — "camada 2"), então o valor digitado não some da
tela; e a brevidade da copy é **decisão registrada do dono** (`managerAuth.ts:33-38`: a
versão anterior explicava a política e foi encurtada a pedido dele). O controle está
enfraquecido, não ausente — P1. Notável: o auditor de dinheiro, que passou por
`Entry.approved_by` e pelo teto de desconto do gerente (`07-money-lifecycle.md:255,315,412`),
não classificou isto como P0.

### O2 — Escassez ao iniciar
Erro de **alcançabilidade**. O auditor inferiu o 409 a partir da existência do
`ShortageDialog` e não conferiu quem levanta a exceção. `apply_start` não checa insumo — a
checagem vive em `check_finish_materials`, chamada só por `apply_finish`
(`shopman/backstage/services/production.py:430-433`). Bate com a memória do projeto
("guardrail ativo em `adjust`/`finish`"). E como `parseShortage` só reconhece
`material_shortage`/`order_shortage`, todo erro real de `start` **já** produz toast
(`useProductionBoard.ts:55`). O ramo `else if (res.shortage)` que falta em `confirmStart`
é defensivo, não corretivo: P2.

### O3 — Virada do dia
Constante confirmada, cenário exagerado. `defaultPlanningDate` já leva o padrão para
**amanhã** depois do meio-dia, que é exatamente o dia certo às 4h da manhã seguinte; e a
data por extenso está na barra (`:466-468`) e é ecoada no diálogo de planejar (`:692`).
O chip "Hoje" fica mentindo — defeito real, P1 — mas "o padeiro planeja o dia errado"
exige ignorar a data escrita duas vezes.

### O4 / O5 — Menuboard
As duas metades se contradizem: sem refetch (O4), o `error` do O5 não pode aparecer depois
que o cardápio pintou. São **um** defeito — "esta tela carrega uma vez e nunca mais" — e a
página se declara demo no cabeçalho (`menuboard.vue:1-8`). O que fica caro é o `ESGOTADO`
congelado numa parede pública: P1, não P0. A frase "reconectando…" mentindo é P2 e some
junto quando o poll entrar.

### O6 — Chime do forno
Defeito real e a correção apontada (`operator-kit/app/composables/useAlertSound.ts:74-92`,
que arma listeners de gesto) é exatamente a certa. Rebaixado porque o próprio módulo
declara ser **auxiliar** e nomeia o guardrail primário — o alerta de fornada esquecida no
sino, por `started_at` vs. `max_started_minutes` (`useOvenTimers.ts:1-4`) — e porque o card
segue pulsando (`.qc-ringing`, `expedite.vue:612-614`). "Pão queimado" pressupõe que os
dois backstops também falhem.

### O7 / O12 — Foreground e wakeLock
São o mesmo achado por dois ângulos, e nenhum dos dois se prova lendo fonte. Quiosque de TV
e tablet de balcão se mantêm acordados por configuração de SO; `navigator.wakeLock` não
controla um televisor. Adotar `useScreenWake()` no kit continua sendo boa ideia — como
melhoria, P2, e a confirmação do problema exige aparelho.

### O8 — Tom de `accepted`
Resíduo de rename genuíno e barato de corrigir (viola a regra "zero residuals" do
CLAUDE.md). Mas o badge carrega o **rótulo textual** correto (`OrderCard.vue:175-176`,
`status_label` vindo de `order_queue.py:439`): perde-se o realce cromático, não a
informação. P2.

### O9 — Confirmação do disparo
"Um clique manda WhatsApp de verdade" descreve mal o fluxo. Chegar ao botão exige abrir um
sheet dedicado, escrever (ou deixar em branco) o texto e escolher o público, com a
contagem de pessoas atualizando ao vivo em `aria-live` — tudo isso o próprio achado
reconhece como "muito bem feito". Um eco final ("mandar para 143 pessoas?") continua sendo
melhoria correta: P2.

### O10 — Duplicação do disparo
Duplicata de `03-backstage-contract.md` P1-19. O risco (timeout → mensagem afirmando
fracasso → segundo disparo) é real e o gêmeo já traz a correção com o formato de resposta
a copiar (`_receipt_already_received_message`). Fica em P1, como lá.

### O11 — Idempotência da entrada de compras
Refutado inteiro. O auditor parou na view e concluiu ausência a partir de um `grep` que não
alcançou o service. A trava existe, é **de banco**, e o comentário em
`shopman/backstage/services/purchase.py:185-194` descreve palavra por palavra o cenário que
o achado apresenta como aberto — inclusive o caso do reescaneamento três horas depois. É a
refutação mais forte do lote: um "P0 de dinheiro" contra código escrito justamente para
impedir aquele dano.

---

## Calibration

**A assimetria 17×0 foi drift, não fato do sistema.**

Dos 17, **1 sobrevive como P0** na régua do dinheiro: **S5** (Privacidade/Termos sem aval
do dono) — e mesmo esse não é defeito de engenharia. É uma assinatura pendente que o
próprio código pede em comentário, com zero linhas a escrever. Nenhum dos 17 perde
dinheiro, corrompe dado, fura segurança ou torna uma tarefa diária impossível por defeito
de código.

Distribuição final: **1 P0 · 7 P1 · 9 P2**.

Três padrões produziram a inflação:

1. **Severidade puxada pela consequência narrada, não pela demonstrada.** "Pão queimado",
   "25 kg de farinha duas vezes", "sequestro de conta silencioso" — quatro das cinco
   consequências mais graves não sobreviveram à leitura da camada seguinte (`apply_start`,
   `confirm_receipt`, `_debug_otp_allowed`, o rodapé do passo de confirmação do checkout).
   O padrão é sempre o mesmo: o achado para na primeira camada onde a guarda não está e
   conclui que ela não existe em lugar nenhum.

2. **Alcançabilidade não checada.** O2 e O11 assumem que o servidor produz um erro ou
   aceita uma escrita que ele de fato não produz/não aceita. O5 assume um refetch que a
   própria linha anterior do relatório diz não existir. O12 assume uma política de
   aparelho que ninguém verificou.

3. **Duplicatas contadas como achados próprios.** Três dos 17 já estavam nos relatórios de
   contrato (02 P1-12, 03 P1-19) — e lá, feitos pelos auditores que leram o backend, foram
   classificados **P1**. Isso é o controle experimental: quando os mesmos dois defeitos
   foram vistos por auditores diferentes, os de contrato deram P1 e os de UX deram P0.

O contraponto honesto: os dois relatórios de UX são **bons**. Quase todos os 17 apontam
defeitos que existem e valem correção — o `accepted` órfão, o `todayISO` congelado, o
`unlockAudio` que o `load()` não chama, o notice global sem consumidor, a barra do checkout
sob a nav, o valor ausente na assinatura do gerente. O erro não foi inventar problema; foi
**calibrar severidade por gravidade narrativa** em vez de pelo teste de go-live. E o
auditor de dinheiro com zero P0 provavelmente estava certo: o código de dinheiro desta
casa é o mais defendido do repositório, e a auditoria de compras acabou de prová-lo
involuntariamente.

**Recomendação:** rebaixar os 16, promover S5 para a lista de gates de go-live não-técnicos
(assinatura do dono), fundir O4+O5 e O7+O12, e marcar S3, O7 e O12 como pendentes de
confirmação em tela/aparelho antes de virarem tarefa.
