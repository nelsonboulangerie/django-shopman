# Runbook: provar as formas de pagamento da NFC-e em homologação

> Achado F2 do laudo adversarial de 23/10/2026. O adapter
> (`shopman/shop/adapters/fiscal_focusnfe.py`, `_payment_group`) passou a mandar o grupo
> de cartão, a descrição do "outros" e o troco. Teste unitário prova o JSON; só a SEFAZ
> prova que a nota sai. Este runbook é essa prova: **uma nota autorizada por forma**.

⚠️ **Emitir no alpha pede a palavra do Pablo.** Homologação não tem valor fiscal, mas
consome numeração da série de homologação, usa o certificado e o token da casa e cria
pedidos no banco. Sem o "sim" dele, nada deste runbook roda.

## O que o adapter manda (nomes da Focus)

Fonte: referência canônica da Focus NFe,
[FormaPagamentoXML](https://campos.focusnfe.com.br/nfe/FormaPagamentoXML.html) e
[NotaFiscalXML](https://campos.focusnfe.com.br/nfe/NotaFiscalXML.html) (conferidas em 23/10/2026).

| Forma | `forma_pagamento` (tPag) | Campos a mais |
|---|---|---|
| Cartão de crédito (balcão `credit`, Stripe com `card_funding=credit`) | `03` | `tipo_integracao: "2"` (tpIntegra, maquininha não integrada) |
| Cartão de débito (balcão `debit`, Stripe com `card_funding=debit`) | `04` | `tipo_integracao: "2"` |
| Pix | `17` | nenhum |
| Outros (iFood `external`, Stripe `prepaid`/`unknown`) | `99` | `descricao_pagamento` (xPag, 2 a 60 caracteres) |
| Dinheiro com troco | `01` | `valor_pagamento` = o que veio na mão; `valor_troco` (vTroco) no nível da nota |

O troco só sai quando `payment.change_q` e `payment.tendered_q` fecham com o dinheiro
líquido da nota (líquido + troco = entregue). Sem essa prova, a nota declara o líquido
sem `valor_troco`, que também é válido.

## Pré-requisitos

- Ambiente com `SHOPMAN_FISCAL_ADAPTER=shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend`,
  `FOCUS_NFE_ENVIRONMENT=homologacao` e o token de **homologação**
  (ver [ativar-focus-nfe](ativar-focus-nfe.md)). Confira antes: `is_homologation` tem de
  ser verdadeiro; o comando abaixo não deve rodar com token de produção.
- Um pedido concluído, com itens de NCM resolvido, para cada forma. Venda de balcão pelo
  PDV gera o `order.data["payment"]` certo sem edição à mão: crédito, débito, Pix e
  dinheiro com valor entregue maior que o total (ex.: venda de 15,00 paga com 20,00).
  Para o `99`, um pedido de teste do iFood (`is_test`) ou um pagamento Stripe de teste
  com cartão pré-pago.

## Emitir (uma por forma)

```bash
.venv/bin/python manage.py fiscal_emit --order <ref do pedido>
```

O comando roda o handler de emissão contra a homologação e grava chave, protocolo e
DANFE no pedido. Repita para as cinco: `03`, `04`, `17`, `99` e `01` com troco.

## O que conferir em cada nota

No XML autorizado (link `caminho_xml_nota_fiscal` da resposta da Focus):

1. **Status autorizado**, com protocolo. Rejeição é o achado: anote código e motivo.
2. `03`/`04`: dentro de `<detPag>`, o grupo `<card>` com `<tpIntegra>2</tpIntegra>`.
   A rejeição que este grupo evita é a **391** (dados do cartão não informados).
3. `99`: `<xPag>` presente, com a frase do adapter.
4. `17`: só `<tPag>17</tPag>` e `<vPag>`.
5. Dinheiro com troco: `<vPag>` do dinheiro igual ao entregue, `<vTroco>` igual ao troco,
   e `Σ vPag − vTroco = vNF`.
6. DANFE: a forma de pagamento impressa bate com a do balcão.

Guarde o XML e a resposta de cada nota como evidência no PR que fechar o F2.

## Perguntas que não são deste runbook

- **Pix do balcão: 17 (dinâmico) ou 20 (estático)?** O QR impresso do balcão é estático;
  o código manda `17` para todo Pix. Pergunta ao contador; o código não muda sem ele.
- **Conta na casa: 05 ou 21?** A tabela da Focus diz `05` = "Cartão da Loja (Private
  Label)" e `21` = "Crédito em Loja". O código manda `05`, decisão pendente do contador
  desde 17/09/2026.
- **Cartão da loja online (Stripe) como tpIntegra 1?** Comércio eletrônico é "integrado",
  mas o `1` obriga CNPJ da credenciadora e número de autorização, que o pedido não guarda
  hoje. Até haver os dois, sai `2`.
