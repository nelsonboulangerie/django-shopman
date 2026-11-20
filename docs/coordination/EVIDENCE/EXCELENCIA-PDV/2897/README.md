# #2897: o saldo da encomenda em Pix no balcão (prévia)

Gesto de dinheiro tem uma tela só (dono, 16/11/2026). O Pix entra pela mesma tela de Pagamento
do "Receber e entregar" (#2903), do jeito que a venda de balcão recebe Pix: o mesmo QR
(`PosPaymentResult`), a mesma Tela do cliente e a mesma espera (`usePixStatusPoll`).

## Como foi capturado

- **PDV de verdade**: Django local (`:8075`, banco local `shopman_pdv_e5`, `seed --flush`),
  PDV e Cozinha em build de produção, worker de directives ligado, host `pdve5.localhost`.
  Nunca produção. **Pagamento só no simulador local** (`payment_mock`): nada de Efí, cobrança
  real, SMS, e-mail ou WhatsApp.
- **Papéis**: Joyce (Gerente) inicia o dispositivo; Fran (Caixa) opera com PIN. A encomenda nasce
  pela tela (hoje, retirada, a pagar na retirada) e é aberta pela lista das Encomendas.
- **Jornada**: `surfaces/pos-nuxt/tests/e2e-live/j6-receber-e-entregar.live.spec.ts`, describe
  "J6 Pix no saldo", em 375 px e 1366 px, em duas rodadas:
  - `PDV_LIVE_J6_PIX=pago` com `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true` (atraso de 25 s): o
    simulador faz o papel do banco e confirma o Pix pelo caminho canônico (`mock_pix.confirm` →
    `confirm_pix`);
  - `PDV_LIVE_J6_PIX=nao-chega` sem confirmação.
- **Ajustes declarados do ambiente** (só no banco local, nenhum muda regra de negócio):
  - trava automática do PDV em 900 s (o harness);
  - horário de sexta e expediente da equipe até 23h59 (a captura rodou depois das 18h);
  - na rodada `nao-chega`, o prazo do Pix do canal `pdv` em 1 minuto
    (`config.payment.timeout_minutes`), para o vencimento caber na jornada (o padrão é 10).
    Desfeito depois da rodada.
- **Antes**: o Pagamento do saldo do #2903 (código final dele, capturado na prévia do WP-E5,
  `../WP-E5/depois/*/a02-pagamento-com-o-saldo.png`): as formas eram só dinheiro, crédito e débito.

## Antes (`antes/375`, `antes/1366`)

| Arquivo | O que mostra |
|---|---|
| `01-pagamento-do-saldo-sem-pix.png` | o saldo na tela de Pagamento, sem Pix entre as formas |

## Depois (`depois/375`, `depois/1366`)

| Arquivo | O que mostra |
|---|---|
| `a01-pix-escolhido.png` | o Pagamento do saldo com o Pix escolhido (a mesma tela da venda) |
| `a02-pix-qr-na-tela.png` | "Receber e entregar" com Pix: o QR da venda, o copia e cola, "A confirmação chega aqui sozinha." e a saída "Receber em outra forma" |
| `a02b-tela-do-cliente-pix.png` | a Tela do cliente: "Total a pagar" e o mesmo QR grande da venda em Pix |
| `a03-pix-confirmado-entregue.png` | o banco confirma: "Pix de R$ X confirmado. Encomenda entregue." e o PDV volta à lista (a Tela do cliente volta às boas-vindas) |
| `b01-pix-nao-confirmado.png` | o Pix venceu: o aviso abaixo das barras, primeiro conteúdo, com o botão que resolve ("Gerar outro Pix"); a saída "Receber em outra forma" segue à vista |
| `b02-recebe-em-dinheiro-depois-do-pix.png` | o operador volta às formas e recebe em dinheiro (nota de R$ 100, troco grande) |
| `b03-entregue-em-dinheiro.png` | entregue em dinheiro; o Pix do balcão ficou **cancelado** no servidor antes do acerto (o `counter_takeover` do "Receber e entregar"), sem cobrança dupla |

## Auditoria

`auditoria.txt`, gerado pela própria jornada: contraste (mínimo 4,5:1), letra (mínimo 12 px),
dentro da tela, nada cortado, nada encoberto (cada texto rolado até o meio da área visível) e
transbordo horizontal zero. Resultado: nenhuma reprovação nos dois tamanhos.

Notas:

- O aviso do topo é o `alerts` do cabeçalho do kit (`OperatorPageHeader`): abaixo das barras,
  com X e o botão que resolve. O texto dele não entra nesta auditoria (é componente do kit,
  auditado na suíte do kit).
- Dentro do QR vencido, a linha "Não confirmamos o PIX automaticamente. Confira no gestor ou gere
  um novo pagamento." é a do mesmo componente da venda (`PosPaymentResult`), sem mudança. Aqui
  os dois gestos que resolvem estão na tela: "Gerar outro Pix" (no aviso e no rodapé do QR) e
  "Receber em outra forma".
