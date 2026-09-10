# WP-02-agente-d — POS / Caixa

**Status:** pronto para implementação · **Autor:** Agente D (revisão do WP-02 do Agente G)
**Superfície:** 'surfaces/pos-nuxt' + endpoints POS/cash/closing/operator
**Objetivo:** fechar os contratos que podem fazer dinheiro, terminal, pagamento, impressão ou comanda divergirem da realidade física do balcão.

## Diferenças vs. WP original (Agente G)

**Mantidos (validados):** terminal/caixa não é contrato fim a fim ('build_pos' sem terminal em 'operations.py:304'); pagamento digitado pode sumir ('resolvePayment' omite valor para single non-cash e cash parcial — 'posIntent.ts:50'); 'request_change' projetado diverge do payload real (schema inventa 'kind' e omite 'denominations'); aprovador gerencial inconsistente; 'open_cash_shift' clampa negativo em zero ('services/pos.py:65').

**Recalibrados:**
- **P1 terminal default** — o WP via o default como o problema; o problema real é **dois resolvers divergentes**: a projection usa 'Terminal.default()' (= 'pdv-main', 'terminal.py:44-55') e as mutações usam '_terminal("")' (= primeiro terminal ativo por ref, 'services/pos.py:506-507'). Com um totem 'totem-01' ativo (< 'pdv-main'), a tela mostra o turno do pdv-main e as mutações operam no turno do totem — **dinheiro no caixa errado sem erro**, e a tela ainda mostra "abrir caixa" quando o turno já está aberto em outro terminal. 'Terminal.default()' é decisão de produto documentada (loja de um balcão não cadastra terminal) — a correção coexiste com ela (§P0).
- **P2 idempotência fire_tab** — o WP propôs implementar dedupe por 'client_request_id'; a verificação mostrou que **o fire já é idempotente por mecanismo mais forte** (ledger KDS por 'line_id' + 'select_for_update' na Session, 'kds.py:120-160') e que dedupe escopado à comanda inteira **quebraria o fire progressivo por curso**. A correção certa é a opção B do próprio WP: **remover a promessa** da projection.
- **P2 "Sem estação vinculada, POS não abre estado mutável"** — contradiz 'Terminal.default()' explícito; reformulado para: default só quando 0-1 terminal ativo; com 2+, falha fechado até estação/terminal explícito.
- **P2 manager_approval** — além da inconsistência de parser, achado novo: o desconto persiste 'approved_by' do **username cru do payload** (valida A, persiste B) — 'build_session_ops' em 'shop/services/pos.py:1377-1404,1549-1552'. Fronteira: o contrato unificado mora no orquestrador (shop), dono único declarado ('shop/services/pos.py:2193').

**Novos (achados da verificação):**
- **Dois resolvers de terminal default divergentes** (acima) — o achado mais grave do WP.
- **review_sale e close_sale NÃO compartilham validação de pagamento**: o que review trata como warning ('cash_tendered_amount_blank'/'too_low'/'payment_tenders_*'), close rejeita com 'PosIntentError' ('shop/services/pos.py:596-632'). Operador revisa "ok" com warning e a finalização falha.
- **'open_cash_shift' destrói o sinal antes do guard do cashman**: 'max(0, ...)' impede o pacote de rejeitar negativo ('cashman/services/shifts.py:57-58' nunca dispara) — "-10" abre caixa com R$ 0 em silêncio.
- Micro-drift: action 'cash_movement' declara 'reason' required mas o servidor só exige na sangria ('pos.py:1063' vs 'services/pos.py:122-124').

## Fronteira Natural

O POS executa venda, recebimento, gaveta, impressão, comanda, cozinha e fechamento operacional. Não faz conciliação histórica, política fiscal, cadastro profundo, config de terminal, BI ou edição de catálogo. **O contrato 'manager_approval' unificado é do orquestrador (shop)** — o POS (backstage) consome; a decisão de parser e o audit trail são do dono do orquestrador.

## Evidências (verificadas)

- 'build_pos(*, terminal=None, operator=None)' com 'Terminal.default()': 'shopman/backstage/projections/pos.py:440,454-457'.
- 'POSView.get' chama 'build_pos(operator=request.user)' sem terminal: 'shopman/backstage/api/operations.py:304'.
- '_terminal("")' = primeiro ativo por ref (resolver das mutações): 'shopman/backstage/services/pos.py:506-507'.
- 'current_shift()' sem terminal_ref nas mutações: 'operations.py:226-232'.
- 'resolvePayment' omite valor para single non-cash e cash parcial: 'surfaces/pos-nuxt/app/utils/posIntent.ts:44-63'.
- 'request_change' — schema diz 'required: [kind]', endpoint lê amount/denominations/note, service não tem 'kind': 'projections/pos.py:1107-1114', 'operations.py:2109-2111', 'services/pos.py:318', 'usePosCashSession.ts:242-249'.
- fire_tab promete 'idempotency=client_request_id' mas o service só loga: 'projections/pos.py:1221-1223', 'shopman/shop/services/pos.py:1154-1158'.
- 'open_cash_shift' com 'max(0, ...)': 'shopman/backstage/services/pos.py:65'.
- Validadores duplicados: 'validate_manager_approval' (só username+pin) vs 'validate_manager_override' (badge OU username+pin): 'shopman/shop/services/pos.py:1655-1689,1692-1748'.

## Achados Priorizados

### P0 — Resolver único de terminal (dois defaults divergem hoje)

Proposta:
- Um único resolver servidor-side: terminal da estação confiável → senão, 'Terminal.default()' **somente quando há 0-1 terminal ativo**; com 2+ terminais ativos e sem estação vinculada, falha fechado (409 com instrução).
- 'POSView' e todas as mutações cash (open, movement, settle, close, fire, report) resolvem terminal pelo mesmo caminho.
- Se 'terminal_ref' vier do cliente, comparar com o terminal resolvido e auditar mismatch (nunca confiar no payload).

Aceite:
- Dois terminais simultâneos não cruzam turno, venda, estorno, movimento, relatório ou fechamento.
- A projection e as mutações mostram o MESMO turno/terminal (teste de paridade projection↔mutation).
- Loja single-terminal continua abrindo caixa sem cadastrar terminal (decisão de produto preservada).

### P1 — Pagamento digitado pode desaparecer no contrato

Proposta:
- Sempre enviar 'payment_tenders' quando o operador digitou valor (cash parcial inclusive — hoje só o caso cash≥total é preservado).
- Servidor bloqueia single tender parcial/inconsistente com 'review_sale'.
- **'review_sale' e 'close_sale' compartilham a MESMA validação** (hoje divergem: warning vs erro).

Aceite:
- Fuzz de pagamentos cobre cash, pix, card, mixed, conta, parcial, excedente e troco.
- Valor digitado nunca é substituído silenciosamente pelo total.
- 'review_sale' e 'close_sale' aplicam a mesma matriz de validação (teste de paridade).

### P1 — "Abrir caixa" com valor negativo abre com R$ 0 em silêncio

Proposta:
- Rejeitar 'opening_amount_raw' negativo com 400 (em vez de 'max(0, ...)'); o guard do cashman volta a ser o decisor.

Aceite:
- '-10' retorna 400 de campo e não abre turno.
- Turno aberto com valor vazio continua valendo '0' (fluxo atual preservado).

### P2 — Actions/payloads de POS não são contrato gerado (infra compartilhada)

**Este bloco é pré-requisito dos WPs 03 e 05** — o formato do manifest deve ser definido uma vez aqui e consumido lá (ver README agente_d §6).

Proposta:
- Manifest de actions: 'ref', 'href', 'method', 'payload_schema', 'idempotency', 'requires_manager_approval' — gerado da projection (fonte da verdade).
- 'request_change': corrigir o schema para 'amount'/'denominations'/'note' (remover 'kind' fantasma).
- Fallback de URL para mutação crítica falha fechado em teste/produção ('actionHref' com fallback só para leitura; 'concreteActionHref' obrigatório para mutação).

Aceite:
- Remover action obrigatória da projection quebra teste antes de chegar no operador.
- Frontend não possui fallback para mutação crítica (remover '|| fallback' do path de mutação).

### P2 — Aprovação gerencial: parser único + assinatura verificada

Proposta (dono: orquestrador 'shop/services/pos.py'):
- Contrato único 'manager_approval' resolvido no servidor (badge OU username+pin, mesma validação para desconto/override/cancelamento/drawer unlock/refund).
- **Persistir o 'User' verificado como 'approved_by'** (hoje o desconto grava o username cru do payload — validar A, persistir B).
- Bloquear self-approval quando regra exigir segunda pessoa; auditar approver, método, motivo e ação.

Aceite:
- Desconto, override, cancelamento, drawer unlock e refund usam o mesmo parser e o mesmo audit trail.
- 'approved_by' do pedido é o 'User' autenticado na aprovação, não o username do payload.

### P2 — Fire_tab: remover a promessa de idempotência por request

Proposta:
- Projection de 'fire_tab' passa a declarar 'idempotency="ledger"' (ou remove o campo) com nota: idempotência real é por 'line_id' no ledger KDS.
- Manter o 'client_request_id' apenas como correlação de log.

Aceite:
- Duplo submit do mesmo curso não duplica ticket/cozinha (já é verdade — teste existente mantém).
- 'fire_tab' não promete dedupe por 'client_request_id' no contrato.

## Melhorias UX

1. **Semaforo de balcão:** operador, terminal, caixa, gaveta, impressora, fiscal, rede e comanda salva sempre visíveis (terminal = o resolvido pelo servidor).
2. **Previa de efeitos:** antes de finalizar: pedido, pagamento, entrada cash, itens de cozinha, recibo/DANFE.
3. **Outbox operacional:** impressão, DANFE, fiscal, PIX e autosave ficam pendentes com retry, nunca somem.
4. **Conflito de comanda:** se outra estação mexeu, mostrar diff antes de salvar/fire/fechar.
5. **Assistente de troco físico:** sugerir cédulas/moedas e alertar necessidade de sangria/troco.
6. **Scanner visível:** modo scanner com foco protegido.

## RBAC / setup_groups

Nenhuma permissão nova neste WP (gate do POS continua 'cashman.operate_pos'). O contrato unificado 'manager_approval' reutiliza 'cashman.adjust_shift' e perms existentes — sem mudança em 'setup_groups.py'. Coordenar com o dono do orquestrador (shop) para o parser único.

## Pré-requisitos

- Nenhum. O bloco "Contrato de actions" (§P2) deve ser implementado **antes** dos WPs 03 e 05 (dependência declarada).

## Testes

- Multi-terminal: abrir, vender, movimentar, estornar, fechar e relatar sem cruzar terminais; paridade projection↔mutation do turno.
- Pagamento: fuzz de tender e paridade 'review_sale' vs 'close_sale'.
- Negativo: '-10' na abertura retorna 400.
- Idempotência: duplo fire não duplica; contrato sem promessa de dedupe por request.
- Segurança: negativos, enum inválido, CSRF, sessão travada, 'terminal_ref' mismatch auditado.
- Frontend: offline/stale bloqueia ações irreversíveis.

## Fora De Escopo

Conciliação financeira detalhada, ajuste histórico de diferença, regra fiscal, configuração de hardware, permissão, BI, margem, catálogo, correção histórica ampla.

## Prompt Para Agente Executor

~~~text
Execute WP-02-agente-d (POS / Caixa).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-02-agente-d-pos.md
- surfaces/pos-nuxt/app/utils/posIntent.ts
- surfaces/pos-nuxt/app/composables/usePosSale.ts, usePosCashSession.ts
- shopman/backstage/projections/pos.py
- shopman/backstage/api/operations.py (POSView, mutacoes cash)
- shopman/backstage/services/pos.py (_terminal, open_cash_shift)
- packages/cashman/shopman/cashman/models/terminal.py, services/shifts.py
- shopman/shop/services/pos.py (review/close, validadores manager)

Fases:
1. Resolver unico de terminal (estacao → default so com 0-1 ativo; 409 ambiguo) e paridade projection↔mutation.
2. Tender explicito + paridade review/close; rejeitar negativo na abertura.
3. Manifest de actions/payloads (base compartilhada dos WPs 03/05); corrigir schema do request_change; fallback fechado para mutacao.
4. Parser unico de manager_approval + approved_by verificado (coordenar com o dono do shop).
5. Remover promessa de dedupe por client_request_id no fire_tab.
6. UX de semaforo/outbox/conflito.

Nao transforme o POS em Admin ou BI. Corrija o runtime do balcao.
~~~

