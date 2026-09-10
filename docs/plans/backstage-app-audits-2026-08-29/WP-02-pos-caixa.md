# WP-02 - POS / Caixa

**Status:** pronto para implementacao  
**Superficie:** `surfaces/pos-nuxt` + endpoints POS/cash/closing/operator  
**Objetivo:** fechar os contratos que podem fazer dinheiro, terminal, pagamento, impressao ou comanda divergirem da realidade fisica do balcao.

## Fronteira Natural

O POS executa venda, recebimento, gaveta, impressao, comanda, cozinha e fechamento operacional do caixa. Ele nao faz conciliacao financeira historica, politica fiscal, cadastro profundo de cliente, configuracao de terminal, BI ou edicao de catalogo.

Contratos naturais:

- Terminal e caixa pertencem a estacao confiavel resolvida no servidor.
- Pagamento pertence ao payload de venda, com linhas explicitas quando houve digitacao.
- Comanda e cozinha usam actions projetadas pelo servidor.
- Admin audita e configura; POS executa.

## Evidencias Principais

- `build_pos` usa terminal default quando nenhum terminal e passado: `shopman/backstage/projections/pos.py:440`, `:454`.
- `POSView` chama `build_pos(operator=request.user)` sem terminal de estacao: `shopman/backstage/api/operations.py:297`.
- `_open_cash_shift_for_request()` usa `current_shift()` sem `terminal_ref`: `shopman/backstage/api/operations.py:226`.
- `open_cash_shift()` transforma negativo em zero: `shopman/backstage/services/pos.py:65`.
- `resolvePayment()` omite tender explicito para uma linha: `surfaces/pos-nuxt/app/utils/posIntent.ts:44`.
- `actionHref()` cai para fallback hardcoded: `surfaces/pos-nuxt/app/utils/posIntent.ts:65`.
- `request_change` projetado diverge do payload real: `shopman/backstage/projections/pos.py:1107`, `surfaces/pos-nuxt/app/composables/usePosCashSession.ts:242`.

## Achados Priorizados

### P1 - Terminal/caixa nao e contrato fim a fim

A maioria das acoes cash nao carrega terminal e o servidor resolve por default/turno corrente. Em loja com mais de uma gaveta, isso e risco de dinheiro no caixa errado.

Proposta:

- Resolver terminal exclusivamente pela estacao confiavel no servidor.
- Rejeitar requisicao ambigua quando nao houver estacao ou terminal vinculado.
- Se `terminal_ref` vier do cliente, comparar com o terminal da estacao e auditar mismatch.

Aceite:

- Dois terminais simultaneos nao cruzam turno, venda, estorno, movimento, relatorio ou fechamento.
- Sem estacao vinculada, POS nao abre estado operacional mutavel.

### P1 - Pagamento digitado pode desaparecer no contrato

Com um unico tender nao cash ou parcial, a UI envia apenas metodo; backend monta uma linha pelo total. Se a UI estiver stale ou bypassada, o valor digitado pelo operador pode sumir.

Proposta:

- Sempre enviar `payment_tenders` quando o operador digitou valor.
- Servidor bloqueia single tender parcial, acima/abaixo, ou inconsistente com `review_sale`.
- `review_sale` e `close_sale` devem compartilhar validacao.

Aceite:

- Fuzz de pagamentos cobre cash, pix, card, mixed, conta, parcial, excedente e troco.
- Valor digitado nunca e substituido silenciosamente pelo total.

### P2 - Actions/payloads de POS nao sao contrato gerado

`posContract.ts` cobre metodos/colecoes/canais, mas actions, hrefs, capabilities e payload schemas sao manuais.

Proposta:

- Gerar manifest de actions: `ref`, `href`, `method`, `payload_schema`, `idempotency`, `requires_manager_approval`.
- Fallback de URL para mutacao deve falhar fechado em teste/producao.

Aceite:

- Remover action obrigatoria da projection quebra teste antes de chegar no operador.
- Frontend nao possui fallback para mutacao critica.

### P2 - Idempotencia prometida mas nao aplicada

`fire_tab` promete `client_request_id`, mas o servico apenas registra no audit trail.

Proposta:

- Implementar dedupe por `client_request_id` e escopo de comanda/terminal.
- Ou remover promessa da projection e tratar duplo submit como risco explicito.

Aceite:

- Duplo `fire_tab` com mesmo request id nao duplica ticket/cozinha.

### P2 - Aprovacao gerencial inconsistente

Algumas acoes aceitam badge ou PIN; outras aceitam apenas username/PIN.

Proposta:

- Criar contrato unico `manager_approval` resolvido no servidor.
- Bloquear self-approval quando regra exigir segunda pessoa.
- Auditar approver, metodo, motivo e acao.

Aceite:

- Desconto, override, cancelamento, drawer unlock e refund usam mesmo parser.

## Melhorias UX

1. **Semaforo de balcao:** operador, terminal, caixa, gaveta, impressora, fiscal, rede e comanda salva sempre visiveis.
2. **Previa de efeitos:** antes de finalizar: pedido, pagamento, entrada cash, itens de cozinha, recibo/DANFE.
3. **Outbox operacional:** impressao, DANFE, fiscal, PIX e autosave ficam pendentes com retry, nunca somem.
4. **Conflito de comanda:** se outra estacao mexeu, mostrar diff antes de salvar/fire/fechar.
5. **Assistente de troco fisico:** sugerir cedulas/moedas e alertar necessidade de sangria/troco.
6. **Scanner visivel:** modo scanner com foco protegido para evitar leitura cair no campo errado.

## Testes

- Multi-terminal completo: abrir, vender, movimentar, estornar, fechar e relatar.
- Pagamento: fuzz de tender e paridade `review_sale` vs `close_sale`.
- Idempotencia: `client_request_id`, salvar/fire/mover, reimpressao.
- Seguranca: negativos, enum invalido, CSRF, sessao travada.
- Fechamento: quantidade invalida por SKU nao vira zero; corrida retorna 409.
- Frontend: offline/stale bloqueia acoes irreversiveis.

## Fora De Escopo

Conciliacao financeira detalhada, ajuste historico de diferenca, regra fiscal, configuracao de hardware, permissao, BI, margem, catalogo, correcao historica ampla.

## Prompt Para Agente Executor

```text
Execute WP-02 POS / Caixa.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/WP-02-pos-caixa.md
- surfaces/pos-nuxt/app/utils/posIntent.ts
- surfaces/pos-nuxt/app/composables/usePosSale.ts
- surfaces/pos-nuxt/app/composables/usePosCashSession.ts
- shopman/backstage/projections/pos.py
- shopman/backstage/api/operations.py
- shopman/backstage/services/pos.py
- shopman/shop/services/pos.py

Fases:
1. Terminal por estacao e matriz multi-terminal.
2. Tender explicito e paridade review/close.
3. Manifest de actions/payloads sem fallback para mutacao.
4. Idempotencia real de fire/save/mutacoes repetiveis.
5. UX de semaforo/outbox/conflito.

Nao transforme o POS em Admin ou BI. Corrija o runtime do balcao.
```

