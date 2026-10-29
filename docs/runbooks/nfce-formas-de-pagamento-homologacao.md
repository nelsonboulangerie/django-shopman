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
| Pix da cobrança (QR com txid gerado pela Efí, no PDV ou na loja online) | `17` (PIX Dinâmico) | `tipo_integracao: "2"` |
| Pix atestado no balcão ("Recebi o Pix", QR fixo ou chave da loja) | `20` (PIX Estático) | nenhum (a SEFAZ recusa o grupo de cartão no 20: rejeição 963) |
| Conta na casa (`account`, fiado) | `05` (Cartão da Loja, crediário) | nenhum |
| Saldo do cliente na casa (`store_credit`) | `21` (Crédito em Loja) | nenhum |
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
DANFE no pedido. Repita para as seis: `03`, `04`, `17`, `20`, `99` e `01` com troco (o `20` sai de uma venda mista no PDV com "Recebi o Pix").

## O que conferir em cada nota

No XML autorizado (link `caminho_xml_nota_fiscal` da resposta da Focus):

1. **Status autorizado**, com protocolo. Rejeição é o achado: anote código e motivo.
2. `03`/`04`/`17`: dentro de `<detPag>`, o grupo `<card>` com `<tpIntegra>2</tpIntegra>`.
   A rejeição que este grupo evita é a **391** (regra YA04-10), que na NFC-e vale para
   cartão E Pix.
3. `99`: `<xPag>` presente, com a frase do adapter.
4. Dinheiro com troco: `<vPag>` do dinheiro igual ao entregue, `<vTroco>` igual ao troco,
   e `Σ vPag − vTroco = vNF`.
5. DANFE: a forma de pagamento impressa bate com a do balcão.

Guarde o XML e a resposta de cada nota como evidência no PR que fechar o F2.

## Decisões (24/10/2026)

O dono pediu que a casa decidisse pela norma, sem esperar o contador. Cada código abaixo
vem da tabela de meios de pagamento da NT 2023.004, atualizada pelo Informe Técnico
2024.002 (válida desde 01/07/2024), e da regra YA04-10 da NT 2025.001.

- **Pix: 17 ou 20 conforme a origem.** `17` "PIX Dinâmico" é o Pix com QR ou URL
  dinâmicos, isto é, a cobrança com txid que a Efí gera. `20` "PIX Estático" é o "PIX
  realizado com QR Code estático ou por meio de transferência", que é o "Recebi o Pix"
  atestado pelo operador (`tenders[].pix_confirmed_by`).
- **Pix dinâmico leva o grupo de cartão; o estático, não.** A regra YA04-10 (rejeição
  391) exige o grupo `card` na NFC-e para `03`, `04` e `17`. No `20` a SEFAZ do Paraná
  recusa o grupo (rejeição 963, "Tipo de pagamento não aceita o grupo de cartões ou
  boletos"), medido em homologação em 27/10/2026. Uma das fontes de 24/10 dizia que o 20
  também levava o grupo: estava errada.
- **Conta na casa: 05.** A tabela descreve o `05` como "Cartão da loja, na forma de
  crediário etc.", que é o fiado. O `21` é "Crédito em loja decorrente de valor pago
  anteriormente, de devolução de mercadoria", o contrário da conta na casa; ele fica para
  o saldo que o cliente já tem (`store_credit`).
- **tpIntegra: 2 em todas as formas, por ora.** O `1` (integrado: TEF ou comércio
  eletrônico) descreve com mais rigor a loja online e o Pix da cobrança Efí, mas obriga o
  CNPJ da instituição de pagamento e o código de autorização (`cAut`, obrigatório em
  todas as UFs desde a NT 2025.001). O pedido ainda não grava o `authorization_code` da
  Stripe. O `2` passa na regra 391 sem esses campos.

### tpIntegra

Passo seguinte, depois do go-live: gravar o `authorization_code` do cartão Stripe
(`charge.payment_method_details.card.authorization_code`, API 2024-09-30 ou mais nova) e
usar o `e2e_id` do Pix Efí como `cAut`, com o CNPJ da instituição (Efí S.A., 09.089.356/0001-18;
o da Stripe a conferir), e então mandar `tipo_integracao: "1"` nessas duas formas. Se a
SEFAZ do Paraná exigir vinculação do pagamento eletrônico antes disso, este passo sobe de
prioridade.

## Prova em homologação (27/10/2026, alpha)

| Forma | Pedido | NFC-e | Resultado |
|---|---|---|---|
| `04` débito | PDV-261027-Z64 | 719 | autorizada (cStat 100), `<card><tpIntegra>2</tpIntegra></card>` |
| `03` crédito | PDV-261027-Z06 | 720 | autorizada (cStat 100), `<card><tpIntegra>2</tpIntegra></card>` |
| `17` Pix da cobrança | PDV-261027-D55 | 721 | autorizada (cStat 100), `<card><tpIntegra>2</tpIntegra></card>` |
| `01` dinheiro com troco | PDV-261027-J37 | 722 | autorizada (cStat 100), `vPag` 10,00, `vTroco` 1,00, `vNF` 9,00 |
| `01` + `20` venda mista com "Recebi o Pix" | PDV-261027-N09 | 723 | 27/10: **rejeição 963** com o grupo `card` no `20`. 28/10, depois do #2023 (o `20` sem grupo), "Reprocessar NFC-e" no Gestor: **autorizada** (protocolo 141260001773024), DANFE com "Dinheiro R$ 5,00" e "PIX Estático R$ 4,00" |
| `99` outros | nenhum | nenhuma | não provado: o PDV não tem essa forma; sai de pedido iFood ou de cartão Stripe pré-pago |
