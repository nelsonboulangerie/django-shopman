# ADR-035 — Entrega sem CPF é aceita em todo canal, e a NFC-e sai presencial

**Status:** Aceito
**Data:** 2026-10-13
**Decisão:** dono; substitui a decisão de 24/09/2026
**Pendência:** confirmação do contador (`docs/plans/LEVA-CONTADOR-ADVOGADO.md`, itens 2.1 e 2.2).

## Contexto

A NFC-e de entrega a domicílio (`indPres=4`) exige destinatário identificado (E01-20, rejeição
787) e endereço (E05-20, rejeição 788). Em 24/09/2026 a casa decidiu dois caminhos:

- **canal próprio** (loja, PDV, WhatsApp): CPF/CNPJ exigido na ENTRADA do pedido de entrega; quem
  não quisesse informar ficava só com a retirada;
- **iFood sem CPF**: a nota sai presencial, consumidor não identificado (praxe do mercado).

Na prática, exigir CPF para entregar é atrito que nenhum concorrente impõe, e o iFood já provava
o caminho presencial.

## Decisão

A **praxe do delivery vale para todos os canais**:

1. **Entrega sem CPF/CNPJ é aceita.** A NFC-e sai como venda presencial (`indPres=1`), consumidor
   não identificado, sem grupo de entrega, sem destinatário, `modalidade_frete=9`. A taxa de
   entrega que é da casa vira **outras despesas** (`vOutro`), para o total bater com o que o
   cliente pagou. Código: `services.fiscal.delivery_issues_as_presential`, chamado em
   `build_emission_payload` (o mesmo caminho do iFood sem CPF).
2. **Com CPF/CNPJ**, a nota de entrega a domicílio (`indPres=4`) de sempre, com destinatário,
   endereço e frete.
3. **CPF informado e inválido continua recusado** na porta: já é pedido de nota com dado errado.
4. **Endereço completo continua exigido** para a entrega com nota prevista (é logística).

A porta do pedido (`DeliveryFiscalIdentityRule`, PDV, checkout da loja, concierge, edição da
encomenda) lê `delivery_fiscal_gaps`, que deixa passar a falta do documento. A régua da emissão
(`recipient_gaps`, usada pelo adapter Focus na nota de entrega) continua exigindo o documento,
porque só chega lá quem tem documento.

Nas telas o CPF passa a ser convite: "CPF ou CNPJ na nota (opcional)" na loja; no PDV o Validar
não trava mais pela falta do documento.
