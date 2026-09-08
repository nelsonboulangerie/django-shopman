# Inventário do silêncio — a dívida da meia-correção

> Medido em **05/09/2026**, no `main` (`089d164a8`), por
> `make test-silent-swallow all=1` (`scripts/check_silent_swallow.py`).
> Regenerar com o mesmo comando; a coluna **Estado** é a única escrita à mão.

## O que esta lista é

**50 arquivos de produção** que contêm, ao mesmo tempo, duas coisas que não
deveriam conviver:

- **um relato de falha alto e correto** — `create_operator_alert`,
  `record_*_failure`, `logger.error/warning/exception`, `raise` de erro de
  domínio. O arquivo prova que alguém, algum dia, soube gritar ali; e
- **um engolimento mudo** — `except: pass`, `except → logger.debug`,
  `.catch(() => {})`, `catch {}`. São **94 sites**.

Não é uma lista de "arquivos sem tratamento de erro". É uma lista de
**contradições internas**: o mesmo autor, no mesmo arquivo, tratou um caso e
deixou o irmão calado. Essa é a assinatura da meia-correção.

## Por que ela existe

A hipótese fácil — "feature entra sem teste" — **não se sustenta**. A suíte
inteira roda em cada PR (7.780 testes coletados), são 21 checks obrigatórios
com `enforce_admins: true`, vitest nos 10 apps Nuxt, Playwright de verdade.

A causa é a **distribuição do remédio**. Dezenas de sessões trabalham em
worktrees paralelas; cada uma conserta o site exato que foi reportado e o irmão
idêntico, no mesmo arquivo, sobrevive calado. Três provas medidas:

1. `record_payment_reconciliation_failure` é chamado em 3 lugares (estorno
   Stripe, disputa, comando noturno). Os `except PaymentError: pass` de
   **authorize e capture** não têm nada. **Dinheiro saindo alerta; dinheiro
   entrando é silêncio.** A mesma assimetria no Efí: alerta no refund, engole o
   authorize — e ainda devolve `success=True`.
2. `shopman/shop/services/notification.py:522` carrega o comentário *"Isto era
   logger.debug e engoliu em silêncio o defeito que chegou ao cliente"*. Nas
   linhas **710 e 721 do mesmo arquivo** os irmãos continuam em `logger.debug`.
3. Par commit→regressão: `c5d7fa951` (25/08, "o CPF é o pedido da nota")
   resolveu metade; `ac1ff3c1e` (05/09, **11 dias depois**) resolveu a outra —
   e o canal `email` do mesmo `receipt.channels` segue inerte.

Churn compatível: `PosPaymentWorkspace.vue` levou 25 commits `fix(` em 6
semanas ("troco" reescrito 4 vezes, três delas no mesmo dia). No repositório
inteiro, **404 `fix(` contra 352 `feat(`** em 1.527 commits.

## ⚠️ O amplificador: `logger.debug` não chega a lugar nenhum

Isto muda a leitura da tabela inteira e precisa ser dito em separado.

`DJANGO_LOG_LEVEL` tem default **`INFO`**. Um `except → logger.debug` **não
emite uma linha sequer**, em lugar nenhum — nem no log do DO, nem em arquivo,
nem em serviço externo. Ele é um `except: pass` disfarçado, e o disfarce é o
problema: passa despercebido na revisão de código justamente por *parecer*
tratado.

Os números, medidos com o mesmo AST do gate (1.035 arquivos de produção
Python), porque a ordem de grandeza importa e cada corte responde outra
pergunta:

| Medida | Quantidade |
|---|---|
| Chamadas `logger.debug` em produção | **375** |
| …dentro de algum `except` | **340** |
| `except` cujo corpo é **só** `logger.debug` (mudez estrita) | **65** |
| `except` cujo corpo é **só** `pass` / `...` | **68** |
| **Sites mudos no total** | **133** |
| …destes, nos 50 arquivos com contradição interna | **94** |

As duas primeiras linhas são a superfície de risco: 340 lugares onde uma
exceção é registrada num nível que não sai. As três últimas são a dívida
acionável — handler que não faz absolutamente mais nada. A auditoria original
citou "333", que é a segunda linha desta tabela; a diferença é escopo de
varredura, não discordância.

E o segundo andar do amplificador: `SENTRY_DSN` **não estava setado em nenhum
dos dois specs** do App Platform, apesar de o `sentry-sdk` estar instalado,
pinado (2.68.1) e com o `init` pronto e caprichado em `config/settings.py`.
Código correto, inerte. Este PR acrescenta a env aos dois specs; **o DSN em si
precisa da mão do dono** — ver [`docs/runbooks/ativar-sentry.md`](../runbooks/ativar-sentry.md).

Enquanto o Sentry não estiver ligado, cada linha desta tabela é um defeito que
não tem como ser descoberto senão por um cliente reclamando.

## Como usar

Ao consertar uma linha, **uma das duas — nunca nenhuma**:

1. Faça o irmão gritar como o vizinho já grita naquele arquivo
   (`create_operator_alert` / `record_*_failure` / `logger.error` / `raise`); ou
2. Declare que o silêncio é de propósito, **com a razão**:

```python
except StaleDataError:  # silêncio-deliberado: corrida benigna, o worker relê
    pass
```
```ts
void refreshCart().catch(() => null)  // silêncio-deliberado: refresh oportunista
```

Degradação deliberada é legítima. O que não pode é ser **acidental**. O
marcador é lido por `scripts/check_silent_swallow.py` e vale na linha do
`except`, no corpo do handler, ou na linha imediatamente acima.

## Placar — o gate vira bloqueante quando `dinheiro` e `fiscal` zerarem

O gate está no CI **não-bloqueante** (`continue-on-error: true` em
`.github/workflows/runtime-gate.yml`). Nascer reprovando 50 arquivos garantiria
ser desligado no primeiro dia.

| Faixa | Arquivos | Sites | Situação |
|---|---|---|---|
| 💸 Dinheiro | 5 | 15 | ⬜ aberto |
| 🧾 Nota fiscal | 1 | 1 | ⬜ aberto |
| 🙋 Promessa ao cliente | 17 | 37 | ⬜ aberto |
| 🔧 Interno | 15 | 19 | ⬜ aberto |
| ✅ Provavelmente inofensivo | 12 | 22 | ⬜ falta só o marcador |
| **Total** | **50** | **94** | |

**Portão para tornar o check obrigatório: as faixas 💸 e 🧾 zeradas — 6
arquivos, 16 sites.** Não são 50. Quem fechar a última linha dessas duas:
apague o `continue-on-error` do job `silent-swallow-gate` e peça ao dono para
marcar `Gate da meia-correção` como required na branch protection (é a mão dele
no GitHub, não a nossa). ⚠️ **Os dois passos são um só movimento.** Tirar o
`continue-on-error` antes do required deixa o gate reprovando sem bloquear —
ruído vermelho que ninguém precisa olhar. Marcar required antes de tirá-lo dá
um check obrigatório que sempre passa. Qualquer uma das metades sozinha ensina
o time a ignorar o vermelho.

### ✅ A base do diff não mente mais (pré-condição, resolvida)

O `Gate da meia-correção` chegou a reprovar o **PR #554** por um arquivo que
aquele PR nunca abriu. `resolve_diff_base` (em `scripts/check_adr015.py`,
compartilhada com o gate do ADR-015) usava a **ponta** da base como referência.
O merge ref `refs/pull/N/merge` é gerado no push e **não é refeito quando a base
anda**: o #549 entrou no meio, a ponta avançou, o `HEAD` não, e o diff passou a
mostrar as mudanças do PR alheio **ao contrário**.

A base agora sai do **pai 1 do merge ref** — o commit exato sobre o qual o merge
foi montado, imune à base andar depois. Ele é lido do objeto do commit
(`git cat-file commit HEAD`), e não de `rev-parse HEAD^1`, porque o enxerto do
`fetch-depth: 1` esconde os pais da revision walk mas não do objeto: por isso o
conserto **não custou nada de CI** e o job `quality`, que faz checkout raso,
continua como está. Sem base resolvível os dois gates **reprovam** com a razão
escrita — nunca verde por ter olhado zero arquivo.

Os 12 "provavelmente inofensivos" **não pedem conserto, pedem marcador**: são a
forma mais barata de encolher a lista sem mexer em comportamento, e o marcador
é o que impede que alguém, daqui a três meses, "conserte" um silêncio que era
de propósito.

## A tabela

Ordenada por dano: dinheiro > nota fiscal > promessa ao cliente > resto. A
coluna "já grita na linha" é a prova da contradição — é onde o próprio arquivo
demonstra que sabia relatar.


### 💸 Dinheiro — 5 arquivos, 16 sites

| Arquivo | Linhas mudas | O que se perde | Estado |
|---|---|---|---|
| `shopman/shop/adapters/payment_stripe.py`<br><sub>já grita na linha 582 · except_debug/except_pass</sub> | `291`, `457`, `973`, `979`, `992`, `996`, `1014` | webhook confirma no Stripe e o pedido nunca sai de pendente; ninguém soube | ⬜ aberto |
| `shopman/shop/adapters/payment_efi.py`<br><sub>já grita na linha 132 · except_pass</sub> | `296`, `438` | PIX pago ou cancelado na Efí sem refletir no intent; caixa diverge | ⬜ aberto |
| `shopman/shop/services/payment.py`<br><sub>já grita na linha 447 · except_debug/except_pass</sub> | `1242`, `1405`, `1518`, `1606` | intent reaproveitável some e o cliente recebe segunda cobrança pelo mesmo pedido | ⬜ aberto |
| `shopman/shop/services/pix_confirmation.py`<br><sub>já grita na linha 432 · except_debug</sub> | `596`, `729` | PIX entra mas o alerta de falha segue aceso; operador persegue dinheiro já recebido | ⬜ aberto |
| `shopman/shop/services/pos.py`<br><sub>já grita na linha 918 · except_debug</sub> | `2489` | teto de desconto da loja é ignorado; balcão libera desconto sem gerente | ⬜ aberto |

### 🧾 Nota fiscal — 1 arquivos, 1 sites

| Arquivo | Linhas mudas | O que se perde | Estado |
|---|---|---|---|
| `shopman/shop/adapters/purchase_invoice_nfe.py`<br><sub>já grita na linha 236 · except_pass</sub> | `984` | XML da nota do fornecedor volta ilegível e a entrada fiscal não fecha | ⬜ aberto |

### 🙋 Promessa ao cliente — 17 arquivos, 42 sites

| Arquivo | Linhas mudas | O que se perde | Estado |
|---|---|---|---|
| `packages/guestman/shopman/guestman/contrib/manychat/resolver.py`<br><sub>já grita na linha 119 · except_debug</sub> | `83`, `124`, `231`, `377`, `440`, `503`, `571` | contato não é resolvido no ManyChat e a mensagem nunca chega ao cliente | ⬜ aberto |
| `packages/guestman/shopman/guestman/contrib/merge/service.py`<br><sub>já grita na linha 81 · except_pass</sub> | `213`, `232`, `244`, `256`, `271`, `826`, `865`, `891` | desfazer fusão fica pela metade: pedidos e consentimentos presos no cliente errado | ⬜ aberto |
| `packages/guestman/shopman/guestman/services/customer.py`<br><sub>já grita na linha 283 · except_pass</sub> | `210` | cliente nasce sem a tabela de preço combinada e paga o cheio | ⬜ aberto |
| `packages/orderman/shopman/orderman/services/commit.py`<br><sub>já grita na linha 222 · except_pass</sub> | `329`, `419`, `459` | encomenda perde a marcação e o lembrete véspera; cliente esquece de retirar | ⬜ aberto |
| `packages/stockman/shopman/stockman/contrib/alerts/handlers.py`<br><sub>já grita na linha 130 · except_debug</sub> | `127` | alerta de estoque baixo não vira tarefa; produto acaba sem ninguém repor | ⬜ aberto |
| `shopman/shop/adapters/notification_manychat.py`<br><sub>já grita na linha 238 · except_debug</sub> | `219` | template configurado no Admin é ignorado e o cliente recebe a mensagem errada | ⬜ aberto |
| `shopman/shop/adapters/stock.py`<br><sub>já grita na linha 204 · except_debug/except_pass</sub> | `299`, `315` | reserva fica presa e o produto some da vitrine mesmo tendo estoque | ⬜ aberto |
| `shopman/shop/handlers/_stock_receivers.py`<br><sub>já grita na linha 77 · except_debug/except_pass</sub> | `44`, `117`, `231`, `299`, `305` | fornada chega e quem estava esperando não é avisado; reserva morre pendurada | ⬜ aberto |
| `shopman/shop/handlers/campaign.py`<br><sub>já grita na linha 370 · except_pass</sub> | `48` | novidade e volta de produto nunca viram campanha; cliente não fica sabendo | ⬜ aberto |
| `shopman/shop/modifiers.py`<br><sub>já grita na linha 598 · except_debug</sub> | `824` | desconto por segmento não aplica e o cliente paga sem a promoção prometida | ⬜ aberto |
| `shopman/shop/projections/order_tracking.py`<br><sub>já grita na linha 1401 · except_debug</sub> | `1299` | acompanhamento não mostra a hora do pagamento; cliente duvida se pagou | ⬜ aberto |
| `shopman/shop/rules/engine.py`<br><sub>já grita na linha 153 · except_debug</sub> | `84`, `114`, `228`, `230` | regras da casa deixam de valer sem aviso: pedido passa por gate inexistente | ⬜ aberto |
| `shopman/shop/rules/validation.py`<br><sub>já grita na linha 269 · except_debug</sub> | `100`, `124` | loja fechada ou feriado aceita pedido que ninguém vai produzir nem entregar | ⬜ aberto |
| `shopman/shop/services/fulfillment_window.py`<br><sub>já grita na linha 293 · except_debug</sub> | `111` | cliente escolhe horário genérico que a casa não combinou cumprir | ⬜ aberto |
| `shopman/shop/services/notification.py`<br><sub>já grita na linha 365 · except_debug</sub> | `710`, `721` | pedido fica sem dono identificado e a notificação some sem destinatário | ⬜ aberto |
| `shopman/storefront/concierge/service.py`<br><sub>já grita na linha 164 · except_debug</sub> | `114` | cliente autorizado é barrado no concierge do WhatsApp e fica sem atendimento | ⬜ aberto |
| `shopman/storefront/services/stock_alerts.py`<br><sub>já grita na linha 360 · except_debug</sub> | `53` | quem pediu aviso de fornada é inscrito no eixo errado e nunca avisado | ⬜ aberto |

### 🔧 Interno — 15 arquivos, 17 sites

| Arquivo | Linhas mudas | O que se perde | Estado |
|---|---|---|---|
| `shopman/shop/lifecycle.py`<br><sub>já grita na linha 379 · except_pass</sub> | `544` | ticket de cozinha do pedido cancelado continua na fila; produção vira desperdício | ⬜ aberto |
| `shopman/backstage/projections/pos.py`<br><sub>já grita na linha 939 · except_debug</sub> | `785` | balcão não vê a promoção de aniversariante e deixa de oferecê-la | ⬜ aberto |
| `shopman/backstage/projections/recipe_book.py`<br><sub>já grita na linha 757 · except_debug</sub> | `530`, `538` | receita mostra código de SKU no lugar do nome; padeiro lê cru | ⬜ aberto |
| `shopman/shop/services/checkout.py`<br><sub>já grita na linha 133 · except_pass</sub> | `202` | cadastro do cliente web não nasce numa corrida; histórico dele fica partido | ⬜ aberto |
| `shopman/shop/services/customer.py`<br><sub>já grita na linha 75 · except_debug</sub> | `310` | nome informado no pedido não gruda no cadastro; cliente segue anônimo | ⬜ aberto |
| `shopman/storefront/api/auth.py`<br><sub>já grita na linha 195 · except_debug</sub> | `147`, `284` | identidade cai para o nível fraco por segurança e a sessão volta incompleta | ⬜ aberto |
| `packages/craftsman/shopman/craftsman/contrib/demand/backend.py`<br><sub>já grita na linha 153 · except_debug</sub> | `108` | demanda calculada sem perdas; padeiro planeja fornada com número otimista demais | ⬜ aberto |
| `shopman/shop/services/production.py`<br><sub>já grita na linha 430 · except_pass</sub> | `540` | produção entra na posição padrão e o estoque aparece no lugar errado | ⬜ aberto |
| `shopman/shop/services/product_readiness.py`<br><sub>já grita na linha 114 · except_debug</sub> | `176` | hora prevista de fornada sai em fuso errado na previsão de prontidão | ⬜ aberto |
| `shopman/shop/handlers/_sse_emitters.py`<br><sub>já grita na linha 97 · except_debug</sub> | `493` | evento vai para o painel geral e a loja certa pode não ver | ⬜ aberto |
| `shopman/shop/services/courier.py`<br><sub>já grita na linha 304 · except_debug</sub> | `68` | painel não atualiza o status do entregador; operador recarrega para saber | ⬜ aberto |
| `shopman/shop/models/rules.py`<br><sub>já grita na linha 67 · except_pass</sub> | `111` | auditoria da mudança de regra sai sem o caminho antigo para comparar | ⬜ aberto |
| `shopman/shop/views/product_feed.py`<br><sub>já grita na linha 53 · except_debug</sub> | `131` | feed de produtos sai sem o nome da marca para Google e Meta | ⬜ aberto |
| `shopman/storefront/presentation/product_detail.py`<br><sub>já grita na linha 427 · except_debug</sub> | `522` | página do produto fica sem a dica de conservação padrão da casa | ⬜ aberto |
| `shopman/shop/services/whatsapp_verify.py`<br><sub>já grita na linha 53 · except_debug</sub> | `51` | pouco perdido: o erro logo abaixo grita a ausência de número | ⬜ aberto |

### ✅ Provavelmente inofensivo — 12 arquivos, 18 sites

| Arquivo | Linhas mudas | O que se perde | Estado |
|---|---|---|---|
| `packages/doorman/shopman/doorman/services/_user_bridge.py`<br><sub>já grita na linha 104 · except_pass</sub> | `40` | ausência de vínculo é o caminho normal para criar o usuário | ⬜ aberto |
| `packages/guestman/shopman/guestman/contrib/admin_unfold/admin.py`<br><sub>já grita na linha 92 · except_pass</sub> | `40`, `429`, `720` | registro de admin e colunas opcionais de segmento somem da lista | ⬜ aberto |
| `packages/guestman/shopman/guestman/contrib/manychat/service.py`<br><sub>já grita na linha 134 · except_pass</sub> | `180`, `199`, `213` | identificador ausente apenas segue para a próxima tentativa de busca | ⬜ aberto |
| `packages/guestman/shopman/guestman/services/address.py`<br><sub>já grita na linha 100 · except_pass</sub> | `291` | sem contagem de uso, o endereço mais recente já serve de escolha | ⬜ aberto |
| `packages/offerman/shopman/offerman/contrib/admin_unfold/admin.py`<br><sub>já grita na linha 105 · except_pass</sub> | `49` | desregistro de admin que já não estava registrado | ⬜ aberto |
| `packages/stockman/shopman/stockman/services/holds.py`<br><sub>já grita na linha 34 · except_pass</sub> | `32` | id de reserva inválido cai no erro de domínio logo abaixo | ⬜ aberto |
| `shopman/shop/admin/shop.py`<br><sub>já grita na linha 900 · except_pass</sub> | `1252` | cor de tema inválida cai no cinza padrão da interface | ⬜ aberto |
| `shopman/shop/apps.py`<br><sub>já grita na linha 290 · except_pass</sub> | `98`, `100` | registro duplicado ou módulo ausente de tipos de ref no boot | ⬜ aberto |
| `shopman/storefront/concierge/tools.py`<br><sub>já grita na linha 373 · except_debug</sub> | `104` | cardápio do concierge cai no catálogo da loja online | ⬜ aberto |
| `surfaces/pos-nuxt/app/composables/usePosSale.ts`<br><sub>já grita na linha 1046 · catch_block</sub> | `185` | falha de rede transiente; polling segue e o desfecho aparece no chip | ⬜ aberto |
| `surfaces/storefront-nuxt/app/plugins/errorReporter.client.ts`<br><sub>já grita na linha 20 · catch_arrow</sub> | `30` | telemetria de erro best-effort que nunca pode quebrar a loja | ⬜ aberto |
| `tools/pos-counter-agent/counter_agent.py`<br><sub>já grita na linha 395 · except_pass</sub> | `1004`, `1901` | faxina de serviço legado e espera de health check no instalador | ⬜ aberto |

## Arquivos citados que este PR NÃO tocou

`shopman/shop/services/pos.py` e `shopman/shop/lifecycle.py` aparecem na tabela
como **dado medido**, não como trabalho pendente desta frente: estavam em uso
por outras sessões no momento da medição. Quem for consertá-los, confira antes
se a linha ainda é a mesma — referência arquivo:linha envelhece em horas neste
repositório.

## Como regenerar

```bash
make test-silent-swallow all=1          # relatório legível
make test-silent-swallow all=1 json=1   # JSON, para remontar a tabela
make test-silent-swallow                # só o que o SEU PR tocou (é o que a CI roda)
```

O gate não conta o próprio `scripts/`, nem testes, nem migrações, nem
`node_modules` — ver `EXCLUDED_SEGMENTS` no script. Os testes dele vivem em
`shopman/shop/tests/test_silent_swallow_gate.py`, e são simétricos de
propósito: metade prova o que deve reprovar, metade prova o que deve passar. A
segunda metade é a que mantém a ferramenta viva.
