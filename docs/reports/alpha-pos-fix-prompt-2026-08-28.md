# Prompt — Analisar e corrigir achados da revisão alpha do PDV

> **Para:** agente de código (nova sessão, sem contexto desta conversa)
> **Origem:** revisão alpha tester do PDV (2026-08-28, ambiente alpha DigitalOcean — `pdv.boulangerie.com.br`)
> **Regra de ouro do repositório:** antes de escrever qualquer coisa, entre num worktree (ver `CLAUDE.md`). O checkout principal é compartilhado.

## Missão

Analisar e **corrigir** os 6 achados abaixo no código do Shopman. Cada correção deve vir acompanhada de teste que a prove (regressão), rodar a suíte afetada e seguir as convenções do projeto (prosa em português, `_q` para centavos, zero aliases, URL em inglês — ver `CLAUDE.md`).

## Contexto rápido do domínio

- `surfaces/pos-nuxt/` = UI do PDV (Nuxt 4). `shopman/backstage/` = API/backend da superfície operador. `shopman/shop/services/pos.py` + `shopman/shop/services/pos_intent.py` = contrato de intenção de venda do PDV. `shopman/shop/eventstream.py` = permissões de canais SSE.
- O PDV envia um "sale intent" versionado (`pos.sale-intent.v1`); `parse_pos_sale_intent` valida; `review_sale`/`close_sale` normalizam; a UI monta o payload em `surfaces/pos-nuxt/app/utils/posIntent.ts` (`buildPosSaleIntent` — manda `unit_price_q` por item).
- Testes de referência: `shopman/backstage/tests/test_pos_*.py`, `shopman/shop/tests/test_pos_*.py`, `shopman/backstage/tests/test_pos_tabs.py` (tem fixture com `meta._list_q`).

---

## Achados (ordem de prioridade)

### F1 — [P2] `review_sale` calcula total zerado quando o item não traz `unit_price_q` (e o troco sai errado)

**Sintoma (reproduzido no alpha):** `POST /api/v1/backstage/pos/sale/review/` com `items:[{sku, qty}]` (sem `unit_price_q`) retorna `subtotal_q:0, total_q:0` e `change_q = valor entregue` (ex.: tendered 2600 → `change_display "R$ 26,00"`) — mesmo com a comanda salva e precificada (a projeção do tab mostra R$ 26,00). O `close_sale` com o MESMO payload calcula certo (R$ 41,00 no caminho feliz). A UI não sofre porque sempre envia `unit_price_q`, mas qualquer consumidor do contrato sem preço (replay offline, clientes de API) vê revisão mentirosa e troco errado.

**Causa raiz provável:** `_payload_subtotal_q` (`shopman/shop/services/pos.py:1815`) soma `qty * unit_price_q` e, sem o preço, soma 0 silenciosamente. O carimbo `_stamp_list_prices_from_session` (`pos.py:1844`) só preenche `unit_price_q` quando a sessão tem `meta._list_q` — e no alpha as sessões POS **não** têm `meta._list_q` (ver F4). Resultado: o carimbo é inerte e a review fica às cegas.

**Correção esperada:**
1. `_payload_subtotal_q` deve cair para o preço de ETIQUETA da sessão quando `unit_price_q` ausente (mesma fonte do kernel), em vez de somar 0. Avaliar também se a review deveria exigir preço resolvido (falhar com `PosIntentError` claro) quando não há sessão para carimbar.
2. Garantir que `meta._list_q` seja escrito nas linhas das sessões do canal POS (ver F4), para o carimbo funcionar em produção — e adicionar teste que reproduza o cenário "review sem `unit_price_q` com sessão precificada".

**Reprodução (via API, sessão de operador `admin`/`admin` no alpha):**
```bash
curl -s -c /tmp/j -b /tmp/j -X POST https://pdv.boulangerie.com.br/api/v1/backstage/operator/login/ -H 'content-type: application/json' -d '{"username":"admin","password":"admin"}'
# abrir comanda, salvar itens, depois:
curl -s -b /tmp/j -X POST https://pdv.boulangerie.com.br/api/v1/backstage/pos/sale/review/ -H 'content-type: application/json' -d '{"intent_version":"pos.sale-intent.v1","items":[{"sku":"CT","qty":2}],"tab_ref":"9999","tab_session_key":"<key>","fulfillment_type":"pickup","payment_method":"cash","payment_tenders":[{"method":"cash","amount_q":2600,"collection":"terminal"}],"tendered_q":2600}'
# esperado: total 2600, change 0. Obtido hoje: total 0, change 2600.
```

### F2 — [P2] Cancelar venda de balcão gera alerta `notification_failed` (ruído falso)

**Sintoma (reproduzido no alpha):** ao cancelar venda POS (`POST /pos/sale/recent/cancel/`), o lifecycle dispara a notificação `order_cancelled`; sem cliente/destinatário no pedido de balcão, a entrega falha 5× e cria alerta: `Notificação 'order_cancelled' falhou após 5 tentativas para pedido PDV-260828-Y32. Último erro: no active notification recipient available`. O gestor vê erro onde não há problema.

**Correção esperada:** o handler/dispatcher de notificações deve **pular silenciosamente** (ou registrar em nível debug) notificações de origem `pos` sem destinatário ativo (sem `Customer`/canal), em vez de retry+alerta. Localizar o dispatcher (`shopman/shop/notifications.py`, handlers em `shopman/shop/handlers/`) e o gatilho do `order_cancelled`; cobrir com teste (cancelar venda POS sem cliente → nenhum alerta `notification_failed`).

### F3 — [P3] SSE: ciclo de reconexão 400 no EventSource em estados de gate (login/lock)

**Sintoma (medido no browser headless):** em estados não identificados (tela de login, lock), o EventSource de `/sse/cash` e `/sse/tabs` entra em ciclo `200 → 400 → 200` (console: "Failed to load resource: 400"). Com sessão autenticada e estação desbloqueada, os canais ficam estáveis em 200 (verificado). Não quebra a operação (fallback poll de 60s cobre — `surfaces/pos-nuxt/app/composables/usePosEvents.ts`), mas gera ruído e reconexões inúteis. O BFF repassa status do Django (`surfaces/operator-kit/server/utils/eventStream.ts`); o 400 transiente na reconexão ainda não foi atribuído (BFF/Cloudflare/origem).

**Correção esperada:**
1. Não conectar EventSource quando a estação não está identificada (login/lock) — ex.: só conectar SSE quando `canIdentify && !locked` (estado já disponível no `useOperatorLock`), e fechar os streams ao travar.
2. Investigar o 400 transiente na RECONEXÃO (sem `Last-Event-ID` enviado): reproduzir localmente contra o BFF e o `/events/<kind>/` do Django; se for o BFF/Cloudflare, documentar/tratar. Adicionar teste de contrato se couber (`shopman/backstage/tests/test_pos_sse_cash_channel.py` existe — estender se necessário).

### F4 — [P3] `meta._list_q` ausente nas sessões do canal POS (raiz da F1)

**Sintoma:** `_stamp_list_prices_from_session` não encontra `meta._list_q` nas linhas das sessões POS salvas (projeção mostra preço via outro campo, mas o carimbo fica vazio). O modifier de pricing (`shopman/shop/handlers/pricing.py:121`) escreve `_list_q` no pricing de ORDER; conferir se o mesmo caminho roda para SESSÃO do canal POS (config de pricing do canal, `RuleConfig`, modifiers em `shopman/shop/modifiers.py`) e, se for gap, fechá-lo — sem quebrar a regra "maior desconto ganha" (testes: `shopman/shop/tests/test_pos_line_discount_matches_kernel.py`).

### F5 — [P3] Aviso de hidratação Vue no console ("Hydration completed but contains mismatches")

**Sintoma:** console do browser no carregamento do PDV. Cosmético, mas indica estado SSR ≠ cliente (provável relógio/estado reativo). Localizar a fonte (componentes com `new Date()`/`Date.now()`/estado local na montagem em `surfaces/pos-nuxt/app/` e `surfaces/operator-kit/`) e corrigir ou documentar a supressão legítima.

### F6 — [P3] `ERR_CONNECTION_REFUSED` para `127.0.0.1:47811` (agente do balcão ausente)

**Sintoma:** console acusa conexão recusada no health-check do agente de impressora/gaveta (`PosTerminalHealth`). **Comportamento da UI confirmado como correto:** a tela de resultado de venda mostra "A gaveta não abriu: O agente da estação não está rodando." — mensagem calma e acionável. **Ação:** apenas confirmar que o health-check não dispara toast/erro bloqueante em produção sem agente e, se necessário, silenciar o log de console (nível info/debug) — sem mudar o comportamento.

---

## O que NÃO corrigir (comportamentos validados como corretos)

- Gate de login, provisionamento de estação, lock por PIN/crachá (RBAC: fran/caixa sem senha — só PIN; lista numerada 1-9; crachá hex 12 dígitos com cadência <120ms).
- Venda completa: comanda → itens → fire (cozinha) → review → close → recibo; idempotência por `client_request_id` (mesmo envio → mesmo `order_ref`).
- Pagamentos: dinheiro (troco, cédulas do contrato), PIX mock (QR + confirmação automática), split, excedente não-dinheiro vira warning; pagamento a menor → 422 `payment_tenders_total_mismatch`.
- Aprovação gerencial: desconto > teto, price override, cancelamento de venda, sangria, servir troco — sempre com PIN de gerente; `close` sem gerente → 422 `manager_approval_required`; fran tentando fechar caixa → 403 `cash_close_forbidden`.
- Entrega/COD, CPF na nota (NFC-e homologação, `fiscal_expected`), contas na casa, fechamento de turno cego (blind count), mover linhas, renomear comanda, abrir gaveta sem venda.
- Fronteiras: ticket KDS por comanda fireada (fechar a venda NÃO encerra o ticket — a cozinha marca `done`), pedidos PDV na zona prep do gestor, hub da central.
- Ticket KDS do tab: `order_ref` do ticket = ref da comanda (ex.: "1200") — é o desenho atual.

## Como verificar antes de concluir

1. Rodar a suíte afetada: `make test-framework` (orquestrador+backstage) e, se tocar em superfícies, `make lint`; rodar os testes específicos dos arquivos alterados.
2. Para F1/F4: o teste novo deve falhar no estado atual e passar após a correção (reprodução determinística sem depender do alpha).
3. Para F2: teste que cancela venda POS sem cliente e asserta ausência de `OperatorAlert` tipo `notification_failed`.
4. Não mexer em migrações do Core sem necessidade comprovada (dados contextuais vivem em JSONField — ver `docs/reference/data-schemas.md`).
5. Entregar um PR (ou branch + resumo) por achado ou agrupado por prioridade, com referência a este documento.

## Artefatos de apoio (opcional, na máquina do Pablo)

- Scripts e screenshots da revisão: `/tmp/dsh-pos-alpha/` (harness Playwright, logs, PNGs: login, lock, board, grid, pagamento, resultado, KDS, central, sessão).
- Alpha vivo: `https://pdv.boulangerie.com.br` (operadores dev: `admin`/`admin`, PIN `1234`; `joyce` (gerente), `fran` (caixa), `diofer` (cozinha)).
